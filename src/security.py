"""Security module for DevOps Agent.

Provides authorization, command validation, audit logging, and injection protection.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import settings

# Dangerous patterns that are always blocked
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    # Destructive commands
    (r"rm\s+-rf\s+/", "destructive rm -rf /"),
    (r"rm\s+-rf\s+\*", "destructive rm -rf *"),
    (r"rm\s+-rf\s+~", "delete home directory"),
    (r"mkfs\.", "filesystem formatting"),
    (r"dd\s+if=", "raw disk write"),
    (r">\s*/dev/sd", "direct disk write"),
    # Permissions
    (r"chmod\s+-R\s+777", "insecure permissions"),
    (r"chown\s+-R\s+root", "change ownership to root"),
    # Code injection
    (r"\|\s*sh\b", "pipe to shell"),
    (r"\|\s*bash\b", "pipe to bash"),
    (r"curl.*\|\s*bash", "curl pipe to bash"),
    (r"wget.*\|\s*sh", "wget pipe to shell"),
    (r"\$\(", "command substitution $(...)"),
    (r"`[^`]+`", "command substitution `...`"),
    # Privilege escalation
    (r"sudo\s+su\b", "sudo su"),
    (r"\bpasswd\b", "password change"),
    (r"\bvisudo\b", "sudoers editing"),
    # System config
    (r">(>)?\s*/etc/", "overwrite system config"),
    # System destruction
    (r":\s*\(\s*\)\s*\{", "fork bomb pattern"),
    (r"\bshutdown\b", "system shutdown"),
    (r"\breboot\b", "system reboot"),
    (r"\binit\s+0\b", "system halt"),
    # Interactive commands (will hang)
    (r"\bvim?\s", "interactive editor vim"),
    (r"\bnano\s", "interactive editor nano"),
    (r"\bless\s", "interactive pager less"),
    (r"\bmore\s", "interactive pager more"),
    (r"\bmysql\s*$", "interactive mysql shell"),
    (r"\bpsql\s*$", "interactive psql shell"),
    (r"\bmongo\s*$", "interactive mongo shell"),
]

# Characters to remove during sanitization
DANGEROUS_CHARS = [
    ";",
    "`",
    "$",
    "&",
    "|",
    "(",
    ")",
    "{",
    "}",
    "[",
    "]",
    "!",
    "\n",
    "\r",
]


@dataclass(slots=True)
class AuditEntry:
    """Single audit log entry."""

    timestamp: str
    user_id: int
    action: str
    details: str
    allowed: bool
    warnings: list[str] = field(default_factory=list)


class SecurityGuard:
    """Security guard for command validation and user authorization.

    Provides multiple layers of security:
    - User allowlist checking
    - Command allowlist validation
    - Dangerous pattern detection
    - Input sanitization
    - Audit logging

    Args:
        allowed_user_ids: List of authorized Telegram user IDs.
        allowlist_path: Path to allowlist.json configuration.
        audit_log_path: Path to audit log file.
    """

    def __init__(
        self,
        allowed_user_ids: list[int] | None = None,
        allowlist_path: Path | None = None,
        audit_log_path: Path | None = None,
    ) -> None:
        """Initialize SecurityGuard.

        Args:
            allowed_user_ids: Authorized user IDs. Defaults to settings.
            allowlist_path: Path to allowlist.json. Defaults to config/allowlist.json.
            audit_log_path: Path to audit log. Defaults to logs/audit.log.
        """
        self._allowed_users = set(allowed_user_ids or settings.allowed_user_ids)
        self._allowlist_path = allowlist_path or (
            settings.base_dir / "config" / "allowlist.json"
        )
        self._audit_log_path = audit_log_path or (settings.logs_dir / "audit.log")
        self._allowlist: dict[str, Any] = {}
        self._logger = logging.getLogger(__name__)
        self._load_allowlist()

    def _load_allowlist(self) -> None:
        """Load allowlist from JSON file."""
        if self._allowlist_path.exists():
            with self._allowlist_path.open() as f:
                self._allowlist = json.load(f)
        else:
            self._logger.warning(f"Allowlist not found: {self._allowlist_path}")
            self._allowlist = {"commands": {}, "blocked_patterns": []}

    def reload_allowlist(self) -> None:
        """Reload allowlist from file."""
        self._load_allowlist()

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if user is authorized.

        Args:
            user_id: Telegram user ID to check.

        Returns:
            True if user is in allowlist, False otherwise.
        """
        return user_id in self._allowed_users

    def is_command_allowed(self, command: str) -> bool:
        """Check if command is allowed by allowlist.

        First checks for dangerous patterns, then validates against allowlist.

        Args:
            command: Shell command to validate.

        Returns:
            True if command is safe and allowed, False otherwise.
        """
        # First check dangerous patterns
        if self.check_dangerous_patterns(command):
            return False

        # Get all allowed command prefixes
        allowed_commands: list[str] = []
        for category in self._allowlist.get("commands", {}).values():
            allowed_commands.extend(category)

        # Check if command starts with any allowed prefix
        command_stripped = command.strip()
        return any(command_stripped.startswith(allowed) for allowed in allowed_commands)

    def check_dangerous_patterns(self, command: str) -> list[str]:
        """Check command for dangerous patterns.

        Args:
            command: Command to check.

        Returns:
            List of warning messages for detected patterns.
        """
        warnings: list[str] = []
        command_lower = command.lower()

        # Check compiled dangerous patterns
        for pattern, description in DANGEROUS_PATTERNS:
            if re.search(pattern, command_lower, re.IGNORECASE):
                warnings.append(f"Dangerous pattern detected: {description}")

        # Check blocked patterns from allowlist
        for blocked in self._allowlist.get("blocked_patterns", []):
            if blocked.lower() in command_lower:
                warnings.append(f"Blocked pattern: {blocked}")

        return warnings

    def sanitize_input(self, text: str) -> str:
        """Sanitize user input by removing dangerous characters.

        Args:
            text: Input text to sanitize.

        Returns:
            Sanitized text with dangerous characters removed.
        """
        result = text
        for char in DANGEROUS_CHARS:
            result = result.replace(char, "")

        # Remove multiple spaces
        result = re.sub(r"\s+", " ", result)

        return result.strip()

    def audit_log(
        self,
        user_id: int,
        action: str,
        details: str,
        allowed: bool = True,
        warnings: list[str] | None = None,
    ) -> None:
        """Write entry to audit log.

        Args:
            user_id: User performing the action.
            action: Type of action (e.g., "command", "login").
            details: Action details.
            allowed: Whether action was allowed.
            warnings: Any security warnings.
        """
        entry = AuditEntry(
            timestamp=datetime.now(UTC).isoformat(),
            user_id=user_id,
            action=action,
            details=details,
            allowed=allowed,
            warnings=warnings or [],
        )

        # Ensure logs directory exists
        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        # Append to audit log
        log_line = json.dumps(
            {
                "timestamp": entry.timestamp,
                "user_id": entry.user_id,
                "action": entry.action,
                "details": entry.details,
                "allowed": entry.allowed,
                "warnings": entry.warnings,
            }
        )

        with self._audit_log_path.open("a") as f:
            f.write(log_line + "\n")

        # Also log to standard logger
        log_msg = f"[AUDIT] user={user_id} action={action} allowed={allowed}"
        if allowed:
            self._logger.info(log_msg)
        else:
            self._logger.warning(f"{log_msg} warnings={warnings}")

    def validate_command(
        self,
        user_id: int,
        command: str,
        *,
        skip_allowlist: bool = False,
    ) -> tuple[bool, list[str]]:
        """Validate command comprehensively.

        Performs full security check: user authorization, dangerous patterns,
        and optionally allowlist validation.

        Args:
            user_id: User requesting command execution.
            command: Command to validate.
            skip_allowlist: If True, skip allowlist check (for SSH per-level validation).

        Returns:
            Tuple of (is_allowed, list_of_warnings).
        """
        warnings: list[str] = []

        # Check user authorization
        if not self.is_user_allowed(user_id):
            warnings.append("User not authorized")
            self.audit_log(
                user_id, "command", command, allowed=False, warnings=warnings
            )
            return False, warnings

        # Check dangerous patterns
        pattern_warnings = self.check_dangerous_patterns(command)
        if pattern_warnings:
            warnings.extend(pattern_warnings)
            self.audit_log(
                user_id, "command", command, allowed=False, warnings=warnings
            )
            return False, warnings

        # Check allowlist (skip for SSH - uses per-level validation instead)
        if not skip_allowlist and not self.is_command_allowed(command):
            warnings.append("Command not in allowlist")
            self.audit_log(
                user_id, "command", command, allowed=False, warnings=warnings
            )
            return False, warnings

        # Command is allowed
        self.audit_log(user_id, "command", command, allowed=True)
        return True, []

    def get_allowed_commands(self) -> dict[str, list[str]]:
        """Get all allowed commands grouped by category.

        Returns:
            Dictionary of category -> list of allowed command prefixes.
        """
        return dict(self._allowlist.get("commands", {}))
