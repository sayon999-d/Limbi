

from __future__ import annotations

import importlib
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger("limbi.llm_provider")

_PROVIDER_DEFAULT_MODELS = {
    "ollama": "llama3.2:3b",
    "ollama_cloud": "gpt-oss:120b-cloud",
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "google": "gemini-1.5-pro",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "openai/gpt-4o",
    "huggingface": "meta-llama/Llama-3.1-8B-Instruct",
    "chutes": "meta-llama/Llama-3.1-8B-Instruct",
    "bytez": "meta-llama/Llama-3.1-8B-Instruct",
    "together": "meta-llama/Llama-3-70b-chat-hf",
    "mistral": "mistral-large-latest",
    "azure": "gpt-4o",
    "cohere": "command-r-plus",
}

_PROVIDER_MODEL_ALIASES = {
    "groq": {
        "llama-3.1-70b-versatile": "llama-3.3-70b-versatile",
        "llama3-70b-8192": "llama-3.3-70b-versatile",
        "deepseek-r1-distill-llama-70b": "llama-3.3-70b-versatile",
    },
}

_OPTIONAL_DEPENDENCIES = {
    "langchain_ollama": ("langchain-ollama", "limbi[ollama]"),
    "langchain_openai": ("langchain-openai", "limbi[openai]"),
    "langchain_anthropic": ("langchain-anthropic", "limbi[anthropic]"),
    "langchain_google_genai": ("langchain-google-genai", "limbi[google]"),
    "langchain_groq": ("langchain-groq", "limbi[groq]"),
    "langchain_mistralai": ("langchain-mistralai", "limbi[mistral]"),
    "langchain_cohere": ("langchain-cohere", "limbi[cohere]"),
}

_PROVIDER_DEPENDENCY_HINTS = {
    "ollama": ("langchain_ollama", "langchain-ollama"),
    "ollama_cloud": ("langchain_openai", "langchain-openai"),
    "openai": ("langchain_openai", "langchain-openai"),
    "anthropic": ("langchain_anthropic", "langchain-anthropic"),
    "claude": ("langchain_anthropic", "langchain-anthropic"),
    "google": ("langchain_google_genai", "langchain-google-genai"),
    "gemini": ("langchain_google_genai", "langchain-google-genai"),
    "groq": ("langchain_groq", "langchain-groq"),
    "openrouter": ("langchain_openai", "langchain-openai"),
    "huggingface": ("langchain_openai", "langchain-openai"),
    "hf": ("langchain_openai", "langchain-openai"),
    "chutes": ("langchain_openai", "langchain-openai"),
    "bytez": ("langchain_openai", "langchain-openai"),
    "together": ("langchain_openai", "langchain-openai"),
    "mistral": ("langchain_mistralai", "langchain-mistralai"),
    "azure": ("langchain_openai", "langchain-openai"),
    "azure_openai": ("langchain_openai", "langchain-openai"),
    "cohere": ("langchain_cohere", "langchain-cohere"),
    "openai_compatible": ("langchain_openai", "langchain-openai"),
    "lmstudio": ("langchain_openai", "langchain-openai"),
    "vllm": ("langchain_openai", "langchain-openai"),
    "localai": ("langchain_openai", "langchain-openai"),
    "koboldcpp": ("langchain_openai", "langchain-openai"),
    "llamacpp": ("langchain_openai", "langchain-openai"),
}


