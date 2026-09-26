# HIGH 34건 작업 일지 (2026-09-26)

> 전수 리포트: `tasks/lint_report.md` (생성 스크립트: `tasks/gen_lint_report.py`)
> 실패 분석: `tasks/test_failures_v38_report.md`

## 요약

| 룰 | 건수 | 처리 |
|---|---:|---|
| F823 | 1 | 수정 — 진짜 버그 (아래 증거) |
| F811 | 8 | 제거 — 중복 import/함수/클래스 |
| F841 | 7 | 제거 — 죽은 할당 6 + 테스트 결함 1 |
| PLW1510 | 11 | `check=False` 명시 — 동작 불변 |
| RUF012 | 4 | `ClassVar` 명시 — `[]` 유지 |
| DTZ005 | 1 | `astimezone()` |
| PLC0206 | 1 | `.items()` 순회 |
| SIM115 | 1 | `noqa` + 사유 (자식 프로세스 공유 핸들) |

검증: HIGH 셀렉터 전체 `All checks passed`, 영향 테스트 11개 파일 133 passed,
전체(기존 실패 3파일 제외) 327 passed. 전체 린트 729 → 688건.

## F823 실측 증거 (live_recorder.py `_drain_stderr`)

바이트코드에서 `raw_log`가 지역 변수로 바인딩됨을 확인:

```
96  LOAD_FAST_CHECK  2 (raw_log)   ← 235줄 참조
250 STORE_FAST       2 (raw_log)   ← 242줄 except 블록 (실패 경로에서만 실행)
```

`LOAD_FAST_CHECK`는 미할당 시 `UnboundLocalError` → ffmpeg stderr 로그 매번 유실,
스레드 조용히 사망. 지역 import 2곳 제거 → 모듈 전역 사용으로 통일.
검증: 지역 변수에서 `raw_log` 완전 제거 + `test_live_recorder.py` 13 passed.

## 수정 파일 목록

- `chzzktube/pipeline/live_recorder.py` — F823 (지역 import 제거 ×2)
- `chzzktube/pipeline/target_downloader/youtube_vod.py` — F811 (중복 import 2줄, 지역 `import time`)
- `chzzktube/pipeline/target_downloader/chzzk.py` — F811 (지역 `import chzzk_api`)
- `tests/test_v38_contracts.py` — F811 (중복 테스트 3 + 중복 클래스 1) → 38→40 passed
- `chzzktube/control/pot_manager.py` — F841 (`as ff_ex` 제거)
- `chzzktube/infra/updater.py` — F841 (`pypi_name`) + PLW1510 ×5
- `chzzktube/infra/yt_dlp_binary.py` — F841 (`machine`) + PLW1510 ×1
- `chzzktube/pipeline/progress_emitter.py` — F841 (`title = ""`)
- `chzzktube/pipeline/target_downloader/flatten.py` — F841 (`url_short`)
- `chzzktube/workers/analyze_worker.py` — F841 (`configured`→주석) + RUF012 (`ClassVar`)
- `tests/test_download_pipeline.py` — F841 (죽은 `ctx` 제거 + 테스트명 정정)
- `tests/test_analysis_retry.py` — RUF012 (`ClassVar` ×3)
- `tests/test_progress_integration.py` — RUF012 (`ClassVar` ×2)
- `chzzktube/infra/components.py` — PLW1510 ×1
- `chzzktube/infra/node_provider.py` — PLW1510 ×1
- `chzzktube/infra/pot_server.py` — PLW1510 ×1 + SIM115 (noqa + 사유)
- `chzzktube/infra/provisioning/verifier.py` — PLW1510 ×1
- `tests/test_window_initialization.py` — PLW1510 ×1
- `chzzktube/core/log_history.py` — DTZ005 (`astimezone()`)
- `chzzktube/core/log_emitter.py` — PLC0206 (`.items()`)

## 테스트 결함으로 열어둔 항목 (수정 없이 기록)

상세: `tasks/test_failures_v38_report.md` T1~T6.
