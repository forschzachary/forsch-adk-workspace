"""Apple/iCloud Reminders sync adapter interface.

No implementation — just the contract. Future lane will provide an
actual iCloud adapter; this module exists so tests can document the
skipped integration boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel


class SyncResult(BaseModel):
    """Result of an attempted Apple Reminders sync."""
    synced: bool
    device: str
    error: Optional[str] = None


class AppleRemindersSync(ABC):
    """Abstract base for Apple Reminders sync adapters.

    Implementations will push reminders to Apple Reminders via
    CloudKit / CalDAV / Shortcuts. This interface exists so remindctl
    can remain agnostic to the sync mechanism.
    """

    @abstractmethod
    def sync_reminder(self, reminder_id: int) -> SyncResult:
        """Push a single reminder to Apple Reminders.

        Args:
            reminder_id: The local Shelby reminder ID to sync.

        Returns:
            SyncResult indicating success/failure and target device.
        """
        ...

    @abstractmethod
    def sync_all_pending(self) -> list[SyncResult]:
        """Sync all unsynced reminders. Returns per-reminder results."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the sync backend is reachable."""
        ...
