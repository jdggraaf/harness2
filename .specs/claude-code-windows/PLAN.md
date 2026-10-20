# Plan: Claude Code executor (`cc`) for Harness², runnable on native Windows

Status: researched against commit `1cfe254` (main). Every "Fact" below was verified in the code;
`file:line` references are to that commit. Scope of the first iteration: **JobBench only**.

---

## 1. Goal and decisions

| # | Decision | Why |
|---|---|---|
| D1 | New substrate key `cc`, class `ClaudeCodeSubstrate`, surface name `claude_code`, install mode `claude_root`. | Mirrors `cx` / `CodexSubstrate` / `codex` / `codex_root`. |
| D2 | JobBench only. LAB and WorkBuddy stay `oc`/`cx`. | WorkBuddy needs Docker; LAB has its own runner. One benchmark proves the substrate. |
| D3 | The JobBench `cc` launcher is **pure Python** (no bash runner). | The `cx` runner is a 559-line bash script; a Python port is the only thing that runs on native Windows. |
| D4 | The improver (proposer/selector) uses the existing `claude_cli` channel for `cc` cells. | Avoids installing OpenCode + Bun on Windows. |
| D5 | Base harness for `cc` = the codex base harness text, renamed to `CLAUDE.md`. | Keeps `cc` vs `cx` comparisons fair. |
| D6 | All OS branching lives in one new module, `harness2/core/proc.py`. POSIX behaviour stays byte-for-byte identical. | Smallest blast radius; existing tests keep passing. |
| D7 | No new dependencies. Tests use stdlib `unittest`. | Matches the repo (`tests/test_workflow.py`, `dependencies = []`). |

---

## 2. Verified facts (ground truth)

### Substrate and tree
- F1 `Substrate` protocol: `surface()`, `materialise(tree_dir, spec, ctx) -> Install`, `execute(task_ref, install, run_ids, timeout)`, `read_trajectory(stream_path, *, obs_trunc, max_chars, args_trunc)`, `preflight()` — `substrate/base.py:48-80`.
- F2 `CodexSubstrate` is the closest template: `materialise` copies `CODEX_ROOT_ENTRIES` into a `tempfile.mkdtemp` and returns `Install(staging_dir, fingerprint=RM.fingerprint(tree_dir), extras={"install_mode": ...})` — `substrate/codex.py:120-147`. `execute` delegates to a launcher the benchmark supplies — `codex.py:185-196`.
- F3 Codex renders its stream into the shared grammar: `[ACTION] name: args`, `[OBSERVATION]` / `[OBSERVATION ERROR]`, `[ASSISTANT]`, `[REASONING]`, `[HARNESS] ...`, `[ERROR]`, then clips to `max_chars` with `_TRUNC_FMT` — `codex.py:205-460`.
- F4 `SurfaceSpec` fields: `name, always_on, always_on_max, always_on_cap_reason, skill_dir, skill_name_rule ("must_match"|"overrides_dir"), trigger_hint, autotrigger_file, trigger_line, subagent_requires_mode, plugin_dir, hooks_file, hook_events, compile_skill_scripts, reject_empty_always_on, stubs` — `core/tree.py:41-60`.
- F5 Tree paths the validator allows: always-on files, `hooks_file`, `<skill_dir>/<name>/SKILL.md`, `<skill_dir>/<name>/scripts/*`, `sub_agents/<name>/AGENT.md`, `scripts/<name>.py`, plugins if `plugin_dir` — `tree.py:64-111`.
- F6 `check_hooks` already validates the Claude Code hook schema (`{"hooks": {"<Event>": [{"matcher":..., "hooks":[{"type":"command","command":...}]}]}}`) — `tree.py:216-251`. No change needed.
- F7 `INSTALL_MODES` is a closed tuple — `core/spec.py:129`.
- F8 There is **no** `ClaudeSubstrate`. Claude exists only as the proposer channel `claude_cli` — `core/spec.py:33`, `core/proposer.py:210-252`.

### Proposer prompts (easy to miss)
- F9 The proposer is told which files it may edit through per-surface prompt text keyed by `surface.name`: `_SURFACE_OPENCODE`, `_SURFACE_CODEX`, `_TTS_SURFACE_HEAD_*`, `_build_surface_texts()` — `core/prompts.py:95-664`. An unknown surface name raises `ValueError` at `prompts.py:667-672`. **A `claude_code` surface text is required or the improver cannot run.**

