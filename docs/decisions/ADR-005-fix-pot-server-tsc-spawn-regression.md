# ADR-005: Fix POT Server TSC Spawn Regression (KeyError: 'creationflags')

## Status
Accepted

## Date
2025-09-26

## Context
The POT server's `_run_tsc_compile` function uses `daemon_spawn_kwargs(use_no_window=False)` to spawn the TypeScript compiler (`tsc`) so that compiler output is visible in logs. 

On Windows, `daemon_spawn_kwargs(use_no_window=False)` calls `spawn_kwargs(False)` which returns an empty dict `{}`. The code then attempted:
```python
kw["creationflags"] |= CREATE_NEW_PROCESS_GROUP
```
This raised `KeyError: 'creationflags'` because the dict was empty, causing the TypeScript compilation to fail entirely. The POT server would fail to start, showing "server failed → check logs (F12)" in logs.

## Decision
Modified `daemon_spawn_kwargs` in `chzzktube/infra/platform.py` to use `kw.get("creationflags", 0)` to safely initialize the `creationflags` key before the bitwise OR operation:

```python
kw["creationflags"] = kw.get("creationflags", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
```

Added a comment explaining the pattern.

## Alternatives Considered

### Option 1: Initialize creationflags to 0 before spawning (Chosen)
- Pro: Minimal change, safe for all code paths
- Pro: No behavior change for existing callers
- Con: Slightly less explicit

### Option 2: Make spawn_kwargs return creationflags=0 when use_no_window=False
- Pro: More consistent API
- Con: Changes semantics for all callers; could affect callers that rely on empty dict

### Option 3: Add explicit check in pot_server.py before calling daemon_spawn_kwargs
- Pro: Localizes fix to caller
- Con: Scatters fix logic; caller shouldn't need to know internals

## Consequences
- Positive: TypeScript compilation now works on Windows; POT server starts correctly
- Positive: No behavior change for existing callers with `use_no_window=True`
- Negative: None — the fix is defensive and doesn't alter observable behavior for valid inputs

## Verification
- [x] Unit tests pass: `test_daemon_spawn_kwargs_use_no_window_false` and `test_daemon_spawn_kwargs_use_no_window_true`
- [x] POT server tests pass: `test_pot_server_timeout.py` (4 passed), `test_pot_manager.py` (10 passed)
- [x] Full test suite: 327 passed (excluding pre-existing failures in 3 test files)
- [x] Ruff lint: 0 errors (SILENT category 0, HIGH 0)

## Related Files
- `chzzktube/infra/platform.py` — Fixed `daemon_spawn_kwargs`
- `chzzktube/infra/pot_server.py` — Uses `daemon_spawn_kwargs(use_no_window=False)` for tsc compilation
- `tests/test_deps_bgutil_and_pot_fixes.py` — Unit tests for the fix

## Notes
This regression was introduced during a previous refactoring. The fix is defensive and ensures the `creationflags` key is always initialized before bitwise operations, regardless of the `use_no_window` parameter value.