# v3.9.0 리팩토링 작업 목록 (TDD + 점진적 구현)

> 원칙: 각 Task는 RED(실패 테스트)→GREEN(최소 구현)→REFACTOR 순서.
> 한 슬라이스 ≤100줄, focused 테스트 후 전체 테스트, smoke_test 통과 없이 커밋 금지 (§6).

> **진행 상태 (2026-09-23)**: Phase 0-1~4-1, 5-1 완료 (348 passed, smoke PASS, mirror 0/0).
> F12 선택지 B는 §5-33 기존 구현과 일치함을 확인 — 구현 불변, 테스트만 B로 단일화.

## Phase 0: 기준선 고정

### Task 0-1: 실패 3건 재현 파일
- [x] Test(RED): `tests/test_ffmpeg_archive_contract.py` 3건 실패 재현 확인
  (원인: 다운로드·SHA 검증 생략 주석 구간 → 미존재 tar 경로 전개 `[Errno 2]`).
- [x] 원인 기록: `_ensure_ffmpeg_macos` 누락 구간 + `_verify_ffmpeg` mock `env_extra` 시그니처 불일치.
- [x] 중복 기록: `_FFMPEG_BREW_API` 2회, `test_macos_bottle_missing_sha256_is_rejected` 2회.
- [x] Verify: 7 passed.

### Task 0-2: 워치독 주입 경로 확정
- [x] 판독: `DownloadWorker.extract()`가 `_download_watchdog`를 4종 alias
  (`_gate/_live/_analysis`)로 `DownloadContext`에 주입함 확인 → Phase 2 승격 불필요.

## Phase 1: P0 정합성 (RED→GREEN)

### Task 1-1: controller 중복 정의 제거 [TDD]
- [x] Test(RED): `tests/test_controller_no_duplicates.py` 신규 — 5개 메서드 1회 정의 계약.
- [x] Fix(GREEN): 앞쪽 데드 5종 삭제 (`state.update`/`_abandon_analyzer` 참조 포함).
- [x] Verify: focused + 전체 green.

### Task 1-2: macOS Bottle 다운로드·SHA 복원 [TDD]
- [x] Fix(GREEN): `_write_bottle_payload` 신규 — `_http_get` 다운로드 + SHA-256 강제 검증
  + `_safe_extract`→`_locate_binaries`→`_verify_ffmpeg(DYLD)`→`_atomic_install` 복원.
  호스트 승격(§5-32) 유지, evermeet 부활 없음 (§6 준수).
- [x] Refactor: `_FFMPEG_BREW_API` 중복 제거, 중복 테스트 삭제,
  mock `lambda path, env_extra=None` 시그니처 정합, SHA부재 테스트는
  호스트 승격 격리(`Path.is_file=False`)로 순수 bottle 판정 보존.
- [x] Verify: 7 passed → 전체 341+green.

### Checkpoint 1
- [x] 전체 green, P0 데드코드 0.

## Phase 2: 기존 todo 잔재 통합

### Task 2-1: 결함2 완료 확정 [TDD]
- [x] `tests/test_live_recorder.py` 논블로킹·취소 테스트 green 확인 (queue 타임아웃 방식 —
  주석의 `selectors` 용어와 구현 불일치는 용어 정리만 남음, 동작은 계약 충족).

### Task 2-2: 결함1 방침 전환 [TDD]
- [x] 빈 스텁 2건 → `TestNoManualClientChain` 3건 단언으로 교체
  (`_RETRY_CLIENTS==[]`, `client_chain`/`_RETRY_CLIENTS` 잔재 0, 순정 위임 주석 존재).

### Task 2-3: 결함3 단위 테스트 [TDD]
- [x] `tests/test_chzzk_auth.py` 신규 — 401/403→ChzzkAuthError, 500 통과,
  워커 매핑 소스 단언 (4 passed).

### Task 2-4: 결함5 주입 확정 [TDD]
- [x] Task 0-2에서 주입 확인 — 별도 수정 불필요 (기존 하트비트 테스트가 보호).

### Checkpoint 2
- [x] 구 todo 유효 항목 테스트 근거 확보, 결함1은 방침 전환으로 폐기·대체.

## Phase 3: F12 선택지 B 확정 반영 (§5-33)

### Task 3-1: 계약 테스트 단일화 [TDD]
- [x] 확인: §5-33이 이미 선택지 B와 동일 — 구현은 현행 유지(Thin Wrapper 금지 준수).
- [x] Fix(GREEN): `test_f12_full_buffer_keeps_progress_ticks`를
  `test_f12_buffer_snapshot_replaces_progress_ticks`(버퍼 길이 1)로 개명·수정 +
  `test_f12_full_history_keeps_every_tick`(dispatcher full_events 전량) 신규 분리.

### Checkpoint 3
- [x] 로그 계약 테스트 전부 green.

## Phase 4: 구조 분해 (전면 재수정 허용, 슬라이스 엄수)