### JobBench wiring
- F10 Hard-coded substrate tables: `_INSTALL_MODE`, `_DEFAULT_TIMEOUT`, `make_spec` (raises unless `oc`/`cx`), `allow_subagents=(substrate == "oc")` — `benchmarks/jobbench.py:497-521`. Adapter picks launcher/substrate with `if substrate == "oc" ... else` — `jobbench.py:635-640`. `base_harness()` — `jobbench.py:950-958`. `preflight()` has a `cx` branch — `jobbench.py:964-1003`.
- F11 What the `cx` runner does (to port): copy `task_folder` into a temp workspace, copy harness entries into the workspace root, build a fixed prompt (task folder + output dir + rules), run the CLI with a timeout, write stdout to `model_traj/<label>/<profession>_<taskN>_<label>_attempt1_<stamp>.jsonl`, append `attempt_index.tsv`, treat empty output as failure, move outputs to `model_output/<label>/`, delete the workspace — `third_party/jb_runner/run_benchmark_codex_cli_adapt.sh` (`run_task`).
- F12 `trajectory()` reads the newest `model_traj/<label>/*.jsonl` and calls `substrate.read_trajectory(..., max_chars=8_000_000)` — `jobbench.py:868-880`.
- F13 Codex base harness = one 116-byte `AGENTS.md` — `third_party/jb_runner/codex_base_harness/AGENTS.md`.
- F14 CLI substrate choices: `cli/_common.py:32` (`SUBSTRATES`), help text `_common.py:107`; `cli/setup.py:36` (`choices=("oc","cx")`).

### Windows blockers on the `cc` + JobBench path
- W1 `core/schedule.py:294-328` imports `fcntl` → every run crashes on Windows.
- W2 `jobbench.py:55-69` `run_detached`: `start_new_session=True` + `os.killpg` (POSIX only).
- W3 `jobbench.py:838-841` builds `PATH` with `:` instead of `os.pathsep`.
- W4 `core/tree.py:140,167` use `str(p.relative_to(d))` → tree keys get backslashes on Windows, so lookups like `tree[f"sub_agents/{name}/AGENT.md"]` (`tree.py:308`) miss. Same in `core/runmark.py:54` and `core/proposer.py:525` (fingerprints). Fix with `.as_posix()` (identical output on POSIX).
- W5 `config.py:132,137` and `cli/setup.py`, `install.py:312` hard-code `.venv/bin/python`; on Windows it is `.venv\Scripts\python.exe`.
- W6 `proposer.py:39` `SYSTEM_ARG_MAX = 120_000` passes up to 120 KB via argv → `WinError 206` (limit ~32 KB). Stdin fallback already exists at `proposer.py:224-229`; only the threshold must drop on Windows.
- W7 `proposer.py:105-115` forces Vertex for `claude_cli` (`CLAUDE_CODE_USE_VERTEX=1`). Users with `claude login` or an API key cannot use it.
- W8 `config.py:174` `DEFAULT_PROPOSER_CHANNEL = "opencode"` (not configurable) and `config.validate_models` (`config.py:181-186`) requires provider-prefixed models (`a/b`); a bare Claude id fails.
- W9 `preflight.check()` always runs `OpencodeSubstrate().preflight` and checks the OpenCode checkout/patch — `preflight.py:33-60`. `cli/setup.py` always installs OpenCode + Bun.
- W10 The JobBench judge needs an OpenAI-compatible endpoint (`HARNESS2_JUDGE_BASE_URL`, `HARNESS2_JUDGE_MODEL`) — `config.py:138-153`. Not Windows-specific, but a user without Vertex must point it somewhere.

---

## 3. Design

### 3.1 New configuration (all optional; defaults keep today's behaviour)

