"""
LLM Client with retry logic and multi-provider support.
"""
import asyncio
import json
import logging
import random
from typing import Optional
from openai import AsyncOpenAI
from openai import RateLimitError, APIError

from app.core.config import settings
from app.core.time import now_utc

logger = logging.getLogger(__name__)


# Provider configurations
OPENROUTER_CONFIG = {
    "base_url": "https://openrouter.ai/api/v1",
    "models": {
        "claude-sonnet-4": "anthropic/claude-sonnet-4",
        "gpt-4o-mini": "openai/gpt-4o-mini",
        "claude-haiku": "anthropic/claude-3-haiku",
        # Gemini is routed via OpenRouter (not Groq)
        "gemini-flash": "google/gemini-2.0-flash-001",
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
    
    def _get_client_and_model(self, model_type: str):
        """Get the appropriate client and model name."""
        if model_type in OPENROUTER_CONFIG["models"]:
            return self.openrouter_client, OPENROUTER_CONFIG["models"][model_type]
        elif model_type in GROQ_CONFIG["models"]:
            return self.groq_client, GROQ_CONFIG["models"][model_type]
        else:
            # Default to OpenRouter with GPT-4o-mini
            logger.warning(f"Unknown model type: {model_type}, defaulting to gpt-4o-mini")
            return self.openrouter_client, OPENROUTER_CONFIG["models"]["gpt-4o-mini"]
    
    async def get_completion(
        self,
        model_type: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> Optional[str]:
        """Get a completion with retry logic."""
        
        if model_type in OPENROUTER_CONFIG["models"] or model_type not in GROQ_CONFIG["models"]:
            if not settings.OPENROUTER_API_KEY:
                logger.error("OPENROUTER_API_KEY is not set; returning no completion.")
                return None
        if model_type in GROQ_CONFIG["models"]:
            if not settings.GROQ_API_KEY:
                logger.error("GROQ_API_KEY is not set; returning no completion.")
                return None

        client, model_name = self._get_client_and_model(model_type)
        
        for attempt in range(max_retries):
            try:
                response = await client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                
                return response.choices[0].message.content
                
            except RateLimitError as e:
                wait_time = (2 ** attempt) + random.random()
                logger.warning(f"Rate limited, waiting {wait_time:.2f}s (attempt {attempt + 1})")
                await asyncio.sleep(wait_time)
                
            except APIError as e:
                logger.error(f"API error: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1)
        
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
            max_tokens=500,
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
