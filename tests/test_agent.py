"""Tests for DevOps Agent."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agent import SSH_SYSTEM_PROMPT, AgentResult, DevOpsAgent
from src.security import SecurityGuard
from src.state import StateManager
from src.tools import ToolRegistry, ToolResult


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_successful_result(self) -> None:
        """Successful result should have correct attributes."""
        result = AgentResult(
            success=True,
            response="Task completed",
            tools_used=["check_service"],
            iterations=2,
            duration_seconds=1.5,
        )
        assert result.success is True
        assert result.response == "Task completed"
        assert result.tools_used == ["check_service"]
        assert result.iterations == 2
        assert result.duration_seconds == 1.5
        assert result.error is None

    def test_failed_result(self) -> None:
        """Failed result should include error."""
        result = AgentResult(
            success=False,
            response="",
            error="API connection failed",
        )
        assert result.success is False
        assert result.error == "API connection failed"

    def test_default_values(self) -> None:
        """Should have correct default values."""
        result = AgentResult(success=True, response="test")
        assert result.tools_used == []
        assert result.iterations == 0
        assert result.duration_seconds == 0.0
        assert result.error is None


class TestDevOpsAgent:
    """Tests for DevOpsAgent."""

    @pytest.fixture
    def security_guard(self, tmp_path: Path) -> SecurityGuard:
        """Create SecurityGuard for tests."""
        allowlist_path = tmp_path / "allowlist.json"
        allowlist_path.write_text(
            json.dumps(
                {
                    "commands": {"system": ["echo", "ls"]},
                    "blocked_patterns": ["rm -rf"],
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
    def mock_client(self) -> AsyncMock:
        """Create mock AsyncAnthropic client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def agent(
        self,
        tool_registry: ToolRegistry,
        state_manager: StateManager,
        security_guard: SecurityGuard,
        mock_client: AsyncMock,
    ) -> DevOpsAgent:
        """Create DevOpsAgent with mocked client."""
        return DevOpsAgent(
            tool_registry=tool_registry,
            state_manager=state_manager,
            security_guard=security_guard,
            client=mock_client,
        )

    @pytest.mark.asyncio
    async def test_rejects_unauthorized_user(
        self, agent: DevOpsAgent, state_manager: StateManager
    ) -> None:
        """Should reject unauthorized users."""
        await state_manager.initialize()

        result = await agent.run(user_id=999, query="check nginx")

        assert result.success is False
        assert result.error == "User not authorized"

    @pytest.mark.asyncio
    async def test_creates_session_if_needed(
        self,
        agent: DevOpsAgent,
        state_manager: StateManager,
        mock_client: AsyncMock,
    ) -> None:
        """Should create session for new user."""
        await state_manager.initialize()

        # Mock Claude response with end_turn
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="Hello!")]
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        result = await agent.run(user_id=123, query="hello")

        assert result.success is True

        # Verify session was created
        session = await state_manager.get_active_session(123)
        assert session is not None

    @pytest.mark.asyncio
    async def test_simple_query_returns_response(
        self,
        agent: DevOpsAgent,
        state_manager: StateManager,
        mock_client: AsyncMock,
    ) -> None:
        """Should return Claude's response for simple queries."""
        await state_manager.initialize()

        # Mock response
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(type="text", text="The nginx service is running.")
        ]
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        result = await agent.run(user_id=123, query="Is nginx running?")

        assert result.success is True
        assert "nginx" in result.response.lower()
        assert result.iterations == 1

    @pytest.mark.asyncio
    async def test_uses_tools_when_needed(
        self,
        agent: DevOpsAgent,
        state_manager: StateManager,
        mock_client: AsyncMock,
    ) -> None:
        """Should execute tools when Claude requests them."""
        await state_manager.initialize()

        # First response: tool use
        tool_use_block = MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.name = "system_health"
        tool_use_block.input = {}
        tool_use_block.id = "tool_123"

        mock_response_1 = MagicMock()
        mock_response_1.content = [tool_use_block]
        mock_response_1.stop_reason = "tool_use"

        # Second response: final text
        mock_response_2 = MagicMock()
        mock_response_2.content = [
            MagicMock(type="text", text="System health looks good.")
        ]
        mock_response_2.stop_reason = "end_turn"

        mock_client.messages.create.side_effect = [mock_response_1, mock_response_2]

        result = await agent.run(user_id=123, query="Check system health")

        assert result.success is True
        assert "system_health" in result.tools_used
        assert result.iterations == 2

    @pytest.mark.asyncio
    async def test_respects_max_iterations(
        self,
        agent: DevOpsAgent,
        state_manager: StateManager,
        mock_client: AsyncMock,
    ) -> None:
        """Should stop after max_iterations."""
        await state_manager.initialize()
        agent._max_iterations = 2

        # Always return tool_use (never end_turn)
        tool_use_block = MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.name = "system_health"
        tool_use_block.input = {}
        tool_use_block.id = "tool_123"

        mock_response = MagicMock()
        mock_response.content = [tool_use_block]
        mock_response.stop_reason = "tool_use"

        mock_client.messages.create.return_value = mock_response

        result = await agent.run(user_id=123, query="Keep checking forever")

        assert result.success is True
        assert result.iterations == 2
        assert "maximum" in result.response.lower()

    @pytest.mark.asyncio
    async def test_handles_api_error(
        self,
        agent: DevOpsAgent,
        state_manager: StateManager,
        mock_client: AsyncMock,
    ) -> None:
        """Should handle API errors gracefully."""
        await state_manager.initialize()

        mock_client.messages.create.side_effect = Exception("API Error")

        result = await agent.run(user_id=123, query="test query")

        assert result.success is False
        assert result.error is not None
        assert "API Error" in result.error

    @pytest.mark.asyncio
    async def test_saves_incident(
        self,
        agent: DevOpsAgent,
        state_manager: StateManager,
        mock_client: AsyncMock,
    ) -> None:
        """Should save incident after execution."""
        await state_manager.initialize()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="Done")]
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        await agent.run(user_id=123, query="test incident")

        # Check incident was saved
        incidents = await state_manager.get_recent_incidents(user_id=123, limit=1)
        assert len(incidents) == 1
        assert incidents[0].query == "test incident"
        assert incidents[0].success is True

    @pytest.mark.asyncio
    async def test_records_tools_used(
        self,
        agent: DevOpsAgent,
        state_manager: StateManager,
        mock_client: AsyncMock,
    ) -> None:
        """Should record all tools used in incident."""
        await state_manager.initialize()

        # Use two different tools
        tool_1 = MagicMock()
        tool_1.type = "tool_use"
        tool_1.name = "system_health"
        tool_1.input = {}
        tool_1.id = "tool_1"

        tool_2 = MagicMock()
        tool_2.type = "tool_use"
        tool_2.name = "check_port"
        tool_2.input = {"port": 80}
        tool_2.id = "tool_2"

        mock_response_1 = MagicMock()
        mock_response_1.content = [tool_1, tool_2]
        mock_response_1.stop_reason = "tool_use"

        mock_response_2 = MagicMock()
        mock_response_2.content = [MagicMock(type="text", text="All checks done")]
        mock_response_2.stop_reason = "end_turn"

        mock_client.messages.create.side_effect = [mock_response_1, mock_response_2]

        result = await agent.run(user_id=123, query="Check everything")

        assert "system_health" in result.tools_used
        assert "check_port" in result.tools_used

        # Verify incident has tools
        incidents = await state_manager.get_recent_incidents(user_id=123, limit=1)
        assert "system_health" in incidents[0].tools_used
        assert "check_port" in incidents[0].tools_used

    @pytest.mark.asyncio
    async def test_handles_tool_execution_error(
        self,
        agent: DevOpsAgent,
        state_manager: StateManager,
        mock_client: AsyncMock,
    ) -> None:
        """Should handle tool execution errors gracefully."""
        await state_manager.initialize()

        # Mock tool that will fail
        tool_use_block = MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.name = "nonexistent_tool"
        tool_use_block.input = {}
        tool_use_block.id = "tool_fail"

        mock_response_1 = MagicMock()
        mock_response_1.content = [tool_use_block]
        mock_response_1.stop_reason = "tool_use"

        # Claude handles the error and responds
        mock_response_2 = MagicMock()
        mock_response_2.content = [
            MagicMock(type="text", text="Tool not found, but I handled it.")
        ]
        mock_response_2.stop_reason = "end_turn"

        mock_client.messages.create.side_effect = [mock_response_1, mock_response_2]

        result = await agent.run(user_id=123, query="Use unknown tool")

        # Should still succeed overall
        assert result.success is True
        assert result.iterations == 2

    @pytest.mark.asyncio
    async def test_uses_existing_session(
        self,
        agent: DevOpsAgent,
        state_manager: StateManager,
        mock_client: AsyncMock,
    ) -> None:
        """Should use existing session if provided."""
        await state_manager.initialize()

        # Create session first
        session = await state_manager.create_session(123)

        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="Using session")]
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        result = await agent.run(user_id=123, query="test", session_id=session.id)

        assert result.success is True

        # Verify messages were added to correct session
        messages = await state_manager.get_messages(session.id)
        assert len(messages) >= 1

    @pytest.mark.asyncio
    async def test_loads_conversation_history(
        self,
        agent: DevOpsAgent,
        state_manager: StateManager,
        mock_client: AsyncMock,
    ) -> None:
        """Should include conversation history in API call."""
        await state_manager.initialize()

        # Create session with history
        session = await state_manager.create_session(123)
        await state_manager.add_message(session.id, "user", "Previous question")
        await state_manager.add_message(session.id, "assistant", "Previous answer")

        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="New answer")]
        mock_response.stop_reason = "end_turn"
        mock_client.messages.create.return_value = mock_response

        await agent.run(user_id=123, query="New question", session_id=session.id)

        # Verify API was called with history
        call_kwargs = mock_client.messages.create.call_args.kwargs
        messages = call_kwargs["messages"]

        # Should have: prev_user, prev_assistant, new_user
        assert len(messages) == 3
        assert messages[0]["content"] == "Previous question"
        assert messages[1]["content"] == "Previous answer"
        assert messages[2]["content"] == "New question"


