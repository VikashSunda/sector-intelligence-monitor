"""
Provider-agnostic LLM client.

Primary provider: Claude (Anthropic) — claude-sonnet-4-5 by default.
Supported fallbacks: Gemini (Google), OpenAI.

Switch providers with environment variables — zero code changes required:
    LLM_PROVIDER=claude    → ANTHROPIC_API_KEY
    LLM_PROVIDER=gemini    → GEMINI_API_KEY
    LLM_PROVIDER=openai    → OPENAI_API_KEY
    LLM_MODEL=<name>       → overrides default model for the active provider

All provider SDKs are imported lazily — missing packages do not crash at import time.
Only the active provider's SDK and API key are required at runtime.

Structured extraction:
  - Prompt is augmented with the Pydantic schema
  - Response is parsed as JSON → model_validate_json()
  - On validation failure: one retry with error feedback appended to prompt
  - On second failure: returns None and logs error (pipeline continues)
"""

import json
import logging
import os
import re
import time
from typing import Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ─── Provider defaults ────────────────────────────────────────────────────────

_PROVIDER_DEFAULTS: dict[str, dict] = {
    "claude": {
        "model": "claude-sonnet-4-5",
        "max_tokens": 4096,
    },
    "gemini": {
        "model": "gemini-1.5-flash",
        "max_tokens": 4096,
    },
    "openai": {
        "model": "gpt-4o-mini",
        "max_tokens": 4096,
    },
}


class LLMClient:
    """
    Provider-agnostic LLM wrapper with structured extraction and retry logic.

    Usage:
        client = LLMClient()                              # reads LLM_PROVIDER env var
        client = LLMClient(provider="claude")             # explicit
        client = LLMClient(provider="gemini", model="gemini-1.5-pro")

        text = client.complete("Summarise the Indian fintech sector in 3 bullet points.")

        from pipeline.schemas import FintechMetrics
        metrics = client.extract_structured(prompt, FintechMetrics)
        # Returns FintechMetrics | None
    """

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "claude")).lower().strip()

        if self.provider not in _PROVIDER_DEFAULTS:
            raise ValueError(
                f"Unknown LLM provider '{self.provider}'. "
                f"Supported: {list(_PROVIDER_DEFAULTS.keys())}"
            )

        default_model = _PROVIDER_DEFAULTS[self.provider]["model"]
        self.model = model or os.getenv("LLM_MODEL", "").strip() or default_model
        self.max_tokens = int(
            os.getenv("LLM_MAX_TOKENS", str(_PROVIDER_DEFAULTS[self.provider]["max_tokens"]))
        )
        self._rate_limit_sleep = float(os.getenv("LLM_RATE_LIMIT_SLEEP", "2"))

        logger.info(
            f"LLMClient initialised: provider={self.provider}, model={self.model}"
        )

    # ─── Public API ───────────────────────────────────────────────────────────

    def complete(self, prompt: str) -> str:
        """
        Free-form text completion. Returns the raw response string.
        Raises on API error (caller decides whether to catch).
        """
        return self._call(prompt)

    def extract_structured(self, prompt: str, schema_class: Type[T]) -> Optional[T]:
        """
        Extract structured data from the prompt and validate against schema_class.

        Augments the prompt with the JSON schema.
        Retries once if the response fails Pydantic validation.
        Returns None if both attempts fail (logs the error).

        Args:
            prompt: Instruction + source text to extract from.
            schema_class: A Pydantic BaseModel subclass.

        Returns:
            An instance of schema_class, or None on failure.
        """
        schema_json = json.dumps(schema_class.model_json_schema(), indent=2)
        full_prompt = (
            f"{prompt}\n\n"
            "Return a JSON object that matches the schema below exactly.\n"
            "Use null for any field that is not mentioned or cannot be determined from the text.\n"
            "Do NOT invent or hallucinate values. Only extract what is explicitly stated.\n"
            f"Schema:\n{schema_json}\n\n"
            "Respond with ONLY the JSON object. No markdown fences, no explanation."
        )

        for attempt in range(2):
            try:
                raw = self._call(full_prompt)
                time.sleep(self._rate_limit_sleep)  # Respect free-tier rate limits
                json_str = self._extract_json(raw)
                instance = schema_class.model_validate_json(json_str)
                logger.debug(f"Extraction succeeded on attempt {attempt + 1}")
                return instance

            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                if attempt == 0:
                    logger.warning(
                        f"Extraction attempt 1 failed ({type(exc).__name__}: {exc}). "
                        "Retrying with error context."
                    )
                    full_prompt += (
                        f"\n\nYour previous response failed JSON validation:\n{exc}\n"
                        "Fix the issue and return ONLY valid JSON matching the schema."
                    )
                else:
                    logger.error(
                        f"Extraction failed after 2 attempts. "
                        f"Last error: {type(exc).__name__}: {exc}"
                    )
                    return None

        return None  # Unreachable but satisfies type checker

    # ─── Internal dispatch ────────────────────────────────────────────────────

    def _call(self, prompt: str) -> str:
        """Route to the active provider's call method."""
        if self.provider == "claude":
            return self._call_claude(prompt)
        if self.provider == "gemini":
            return self._call_gemini(prompt)
        if self.provider == "openai":
            return self._call_openai(prompt)
        raise ValueError(f"Provider not handled: {self.provider}")

    def _call_claude(self, prompt: str) -> str:
        try:
            import anthropic  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "Anthropic SDK not installed. Run: pip install anthropic"
            ) from exc

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file or environment."
            )

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def _call_gemini(self, prompt: str) -> str:
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "Google GenerativeAI SDK not installed. "
                "Run: pip install google-generativeai"
            ) from exc

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set.")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(self.model)
        response = model.generate_content(prompt)
        return response.text

    def _call_openai(self, prompt: str) -> str:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "OpenAI SDK not installed. Run: pip install openai"
            ) from exc

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY is not set.")

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content

    # ─── JSON extraction ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_json(text: str) -> str:
        """
        Extract the first complete JSON object from LLM response text.
        Handles markdown code fences (```json ... ```) and raw JSON.
        Raises ValueError if no valid JSON object is found.
        """
        # Remove markdown code fences
        text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
        text = text.strip()

        # Find the outermost { ... } block using brace counting
        start = text.find("{")
        if start == -1:
            raise ValueError(f"No JSON object found in LLM response. Got: {text[:200]!r}")

        depth = 0
        in_string = False
        escape_next = False

        for i, ch in enumerate(text[start:], start):
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        raise ValueError(
            f"Malformed JSON in LLM response — unmatched braces. "
            f"Raw (first 300 chars): {text[:300]!r}"
        )