def _require_optional_dependency(module_name: str, package_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        pip_package, limbi_extra = _OPTIONAL_DEPENDENCIES.get(module_name, (package_name, ""))
        hint = f"Install it with `python -m pip install '{pip_package}'`"
        if limbi_extra:
            hint += f" or `python -m pip install \"{limbi_extra}\"`"
        raise ModuleNotFoundError(
            f"Missing optional dependency '{pip_package}'. {hint}."
        ) from exc


def provider_dependency_hint(provider_name: str) -> tuple[str, str]:
    provider = (provider_name or "").strip().lower()
    return _PROVIDER_DEPENDENCY_HINTS.get(provider, ("", ""))


def normalize_provider_model(provider_name: str, model: str | None = None) -> str:
    provider = (provider_name or "").lower().strip()
    normalized_model = (model or "").strip()
    aliases = _PROVIDER_MODEL_ALIASES.get(provider, {})
    if normalized_model in aliases:
        return aliases[normalized_model]
    if normalized_model:
        return normalized_model
    return _PROVIDER_DEFAULT_MODELS.get(provider, "llama3.2:3b")

@dataclass
class ProviderConfig:

    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    temperature: float = 0.1
    max_tokens: int = 1024

    azure_deployment: str = ""
    azure_api_version: str = "2024-06-01"

    @classmethod
    def from_env(cls) -> "ProviderConfig":
        provider = os.getenv("LLM_PROVIDER", "ollama").lower().strip()
        explicit_base_url = os.getenv("LLM_BASE_URL", "").strip()
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "").strip()
        is_ollama_cloud = provider == "ollama_cloud" or "ollama.com" in explicit_base_url.lower() or "ollama.com" in ollama_base_url.lower()
        local_provider_names = {"ollama", "lmstudio", "vllm", "localai", "koboldcpp", "llamacpp"}
        default_model = normalize_provider_model(provider, None)
        default_base_url = "https://ollama.com/v1" if is_ollama_cloud else "http://localhost:11434"
        if provider in {"openai", "anthropic", "google", "groq", "together", "mistral", "azure", "cohere", "openrouter", "huggingface", "chutes", "bytez"}:
            default_base_url = ""
        if provider == "openai_compatible" and explicit_base_url:
            default_base_url = explicit_base_url
        if provider in local_provider_names:
            default_base_url = explicit_base_url or ollama_base_url or default_base_url
        if provider == "ollama" and not explicit_base_url and ollama_base_url:
            default_base_url = ollama_base_url

        return cls(
            provider=provider,
            model=normalize_provider_model(
                provider,
                os.getenv("LLM_MODEL", os.getenv("OLLAMA_MODEL", default_model)),
            ),
            base_url=explicit_base_url or default_base_url,
            api_key=os.getenv("LLM_API_KEY", os.getenv("OLLAMA_API_KEY", "")),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1024")),
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


class OllamaCloudProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "ollama_cloud"

    def get_chat_model(self) -> BaseChatModel:
        ChatOpenAI = _require_optional_dependency("langchain_openai", "langchain-openai").ChatOpenAI
        return ChatOpenAI(
            model=self.config.model or "gpt-oss:120b-cloud",
            api_key=self.config.api_key,
            base_url=self.config.base_url or "https://ollama.com/v1",
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

class OpenAIProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "openai"

    def get_chat_model(self) -> BaseChatModel:
        ChatOpenAI = _require_optional_dependency("langchain_openai", "langchain-openai").ChatOpenAI
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
            model=normalize_provider_model(self.provider_name(), self.config.model),
            api_key=self.config.api_key,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

class TogetherProvider(BaseLLMProvider):

    def provider_name(self) -> str:
        return "together"

    def get_chat_model(self) -> BaseChatModel:
        ChatOpenAI = _require_optional_dependency("langchain_openai", "langchain-openai").ChatOpenAI
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
        AzureChatOpenAI = _require_optional_dependency("langchain_openai", "langchain-openai").AzureChatOpenAI
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
        ChatOpenAI = _require_optional_dependency("langchain_openai", "langchain-openai").ChatOpenAI
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
        ChatOpenAI = _require_optional_dependency("langchain_openai", "langchain-openai").ChatOpenAI
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
        ChatOpenAI = _require_optional_dependency("langchain_openai", "langchain-openai").ChatOpenAI
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
        ChatOpenAI = _require_optional_dependency("langchain_openai", "langchain-openai").ChatOpenAI
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
        ChatOpenAI = _require_optional_dependency("langchain_openai", "langchain-openai").ChatOpenAI
        return ChatOpenAI(
            model=self.config.model or "default",
            api_key=self.config.api_key or "not-needed",
            base_url=self.config.base_url,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

_PROVIDER_MAP: dict[str, type[BaseLLMProvider]] = {
    "ollama": OllamaProvider,
    "ollama_cloud": OllamaCloudProvider,
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
    if cfg.provider == "ollama" and not provider_is_local(cfg.provider, cfg.base_url):
        provider_cls = OllamaCloudProvider

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
    "ollama_cloud": ("https://ollama.com/api/tags", "bearer"),
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


def _parse_parameter_size(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    text = str(value).strip().lower()
    if not text:
        return None
    text = text.replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([kmgt]?)\s*(?:params?|parameters?|b|m|k)?", text)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2)
    multiplier = {
        "": 1.0,
        "k": 1_000.0,
        "m": 1_000_000.0,
        "g": 1_000_000_000.0,
        "t": 1_000_000_000_000.0,
    }.get(suffix, 1.0)
    if "b" in text and suffix == "":
        multiplier = 1_000_000_000.0
    return number * multiplier


def _extract_model_size_score(row: Any) -> float | None:
    if isinstance(row, dict):
        for key in (
            "parameter_size",
            "parameterSize",
            "parameters",
            "params",
            "size",
        ):
            score = _parse_parameter_size(row.get(key))
            if score:
                return score
        details = row.get("details")
        if isinstance(details, dict):
            for key in ("parameter_size", "parameterSize", "parameters", "params", "size"):
                score = _parse_parameter_size(details.get(key))
                if score:
                    return score
        if isinstance(details, str):
            score = _parse_parameter_size(details)
            if score:
                return score
        for key in ("id", "modelId", "name", "slug"):
            score = _parse_parameter_size(row.get(key))
            if score:
                return score
    elif isinstance(row, str):
        return _parse_parameter_size(row)
    return None


def _normalize_model_ids(payload: Any, provider: str) -> list[str]:
    rows: list[Any] = []
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("output") or payload.get("models") or []
    elif isinstance(payload, list):
        rows = payload
    if not isinstance(rows, list):
        return []

    ranked: list[tuple[int, float | None, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
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
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        ranked.append((index, _extract_model_size_score(row), model_id))

    ranked.sort(
        key=lambda item: (
            1 if item[1] is None else 0,
            -(item[1] or 0.0),
            item[0],
            item[2],
        )
    )
    return [item[2] for item in ranked]


def list_available_models(provider_name: str, api_key: str = "", base_url: str | None = None) -> list[str]:
    provider = (provider_name or "").lower().strip()
    resolved_base_url = (base_url or "").strip().rstrip("/")

    if provider == "ollama":
        endpoint = "https://ollama.com/api/tags" if not provider_is_local(provider, base_url) else f"{resolved_base_url or 'http://localhost:11434'}/api/tags"
        headers: dict[str, str] = {}
        if api_key and not provider_is_local(provider, base_url):
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            return _normalize_model_ids(_fetch_json(endpoint, headers=headers), provider)
        except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
            logger.info("Model catalog lookup failed for %s at %s: %s", provider, endpoint, exc)
            return []

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
    if name == "ollama":
        if base_url and not _is_local_base_url(base_url):
            return False
        return True
    if name in _LOCAL_PROVIDER_NAMES:
        return True
    if name in {"openai_compatible", "azure_openai"} and _is_local_base_url(base_url):
        return True
    return _is_local_base_url(base_url)


def provider_requires_api_key(provider_name: str, base_url: str | None = None) -> bool:
    return not provider_is_local(provider_name, base_url)
