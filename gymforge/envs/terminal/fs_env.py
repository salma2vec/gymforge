"""Shell environment with bounded, workspace-only filesystem observations."""

from __future__ import annotations

import hashlib
from pathlib import Path

from gymforge.envs.terminal.bash_env import BashEnvironment


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
        for path in sorted(Path(self.workdir).rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            if len(result) >= 1000:
                result["<truncated>"] = "file limit reached"
                break
            key = str(path.relative_to(self.workdir))
            if path.stat().st_size > 1_048_576:
                result[key] = "<exceeds snapshot limit>"
            else:
                result[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    @staticmethod
    def _delta(old, new):
        return {
            "added": sorted(new.keys() - old.keys()),
            "removed": sorted(old.keys() - new.keys()),
            "modified": sorted(k for k in old.keys() & new.keys() if old[k] != new[k]),
        }
