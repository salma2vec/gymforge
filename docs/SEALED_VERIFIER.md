# Sealed sum-script verifier protocol v2

## Falsified assumption

The v1 sum-script challenge calls its cases “independent,” but its recorded runner fixes verifier seeds in public source. After publication, a submission can reconstruct all twelve cases and return a lookup-table answer without implementing addition. `benchmarks/sealed_verifier.py` preserves that negative control: the lookup program passes v1.

This is a concrete evaluator-leakage failure. It does not show that the earlier recorded result was fabricated; all earlier attack programs were frozen before those cases were generated. It shows that the public v1 panel cannot be reused prospectively against an adaptive submission.

## Commit–freeze–reveal protocol

Use a fresh challenge for one closed batch of submissions:

```text
32-byte OS-random secret
          |
          v
publish SHA-256 commitment + challenge ID
          |
          v
freeze SHA-256 of every executable submission
          |
          v
derive cases with domain-separated HMAC-SHA256
          |
          v
grade frozen bytes; preserve every case record
          |
          v
after the complete batch, reveal the secret for replay
```

The commitment prevents the evaluator from choosing a favorable secret after seeing submissions. The frozen submission digest prevents a participant from changing its program after learning cases. The grading record includes the challenge ID, commitment, submission digest, inputs, outputs, exit codes and per-case verdicts, but never the secret. The post-batch reveal reproduces the panel and verifies the commitment. Revealed challenges are retired permanently.

The case generator uses fixed shapes and domain-separated HMAC-SHA256 draws rather than Python's simulation PRNG. The secret must be exactly 32 bytes. The standard-library `secrets.token_bytes(32)` source is appropriate for the prospective key; the benchmark runner uses it. Exact source and task versions still need a release manifest.

The process boundary remains operational: publish the commitment somewhere append-only before accepting submissions, freeze every submission in the batch, restrict secret access to the evaluator, and reveal only after the last result is final. The Python API cannot prove that an operator followed that chronology.

## Local falsification run

Commit the protocol and fixtures first, then run:

```bash
python -m benchmarks.sealed_verifier \
  --challenge-id local-2026-10-14 \
  --backend unsafe-local \
  --output /tmp/gymforge-sealed-verifier.json
```

`unsafe-local` is only for the three inspected programs in the runner. Never use it for agent-produced code. A serious evaluation must use the Docker backend or a disposable VM and must freeze all submissions before the secret is available to them.

The gate requires the legitimate loop to pass v1 and v2, the no-op to fail both, the public-v1 lookup to pass v1 and fail the fresh sealed panel, and a post-freeze program tailored to the revealed cases to be rejected before any case executes. Preserve a failed gate and the full artifact rather than selecting a replacement secret.

## Evidence boundary and next gate

The local runner has one legitimate implementation and two controls. It tests protocol mechanics and a known exploit, not the rate at which unseen adversaries evade the verifier. The twelve cases still cover only canonical decimal integer addition. A malicious program can identify its runtime environment, write auxiliary files, exploit the execution boundary, or implement addition only on the sampled domain. Commit–reveal does not validate task instructions, detect model pretraining contamination, or make terminal tasks representative of browser or desktop computer use.

Before using GymForge for a computer-use agent claim:

1. Run the sealed protocol in the real Docker path with independently authored attacks and preserve all failures.
2. Add a versioned release manifest that pins task, evaluator, environment image and agent configuration.
3. Build validated browser or desktop workflows with multiple legitimate end states and audit both false positives and false negatives from traces.
4. Pre-register the task panel, trial count and statistical estimand; report task-level outcomes and uncertainty rather than treating repeated seeds of one program as independent samples.

The protocol follows the direction of current benchmark practice: OSWorld 2.1 gates task implementations to reduce leakage and pins task, asset, website, code and provider-image releases; Terminal-Bench 4.0 treats reward-hack fixes as benchmark-version changes. Recent computer-use audits also show why verifier integrity alone is insufficient: task failures and valid alternative completions can be mis-scored, so failure-inclusive traces and task audits remain required.

Primary sources:

- [OSWorld 2.1 repository and gated task rationale](https://github.com/xlang-ai/OSWorld-V2)
- [OSWorld V2 benchmark release manifests](https://github.com/xlang-ai/OSWorld-V2/blob/main/benchmark_releases/README.md)
- [Terminal-Bench 4.0 versioning and verifier-repair policy](https://www.tbench.ai/news/terminal-bench-4-0)
- [How Benchmarks Mis-Score Computer-Use Agents](https://arxiv.org/abs/2607.28367)
- [Python `secrets` documentation](https://docs.python.org/3/library/secrets.html)
- [Python `hmac` documentation](https://docs.python.org/3/library/hmac.html)
