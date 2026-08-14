"""
LLM service (real, no webhooks, no fake responses)
==================================================
Provides a simple interface to generate assistant responses.

Currently supports OpenAI Chat Completions when OPENAI_API_KEY is set.
If no provider is configured, returns a structured error (and does NOT fake output).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional


class LLMService:
    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "openai").strip().lower()
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.api_key = os.environ.get("OPENAI_API_KEY", "")

    def is_configured(self) -> bool:
        if self.provider == "openai":
            return bool(self.api_key)
        return False

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.4, max_tokens: int = 500) -> Dict:
        """
        messages: [{role: 'system'|'user'|'assistant', content: '...'}]
        """
        if self.provider == "openai":
            return self._chat_openai(messages, temperature=temperature, max_tokens=max_tokens)
        return {
            "success": False,
            "error": f"Unsupported LLM_PROVIDER '{self.provider}'.",
        }

    def _chat_openai(self, messages: List[Dict[str, str]], temperature: float, max_tokens: int) -> Dict:
        if not self.api_key:
            return {"success": False, "error": "OPENAI_API_KEY is not configured."}

        try:
            from openai import OpenAI
        except Exception as e:
            return {"success": False, "error": f"openai package not installed: {e}"}

        try:
            client = OpenAI(api_key=self.api_key)
            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=float(temperature),
                max_tokens=int(max_tokens),
            )
            content = resp.choices[0].message.content if resp.choices else ""
            return {
                "success": True,
                "provider": "openai",
                "model": self.model,
                "content": content or "",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

