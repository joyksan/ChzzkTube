# ChzzkTube GUI 대규모 리팩토링 원자적 작업 목록 (5축 90점+ 달성)

## Phase 1: Foundation — 크리티컬 버그 수정 및 안정성 확보

### Task 1.1: `main_window.py` _platform_of_url 복구 및 closeEvent Dataclass 호출 수정
**Description:** `main_window.py`의 Line 390에서 오기입된 `_on_analysis_timeout` 메서드명을 `_platform_of_url(self)`로 변경하여 분석 완료 시 발생하는 `AttributeError`를 해결하고, `closeEvent`에서 불변 데이터클래스 `self.ctrl.state`에 대해 `.get()`을 호출하던 오류를 `self.ctrl.running` 프로퍼티 조회로 수정한다.

**Acceptance criteria:**
- [ ] `MainWindow._platform_of_url` 메서드가 정상 존재하고 올바른 플랫폼 태그("YT", "CHZ" 등)를 반환한다.
- [ ] `MainWindow.closeEvent` 실행 시 `AttributeError: 'SessionState' object has no attribute 'get'` 예외가 발생하지 않는다.
- [ ] 분석 완료(`stop_analysis_anim`) 및 타임아웃(`_on_analysis_timeout`) 처리 시 크래시 없이 로그가 발행된다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_window_initialization.py tests/test_analysis_timeout.py`
- [ ] Manual check: Python에서 `hasattr(MainWindow, '_platform_of_url')` 검증 및 `MainWindow().closeEvent()` 모의 호출 성공 확인

**Dependencies:** None
**Files likely touched:**
- `chzzktube/ui/main_window.py`
**Estimated scope:** S (1 file, ~15m)

---

### Task 1.2: `startup_coordinator.py` NameError: raw_log 수정 및 실패 로깅 방어
**Description:** `startup_coordinator.py`의 모듈 레벨에 `chzzktube.core.raw_log as raw_log`를 임포트하여 `report_upgrade` 및 `report_pot`에서 실패(`ok=False`) 처리 시 발생하는 `NameError: name 'raw_log' is not defined` 예외를 제거하고, 기동 시퀀스 오류가 GUI 메인 루프에 안전하게 전달되도록 보장한다.

**Acceptance criteria:**
- [ ] `coord.report_upgrade(False, "fail")` 호출 시 `NameError` 없이 에러 로그가 버스에 전송된다.
- [ ] `coord.report_pot(False, "fail")` 호출 시 `NameError` 없이 표준 에러 이벤트가 생성된다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_coordinator.py tests/test_startup_coordinator.py`
- [ ] Manual check: `python -c "from chzzktube.control.startup_coordinator import StartupCoordinator; from chzzktube.control.pot_manager import POTManager; c = StartupCoordinator(POTManager()); c.report_upgrade(False, 'err'); c.report_pot(False, 'err')"` 성공

**Dependencies:** None
**Files likely touched:**
- `chzzktube/control/startup_coordinator.py`
**Estimated scope:** XS (1 file, ~10m)

---

### Task 1.3: `downloader.py` _canceled 신호 동기화 및 skip 플래그 리셋 결함 수정
**Description:** `DownloadWorker`가 `DownloadContext`로 상태를 전달할 때 매번 새 딕셔너리를 반환하던 프로퍼티 구조를 단일 공유 참조 딕셔너리(`self._shared_state`)로 개편하여 `canceled_signal` 수신 시 파이프라인(`ctx.state['canceled']`)에 즉시 반영되도록 하고, 루프 내 `skip` 플래그 초기화 시 인스턴스 변수(`self._skip`)도 함께 `False`로 리셋하여 재생목록의 모든 영상이 연쇄 스킵되는 버그를 수정한다.

