"""One bounded literal text write; no generated commands or code execution."""

from __future__ import annotations

import json
from pathlib import PurePosixPath


def _path(path: str) -> str:
    relative = PurePosixPath(path)
    if (
        not path
        or len(path) > 200
        or relative.is_absolute()
        or relative.as_posix() != path
        or "\\" in path
        or any(ord(c) < 32 for c in path)
        or any(part.startswith(".") for part in relative.parts)
        or relative.suffix not in {".txt", ".ini", ".csv"}
    ):
        raise ValueError("Only a confined plain-text task path is allowed")
    return path


def literal_write_schema(allowed_path: str) -> dict:
    return {
        "type": "object",
        "properties": {
            "op": {"const": "write"},
            "path": {"const": _path(allowed_path)},
            "content": {"type": "string", "maxLength": 8192},
        },
        "required": ["op", "path", "content"],
        "additionalProperties": False,
    }


def parse_literal_write(raw: str, allowed_path: str) -> str:
    """Validate before EditorEnvironment receives an action. Never repair output."""
    _path(allowed_path)
    if len(raw.encode("utf-8")) > 32768:
        raise ValueError("Action exceeds 32 KiB")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate action field")
            value[key] = item
        return value

    action = json.loads(raw, object_pairs_hook=unique)
    if (
        not isinstance(action, dict)
        or set(action) != {"op", "path", "content"}
        or action["op"] != "write"
        or action["path"] != allowed_path
        or not isinstance(action["content"], str)
        or len(action["content"].encode("utf-8")) > 8192
    ):
        raise ValueError("Expected one bounded write to the exact allowed task path")
    return json.dumps(action, ensure_ascii=False)
