"""Runtime timeline; scene snapshots must never restore this counter."""
import uuid

from .errors import ToolError


class RuntimeState:
    def __init__(self):
        self._session_id = str(uuid.uuid4())
        self._revision = 0

    @property
    def session_id(self):
        return self._session_id

    @property
    def revision(self):
        return self._revision

    def check(self, session_id, expected_revision):
        if session_id != self.session_id:
            raise ToolError('SESSION_MISMATCH', 'Request belongs to a different runtime session.')
        if expected_revision != self.revision:
            raise ToolError('STALE_SCENE_STATE', 'Expected revision does not match the runtime.',
                            {'expected_revision': expected_revision, 'current_revision': self.revision})

    def advance(self):
        """Record a mutation attempt or rollback without rewinding scene history."""
        self._revision += 1
        return self._revision
