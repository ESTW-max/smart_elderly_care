from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_API_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    app_name: str = "MiniApp API"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    cors_origins: str = (
        "http://localhost:5173,http://localhost:5174,"
        "http://127.0.0.1:5173,http://127.0.0.1:5174"
    )
    jwt_secret: str = "replace-this-in-production"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_temperature: float = 0.2
    deepseek_max_output_tokens: int = 4096
    deepseek_timeout_seconds: float = 60.0
    deepseek_max_retries: int = 2
    agent_system_prompt: str = "You are a helpful coding agent."
    agent_workspace: str = "."
    agent_test_endpoint_enabled: bool = False
    agent_api_token: str = ""
    agent_max_steps: int = 100
    agent_max_tokens: int = 100_000
    agent_max_seconds: float = 3600.0
    agent_context_max_tokens: int = 16_000
    agent_message_max_tokens: int = 8_000
    agent_tool_output_max_tokens: int = 6_000
    agent_state_database_path: str = "./data/agent-state.db"
    agent_allowed_commands: str = "pwd,ls,find,grep,git,python,pytest,ruff"
    agent_file_read_enabled: bool = True
    agent_file_write_enabled: bool = False
    agent_approval_required_risk: str = "high"
    agent_max_output_chars: int = 8_000
    agent_max_cpu_seconds: int | None = None
    agent_max_file_size_bytes: int = 10_000_000
    agent_blocked_env_prefixes: str = "DEEPSEEK_,OPENAI_,ANTHROPIC_"

    model_config = SettingsConfigDict(
        env_file=(str(_PROJECT_ROOT / ".env"), str(_API_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def agent_api_token_map(self) -> dict[str, str]:
        """Parse ``name:token`` pairs into an actor-to-token mapping.

        A bare entry without ``:`` is attributed to the actor ``default``.
        An empty setting yields an empty map, which callers treat as
        "no credentials configured" rather than "no authentication needed".
        """
        tokens: dict[str, str] = {}
        for entry in self.agent_api_token.split(","):
            entry = entry.strip()
            if not entry:
                continue
            actor, separator, token = entry.partition(":")
            if not separator:
                actor, token = "default", actor
            actor, token = actor.strip(), token.strip()
            if token:
                tokens[actor or "default"] = token
        return tokens


@lru_cache
def get_settings() -> Settings:
    return Settings()
