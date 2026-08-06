---
id: WP1D-SESSION-TEARDOWN-0806
title: Normal formal Runner and asyncio shutdown
status: CLOSED
risk: HIGH
owner: Codex
created_at: 2026-08-06T13:12:22+08:00
updated_at: 2026-08-06T13:41:10+08:00
allowed_files:
  - coordination/active/WP1D-SESSION-TEARDOWN-0806.md
  - jiuwenswarm/evaluation/run_multi_agent.py
  - jiuwenswarm/tests/unit_tests/quant/test_run_multi_agent_validator.py
acceptance:
  - Formal teardown calls session stop, stream close and Runner.stop in bounded order, preserves every failure as evidence, main returns a normal exit code without os._exit, and focused success/timeout/failure tests plus Ruff, pycompile, scope-check and diff-check pass.
---

## Goal

Remove forced process termination and make the standalone formal validator stop the session, stream, global Runner resources and asyncio loop through bounded normal return.

## Non-goals

- Do not change strategy, roles, RPC order, resource gates, Provider behavior or
  TeamManager lifecycle semantics used by the long-running application.
- Do not cancel arbitrary event-loop tasks from the standalone validator.
- Do not claim normal Windows process exit until a real formal run proves it.

## Invariants

- Preserve AGENTS.md and project safety contracts.

## Locate brief

- Scout confidence 0.94: the per-session stop already releases the formal team,
  A2X transports and local registries, but the standalone script never calls
  public `Runner.stop()`. In locked openJiuwen 0.1.15.post3, that call releases
  the resource manager and closes/cancels the Runner root task group in `finally`.
- Add one bounded teardown helper in `run_multi_agent.py`; test ordered cleanup,
  timeouts, ordinary exceptions, false Runner-stop results and normal exit-code
  return. `team_manager.py` is read-only evidence, not a write target.

## Implementation evidence

- The formal `finally` path now runs bounded `team_session_stop -> stream_close
  -> Runner.stop` cleanup, continues after ordinary failures, and serializes
  per-step results into `runtime_teardown`. A false TeamManager result means no
  tracked wrapper runtime and is not invented as a failure; a false global
  Runner stop fails formal validation.
- Teardown failure is part of `validation_passed`, so a business-complete 8/8
  trace cannot become an accepted summary if global runtime cleanup failed.
- `main()` returns `0/1` and the module guard raises `SystemExit` normally;
  `os._exit()` is absent and no arbitrary loop-task cancellation was added.
- Each step uses `asyncio.wait` over an explicitly retained task, so the hard
  deadline records a failure and proceeds even if that cleanup coroutine
  suppresses cancellation; late completion/exception is observed and no
  unrelated event-loop task is touched.
- The public CLI now supervises one PID-bound worker process for 720 seconds.
  Healthy runs still return normally through `asyncio.run`; if a concrete
  upstream cleanup violates cancellation forever, that worker and its recursive
  descendants are terminated, the parent returns failure, and no successful
  formal claim is possible. Worker mode cannot be selected with a public CLI
  argument; it requires a parent-PID marker that matches the live supervisor.
- 44/44 focused validator/resource/aggregator tests, Ruff, pycompile, frozen
  scope-check and `git diff --check` pass locally.

## Review evidence

- Independent Critic ACCEPT on frozen diff
  `2d5fad64382712fa17033aa9183fcd2bb5193af853f03bd3db0e0bdfdd36d4b3`;
  P0/P1/P2/P3 are empty. Five adversarial closure regressions passed.
- Local verification: 44 focused tests passed. The broader quant suite reached
  586 passed and 1 skipped; its 10 failures are the known fail-closed dependency
  on absent ignored historical `WP1B-EVALUATION-0804/review.json`. No historical
  evidence was created or overwritten.
- Windows/model-backed formal normal-exit proof remains an explicit external
  acceptance gate; this Mac close certifies code and deterministic tests only.

## Progress

- 2026-08-06T13:12:22+08:00 `DRAFT`: Task created.
- 2026-08-06T13:15:37+08:00 `LOCATED`: Scout location validated at confidence 0.94; Planner accepted a three-file validator/helper/test boundary and confirmed Runner.stop closes the locked runtime root task group.
- 2026-08-06T13:15:37+08:00 `LOCATED`: Write scope approved by Planner.
- 2026-08-06T13:15:42+08:00 `READY`: Baseline frozen; implementation may start.
- 2026-08-06T13:18:49+08:00 `IMPLEMENTED`: Builder added bounded ordered global Runner teardown, fail-closed summary evidence and normal SystemExit return; 37 focused tests and static/scope checks pass.
- 2026-08-06T13:20:00+08:00 `REVIEWED/REJECT`: Independent Critic found
  that `asyncio.wait_for` waits for cancellation completion and therefore did
  not provide the claimed hard deadline.
- 2026-08-06T13:25:10+08:00 `IMPLEMENTED`: Replaced `wait_for` with retained,
  observed teardown tasks and deadline-only `asyncio.wait`; a
  cancellation-suppressing counterexample now proves later cleanup proceeds.
- 2026-08-06T13:27:00+08:00 `REVIEWED/REJECT`: Closure review confirmed later
  cleanup proceeds but showed the retained task can still block
  `asyncio.run()` final cancellation forever.
- 2026-08-06T13:29:30+08:00 `IMPLEMENTED`: Added a task-scoped worker
  supervisor. The healthy worker exits normally; the 720-second outer watchdog
  terminates only a non-returning worker and fails the run.
- 2026-08-06T13:31:30+08:00 `REVIEWED/REJECT`: Independent Critic found the
  internal worker CLI flag could bypass the watchdog, direct-PID termination
  could orphan descendants, and final kill timeout was not caught.
- 2026-08-06T13:36:30+08:00 `IMPLEMENTED`: Removed the worker CLI flag, bound
  worker authority to the supervisor's live parent PID, added recursive child
  termination and bounded final kill handling, and covered both paths with
  deterministic regressions; 43 focused tests and static/scope checks pass.
- 2026-08-06T13:37:50+08:00 `REVIEWED/REJECT`: Closure review found a
  `psutil.Error` during the initial descendant lookup could escape before the
  direct worker was terminated; it also identified a one-snapshot child-spawn
  race.
- 2026-08-06T13:39:20+08:00 `IMPLEMENTED`: Process inspection failure is now
  isolated from mandatory direct-parent termination, descendants are scanned
  again after signaling the parent, and a deterministic AccessDenied-style
  regression proves the supervisor still returns failure; 44 focused tests
  pass.
- 2026-08-06T13:40:40+08:00 `REVIEWED`: Independent Critic accepted the frozen
  implementation diff with P0-P3 empty after five focused adversarial tests.
- 2026-08-06T13:41:10+08:00 `VERIFIED/CLOSED`: Planner verified scope, hashes,
  44 focused passes, broad-suite known evidence-only failures and retained
  Windows formal gate; no push and no historical evidence mutation.
