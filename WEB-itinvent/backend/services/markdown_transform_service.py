"""
Service for converting plain text into Markdown using OpenRouter.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from dotenv import dotenv_values

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency at runtime
    OpenAI = None


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
ROOT_ENV = dotenv_values(str(ROOT_ENV_PATH)) if ROOT_ENV_PATH.exists() else {}

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MARKDOWN_MODEL = "openai/gpt-4o-mini"


class MarkdownTransformConfigError(RuntimeError):
    """Raised when LLM configuration is incomplete or unavailable."""


class MarkdownTransformError(RuntimeError):
    """Raised when LLM request fails or returns invalid payload."""


def _read_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value not in (None, ""):
        return str(value).strip()
    root_value = ROOT_ENV.get(name)
    if root_value not in (None, ""):
        return str(root_value).strip()
    return default


def _normalize_openrouter_base_url(raw_value: Any, default_base_url: str) -> str:
    raw = str(raw_value or "").strip()
    if not raw:
        return default_base_url

    value = raw.rstrip("/")
    lower = value.lower()

    if lower.endswith("/chat/completions"):
        value = value[: -len("/chat/completions")]
        lower = value.lower()
    elif lower.endswith("/completions"):
        value = value[: -len("/completions")]
        lower = value.lower()

    if lower.endswith("/api"):
        value = f"{value}/v1"
        lower = value.lower()

    if lower.endswith("/v1") and not lower.endswith("/api/v1"):
        value = re.sub(r"/v1$", "", value, flags=re.IGNORECASE)
        value = f"{value}/api/v1"
        lower = value.lower()

    if not lower.endswith("/api/v1"):
        value = f"{value}/api/v1"

    return value


def _to_int(value: Any) -> Optional[int]:
    try:
        if value in (None, "", "null"):
            return None
        return int(value)
    except Exception:
        return None


def _cleanup_markdown_wrapper(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    wrapped = re.match(r"^```(?:markdown|md)?\s*\n([\s\S]*?)\n```$", normalized, flags=re.IGNORECASE)
    if wrapped:
        return str(wrapped.group(1) or "").strip()
    return normalized


def _extract_completion_text(completion: Any) -> str:
    try:
        message = completion.choices[0].message
    except Exception:
        return ""

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                token = item.get("text") or item.get("content")
            else:
                token = getattr(item, "text", None) or getattr(item, "content", None)
            if token:
                parts.append(str(token))
        return "\n".join(parts).strip()
    return str(content or "").strip()


class MarkdownTransformService:
    def __init__(self, *, request_timeout_sec: float = 20.0) -> None:
        self.request_timeout_sec = float(request_timeout_sec)

    def _resolve_key(self) -> str:
        key = _read_env("OPENROUTER_API_KEY") or _read_env("OPENAI_API_KEY")
        if not key:
            raise MarkdownTransformConfigError("OPENROUTER_API_KEY не задан.")
        return key

    def _resolve_base_url(self) -> str:
        raw = _read_env("OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL)
        return _normalize_openrouter_base_url(raw, DEFAULT_OPENROUTER_BASE_URL)

    def _resolve_model(self) -> str:
        return (
            _read_env("OPENROUTER_MODEL_MARKDOWN")
            or _read_env("ACT_PARSE_MODEL")
            or _read_env("OCR_MODEL")
            or DEFAULT_MARKDOWN_MODEL
        )

    def transform_text(self, *, text: str, context: str) -> dict[str, Any]:
        normalized_text = str(text or "").strip()
        normalized_context = str(context or "").strip().lower()

        if len(normalized_text) < 3:
            raise ValueError("Текст слишком короткий для преобразования.")
        if len(normalized_text) > 20000:
            raise ValueError("Текст слишком большой. Максимум 20000 символов.")
        if normalized_context not in {"announcement", "task"}:
            raise ValueError("Неверный context. Допустимо: announcement или task.")

        if OpenAI is None:
            raise MarkdownTransformConfigError("Пакет openai не установлен.")

        api_key = self._resolve_key()
        base_url = self._resolve_base_url()
        model = self._resolve_model()
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=self.request_timeout_sec)

        if normalized_context == "announcement":
            context_emoji_rule = (
                "For announcement context, keep emoji usage neutral and sparse. "
                "Use emoji only for light structure accents when helpful (for example pin/info/check style accents)."
            )
        else:
            context_emoji_rule = (
                "For task context, use emoji only for functional highlights such as status or deadline emphasis "
                "(for example warning/check/clock style accents) when it improves scanability."
            )

        system_prompt = (
            "Convert user text into clean Markdown. "
            "Do not change facts or meaning. "
            "Improve readability with headings, lists, checklists, and tables only when appropriate. "
            "Emoji policy is moderate: use at most one emoji per heading or meaningful block, "
            "do not add emoji to every line or every bullet, and keep a professional tone. "
            "If text is short or formal, emoji may be omitted entirely. "
            f"{context_emoji_rule} "
            "Return only final Markdown without explanations."
        )
        user_prompt = (
            f"Context: {normalized_context}\n"
            "Requirements:\n"
            "- Preserve the original language.\n"
            "- Do not add new information.\n"
            "- Keep names, numbers, and dates accurate.\n"
            "- Emoji mode: moderate.\n\n"
            "Source text:\n"
            f"{normalized_text}"
        )

        try:
            completion = client.chat.completions.create(
                model=model,
                temperature=0.2,
                max_tokens=3000,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as exc:
            logger.warning("Markdown transform request failed: context=%s error=%s", normalized_context, exc)
            raise MarkdownTransformError("Не удалось обратиться к LLM для преобразования текста.") from exc

        markdown = _cleanup_markdown_wrapper(_extract_completion_text(completion))
        if not markdown:
            raise MarkdownTransformError("LLM вернул пустой ответ.")

        usage = getattr(completion, "usage", None)
        usage_payload = {
            "prompt_tokens": _to_int(getattr(usage, "prompt_tokens", None) if usage is not None else None),
            "completion_tokens": _to_int(getattr(usage, "completion_tokens", None) if usage is not None else None),
            "total_tokens": _to_int(getattr(usage, "total_tokens", None) if usage is not None else None),
        }
        usage_payload = {k: v for k, v in usage_payload.items() if v is not None}

        logger.info(
            "Markdown transform done: context=%s model=%s input_len=%s output_len=%s",
            normalized_context,
            model,
            len(normalized_text),
            len(markdown),
        )
        return {
            "markdown": markdown,
            "provider": "openrouter",
            "model": model,
            "usage": usage_payload,
        }


markdown_transform_service = MarkdownTransformService()
