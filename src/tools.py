"""SSH-based DevOps tools for the agent.

Provides async tools for remote server management via SSH.
All commands are executed on remote servers, not locally.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from .security import SecurityGuard
    from .ssh_manager import SSHManager


@dataclass(slots=True)
class ToolResult:
    """Result of tool execution.

    Attributes:
        success: Whether the tool executed successfully.
        output: Tool output text.
        error: Error message if execution failed.
        metadata: Additional structured data from the tool.
    """

    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    """Base class for all tools.

    Each tool must define name, description, and parameters schema
    compatible with Claude's tool_use format.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    parameters: ClassVar[dict[str, Any]]

    def __init__(
        self,
        ssh_manager: SSHManager | None = None,
        security_guard: SecurityGuard | None = None,
    ) -> None:
        """Initialize tool.

        Args:
            ssh_manager: SSHManager for remote execution.
            security_guard: SecurityGuard for command validation.
        """
        self._ssh = ssh_manager
        self._security = security_guard

    @abstractmethod
    async def execute(self, **_kwargs: Any) -> ToolResult:
        """Execute the tool with given arguments.

        Args:
            **kwargs: Tool-specific arguments.

        Returns:
            ToolResult with execution outcome.
        """
        raise NotImplementedError

    def to_claude_schema(self) -> dict[str, Any]:
        """Convert tool to Claude API schema format.

        Returns:
            Dictionary compatible with Claude's tools parameter.
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class SSHExecuteTool(Tool):
    """Execute a command on remote server via SSH."""

    name: ClassVar[str] = "ssh_execute"
    description: ClassVar[str] = (
        "Execute a command on a remote server via SSH. "
        "Commands are subject to permission level restrictions based on the host. "
        "IMPORTANT: Each command runs in a separate SSH session. "
        "To run multiple related commands, combine them with && "
        "(e.g., 'cd /opt/app && docker compose ps')."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute on the remote server",
            },
            "host": {
                "type": "string",
                "description": (
                    "Server alias from configuration (e.g., 'biotact', 'prod-1'). "
                    "If not specified, uses the default host."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": "Command timeout in seconds (default: 60)",
                "default": 60,
            },
        },
        "required": ["command"],
    }

    async def execute(
        self,
        command: str,
        host: str | None = None,
        timeout: int | None = None,
        user_id: int = 0,
        **_kwargs: Any,
    ) -> ToolResult:
        """Execute command on remote server via SSH.

        Args:
            command: Shell command to execute.
            host: Server alias (default: from config).
            timeout: Execution timeout in seconds.
            user_id: User ID for security validation.
            **_kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with command output or error.
        """
        if not self._ssh:
            return ToolResult(
                success=False,
                output="",
                error="SSH manager not configured",
            )

        result = await self._ssh.execute(
            command=command,
            host=host,
            timeout=timeout,
            user_id=user_id,
        )

        # Build output with truncation info if needed
        output = result.output
        if result.truncated and result.truncated_info:
            output = f"{output}\n\n[{result.truncated_info}]"

        return ToolResult(
            success=result.success,
            output=output,
            error=result.error if not result.success else None,
            metadata={
                "host": result.host,
                "exit_code": result.exit_code,
                "truncated": result.truncated,
            },
        )


class SSHListHostsTool(Tool):
    """List available SSH hosts and their permission levels."""

    name: ClassVar[str] = "ssh_list_hosts"
    description: ClassVar[str] = (
        "List all available SSH hosts with their permission levels and descriptions. "
        "Use this to see which servers are available and what actions are allowed on each."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **_kwargs: Any) -> ToolResult:
        """List available SSH hosts.

        Args:
            **_kwargs: Additional arguments (ignored).

        Returns:
            ToolResult with host list.
        """
        if not self._ssh:
            return ToolResult(
                success=False,
                output="",
                error="SSH manager not configured",
            )

        hosts_info = self._ssh.format_hosts_list()
        host_count = len(self._ssh.list_hosts())

        return ToolResult(
            success=True,
            output=hosts_info,
            metadata={
                "host_count": host_count,
                "default_host": self._ssh.settings.default_host,
            },
        )


class ToolRegistry:
    """Registry for managing available tools.

    Provides methods to register, retrieve, and list tools.
    """

    def __init__(
        self,
        ssh_manager: SSHManager | None = None,
        security_guard: SecurityGuard | None = None,
    ) -> None:
        """Initialize registry.

        Args:
            ssh_manager: SSHManager for remote execution.
            security_guard: SecurityGuard for command validation.
        """
        self._tools: dict[str, Tool] = {}
        self._ssh = ssh_manager
        self._security = security_guard
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register all default tools."""
        default_tools: list[type[Tool]] = [
            SSHExecuteTool,
            SSHListHostsTool,
        ]

        for tool_cls in default_tools:
            tool = tool_cls(
                ssh_manager=self._ssh,
                security_guard=self._security,
            )
            self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Get tool by name.

        Args:
            name: Tool name.

        Returns:
            Tool instance or None if not found.
        """
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names.

        Returns:
            List of tool names.
        """
        return list(self._tools.keys())

    def get_all_schemas(self) -> list[dict[str, Any]]:
        """Get Claude API schemas for all tools.

        Returns:
            List of tool schemas for Claude API.
        """
        return [tool.to_claude_schema() for tool in self._tools.values()]

    async def execute(
        self,
        tool_name: str,
        user_id: int = 0,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute a tool by name.

        Args:
            tool_name: Name of tool to execute.
            user_id: User ID for security validation.
            **kwargs: Tool arguments.

        Returns:
            ToolResult from tool execution.
        """
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {tool_name}",
            )

        # Add user_id to kwargs for security checks
        kwargs["user_id"] = user_id

        return await tool.execute(**kwargs)
