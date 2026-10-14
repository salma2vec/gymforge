"""Shell environment with bounded, workspace-only filesystem observations."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from gymforge.envs.terminal.bash_env import BashEnvironment

MAX_SNAPSHOT_ENTRIES = 1000
MAX_SNAPSHOT_BYTES = 16 * 1_048_576
MAX_SNAPSHOT_FILE_BYTES = 1_048_576


class FileSystemEnvironment(BashEnvironment):
    def reset(self):
        obs = super().reset()
        self._last_fs_state = self._snapshot()
        return {**obs, "fs_state": self._last_fs_state}

    def step(self, action):
        obs, reward, done, info = super().step(action)
        state = self._snapshot()
        obs.update(fs_state=state, fs_delta=self._delta(self._last_fs_state, state))
        self._last_fs_state = state
        return obs, reward, done, info

    def _snapshot(self):
        result = {}
        total_bytes = 0
        visited = 0
        pending = [Path(self.workdir)]
        # pathlib.rglob may materialize a whole directory before yielding on
        # supported Python versions. Consume scandir entries within our budget.
        while pending:
            directory = pending.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if visited >= MAX_SNAPSHOT_ENTRIES:
                            result["<truncated>"] = "entry limit reached"
                            return dict(sorted(result.items()))
                        visited += 1
                        path = Path(entry.path)
                        key = str(path.relative_to(self.workdir))
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                pending.append(path)
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            if entry.stat(follow_symlinks=False).st_size > MAX_SNAPSHOT_FILE_BYTES:
                                result[key] = "<exceeds snapshot limit>"
                                continue
                            remaining = MAX_SNAPSHOT_BYTES - total_bytes
                            limit = min(MAX_SNAPSHOT_FILE_BYTES, remaining)
                            with path.open("rb") as handle:
                                data = handle.read(limit + 1)
                            if len(data) > remaining:
                                result["<truncated>"] = "aggregate byte limit reached"
                                return dict(sorted(result.items()))
                            if len(data) > MAX_SNAPSHOT_FILE_BYTES:
                                result[key] = "<exceeds snapshot limit>"
                                continue
                            total_bytes += len(data)
                            result[key] = hashlib.sha256(data).hexdigest()
                        except OSError:
                            result[key] = "<unreadable>"
            except OSError:
                result[str(directory.relative_to(self.workdir))] = "<unreadable>"
        return dict(sorted(result.items()))

    @staticmethod
    def _delta(old, new):
        return {
            "added": sorted(new.keys() - old.keys()),
            "removed": sorted(old.keys() - new.keys()),
            "modified": sorted(k for k in old.keys() & new.keys() if old[k] != new[k]),
        }
