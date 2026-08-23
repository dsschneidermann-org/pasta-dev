"""A readers-writer lock: many concurrent readers, one exclusive writer.

Writer-preferred, so a steady stream of reads cannot starve a write. In-process only.
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import final


@final
class ReadWriteLock:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._readers = 0
        self._writer: int | None = None
        self._depth = 0
        self._waiting_writers = 0

    @contextmanager
    def read(self) -> Generator[None]:
        """Hold the shared lock; a no-op if this thread already holds the write lock.

        Do not take the write lock while holding this one - it self-deadlocks.
        """
        if self._writer == threading.get_ident():
            yield
            return
        with self._condition:
            while self._writer is not None or self._waiting_writers:
                _ = self._condition.wait()
            self._readers += 1
        try:
            yield
        finally:
            with self._condition:
                self._readers -= 1
                if self._readers == 0:
                    self._condition.notify_all()

    @contextmanager
    def write(self) -> Generator[None]:
        """Hold the exclusive lock. Reentrant for the thread that owns it."""
        ident = threading.get_ident()
        with self._condition:
            if self._writer == ident:
                self._depth += 1
            else:
                self._waiting_writers += 1
                try:
                    while self._writer is not None or self._readers:
                        _ = self._condition.wait()
                finally:
                    self._waiting_writers -= 1
                self._writer = ident
                self._depth = 1
        try:
            yield
        finally:
            with self._condition:
                self._depth -= 1
                if self._depth == 0:
                    self._writer = None
                    self._condition.notify_all()
