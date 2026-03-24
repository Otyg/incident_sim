# LICENSE HEADER MANAGED BY add-license-header
#
# BSD 3-Clause License
#
# Copyright (c) 2026, Martin Vesterlund
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""Buffered session repository that only persists completed sessions."""

from src.models.session import SessionState
from src.models.turn import Turn
from src.storage.in_memory import InMemorySessionRepository
from src.storage.tinydb_json import TinyDBSessionRepository


class BufferedSessionRepository:
    """Keep active sessions in memory and persist only completed sessions."""

    def __init__(
        self,
        active_repo: InMemorySessionRepository | None = None,
        archive_repo: TinyDBSessionRepository | None = None,
    ) -> None:
        self._active = active_repo or InMemorySessionRepository()
        self._archive = archive_repo or TinyDBSessionRepository()

    def save(self, session: SessionState) -> SessionState:
        """Store active sessions in memory and archive completed sessions."""

        if session.status == "completed":
            timeline = self._active.get_timeline(session.session_id)
            self._archive.save(session)
            for turn in timeline:
                self._archive.append_turn(session.session_id, turn)
            self._active.remove(session.session_id)
            return session

        return self._active.save(session)

    def get(self, session_id: str) -> SessionState | None:
        """Fetch session state from memory first, then archive."""

        active = self._active.get(session_id)
        if active is not None:
            return active
        return self._archive.get(session_id)

    def append_turn(self, session_id: str, turn: Turn) -> Turn:
        """Append turns only to the in-memory timeline."""

        return self._active.append_turn(session_id, turn)

    def get_timeline(self, session_id: str) -> list[Turn]:
        """Fetch timeline from memory first, then archive."""

        timeline = self._active.get_timeline(session_id)
        if timeline:
            return timeline
        return self._archive.get_timeline(session_id)

    def count(self) -> int:
        """Count both active and archived sessions."""

        return self._active.count() + self._archive.count()

    def save_report(self, session_id: str, markdown: str) -> str:
        """Persist reports in the archive store."""

        return self._archive.save_report(session_id, markdown)

    def get_report(self, session_id: str) -> str | None:
        """Fetch reports from the archive store."""

        return self._archive.get_report(session_id)

    def clear(self) -> None:
        """Remove all stored sessions, timelines, and reports."""

        self._active.clear()
        self._archive.clear()