**Acceptance criteria:**
- [ ] `DownloadWorker._on_canceled(True)` 호출 시 `ctx.state['canceled']`가 즉각 `True`로 동기화된다.
- [ ] 재생목록 다운로드 중 첫 번째 항목을 스킵했을 때, 두 번째 항목이 연속으로 자동 스킵되지 않고 정상 처리된다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_download_pipeline.py tests/test_context_lifecycle.py`
- [ ] Manual check: `DownloadWorker` 단위 테스트에서 cancel/skip 시그널 수신 후 컨텍스트 상태 무결성 검증

**Dependencies:** None
**Files likely touched:**
- `chzzktube/workers/downloader.py`
- `chzzktube/control/controller.py`
**Estimated scope:** S (2 files, ~20m)

---

### Task 1.4: `main_window.py` 9개 중복 메서드 제거, `dialogs.py` 데드코드 정리 및 UTF-8 BOM 소거
**Description:** `main_window.py` 내부에 중복 선언된 9개의 워치독/상태 관리 메서드(`_start_gate_watchdog`, `_stop_gate_watchdog`, `_on_pot_work_tick`, `_on_gate_timeout`, `_arm_analysis_watchdog`, `_disarm_analysis_watchdog`, `_on_analysis_timeout`, `get_current_app_state`, `_finalize_concise_progress`)를 정리하고, `dialogs.py`의 쿠키 선택 중복 코드를 제거하며, Python 3.14 호환성을 위해 코어 파일 4개의 UTF-8 BOM(`\ufeff`)을 완전히 제거한다.

**Acceptance criteria:**
- [ ] `MainWindow` 클래스 내에 중복 정의된 메서드가 0개이다.
- [ ] `dialogs.py`의 `CookieSelectDialog.on_select` 내 중복 accept 호출이 제거된다.
- [ ] `components.py`, `cookies.py`, `media.py`, `raw_log.py`의 첫 바이트에 `\ufeff`가 존재하지 않는다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_window_initialization.py`
- [ ] AST parse check: 모든 파이썬 파일이 표준 UTF-8로 `ast.parse` 오류 없이 로드되는지 확인

**Dependencies:** Tasks 1.1, 1.2
**Files likely touched:**
- `chzzktube/ui/main_window.py`
- `chzzktube/ui/dialogs.py`
- `chzzktube/infra/components.py`
- `chzzktube/core/cookies.py`
- `chzzktube/core/media.py`
- `chzzktube/core/raw_log.py`
**Estimated scope:** M (6 files, ~25m)

---

## Checkpoint 1: Foundation 안정화 검증
- [ ] 모든 크리티컬 런타임 크래시(`AttributeError`, `NameError`) 0건 확인
- [ ] `pytest tests/` 핵심 테스트 스위트 정상 통과
- [ ] 파이썬 3.12/3.14 정적 파싱 및 문법 검사 통과

---

## Phase 2: Performance — 콘솔 렌더링 병목 및 블로킹 I/O 해소

### Task 2.1: `log_console.py` 타깃형 단일 블록 치환 (Targeted In-Place Mutation) 구현
**Description:** `ConciseLogConsole`의 `_update_progress_line` 호출 시 문서 전체를 클리어하고 수천 개 항목을 다시 루프 돌던 `self.reflow()` 호출을 폐기하고, `VerboseLogWindow`와 동일하게 `QTextDocument.findBlockByNumber()` 및 `QTextCursor`를 활용하여 대상 블록 텍스트만 O(1)로 치환하도록 개선한다.