| Env var | Default | Meaning |
|---|---|---|
| `HARNESS2_CC_MODEL` | `""` (required for `cc`) | Bare Anthropic id for the executor, e.g. `claude-sonnet-5-5`. |
| `HARNESS2_CC_EFFORT` | `high` | Passed as `--effort`. |
| `HARNESS2_CLAUDE_BIN` | `shutil.which("claude")` | Override for the CLI path. |
| `HARNESS2_CLAUDE_AUTH` | `vertex` | `vertex` \| `api_key` \| `bedrock` \| `login`. Used by both the executor and the `claude_cli` proposer. `vertex` reproduces today's proposer env exactly. |
| `HARNESS2_PROPOSER_CHANNEL` | `opencode` | `opencode` \| `claude_cli`; feeds `config.DEFAULT_PROPOSER_CHANNEL`. |
| `CLAUDE_CODE_GIT_BASH_PATH` | auto | Standard Claude Code variable; set by preflight on Windows when found. |

`config.validate_models(substrate=...)`: when the substrate is `cc` **and** the proposer channel is `claude_cli`, require `HARNESS2_CC_MODEL` and accept bare ids; otherwise keep the current check unchanged.

### 3.2 `harness2/core/proc.py` (new)
- `popen_group(cmd, **kw) -> Popen`: POSIX `start_new_session=True`; Windows `creationflags=CREATE_NEW_PROCESS_GROUP`.
- `kill_tree(proc)`: POSIX `os.killpg(pid, SIGKILL)` → fallback `proc.kill()` (current behaviour). Windows `taskkill /F /T /PID <pid>` → if non-zero: `terminate()`, `wait(5)`, `kill()`, `wait(2)`, then log a warning.
- `file_lock(path)` context manager: POSIX `fcntl.flock`; Windows `msvcrt.locking(fd, LK_LOCK, 1)` with a retry loop (LK_LOCK gives up after ~10 s).
- `rmtree_robust(path)`: `shutil.rmtree(onexc=...)` that clears read-only bits and retries on `PermissionError` (WinError 32) with backoff (0.2 s → 3.2 s).
- `venv_python(repo) -> Path`: `.venv/Scripts/python.exe` on Windows, else `.venv/bin/python`.

### 3.3 Surface `CLAUDE_CODE_SURFACE` (in `substrate/claude_code.py`)

```
name="claude_code"
always_on=("CLAUDE.md",)
always_on_max=8_000
always_on_cap_reason="CLAUDE.md is loaded whole into the context of EVERY turn"
skill_dir=".claude/skills"
skill_name_rule="must_match"        # verify in W0: Claude Code uses the `name:` field
trigger_hint / trigger_line         # as codex, with .claude/skills paths
autotrigger_file="CLAUDE.md"
subagent_requires_mode=False
plugin_dir=None
hooks_file=".claude/settings.json"  # NOT settings.local.json: that is the "local" source and is
                                    # not loaded with --setting-sources project
hook_events = PreToolUse, PostToolUse, UserPromptSubmit, Stop, SubagentStop,
              SessionStart, PreCompact, Notification   # W0 confirms against the installed CLI
compile_skill_scripts=True
reject_empty_always_on=True
stubs = README stubs for scripts/, sub_agents/, .claude/, .claude/skills/ (as codex)
```

### 3.4 `ClaudeCodeSubstrate.materialise` (install mode `claude_root`)
1. Reject any other install mode; reject a dir that is not a tree (as `codex.py:126-131`).
2. Stage into `tempfile.mkdtemp(prefix="adapt-cc-root-")`:
   - `CLAUDE.md`, `.claude/skills/**`, `scripts/**`, `.claude/settings.json` (copied as is).
   - each `sub_agents/<name>/AGENT.md` → `.claude/agents/<name>.md`; inject `name: <name>` into the frontmatter if absent (Claude Code requires `name` + `description`).
3. Every text file is written `encoding="utf-8", newline="\n"`; CRLF in the source is normalised to LF.
4. Return `Install(staged, RM.fingerprint(tree_dir), extras={"install_mode": "claude_root", ...ctx without file:})`.

### 3.5 Command and environment (built by `exec_argv` / `exec_env`, like codex)

```
[claude, "-p",
 "--output-format", "stream-json", "--verbose",
 "--model", HARNESS2_CC_MODEL, "--effort", HARNESS2_CC_EFFORT,
 "--permission-mode", "bypassPermissions",
 "--setting-sources", "project",
 "--strict-mcp-config",
 "--no-session-persistence"]
cwd = workspace, prompt on stdin (never argv), stdout -> traj .jsonl, stderr -> log
Popen(..., encoding="utf-8", errors="replace")
```

