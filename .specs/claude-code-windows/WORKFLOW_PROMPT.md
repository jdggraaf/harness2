Use a workflow to implement `.specs/claude-code-windows/PLAN.md`. Load the `workflow-authoring` skill first.

## Before the workflow (main session)
1. Create branch `windows-support` from the branch that holds PLAN.md. Working tree must be clean.
2. Read PLAN.md fully. It is the source of truth; its section 2 facts were verified against the code.
3. Run wave W0 yourself (it needs the real `claude` CLI and is cheap): record the findings PLAN.md asks for
   and update PLAN.md §3.3/§3.5 if the installed CLI differs. Show me the W0 findings and wait for my OK.

## Workflow (waves W1–W4, strictly sequential)
Per wave: implementer (RED tests first, show them failing, then GREEN) -> reviewer -> at most one fixer round.
Every agent gets: the PLAN.md path, its wave, the gate command
`python -m unittest discover -s tests -v && ruff check harness2 tests`, and the rule
"only touch files listed for this wave in PLAN.md §4".

Implementer/fixer returns: `{ gate_passed, gate_output_tail, files_changed, notes }`
Reviewer returns: `{ verdict: "approve"|"fix", blocking: [{file, line, problem, fix}], non_blocking }`
Abort and report if a gate still fails after the fix round. After each approved wave: commit
`cc-windows: W<n> <summary>`.

| Wave | Implementer | Reviewer | Reviewer focus |
|---|---|---|---|
| W1 portability | sonnet | opus | POSIX behaviour byte-identical; Windows ladder; `as_posix` everywhere tree keys are built |
| W2 substrate core | opus | opus | Protocol conformance, LF/UTF-8, `.claude/settings.json`, sub_agents conversion, grammar matches codex, prompts.py diff only changes paths |
| W3 preflight/auth/config | sonnet | sonnet | `vertex` default reproduces today's proposer env exactly; `login` never sets `CLAUDE_CONFIG_DIR`; actionable error messages |
| W4 JobBench wiring | sonnet | opus | Whole-branch `git diff main...HEAD`: launcher matches the bash runner (prompt text, index columns, exit codes), nothing outside §4 touched, no weakened tests |

Fixer uses the implementer's model. Model rationale: opus for design-heavy work and risky reviews,
sonnet for well-specified TDD work.

## After the workflow (main session)
1. Summarise per wave: gate, verdict, commits.
2. Do not run W5/W6 smoke tests: they cost money. Give me the exact commands for one task on
   Linux/WSL (W5) and on native Windows PowerShell 7 (W6), including the env vars from PLAN.md §3.1.
3. Push only after I confirm.
