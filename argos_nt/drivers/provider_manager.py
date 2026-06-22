from __future__ import annotations

import json
from enum import Enum
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from argos_nt.config_manager import AppConfig


class Provider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"


class ProviderManager:
    """Instantiate chat providers dynamically from runtime configuration."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def get_active_provider(self) -> Provider:
        return Provider(self._config.ai.provider.lower())

    def get_model_name_for_provider(self, provider: Provider) -> str:
        ai = self._config.ai
        if provider == Provider.OLLAMA:
            return ai.ollama_model or ai.model
        if provider == Provider.OPENAI:
            return ai.openai_model or ai.model
        if provider == Provider.ANTHROPIC:
            return ai.anthropic_model or ai.model
        if provider == Provider.DEEPSEEK:
            return ai.deepseek_model or ai.model
        return ai.model

    def get_active_model_name(self) -> str:
        return self.get_model_name_for_provider(self.get_active_provider())

    def get_chat_model(self) -> BaseChatModel:
        provider = self.get_active_provider()
        model_name = self.get_model_name_for_provider(provider)

        if provider == Provider.OLLAMA:
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=model_name,
                base_url=self._config.ai.ollama_base_url,
                temperature=0.1,
            )

        if provider == Provider.OPENAI:
            from langchain_openai import ChatOpenAI

            if not self._config.api_keys.openai:
                raise ValueError("OPENAI_API_KEY is required for provider 'openai'.")

            return ChatOpenAI(
                model=model_name,
                api_key=self._config.api_keys.openai,
                temperature=0.1,
            )

        if provider == Provider.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic

            if not self._config.api_keys.anthropic:
                raise ValueError("ANTHROPIC_API_KEY is required for provider 'anthropic'.")

            return ChatAnthropic(
                model=model_name,
                api_key=self._config.api_keys.anthropic,
                temperature=0.1,
            )

        if provider == Provider.DEEPSEEK:
            from langchain_openai import ChatOpenAI

            if not self._config.api_keys.deepseek:
                raise ValueError("DEEPSEEK_API_KEY is required for provider 'deepseek'.")

            return ChatOpenAI(
                model=model_name,
                api_key=self._config.api_keys.deepseek,
                base_url=self._config.ai.deepseek_base_url,
                temperature=0.1,
            )

        raise ValueError(f"Unsupported provider: {provider}")

    def invoke_json(self, system_prompt: str, user_input: str) -> dict[str, Any]:
        model = self.get_chat_model()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input),
        ]
        response = model.invoke(messages)
        content = str(response.content)
        return json.loads(content)