**Acceptance criteria:**
- [ ] `_update_progress_line()` 호출 시 `self.te.clear()` 또는 전체 버퍼 루프가 호출되지 않는다.
- [ ] 진행률 업데이트 시 기존 로그의 스크롤 위치가 튀지 않고 해당 진행 라인만 제자리에서 부드럽게 갱신된다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_log_console.py`
- [ ] Manual check: 4,000줄 로그 누적 상태에서 100회 연속 진행률 갱신 시 CPU 점유율 및 지연 시간 5ms 이하 확인

**Dependencies:** Checkpoint 1
**Files likely touched:**
- `chzzktube/ui/log_console.py`
- `chzzktube/ui/log_mirror.py`
**Estimated scope:** M (2 files, ~30m)

---

### Task 2.2: 메인 스레드 동기 `server_ping` 비동기화 및 분석기 `wait(2000)` 블로킹 제거
**Description:** `main_window.py`의 `_wait_pot_if_needed`에서 GUI 스레드를 800ms 동안 멈추게 하던 `server_ping()` 동기 호출을 비차단 방식으로 전환하고, `MediaController._terminate_analyzer()`에서 2초간 GUI를 얼리던 `wait(2000)` 및 `terminate()` 강제 중단을 비동기 좀비 워커 자연 종료 수거 패턴으로 대체한다.

**Acceptance criteria:**
- [ ] POT 서버 확인 시 GUI 메인 스레드 프리징(이벤트 루프 차단)이 발생하지 않는다.
- [ ] URL 연속 입력 시 이전 `AnalyzeWorker`가 메인 스레드를 2초간 멈추지 않고 비동기 폐기된다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_analysis_retry.py tests/test_pot_server_timeout.py`
- [ ] Manual check: URL 빠르게 연속 변경 시 GUI 입력창 타이핑 지연 0ms 확인

**Dependencies:** Checkpoint 1
**Files likely touched:**
- `chzzktube/ui/main_window.py`
- `chzzktube/control/controller.py`
**Estimated scope:** S (2 files, ~25m)

---

### Task 2.3: 고주파 진행률 틱 50ms 쓰로틀링 및 버퍼 메모리 최적화
**Description:** 초당 수십 건씩 유입되는 다운로드 틱 이벤트를 최대 20Hz(50ms)로 쓰로틀링하여 GUI 렌더링 부하를 억제하고, `_buffer`의 진행 라인 인덱스 참조 테이블(`_progress_lines`)이 누수 없이 완료 시점에 즉각 정리되도록 보강한다.

**Acceptance criteria:**
- [ ] 1초에 100건 이상의 틱이 유입되어도 GUI에는 최대 20회의 렌더 이벤트만 전달된다.
- [ ] 다운로드 완료 시 `_progress_lines` 딕셔너리가 빈 상태로 정상 환원된다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_progress_integration.py`
- [ ] Bench check: 고속 다운로드 시뮬레이션 시 UI 프레임 드랍 0회 달성

**Dependencies:** Task 2.1
**Files likely touched:**
- `chzzktube/ui/log_console.py`
- `chzzktube/ui/progress_bar.py`
**Estimated scope:** S (2 files, ~20m)

---

## Checkpoint 2: Performance 렌더링 최적화 검증
- [ ] 진행률 업데이트 시 `reflow()` 호출 0건 확인
- [ ] 다운로드 틱 폭주 시 GUI 60fps 유지 및 반응성 확인
- [ ] 전체 pytest 통과

---

## Phase 3: Architecture — MainWindow 모듈 분해 및 상태 머신 단일화

### Task 3.1: 상단 경로/설정/로그 바 분리 (`HeaderBarWidget`)
**Description:** `main_window.py`에 강결합되어 있던 Layer 1 구성요소(다운로드 경로 표시, 폴더 변경/열기, Full Log, Settings 버튼)를 독립 위젯 `chzzktube/ui/components/header_bar.py`로 분리하고 Qt Signal을 통해 MainWindow와 느슨하게 결합한다.

**Acceptance criteria:**
- [ ] `HeaderBarWidget`이 자체 레이아웃과 버튼들을 소유하며 `path_changed`, `settings_requested`, `log_requested` 시그널을 발행한다.
- [ ] `MainWindow.setup_ui`에서 70줄 이상의 Layer 1 코드가 제거된다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_ui_startup.py`
- [ ] Component test: `HeaderBarWidget` 단독 인스턴스화 및 시그널 발행 검증

**Dependencies:** Checkpoint 2
**Files likely touched:**
- `chzzktube/ui/components/header_bar.py` (신규)
- `chzzktube/ui/components/__init__.py`
- `chzzktube/ui/main_window.py`
**Estimated scope:** M (3 files, ~25m)

