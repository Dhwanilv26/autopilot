from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import json
import os
from typing import Any

from config.loader import get_data_dir


def generate_session_id(sessions_dir) -> str:
    today = datetime.now().strftime("%Y-%m-%d")

    # find all today's sessions
    existing = list(sessions_dir.glob(f"chat-{today}-*.json"))

    count = len(existing) + 1

    return f"chat-{today}-{count:03d}"


def format_datetime(self, dt_str: str) -> str:
    dt = datetime.fromisoformat(dt_str)
    hour = dt.strftime("%I").lstrip("0")
    return f"{hour}:{dt.strftime('%M %p, %d %B %Y')}"


@dataclass
class SessionSnapshot:
    session_id: str
    created_at: datetime
    updated_at: datetime
    turn_count: int
    messages: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "turn_count": self.turn_count,
            "messages": self.messages
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionSnapshot:
        return cls(
            session_id=data["session_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            turn_count=data["turn_count"],
            messages=data["messages"]
        )


class PersistenceManager:
    def __init__(self) -> None:
        self.data_dir = get_data_dir()
        self.sessions_dir = self.data_dir/'sessions'
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.sessions_dir, 0o700)

    def format_datetime(self, dt_str: str) -> str:
        dt = datetime.fromisoformat(dt_str)
        hour = dt.strftime("%I").lstrip("0")
        return f"{hour}:{dt.strftime('%M %p, %d %B %Y')}"

    def generate_session_id(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")

        existing = list(self.sessions_dir.glob(f"chat-{today}-*.json"))
        count = len(existing) + 1

        return f"chat-{today}-{count:03d}"

    def save_session(self, snapshot: SessionSnapshot) -> None:
        file_path = self.sessions_dir/f"{snapshot.session_id}.json"

        with open(file_path, "w", encoding="utf-8") as fp:
            json.dump(snapshot.to_dict(), fp, indent=2)

        os.chmod(file_path, 0o600)

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = []
        for file_path in self.sessions_dir.glob("*.json"):
            with open(file_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            sessions.append(
                {
                    "session_id": data["session_id"],
                    "created_at": self.format_datetime(data["created_at"]),
                    "updated_at": self.format_datetime(data["updated_at"]),
                    "turn_count": data["turn_count"],
                }
            )
        sessions.sort(key=lambda x: x["updated_at"], reverse=True)
        return sessions
