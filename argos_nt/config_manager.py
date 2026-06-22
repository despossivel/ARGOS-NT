from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Neo4jConfig(BaseModel):
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "argosnt123"
    database: str = "neo4j"


class ApiKeys(BaseModel):
    openai: str | None = None
    deepseek: str | None = None
    anthropic: str | None = None


class AiConfig(BaseModel):
    provider: str = "ollama"
    # Legacy shared model fallback (kept for backward compatibility).
    model: str = "llama3.1:8b"

    ollama_model: str = "llama3.1:8b"
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-3-5-sonnet-latest"
    deepseek_model: str = "deepseek-chat"

    ollama_base_url: str = "http://localhost:11434"
    deepseek_base_url: str = "https://api.deepseek.com/v1"


class AppConfig(BaseModel):
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    api_keys: ApiKeys = Field(default_factory=ApiKeys)
    ai: AiConfig = Field(default_factory=AiConfig)


class ConfigManager:
    """Load and persist ARGOS-NT configuration from JSON and environment."""

    def __init__(self, config_path: str | Path = "config/config.json") -> None:
        self.config_path = Path(config_path)

    def load(self) -> AppConfig:
        if not self.config_path.exists():
            return self._from_env(AppConfig())

        with self.config_path.open("r", encoding="utf-8") as file:
            payload: dict[str, Any] = json.load(file)

        config = AppConfig.model_validate(payload)
        return self._from_env(config)

    def save(self, config: AppConfig) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as file:
            json.dump(config.model_dump(), file, indent=2)

    def _from_env(self, config: AppConfig) -> AppConfig:
        config.neo4j.uri = os.getenv("NEO4J_URI", config.neo4j.uri)
        config.neo4j.username = os.getenv("NEO4J_USERNAME", config.neo4j.username)
        config.neo4j.password = os.getenv("NEO4J_PASSWORD", config.neo4j.password)
        config.neo4j.database = os.getenv("NEO4J_DATABASE", config.neo4j.database)

        config.api_keys.openai = os.getenv("OPENAI_API_KEY", config.api_keys.openai)
        config.api_keys.deepseek = os.getenv("DEEPSEEK_API_KEY", config.api_keys.deepseek)
        config.api_keys.anthropic = os.getenv("ANTHROPIC_API_KEY", config.api_keys.anthropic)

        config.ai.provider = os.getenv("ARGOS_AI_PROVIDER", config.ai.provider)
        config.ai.model = os.getenv("ARGOS_AI_MODEL", config.ai.model)

        config.ai.ollama_model = os.getenv("ARGOS_OLLAMA_MODEL", config.ai.ollama_model)
        config.ai.openai_model = os.getenv("ARGOS_OPENAI_MODEL", config.ai.openai_model)
        config.ai.anthropic_model = os.getenv("ARGOS_ANTHROPIC_MODEL", config.ai.anthropic_model)
        config.ai.deepseek_model = os.getenv("ARGOS_DEEPSEEK_MODEL", config.ai.deepseek_model)

        config.ai.ollama_base_url = os.getenv("OLLAMA_BASE_URL", config.ai.ollama_base_url)
        config.ai.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", config.ai.deepseek_base_url)
        return config
