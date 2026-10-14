"""Six bounded local-model artifact edits, scored without executing model code."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import platform
import subprocess
import time
import urllib.request
from pathlib import Path

from gymforge.core.task import TaskSpec
from gymforge.envs import EditorEnvironment
from gymforge.evaluation.literal import literal_write_schema, parse_literal_write
from gymforge.generation import TaskGenerator

MODEL = "qwen2.5-coder:0.5b"
DIGEST = "4ff64a7f502a08b7616edb8ca0a79eb1853fc363d842b7df4b46915d11a3fb09"


class InvalidModelResponse(ValueError):
    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Local model redirects are forbidden")


def request(path: str, body: dict | None = None) -> tuple[str, dict]:
    if path not in {"/api/tags", "/api/show", "/api/version", "/api/chat"}:
        raise ValueError("Forbidden model endpoint")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request(
        "http://127.0.0.1:11434" + path,
        data=json.dumps(body).encode() if body else None,
        headers={"Content-Type": "application/json"},
    )
    with opener.open(req, timeout=30) as response:
        raw = response.read(1_048_577)
    if len(raw) > 1_048_576:
        raise ValueError("Local response exceeds 1 MiB")
    text = raw.decode()
    try:
        parsed = json.loads(text)
    except ValueError as error:
        raise InvalidModelResponse("Model response is not JSON", text) from error
    if not isinstance(parsed, dict):
        raise InvalidModelResponse("Model response is not an object", text)
    return text, parsed


def tasks() -> list[TaskSpec]:
    selected = []
    for seed in [601, 701, 809]:
        panel = TaskGenerator().generate("terminal", 0.4, 200, seed)
        for family in ["find_replace", "sort_dedup_csv"]:
            original = next(
                t
                for t in panel
                if t.metadata["template"] == family and (t.metadata["slots"].get("n_rows", 0) <= 20)
            )
            slots = original.metadata["slots"]
            allowed = slots["filename"] if family == "find_replace" else slots["output_file"]
            if family == "find_replace":
                description = (
                    f"In {slots['filename']}, replace every occurrence of {slots['old_text']!r} "
                    f"with {slots['new_text']!r}. Preserve all other text and the final newline. "
                    "Write the complete edited file. No printed-count requirement applies to this editor variant."
                )
            else:
                description = original.description + ". Preserve the CSV header and final newline."
            selected.append(
                TaskSpec(
                    name=family + "_artifact",
                    description=description,
                    domain="editor",
                    difficulty=original.difficulty,
                    max_steps=1,
                    id=original.id + "-artifact-v1",
                    scaffolding=original.scaffolding,
                    success_criteria={
                        "expected_file": allowed,
                        "expected_file_exact": original.success_criteria["expected_file_exact"],
                    },
                    metadata={
                        **original.metadata,
                        "task_seed": seed,
                        "parent_task_id": original.id,
                    },
                )
            )
    return selected


def reference_content(task: TaskSpec) -> str:
    """Use the task's initial data and slots, never its expected-file criterion."""
    slots = task.metadata["slots"]
    text = task.scaffolding["files"][slots["filename"]]
    if task.metadata["template"] == "find_replace":
        return text.replace(slots["old_text"], slots["new_text"])
    rows = list(csv.reader(io.StringIO(text)))
    index = rows[0].index(slots["sort_col"])
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(rows[0])
    writer.writerows(sorted(set(map(tuple, rows[1:])), key=lambda r: (r[index], r)))
    return buffer.getvalue()


def prompt_for(task: TaskSpec) -> dict:
    allowed = task.success_criteria["expected_file"]
    return {
        "role": "user",
        "content": json.dumps(
            {
                "task": task.description,
                "initial_files": task.scaffolding["files"],
                "allowed_output": allowed,
            },
            ensure_ascii=False,
        ),
    }


