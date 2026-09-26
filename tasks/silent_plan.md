# SILENT 199건 작업 계획 (2026-09-26)

> 전수 리포트: `tasks/lint_report.md` / HIGH 일지: `tasks/high_fixes_log.md`
> 실패 분석: `tasks/test_failures_v38_report.md` (수정 없이 기록 유지)

## 현황: 199건 = BLE001 148 + S110 47 + S112 3 + TRY203 1

## 파일별 분포 (상위)

| 파일 | 건수 |
|---|---:|
| `infra/pot_server.py` | 36 |
| `infra/updater.py` | 24 |
| `infra/cleanup.py` | 18 |
| `core/raw_log.py` | 14 |
| `infra/components.py` | 14 |
| `infra/node_provider.py` | 10 |

## 처리 패턴 (HIGH에서 확립)

1. `except Exception as e: + raw_log.raw(...)` 이미 로깅 중 → `as e` 유지 + `# noqa: BLE001 — <사유>` (동작 불변)
2. 무음 `except Exception: pass` (S110) → `_warn`/`log_f12_net` 1줄 진단 (platform.py 패턴)
3. 좁힐 수 있는 것은 구체 예외로 (`OSError`, `queue.Empty` 등)

## 레이어 원칙

- `chzzktube/core/*`, `infra/*` (raw_log 접근 가능): `raw_log.raw()` 진단
- `infra/platform.py` (stdlib-only 바보 모듈): `_warn()` stderr 진단
- 테스트 파일: SILENT 대상 아님 (이번 작업 제외)

## 순서

1. pot_server.py (36) — 파일 상단 `log_f12_net` 이미 import됨
2. updater.py (24)
3. cleanup.py (18)
4. raw_log.py (14) — 자기 자신 로깅 불가 → stderr/`log_history` 폴백 검토
5. components.py (14)
6. node_provider.py (10)
7. 나머지 자잘한 파일들
