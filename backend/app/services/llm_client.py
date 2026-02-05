"""
LLM Client with retry logic and multi-provider support.
"""
import asyncio
import json
import logging
import random
import time
from collections import deque
from typing import Optional, Any
from openai import AsyncOpenAI
from openai import RateLimitError, APIError

from app.core.config import settings
from app.core.time import now_utc

logger = logging.getLogger(__name__)


# Provider configurations
OPENROUTER_CONFIG = {
    "base_url": "https://openrouter.ai/api/v1",
    "models": {
        # NOTE: Pin to explicit :free model IDs to avoid surprise spend.
        # These keys are internal labels stored on Agent.model_type (agents are not told their tier/model).
        "claude-sonnet-4": "deepseek/deepseek-r1-0528:free",
        "gpt-4o-mini": "stepfun/step-3.5-flash:free",
        "claude-haiku": "arcee-ai/trinity-large-preview:free",
        "llama-3.3-70b": "stepfun/step-3.5-flash:free",
        "llama-3.1-8b": "meta-llama/llama-3.2-3b-instruct:free",
        "gemini-flash": "qwen/qwen3-coder:free",
    }
}

GROQ_CONFIG = {
    "base_url": "https://api.groq.com/openai/v1",
    "models": {
        "llama-3.3-70b": "llama-3.3-70b-versatile",
        "llama-3.1-8b": "llama-3.1-8b-instant",
    }
}


