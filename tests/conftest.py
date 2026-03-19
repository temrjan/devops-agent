"""Shared test configuration."""

import os

# Set test environment variables before any src imports
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-for-ci")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")
os.environ.setdefault("LLM_PROVIDER", "anthropic")
