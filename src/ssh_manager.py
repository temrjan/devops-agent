"""SSH Manager for remote command execution.

This module provides SSH connectivity to remote servers using asyncssh.
It uses standard ~/.ssh/config for connection settings and a separate
permissions file for access control.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import asyncssh
import structlog

if TYPE_CHECKING:
    from .security import SecurityGuard

logger = structlog.get_logger()


class PermissionLevel(str, Enum):
    """Permission levels for SSH hosts."""

    READONLY = "readonly"
    OPERATOR = "operator"
    ADMIN = "admin"


@dataclass(slots=True)
class SSHResult:
    """Result of SSH command execution."""

    success: bool
    output: str
    error: str
    exit_code: int
    host: str
    truncated: bool = False
    truncated_info: str | None = None


@dataclass(slots=True)
class HostConfig:
    """Configuration for a single SSH host."""

    alias: str
    level: PermissionLevel
    description: str


@dataclass(slots=True)
class SSHSettings:
    """SSH-related settings."""

    hosts: dict[str, HostConfig] = field(default_factory=dict)
    default_host: str = "biotact"
    connection_timeout: int = 10
    command_timeout: int = 60
    max_output_lines: int = 150
    max_output_bytes: int = 65536


# Command patterns for permission levels
READONLY_PATTERNS: list[str] = [
    # System info
    r"^cat\s+",
    r"^ls(\s+|$)",
    r"^df(\s+|$)",
    r"^free(\s+|$)",
    r"^uptime$",
    r"^top\s+-bn1",
    r"^ps(\s+|$)",
    r"^netstat(\s+|$)",
    r"^ss(\s+|$)",
    r"^du(\s+|$)",
    r"^head(\s+|$)",
    r"^tail(\s+|$)",
    r"^grep(\s+|$)",
    r"^find(\s+|$)",
    r"^wc(\s+|$)",
    r"^stat(\s+|$)",
    r"^file(\s+|$)",
    r"^which(\s+|$)",
    r"^whoami$",
    r"^hostname$",
    r"^uname(\s+|$)",
    r"^date$",
    r"^id$",
    r"^env$",
    r"^printenv",
    # Service status (read-only)
    r"^systemctl\s+status\s+",
    r"^systemctl\s+is-active\s+",
    r"^systemctl\s+is-enabled\s+",
    r"^systemctl\s+list-units",
    r"^journalctl(\s+|$)",
    # Docker status
    r"^docker\s+ps",
    r"^docker\s+logs(\s+|$)",
    r"^docker\s+inspect(\s+|$)",
    r"^docker\s+images",
    r"^docker\s+stats",
    r"^docker\s+top(\s+|$)",
    r"^docker\s+compose\s+ps",
    r"^docker\s+compose\s+logs",
    r"^docker\s+compose\s+config",
    # Network
    r"^curl(\s+|$)",
    r"^wget\s+.*-O\s*-",  # wget to stdout only
    r"^ping(\s+|$)",
    r"^dig(\s+|$)",
    r"^nslookup(\s+|$)",
    r"^traceroute(\s+|$)",
    r"^host(\s+|$)",
    r"^ip(\s+|$)",
    r"^ifconfig(\s+|$)",
]

OPERATOR_PATTERNS: list[str] = READONLY_PATTERNS + [
    # Service management
    r"^systemctl\s+(restart|start|stop|reload)\s+",
    r"^systemctl\s+daemon-reload$",
    # Docker management
    r"^docker\s+(restart|start|stop)\s+",
    r"^docker\s+compose\s+(up|down|restart|pull)",
    r"^docker\s+exec(\s+|$)",
]

# Admin: all commands except dangerous patterns (checked in SecurityGuard)


class SSHManager:
    """Manager for SSH connections and command execution.

    Uses standard ~/.ssh/config for connection parameters and
    config/ssh_permissions.json for access control.
    """

    def __init__(
        self,
        permissions_path: Path,
        security: SecurityGuard,
        ssh_config_path: Path | None = None,
        known_hosts_path: Path | None = None,
    ) -> None:
        """Initialize SSH Manager.

        Args:
            permissions_path: Path to ssh_permissions.json
            security: SecurityGuard instance for command validation
            ssh_config_path: Path to SSH config (default: ~/.ssh/config)
            known_hosts_path: Path to known_hosts (default: ~/.ssh/known_hosts)
        """
        self._permissions_path = permissions_path
        self._security = security
        self._ssh_config_path = ssh_config_path or Path.home() / ".ssh" / "config"
        self._known_hosts_path = known_hosts_path or Path.home() / ".ssh" / "known_hosts"
        self._settings: SSHSettings | None = None
        self._logger = logger.bind(component="ssh_manager")

    async def initialize(self) -> None:
        """Load permissions configuration."""
        self._settings = await self._load_permissions()
        self._logger.info(
            "SSH Manager initialized",
            hosts=list(self._settings.hosts.keys()),
            default_host=self._settings.default_host,
        )

    async def _load_permissions(self) -> SSHSettings:
        """Load permissions from JSON file."""
        if not self._permissions_path.exists():
            raise FileNotFoundError(
                f"SSH permissions file not found: {self._permissions_path}"
            )

        content = self._permissions_path.read_text()
        data = json.loads(content)

        hosts: dict[str, HostConfig] = {}
        for alias, config in data.get("hosts", {}).items():
            hosts[alias] = HostConfig(
                alias=alias,
                level=PermissionLevel(config["level"]),
                description=config.get("description", ""),
            )

        return SSHSettings(
            hosts=hosts,
            default_host=data.get("default_host", "biotact"),
            connection_timeout=data.get("connection_timeout", 10),
            command_timeout=data.get("command_timeout", 60),
            max_output_lines=data.get("max_output_lines", 150),
            max_output_bytes=data.get("max_output_bytes", 65536),
        )

    @property
    def settings(self) -> SSHSettings:
        """Get SSH settings."""
        if self._settings is None:
            msg = "SSHManager not initialized. Call initialize() first."
            raise RuntimeError(msg)
        return self._settings

    def get_host_config(self, host: str) -> HostConfig | None:
        """Get configuration for a host."""
        return self.settings.hosts.get(host)

    def list_hosts(self) -> list[HostConfig]:
        """List all configured hosts."""
        return list(self.settings.hosts.values())

    def is_host_allowed(self, host: str) -> bool:
        """Check if host is in the allowed list."""
        return host in self.settings.hosts

    def is_command_allowed_for_level(
        self, command: str, level: PermissionLevel
    ) -> bool:
        """Check if command is allowed for permission level.

        Args:
            command: Command to check
            level: Permission level of the host

        Returns:
            True if command is allowed for this level
        """
        command = command.strip()

        # Admin can do anything (dangerous patterns checked separately)
        if level == PermissionLevel.ADMIN:
            return True

        # Select patterns based on level
        patterns = (
            OPERATOR_PATTERNS
            if level == PermissionLevel.OPERATOR
            else READONLY_PATTERNS
        )

        # Check if command matches any allowed pattern
        for pattern in patterns:
            if re.match(pattern, command):
                return True

        return False

    def _truncate_output(self, output: str) -> tuple[str, bool, str | None]:
        """Truncate output if it exceeds limits.

        Args:
            output: Raw output string

        Returns:
            Tuple of (truncated_output, was_truncated, info_message)
        """
        settings = self.settings
        lines = output.split("\n")

        # Check line count
        if len(lines) > settings.max_output_lines:
            truncated = "\n".join(lines[: settings.max_output_lines])
            info = f"Показано {settings.max_output_lines} из {len(lines)} строк"
            return truncated, True, info

        # Check byte size
        output_bytes = len(output.encode("utf-8"))
        if output_bytes > settings.max_output_bytes:
            # Truncate carefully to avoid breaking UTF-8
            truncated = output[: settings.max_output_bytes]
            # Find last complete line
            last_newline = truncated.rfind("\n")
            if last_newline > 0:
                truncated = truncated[:last_newline]
            info = f"Вывод обрезан до {settings.max_output_bytes // 1024}KB"
            return truncated, True, info

        return output, False, None

    async def execute(
        self,
        command: str,
        host: str | None = None,
        timeout: int | None = None,
        user_id: int | None = None,
    ) -> SSHResult:
        """Execute command on remote host via SSH.

        Args:
            command: Command to execute
            host: Host alias (default: from settings)
            timeout: Command timeout in seconds (default: from settings)
            user_id: User ID for audit logging

        Returns:
            SSHResult with execution results
        """
        settings = self.settings
        host = host or settings.default_host
        timeout = timeout or settings.command_timeout

        log = self._logger.bind(host=host, command=command[:100], user_id=user_id)

        # Check host is allowed
        if not self.is_host_allowed(host):
            log.warning("Unknown host requested")
            return SSHResult(
                success=False,
                output="",
                error=f"Сервер '{host}' не найден в конфигурации. "
                f"Доступные: {', '.join(settings.hosts.keys())}",
                exit_code=-1,
                host=host,
            )

        host_config = self.get_host_config(host)
        assert host_config is not None  # Already checked above

        # Check command is allowed for this host's permission level
        if not self.is_command_allowed_for_level(command, host_config.level):
            log.warning(
                "Command not allowed for permission level",
                level=host_config.level.value,
            )
            return SSHResult(
                success=False,
                output="",
                error=f"Команда запрещена на {host} (уровень: {host_config.level.value}). "
                f"На этом сервере разрешены только команды для уровня '{host_config.level.value}'.",
                exit_code=-1,
                host=host,
            )

        # Check dangerous patterns via SecurityGuard (skip allowlist, we use per-level)
        if user_id is not None:
            is_allowed, warnings = self._security.validate_command(
                user_id, command, skip_allowlist=True
            )
            if not is_allowed:
                log.warning("Command blocked by security guard", warnings=warnings)
                return SSHResult(
                    success=False,
                    output="",
                    error=f"Команда заблокирована: {'; '.join(warnings)}",
                    exit_code=-1,
                    host=host,
                )

        # Execute via SSH
        try:
            log.info("Executing SSH command")

            # Read SSH config for connection parameters
            async with asyncssh.connect(
                host,
                config=str(self._ssh_config_path),
                known_hosts=str(self._known_hosts_path),
                connect_timeout=settings.connection_timeout,
            ) as conn:
                result = await asyncio.wait_for(
                    conn.run(command, check=False),
                    timeout=timeout,
                )

            stdout = result.stdout or ""
            stderr = result.stderr or ""
            exit_code = result.exit_status or 0

            # Truncate output if needed
            stdout, truncated, truncated_info = self._truncate_output(stdout)

            success = exit_code == 0

            log.info(
                "SSH command completed",
                exit_code=exit_code,
                stdout_len=len(stdout),
                stderr_len=len(stderr),
                truncated=truncated,
            )

            # Audit log
            if user_id is not None:
                self._security.audit_log(
                    user_id=user_id,
                    action="ssh_execute",
                    details=json.dumps(
                        {
                            "host": host,
                            "command": command,
                            "exit_code": exit_code,
                            "success": success,
                        }
                    ),
                )

            return SSHResult(
                success=success,
                output=stdout,
                error=stderr,
                exit_code=exit_code,
                host=host,
                truncated=truncated,
                truncated_info=truncated_info,
            )

        except asyncssh.DisconnectError as e:
            log.error("SSH disconnect error", error=str(e))
            return SSHResult(
                success=False,
                output="",
                error=f"Сервер {host} разорвал соединение: {e}",
                exit_code=-1,
                host=host,
            )

        except asyncssh.PermissionDenied as e:
            log.error("SSH permission denied", error=str(e))
            return SSHResult(
                success=False,
                output="",
                error=f"Ошибка аутентификации на {host}. Проверьте SSH ключ.",
                exit_code=-1,
                host=host,
            )

        except asyncssh.HostKeyNotVerifiable as e:
            log.error("SSH host key not verifiable", error=str(e))
            return SSHResult(
                success=False,
                output="",
                error=f"Host key {host} не верифицирован. "
                "Возможно, ключ сервера изменился (MITM?) или сервер переустановлен. "
                "Проверьте ~/.ssh/known_hosts.",
                exit_code=-1,
                host=host,
            )

        except asyncio.TimeoutError:
            log.error("SSH command timeout", timeout=timeout)
            return SSHResult(
                success=False,
                output="",
                error=f"Команда на {host} превысила таймаут {timeout}с",
                exit_code=-1,
                host=host,
            )

        except OSError as e:
            log.error("SSH connection error", error=str(e))
            return SSHResult(
                success=False,
                output="",
                error=f"Сервер {host} недоступен: {e}",
                exit_code=-1,
                host=host,
            )

        except asyncssh.Error as e:
            log.error("SSH error", error=str(e))
            return SSHResult(
                success=False,
                output="",
                error=f"SSH ошибка на {host}: {e}",
                exit_code=-1,
                host=host,
            )

    def format_hosts_list(self) -> str:
        """Format list of hosts for display.

        Returns:
            Formatted string with host information
        """
        lines = ["Доступные серверы:", ""]

        for config in self.settings.hosts.values():
            level_str = f"({config.level.value})"
            lines.append(f"• {config.alias} {level_str} — {config.description}")

        lines.append("")
        lines.append(f"По умолчанию: {self.settings.default_host}")

        return "\n".join(lines)
