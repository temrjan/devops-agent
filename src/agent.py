"""DevOps Agent with Agentic Loop.

Provides the main agent class that orchestrates Claude API calls,
tool execution, and conversation management.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from anthropic import AsyncAnthropic
from anthropic.types import Message, ToolUseBlock

from src.config import settings
from src.security import SecurityGuard
from src.state import StateManager
from src.tools import ToolRegistry, ToolResult

if TYPE_CHECKING:
    from src.ssh_manager import SSHManager

logger = logging.getLogger(__name__)

SSH_SYSTEM_PROMPT = """Ты DevOps агент с доступом к удалённым серверам через SSH.

## Доступные серверы:
{hosts_list}

## Инструменты:
- ssh_execute: Выполнить команду на удалённом сервере
- ssh_list_hosts: Показать список серверов

## Правила работы:

### 1. Выбор сервера
- По умолчанию используй: {default_host}
- Если пользователь указал сервер — используй его
- Если неясно какой сервер — спроси или используй default

### 2. Выполнение команд
ВАЖНО: Каждая команда выполняется в ОТДЕЛЬНОЙ SSH сессии!
- Плохо: ssh_execute("cd /opt/app"), потом ssh_execute("docker compose ps")
- Хорошо: ssh_execute(command="cd /opt/app && docker compose ps")

### 3. Последовательность действий
1. GATHER — собери информацию (status, logs, df, ps)
2. ANALYZE — определи проблему
3. ACT — выполни исправление
4. VERIFY — проверь результат

### 4. Permission Levels
- readonly: только чтение (cat, ls, df, ps, docker ps, systemctl status)
- operator: чтение + управление сервисами (systemctl restart, docker restart)
- admin: почти всё (кроме опасных команд)

### 5. Интерактивные команды
НЕ используй команды, требующие ввода:
- vim, nano, less, more → используй cat, head, tail
- mysql, psql без параметров → используй -e "query"
- apt upgrade без -y