Env: copy of `os.environ`, plus `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`; auth block per `HARNESS2_CLAUDE_AUTH`
(the `vertex` block is the one `proposer.py:107-115` uses today; move it into a shared helper
`claude_auth_env(mode, model)` in `claude_code.py` and call it from both places); on Windows
`CLAUDE_CODE_GIT_BASH_PATH`. `CLAUDE_CONFIG_DIR` is set to a per-run temp dir **only** for
`api_key`/`bedrock`/`vertex`; with `login` it is left alone (an empty config dir has no credentials).

Contamination guard: after the run, read the `system/init` event; if it lists plugins, MCP servers,
or skills/agents that are not in the harness, write a `[HARNESS] WARNING: ...` line into the log and
the attempt index. With `login` auth this is the only defence against the user's own `~/.claude`.

### 3.6 `read_trajectory` (stream-json → shared grammar)

| Stream event | Output line |
|---|---|
| `system` / `init` | `[HARNESS] init model=… tools=N skills=[…] agents=[…]` |
| `assistant` → `text` | `[ASSISTANT] …` (clip `obs_trunc`) |
| `assistant` → `thinking` | `[REASONING] …` |
| `assistant` → `tool_use` | `[ACTION] <name>: <input json>` (clip `args_trunc`, default 2000) |
| `user` → `tool_result` | `[OBSERVATION]` or `[OBSERVATION ERROR]` when `is_error` (clip `obs_trunc`) |
| `result` | `[HARNESS] result subtype=… turns=… cost_usd=… tokens in/cache_read/out=…`; `[ERROR] …` when `is_error` |
| non-JSON / blank / undecodable | skipped |

Reuse the codex helpers' behaviour (`_clip`, dedupe consecutive identical lines, final `max_chars`
clip, `"(no parseable events in trajectory)"`, `"(failed to read trajectory: …)"`). Also add
`final_message(path)` returning the `result` event's `result` text.

### 3.7 `preflight()`
1. Resolve the CLI: `HARNESS2_CLAUDE_BIN` → `shutil.which("claude")`. On Windows prefer `claude.exe`; a `.cmd` shim is accepted (argv contains no `"%&|^<>`); a `.ps1`-only install fails with the remedy `irm https://claude.ai/install.ps1 | iex`.
2. Windows: Git Bash via `CLAUDE_CODE_GIT_BASH_PATH` → `%ProgramFiles%\Git\bin\bash.exe` → `%LocalAppData%\Programs\Git\bin\bash.exe` → `shutil.which("bash")` (reject `C:\Windows\System32\bash.exe`, that is WSL).
3. Auth check per mode (`api_key`: `ANTHROPIC_API_KEY`; `vertex`: project + region; `bedrock`: `CLAUDE_CODE_USE_BEDROCK`; `login`: `claude auth status` exit 0).
4. Capability probe: run `claude --version` and `claude --help` once, cache in `config.RUNS / ".cache" / "cc-caps-<version>.json"`, require every flag used in 3.5. Missing → `RuntimeError` naming the flags and the version.
5. Error messages always end with the exact fix, as the other substrates do.

### 3.8 JobBench `_launch_claude` (Python port of F11)
1. `task_id, label, t = self._launch_common(req)`; `self.substrate.preflight()`.
2. Workspace: `Path(tempfile.gettempdir()) / "harness2_cc" / f"{profession}_{taskN}_{label}_{os.getpid()}"` (short; Windows MAX_PATH).
3. Copy `store/<task>/task_folder` → `ws/task_folder`; create `ws/output`; copy `install.staging_dir/*` → `ws/`.
4. Prompt = the exact text from the bash runner, moved to a module constant `JB_TASK_PROMPT` with `{task_folder}`, `{output_dir}`, `{workspace}` placeholders (byte-identical wording to keep `cc` vs `cx` comparable).
5. Run via `proc.popen_group`, wait `t`; on timeout `proc.kill_tree`, status `timeout`, exit code 124 (as the runner).
6. Empty `ws/output` with exit 0 → status `failed`, exit 1. Append `attempt_index.tsv` with the same 11 columns (session id from the `system/init` event).
7. Move outputs to `model_output/<label>/`; `proc.rmtree_robust(ws)`; return `[self._require_artifacts(task_id, label)]`.

