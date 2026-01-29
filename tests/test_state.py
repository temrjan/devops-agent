"""Tests for state management module."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.state import Incident, Message, Session, StateManager


class TestDataModels:
    """Tests for data model classes."""

    def test_session_creation(self) -> None:
        """Session should be created with correct attributes."""
        now = datetime.now(UTC)
        session = Session(
            id="test-id",
            user_id=123,
            started_at=now,
            last_activity=now,
            status="active",
            context={"key": "value"},
        )
        assert session.id == "test-id"
        assert session.user_id == 123
        assert session.status == "active"
        assert session.context["key"] == "value"

    def test_message_creation(self) -> None:
        """Message should be created with correct attributes."""
        now = datetime.now(UTC)
        message = Message(
            id=1,
            session_id="test-session",
            role="user",
            content="Hello",
            timestamp=now,
            metadata={"tool": "test"},
        )
        assert message.id == 1
        assert message.role == "user"
        assert message.content == "Hello"

    def test_incident_creation(self) -> None:
        """Incident should be created with correct attributes."""
        now = datetime.now(UTC)
        incident = Incident(
            id=1,
            user_id=123,
            timestamp=now,
            query="nginx down",
            resolution="restarted",
            tools_used=["check_service", "restart_service"],
            success=True,
            duration_seconds=5.5,
        )
        assert incident.id == 1
        assert incident.query == "nginx down"
        assert incident.success is True
        assert "check_service" in incident.tools_used


class TestStateManager:
    """Tests for StateManager class."""

    @pytest.fixture
    async def state(self, tmp_path: Path) -> StateManager:
        """Create StateManager with temporary database."""
        db_path = tmp_path / "test.db"
        manager = StateManager(db_path=db_path)
        await manager.initialize()
        return manager


class TestSessionManagement(TestStateManager):
    """Tests for session management."""

    @pytest.mark.asyncio
    async def test_creates_session(self, state: StateManager) -> None:
        """Should create session with unique ID."""
        session = await state.create_session(user_id=123)
        assert session.id
        assert session.user_id == 123
        assert session.status == "active"

    @pytest.mark.asyncio
    async def test_get_session(self, state: StateManager) -> None:
        """Should retrieve session by ID."""
        created = await state.create_session(user_id=123)
        retrieved = await state.get_session(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.user_id == 123

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, state: StateManager) -> None:
        """Should return None for nonexistent session."""
        session = await state.get_session("nonexistent-id")
        assert session is None

    @pytest.mark.asyncio
    async def test_get_active_session(self, state: StateManager) -> None:
        """Should get active session for user."""
        await state.create_session(user_id=123)
        active = await state.get_active_session(user_id=123)

        assert active is not None
        assert active.user_id == 123
        assert active.status == "active"

    @pytest.mark.asyncio
    async def test_get_active_session_returns_most_recent(
        self, state: StateManager
    ) -> None:
        """Should return most recent active session."""
        await state.create_session(user_id=123)
        session2 = await state.create_session(user_id=123)

        active = await state.get_active_session(user_id=123)
        assert active is not None
        # Both are active, but session2 should be returned (most recent)
        assert active.id == session2.id

    @pytest.mark.asyncio
    async def test_update_session_activity(self, state: StateManager) -> None:
        """Should update session last activity."""
        session = await state.create_session(user_id=123)
        original_activity = session.last_activity

        await state.update_session_activity(session.id)
        updated = await state.get_session(session.id)

        assert updated is not None
        assert updated.last_activity >= original_activity

    @pytest.mark.asyncio
    async def test_update_session_context(self, state: StateManager) -> None:
        """Should update session context."""
        session = await state.create_session(user_id=123)
        await state.update_session_context(session.id, {"new_key": "new_value"})

        updated = await state.get_session(session.id)
        assert updated is not None
        assert updated.context["new_key"] == "new_value"

    @pytest.mark.asyncio
    async def test_close_session(self, state: StateManager) -> None:
        """Should close session."""
        session = await state.create_session(user_id=123)
        await state.close_session(session.id)

        closed = await state.get_session(session.id)
        assert closed is not None
        assert closed.status == "closed"

    @pytest.mark.asyncio
    async def test_closed_session_not_active(self, state: StateManager) -> None:
        """Closed session should not be returned as active."""
        session = await state.create_session(user_id=123)
        await state.close_session(session.id)

        active = await state.get_active_session(user_id=123)
        assert active is None


class TestMessageManagement(TestStateManager):
    """Tests for message management."""

    @pytest.mark.asyncio
    async def test_add_message(self, state: StateManager) -> None:
        """Should add message to session."""
        session = await state.create_session(user_id=123)
        message = await state.add_message(
            session_id=session.id,
            role="user",
            content="Hello",
        )

        assert message.id
        assert message.role == "user"
        assert message.content == "Hello"

    @pytest.mark.asyncio
    async def test_add_message_with_metadata(self, state: StateManager) -> None:
        """Should add message with metadata."""
        session = await state.create_session(user_id=123)
        message = await state.add_message(
            session_id=session.id,
            role="assistant",
            content="Response",
            metadata={"tool_used": "check_service"},
        )

        assert message.metadata["tool_used"] == "check_service"

    @pytest.mark.asyncio
    async def test_get_messages(self, state: StateManager) -> None:
        """Should get all messages for session."""
        session = await state.create_session(user_id=123)
        await state.add_message(session.id, "user", "Message 1")
        await state.add_message(session.id, "assistant", "Message 2")
        await state.add_message(session.id, "user", "Message 3")

        messages = await state.get_messages(session.id)
        assert len(messages) == 3
        assert messages[0].content == "Message 1"
        assert messages[2].content == "Message 3"

    @pytest.mark.asyncio
    async def test_get_messages_with_limit(self, state: StateManager) -> None:
        """Should respect limit parameter."""
        session = await state.create_session(user_id=123)
        for i in range(10):
            await state.add_message(session.id, "user", f"Message {i}")

        messages = await state.get_messages(session.id, limit=5)
        assert len(messages) == 5

    @pytest.mark.asyncio
    async def test_get_message_count(self, state: StateManager) -> None:
        """Should return correct message count."""
        session = await state.create_session(user_id=123)
        for i in range(5):
            await state.add_message(session.id, "user", f"Message {i}")

        count = await state.get_message_count(session.id)
        assert count == 5

    @pytest.mark.asyncio
    async def test_add_message_updates_session_activity(
        self, state: StateManager
    ) -> None:
        """Adding message should update session activity."""
        session = await state.create_session(user_id=123)
        original = session.last_activity

        await state.add_message(session.id, "user", "Hello")
        updated = await state.get_session(session.id)

        assert updated is not None
        assert updated.last_activity >= original


class TestContextCompaction(TestStateManager):
    """Tests for context compaction."""

    @pytest.mark.asyncio
    async def test_compact_removes_old_messages(self, state: StateManager) -> None:
        """Should remove old messages beyond limit."""
        session = await state.create_session(user_id=123)

        # Add 100 messages
        for i in range(100):
            await state.add_message(session.id, "user", f"msg {i}")

        # Compact to 20
        deleted = await state.compact_context(session.id, max_messages=20)

        assert deleted == 80
        messages = await state.get_messages(session.id)
        assert len(messages) == 20

    @pytest.mark.asyncio
    async def test_compact_keeps_recent_messages(self, state: StateManager) -> None:
        """Should keep most recent messages."""
        session = await state.create_session(user_id=123)

        for i in range(50):
            await state.add_message(session.id, "user", f"msg {i}")

        await state.compact_context(session.id, max_messages=10)
        messages = await state.get_messages(session.id)

        # Should have last 10 messages (msg 40 through msg 49)
        assert len(messages) == 10
        assert messages[-1].content == "msg 49"

    @pytest.mark.asyncio
    async def test_compact_preserves_system_messages(self, state: StateManager) -> None:
        """Should preserve system messages when keep_system=True."""
        session = await state.create_session(user_id=123)

        # Add system message first
        await state.add_message(session.id, "system", "System prompt")

        # Add many user messages
        for i in range(30):
            await state.add_message(session.id, "user", f"msg {i}")

        await state.compact_context(session.id, max_messages=10, keep_system=True)
        messages = await state.get_messages(session.id)

        # Should still have system message
        system_msgs = [m for m in messages if m.role == "system"]
        assert len(system_msgs) >= 1

    @pytest.mark.asyncio
    async def test_compact_no_op_when_under_limit(self, state: StateManager) -> None:
        """Should not delete anything when under limit."""
        session = await state.create_session(user_id=123)

        for i in range(5):
            await state.add_message(session.id, "user", f"msg {i}")

        deleted = await state.compact_context(session.id, max_messages=20)

        assert deleted == 0
        messages = await state.get_messages(session.id)
        assert len(messages) == 5


class TestIncidentManagement(TestStateManager):
    """Tests for incident management."""

    @pytest.mark.asyncio
    async def test_saves_incident(self, state: StateManager) -> None:
        """Should save incident."""
        incident = await state.save_incident(
            user_id=123,
            query="nginx down",
            resolution="restarted",
            success=True,
        )

        assert incident.id
        assert incident.query == "nginx down"
        assert incident.success is True

    @pytest.mark.asyncio
    async def test_save_incident_with_tools(self, state: StateManager) -> None:
        """Should save incident with tools used."""
        incident = await state.save_incident(
            user_id=123,
            query="check nginx",
            tools_used=["check_service", "read_logs"],
            success=True,
        )

        assert "check_service" in incident.tools_used
        assert "read_logs" in incident.tools_used

    @pytest.mark.asyncio
    async def test_save_incident_with_duration(self, state: StateManager) -> None:
        """Should save incident with duration."""
        incident = await state.save_incident(
            user_id=123,
            query="fix nginx",
            duration_seconds=15.5,
            success=True,
        )

        assert incident.duration_seconds == 15.5

    @pytest.mark.asyncio
    async def test_get_recent_incidents(self, state: StateManager) -> None:
        """Should get recent incidents."""
        for i in range(5):
            await state.save_incident(user_id=123, query=f"query {i}")

        incidents = await state.get_recent_incidents(user_id=123)
        assert len(incidents) == 5

    @pytest.mark.asyncio
    async def test_get_recent_incidents_respects_limit(
        self, state: StateManager
    ) -> None:
        """Should respect limit parameter."""
        for i in range(10):
            await state.save_incident(user_id=123, query=f"query {i}")

        incidents = await state.get_recent_incidents(user_id=123, limit=3)
        assert len(incidents) == 3

    @pytest.mark.asyncio
    async def test_get_recent_incidents_ordered_by_timestamp(
        self, state: StateManager
    ) -> None:
        """Should return incidents ordered by timestamp descending."""
        await state.save_incident(user_id=123, query="first")
        await state.save_incident(user_id=123, query="second")
        await state.save_incident(user_id=123, query="third")

        incidents = await state.get_recent_incidents(user_id=123)

        # Most recent first
        assert incidents[0].query == "third"
        assert incidents[2].query == "first"

    @pytest.mark.asyncio
    async def test_get_recent_incidents_all_users(self, state: StateManager) -> None:
        """Should get incidents for all users when user_id is None."""
        await state.save_incident(user_id=123, query="user 1 query")
        await state.save_incident(user_id=456, query="user 2 query")

        incidents = await state.get_recent_incidents(user_id=None)
        assert len(incidents) == 2


class TestSimilarIncidents(TestStateManager):
    """Tests for similar incident search."""

    @pytest.mark.asyncio
    async def test_find_similar_incidents(self, state: StateManager) -> None:
        """Should find incidents with similar queries."""
        await state.save_incident(
            user_id=123,
            query="nginx is down",
            resolution="restarted nginx",
            success=True,
        )
        await state.save_incident(
            user_id=123,
            query="check disk space",
            resolution="cleaned up logs",
            success=True,
        )

        similar = await state.get_similar_incidents(query="nginx not responding")
        assert len(similar) >= 1
        assert any("nginx" in i.query for i in similar)

    @pytest.mark.asyncio
    async def test_similar_incidents_empty_keywords(self, state: StateManager) -> None:
        """Should handle queries with no usable keywords."""
        similar = await state.get_similar_incidents(query="a b")
        assert similar == []


class TestIncidentStats(TestStateManager):
    """Tests for incident statistics."""

    @pytest.mark.asyncio
    async def test_get_incident_stats(self, state: StateManager) -> None:
        """Should return correct statistics."""
        await state.save_incident(user_id=123, query="q1", success=True)
        await state.save_incident(user_id=123, query="q2", success=True)
        await state.save_incident(user_id=123, query="q3", success=False)

        stats = await state.get_incident_stats(user_id=123)

        assert stats["total_incidents"] == 3
        assert stats["successful_incidents"] == 2
        assert stats["success_rate"] == pytest.approx(2 / 3)

    @pytest.mark.asyncio
    async def test_get_incident_stats_with_duration(self, state: StateManager) -> None:
        """Should calculate average duration."""
        await state.save_incident(
            user_id=123, query="q1", success=True, duration_seconds=10.0
        )
        await state.save_incident(
            user_id=123, query="q2", success=True, duration_seconds=20.0
        )

        stats = await state.get_incident_stats(user_id=123)

        assert stats["average_duration_seconds"] == pytest.approx(15.0)

    @pytest.mark.asyncio
    async def test_get_incident_stats_empty(self, state: StateManager) -> None:
        """Should handle no incidents gracefully."""
        stats = await state.get_incident_stats(user_id=999)

        assert stats["total_incidents"] == 0
        assert stats["success_rate"] == 0


class TestCleanup(TestStateManager):
    """Tests for cleanup functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_old_sessions(self, state: StateManager) -> None:
        """Should clean up old closed sessions."""
        # Create and close a session
        session = await state.create_session(user_id=123)
        await state.add_message(session.id, "user", "test")
        await state.close_session(session.id)

        # Cleanup with 0 days should delete it
        await state.cleanup_old_sessions(days=0)

        # Session should be deleted
        retrieved = await state.get_session(session.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_cleanup_preserves_active_sessions(self, state: StateManager) -> None:
        """Should not delete active sessions."""
        session = await state.create_session(user_id=123)

        await state.cleanup_old_sessions(days=0)

        # Active session should still exist
        retrieved = await state.get_session(session.id)
        assert retrieved is not None


class TestInitialization(TestStateManager):
    """Tests for initialization."""

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, tmp_path: Path) -> None:
        """Should create database tables on initialize."""
        db_path = tmp_path / "new.db"
        manager = StateManager(db_path=db_path)
        await manager.initialize()

        # Should be able to use the manager
        session = await manager.create_session(user_id=123)
        assert session.id

    @pytest.mark.asyncio
    async def test_auto_initializes_on_first_operation(self, tmp_path: Path) -> None:
        """Should auto-initialize when needed."""
        db_path = tmp_path / "auto.db"
        manager = StateManager(db_path=db_path)

        # Don't call initialize() explicitly
        session = await manager.create_session(user_id=123)
        assert session.id

    @pytest.mark.asyncio
    async def test_creates_data_directory(self, tmp_path: Path) -> None:
        """Should create data directory if it doesn't exist."""
        db_path = tmp_path / "subdir" / "deep" / "test.db"
        manager = StateManager(db_path=db_path)
        await manager.initialize()

        assert db_path.parent.exists()
