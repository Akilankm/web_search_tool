from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger


@dataclass(frozen=True)
class LLMConfig:
    """Azure OpenAI configuration for exact-product adjudication.

    Values are loaded from environment by default. The class intentionally does
    not import OpenAI until a service instance is created, so the package can be
    imported and tested without the optional `openai` dependency installed.
    """

    api_key: str
    api_version: str
    endpoint: str
    deployment: str
    consumer_id: str = ""
    max_tokens: int = 1600
    temperature: float = 0.0
    connect_timeout: float = 15.0
    read_timeout: float = 120.0
    max_retries: int = 3

    @classmethod
    def from_env(cls) -> "LLMConfig":
        def _get(name: str, default: str = "") -> str:
            return os.getenv(name, default).strip()

        api_key = _get("AZURE_OPENAI_API_KEY") or _get("LLM_API_KEY")
        api_version = _get("AZURE_OPENAI_API_VERSION") or _get("LLM_API_VERSION")
        endpoint = _get("AZURE_OPENAI_ENDPOINT") or _get("LLM_ENDPOINT")
        deployment = _get("AZURE_OPENAI_DEPLOYMENT") or _get("LLM_DEPLOYMENT")
        consumer_id = _get("LLM_CONSUMER_ID") or _get("AZURE_OPENAI_CONSUMER_ID")
        missing = [
            name for name, value in {
                "AZURE_OPENAI_API_KEY/LLM_API_KEY": api_key,
                "AZURE_OPENAI_API_VERSION/LLM_API_VERSION": api_version,
                "AZURE_OPENAI_ENDPOINT/LLM_ENDPOINT": endpoint,
                "AZURE_OPENAI_DEPLOYMENT/LLM_DEPLOYMENT": deployment,
            }.items() if not value
        ]
        if missing:
            raise ValueError("Missing LLM environment variables: " + ", ".join(missing))
        return cls(
            api_key=api_key,
            api_version=api_version,
            endpoint=endpoint,
            deployment=deployment,
            consumer_id=consumer_id,
            max_tokens=int(_get("LLM_MAX_TOKENS", "1600")),
            temperature=float(_get("LLM_TEMPERATURE", "0.0")),
            connect_timeout=float(_get("LLM_CONNECT_TIMEOUT", "15")),
            read_timeout=float(_get("LLM_READ_TIMEOUT", "120")),
            max_retries=int(_get("LLM_MAX_RETRIES", "3")),
        )

    @property
    def default_headers(self) -> Dict[str, str]:
        return {"X-NIQ-CIS-Consumer": self.consumer_id} if self.consumer_id else {}


@dataclass
class LLMResponse:
    content: str
    usage: Dict[str, int] = field(default_factory=dict)
    model: str = ""
    finish_reason: str = ""
    raw: Any = None


_DEFAULT_SERVICE: Optional["LLMService"] = None


def get_llm_service(config: Optional[LLMConfig] = None) -> "LLMService":
    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        _DEFAULT_SERVICE = LLMService(config)
    return _DEFAULT_SERVICE


class LLMService:
    """Unified Azure OpenAI LLM service for text and one-image calls."""

    _cumulative_prompt: int = 0
    _cumulative_completion: int = 0
    _cumulative_calls: int = 0

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig.from_env()
        try:
            import httpx
            from openai import AzureOpenAI
        except Exception as exc:
            raise ImportError(
                "LLM adjudication requires the optional `openai` and `httpx` packages. "
                "Install them or disable enable_llm_adjudication."
            ) from exc
        self._client = AzureOpenAI(
            api_key=self.config.api_key,
            api_version=self.config.api_version,
            azure_endpoint=self.config.endpoint,
            azure_deployment=self.config.deployment,
            default_headers=self.config.default_headers,
            max_retries=self.config.max_retries,
            timeout=httpx.Timeout(
                connect=self.config.connect_timeout,
                read=self.config.read_timeout,
                write=self.config.read_timeout,
                pool=self.config.read_timeout,
            ),
        )

    def predict(
        self,
        text: str,
        *,
        system_prompt: Optional[str] = None,
        image: Optional[Union[str, bytes]] = None,
        image_detail: str = "auto",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_format: Optional[Dict] = None,
        purpose: str = "",
    ) -> LLMResponse:
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": self._build_user_content(text, image, image_detail=image_detail)})
        return self._call(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
            purpose=purpose,
        )

    def _call(
        self,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_format: Optional[Dict] = None,
        purpose: str = "",
    ) -> LLMResponse:
        kwargs: Dict[str, Any] = {
            "model": self.config.deployment,
            "messages": messages,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format
        try:
            completion = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            body = getattr(getattr(exc, "response", None), "text", None)
            if body:
                logger.error("LLM call failed: {} — body={}", exc, body[:1000])
            else:
                logger.exception("LLM call failed")
            raise

        choice = completion.choices[0]
        usage: Dict[str, int] = {}
        if completion.usage:
            usage = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens,
            }
            LLMService._cumulative_prompt += completion.usage.prompt_tokens
            LLMService._cumulative_completion += completion.usage.completion_tokens
            LLMService._cumulative_calls += 1
            logger.info(
                "LLM [{}] prompt={} completion={} total={}",
                purpose or "unknown",
                completion.usage.prompt_tokens,
                completion.usage.completion_tokens,
                completion.usage.total_tokens,
            )
        return LLMResponse(
            content=choice.message.content or "",
            usage=usage,
            model=completion.model or "",
            finish_reason=choice.finish_reason or "",
            raw=completion,
        )

    @classmethod
    def reset_token_counters(cls) -> None:
        cls._cumulative_prompt = 0
        cls._cumulative_completion = 0
        cls._cumulative_calls = 0

    @classmethod
    def token_summary(cls) -> str:
        total = cls._cumulative_prompt + cls._cumulative_completion
        return (
            f"LLM totals: {cls._cumulative_calls} calls | "
            f"prompt={cls._cumulative_prompt:,} completion={cls._cumulative_completion:,} "
            f"total={total:,} tokens"
        )

    def _build_user_content(self, text: str, image: Optional[Union[str, bytes]], *, image_detail: str) -> Union[str, List[Dict[str, Any]]]:
        if image is None:
            return text
        return [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": self._resolve_image(image), "detail": image_detail}},
        ]

    @staticmethod
    def _resolve_image(image: Union[str, bytes]) -> str:
        if isinstance(image, bytes):
            return LLMService._bytes_to_data_url(image)
        if isinstance(image, str):
            if image.startswith(("http://", "https://", "data:")):
                return image
            path = Path(image)
            if path.is_file():
                return LLMService._bytes_to_data_url(path.read_bytes(), path.suffix)
            raise FileNotFoundError(f"Image file not found: {image}")
        raise TypeError(f"Unsupported image type: {type(image)}")

    @staticmethod
    def _bytes_to_data_url(data: bytes, suffix: str = ".png") -> str:
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
        }
        mime = mime_map.get(suffix.lower(), "image/png")
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:{mime};base64,{b64}"