class LLMClient:
    """Unified LLM client supporting multiple providers."""
    
    def __init__(self):
        self.openrouter_client = AsyncOpenAI(
            base_url=OPENROUTER_CONFIG["base_url"],
            api_key=settings.OPENROUTER_API_KEY,
        )
        self.groq_client = AsyncOpenAI(
            base_url=GROQ_CONFIG["base_url"],
            api_key=settings.GROQ_API_KEY,
        )

        # Concurrency guards to reduce provider rate limits.
        self._groq_sem = asyncio.Semaphore(max(1, int(getattr(settings, "GROQ_MAX_CONCURRENCY", 2) or 2)))
        self._openrouter_sem = asyncio.Semaphore(max(1, int(getattr(settings, "OPENROUTER_MAX_CONCURRENCY", 6) or 6)))

        # Client-side RPM limiter to avoid tripping strict OpenRouter free-tier limits.
        # With 20 agents and a 150s loop, steady-state is ~8 RPM; retries can push higher.
        self._openrouter_rpm = max(1, int(getattr(settings, "OPENROUTER_RPM_LIMIT", 6) or 6))
        self._openrouter_window_s = 60.0
        self._openrouter_calls: deque[float] = deque()
        self._openrouter_rpm_lock = asyncio.Lock()

    async def _throttle_openrouter(self) -> None:
        now = time.monotonic()
        async with self._openrouter_rpm_lock:
            while self._openrouter_calls and (now - self._openrouter_calls[0]) > self._openrouter_window_s:
                self._openrouter_calls.popleft()

            if len(self._openrouter_calls) < self._openrouter_rpm:
                self._openrouter_calls.append(now)
                return

            oldest = self._openrouter_calls[0]
            wait_s = max(0.0, self._openrouter_window_s - (now - oldest)) + random.random() * 0.2

        await asyncio.sleep(wait_s)
        return await self._throttle_openrouter()

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
    
    def _get_client_and_model(self, model_type: str, agent_id: int | None = None):
        """Get the appropriate client and model name."""
        provider = (settings.LLM_PROVIDER or "auto").strip().lower()

        if provider == "groq":
            key = settings.GROQ_DEFAULT_MODEL or "llama-3.1-8b"
            model_name = GROQ_CONFIG["models"].get(key, GROQ_CONFIG["models"]["llama-3.1-8b"])
            return self.groq_client, model_name

        if provider == "openrouter":
            # Fall back to a known OpenRouter model when the DB model_type is something else.
            model_name = OPENROUTER_CONFIG["models"].get(model_type, OPENROUTER_CONFIG["models"]["gpt-4o-mini"])
            return self.openrouter_client, model_name

        # auto: honor explicit mapping first, then fall back based on configured keys.
        if model_type in OPENROUTER_CONFIG["models"]:
            # Optional: send a small % of lightweight agents to Groq to reduce OpenRouter load.
            # Deterministic per-agent so the "society" has stable capability asymmetry.
            try:
                groq_share = float(getattr(settings, "GROQ_LIGHTWEIGHT_SHARE", 0.0) or 0.0)
            except Exception:
                groq_share = 0.0

            if (
                groq_share > 0
                and settings.GROQ_API_KEY
                and agent_id is not None
                and model_type == "llama-3.1-8b"
            ):
                rng = random.Random(int(agent_id))
                if rng.random() < groq_share:
                    return self.groq_client, GROQ_CONFIG["models"]["llama-3.1-8b"]

            return self.openrouter_client, OPENROUTER_CONFIG["models"][model_type]
        if model_type in GROQ_CONFIG["models"]:
            return self.groq_client, GROQ_CONFIG["models"][model_type]

        if settings.OPENROUTER_API_KEY:
            logger.warning(f"Unknown model type: {model_type}, defaulting to OpenRouter gpt-4o-mini")
            return self.openrouter_client, OPENROUTER_CONFIG["models"]["gpt-4o-mini"]

        logger.warning(f"Unknown model type: {model_type}, defaulting to Groq {settings.GROQ_DEFAULT_MODEL}")
        key = settings.GROQ_DEFAULT_MODEL or "llama-3.1-8b"
        model_name = GROQ_CONFIG["models"].get(key, GROQ_CONFIG["models"]["llama-3.1-8b"])
        return self.groq_client, model_name
    
    async def get_completion(
        self,
        model_type: str,
        system_prompt: str,
        user_prompt: str,
        agent_id: int | None = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> Optional[str]:
        """Get a completion with retry logic."""

        provider = (settings.LLM_PROVIDER or "auto").strip().lower()
        if provider == "groq":
            if not settings.GROQ_API_KEY:
                logger.error("LLM_PROVIDER=groq but GROQ_API_KEY is not set; returning no completion.")
                return None
        elif provider == "openrouter":
            if not settings.OPENROUTER_API_KEY:
                logger.error("LLM_PROVIDER=openrouter but OPENROUTER_API_KEY is not set; returning no completion.")
                return None
        else:
            # auto
            if not settings.OPENROUTER_API_KEY and not settings.GROQ_API_KEY:
                logger.error("Neither OPENROUTER_API_KEY nor GROQ_API_KEY is set; returning no completion.")
                return None

        client, model_name = self._get_client_and_model(model_type, agent_id=agent_id)

        async def _try_openrouter_alt_model_on_empty() -> Optional[str]:
            """
            If OpenRouter returns an empty payload (e.g., choices=[]), retry once on a different
            OpenRouter model. This avoids hammering Groq when it is rate-limited.
            """
            if client is not self.openrouter_client:
                return None
            if not settings.OPENROUTER_API_KEY:
                return None

            # Prefer a fast, stable instruction model.
            alt_model = OPENROUTER_CONFIG["models"].get("llama-3.1-8b") or OPENROUTER_CONFIG["models"].get("gpt-4o-mini")
            if not alt_model or alt_model == model_name:
                return None

            logger.warning(
                "Empty OpenRouter completion; retrying once with alt model=%s (original=%s)",
                alt_model,
                model_name,
            )
            try:
                async with self._openrouter_sem:
                    resp = await self.openrouter_client.chat.completions.create(
                        model=alt_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                return self._extract_text_from_response(resp)
            except Exception as inner:
                logger.error(f"OpenRouter alt-model retry failed: {inner}")
                return None

        async def _try_alternate_provider_on_empty() -> Optional[str]:
            """
            Provider edge case: sometimes a 200 OK comes back with empty content.
            In auto mode, try the other provider once to keep the simulation moving.
            """
            provider = (settings.LLM_PROVIDER or "auto").strip().lower()
            if provider != "auto":
                return None

            if client is self.openrouter_client and settings.GROQ_API_KEY:
                key = settings.GROQ_DEFAULT_MODEL or "llama-3.1-8b"
                fallback_model = GROQ_CONFIG["models"].get(key, GROQ_CONFIG["models"]["llama-3.1-8b"])
                try:
                    async with self._groq_sem:
                        resp = await self.groq_client.chat.completions.create(
                            model=fallback_model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                    return self._extract_text_from_response(resp)
                except Exception as inner:
                    logger.error(f"Alternate-provider retry (groq) failed: {inner}")
                    return None

            if client is self.groq_client and settings.OPENROUTER_API_KEY:
                fallback_model = OPENROUTER_CONFIG["models"].get(
                    model_type, OPENROUTER_CONFIG["models"]["gpt-4o-mini"]
                )
                try:
                    async with self._openrouter_sem:
                        resp = await self.openrouter_client.chat.completions.create(
                            model=fallback_model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                    return self._extract_text_from_response(resp)
                except Exception as inner:
                    logger.error(f"Alternate-provider retry (openrouter) failed: {inner}")
                    return None

            return None

        async def _try_openrouter_fallback(err: Exception) -> Optional[str]:
            """
            If Groq is rate-limiting (common on free tiers), optionally fall back to OpenRouter
            when a key is configured. This keeps the simulation alive while still preferring Groq.
            """
            provider = (settings.LLM_PROVIDER or "auto").strip().lower()
            if provider == "groq" and not getattr(settings, "ALLOW_OPENROUTER_FALLBACK", False):
                return None
            if not settings.OPENROUTER_API_KEY:
                return None
            if client is not self.groq_client:
                return None

            msg = str(err)
            # RateLimitError usually maps to HTTP 429; keep this check broad.
            if "429" not in msg and "rate" not in msg.lower():
                return None

            fallback_model = OPENROUTER_CONFIG["models"].get(
                model_type, OPENROUTER_CONFIG["models"]["gpt-4o-mini"]
            )
            logger.warning("Groq request rate-limited; falling back to OpenRouter for this request.")
            try:
                response = await self.openrouter_client.chat.completions.create(
                    model=fallback_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return self._extract_text_from_response(response)
            except Exception as inner:
                logger.error(f"OpenRouter fallback failed: {inner}")
                return None

        async def _try_groq_fallback(err: Exception) -> Optional[str]:
            if not settings.GROQ_API_KEY:
                return None
            if client is not self.openrouter_client:
                return None

            msg = str(err)
            if "402" not in msg and "Insufficient credits" not in msg:
                return None

            key = settings.GROQ_DEFAULT_MODEL or "llama-3.1-8b"
            fallback_model = GROQ_CONFIG["models"].get(key, GROQ_CONFIG["models"]["llama-3.1-8b"])
            logger.warning("OpenRouter request failed (likely 402); falling back to Groq for this request.")
            try:
                response = await self.groq_client.chat.completions.create(
                    model=fallback_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return self._extract_text_from_response(response)
            except Exception as inner:
                logger.error(f"Groq fallback failed: {inner}")
                return None
        
        for attempt in range(max_retries):
            try:
                sem = self._openrouter_sem if client is self.openrouter_client else self._groq_sem
                async with sem:
                    if client is self.openrouter_client:
                        await self._throttle_openrouter()
                    response = await client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )

                # Guard against occasional provider/library edge cases where a 200 OK yields
                # an empty/partial payload.
                content = self._extract_text_from_response(response)
                if not content:
                    meta = self._debug_choice_meta(response)
                    provider_name = "openrouter" if client is self.openrouter_client else "groq"
                    logger.warning(
                        "Empty completion content (provider=%s model=%s attempt=%s/%s meta=%s)",
                        provider_name,
                        model_name,
                        attempt + 1,
                        max_retries,
                        meta,
                    )
                    # If OpenRouter is the selected provider, retry once on a different OpenRouter model
                    # before we consider cross-provider fallback.
                    or_alt = await _try_openrouter_alt_model_on_empty()
                    if or_alt:
                        return or_alt
                    raise RuntimeError("Empty completion content")

                return content
                
            except RateLimitError as e:
                or_fallback = await _try_openrouter_fallback(e)
                if or_fallback:
                    return or_fallback
                wait_time = (2 ** attempt) + random.random()
                logger.warning(f"Rate limited, waiting {wait_time:.2f}s (attempt {attempt + 1})")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(wait_time)
                
            except APIError as e:
                or_fallback = await _try_openrouter_fallback(e)
                if or_fallback:
                    return or_fallback
                groq = await _try_groq_fallback(e)
                if groq:
                    return groq
                logger.error(f"API error: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1 + random.random() * 0.25)
                
            except Exception as e:
                or_fallback = await _try_openrouter_fallback(e)
                if or_fallback:
                    return or_fallback
                groq = await _try_groq_fallback(e)
                if groq:
                    return groq
                if str(e) == "Empty completion content":
                    swapped = await _try_alternate_provider_on_empty()
                    if swapped:
                        return swapped
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
) -> Optional[dict]:
    """Get an action decision from an agent."""
    
    def _fallback_action(reason: str) -> dict:
        # Keep the simulation moving even if the LLM provider is unavailable.
        # Bias toward "work" which is always safe and doesn't spam the forum.
        seed = agent_id + int(now_utc().timestamp() // 3600)
        rng = random.Random(seed)
        roll = rng.random()

        if roll < 0.75:
            return {
                "action": "work",
                "work_type": rng.choice(["farm", "generate", "gather"]),
                "hours": rng.randint(1, 4),
                "reasoning": f"Fallback (LLM unavailable): {reason}",
            }
        if roll < 0.9:
            return {"action": "idle", "reasoning": f"Fallback (LLM unavailable): {reason}"}

        return {
            "action": "forum_post",
            "content": (
                "I'm having trouble communicating clearly right now, so I'll focus on work and "
                "staying alive. If anyone has a concrete plan, summarize it and tag me."
            ),
            "reasoning": f"Fallback (LLM unavailable): {reason}",
        }

    try:
        response = await llm_client.get_completion(
            model_type=model_type,
            system_prompt=system_prompt,
            user_prompt=context_prompt,
            agent_id=agent_id,
            max_tokens=250,
            temperature=0.7,
        )
        
        if not response:
            return _fallback_action("No response from LLM")
        
        # Try to parse JSON from response
        return parse_action_response(response)
        
    except Exception as e:
        logger.error(f"Error getting action for agent {agent_id}: {e}")
        return _fallback_action(str(e))


def parse_action_response(response: str) -> dict:
    """Parse LLM response into structured action."""
    import re
    
    # Try to find JSON in the response
    json_patterns = [
        r'\{[^{}]*\}',  # Simple JSON object
        r'```json\s*(\{.*?\})\s*```',  # Markdown code block
        r'```\s*(\{.*?\})\s*```',  # Generic code block
    ]
    
    for pattern in json_patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            try:
                json_str = match.group(1) if match.lastindex else match.group()
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue
    
    # If no valid JSON found, treat as forum post
    clean_response = response.strip()[:2000]
    if clean_response:
        return {"action": "forum_post", "content": clean_response}
    
    return {"action": "idle", "reasoning": "Could not parse response"}