---

### Task 3.2: URL 입력 및 액션 바 분리 (`ActionBarWidget`)
**Description:** Layer 2 구성요소(프롬프트 라벨, `url_input`, TXT 로드, ENTER/ESC 액션 버튼 및 입력 디바운스 타이머)를 `chzzktube/ui/components/action_bar.py`로 캡슐화하여 드래그앤드롭 및 키 입력 이벤트를 전담하도록 분리한다.

**Acceptance criteria:**
- [ ] `ActionBarWidget`이 URL 입력 검증, 디바운스 타이머, 드래그앤드롭 처리를 독립적으로 수행한다.
- [ ] 상태 전이(`IDLE`, `RUNNING`, `PICKING`)에 따른 버튼 활성화/텍스트 변경 로직이 캡슐화된다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_url_gate.py`
- [ ] Component test: `ActionBarWidget` 입력 이벤트 및 다운로드 시작 시그널 검증

**Dependencies:** Task 3.1
**Files likely touched:**
- `chzzktube/ui/components/action_bar.py` (신규)
- `chzzktube/ui/main_window.py`
**Estimated scope:** M (2 files, ~30m)

---

### Task 3.3: 상태 머신 일원화 (`AppState` Enum 도입 및 보일러플레이트 제거)
**Description:** 문자열로 흩어져 있던 상태(`"IDLE"`, `"RUNNING"`, `"STARTUP"`, `"ANALYZING"`, `"PICKING"`)를 단일 `AppState(str, Enum)`으로 정의하고, `MainWindow`에 80줄 이상 누적된 `GateState` 위임 프로퍼티들을 정리하여 상태 소유권을 명확히 한다.

**Acceptance criteria:**
- [ ] 모든 상태 판정이 `AppState` Enum을 통해 타입 안전하게 이루어진다.
- [ ] `MainWindow`의 불필요한 게이트 프로퍼티 게터/세터가 정리되고 `gate_state` 모듈과의 결합도가 낮아진다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_gate_state.py tests/test_analyze_state.py`

**Dependencies:** Task 3.2
**Files likely touched:**
- `chzzktube/control/gate_state.py`
- `chzzktube/control/controller.py`
- `chzzktube/ui/main_window.py`
**Estimated scope:** S (3 files, ~20m)

---

### Task 3.4: `main_window.py` 슬림 오케스트레이터 재조립 (< 400 lines)
**Description:** 분리된 `HeaderBarWidget`, `ActionBarWidget`, `ConciseLogConsole`을 조립하는 루트 창으로 `MainWindow`를 재구성하여 코드 길이를 기존 1,797라인에서 400라인 미만으로 75% 이상 감축한다.

**Acceptance criteria:**
- [ ] `main_window.py`의 라인 수가 450줄 이하로 축소된다.
- [ ] 기존 기능(단축키, 다이얼로그 연동, 워치독 감시, 종료 시퀀스)이 100% 정상 작동한다.

**Verification:**
- [ ] Tests pass: `pytest tests/` 전체 테스트 스위트 통과
- [ ] Line count check: `wc -l chzzktube/ui/main_window.py` <= 450 lines 확인

**Dependencies:** Tasks 3.1, 3.2, 3.3
**Files likely touched:**
- `chzzktube/ui/main_window.py`
**Estimated scope:** M (1 file, ~30m)

---

## Checkpoint 3: Architecture 모듈화 및 회귀 검증
- [ ] UI 컴포넌트(`HeaderBar`, `ActionBar`, `Console`)의 명확한 SRP 분리 확인
- [ ] `main_window.py` 400라인 이하 슬림화 달성
- [ ] 기존 360+ 테스트 전체 패스 유지

---

## Phase 4: Robustness — 반응형 HiDPI 다이얼로그 및 입력 예외 방어

