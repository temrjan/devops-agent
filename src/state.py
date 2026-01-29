"""State management for DevOps Agent.

Provides persistent storage for sessions, incidents, and conversation context
using SQLite with async support via aiosqlite.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from src.config import settings


@dataclass(slots=True)
class Session:
    """User session data.

    Attributes:
        id: Unique session identifier.
        user_id: Telegram user ID.
        started_at: Session start timestamp.
        last_activity: Last activity timestamp.
        status: Session status (active, closed).
        context: Additional session context.
    """

    id: str
    user_id: int
    started_at: datetime
    last_activity: datetime
    status: str = "active"
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Message:
    """Conversation message.

    Attributes:
        id: Message ID.
        session_id: Parent session ID.
        role: Message role (user, assistant, system).
        content: Message content.
        timestamp: Message timestamp.
        metadata: Additional message metadata.
    """

    id: int
    session_id: str
    role: str
    content: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Incident:
    """Recorded incident.

    Attributes:
        id: Incident ID.
        user_id: User who triggered the incident.
        timestamp: When incident occurred.
        query: Original user query.
        resolution: How it was resolved.
        tools_used: List of tools used.
        success: Whether resolution was successful.
        duration_seconds: Time taken to resolve.
    """

    id: int
    user_id: int
    timestamp: datetime
    query: str
    resolution: str | None = None
    tools_used: list[str] = field(default_factory=list)
    success: bool = False
    duration_seconds: float | None = None


# SQL schema for database initialization
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    last_activity TEXT NOT NULL,
    context TEXT DEFAULT '{}',
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    query TEXT NOT NULL,
    resolution TEXT,
    tools_used TEXT DEFAULT '[]',
    success INTEGER DEFAULT 0,
    duration_seconds REAL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    model TEXT DEFAULT 'sonnet',
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_incidents_user_id ON incidents(user_id);
CREATE INDEX IF NOT EXISTS idx_incidents_timestamp ON incidents(timestamp);
"""


