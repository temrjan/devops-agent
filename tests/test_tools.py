"""Tests for SSH-based DevOps tools."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.security import SecurityGuard
from src.ssh_manager import SSHManager, SSHResult
from src.tools import SSHExecuteTool, SSHListHostsTool, ToolRegistry, ToolResult


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_successful_result(self) -> None:
        """Successful result should have correct attributes."""
        result = ToolResult(success=True, output="test output")
        assert result.success is True
        assert result.output == "test output"
        assert result.error is None
        assert result.metadata == {}

    def test_failed_result(self) -> None:
        """Failed result should include error."""
        result = ToolResult(success=False, output="", error="test error")
        assert result.success is False
        assert result.error == "test error"

    def test_result_with_metadata(self) -> None:
        """Result should include metadata."""
        result = ToolResult(
            success=True,
            output="test",
            metadata={"key": "value"},
        )
        assert result.metadata["key"] == "value"


class TestSSHExecuteTool:
    """Tests for SSHExecuteTool."""

    @pytest.fixture
    def mock_ssh_manager(self) -> MagicMock:
        """Create mock SSH manager."""
        manager = MagicMock(spec=SSHManager)
        manager.execute = AsyncMock()
        return manager

    @pytest.fixture
    def tool(self, mock_ssh_manager: MagicMock) -> SSHExecuteTool:
        """Create SSHExecuteTool with mock SSH manager."""
        return SSHExecuteTool(ssh_manager=mock_ssh_manager)

    def test_tool_has_required_attributes(self, tool: SSHExecuteTool) -> None:
        """Tool should have required attributes."""
        assert tool.name == "ssh_execute"
        assert "SSH" in tool.description
        assert "command" in tool.parameters["properties"]

    def test_to_claude_schema(self, tool: SSHExecuteTool) -> None:
        """Tool should generate valid Claude API schema."""
        schema = tool.to_claude_schema()

        assert schema["name"] == "ssh_execute"
        assert "description" in schema
        assert "input_schema" in schema
        assert schema["input_schema"]["type"] == "object"
        assert "command" in schema["input_schema"]["required"]

    @pytest.mark.asyncio
    async def test_execute_without_ssh_manager(self) -> None:
        """Tool should fail if SSH manager not configured."""
        tool = SSHExecuteTool(ssh_manager=None)
        result = await tool.execute(command="ls")

        assert result.success is False
        assert "not configured" in result.error

    @pytest.mark.asyncio
    async def test_execute_success(
        self, tool: SSHExecuteTool, mock_ssh_manager: MagicMock
    ) -> None:
        """Tool should return successful result."""
        mock_ssh_manager.execute.return_value = SSHResult(
            success=True,
            output="file1\nfile2",
            error="",
            exit_code=0,
            host="biotact",
        )

        result = await tool.execute(command="ls", host="biotact", user_id=123)

        assert result.success is True
        assert "file1" in result.output
        assert result.metadata["host"] == "biotact"
        assert result.metadata["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_execute_failure(
        self, tool: SSHExecuteTool, mock_ssh_manager: MagicMock
    ) -> None:
        """Tool should return error on failure."""
        mock_ssh_manager.execute.return_value = SSHResult(
            success=False,
            output="",
            error="Connection refused",
            exit_code=-1,
            host="biotact",
        )

        result = await tool.execute(command="ls", host="biotact", user_id=123)

        assert result.success is False
        assert result.error == "Connection refused"

    @pytest.mark.asyncio
    async def test_execute_with_truncation(
        self, tool: SSHExecuteTool, mock_ssh_manager: MagicMock
    ) -> None:
        """Tool should include truncation info in output."""
        mock_ssh_manager.execute.return_value = SSHResult(
            success=True,
            output="truncated output",
            error="",
            exit_code=0,
            host="biotact",
            truncated=True,
            truncated_info="Показано 150 из 1000 строк",
        )

        result = await tool.execute(command="cat large_file", user_id=123)

        assert result.success is True
        assert "truncated output" in result.output
        assert "150" in result.output
        assert result.metadata["truncated"] is True


class TestSSHListHostsTool:
    """Tests for SSHListHostsTool."""

    @pytest.fixture
    def mock_ssh_manager(self) -> MagicMock:
        """Create mock SSH manager."""
        manager = MagicMock(spec=SSHManager)
        manager.format_hosts_list.return_value = """Доступные серверы:

• biotact (admin) — BioTact server
• prod-1 (readonly) — Production 1