### Task 4.1: 7개 모달 다이얼로그의 `setFixedSize` 제거 및 반응형 레이아웃 전환
**Description:** `ExitConfirmDialog`, `DepsProvisioningDialog`, `TuiNoticeDialog`, `ActionCountdownDialog`, `CookieSelectDialog`, `CookieViewerDialog`, `SettingsDialog`의 하드코딩된 `setFixedSize()`를 제거하고, `setMinimumSize()`와 레이아웃 크기 제약 조건을 적용하여 HiDPI 배율(125%~200%)에서도 폰트 및 버튼 잘림이 없도록 반응형으로 개선한다.

**Acceptance criteria:**
- [ ] 모든 다이얼로그에서 `setFixedSize` 호출이 0개이다.
- [ ] 시스템 폰트 크기 변경이나 150%/200% 디스플레이 배율 환경에서 텍스트가 잘리지 않는다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_dialog_notice.py`
- [ ] Manual check: 각 다이얼로그의 내용물에 맞춰 크기가 자연스럽게 늘어나는지 검증

**Dependencies:** Checkpoint 3
**Files likely touched:**
- `chzzktube/ui/dialogs.py`
**Estimated scope:** M (1 file, ~25m)

---

### Task 4.2: `SettingsDialog` 258라인 UI 조립부의 섹션별 모듈 빌더 분할
**Description:** `SettingsDialog.init_ui()`의 258줄 단일 절차형 코드를 5대 기능 영역(`_build_format_section`, `_build_cookie_section`, `_build_options_section`, `_build_automation_section`, `_build_template_section`)으로 분할하여 가독성과 유지보수성을 극대화한다.

**Acceptance criteria:**
- [ ] `SettingsDialog.init_ui()` 함수가 30줄 이내로 간결해진다.
- [ ] 각 설정 영역이 독립적인 섹션 빌더 메서드로 캡슐화된다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_dialog_notice.py`
- [ ] UI check: 설정창의 모든 체크박스/콤보박스 설정 저장 및 복원이 정상 작동

**Dependencies:** Task 4.1
**Files likely touched:**
- `chzzktube/ui/dialogs.py`
**Estimated scope:** S (1 file, ~20m)

---

### Task 4.3: URL 입력 실시간 유효성 검증 및 예외 바운더리 강화
**Description:** 타이핑 도중 불필요한 `ANAL FAIL` 로그가 남발되던 문제를 방지하기 위해 `ActionBarWidget`에 실시간 정규식 사전 검증을 적용하고, 검증 실패 시 입력창 하단 테두리를 시각적으로 피드백(Soft Warning)하는 스마트 밸리데이션을 구축한다.

**Acceptance criteria:**
- [ ] 타이핑 도중 단순 문자열 입력 시 백그라운드 분석기가 오발화되지 않는다.
- [ ] 유효한 URL 패턴 진입 시에만 디바운스 타이머가 점화된다.

**Verification:**
- [ ] Tests pass: `pytest tests/test_url_gate.py`
- [ ] Manual check: 비URL 타이핑 시 무의미한 에러 로그 미발생 확인

**Dependencies:** Task 3.2
**Files likely touched:**
- `chzzktube/ui/components/action_bar.py`
- `chzzktube/control/controller.py`
**Estimated scope:** S (2 files, ~20m)

---

## Checkpoint 4: Robustness UI/UX 안정성 검증
- [ ] 다이얼로그 HiDPI 반응형 레이아웃 정상 동작 확인
- [ ] 입력값 실시간 검증 및 예외 바운더리 동작 확인
- [ ] 전체 테스트 통과

---

## Phase 5: Maintainability — 클린 코드, 타입 완비 및 90+ 게이트 감사

### Task 5.1: `theme.py` 스타일 충돌 정리 및 하드코딩 색상 시맨틱 토큰화
**Description:** `theme.py`에서 중복 및 덮어쓰기되던 스타일 상수(`BTN_EXIT_DANGER_QSS`, `TE_CONTENT_QSS`, `DLG_GHOST_BTN_QSS`)를 단일화하고, 소스 코드 곳곳에 `#4ec9b0`, `#1a1a1a` 등으로 하드코딩된 색상 리터럴을 `theme.py`의 시맨틱 토큰으로 일괄 치환한다.

