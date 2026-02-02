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

logger = logging.getLogger(__name__)


# Provider configurations
OPENROUTER_CONFIG = {
    "base_url": "https://openrouter.ai/api/v1",
    "models": {
        "claude-sonnet-4": "anthropic/claude-sonnet-4",
        "gpt-4o-mini": "openai/gpt-4o-mini",
        "claude-haiku": "anthropic/claude-3-haiku",
    }
}

GROQ_CONFIG = {
    "base_url": "https://api.groq.com/openai/v1",
    "models": {
        "llama-3.3-70b": "llama-3.3-70b-versatile",
        "llama-3.1-8b": "llama-3.1-8b-instant",
        "gemini-flash": "gemini-2.0-flash",  # Fallback via OpenRouter
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
    
    try:
        response = await llm_client.get_completion(
            model_type=model_type,
            system_prompt=system_prompt,
            user_prompt=context_prompt,
            max_tokens=500,
            temperature=0.7,
        )
        
        if not response:
            return {"action": "idle", "reasoning": "No response from LLM"}
        
        # Try to parse JSON from response
        return parse_action_response(response)
        
    except Exception as e:
        logger.error(f"Error getting action for agent {agent_id}: {e}")
        return {"action": "idle", "reasoning": f"Error: {str(e)}"}


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