## Формат ответов:
- Будь кратким и по делу
- Сообщай что делаешь и почему
- При ошибках объясняй причину
- После исправления — проверяй результат
"""


@dataclass(slots=True)
class AgentResult:
    """Result of agent execution.

    Attributes:
        success: Whether the agent completed successfully.
        response: Final text response to user.
        tools_used: List of tool names that were executed.
        iterations: Number of API calls made.
        duration_seconds: Total execution time.
        error: Error message if execution failed.
    """

    success: bool
    response: str
    tools_used: list[str] = field(default_factory=list)
    iterations: int = 0
    duration_seconds: float = 0.0
    error: str | None = None


class DevOpsAgent:
    """DevOps Agent with Agentic Loop.

    Orchestrates conversation with Claude API, executes tools,
    and manages conversation state.

    Args:
        tool_registry: Registry of available tools.
        state_manager: Manager for session and message persistence.
        security_guard: Guard for user authorization and command validation.
        ssh_manager: Manager for SSH connections.
        client: Optional AsyncAnthropic client (for testing).
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        state_manager: StateManager,
        security_guard: SecurityGuard,
        ssh_manager: SSHManager | None = None,
        client: AsyncAnthropic | None = None,
    ) -> None:
        """Initialize DevOpsAgent.

        Args:
            tool_registry: Registry of available tools.
            state_manager: Manager for session and message persistence.
            security_guard: Guard for user authorization.
            ssh_manager: Manager for SSH connections.
            client: Optional AsyncAnthropic client for dependency injection.
        """
        self._client = client or AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )
        self._tools = tool_registry
        self._state = state_manager
        self._security = security_guard
        self._ssh = ssh_manager
        self._max_iterations = settings.max_iterations
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build system prompt with SSH hosts information.

        Returns:
            Formatted system prompt string.
        """
        if not self._ssh:
            return SSH_SYSTEM_PROMPT.format(
                hosts_list="(SSH не настроен)",
                default_host="(не задан)",
            )

        hosts_list = self._ssh.format_hosts_list()
        default_host = self._ssh.settings.default_host

        return SSH_SYSTEM_PROMPT.format(
            hosts_list=hosts_list,
            default_host=default_host,
        )

    async def run(
        self,
        user_id: int,
        query: str,
        session_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult:
        """Run the agent with user query.

        Executes the agentic loop: sends query to Claude, processes tool calls,
        and continues until Claude returns a final response or max iterations.

        Args:
            user_id: Telegram user ID for authorization.
            query: User's query text.
            session_id: Optional existing session ID.
            model: Optional model override (e.g., 'claude-opus-4-20250514').

        Returns:
            AgentResult with response and execution metadata.
        """
        # Use provided model or default from config
        active_model = model or settings.model
        start_time = time.monotonic()
        tools_used: list[str] = []

        # Check user authorization
        if not self._security.is_user_allowed(user_id):
            self._security.audit_log(
                user_id, "agent_run", query, allowed=False, warnings=["Unauthorized"]
            )
            return AgentResult(
                success=False,
                response="",
                error="User not authorized",
                duration_seconds=time.monotonic() - start_time,
            )

        try:
            # Get or create session
            session = await self._get_or_create_session(user_id, session_id)

            # Build messages from history
            messages = await self._build_messages(session.id, query)

            # Save user message
            await self._state.add_message(session.id, "user", query)

            # Get tool schemas
            tool_schemas = self._tools.get_all_schemas()

            # Agentic loop
            iterations = 0
            final_response = ""

            while iterations < self._max_iterations:
                iterations += 1
                logger.info(f"Agent iteration {iterations}/{self._max_iterations}, model={active_model}")

                # Call Claude API
                response = await self._call_claude(messages, tool_schemas, active_model)

                # Extract text and tool calls
                text_response, tool_calls = self._parse_response(response)

                if text_response:
                    final_response = text_response

                # Check if we should stop
                if response.stop_reason == "end_turn":
                    logger.debug("Agent received end_turn, finishing")
                    break

                if response.stop_reason == "max_tokens":
                    logger.warning("Response truncated due to max_tokens")
                    break

                # Process tool calls
                if tool_calls:
                    # Add assistant message with tool calls
                    messages.append({"role": "assistant", "content": response.content})

                    # Execute tools and collect results
                    tool_results = await self._execute_tools(
                        tool_calls, user_id, tools_used
                    )

                    # Add tool results as user message
                    messages.append({"role": "user", "content": tool_results})
                else:
                    # No tool calls and not end_turn - unusual, but handle gracefully
                    logger.warning(
                        f"No tool calls and stop_reason={response.stop_reason}"
                    )
                    break

            # Check if we hit max iterations
            if (
                iterations >= self._max_iterations
                and response.stop_reason != "end_turn"
            ):
                logger.warning(f"Max iterations ({self._max_iterations}) reached")
                if not final_response:
                    final_response = (
                        "I've reached the maximum number of steps. "
                        "Please try a simpler request."
                    )

            # Save assistant response
            if final_response:
                await self._state.add_message(session.id, "assistant", final_response)

            # Calculate duration
            duration = time.monotonic() - start_time

            # Save incident
            await self._state.save_incident(
                user_id=user_id,
                query=query,
                resolution=final_response,
                tools_used=tools_used,
                success=True,
                duration_seconds=duration,
            )

            self._security.audit_log(user_id, "agent_run", query, allowed=True)

            return AgentResult(
                success=True,
                response=final_response,
                tools_used=tools_used,
                iterations=iterations,
                duration_seconds=duration,
            )

        except Exception as e:
            logger.exception("Agent execution error")
            duration = time.monotonic() - start_time

            # Save failed incident
            await self._state.save_incident(
                user_id=user_id,
                query=query,
                resolution=None,
                tools_used=tools_used,
                success=False,
                duration_seconds=duration,
            )

            return AgentResult(
                success=False,
                response="",
                tools_used=tools_used,
                iterations=0,
                duration_seconds=duration,
                error=str(e),
            )

    async def _get_or_create_session(self, user_id: int, session_id: str | None) -> Any:
        """Get existing session or create new one.

        Args:
            user_id: Telegram user ID.
            session_id: Optional existing session ID.

        Returns:
            Session object.
        """
        if session_id:
            session = await self._state.get_session(session_id)
            if session and session.status == "active":
                return session

        # Try to get active session for user
        session = await self._state.get_active_session(user_id)
        if session:
            return session

        # Create new session
        return await self._state.create_session(user_id)

    async def _build_messages(
        self, session_id: str, current_query: str
    ) -> list[dict[str, Any]]:
        """Build messages list from session history.

        Args:
            session_id: Session ID to load history from.
            current_query: Current user query (not yet saved).

        Returns:
            List of message dicts for Claude API.
        """
        messages: list[dict[str, Any]] = []

        # Load recent messages from session
        history = await self._state.get_messages(session_id, limit=20)

        for msg in history:
            if msg.role in ("user", "assistant"):
                messages.append({"role": msg.role, "content": msg.content})

        # Add current query
        messages.append({"role": "user", "content": current_query})

        return messages

    async def _call_claude(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
    ) -> Message:
        """Call Claude API with messages and tools.

        Args:
            messages: Conversation messages.
            tools: Tool schemas for Claude.
            model: Model ID to use.

        Returns:
            Claude API Message response.
        """
        return await self._client.messages.create(
            model=model,
            max_tokens=settings.max_tokens,
            system=self._system_prompt,
            messages=messages,  # type: ignore[arg-type]
            tools=tools,  # type: ignore[arg-type]
        )

    def _parse_response(self, response: Message) -> tuple[str, list[ToolUseBlock]]:
        """Parse Claude response into text and tool calls.

        Args:
            response: Claude API Message response.

        Returns:
            Tuple of (text_response, list_of_tool_calls).
        """
        text_parts: list[str] = []
        tool_calls: list[ToolUseBlock] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(block)

        return "\n".join(text_parts), tool_calls

    async def _execute_tools(
        self,
        tool_calls: list[ToolUseBlock],
        user_id: int,
        tools_used: list[str],
    ) -> list[dict[str, Any]]:
        """Execute tool calls and format results.

        Args:
            tool_calls: List of ToolUseBlock from Claude response.
            user_id: User ID for security validation.
            tools_used: List to append used tool names to.

        Returns:
            List of tool_result dicts for Claude API.
        """
        results: list[dict[str, Any]] = []

        for tool_call in tool_calls:
            tool_name = tool_call.name
            tool_input = tool_call.input
            tool_id = tool_call.id

            logger.info(f"Executing tool: {tool_name}")

            # Track tool usage
            if tool_name not in tools_used:
                tools_used.append(tool_name)

            # Execute tool
            result = await self._tools.execute(tool_name, user_id=user_id, **tool_input)

            # Format result for Claude
            results.append(self._format_tool_result(tool_id, result))

        return results

    def _format_tool_result(self, tool_id: str, result: ToolResult) -> dict[str, Any]:
        """Format ToolResult for Claude API.

        Args:
            tool_id: Tool use ID from Claude.
            result: ToolResult from tool execution.

        Returns:
            Dict formatted for Claude tool_result.
        """
        if result.success:
            content = result.output
        else:
            content = f"Error: {result.error}" if result.error else "Unknown error"

        return {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": content,
            "is_error": not result.success,
        }
