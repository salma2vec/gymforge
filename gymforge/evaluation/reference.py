"""Transparent reference solvers for bundled task-family integrity checks."""

import shlex

from gymforge.core.task import TaskSpec


def reference_action(task: TaskSpec) -> str:
    s = task.metadata["slots"]
    family = task.metadata["template"]
    if family == "count_lines":
        return f"grep -F -c -- {shlex.quote(s['pattern'])} {shlex.quote(s['filename'])}"
    if family == "find_largest_file":
        code = f"from pathlib import Path; print(max(Path({s['directory']!r}).iterdir(), key=lambda p: p.stat().st_size).name)"
    elif family == "find_replace":
        code = f"from pathlib import Path; p=Path({s['filename']!r}); t=p.read_text(); print(t.count({s['old_text']!r})); p.write_text(t.replace({s['old_text']!r}, {s['new_text']!r}))"
    elif family == "sort_dedup_csv":
        code = f"import csv; rows=list(csv.reader(open({s['filename']!r}))); col=rows[0].index({s['sort_col']!r}); out=open({s['output_file']!r}, 'w', newline=''); w=csv.writer(out, lineterminator='\\n'); w.writerow(rows[0]); w.writerows(sorted(set(map(tuple, rows[1:])), key=lambda row:(row[col],row))); out.close()"
    elif family == "write_bash_script":
        content = (
            '#!/bin/bash\nsum=0\nfor x in "$@"; do sum=$((sum+x)); done\nprintf "%s\\n" "$sum"\n'
        )
        code = f"from pathlib import Path; p=Path({s['script_name']!r}); p.write_text({content!r}); p.chmod(0o755)"
    else:
        raise ValueError("No reference solver for custom template")
    return "python3 -c " + shlex.quote(code)