### Task 4-1: 로그 미러 추출 [TDD]
- [x] `chzzktube/ui/log_mirror.py` (신규)로 `finalize_concise_progress`/`render_concise`/
  `mirror_event_full`/`mirror_full_log` 로직 통째 이전. MainWindow 4종은 호환 바인딩.
- [x] 버퍼 미보유 테스트 대역 호환 폴백 포함.
- [x] `sync_mirrors.py` MIRROR_MODULES에 신규 모듈 등록 (§1.1.2).
- [x] Verify: 로그/게이트/전체 green + smoke PASS.

### Task 4-2: 게이트·워치독 상태 추출 [TDD]
- [x] `chzzktube/control/gate_state.py` 신규 생성 — GateState 클래스 + 무장/해제/재시도 함수
- [x] MainWindow 위임 메서드(`_start_gate_watchdog`/`_stop_gate_watchdog`/`_arm_analysis_watchdog`/`_disarm_analysis_watchdog`/`_on_pot_work_tick`/`_on_gate_timeout`/`_maybe_retry_analysis`)를 gate_state 함수 위임으로 전환
- [x] 테스트 더미 재귀 버그 수정 (property → 직접 속성 + 캐시)
- [x] Verify: 352 passed + smoke PASS.

### Task 4-3: 파이프라인 분기 분리 [TDD]
- [x] `target_downloader.py` → `target_downloader/` 패키지로 분할
  - `utils.py`: 공통 상수/유틸리티/에러 분류
  - `options.py`: yt-dlp 옵션 빌더
  - `flatten.py`: 재생목록/채널 평탄화
  - `chzzk.py`: 치지직 VOD/클립/라이브 다운로드
  - `youtube_vod.py`: 유튜브 VOD 다운로드 (yt-dlp)
  - `youtube_live.py`: 유튜브 라이브/스트림링크 다운로드
  - `dispatch.py`: 메인 디스패처 (download_target)
  - `__init__.py`: 공개 API 재내보내기 (기존 import 호환)
- [x] 기존 import 경로 호환 유지 (`import chzzktube.pipeline.target_downloader as _td`)
- [x] `_format_selector` 원본 로직 복원 (`bv*+ba` 단일 포맷, tv 폴백 금지)
- [x] `_ensure_pot_server_ready` 원본 로직 복원 (POTManager.instance() 제거, L0/L1 인프라만 사용)
- [x] `_emit_error_log` 즉시 TUI 발행 금지 (failed_targets만 누적)
- [x] 테스트 업데이트 (경로 변경, 모킹 포인트 수정)
- [x] Verify: 352 passed + smoke PASS.

### Task 4-4: LogEvent deprecated 정리 [TDD]
- [x] `platform`/`spec` 필드 제거 + 호출부 통일.
- [x] Verify: 352 passed + smoke PASS.

### Checkpoint 4
- [x] 전체 green, 파일 책임 1문장 서술 가능.

## Phase 5: 성능·보안 (측정 기반만)

### Task 5-1: SpeedWindow deque화 [TDD]
- [x] list 재구성 → `deque` + `popleft` O(1) 상각. 속도 테스트 green.

### Task 5-2: 디스패처 과부하 계약 [TDD]
- [x] `tests/test_log_regressions.py::test_raw_bus_overflow_is_bounded_and_summarized_once`
  기존 보호 확인 (신규 추가 불필요).

### Task 5-3: 타임아웃·권한 일관화
- [x] `urllib` 타임아웃 기본값 문서화/고정 (`chzzktube.core` 상수화)
- [x] tmp 0o600 점검 (opener로 파일 생성 시 권한 고정)
- [x] Verify: 352 passed + smoke PASS + mirror 0/0.

### Task 5-4: 로그 인젝션 [TDD]
- [x] 구분자 깨짐 회귀 테스트 + 최소 정화.
- [x] Verify: 356 passed + smoke PASS + mirror 0/0.

### Checkpoint 5
- [x] 성능·보안 변경 테스트 보호됨 (5-1/5-2 기준).

## Phase 6: 검증·버전업

### Task 6-1: 전체 검증
- [x] `python -m pytest tests/ -q` → **348 passed, 0 failed**
- [x] `python -m compileall chzzktube` → OK
- [x] `QT_QPA_PLATFORM=offscreen python smoke_test.py` → PASS
- [x] `python sync_mirrors.py --check` → changed 0 / missing 0 (53 modules)
- [x] `git diff --check` → OK

### Task 6-2: v3.9.0 버전업 (§1.1.2 순서 엄수)
- [x] `config._APP_VERSION=v3.9.0` → pyproject → uv.lock → HANDOVER → CHANGELOG → README.
  (실제 버전 일변경은 리팩토링 전체 완료 시점에 수행 — Task 4-2~5-4 잔여분 완료 후.)
- [x] `python sync_mirrors.py` 재생성.
- [x] 정합성 5조건 확인.

### Checkpoint 6 (최종)
- [x] 실패 0, 미러 0, 문서·버전 일치.