class TestDevOpsAgentIntegration:
    """Integration tests for DevOpsAgent."""

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
            allowed_user_ids=[123],
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

    @pytest.mark.asyncio
    async def test_tool_result_format(
        self,
        tool_registry: ToolRegistry,
        state_manager: StateManager,
        security_guard: SecurityGuard,
    ) -> None:
        """Tool results should be formatted correctly for Claude."""
        mock_client = AsyncMock()

        agent = DevOpsAgent(
            tool_registry=tool_registry,
            state_manager=state_manager,
            security_guard=security_guard,
            client=mock_client,
        )

        # Create successful tool result
        result = ToolResult(success=True, output="Command output")
        formatted = agent._format_tool_result("tool_123", result)

        assert formatted["type"] == "tool_result"
        assert formatted["tool_use_id"] == "tool_123"
        assert formatted["content"] == "Command output"
        assert formatted["is_error"] is False

        # Create failed tool result
        result_fail = ToolResult(success=False, output="", error="Command failed")
        formatted_fail = agent._format_tool_result("tool_456", result_fail)

        assert formatted_fail["is_error"] is True
        assert "Error" in formatted_fail["content"]


class TestSystemPrompt:
    """Tests for system prompt configuration."""

    def test_system_prompt_exists(self) -> None:
        """System prompt should be defined."""
        assert SSH_SYSTEM_PROMPT is not None
        assert len(SSH_SYSTEM_PROMPT) > 100

    def test_system_prompt_mentions_ssh(self) -> None:
        """System prompt should mention SSH functionality."""
        assert "ssh" in SSH_SYSTEM_PROMPT.lower()
        assert "сервер" in SSH_SYSTEM_PROMPT.lower()

    def test_system_prompt_has_permission_levels(self) -> None:
        """System prompt should mention permission levels."""
        assert "readonly" in SSH_SYSTEM_PROMPT.lower()
        assert "operator" in SSH_SYSTEM_PROMPT.lower()
        assert "admin" in SSH_SYSTEM_PROMPT.lower()
