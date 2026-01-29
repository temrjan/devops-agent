"""Tests for Telegram bot."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent import AgentResult
from src.bot import DevOpsBot, RateLimiter, create_bot
from src.security import SecurityGuard
from src.state import StateManager
from src.tools import ToolRegistry


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_allows_under_limit(self) -> None:
        """Should allow requests under limit."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)

        for _ in range(4):
            assert not limiter.is_limited(123)
            limiter.record(123)

    def test_blocks_over_limit(self) -> None:
        """Should block requests over limit."""
        limiter = RateLimiter(max_requests=3, window_seconds=60)

        for _ in range(3):
            limiter.record(123)

        assert limiter.is_limited(123)

    def test_reset_clears_limit(self) -> None:
        """Should clear limit after reset."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        limiter.record(123)
        limiter.record(123)
        assert limiter.is_limited(123)

        limiter.reset(123)
        assert not limiter.is_limited(123)

    def test_different_users_independent(self) -> None:
        """Different users should have independent limits."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)

        limiter.record(123)
        limiter.record(123)

        assert limiter.is_limited(123)
        assert not limiter.is_limited(456)


class TestDevOpsBot:
    """Tests for DevOpsBot."""

    @pytest.fixture
    def security_guard(self, tmp_path: Path) -> SecurityGuard:
        """Create SecurityGuard for tests."""
        allowlist_path = tmp_path / "allowlist.json"
        allowlist_path.write_text(
            json.dumps(
                {
                    "commands": {"system": ["echo"]},
                    "blocked_patterns": [],
                }
            )
        )
        return SecurityGuard(
            allowed_user_ids=[123, 456],
            allowlist_path=allowlist_path,
            audit_log_path=tmp_path / "audit.log",
        )

    @pytest.fixture
    def state_manager(self, tmp_path: Path) -> StateManager:
        """Create StateManager for tests."""
        return StateManager(db_path=tmp_path / "test.db")

    @pytest.fixture
    def tool_registry(self, security_guard: SecurityGuard) -> ToolRegistry:
        """Create ToolRegistry for tests."""
        return ToolRegistry(security_guard=security_guard)

    @pytest.fixture
    def mock_agent(self) -> MagicMock:
        """Create mock DevOpsAgent."""
        agent = MagicMock()
        agent.run = AsyncMock(
            return_value=AgentResult(
                success=True,
                response="Task completed",
                tools_used=["system_health"],
                iterations=1,
                duration_seconds=0.5,
            )
        )
        return agent

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        """Create mock aiogram Bot."""
        bot = MagicMock()
        bot.session = MagicMock()
        bot.session.close = AsyncMock()
        return bot

    @pytest.fixture
    def devops_bot(
        self,
        security_guard: SecurityGuard,
        state_manager: StateManager,
        tool_registry: ToolRegistry,
        mock_agent: MagicMock,
        mock_bot: MagicMock,
    ) -> DevOpsBot:
        """Create DevOpsBot for tests."""
        return DevOpsBot(
            security_guard=security_guard,
            state_manager=state_manager,
            tool_registry=tool_registry,
            agent=mock_agent,
            bot=mock_bot,
        )

    def create_mock_message(self, user_id: int, text: str = "test") -> MagicMock:
        """Create mock Message object.

        Args:
            user_id: User ID for the message.
            text: Message text.

        Returns:
            Mock Message object.
        """
        message = MagicMock()
        message.from_user = MagicMock()
        message.from_user.id = user_id
        message.text = text
        message.answer = AsyncMock()
        return message

    @pytest.mark.asyncio
    async def test_check_auth_allows_authorized(self, devops_bot: DevOpsBot) -> None:
        """Should allow authorized users."""
        message = self.create_mock_message(user_id=123)
        result = await devops_bot._check_auth(message)
        assert result is True

    @pytest.mark.asyncio
    async def test_check_auth_blocks_unauthorized(self, devops_bot: DevOpsBot) -> None:
        """Should block unauthorized users."""
        message = self.create_mock_message(user_id=999)
        result = await devops_bot._check_auth(message)
        assert result is False

    @pytest.mark.asyncio
    async def test_check_rate_limit_allows_normal(self, devops_bot: DevOpsBot) -> None:
        """Should allow requests under rate limit."""
        message = self.create_mock_message(user_id=123)
        result = await devops_bot._check_rate_limit(message)
        assert result is True

    @pytest.mark.asyncio
    async def test_check_rate_limit_blocks_excessive(
        self, devops_bot: DevOpsBot
    ) -> None:
        """Should block excessive requests."""
        message = self.create_mock_message(user_id=123)

        # Exhaust rate limit
        for _ in range(10):
            devops_bot.rate_limiter.record(123)

        result = await devops_bot._check_rate_limit(message)
        assert result is False
        message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_start_authorized(self, devops_bot: DevOpsBot) -> None:
        """Should respond to /start for authorized users."""
        message = self.create_mock_message(user_id=123, text="/start")

        await devops_bot._handle_start(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "DevOps Agent" in call_args

    @pytest.mark.asyncio
    async def test_handle_start_unauthorized(self, devops_bot: DevOpsBot) -> None:
        """Should not respond to /start for unauthorized users."""
        message = self.create_mock_message(user_id=999, text="/start")

        await devops_bot._handle_start(message)

        message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_help(self, devops_bot: DevOpsBot) -> None:
        """Should respond to /help command."""
        message = self.create_mock_message(user_id=123, text="/help")

        await devops_bot._handle_help(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Справка" in call_args

    @pytest.mark.asyncio
    async def test_handle_health(
        self,
        devops_bot: DevOpsBot,
        state_manager: StateManager,
    ) -> None:
        """Should return system health."""
        await state_manager.initialize()
        message = self.create_mock_message(user_id=123, text="/health")

        await devops_bot._handle_health(message)

        # Should be called twice: "Проверяю..." and result
        assert message.answer.call_count == 2

    @pytest.mark.asyncio
    async def test_handle_logs_with_service(
        self,
        devops_bot: DevOpsBot,
        state_manager: StateManager,
    ) -> None:
        """Should return logs for specified service."""
        await state_manager.initialize()
        message = self.create_mock_message(user_id=123, text="/logs nginx")

        await devops_bot._handle_logs(message)

        # Should be called twice: "Читаю..." and result
        assert message.answer.call_count >= 2

    @pytest.mark.asyncio
    async def test_handle_logs_without_service(self, devops_bot: DevOpsBot) -> None:
        """Should ask for service name if not provided."""
        message = self.create_mock_message(user_id=123, text="/logs")

        await devops_bot._handle_logs(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Укажите сервис" in call_args

    @pytest.mark.asyncio
    async def test_handle_status(
        self,
        devops_bot: DevOpsBot,
        state_manager: StateManager,
    ) -> None:
        """Should return agent status."""
        await state_manager.initialize()
        message = self.create_mock_message(user_id=123, text="/status")

        await devops_bot._handle_status(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Статус агента" in call_args

    @pytest.mark.asyncio
    async def test_handle_history_empty(
        self,
        devops_bot: DevOpsBot,
        state_manager: StateManager,
    ) -> None:
        """Should show message when history is empty."""
        await state_manager.initialize()
        message = self.create_mock_message(user_id=123, text="/history")

        await devops_bot._handle_history(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "пуста" in call_args.lower()

    @pytest.mark.asyncio
    async def test_handle_history_with_incidents(
        self,
        devops_bot: DevOpsBot,
        state_manager: StateManager,
    ) -> None:
        """Should show incident history."""
        await state_manager.initialize()

        # Add some incidents
        await state_manager.save_incident(
            user_id=123,
            query="check nginx",
            resolution="nginx is running",
            success=True,
        )

        message = self.create_mock_message(user_id=123, text="/history")
        await devops_bot._handle_history(message)

        message.answer.assert_called_once()
        call_args = message.answer.call_args[0][0]
        assert "Последние инциденты" in call_args

    @pytest.mark.asyncio
    async def test_handle_message_triggers_agent(
        self,
        devops_bot: DevOpsBot,
        state_manager: StateManager,
        mock_agent: MagicMock,
    ) -> None:
        """Should trigger agent for regular messages."""
        await state_manager.initialize()
        message = self.create_mock_message(user_id=123, text="check nginx status")

        await devops_bot._handle_message(message)

        mock_agent.run.assert_called_once_with(
            user_id=123, query="check nginx status", model="claude-sonnet-4-20250514"
        )

    @pytest.mark.asyncio
    async def test_handle_message_sends_response(
        self,
        devops_bot: DevOpsBot,
        state_manager: StateManager,
    ) -> None:
        """Should send agent response to user."""
        await state_manager.initialize()
        message = self.create_mock_message(user_id=123, text="test query")

        await devops_bot._handle_message(message)

        # Should be called: "Обрабатываю..." and response
        assert message.answer.call_count >= 2

        # Check response includes agent result
        last_call = message.answer.call_args_list[-1]
        assert "Task completed" in last_call[0][0]

    @pytest.mark.asyncio
    async def test_handle_message_shows_tools_used(
        self,
        devops_bot: DevOpsBot,
        state_manager: StateManager,
    ) -> None:
        """Should show which tools were used."""
        await state_manager.initialize()
        message = self.create_mock_message(user_id=123, text="test")

        await devops_bot._handle_message(message)

        last_call = message.answer.call_args_list[-1]
        assert "system_health" in last_call[0][0]

    @pytest.mark.asyncio
    async def test_handle_message_agent_error(
        self,
        devops_bot: DevOpsBot,
        state_manager: StateManager,
        mock_agent: MagicMock,
    ) -> None:
        """Should show error when agent fails."""
        await state_manager.initialize()
        mock_agent.run.return_value = AgentResult(
            success=False,
            response="",
            error="Test error",
        )

        message = self.create_mock_message(user_id=123, text="test")
        await devops_bot._handle_message(message)

        last_call = message.answer.call_args_list[-1]
        assert "Ошибка" in last_call[0][0]

    def test_split_message_short(self, devops_bot: DevOpsBot) -> None:
        """Should not split short messages."""
        text = "Short message"
        chunks = devops_bot._split_message(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_message_long(self, devops_bot: DevOpsBot) -> None:
        """Should split long messages."""
        text = "Line\n" * 1000  # Long text
        chunks = devops_bot._split_message(text, max_length=100)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 100


class TestDevOpsBotRateLimiting:
    """Tests for rate limiting integration."""

    @pytest.fixture
    def security_guard(self, tmp_path: Path) -> SecurityGuard:
        """Create SecurityGuard for tests."""
        allowlist_path = tmp_path / "allowlist.json"
        allowlist_path.write_text(json.dumps({"commands": {}, "blocked_patterns": []}))
        return SecurityGuard(
            allowed_user_ids=[123],
            allowlist_path=allowlist_path,
            audit_log_path=tmp_path / "audit.log",
        )

    @pytest.fixture
    def state_manager(self, tmp_path: Path) -> StateManager:
        """Create StateManager for tests."""
        return StateManager(db_path=tmp_path / "test.db")

    @pytest.fixture
    def devops_bot(
        self,
        security_guard: SecurityGuard,
        state_manager: StateManager,
    ) -> DevOpsBot:
        """Create DevOpsBot for tests."""
        tools = ToolRegistry(security_guard=security_guard)
        agent = MagicMock()
        agent.run = AsyncMock(return_value=AgentResult(success=True, response="OK"))
        mock_bot = MagicMock()
        mock_bot.session = MagicMock()
        mock_bot.session.close = AsyncMock()

        return DevOpsBot(
            security_guard=security_guard,
            state_manager=state_manager,
            tool_registry=tools,
            agent=agent,
            bot=mock_bot,
        )

    @pytest.mark.asyncio
    async def test_rate_limited_health_command(
        self,
        devops_bot: DevOpsBot,
        state_manager: StateManager,
    ) -> None:
        """Rate limited user should be blocked from /health."""
        await state_manager.initialize()

        # Exhaust rate limit
        for _ in range(10):
            devops_bot.rate_limiter.record(123)

        message = MagicMock()
        message.from_user = MagicMock()
        message.from_user.id = 123
        message.text = "/health"
        message.answer = AsyncMock()

        await devops_bot._handle_health(message)

        # Should only get rate limit message
        message.answer.assert_called_once()
        assert "Слишком много" in message.answer.call_args[0][0]


class TestCreateBot:
    """Tests for create_bot factory function."""

    @pytest.mark.asyncio
    async def test_create_bot_returns_devops_bot(self) -> None:
        """Should return configured DevOpsBot."""
        with patch("src.bot.Bot"):
            bot = await create_bot()
            assert isinstance(bot, DevOpsBot)