Plus: `_INSTALL_MODE["cc"]="claude_root"`, `_DEFAULT_TIMEOUT["cc"]=3600`, `allow_subagents=substrate in ("oc","cc")`, `CC_BASE_HARNESS = _RUNNER_DIR / "claude_base_harness"`, `base_harness()` and `preflight()` branches, `run_detached` → `proc`, `PATH` → `os.pathsep`.

### 3.9 Proposer prompts (`core/prompts.py`)
Add `_SURFACE_CLAUDE_CODE` and `_TTS_SURFACE_HEAD_CLAUDE_CODE`, derived from the codex texts with:
`AGENTS.md`→`CLAUDE.md`, `.agents/skills`→`.claude/skills`, `.codex/hooks.json`→`.claude/settings.json`,
plus a `sub_agents/<name>/AGENT.md` row (codex has subagents disabled on JB; claude_code enables them).
Register `"claude_code"` in `_build_surface_texts()`. Keep every other sentence identical to the
codex text so prompt differences between `cx` and `cc` are only the paths.

---

## 4. File mutation map

| File | Action | Wave |
|---|---|---|
| `harness2/core/proc.py` | CREATE | W1 |
| `harness2/core/schedule.py` | MODIFY: lock via `proc.file_lock` | W1 |
| `harness2/core/tree.py` | MODIFY: `.as_posix()` at :140, :167 | W1 |
| `harness2/core/runmark.py` | MODIFY: `.as_posix()` at :54 | W1 |
| `harness2/core/proposer.py` | MODIFY: `.as_posix()` at :525; Windows `SYSTEM_ARG_MAX` 24_000; auth via `claude_auth_env` | W1, W3 |
| `harness2/benchmarks/jobbench.py` | MODIFY: `run_detached` via `proc`, `os.pathsep` (W1); `cc` wiring + `_launch_claude` (W4) | W1, W4 |
| `harness2/config.py` | MODIFY: `venv_python`, new env vars, channel default from env, `validate_models(substrate=)` | W1, W3 |
| `harness2/install.py` | MODIFY: `venv_python` at :312 | W1 |
| `harness2/core/spec.py` | MODIFY: add `"claude_root"` to `INSTALL_MODES` | W2 |
| `harness2/substrate/claude_code.py` | CREATE | W2, W3 |
| `harness2/substrate/__init__.py` | MODIFY: export | W2 |
| `harness2/core/prompts.py` | MODIFY: claude_code surface texts | W2 |
| `harness2/preflight.py` | MODIFY: skip OpenCode checks when `cc` + `claude_cli` | W3 |
| `harness2/cli/_common.py` | MODIFY: `SUBSTRATES += ("cc",)`, help | W4 |
| `harness2/cli/setup.py` | MODIFY: `--substrate cc`, skip OpenCode/Bun for cc, `venv_python` | W4 |
| `third_party/jb_runner/claude_base_harness/CLAUDE.md` | CREATE (codex text) | W4 |
| `tests/test_proc.py` | CREATE | W1 |
| `tests/test_claude_code.py` | CREATE | W2–W4 |
| `tests/fixtures/claude_stream/*.jsonl` | CREATE | W2 |
| `README.md`, `docs/BENCHMARKS.md`, `.env.example` | MODIFY: cc + Windows section | W5 |
| `pyproject.toml` | MODIFY: Windows classifier, only after W6 passes | W6 |

Not touched: `opencode.py`, `codex.py`, `lab.py`, `workbuddy.py`, `jb_opencode_runner.py`, judge code, scoring.

---

## 5. Tests (stdlib `unittest`; Windows paths tested on every OS via `mock.patch`)

