# Literal artifact agent pilot v1

This pilot asks whether an existing local language model can complete concrete text-file transformations through Gymforge's actual editor and exact-content scorer. It does not execute generated commands or code. It is a trusted artifact interpreter on the host, not Docker containment or evidence of full terminal computer use or reinforcement learning.

Freeze source before running controls, then inference into a different fresh file:

```bash
python -m benchmarks.literal_agent --controls-only --output /tmp/gymforge-literal-controls.json
python -m benchmarks.literal_agent --output /tmp/gymforge-literal-model.json
```

For each unseen task seed 601, 701 and 809, generate the same 200-task terminal panel at requested difficulty 0.4. Select the first `find_replace` task and the first `sort_dedup_csv` task with at most 20 rows. Derive six one-step editor tasks with unchanged initial files and exact-content expectations. The replacement variant removes the terminal printed-count requirement and explicitly requests the entire edited file; the sorting variant preserves the header and final newline. These are new editor variants, not successful terminal episodes. The 0.4 parameter is a generator input, not a calibrated measure of model difficulty.

A deterministic reference derives the correct transformation from initial files and public task slots without reading expected contents. Every reference must pass and every no-op must fail before any model call. Tests also require a one-byte output mutation to fail. The model sees only the natural-language request, initial files and one allowed output path; evaluation-only expected contents remain outside the model request.

Use the already installed Qwen2.5-Coder 0.5B Q4_K_M model with the pinned digest recorded in the runner. Six calls maximum, one per task, no retries, repairs or fallback. Use native loopback Ollama chat, temperature 0, per-task sampling seeds 2000–2005, context request 8192, output budget 1000 and 30-second timeout. Provider truncation, malformed output and execution/scoring failures remain in the six-task denominator. No generated shell, expressions, imports, programs or file contents are evaluated. A strict parser permits only one `write` to the exact allowlisted `.txt`, `.ini` or `.csv` path, at most 8 KiB of literal UTF-8 content. Editor path confinement still applies.

The minimal functional gate is at least one exact completion in each family, with all reference/no-op gates and reported model-digest continuity passing. This is an existence check on a fixed six-task panel, not a reliability threshold. Report all six outcomes, valid actions separately from successful tasks, and failures with raw outputs. No confidence interval or population-level effect is claimed from three dependent generated tasks per family.

The artifact records source commit/hashes, complete model requests/responses, output hashes, model parameters, runtime and service-reported digest before and after inference. This is continuity evidence, not model attestation. Sampling seeds request reproducibility; no native full-prompt token equality check is performed, so context completeness remains unverified. A negative result remains published; changing model, schema, budget or tasks requires a separately frozen follow-up.

Promotion still requires a larger held-out task panel, independent templates, stronger models, adversarial scorer controls, and Docker-contained execution for terminal agents. No learning claim is supported until an actual training intervention improves held-out performance against compute-matched controls.
