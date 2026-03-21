"""EditorEnvironment: structured read/write/patch operations on files."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from difflib import unified_diff
from pathlib import Path
from typing import Any

from gymforge.core.environment import BaseEnvironment, Observation
from gymforge.core.task import TaskSpec


class EditorEnvironment(BaseEnvironment):
    """Provides read/write/patch operations on files in a sandboxed workspace.

    Actions are JSON-encoded dicts with an ``"op"`` key:

    - ``{"op": "read", "path": "relative/path"}``
      Returns the file content in ``obs["content"]``.
    - ``{"op": "write", "path": "relative/path", "content": "..."}``
      Writes content to the file, creating parent dirs as needed.
    - ``{"op": "patch", "path": "relative/path", "old": "...", "new": "..."}``
      Replaces the first occurrence of *old* with *new*.
    - ``{"op": "list", "path": "relative/dir"}``
      Lists directory contents. Defaults to workspace root if path omitted.
    - ``{"op": "delete", "path": "relative/path"}``
      Deletes a file.

    Success is evaluated against ``task_spec.success_criteria``:
    - ``expected_file``: the file must exist.
    - ``expected_file_content``: a substring that must appear in the file.
    - ``expected_file_exact``: the file content must exactly match.
    """

    def __init__(self, task_spec: TaskSpec, timeout: int = 10) -> None:
        self._task_spec = task_spec
        self._timeout = timeout
        self._workdir: str | None = None
        self._step_count: int = 0

    # ------------------------------------------------------------------
    # BaseEnvironment interface
    # ------------------------------------------------------------------

    def reset(self) -> Observation:
        """Reset the workspace and apply scaffolding."""
        if self._workdir and os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir, ignore_errors=True)
        self._workdir = tempfile.mkdtemp()
        self._step_count = 0
        self._apply_scaffolding()
        return {
            "status": "ok",
            "op": "reset",
            "content": "",
            "error": "",
            "cwd": self._workdir,
        }

    def step(self, action: str) -> tuple[Observation, float, bool, dict]:
        """Execute *action* as a structured editor operation.

        *action* must be a JSON string with an ``"op"`` field.
        """
        if self._workdir is None:
            raise RuntimeError("Call reset() before step().")

        obs = self._dispatch(action)
        self._step_count += 1
        success = self._check_success()
        reward = 1.0 if success else 0.0
        done = success or (self._step_count >= self._task_spec.max_steps)
        return obs, reward, done, {"step": self._step_count}

    def render(self) -> str:
        """Return a tree view of the current workspace."""
        lines = [f"EditorEnvironment(workdir={self._workdir})"]
        if self._workdir and os.path.isdir(self._workdir):
            for dirpath, dirnames, filenames in os.walk(self._workdir):
                rel = os.path.relpath(dirpath, self._workdir)
                prefix = "  " if rel == "." else f"  {rel}/"
                for fname in sorted(filenames):
                    lines.append(f"{prefix}{fname}")
        return "\n".join(lines)

    def close(self) -> None:
        """Remove the workspace directory."""
        if self._workdir and os.path.isdir(self._workdir):
            shutil.rmtree(self._workdir, ignore_errors=True)
        self._workdir = None

    @property
    def task_spec(self) -> TaskSpec:
        """Return the TaskSpec driving this environment."""
        return self._task_spec

    @property
    def workdir(self) -> str | None:
        """Return the current workspace directory path."""
        return self._workdir

    # ------------------------------------------------------------------
    # Dispatch helpers
    # ------------------------------------------------------------------

    def _dispatch(self, action: str) -> Observation:
        """Parse and dispatch an action string to the appropriate handler."""
        base: Observation = {
            "status": "ok",
            "op": "",
            "content": "",
            "error": "",
            "cwd": self._workdir,
        }
        try:
            cmd = json.loads(action)
        except json.JSONDecodeError as exc:
            base["status"] = "error"
            base["error"] = f"Invalid JSON action: {exc}"
            return base

        op = cmd.get("op", "")
        base["op"] = op

        if op == "read":
            return self._op_read(cmd, base)
        elif op == "write":
            return self._op_write(cmd, base)
        elif op == "patch":
            return self._op_patch(cmd, base)
        elif op == "list":
            return self._op_list(cmd, base)
        elif op == "delete":
            return self._op_delete(cmd, base)
        else:
            base["status"] = "error"
            base["error"] = f"Unknown op: {op!r}"
            return base

    def _resolve(self, rel_path: str) -> str:
        """Resolve *rel_path* relative to the workspace, rejecting path traversal."""
        resolved = os.path.realpath(os.path.join(self._workdir, rel_path))  # type: ignore[arg-type]
        if not resolved.startswith(os.path.realpath(self._workdir)):  # type: ignore[arg-type]
            raise ValueError(f"Path traversal detected: {rel_path!r}")
        return resolved

    def _op_read(self, cmd: dict, obs: Observation) -> Observation:
        path = self._resolve(cmd.get("path", ""))
        if not os.path.isfile(path):
            obs["status"] = "error"
            obs["error"] = f"File not found: {cmd.get('path')}"
            return obs
        with open(path) as fh:
            obs["content"] = fh.read()
        return obs

    def _op_write(self, cmd: dict, obs: Observation) -> Observation:
        path = self._resolve(cmd.get("path", ""))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(cmd.get("content", ""))
        obs["content"] = cmd.get("content", "")
        return obs

    def _op_patch(self, cmd: dict, obs: Observation) -> Observation:
        path = self._resolve(cmd.get("path", ""))
        if not os.path.isfile(path):
            obs["status"] = "error"
            obs["error"] = f"File not found: {cmd.get('path')}"
            return obs
        with open(path) as fh:
            original = fh.read()
        old = cmd.get("old", "")
        new = cmd.get("new", "")
        if old not in original:
            obs["status"] = "error"
            obs["error"] = f"Pattern not found in {cmd.get('path')}"
            return obs
        patched = original.replace(old, new, 1)
        with open(path, "w") as fh:
            fh.write(patched)
        diff = list(
            unified_diff(
                original.splitlines(keepends=True),
                patched.splitlines(keepends=True),
                fromfile=f"a/{cmd.get('path')}",
                tofile=f"b/{cmd.get('path')}",
            )
        )
        obs["content"] = "".join(diff)
        return obs

    def _op_list(self, cmd: dict, obs: Observation) -> Observation:
        rel = cmd.get("path", ".")
        path = self._resolve(rel)
        if not os.path.isdir(path):
            obs["status"] = "error"
            obs["error"] = f"Directory not found: {rel}"
            return obs
        entries = sorted(os.listdir(path))
        obs["content"] = "\n".join(entries)
        return obs

    def _op_delete(self, cmd: dict, obs: Observation) -> Observation:
        path = self._resolve(cmd.get("path", ""))
        if not os.path.exists(path):
            obs["status"] = "error"
            obs["error"] = f"Path not found: {cmd.get('path')}"
            return obs
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return obs

    # ------------------------------------------------------------------
    # Scaffolding & success check
    # ------------------------------------------------------------------

    def _apply_scaffolding(self) -> None:
        for fname, content in self._task_spec.scaffolding.get("files", {}).items():
            path = os.path.join(self._workdir, fname)  # type: ignore[arg-type]
            os.makedirs(os.path.dirname(path) or self._workdir, exist_ok=True)
            with open(path, "w") as fh:
                fh.write(content)

    def _check_success(self) -> bool:
        """Evaluate the workspace against the task success criteria."""
        criteria = self._task_spec.success_criteria
        if not criteria:
            return False

        expected_file = criteria.get("expected_file")
        if expected_file:
            path = os.path.join(self._workdir, expected_file)  # type: ignore[arg-type]
            if not os.path.isfile(path):
                return False

            if "expected_file_exact" in criteria:
                with open(path) as fh:
                    return fh.read() == criteria["expected_file_exact"]

            if "expected_file_content" in criteria:
                with open(path) as fh:
                    return criteria["expected_file_content"].strip() in fh.read()

            return True

        return False
