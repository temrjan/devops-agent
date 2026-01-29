"""Tests for SSH Manager."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.security import SecurityGuard
from src.ssh_manager import (
    HostConfig,
    PermissionLevel,
    SSHManager,
    SSHResult,
    SSHSettings,
)


class TestSSHResult:
    """Tests for SSHResult dataclass."""

    def test_successful_result(self) -> None:
        """Successful result should have correct attributes."""
        result = SSHResult(
            success=True,
            output="test output",
            error="",
            exit_code=0,
            host="biotact",
        )
        assert result.success is True
        assert result.output == "test output"
        assert result.exit_code == 0
        assert result.host == "biotact"
        assert result.truncated is False

    def test_failed_result(self) -> None:
        """Failed result should include error."""
        result = SSHResult(
            success=False,
            output="",
            error="Connection refused",
            exit_code=-1,
            host="biotact",
        )
        assert result.success is False
        assert result.error == "Connection refused"

    def test_truncated_result(self) -> None:
        """Truncated result should have truncation info."""
        result = SSHResult(
            success=True,
            output="truncated output",
            error="",
            exit_code=0,
            host="biotact",
            truncated=True,
            truncated_info="Показано 150 из 1000 строк",
        )
        assert result.truncated is True
        assert result.truncated_info is not None


class TestHostConfig:
    """Tests for HostConfig dataclass."""

    def test_host_config_creation(self) -> None:
        """HostConfig should be created with correct attributes."""
        config = HostConfig(
            alias="biotact",
            level=PermissionLevel.ADMIN,
            description="Test server",
        )
        assert config.alias == "biotact"
        assert config.level == PermissionLevel.ADMIN
        assert config.description == "Test server"


class TestPermissionLevel:
    """Tests for PermissionLevel enum."""

    def test_permission_levels_exist(self) -> None:
        """All permission levels should exist."""
        assert PermissionLevel.READONLY.value == "readonly"
        assert PermissionLevel.OPERATOR.value == "operator"
        assert PermissionLevel.ADMIN.value == "admin"


class TestSSHSettings:
    """Tests for SSHSettings dataclass."""

    def test_default_settings(self) -> None:
        """Default settings should have correct values."""
        settings = SSHSettings()
        assert settings.default_host == "biotact"
        assert settings.connection_timeout == 10
        assert settings.command_timeout == 60
        assert settings.max_output_lines == 150
        assert settings.max_output_bytes == 65536


class TestSSHManager:
    """Tests for SSHManager."""

    @pytest.fixture
    def permissions_file(self, tmp_path: Path) -> Path:
        """Create temporary permissions file."""
        permissions = {
            "hosts": {
                "biotact": {
                    "level": "admin",
                    "description": "BioTact server",
                },
                "prod-1": {
                    "level": "readonly",
                    "description": "Production 1",
                },
                "staging": {
                    "level": "operator",
                    "description": "Staging server",
                },
            },
            "default_host": "biotact",
            "connection_timeout": 10,
            "command_timeout": 60,
            "max_output_lines": 150,
            "max_output_bytes": 65536,
        }
        path = tmp_path / "ssh_permissions.json"
        path.write_text(json.dumps(permissions))
        return path

    @pytest.fixture
    def security_guard(self, tmp_path: Path) -> SecurityGuard:
        """Create security guard for tests."""
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
            allowed_user_ids=[123],
            allowlist_path=allowlist_path,
            audit_log_path=tmp_path / "audit.log",
        )

    @pytest.fixture
    async def ssh_manager(
        self, permissions_file: Path, security_guard: SecurityGuard
    ) -> SSHManager:
        """Create and initialize SSH manager."""
        manager = SSHManager(
            permissions_path=permissions_file,
            security=security_guard,
        )
        await manager.initialize()
        return manager

    @pytest.mark.asyncio
    async def test_initialization(
        self, permissions_file: Path, security_guard: SecurityGuard
    ) -> None:
        """SSH manager should initialize from permissions file."""
        manager = SSHManager(
            permissions_path=permissions_file,
            security=security_guard,
        )
        await manager.initialize()

        assert len(manager.settings.hosts) == 3
        assert "biotact" in manager.settings.hosts
        assert manager.settings.default_host == "biotact"

    @pytest.mark.asyncio
    async def test_initialization_file_not_found(
        self, tmp_path: Path, security_guard: SecurityGuard
    ) -> None:
        """SSH manager should raise error if permissions file not found."""
        manager = SSHManager(
            permissions_path=tmp_path / "nonexistent.json",
            security=security_guard,
        )
        with pytest.raises(FileNotFoundError):
            await manager.initialize()

    @pytest.mark.asyncio
    async def test_list_hosts(self, ssh_manager: SSHManager) -> None:
        """list_hosts should return all configured hosts."""
        hosts = ssh_manager.list_hosts()
        assert len(hosts) == 3
        aliases = [h.alias for h in hosts]
        assert "biotact" in aliases
        assert "prod-1" in aliases
        assert "staging" in aliases

    @pytest.mark.asyncio
    async def test_get_host_config(self, ssh_manager: SSHManager) -> None:
        """get_host_config should return config for known host."""
        config = ssh_manager.get_host_config("biotact")
        assert config is not None
        assert config.alias == "biotact"
        assert config.level == PermissionLevel.ADMIN

    @pytest.mark.asyncio
    async def test_get_host_config_unknown(self, ssh_manager: SSHManager) -> None:
        """get_host_config should return None for unknown host."""
        config = ssh_manager.get_host_config("unknown")
        assert config is None

    @pytest.mark.asyncio
    async def test_is_host_allowed(self, ssh_manager: SSHManager) -> None:
        """is_host_allowed should return correct values."""
        assert ssh_manager.is_host_allowed("biotact") is True
        assert ssh_manager.is_host_allowed("unknown") is False

    @pytest.mark.asyncio
    async def test_format_hosts_list(self, ssh_manager: SSHManager) -> None:
        """format_hosts_list should return formatted string."""
        output = ssh_manager.format_hosts_list()
        assert "Доступные серверы:" in output
        assert "biotact" in output
        assert "(admin)" in output
        assert "prod-1" in output
        assert "(readonly)" in output

    @pytest.mark.asyncio
    async def test_is_command_allowed_for_level_admin(
        self, ssh_manager: SSHManager
    ) -> None:
        """Admin level should allow all commands."""
        assert ssh_manager.is_command_allowed_for_level(
            "any command", PermissionLevel.ADMIN
        )
        assert ssh_manager.is_command_allowed_for_level(
            "rm something", PermissionLevel.ADMIN
        )

    @pytest.mark.asyncio
    async def test_is_command_allowed_for_level_readonly(
        self, ssh_manager: SSHManager
    ) -> None:
        """Readonly level should only allow read commands."""
        # Allowed
        assert ssh_manager.is_command_allowed_for_level(
            "cat /etc/passwd", PermissionLevel.READONLY
        )
        assert ssh_manager.is_command_allowed_for_level(
            "ls -la", PermissionLevel.READONLY
        )
        assert ssh_manager.is_command_allowed_for_level(
            "docker ps", PermissionLevel.READONLY
        )
        assert ssh_manager.is_command_allowed_for_level(
            "systemctl status nginx", PermissionLevel.READONLY
        )
        # Not allowed
        assert not ssh_manager.is_command_allowed_for_level(
            "systemctl restart nginx", PermissionLevel.READONLY
        )
        assert not ssh_manager.is_command_allowed_for_level(
            "docker restart app", PermissionLevel.READONLY
        )

    @pytest.mark.asyncio
    async def test_is_command_allowed_for_level_operator(
        self, ssh_manager: SSHManager
    ) -> None:
        """Operator level should allow read + service management."""
        # Read commands
        assert ssh_manager.is_command_allowed_for_level(
            "cat /var/log/app.log", PermissionLevel.OPERATOR
        )
        # Service management
        assert ssh_manager.is_command_allowed_for_level(
            "systemctl restart nginx", PermissionLevel.OPERATOR
        )
        assert ssh_manager.is_command_allowed_for_level(
            "docker restart app", PermissionLevel.OPERATOR
        )
        assert ssh_manager.is_command_allowed_for_level(
            "docker compose up -d", PermissionLevel.OPERATOR
        )

    @pytest.mark.asyncio
    async def test_execute_unknown_host(self, ssh_manager: SSHManager) -> None:
        """execute should fail for unknown host."""
        result = await ssh_manager.execute(
            command="ls",
            host="unknown-server",
            user_id=123,
        )
        assert result.success is False
        assert "не найден" in result.error

    @pytest.mark.asyncio
    async def test_execute_permission_denied_for_level(
        self, ssh_manager: SSHManager
    ) -> None:
        """execute should fail if command not allowed for permission level."""
        result = await ssh_manager.execute(
            command="systemctl restart nginx",
            host="prod-1",  # readonly level
            user_id=123,
        )
        assert result.success is False
        assert "запрещена" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_dangerous_command_blocked(
        self, ssh_manager: SSHManager
    ) -> None:
        """execute should block dangerous commands."""
        result = await ssh_manager.execute(
            command="rm -rf /",
            host="biotact",
            user_id=123,
        )
        assert result.success is False
        assert "заблокирована" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_success(self, ssh_manager: SSHManager) -> None:
        """execute should succeed with mocked SSH connection."""
        mock_result = MagicMock()
        mock_result.stdout = "test output"
        mock_result.stderr = ""
        mock_result.exit_status = 0

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)

        with patch("src.ssh_manager.asyncssh.connect") as mock_connect:
            mock_connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_connect.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await ssh_manager.execute(
                command="ls -la",
                host="biotact",
                user_id=123,
            )

        assert result.success is True
        assert result.output == "test output"
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_execute_with_truncation(self, ssh_manager: SSHManager) -> None:
        """execute should truncate long output."""
        # Create output with more than max_output_lines
        long_output = "\n".join([f"line {i}" for i in range(200)])

        mock_result = MagicMock()
        mock_result.stdout = long_output
        mock_result.stderr = ""
        mock_result.exit_status = 0

        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)

        with patch("src.ssh_manager.asyncssh.connect") as mock_connect:
            mock_connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_connect.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await ssh_manager.execute(
                command="cat large_file",
                host="biotact",
                user_id=123,
            )

        assert result.success is True
        assert result.truncated is True
        assert result.truncated_info is not None
        assert "150" in result.truncated_info


class TestSSHManagerTruncation:
    """Tests for output truncation."""

    @pytest.fixture
    async def ssh_manager(self, tmp_path: Path) -> SSHManager:
        """Create SSH manager with low limits for testing."""
        permissions = {
            "hosts": {"test": {"level": "admin", "description": "Test"}},
            "default_host": "test",
            "max_output_lines": 10,
            "max_output_bytes": 100,
        }
        path = tmp_path / "ssh_permissions.json"
        path.write_text(json.dumps(permissions))

        allowlist_path = tmp_path / "allowlist.json"
        allowlist_path.write_text(json.dumps({"commands": {}, "blocked_patterns": []}))

        guard = SecurityGuard(
            allowed_user_ids=[123],
            allowlist_path=allowlist_path,
            audit_log_path=tmp_path / "audit.log",
        )

        manager = SSHManager(permissions_path=path, security=guard)
        await manager.initialize()
        return manager

    @pytest.mark.asyncio
    async def test_truncate_by_lines(self, ssh_manager: SSHManager) -> None:
        """Output should be truncated by line count."""
        output = "\n".join([f"line {i}" for i in range(20)])
        truncated, was_truncated, info = ssh_manager._truncate_output(output)

        assert was_truncated is True
        assert info is not None
        assert "10" in info
        assert truncated.count("\n") == 9  # 10 lines = 9 newlines

    @pytest.mark.asyncio
    async def test_truncate_by_bytes(self, ssh_manager: SSHManager) -> None:
        """Output should be truncated by byte count."""
        # Create output that exceeds byte limit but not line limit
        output = "x" * 200  # 200 bytes, single line
        truncated, was_truncated, info = ssh_manager._truncate_output(output)

        assert was_truncated is True
        assert info is not None
        assert len(truncated.encode()) <= 100

    @pytest.mark.asyncio
    async def test_no_truncation_needed(self, ssh_manager: SSHManager) -> None:
        """Short output should not be truncated."""
        output = "short output"
        truncated, was_truncated, info = ssh_manager._truncate_output(output)

        assert was_truncated is False
        assert info is None
        assert truncated == output
