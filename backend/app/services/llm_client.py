"""
LLM Client with retry logic and multi-provider support.
"""
import asyncio
import base64
import json
import logging
import random
import re
import time
from collections import deque
from typing import Optional, Any
from types import SimpleNamespace

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account
from openai import AsyncOpenAI
from openai import RateLimitError, APIError

from app.core.config import settings
from app.core.time import now_utc
from app.services.run_policy import build_terminal_llm_failure_action, current_run_class
from app.services.runtime_config import runtime_config_service
from app.services.usage_budget import usage_budget

logger = logging.getLogger(__name__)


# Provider configurations
OPENROUTER_CONFIG = {
    "base_url": "https://openrouter.ai/api/v1",
    "models": {
        # Attribution cohorts (seeded explicitly in scripts/seed_agents.py)
        "or_gpt_oss_120b": "openai/gpt-oss-120b",
        "or_qwen3_235b_a22b_2507": "qwen/qwen3-235b-a22b-2507",
        "or_deepseek_v3_2": "deepseek/deepseek-v3.2",
        "or_deepseek_chat_v3_1": "deepseek/deepseek-chat-v3.1",
        "or_gpt_oss_20b": "openai/gpt-oss-20b",
        "or_qwen3_32b": "qwen/qwen3-32b",
        "or_mistral_small_3_1_24b_free": "mistralai/mistral-small-3.1-24b-instruct:free",
        # Legacy model_type values kept for backward compatibility.
        "claude-sonnet-4": "deepseek/deepseek-r1-0528:free",
        "gpt-4o-mini": "stepfun/step-3.5-flash:free",
        "claude-haiku": "arcee-ai/trinity-large-preview:free",
        "llama-3.3-70b": "stepfun/step-3.5-flash:free",
        "llama-3.1-8b": "meta-llama/llama-3.2-3b-instruct:free",
        "gemini-flash": "qwen/qwen3-coder:free",
    },
}

MISTRAL_CONFIG = {
    "base_url": "https://api.mistral.ai/v1",
    "models": {
        # Cohort label kept stable for DB compatibility.
        # Resolved direct model is configurable via MISTRAL_SMALL_MODEL.
        "or_mistral_small_3_1_24b": "mistral-small-latest",
    },
}

GEMINI_CONFIG = {
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    "models": {
        # Stable Gemini cohort keys (seeded explicitly in scripts/seed_agents.py)
        "gm_gemini_2_5_flash": "gemini-2.5-flash",
        # Canary E showed gemini-2.0-flash was functionally unavailable under
        # run pressure. Keep the cohort key stable for tier attribution, but
        # route it to the stable Gemini 2.5 Flash model before Canary F.
        "gm_gemini_2_0_flash": "gemini-2.5-flash",
        # Aborted Canary F smoke showed the remaining Gemini Lite and OpenRouter
        # free cohorts were still provider-confounded under burst pressure. Keep
        # cohort labels stable, but route these fragile labels to the stable
        # direct Gemini path for the provider-stabilized Canary F rerun.
        "gm_gemini_2_0_flash_lite": "gemini-2.5-flash",
        "or_gpt_oss_20b_free": "gemini-2.5-flash",
        "or_qwen3_4b_free": "gemini-2.5-flash",
    },
}

VERTEX_GEMINI_CONFIG = {
    "provider": "google_vertex",
    "scopes": ("https://www.googleapis.com/auth/cloud-platform",),
}

_ACTION_FORMAT_RETRY_SUFFIX = (
    "\n\nFORMAT RETRY:\n"
    "- Your previous output could not be parsed.\n"
    "- Return exactly one valid JSON object and nothing else.\n"
    "- Include an `action` field.\n"
    "- Do not use markdown code fences.\n"
)