**Acceptance criteria:**
- [ ] `theme.py` 내 동일 변수 재선언/덮어쓰기가 0개이다.
- [ ] UI 코드 내 인라인 하드코딩 색상 문자열이 제거되고 테마 상수를 참조한다.

**Verification:**
- [ ] Style check: `theme.py` 중복 심볼 검사 스크립트 통과
- [ ] UI visual test: 메인 화면 및 다이얼로그 테마 깨짐 없음 확인

**Dependencies:** Checkpoint 4
**Files likely touched:**
- `chzzktube/ui/theme.py`
- `chzzktube/ui/dialogs.py`
- `chzzktube/ui/components/*.py`
**Estimated scope:** S (3 files, ~20m)

---

### Task 5.2: GUI/Control 계층 전수 Type Hints (`mypy`/`pyright` 무결성 달성)
**Description:** `MainWindow`, `ActionBarWidget`, `HeaderBarWidget`, `MediaController`, `StartupCoordinator`, `ConciseLogConsole`의 모든 공용 메서드 및 시그널에 엄격한 Python 3.12+ 타입 힌트(`Callable`, `Optional`, `Self` 등)를 완비한다.

**Acceptance criteria:**
- [ ] GUI 계층 핵심 클래스의 모든 public 메서드에 파라미터 및 반환 타입 어노테이션이 100% 적용된다.
- [ ] 정적 타입 검사 시 Any 남용 없이 타입 추론이 정상 통과한다.

**Verification:**
- [ ] Type check: 정적 타입 검증 통과

**Dependencies:** Task 5.1
**Files likely touched:**
- `chzzktube/ui/main_window.py`
- `chzzktube/ui/components/*.py`
- `chzzktube/control/controller.py`
- `chzzktube/control/startup_coordinator.py`
**Estimated scope:** M (5 files, ~30m)

---

### Task 5.3: 5개 평가 축 전수 재진단 및 최종 품질 게이트 통과
**Description:** 초기 진단에서 평가한 5대 항목(정적 분석, 아키텍처, 성능, 가독성, UI/UX 안정성)에 대해 동일한 기준으로 전수 재감사를 실시하고, 각 항목 90점 이상(평균 92점 이상) 달성을 최종 검증한다.

**Acceptance criteria:**
- [ ] [항목 1] 정적 분석 및 디버깅: 95점 이상 (크래시 0건, 중복 정의 0건)
- [ ] [항목 2] GUI 아키텍처 및 상태 관리: 93점 이상 (단일 책임, 상태 동기화 완비)
- [ ] [항목 3] 성능 및 리소스 최적화: 92점 이상 (O(1) 블록 갱신, 60fps 유지)
- [ ] [항목 4] 가독성 및 유지보수성: 94점 이상 (모듈 분해, 타입 100%, 테마 단일화)
- [ ] [항목 5] UI/UX 안정성: 92점 이상 (HiDPI 반응형, 실시간 검증 완비)
- [ ] 종합 평균 점수: 93점 이상 달성

**Verification:**
- [ ] Tests pass: `pytest tests/` 전체 회귀 테스트 스위트 100% 성공
- [ ] 최종 진단 보고서 작성 및 품질 게이트 승인

**Dependencies:** Tasks 5.1, 5.2
**Files likely touched:**
- `docs/HANDOVER.md`
- `docs/architecture.md`
- `tasks/todo.md`
**Estimated scope:** S (Documentation & Audit, ~20m)

---

## Checkpoint 5: Final 5-Axis 90+ Score Gate Approval
- [ ] 5개 평가 항목 모두 90점 이상 공식 달성
- [ ] 전체 테스트 100% 그린
- [ ] 대규모 리팩토링 최종 완료 및 배포 준비
- [ ] 코드 리뷰 5축 품질 게이트 통과