def score(task: TaskSpec, action: str | None) -> dict:
    env = EditorEnvironment(task)
    try:
        env.reset()
        if action is None:
            return {"accepted": env._check_success(), "action_valid": False}
        validated = parse_literal_write(action, task.success_criteria["expected_file"])
        observation, reward, _, _ = env.step(validated)
        output = Path(env.workdir) / task.success_criteria["expected_file"]
        return {
            "accepted": reward == 1 and observation["status"] == "ok",
            "action_valid": True,
            "output": output.read_text(),
            "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        }
    finally:
        env.close()


def run(output: Path, controls_only: bool) -> dict:
    if output.exists():
        raise ValueError("Choose a fresh output path")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("Commit protocol and source before running")
    selected = tasks()
    rows = []
    paths = sorted(
        [
            *Path("gymforge").rglob("*.py"),
            Path("benchmarks/literal_agent.py"),
            Path("docs/LITERAL_AGENT_PILOT.md"),
        ]
    )
    artifact = {
        "protocol": "literal-artifact-agent-v1",
        "python": platform.python_version(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_hashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "controls_only": controls_only,
        "model": MODEL,
        "rows": rows,
        "limits": "Six derived editor tasks, one local model, one sample each. No shell/code execution, no full terminal success, RL or difficulty-calibration claim. Context completeness unverified.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        temporary = output.with_suffix(output.suffix + ".tmp")
        with temporary.open("x") as handle:
            json.dump(artifact, handle, indent=2, allow_nan=False)
            handle.write("\n")
        temporary.replace(output)

    output.touch(exist_ok=False)
    save()
    for task in selected:
        action = json.dumps(
            {
                "op": "write",
                "path": task.success_criteria["expected_file"],
                "content": reference_content(task),
            }
        )
        controls = {"reference": score(task, action), "noop": score(task, None)}
        row = {
            "task": task.to_dict(),
            "controls": controls,
            "accepted": False,
            "action_valid": False,
            "status": "not_attempted",
        }
        rows.append(row)
        if not controls["reference"]["accepted"] or controls["noop"]["accepted"]:
            save()
            raise ValueError("Reference/no-op gate failed before model inference")
    save()
    if not controls_only:
        _, tags = request("/api/tags")
        installed = next((m for m in tags.get("models", []) if m.get("name") == MODEL), None)
        if not installed or installed.get("digest") != DIGEST:
            raise ValueError("Pinned model must already be installed; never download")
        _, details = request("/api/show", {"model": MODEL})
        if details.get("remote_host") or details.get("remote_model"):
            raise ValueError("Cloud model forbidden")
        _, runtime = request("/api/version")
        artifact.update(
            model_metadata=installed,
            runtime=runtime,
            model_parameters=details.get("parameters"),
            template_sha256=hashlib.sha256(details.get("template", "").encode()).hexdigest(),
        )
        for index, (task, row) in enumerate(zip(selected, rows, strict=True)):
            body = {
                "model": MODEL,
                "stream": False,
                "format": literal_write_schema(task.success_criteria["expected_file"]),
                "messages": [
                    {
                        "role": "system",
                        "content": "Perform the requested text-file transformation. Return one JSON write action with the complete literal file content. Never return commands, code, explanations or markdown. Preserve unchanged text exactly.",
                    },
                    prompt_for(task),
                ],
                "options": {
                    "temperature": 0,
                    "seed": 2000 + index,
                    "num_ctx": 8192,
                    "num_predict": 1000,
                },
            }
            row.update(
                request=body,
                request_sha256=hashlib.sha256(json.dumps(body).encode()).hexdigest(),
                status="running",
            )
            save()
            started = time.monotonic()
            try:
                raw, response = request("/api/chat", body)
                row.update(response=raw, response_sha256=hashlib.sha256(raw.encode()).hexdigest())
                if response.get("done") is not True or response.get("done_reason") != "stop":
                    raise ValueError("Incomplete response")
                message = response.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                if not isinstance(content, str):
                    raise ValueError("Missing model content")
                row.update(score(task, content), status="completed")
            except (OSError, ValueError, UnicodeError, RecursionError) as error:
                if isinstance(error, InvalidModelResponse):
                    row.update(
                        response=error.raw,
                        response_sha256=hashlib.sha256(error.raw.encode()).hexdigest(),
                    )
                row.update(error=str(error), status="failed")
            row["elapsed_seconds"] = time.monotonic() - started
            save()
            print(
                json.dumps(
                    {
                        "index": index,
                        "family": task.name,
                        "accepted": row["accepted"],
                        "status": row["status"],
                    }
                ),
                flush=True,
            )
        _, final_tags = request("/api/tags")
        artifact["digest_continuity"] = any(
            m.get("name") == MODEL and m.get("digest") == DIGEST
            for m in final_tags.get("models", [])
        )
    artifact["summary"] = {
        "tasks": len(rows),
        "reference_passes": sum(r["controls"]["reference"]["accepted"] for r in rows),
        "noop_passes": sum(r["controls"]["noop"]["accepted"] for r in rows),
        "attempted": sum("request" in r for r in rows),
        "valid_actions": sum(r["action_valid"] for r in rows),
        "task_completions": sum(r["accepted"] for r in rows),
    }
    families = {t.metadata["template"] for t in selected}
    artifact["summary"]["by_family"] = {
        family: {
            "tasks": sum(t.metadata["template"] == family for t in selected),
            "completed": sum(
                r["accepted"]
                for t, r in zip(selected, rows, strict=True)
                if t.metadata["template"] == family
            ),
        }
        for family in sorted(families)
    }
    artifact["summary"]["functional_gate_passed"] = (
        not controls_only
        and artifact.get("digest_continuity") is True
        and all(result["completed"] >= 1 for result in artifact["summary"]["by_family"].values())
    )
    save()
    print(json.dumps(artifact["summary"], indent=2))
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--controls-only", action="store_true")
    args = parser.parse_args()
    run(args.output, args.controls_only)
