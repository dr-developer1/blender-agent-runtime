"""Public tool errors, independent of Blender and transport."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self):
        return {'code': self.code, 'message': self.message, 'details': self.details}
