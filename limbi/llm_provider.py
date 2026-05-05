

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger("limbi.llm_provider")

@dataclass
class ProviderConfig:

    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    temperature: float = 0.3
    max_tokens: int = 4096

    azure_deployment: str = ""
    azure_api_version: str = "2024-06-01"

    @classmethod
    def from_env(cls) -> "ProviderConfig":

        return cls(
            provider=os.getenv("LLM_PROVIDER", "ollama").lower().strip(),
            model=os.getenv("LLM_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2:3b")),
            base_url=os.getenv("LLM_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")),
            api_key=os.getenv("LLM_API_KEY", ""),
            temperature=float(os.getenv("LLM_TEMPERATURE", "0.3")),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
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
    "together": TogetherProvider,
    "mistral": MistralProvider,
    "azure": AzureOpenAIProvider,
    "azure_openai": AzureOpenAIProvider,
    "cohere": CohereProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "lmstudio": OpenAICompatibleProvider,
    "vllm": OpenAICompatibleProvider,
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
