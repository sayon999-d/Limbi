

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger("limbi.llm_provider")

@dataclass
class ProviderConfig:

    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 2048

    azure_deployment: str = ""
    azure_api_version: str = "2024-06-01"

    @classmethod
    def from_env(cls) -> "ProviderConfig":

        return cls(
            provider=os.getenv("LLM_PROVIDER", "ollama").lower().strip(),
            model=os.getenv("LLM_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2:3b")),
            base_url=os.getenv("LLM_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")),
            api_key=os.getenv("LLM_API_KEY", ""),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
            azure_deployment=os.getenv("AZURE_DEPLOYMENT", ""),
            azure_api_version=os.getenv("AZURE_API_VERSION", "2024-06-01"),
        )

class BaseLLMProvider(ABC):

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @abstractmethod
    def get_chat_model(self) -> BaseChatModel:

        ...

    @abstractmethod
    def provider_name(self) -> str:
        ...

    def info(self) -> dict[str, Any]:

        return {
            "provider": self.provider_name(),
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "base_url": self.config.base_url or "(default)",
        }

class OllamaProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "ollama"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=self.config.model,
            base_url=self.config.base_url or "http://localhost:11434",
            temperature=self.config.temperature,
            num_predict=self.config.max_tokens,
        )

class OpenAIProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "openai"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        kwargs: dict[str, Any] = {
            "model": self.config.model or "gpt-4o",
            "api_key": self.config.api_key,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        return ChatOpenAI(**kwargs)

class AnthropicProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "anthropic"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=self.config.model or "claude-sonnet-4-20250514",
            api_key=self.config.api_key,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

class GoogleProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "google"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=self.config.model or "gemini-1.5-pro",
            google_api_key=self.config.api_key,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
        )

class GroqProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "groq"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=self.config.model or "llama-3.1-70b-versatile",
            api_key=self.config.api_key,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

class TogetherProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "together"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self.config.model or "meta-llama/Llama-3-70b-chat-hf",
            api_key=self.config.api_key,
            base_url="https://api.together.xyz/v1",
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

class MistralProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "mistral"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_mistralai import ChatMistralAI
        return ChatMistralAI(
            model=self.config.model or "mistral-large-latest",
            api_key=self.config.api_key,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

class AzureOpenAIProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "azure"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_openai import AzureChatOpenAI
        return AzureChatOpenAI(
            azure_deployment=self.config.azure_deployment or self.config.model,
            api_key=self.config.api_key,
            azure_endpoint=self.config.base_url,
            api_version=self.config.azure_api_version,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

class CohereProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "cohere"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_cohere import ChatCohere
        return ChatCohere(
            model=self.config.model or "command-r-plus",
            cohere_api_key=self.config.api_key,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )


class OpenRouterProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "openrouter"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self.config.model or "openai/gpt-4o",
            api_key=self.config.api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )


class HuggingFaceProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "huggingface"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self.config.model or "meta-llama/Llama-3.1-8B-Instruct",
            api_key=self.config.api_key,
            base_url="https://router.huggingface.co/v1",
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )


class ChutesProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "chutes"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self.config.model or "meta-llama/Llama-3.1-8B-Instruct",
            api_key=self.config.api_key,
            base_url="https://llm.chutes.ai/v1",
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )


class BytezProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "bytez"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self.config.model or "meta-llama/Llama-3.1-8B-Instruct",
            api_key=self.config.api_key,
            base_url="https://api.bytez.com/models/v2/openai/v1",
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

class OpenAICompatibleProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "openai_compatible"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=self.config.model or "default",
            api_key=self.config.api_key or "not-needed",
            base_url=self.config.base_url,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

_PROVIDER_MAP: dict[str, type[BaseLLMProvider]] = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "claude": AnthropicProvider,
    "google": GoogleProvider,
    "gemini": GoogleProvider,
    "groq": GroqProvider,
    "openrouter": OpenRouterProvider,
    "huggingface": HuggingFaceProvider,
    "hf": HuggingFaceProvider,
    "chutes": ChutesProvider,
    "bytez": BytezProvider,
    "together": TogetherProvider,
    "mistral": MistralProvider,
    "azure": AzureOpenAIProvider,
    "azure_openai": AzureOpenAIProvider,
    "cohere": CohereProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "lmstudio": OpenAICompatibleProvider,
    "vllm": OpenAICompatibleProvider,
    "localai": OpenAICompatibleProvider,
    "koboldcpp": OpenAICompatibleProvider,
    "llamacpp": OpenAICompatibleProvider,
}