По умолчанию: biotact"""
        manager.list_hosts.return_value = [MagicMock(), MagicMock()]
        manager.settings.default_host = "biotact"
        return manager

    @pytest.fixture
    def tool(self, mock_ssh_manager: MagicMock) -> SSHListHostsTool:
        """Create SSHListHostsTool with mock SSH manager."""
        return SSHListHostsTool(ssh_manager=mock_ssh_manager)

    def test_tool_has_required_attributes(self, tool: SSHListHostsTool) -> None:
        """Tool should have required attributes."""
        assert tool.name == "ssh_list_hosts"
        assert "hosts" in tool.description.lower()

    def test_to_claude_schema(self, tool: SSHListHostsTool) -> None:
        """Tool should generate valid Claude API schema."""
        schema = tool.to_claude_schema()

        assert schema["name"] == "ssh_list_hosts"
        assert schema["input_schema"]["required"] == []

    @pytest.mark.asyncio
    async def test_execute_without_ssh_manager(self) -> None:
        """Tool should fail if SSH manager not configured."""
        tool = SSHListHostsTool(ssh_manager=None)
        result = await tool.execute()

        assert result.success is False
        assert "not configured" in result.error

    @pytest.mark.asyncio
    async def test_execute_success(
        self, tool: SSHListHostsTool, mock_ssh_manager: MagicMock
    ) -> None:
        """Tool should return host list."""
        result = await tool.execute()

        assert result.success is True
        assert "biotact" in result.output
        assert "admin" in result.output
        assert result.metadata["host_count"] == 2
        assert result.metadata["default_host"] == "biotact"


class TestToolRegistry:
    """Tests for ToolRegistry."""

    @pytest.fixture
    def mock_ssh_manager(self) -> MagicMock:
        """Create mock SSH manager."""
        manager = MagicMock(spec=SSHManager)
        manager.execute = AsyncMock()
        manager.format_hosts_list.return_value = "hosts list"
        manager.list_hosts.return_value = []
        manager.settings.default_host = "biotact"
        return manager

    @pytest.fixture
    def registry(self, mock_ssh_manager: MagicMock) -> ToolRegistry:
        """Create ToolRegistry with mock SSH manager."""
        return ToolRegistry(ssh_manager=mock_ssh_manager)

    def test_registry_has_default_tools(self, registry: ToolRegistry) -> None:
        """Registry should have default SSH tools."""
        tools = registry.list_tools()
        assert "ssh_execute" in tools
        assert "ssh_list_hosts" in tools

    def test_get_tool(self, registry: ToolRegistry) -> None:
        """Registry should return tool by name."""
        tool = registry.get("ssh_execute")
        assert tool is not None
        assert tool.name == "ssh_execute"

    def test_get_unknown_tool(self, registry: ToolRegistry) -> None:
        """Registry should return None for unknown tool."""
        tool = registry.get("unknown_tool")
        assert tool is None

    def test_get_all_schemas(self, registry: ToolRegistry) -> None:
        """Registry should return schemas for all tools."""
        schemas = registry.get_all_schemas()
        assert len(schemas) == 2

        names = [s["name"] for s in schemas]
        assert "ssh_execute" in names
        assert "ssh_list_hosts" in names

    @pytest.mark.asyncio
    async def test_execute_tool(
        self, registry: ToolRegistry, mock_ssh_manager: MagicMock
    ) -> None:
        """Registry should execute tool by name."""
        mock_ssh_manager.execute.return_value = SSHResult(
            success=True,
            output="test",
            error="",
            exit_code=0,
            host="biotact",
        )

        result = await registry.execute("ssh_execute", command="ls", user_id=123)

        assert result.success is True
        mock_ssh_manager.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, registry: ToolRegistry) -> None:
        """Registry should return error for unknown tool."""
        result = await registry.execute("unknown_tool", user_id=123)

        assert result.success is False
        assert "Unknown tool" in result.error


class TestToolRegistryWithoutSSH:
    """Tests for ToolRegistry without SSH manager."""

    def test_registry_without_ssh_manager(self) -> None:
        """Registry should work without SSH manager (tools will fail on execute)."""
        registry = ToolRegistry(ssh_manager=None)
        tools = registry.list_tools()
        assert "ssh_execute" in tools

    @pytest.mark.asyncio
    async def test_execute_without_ssh_manager(self) -> None:
        """Tools should fail gracefully without SSH manager."""
        registry = ToolRegistry(ssh_manager=None)
        result = await registry.execute("ssh_execute", command="ls", user_id=123)

        assert result.success is False
        assert "not configured" in result.error
