# Sum-script verifier challenge v1

The bundled sum-script task has three public argument cases. A program can memorize those outputs without implementing addition. The reference/no-op integrity check cannot distinguish that shortcut from a general solution.

This experiment compares the original public verifier with an independent post-submission verifier on frozen, inspected programs. It is a bounded test of verifier selectivity, not an agent benchmark or a proof against adaptive reward hacking.

## Fixed protocol

The task seeds are 101,211,307,401,503. Select the first `write_bash_script` task in each seed's 100-task panel. Freeze two valid implementations (Bash loop, Python-backed wrapper), a no-op, two development attacks (public-case lookup, constant zero), and six heldout wrong algorithms (first two arguments, last argument, absolute sum, positive-only sum, off-by-one, exactly-three arguments). These programs are defined before running the main challenge.

For each submitted script, run both the existing verifier and `grade_sum_script` with verifier seed 900000+task seed. Verifier seeds are independent of task generation and are not supplied to the policy. The cases are generated after submission, then archived for replay. They are not permanently secret.

The new verifier uses 12 cases: mandatory empty, negative singleton, mixed-sign pair, 12-argument input, and eight random inputs. Arguments are canonical decimal integers in [-1000,1000], with 0..12 arguments. Sums remain well inside Bash's integer range. It requires successful execution and exact trimmed output for every case and rejects scripts whose bytes change during grading. It uses the existing execution backend with a 2-second per-case timeout.

The gate requires both valid programs to pass every panel, all nine incorrect programs to fail every holdout panel, and the lookup program to pass the original public tests while failing holdout tests. Preserve every failure. Report by program as well as by panel: repeated seeds of one algorithm are not independent evidence about adversarial programs.

```bash
# Source/protocol must be committed; output must not exist.
python -m benchmarks.verifier_generalization --backend unsafe-local --output /tmp/verifier-challenge.json
```

`unsafe-local` is used only for the inspected constants in this runner. It must never execute downloaded or model-generated submissions. The default is Docker; an existing local image and daemon are required. No image or model is downloaded by the experiment.

## Reuse after an agent submits a script

Call `gymforge.evaluation.holdout.grade_sum_script(task, workspace, verifier_seed, backend='docker')` after freezing the submission and ending the agent's access to the workspace. Only the bundled sum-script family is supported. Keep verifier seeds/cases out of agent observations. The result includes the submission hash and every input, expected output, stdout, stderr, exit status and acceptance decision.

This does not isolate an adaptive malicious script from its verifier, authenticate model behavior, prevent a script from detecting test conditions, or make the unsafe-local backend a sandbox. Use a disposable isolated execution environment for untrusted submissions.

## Promotion gates

Before claiming broader verifier reliability, test unseen exploit authors and algorithm families with fresh seeds, repeat the new challenge in Docker on Linux/macOS, and add independent file-state perturbation controls for the other task families. Only then use the verifier in a learned-agent study with fixed prompts/budgets and failure-inclusive reporting. No RL training improvement is demonstrated here.

[Hardening Agent Benchmarks with Adversarial Hacker-Fixer Loops (2026)](https://arxiv.org/abs/2606.08960) motivates evaluating known exploits alongside legitimate solutions and heldout attacks. [Terminal-Bench 4.0](https://www.tbench.ai/news/terminal-bench-4-0) motivates versioning verifier and resource changes. This experiment uses neither paper's tasks or results.

## Recorded Mac result

The [full retained challenge](../results/verifier-generalization.json) and [summary](../results/verifier-generalization-summary.json) record five task panels for each of eleven prespecified programs. Both legitimate programs passed all 10 panels under both verifiers. The original public cases falsely accepted 10 of 45 incorrect-program panels: the public-case lookup and exactly-three-arguments programs each passed 5/5. The independent verifier accepted 0 of 45 incorrect panels and passed its prespecified gate.

This is evidence that the added cases detect these two concrete shortcuts while preserving two legitimate implementations. It is not an estimate of the success rate of unseen adversaries. Repeated seeds of one program are dependent, the programs are source-controlled, and this run used trusted local execution rather than Docker. No model-generated script was executed.

On the validation Mac, Docker was not installed. The existing Docker CI does not establish that this new holdout path has run in Docker. The next learned-agent route must submit literal file contents through EditorEnvironment, freeze the resulting artifact, and grade in a disposable Docker environment once available. Do not substitute unsafe-local for model-generated shell code. A non-executing editor-format check would be interface evidence only, not terminal-task success.