def get_llm_provider(config: ProviderConfig | None = None) -> BaseLLMProvider:

    cfg = config or ProviderConfig.from_env()
    provider_cls = _PROVIDER_MAP.get(cfg.provider)

    if not provider_cls:
        logger.warning(
            "Unknown LLM_PROVIDER=%r, falling back to Ollama. Valid: %s",
            cfg.provider, ", ".join(sorted(_PROVIDER_MAP.keys())),
        )
        provider_cls = OllamaProvider

    provider = provider_cls(cfg)
    logger.info("LLM provider: %s (model=%s)", provider.provider_name(), cfg.model)
    return provider

def list_providers() -> list[str]:

    return sorted(set(cls.__name__ for cls in _PROVIDER_MAP.values()))


_MODEL_LIST_ENDPOINTS = {
    "openrouter": ("https://openrouter.ai/api/v1/models", "bearer"),
    "groq": ("https://api.groq.com/openai/v1/models", "bearer"),
    "huggingface": ("https://router.huggingface.co/v1/models", "bearer"),
    "hf": ("https://router.huggingface.co/v1/models", "bearer"),
    "chutes": ("https://llm.chutes.ai/v1/models", "bearer"),
    "bytez": ("https://api.bytez.com/models/v2/list/models?task=chat", "raw"),
}


def _fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 10) -> Any:
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize_model_ids(payload: Any, provider: str) -> list[str]:
    models: list[str] = []
    rows = []
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("output") or payload.get("models") or []
    elif isinstance(payload, list):
        rows = payload
    if not isinstance(rows, list):
        return models
    for row in rows:
        if isinstance(row, str):
            model_id = row.strip()
        elif isinstance(row, dict):
            model_id = str(
                row.get("id")
                or row.get("modelId")
                or row.get("name")
                or row.get("slug")
                or ""
            ).strip()
        else:
            model_id = ""
        if model_id:
            models.append(model_id)
    return sorted(dict.fromkeys(models))


def list_available_models(provider_name: str, api_key: str = "", base_url: str | None = None) -> list[str]:
    provider = (provider_name or "").lower().strip()
    resolved_base_url = (base_url or "").strip().rstrip("/")

    if provider in _MODEL_LIST_ENDPOINTS:
        endpoint, auth_style = _MODEL_LIST_ENDPOINTS[provider]
        headers: dict[str, str] = {}
        if api_key:
            if auth_style == "bearer":
                headers["Authorization"] = f"Bearer {api_key}"
            else:
                headers["Authorization"] = api_key
        try:
            return _normalize_model_ids(_fetch_json(endpoint, headers=headers), provider)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
            logger.info("Model catalog lookup failed for %s: %s", provider, exc)
            return []

    if provider in {"openai", "openai_compatible", "azure", "azure_openai", "lmstudio", "vllm", "localai", "koboldcpp", "llamacpp"} and resolved_base_url:
        endpoint = f"{resolved_base_url}/models"
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            return _normalize_model_ids(_fetch_json(endpoint, headers=headers), provider)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
            logger.info("Model catalog lookup failed for %s at %s: %s", provider, endpoint, exc)
            return []

    return []


_LOCAL_PROVIDER_NAMES = {
    "ollama",
    "lmstudio",
    "vllm",
    "localai",
    "koboldcpp",
    "llamacpp",
}


def _is_local_base_url(base_url: str | None) -> bool:
    if not base_url:
        return False
    normalized = base_url.strip().lower()
    return any(
        token in normalized
        for token in (
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "::1",
            "file://",
        )
    )


def provider_is_local(provider_name: str, base_url: str | None = None) -> bool:
    name = (provider_name or "").lower().strip()
    if name in _LOCAL_PROVIDER_NAMES:
        return True
    if name in {"openai_compatible", "azure_openai"} and _is_local_base_url(base_url):
        return True
    return _is_local_base_url(base_url)


def provider_requires_api_key(provider_name: str, base_url: str | None = None) -> bool:
    return not provider_is_local(provider_name, base_url)