| Test | Covers |
|---|---|
| `test_proc.FileLock*` | lock/unlock both branches; contention with two threads |
| `test_proc.KillTree*` | POSIX killpg path unchanged; Windows taskkill → terminate → kill ladder |
| `test_proc.RmtreeRobust*` | read-only file; PermissionError retried then succeeds |
| `test_proc.TreeKeysPosix` | `read_tree` keys use `/` when `relative_to` yields `\` |
| `test_claude_code.Surface*` | surface shape; `tree.validate` accepts a valid cc tree, rejects `settings.local.json` |
| `test_claude_code.Materialise*` | all entries staged; `sub_agents` → `.claude/agents/<n>.md` with `name:`; no `\r\n` anywhere (seeded random CRLF input); fingerprint = source digest |
| `test_claude_code.Command*` | argv exact; prompt only on stdin; argv < 8 KB for a 200 KB prompt; env per auth mode; `CLAUDE_CONFIG_DIR` absent for `login` |
| `test_claude_code.Trajectory*` | fixtures: normal run, tool error, non-BMP chars, banner noise, truncated last line, empty file, `result.is_error` |
| `test_claude_code.Preflight*` | missing CLI / Git Bash / auth → message with fix; `.ps1`-only; WSL bash rejected; capability cache hit/miss; missing flag |
| `test_claude_code.JobBench*` | `make_spec("cc")`; `base_harness()` is a cc tree; `_launch_claude` with a fake CLI (a Python script emitting fixture events + writing a file to output): artifacts moved, index row, timeout → 124 + tree killed, empty output → failure |
| `test_claude_code.Prompts*` | `prompts.propose/aggregate/compose_round` accept `CLAUDE_CODE_SURFACE`; text mentions `CLAUDE.md`, not `AGENTS.md` |

Gate per wave: `python -m unittest discover -s tests -v` fully green, plus `ruff check harness2 tests`.

---

## 6. Waves (sequential; commit after each green gate)

| Wave | Work | Gate |
|---|---|---|
| W0 | Baseline + probes: run suite (Linux/WSL and Windows); record `claude --version`, `claude --help`, and one real `claude -p --output-format stream-json --verbose` run on a trivial prompt into `tests/fixtures/claude_stream/real_minimal.jsonl`; confirm hook event names, skill `name:` rule, whether `--setting-sources project` keeps `~/.claude/CLAUDE.md` and user plugins out. Update §3.3/§3.5 if anything differs. | written findings, no code changes |
| W1 | Portability: `proc.py`, `schedule.py`, `.as_posix()` fixes, `run_detached`, `os.pathsep`, `venv_python`. | suite green on Linux; imports clean on Windows |
| W2 | Substrate core: surface, `materialise`, `read_trajectory`, `claude_root`, prompts.py texts. | suite green |
| W3 | Preflight, auth helper (shared with proposer), config/env vars, `validate_models`, `preflight.check` skips, Windows `SYSTEM_ARG_MAX`. | suite green; existing proposer tests unchanged |
| W4 | JobBench wiring, `_launch_claude`, base harness, CLI/setup choices. | suite green incl. fake-CLI launcher tests |
| W5 | Smoke on Linux/WSL (user runs; costs money): `harness2-setup jb --substrate cc`, `harness2-check --bench jb --substrate cc`, then one task with `--split-file` + `--k 1`. Then docs. | one rollout delivered, trajectory renders, judge scores |
| W6 | Same smoke on native Windows (PowerShell 7). Then the classifier. | same as W5 on Windows |

---

## 7. Risks and open questions

| # | Risk | Mitigation |
|---|---|---|
| R1 | `login` auth cannot be isolated: user `~/.claude` (CLAUDE.md, plugins, skills) may leak into rollouts. | W0 verifies; contamination guard (§3.5); recommend `api_key` or `vertex` for real experiments. |
| R2 | Claude Code flags/events drift between versions. | Capability probe + cached caps; fixtures recorded from the real CLI in W0. |
| R3 | JobBench judge needs an OpenAI-compatible endpoint. | User decides: Vertex (current), or another OpenAI-compatible endpoint via `HARNESS2_JUDGE_BASE_URL`. Not changed by this plan. |
| R4 | `harness2-setup jb` still clones/patches upstream repos and runs `uv sync`; untested on Windows. | Covered by W6; fix only what blocks JobBench. |
| R5 | Hooks run through Git Bash on Windows; `python3` often missing there. | cc base harness has no hooks; prompts.py cc text says helpers run as `python scripts/<name>.py`. Verify in W6. |
| R6 | Fingerprints differ between OSes (path separator) before W1. | After W1 (`as_posix`) they match; do not mix pre-W1 Windows runs with Linux runs. |
| R7 | Cost: Opus/Sonnet executor runs on JobBench are expensive. | Smoke on one task first; set `--k 1`. |

## 8. Out of scope
LAB and WorkBuddy for `cc`; running `oc`/`cx` on Windows; changes to scoring, judge prompts, or
recursion logic; renaming anything that exists.