class RetryableCompletionError(RuntimeError):
    """Raised when provider output is present but unusable and worth retrying."""

    def __init__(self, reason: str, finish_reason: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.finish_reason = finish_reason


class LLMConfigurationError(RuntimeError):
    """Raised when model/provider routing is invalid for the current config."""


class VertexGeminiRoute:
    """Sentinel route for Gemini calls made through Google Vertex AI."""


class LLMClient:
    """Unified LLM client supporting multiple providers."""
    
    def __init__(self):
        self.openrouter_client = AsyncOpenAI(
            base_url=OPENROUTER_CONFIG["base_url"],
            api_key=settings.OPENROUTER_API_KEY,
        )
        self.mistral_client = AsyncOpenAI(
            base_url=(getattr(settings, "MISTRAL_BASE_URL", "") or MISTRAL_CONFIG["base_url"]),
            api_key=settings.MISTRAL_API_KEY,
        )
        self.gemini_client = AsyncOpenAI(
            base_url=(getattr(settings, "GEMINI_BASE_URL", "") or GEMINI_CONFIG["base_url"]),
            api_key=settings.GEMINI_API_KEY,
        )
        self.vertex_gemini_client = VertexGeminiRoute()
        self._vertex_credentials = None
        self._vertex_auth_lock = asyncio.Lock()

        # Concurrency guards to reduce provider rate limits.
        self._openrouter_sem = asyncio.Semaphore(max(1, int(getattr(settings, "OPENROUTER_MAX_CONCURRENCY", 6) or 6)))
        self._mistral_sem = asyncio.Semaphore(max(1, int(getattr(settings, "MISTRAL_MAX_CONCURRENCY", 4) or 4)))
        self._gemini_sem = asyncio.Semaphore(max(1, int(getattr(settings, "GEMINI_MAX_CONCURRENCY", 4) or 4)))

        # Client-side RPM limiter to avoid tripping strict OpenRouter free-tier limits.
        # With 20 agents and a 150s loop, steady-state is ~8 RPM; retries can push higher.
        self._openrouter_rpm = max(1, int(getattr(settings, "OPENROUTER_RPM_LIMIT", 6) or 6))
        self._openrouter_window_s = 60.0
        self._openrouter_calls: deque[float] = deque()
        self._openrouter_rpm_lock = asyncio.Lock()
        self._gemini_rpm = max(1, int(getattr(settings, "GEMINI_RPM_LIMIT", 8) or 8))
        self._gemini_window_s = 60.0
        self._gemini_calls: deque[float] = deque()
        self._gemini_rpm_lock = asyncio.Lock()

        configured_run_id = str(getattr(settings, "SIMULATION_RUN_ID", "") or "").strip()
        self._default_run_id = configured_run_id or now_utc().strftime("run-%Y%m%dT%H%M%SZ")

    @staticmethod
    def _vertex_gemini_enabled() -> bool:
        return bool(getattr(settings, "VERTEX_GEMINI_ENABLED", False))

    @staticmethod
    def _vertex_service_account_info() -> dict[str, Any]:
        raw = str(getattr(settings, "VERTEX_GEMINI_SERVICE_ACCOUNT_JSON", "") or "").strip()
        if not raw:
            raise LLMConfigurationError("Vertex Gemini service account JSON is not configured")
        if raw.startswith("@"):
            with open(raw[1:], "r", encoding="utf-8") as f:
                return json.load(f)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                decoded = base64.b64decode(raw).decode("utf-8")
                return json.loads(decoded)
            except Exception as exc:
                raise LLMConfigurationError("Vertex Gemini service account JSON is invalid") from exc

    def _vertex_project_id(self) -> str:
        configured = str(getattr(settings, "VERTEX_GEMINI_PROJECT_ID", "") or "").strip()
        if configured:
            return configured
        info = self._vertex_service_account_info()
        project_id = str(info.get("project_id") or "").strip()
        if not project_id:
            raise LLMConfigurationError("Vertex Gemini project id is not configured")
        return project_id

    async def _vertex_access_token(self) -> str:
        async with self._vertex_auth_lock:
            if self._vertex_credentials is None:
                self._vertex_credentials = service_account.Credentials.from_service_account_info(
                    self._vertex_service_account_info(),
                    scopes=list(VERTEX_GEMINI_CONFIG["scopes"]),
                )
            if not self._vertex_credentials.valid:
                await asyncio.to_thread(self._vertex_credentials.refresh, GoogleAuthRequest())
            token = str(self._vertex_credentials.token or "")
            if not token:
                raise LLMConfigurationError("Vertex Gemini service account did not return an access token")
            return token

    async def _create_vertex_gemini_completion(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> Any:
        project_id = self._vertex_project_id()
        location = str(getattr(settings, "VERTEX_GEMINI_LOCATION", "") or "global").strip()
        base_url = str(getattr(settings, "VERTEX_GEMINI_BASE_URL", "") or "https://aiplatform.googleapis.com").rstrip("/")
        token = await self._vertex_access_token()
        url = (
            f"{base_url}/v1/projects/{project_id}/locations/{location}"
            f"/publishers/google/models/{model_name}:generateContent"
        )
        generation_config: dict[str, Any] = {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        }
        if model_name.strip().lower().startswith("gemini-2.5-flash"):
            generation_config["thinkingConfig"] = {"thinkingBudget": 0}
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": generation_config,
        }
        async with httpx.AsyncClient(timeout=75.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        response.raise_for_status()
        body = response.json()
        candidates = body.get("candidates") or []
        first = candidates[0] if candidates else {}
        parts = ((first.get("content") or {}).get("parts") or [])
        text_parts = [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")]
        usage = body.get("usageMetadata") or {}
        return SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=int(usage.get("promptTokenCount") or 0),
                completion_tokens=int(usage.get("candidatesTokenCount") or 0),
                total_tokens=int(usage.get("totalTokenCount") or 0),
            ),
            choices=[
                SimpleNamespace(
                    finish_reason=first.get("finishReason"),
                    message=SimpleNamespace(content="\n".join(text_parts).strip()),
                )
            ],
        )

    def _current_run_id(self) -> str:
        configured_run_id = str(runtime_config_service.get_effective_value_cached("SIMULATION_RUN_ID") or "").strip()
        if configured_run_id:
            return configured_run_id[:64]
        return self._default_run_id

    async def _throttle_openrouter(self) -> None:
        now = time.monotonic()
        raw_rpm_limit = runtime_config_service.get_effective_value_cached("OPENROUTER_RPM_LIMIT")
        rpm_limit = max(
            1,
            int(self._openrouter_rpm if raw_rpm_limit is None else raw_rpm_limit),
        )
        async with self._openrouter_rpm_lock:
            while self._openrouter_calls and (now - self._openrouter_calls[0]) > self._openrouter_window_s:
                self._openrouter_calls.popleft()

            if len(self._openrouter_calls) < rpm_limit:
                self._openrouter_calls.append(now)
                return

            oldest = self._openrouter_calls[0]
            wait_s = max(0.0, self._openrouter_window_s - (now - oldest)) + random.random() * 0.2

        await asyncio.sleep(wait_s)
        return await self._throttle_openrouter()

    async def _throttle_gemini(self) -> None:
        now = time.monotonic()
        raw_rpm_limit = runtime_config_service.get_effective_value_cached("GEMINI_RPM_LIMIT")
        rpm_limit = max(
            1,
            int(self._gemini_rpm if raw_rpm_limit is None else raw_rpm_limit),
        )
        async with self._gemini_rpm_lock:
            while self._gemini_calls and (now - self._gemini_calls[0]) > self._gemini_window_s:
                self._gemini_calls.popleft()

            if len(self._gemini_calls) < rpm_limit:
                self._gemini_calls.append(now)
                return

            oldest = self._gemini_calls[0]
            wait_s = max(0.0, self._gemini_window_s - (now - oldest)) + random.random() * 0.2

        await asyncio.sleep(wait_s)
        return await self._throttle_gemini()

    @staticmethod
    def _extract_text_from_message(message: Any) -> Optional[str]:
        """
        Normalize provider/library response shapes into plain text.

        OpenAI-compatible APIs sometimes return:
        - `message.content` as a string
        - `message.content` as a list of parts (e.g. [{"type":"text","text":"..."}])
        - `message.content` as None (rare provider edge cases)
        """
        if message is None:
            return None

        content = getattr(message, "content", None)

        if isinstance(content, str):
            text = content.strip()
            return text or None

        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    if part.strip():
                        parts.append(part.strip())
                    continue
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                    continue
                # Some SDKs/providers return typed objects for content parts.
                # Be liberal in what we accept: look for common attributes.
                text_attr = getattr(part, "text", None)
                if isinstance(text_attr, str) and text_attr.strip():
                    parts.append(text_attr.strip())
                    continue
                content_attr = getattr(part, "content", None)
                if isinstance(content_attr, str) and content_attr.strip():
                    parts.append(content_attr.strip())
                    continue
                value_attr = getattr(part, "value", None)
                if isinstance(value_attr, str) and value_attr.strip():
                    parts.append(value_attr.strip())
                    continue
            joined = "\n".join(parts).strip()
            return joined or None

        return None

    @classmethod
    def _extract_text_from_response(cls, response: Any) -> Optional[str]:
        try:
            choices = getattr(response, "choices", None) or []
            first = choices[0] if choices else None
            message = getattr(first, "message", None)
            return cls._extract_text_from_message(message)
        except Exception:
            return None

    @staticmethod
    def _debug_choice_meta(response: Any) -> dict:
        try:
            choices = getattr(response, "choices", None) or []
            first = choices[0] if choices else None
            finish = getattr(first, "finish_reason", None)
            usage = getattr(response, "usage", None)
            return {
                "finish_reason": finish,
                "has_choices": bool(choices),
                "usage": getattr(usage, "model_dump", lambda: usage)() if usage else None,
            }
        except Exception:
            return {"finish_reason": None, "has_choices": None, "usage": None}

    @staticmethod
    def _extract_byok_used(response: Any, provider_name: str) -> bool | None:
        """
        Return BYOK signal when provider exposes it.

        OpenRouter exposes `usage.is_byok` in OpenAI-compatible responses.
        Return None when unknown/unavailable to avoid false attribution.
        """
        if provider_name != "openrouter":
            return None
        try:
            usage = getattr(response, "usage", None)
            if usage is None:
                return None
            value = getattr(usage, "is_byok", None)
            if value is None and isinstance(usage, dict):
                value = usage.get("is_byok")
            if value is None and hasattr(usage, "model_dump"):
                dumped = usage.model_dump()
                if isinstance(dumped, dict):
                    value = dumped.get("is_byok")
            if value is None:
                return None
            return bool(value)
        except Exception:
            return None

    def _provider_name_for_client(self, client: AsyncOpenAI) -> str:
        if client is self.openrouter_client:
            return "openrouter"
        if client is self.gemini_client:
            return "gemini"
        if client is self.vertex_gemini_client:
            return VERTEX_GEMINI_CONFIG["provider"]
        return "mistral"

    @staticmethod
    def _gemini_completion_extra_body(model_name: str) -> dict[str, Any] | None:
        """
        Gemini 2.5 Flash uses dynamic thinking by default. For short action JSON
        completions, hidden thinking can consume the output budget and leave
        truncated JSON. Disable thinking on the action route to preserve the
        provider cohort while keeping checkpoint responses parseable.
        """
        normalized = (model_name or "").strip().lower()
        if normalized.startswith("gemini-2.5-flash"):
            return {"extra_body": {"google": {"thinking_config": {"thinking_budget": 0}}}}
        return None

    async def _create_completion_with_budget(
        self,
        *,
        client: AsyncOpenAI,
        agent_id: int | None,
        checkpoint_number: int | None,
        usage_run_id: str | None = None,
        model_type: str,
        model_name: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        fallback_used: bool,
    ) -> tuple[Any | None, str, str, str | None]:
        """
        Execute one provider request with budget checks and usage recording.

        Returns:
            response, used_model_name, provider_name, blocked_reason
        """
        provider_name = self._provider_name_for_client(client)
        decision = usage_budget.preflight(provider=provider_name, model_name=model_name)
        if not decision.allowed:
            logger.warning(
                "LLM request blocked by budget (provider=%s model=%s reason=%s calls_total=%s cost=%.6f)",
                provider_name,
                model_name,
                decision.reason,
                decision.snapshot.calls_total,
                decision.snapshot.estimated_cost_usd,
            )
            return None, model_name, provider_name, decision.reason

        used_model_name = model_name
        used_max_tokens = max_tokens
        used_temperature = temperature
        if decision.soft_cap_reached:
            reduced_tokens = max(16, max_tokens // 2 if max_tokens > 1 else max_tokens)
            used_max_tokens = min(max_tokens, reduced_tokens)
            used_temperature = min(temperature, 0.5)
            logger.info(
                "LLM soft-cap degrade active (provider=%s model=%s max_tokens=%s->%s)",
                provider_name,
                model_name,
                max_tokens,
                used_max_tokens,
            )

        if client is self.openrouter_client:
            sem = self._openrouter_sem
        elif client is self.gemini_client or client is self.vertex_gemini_client:
            sem = self._gemini_sem
        else:
            sem = self._mistral_sem
        started = time.monotonic()
        try:
            async with sem:
                if client is self.openrouter_client:
                    await self._throttle_openrouter()
                elif client is self.gemini_client or client is self.vertex_gemini_client:
                    await self._throttle_gemini()
                if client is self.vertex_gemini_client:
                    response = await self._create_vertex_gemini_completion(
                        model_name=used_model_name,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        max_tokens=used_max_tokens,
                        temperature=used_temperature,
                    )
                else:
                    extra_body = (
                        self._gemini_completion_extra_body(used_model_name)
                        if client is self.gemini_client
                        else None
                    )
                    request_kwargs = {
                        "model": used_model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": used_max_tokens,
                        "temperature": used_temperature,
                    }
                    if extra_body:
                        request_kwargs["extra_body"] = extra_body
                    response = await client.chat.completions.create(
                        **request_kwargs,
                    )
        except Exception as e:
            latency_ms = int((time.monotonic() - started) * 1000)
            usage_budget.record_call(
                run_id=(str(usage_run_id or "").strip()[:64] or self._current_run_id()),
                agent_id=agent_id,
                checkpoint_number=checkpoint_number,
                provider=provider_name,
                model_name=used_model_name,
                model_type=model_type,
                resolved_model_name=used_model_name,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                success=False,
                fallback_used=fallback_used,
                byok_used=None,
                latency_ms=latency_ms,
                error_type=e.__class__.__name__,
            )
            raise

        latency_ms = int((time.monotonic() - started) * 1000)
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens))
        byok_used = self._extract_byok_used(response=response, provider_name=provider_name)
        usage_budget.record_call(
            run_id=(str(usage_run_id or "").strip()[:64] or self._current_run_id()),
            agent_id=agent_id,
            checkpoint_number=checkpoint_number,
            provider=provider_name,
            model_name=used_model_name,
            model_type=model_type,
            resolved_model_name=used_model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            success=True,
            fallback_used=fallback_used,
            byok_used=byok_used,
            latency_ms=latency_ms,
            error_type=None,
        )
        return response, used_model_name, provider_name, None
    
    def _get_client_and_model(self, model_type: str):
        """Get the appropriate client and model name."""
        mistral_default_model = str(
            getattr(settings, "MISTRAL_SMALL_MODEL", MISTRAL_CONFIG["models"]["or_mistral_small_3_1_24b"])
            or MISTRAL_CONFIG["models"]["or_mistral_small_3_1_24b"]
        ).strip()

        # Direct Mistral cohort mapping.
        if model_type in MISTRAL_CONFIG["models"]:
            return self.mistral_client, mistral_default_model
        # Direct Gemini cohort mapping.
        if model_type in GEMINI_CONFIG["models"]:
            if self._vertex_gemini_enabled():
                return self.vertex_gemini_client, GEMINI_CONFIG["models"][model_type]
            return self.gemini_client, GEMINI_CONFIG["models"][model_type]

        # Explicit mappings always take precedence for clean attribution.
        if model_type in OPENROUTER_CONFIG["models"]:
            return self.openrouter_client, OPENROUTER_CONFIG["models"][model_type]

        logger.error("Unknown model type configured for agent routing: %s", model_type)
        raise LLMConfigurationError(f"Unknown model type: {model_type}")
    
    async def get_completion(
        self,
        model_type: str,
        system_prompt: str,
        user_prompt: str,
        agent_id: int | None = None,
        checkpoint_number: int | None = None,
        usage_run_id: str | None = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> Optional[str]:
        """Get a completion with retry logic."""

        has_vertex_gemini = bool(
            self._vertex_gemini_enabled()
            and str(getattr(settings, "VERTEX_GEMINI_SERVICE_ACCOUNT_JSON", "") or "").strip()
        )
        if not settings.OPENROUTER_API_KEY and not settings.MISTRAL_API_KEY and not settings.GEMINI_API_KEY and not has_vertex_gemini:
            logger.error(
                "No provider credentials are set (OPENROUTER_API_KEY/MISTRAL_API_KEY/GEMINI_API_KEY/VERTEX_GEMINI_SERVICE_ACCOUNT_JSON)."
            )
            raise LLMConfigurationError("No configured LLM providers are available")

        client, model_name = self._get_client_and_model(model_type)
        if client is self.openrouter_client and not settings.OPENROUTER_API_KEY:
            logger.error("Selected OpenRouter route for model_type=%s but OPENROUTER_API_KEY is not set.", model_type)
            raise LLMConfigurationError("OpenRouter API key is not configured")
        if client is self.mistral_client and not settings.MISTRAL_API_KEY:
            logger.error("Selected Mistral route for model_type=%s but MISTRAL_API_KEY is not set.", model_type)
            raise LLMConfigurationError("Mistral API key is not configured")
        if client is self.gemini_client and not settings.GEMINI_API_KEY:
            logger.error("Selected Gemini route for model_type=%s but GEMINI_API_KEY is not set.", model_type)
            raise LLMConfigurationError("Gemini API key is not configured")
        if client is self.vertex_gemini_client and not has_vertex_gemini:
            logger.error(
                "Selected Vertex Gemini route for model_type=%s but VERTEX_GEMINI_SERVICE_ACCOUNT_JSON is not set.",
                model_type,
            )
            raise LLMConfigurationError("Vertex Gemini service account is not configured")
        
        attempt_max_tokens = max(64, int(max_tokens or 64))
        max_retry_tokens = 900

        for attempt in range(max_retries):
            try:
                response, used_model_name, provider_name, blocked_reason = await self._create_completion_with_budget(
                    client=client,
                    agent_id=agent_id,
                    checkpoint_number=checkpoint_number,
                    usage_run_id=usage_run_id,
                    model_type=model_type,
                    model_name=model_name,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=attempt_max_tokens,
                    temperature=temperature,
                    fallback_used=False,
                )
                if blocked_reason:
                    return None

                # Guard against occasional provider/library edge cases where a 200 OK yields
                # an empty/partial payload.
                content = self._extract_text_from_response(response)
                if not content:
                    meta = self._debug_choice_meta(response)
                    finish_reason = str(meta.get("finish_reason") or "")
                    reason = "empty_content_length" if finish_reason == "length" else "empty_content"
                    logger.warning(
                        "Empty completion content (provider=%s model=%s attempt=%s/%s meta=%s)",
                        provider_name,
                        used_model_name,
                        attempt + 1,
                        max_retries,
                        meta,
                    )
                    raise RetryableCompletionError(reason=reason, finish_reason=finish_reason or None)

                return content

            except RetryableCompletionError as e:
                wait_time = 0.5 + random.random() * 0.75
                if e.finish_reason == "length":
                    bumped_tokens = min(max_retry_tokens, max(attempt_max_tokens + 120, int(attempt_max_tokens * 1.4)))
                    if bumped_tokens > attempt_max_tokens:
                        logger.info(
                            "Retrying completion after truncation (model_type=%s tokens=%s->%s attempt=%s/%s)",
                            model_type,
                            attempt_max_tokens,
                            bumped_tokens,
                            attempt + 1,
                            max_retries,
                        )
                        attempt_max_tokens = bumped_tokens
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(wait_time)

            except LLMConfigurationError:
                raise
                
            except RateLimitError as e:
                wait_time = (2 ** attempt) + random.random()
                logger.warning(f"Rate limited, waiting {wait_time:.2f}s (attempt {attempt + 1})")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(wait_time)
                
            except APIError as e:
                logger.error(f"API error: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1 + random.random() * 0.25)
                
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1 + random.random() * 0.25)
        
        return None


# Singleton instance
llm_client = LLMClient()


async def get_agent_action(
    agent_id: int,
    model_type: str,
    system_prompt: str,
    context_prompt: str,
    checkpoint_number: int | None = None,
    run_class: str | None = None,
) -> Optional[dict]:
    """Get an action decision from an agent."""

    resolved_run_class = run_class or current_run_class()

    try:
        raw_max_action_tokens = runtime_config_service.get_effective_value_cached("LLM_ACTION_MAX_TOKENS")
        max_action_tokens = max(
            128,
            int(settings.LLM_ACTION_MAX_TOKENS if raw_max_action_tokens is None else raw_max_action_tokens),
        )
        raw_parse_retry_attempts = runtime_config_service.get_effective_value_cached(
            "LLM_ACTION_PARSE_RETRY_ATTEMPTS"
        )
        parse_retry_attempts = max(
            0,
            int(
                settings.LLM_ACTION_PARSE_RETRY_ATTEMPTS
                if raw_parse_retry_attempts is None
                else raw_parse_retry_attempts
            ),
        )
        base_context_prompt = context_prompt
        last_parse_meta: dict[str, Any] | None = None

        for parse_attempt in range(parse_retry_attempts + 1):
            if parse_attempt == 0:
                effective_prompt = base_context_prompt
            else:
                parse_error = (last_parse_meta or {}).get("error_type") or "parse_error"
                effective_prompt = (
                    f"{base_context_prompt}{_ACTION_FORMAT_RETRY_SUFFIX}"
                    f"- Previous parse error: {parse_error}\n"
                )

            response = await llm_client.get_completion(
                model_type=model_type,
                system_prompt=system_prompt,
                user_prompt=effective_prompt,
                agent_id=agent_id,
                checkpoint_number=checkpoint_number,
                max_tokens=max_action_tokens,
                temperature=0.7,
            )

            if not response:
                if parse_attempt < parse_retry_attempts:
                    continue
                return build_terminal_llm_failure_action(
                    agent_id=agent_id,
                    reason="No response from LLM",
                    run_class=resolved_run_class,
                    failure_stage="terminal_llm_failure",
                )

            action_data, parse_meta = parse_action_response_with_meta(response)
            parse_meta["attempt"] = parse_attempt + 1
            parse_meta["max_attempts"] = parse_retry_attempts + 1
            last_parse_meta = parse_meta

            # Parsed JSON action object as requested.
            if parse_meta.get("ok"):
                action_data["_llm_meta"] = {"parse": parse_meta}
                return action_data

            if parse_attempt < parse_retry_attempts:
                logger.warning(
                    "Action parse failed; retrying same model (agent=%s model_type=%s parse_error=%s attempt=%s/%s)",
                    agent_id,
                    model_type,
                    parse_meta.get("error_type"),
                    parse_attempt + 1,
                    parse_retry_attempts + 1,
                )
                # Give retries more room so JSON isn't cut off.
                max_action_tokens = min(900, max_action_tokens + 120)
                continue

            fallback_action = build_terminal_llm_failure_action(
                agent_id=agent_id,
                reason=f"Unusable checkpoint output: {parse_meta.get('error_type') or 'parse_error'}",
                run_class=resolved_run_class,
                failure_stage="invalid_checkpoint_output",
            )
            fallback_action["_llm_meta"] = {"parse": parse_meta}
            return fallback_action
        
    except Exception as e:
        logger.error(f"Error getting action for agent {agent_id}: {e}")
        return build_terminal_llm_failure_action(
            agent_id=agent_id,
            reason=str(e),
            run_class=resolved_run_class,
            failure_stage="terminal_llm_failure",
        )


def parse_action_response(response: str) -> dict:
    """Parse LLM response into structured action."""
    action, _ = parse_action_response_with_meta(response)
    return action


def parse_action_response_with_meta(response: str) -> tuple[dict, dict]:
    """
    Parse LLM response into a structured action and parse telemetry metadata.

    Parse metadata fields:
    - ok: True when a JSON object with `action` field was parsed.
    - parse_status: stable status label for analytics.
    - error_type: machine-friendly failure reason for retries/analysis.
    - likely_truncated: best-effort signal for outputs cut by token limits.
    """
    raw = (response or "").strip()

    base_meta: dict[str, Any] = {
        "ok": False,
        "parse_status": "unknown",
        "error_type": None,
        "likely_truncated": False,
        "response_chars": len(raw),
    }

    if not raw:
        meta = dict(base_meta)
        meta.update({"parse_status": "empty_response", "error_type": "empty_response"})
        return {"action": "idle", "reasoning": "Could not parse response"}, meta

    json_patterns = [
        r"```json\s*(\{.*?\})\s*```",
        r"```\s*(\{.*?\})\s*```",
        r"\{.*\}",
    ]

    last_decode_error: json.JSONDecodeError | None = None
    for pattern in json_patterns:
        match = re.search(pattern, raw, re.DOTALL)
        if not match:
            continue
        json_str = match.group(1) if match.lastindex else match.group()
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as decode_error:
            last_decode_error = decode_error
            continue

        if not isinstance(parsed, dict):
            meta = dict(base_meta)
            meta.update({"parse_status": "non_object_json", "error_type": "non_object_json"})
            return {"action": "idle", "reasoning": "Could not parse response"}, meta

        action_value = parsed.get("action")
        if not isinstance(action_value, str) or not action_value.strip():
            meta = dict(base_meta)
            meta.update({"parse_status": "json_missing_action", "error_type": "json_missing_action"})
            return {"action": "idle", "reasoning": "Could not parse response"}, meta

        meta = dict(base_meta)
        meta.update({"ok": True, "parse_status": "json_ok"})
        return parsed, meta

    jsonish_payload = raw.lstrip().startswith("{") or '"action"' in raw

    # No JSON object was parsed. If the model appears to be emitting malformed JSON,
    # treat this as unusable structured output rather than publishing the raw blob.
    if jsonish_payload:
        meta = dict(base_meta)
        if last_decode_error is not None:
            meta.update(
                {
                    "parse_status": "json_decode_error_rejected",
                    "error_type": "json_decode_error",
                    "likely_truncated": _is_likely_truncated_json(raw, last_decode_error),
                }
            )
        else:
            meta.update(
                {
                    "parse_status": "json_not_found_rejected",
                    "error_type": "json_not_found",
                    "likely_truncated": raw.count("{") > raw.count("}") or raw.endswith(("{", "[", ":", ",", '"')),
                }
            )
        return {"action": "idle", "reasoning": "Could not parse response"}, meta

    # No JSON object was parsed. Keep simulation moving with a safe coercion for plain text.
    clean_response = raw[:2000]
    meta = dict(base_meta)
    if last_decode_error is not None:
        likely_truncated = _is_likely_truncated_json(raw, last_decode_error)
        meta.update(
            {
                "parse_status": "json_decode_error_coerced_forum_post",
                "error_type": "json_decode_error",
                "likely_truncated": likely_truncated,
            }
        )
    else:
        likely_truncated = raw.count("{") > raw.count("}") or raw.endswith(("{", "[", ":", ",", '"'))
        meta.update(
            {
                "parse_status": "json_not_found_coerced_forum_post",
                "error_type": "json_not_found",
                "likely_truncated": likely_truncated,
            }
        )
    return {"action": "forum_post", "content": clean_response}, meta


def _is_likely_truncated_json(raw_response: str, error: json.JSONDecodeError) -> bool:
    """Best-effort signal that malformed JSON was cut off by output limits."""
    stripped = (raw_response or "").rstrip()
    if not stripped:
        return False

    # Unbalanced braces are the strongest signal of cutoff.
    if stripped.count("{") > stripped.count("}"):
        return True

    # Common trailing syntax when generation is cut mid-object.
    if stripped.endswith(("{", "[", ":", ",", '"')):
        return True

    msg = str(getattr(error, "msg", "") or "")
    if "Unterminated string" in msg or "Expecting value" in msg:
        return True

    return False
