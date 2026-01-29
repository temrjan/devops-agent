"""Tests for configuration."""

from pathlib import Path

import pytest


class TestSettings:
    """Tests for Settings class."""

    def test_base_dir_exists(self) -> None:
        """Base directory should exist."""
        from src.config import settings
        assert settings.base_dir.exists()

    def test_default_model(self) -> None:
        """Default model should be set."""
        from src.config import settings
        assert "claude" in settings.model

    def test_max_iterations_positive(self) -> None:
        """Max iterations should be positive."""
        from src.config import settings
        assert settings.max_iterations > 0

    def test_tool_timeout_positive(self) -> None:
        """Tool timeout should be positive."""
        from src.config import settings
        assert settings.tool_timeout > 0
