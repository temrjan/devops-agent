"""Application configuration."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: SecretStr = Field(alias="TELEGRAM_BOT_TOKEN")
    allowed_user_ids: list[int] = Field(default_factory=list, alias="ALLOWED_USER_IDS")

    # Anthropic
    anthropic_api_key: SecretStr = Field(alias="ANTHROPIC_API_KEY")
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096

    # Paths
    base_dir: Path = Path(__file__).parent.parent

    # Agent
    max_iterations: int = 10
    tool_timeout: int = 30

    # SSH
    ssh_config_path: Path = Path.home() / ".ssh" / "config"
    ssh_known_hosts_path: Path = Path.home() / ".ssh" / "known_hosts"
    ssh_permissions_path: Path | None = None  # Defaults to config/ssh_permissions.json

    # Debug
    debug: bool = False

    @property
    def data_dir(self) -> Path:
        """Get data directory path."""
        return self.base_dir / "data"

    @property
    def logs_dir(self) -> Path:
        """Get logs directory path."""
        return self.base_dir / "logs"

    @property
    def effective_ssh_permissions_path(self) -> Path:
        """Get SSH permissions file path."""
        if self.ssh_permissions_path:
            return self.ssh_permissions_path
        return self.base_dir / "config" / "ssh_permissions.json"


settings = Settings()