class StateManager:
    """Manager for persistent application state.

    Provides async methods for managing sessions, messages, and incidents
    with SQLite backend.

    Args:
        db_path: Path to SQLite database file.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize StateManager.

        Args:
            db_path: Path to database. Defaults to settings.data_dir/agent.db.
        """
        self._db_path = db_path or (settings.data_dir / "agent.db")
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize database and create tables if needed."""
        # Ensure data directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

        self._initialized = True

    async def _ensure_initialized(self) -> None:
        """Ensure database is initialized before operations."""
        if not self._initialized:
            await self.initialize()

    # ==================== Session Management ====================

    async def create_session(self, user_id: int) -> Session:
        """Create a new session for user.

        Args:
            user_id: Telegram user ID.

        Returns:
            Created Session object.
        """
        await self._ensure_initialized()

        session_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions
                (id, user_id, started_at, last_activity, context, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, user_id, now.isoformat(), now.isoformat(), "{}", "active"),
            )
            await db.commit()

        return Session(
            id=session_id,
            user_id=user_id,
            started_at=now,
            last_activity=now,
            status="active",
            context={},
        )

    async def get_session(self, session_id: str) -> Session | None:
        """Get session by ID.

        Args:
            session_id: Session identifier.

        Returns:
            Session object or None if not found.
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM sessions WHERE id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        return Session(
            id=row["id"],
            user_id=row["user_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            last_activity=datetime.fromisoformat(row["last_activity"]),
            status=row["status"],
            context=json.loads(row["context"]),
        )

    async def get_active_session(self, user_id: int) -> Session | None:
        """Get active session for user.

        Args:
            user_id: Telegram user ID.

        Returns:
            Active session or None if no active session exists.
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = ? AND status = 'active'
                ORDER BY last_activity DESC
                LIMIT 1
                """,
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        return Session(
            id=row["id"],
            user_id=row["user_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            last_activity=datetime.fromisoformat(row["last_activity"]),
            status=row["status"],
            context=json.loads(row["context"]),
        )

    async def update_session_activity(self, session_id: str) -> None:
        """Update session last activity timestamp.

        Args:
            session_id: Session identifier.
        """
        await self._ensure_initialized()

        now = datetime.now(UTC)
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE sessions SET last_activity = ? WHERE id = ?",
                (now.isoformat(), session_id),
            )
            await db.commit()

    async def update_session_context(
        self, session_id: str, context: dict[str, Any]
    ) -> None:
        """Update session context.

        Args:
            session_id: Session identifier.
            context: New context dictionary.
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE sessions SET context = ? WHERE id = ?",
                (json.dumps(context), session_id),
            )
            await db.commit()

    async def close_session(self, session_id: str) -> None:
        """Close a session.

        Args:
            session_id: Session identifier.
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "UPDATE sessions SET status = 'closed' WHERE id = ?",
                (session_id,),
            )
            await db.commit()

    # ==================== Message Management ====================

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        """Add message to session.

        Args:
            session_id: Parent session ID.
            role: Message role (user, assistant, system).
            content: Message content.
            metadata: Additional metadata.

        Returns:
            Created Message object.
        """
        await self._ensure_initialized()

        now = datetime.now(UTC)
        metadata = metadata or {}

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO messages (session_id, role, content, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, now.isoformat(), json.dumps(metadata)),
            )
            message_id = cursor.lastrowid
            await db.commit()

        # Update session activity
        await self.update_session_activity(session_id)

        return Message(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            timestamp=now,
            metadata=metadata,
        )

    async def get_messages(
        self,
        session_id: str,
        limit: int | None = None,
    ) -> list[Message]:
        """Get messages for session.

        Args:
            session_id: Session identifier.
            limit: Maximum number of messages to return.

        Returns:
            List of Message objects ordered by timestamp.
        """
        await self._ensure_initialized()

        query = """
            SELECT * FROM messages
            WHERE session_id = ?
            ORDER BY timestamp ASC
        """
        params: list[Any] = [session_id]

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()

        return [
            Message(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]

    async def get_message_count(self, session_id: str) -> int:
        """Get message count for session.

        Args:
            session_id: Session identifier.

        Returns:
            Number of messages in session.
        """
        await self._ensure_initialized()

        async with (
            aiosqlite.connect(self._db_path) as db,
            db.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (session_id,),
            ) as cursor,
        ):
            row = await cursor.fetchone()

        return row[0] if row else 0

    async def compact_context(
        self,
        session_id: str,
        max_messages: int = 20,
        keep_system: bool = True,
    ) -> int:
        """Compact session context by removing old messages.

        Keeps the most recent messages and optionally all system messages.

        Args:
            session_id: Session identifier.
            max_messages: Maximum messages to keep.
            keep_system: Whether to keep all system messages.

        Returns:
            Number of messages deleted.
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as db:
            # Get current message count
            async with db.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
                total_count = row[0] if row else 0

            if total_count <= max_messages:
                return 0

            # Calculate how many to delete
            to_delete = total_count - max_messages

            if keep_system:
                # Delete oldest non-system messages
                await db.execute(
                    """
                    DELETE FROM messages
                    WHERE id IN (
                        SELECT id FROM messages
                        WHERE session_id = ? AND role != 'system'
                        ORDER BY timestamp ASC
                        LIMIT ?
                    )
                    """,
                    (session_id, to_delete),
                )
            else:
                # Delete oldest messages regardless of role
                await db.execute(
                    """
                    DELETE FROM messages
                    WHERE id IN (
                        SELECT id FROM messages
                        WHERE session_id = ?
                        ORDER BY timestamp ASC
                        LIMIT ?
                    )
                    """,
                    (session_id, to_delete),
                )

            await db.commit()

            # Get actual deleted count
            async with db.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                row = await cursor.fetchone()
                new_count = row[0] if row else 0

        return total_count - new_count

    # ==================== Incident Management ====================

    async def save_incident(
        self,
        user_id: int,
        query: str,
        resolution: str | None = None,
        tools_used: list[str] | None = None,
        success: bool = False,
        duration_seconds: float | None = None,
    ) -> Incident:
        """Save an incident record.

        Args:
            user_id: User who triggered the incident.
            query: Original user query.
            resolution: How it was resolved.
            tools_used: List of tools used.
            success: Whether resolution was successful.
            duration_seconds: Time taken to resolve.

        Returns:
            Created Incident object.
        """
        await self._ensure_initialized()

        now = datetime.now(UTC)
        tools_used = tools_used or []

        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO incidents
                (user_id, timestamp, query, resolution,
                 tools_used, success, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    now.isoformat(),
                    query,
                    resolution,
                    json.dumps(tools_used),
                    1 if success else 0,
                    duration_seconds,
                ),
            )
            incident_id = cursor.lastrowid
            await db.commit()

        return Incident(
            id=incident_id,
            user_id=user_id,
            timestamp=now,
            query=query,
            resolution=resolution,
            tools_used=tools_used,
            success=success,
            duration_seconds=duration_seconds,
        )

    async def get_recent_incidents(
        self,
        user_id: int | None = None,
        limit: int = 10,
    ) -> list[Incident]:
        """Get recent incidents.

        Args:
            user_id: Filter by user ID (optional).
            limit: Maximum incidents to return.

        Returns:
            List of Incident objects ordered by timestamp descending.
        """
        await self._ensure_initialized()

        if user_id is not None:
            query = """
                SELECT * FROM incidents
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params: tuple[Any, ...] = (user_id, limit)
        else:
            query = """
                SELECT * FROM incidents
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = (limit,)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()

        return [
            Incident(
                id=row["id"],
                user_id=row["user_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                query=row["query"],
                resolution=row["resolution"],
                tools_used=json.loads(row["tools_used"]),
                success=bool(row["success"]),
                duration_seconds=row["duration_seconds"],
            )
            for row in rows
        ]

    async def get_similar_incidents(
        self,
        query: str,
        user_id: int | None = None,
        limit: int = 5,
    ) -> list[Incident]:
        """Get incidents with similar queries.

        Uses simple keyword matching for similarity.

        Args:
            query: Query to match against.
            user_id: Filter by user ID (optional).
            limit: Maximum incidents to return.

        Returns:
            List of similar Incident objects.
        """
        await self._ensure_initialized()

        # Extract keywords (simple approach)
        keywords = [w.lower() for w in query.split() if len(w) > 2]

        if not keywords:
            return []

        # Build LIKE conditions for each keyword
        like_conditions = " OR ".join(["query LIKE ?" for _ in keywords])
        params: list[Any] = [f"%{kw}%" for kw in keywords]

        sql = f"""
            SELECT * FROM incidents
            WHERE ({like_conditions})
        """

        if user_id is not None:
            sql += " AND user_id = ?"
            params.append(user_id)

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cursor:
                rows = await cursor.fetchall()

        return [
            Incident(
                id=row["id"],
                user_id=row["user_id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                query=row["query"],
                resolution=row["resolution"],
                tools_used=json.loads(row["tools_used"]),
                success=bool(row["success"]),
                duration_seconds=row["duration_seconds"],
            )
            for row in rows
        ]

    async def get_incident_stats(self, user_id: int | None = None) -> dict[str, Any]:
        """Get incident statistics.

        Args:
            user_id: Filter by user ID (optional).

        Returns:
            Dictionary with statistics.
        """
        await self._ensure_initialized()

        if user_id is not None:
            where_clause = "WHERE user_id = ?"
            params: tuple[Any, ...] = (user_id,)
        else:
            where_clause = ""
            params = ()

        async with aiosqlite.connect(self._db_path) as db:
            # Total incidents
            async with db.execute(
                f"SELECT COUNT(*) FROM incidents {where_clause}",
                params,
            ) as cursor:
                row = await cursor.fetchone()
                total = row[0] if row else 0

            # Successful incidents
            success_where = (
                "WHERE success = 1 AND user_id = ?" if user_id else "WHERE success = 1"
            )
            async with db.execute(
                f"SELECT COUNT(*) FROM incidents {success_where}",
                params if user_id else (),
            ) as cursor:
                row = await cursor.fetchone()
                successful = row[0] if row else 0

            # Average duration
            async with db.execute(
                f"""
                SELECT AVG(duration_seconds) FROM incidents
                {where_clause}
                """,
                params,
            ) as cursor:
                row = await cursor.fetchone()
                avg_duration = row[0] if row and row[0] else 0

        return {
            "total_incidents": total,
            "successful_incidents": successful,
            "success_rate": successful / total if total > 0 else 0,
            "average_duration_seconds": avg_duration,
        }

    # ==================== User Settings ====================

    async def get_user_model(self, user_id: int) -> str:
        """Get user's preferred model.

        Args:
            user_id: Telegram user ID.

        Returns:
            Model key (sonnet, opus, haiku). Defaults to 'sonnet'.
        """
        await self._ensure_initialized()

        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT model FROM user_settings WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()

        return row[0] if row else "sonnet"

    async def set_user_model(self, user_id: int, model: str) -> None:
        """Set user's preferred model.

        Args:
            user_id: Telegram user ID.
            model: Model key (sonnet, opus, haiku).
        """
        await self._ensure_initialized()

        now = datetime.now(UTC)

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO user_settings (user_id, model, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    model = excluded.model,
                    updated_at = excluded.updated_at
                """,
                (user_id, model, now.isoformat()),
            )
            await db.commit()

    # ==================== Cleanup ====================

    async def cleanup_old_sessions(self, days: int = 7) -> int:
        """Clean up old closed sessions.

        Args:
            days: Delete sessions older than this many days.

        Returns:
            Number of sessions deleted.
        """
        await self._ensure_initialized()

        cutoff = datetime.now(UTC)
        # Calculate cutoff by subtracting days worth of seconds
        from datetime import timedelta

        cutoff = cutoff - timedelta(days=days)

        async with aiosqlite.connect(self._db_path) as db:
            # Get count before deletion
            async with db.execute(
                """
                SELECT COUNT(*) FROM sessions
                WHERE status = 'closed' AND last_activity < ?
                """,
                (cutoff.isoformat(),),
            ) as cursor:
                row = await cursor.fetchone()
                count = row[0] if row else 0

            # Delete old messages first (foreign key)
            await db.execute(
                """
                DELETE FROM messages WHERE session_id IN (
                    SELECT id FROM sessions
                    WHERE status = 'closed' AND last_activity < ?
                )
                """,
                (cutoff.isoformat(),),
            )

            # Delete old sessions
            await db.execute(
                """
                DELETE FROM sessions
                WHERE status = 'closed' AND last_activity < ?
                """,
                (cutoff.isoformat(),),
            )
            await db.commit()

        return count

    async def close(self) -> None:
        """Close any resources (placeholder for future use)."""
        # aiosqlite manages connections per-operation, nothing to close
        pass
