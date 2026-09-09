"""Runtime settings. Every value can come from environment variables or a .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from harness_server import __version__

DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    # server (env aliases: HARNESS_HOST / HARNESS_PORT / HARNESS_DATA_DIR …)
    host: str = Field(default="127.0.0.1", validation_alias="HARNESS_HOST")
    port: int = Field(default=9876, validation_alias="HARNESS_PORT")
    data_dir: Path = Field(default=Path("./data"), validation_alias="HARNESS_DATA_DIR")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    debug: bool = Field(default=False, validation_alias="DEBUG")

    # agent loop
    max_agent_steps: int = 20
    max_vision_refinements: int = 3
    blender_tool_timeout_s: float = 120.0
    llm_timeout_s: float = 180.0
    allow_execute_python: bool = False

    # LLM (OpenAI-compatible)
    ai_base_url: Optional[str] = None
    ai_api_key: Optional[str] = None
    ai_model: Optional[str] = None

    # Vision (falls back to chat provider when unset)
    ai_vision_base_url: Optional[str] = None
    ai_vision_api_key: Optional[str] = None
    ai_vision_model: Optional[str] = None

    # ------------------------------------------------------------------
    @property
    def base_url(self) -> str:
        return (self.ai_base_url or DEFAULT_OPENAI_BASE).rstrip("/")

    @property
    def chat_configured(self) -> bool:
        return bool(self.ai_model)

    @property
    def chat_model(self) -> str:
        return self.ai_model or ""

    @property
    def vision_base_url(self) -> str:
        return (self.ai_vision_base_url or self.base_url).rstrip("/")

    @property
    def vision_api_key(self) -> Optional[str]:
        return self.ai_vision_api_key or self.ai_api_key

    @property
    def vision_model(self) -> Optional[str]:
        # "" or unset -> reuse chat model when chat is configured
        if self.ai_vision_model is None or self.ai_vision_model == "":
            return self.ai_model
        return self.ai_vision_model

    @property
    def vision_configured(self) -> bool:
        model = self.vision_model
        if not model:
            return False
        # local providers (ollama / lm studio / vllm on localhost) work without a key
        if self.vision_api_key:
            return True
        base = self.vision_base_url
        return "localhost" in base or "127.0.0.1" in base or "0.0.0.0" in base

    @property
    def version(self) -> str:
        return __version__

    def media_dir(self) -> Path:
        p = self.data_dir / "media"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def logs_dir(self) -> Path:
        p = self.data_dir.parent / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p
