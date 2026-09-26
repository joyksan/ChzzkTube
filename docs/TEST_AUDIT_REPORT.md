# ChzzkTube 테스트 스위트 전수조사 및 결함 분석 보고서 (Test Audit Report)

> **문서 상태**: 공식 승인 완료 (v3.12.4 기준)  
> **조사 일시**: 2026-09-26  
> **조사 대상**: 루트 `smoke_test.py` 및 `tests/` 디렉터리 내 43개 테스트 모듈 (총 337개 테스트 함수)  
> **조사 목적**: 코드베이스 내 방치된 **레거시 테스트**, **데드 테스트**, **눈속임 테스트(Pass를 띄우기 위한 악질적 타협/허위 단언)**, **플랫폼 비호환 및 미구현 가짜 계약 테스트**를 전수 색출하고 개선 방향을 확립함.

---

## 1. 종합 요약 (Executive Summary)

현재 ChzzkTube의 테스트 스위트는 외형상 380개 이상의 테스트가 등록되어 있으나, 정밀 전수조사 결과 **실제 프로덕션 코드의 품질과 회귀를 보장하지 못하는 다수의 결함 테스트가 방치**되어 있음이 확인되었습니다.

### 📊 전수조사 통계 요약

| 분류 항목 | 파일 수 | 테스트 수 | 비중 / 심각도 | 핵심 특징 요약 |
|:---|:---:|:---:|:---:|:---|
| **전체 조사 대상** | 44개 파일 | 337개 함수 | 100% | `smoke_test.py` 1개 + `tests/*.py` 43개 |
| **🚨 상시 실패 (FAIL)** | 3개 파일 | 9개 함수 | **치명적 (High)** | 레거시 속성 오류, 미구현 계약 단언, 플랫폼 비호환 |
| **🎭 눈속임 / 허위 단언** | 4개 파일 | 8개 함수 | **심각 (High)** | 자작 인형극(더미 검증), 소스 텍스트/주석 문자열 매칭 |
| **🏛️ 레거시 / 폐기 유물** | 3개 파일 | 12개 함수 | **중간 (Medium)** | 폐기된 `log_history`, UV 전환 이전 `.pylib` 오버레이 |
| **⚠️ 과도한 Mocking / 껍데기** | 3개 파일 | 5개 함수 | **주의 (Medium)** | 파이프라인 전체 Mock 대체, 프라이빗 메서드 억지 바인딩 |
| **🐢 하드 슬립 / 서브프로세스** | 2개 파일 | 2개 함수 | **개선 (Low)** | `QTest.qWait(1100)` 1.1초 슬립, 인라인 문자열 `subprocess` 스폰 |

---

## 2. 결함 유형별 세부 분석

---

### [유형 1] `smoke_test.py`의 구조적 결함 (껍데기 스모크)

* **대상 파일**: [`smoke_test.py`](file:///c:/dev/ChzzkTube/smoke_test.py)
* **결함 분류**: **눈속임 패스 (Sham Pass) & 비동기 워커 은폐**

#### 🔍 상세 결함 분석
1. **지극히 얕은 검증 범위 (Superficial Verification)**:
   - `MainWindow()` 생성과 `SettingsDialog`의 콤보박스 개수 3개(`assert dlg.cb_container.count() == 3`)만 확인하고 즉시 `return 0`을 반환하며 종료됨.
   - 핵심 비즈니스 로직인 다운로드 파이프라인, 분석 엔진, 의존성 프로비저닝, POT 토큰 서버 스폰 로직은 전혀 검증하지 않음.
2. **비동기 워커 크래시 무감지 (Asynchronous Death Blindness)**:
   - `MainWindow` 생성 시 백그라운드로 `StartupCoordinator`, `UpdateWorker`, `_POTWorker`가 비동기 구동을 시작함.
   - 그러나 메인 스레드가 85~91번 줄에서 0.1초 만에 `return 0`으로 프로세스를 종료해버리므로, 백그라운드 워커가 `ImportError`나 `KeyError`로 즉시 사망하더라도 `smoke_test.py`는 **무조건 PASS를 출력하고 성공(0)으로 판정**함. (실제로 v3.12.4 이전 `DEFAULT_HOST` 누락 참사 시에도 smoke_test는 통과했음).
3. **취약한 예외 처리**:
   - `except (OSError, re.error) as e:`로 특정 예외만 포획하여, 일반적인 파이썬 런타임 오류(`TypeError`, `AttributeError`, `ImportError` 등) 발생 시 하네스가 비정상 크래시됨.
4. **목적 불일치 코드 혼재**:
   - `--debug-dialogs`는 CI/검증용 코드가 아니라, 화면에 다이얼로그 7종을 띄우는 수동 GUI 프리뷰 유틸리티임.

---

### [유형 2] 눈속임 / Pass를 위한 악질적 타협 테스트 (Sham Tests)

실제 프로덕션 코드를 검증하지 않고, 테스트 코드 내에서 자작한 가짜 객체를 검증하거나 소스코드 텍스트의 글자 존재 여부만 검사하여 "통과(Pass)" 숫자만 채우는 가장 질 나쁜 테스트 유형입니다.

#### 1. 자작 인형극 테스트 (100% Puppetry / Self-Assertion)
* **대상 파일**: [`tests/test_fallback_watchdog.py`](file:///c:/dev/ChzzkTube/tests/test_fallback_watchdog.py)
```python
# test_fallback_watchdog.py 라인 8-35 발췌
class _View:
    def __init__(self):
        self._startup_completed = False
        self._startup_coord = SimpleNamespace(
            _state=SimpleNamespace(deps_error_msg="ffmpeg: dyld symbol not found"),
        )
    def get_current_app_state(self):
        return "STARTUP"

def test_deps_error_keeps_input_locked():
    view = _View()
    state = view.get_current_app_state()
    assert state == "STARTUP" # 자기가 하드코딩한 값을 자기가 검증
    assert view._startup_coord._state.deps_error_msg

def test_no_fallback_timer():
    view = _View()
    assert not hasattr(view, "_fallback_timer") # 자기가 속성을 안 넣고 속성이 없다고 단언
```
* **결함 내용**:
  - 실제 앱의 `MainWindow`, `Controller`, `StartupCoordinator`는 단 1줄도 임포트하거나 실행하지 않음.
  - 테스트 코드 안에서 자기가 임의로 만든 `_View` 클래스에 `return "STARTUP"`을 박아두고 그것이 맞는지 단언함.
  - `_View`에 `_fallback_timer`를 정의하지 않아놓고 "폴백 타이머가 제거되었음"이라고 단언함. 프로덕션 코드가 어떻게 바뀌든 영원히 PASS되는 100% 가짜 테스트.

#### 2. 소스 코드 텍스트 / 주석 문자열 매칭 테스트 (Source Text Grep Test)
* **대상 파일 및 함수**:
  1. [`tests/test_defect1_tv_fallback.py`](file:///c:/dev/ChzzkTube/tests/test_defect1_tv_fallback.py) -> `test_pure_delegation_comment_present`:
     ```python
     src = pathlib.Path("chzzktube/pipeline/target_downloader/options.py").read_text(encoding="utf-8")
     assert "순정" in src  # 소스코드에 "순정"이라는 한국어 주석 단어가 있는지 검사
     ```
     - 소스 파일에서 주석 한 줄 지우면 기능이 정상이어도 테스트가 깨지고, 반대로 로직이 완전히 파괴되어도 `순정`이라는 단어만 있으면 통과.
  2. [`tests/test_chzzk_auth.py`](file:///c:/dev/ChzzkTube/tests/test_chzzk_auth.py) -> `test_analyze_worker_maps_auth_error_to_cookie_message`:
     ```python
     src = inspect.getsource(aw.AnalyzeWorker.run)
     assert "ChzzkAuthError" in src
     assert "cookie" in src.lower()
     ```
     - `AnalyzeWorker.run`을 실행해 인증 오류 시 쿠키 다이얼로그나 로그가 발생하는지 런타임 검증을 하지 않고, 함수 소스 텍스트 안에 특정 단어가 들어있는지만 확인.
  3. [`tests/test_live_recorder.py`](file:///c:/dev/ChzzkTube/tests/test_live_recorder.py):
     - `test_stream_finish_is_module_function`: `assert "handle_stream_finish(ctx" in src`
     - `test_no_self_import_alias`: `assert "_lr." not in src`
     - `test_stream_finish_uses_module_log_success_info`: `assert "log_success_info(ctx" in src`
  4. [`tests/test_controller_no_duplicates.py`](file:///c:/dev/ChzzkTube/tests/test_controller_no_duplicates.py) -> `test_media_controller_has_no_duplicate_session_methods`:
     - `controller.py` 소스를 읽어 `def begin_download`의 출현 횟수가 1인지 정규식 검사.
* **결함 내용**:
  - 단위 테스트(Unit Test)의 본질인 "입력값에 대한 출력값 및 부작용(Side-effect) 검증"을 완전히 포기하고, Linter가 해야 할 텍스트 정규식 검사로 둔갑시켜 통과율만 높임.

---

### [유형 3] 상시 실패 (FAIL) 및 방치된 레거시/가짜 계약 테스트

현재 전체 `pytest tests/` 실행 시 항상 빨간불(FAIL)을 발생시키며 방치된 테스트들입니다.

#### 1. 폐기된 모듈 역참조로 인한 크래시 (Legacy Crash)
* **대상 파일**: [`tests/test_log_regressions.py`](file:///c:/dev/ChzzkTube/tests/test_log_regressions.py) -> `test_raw_bus_overflow_is_bounded_and_summarized_once`
* **에러 로그**:
  ```text
  with patch.object(chzzktube.core.log_history, "log") as history_log:
  AttributeError: module 'chzzktube.core' has no attribute 'log_history'
  ```
* **결함 내용**:
  - v3.3.0에서 로그 버스가 단일화되면서 `log_history` 직접 호출이 영구 금지(HANDOVER §13 불변식 11번)되었고 최상위 export에서 제거됨.
  - 그러나 과거 아키텍처 시절 작성된 테스트가 최신 계약에 맞게 수정되지 않고 수개월간 방치되어 실행 시 즉시 크래시 발생.

#### 2. 프로덕션 구현 없는 가짜 계약 단언 (Phantom Contract Failures)
* **대상 파일**: [`tests/test_v38_contracts.py`](file:///c:/dev/ChzzkTube/tests/test_v38_contracts.py)
* **실패 테스트 4종**:
  1. `test_cause_action_keywords_standardized`:
     - 구현체(`_normalize_action`)는 `retry mirror (\d+/\d+)` 정규식을 지원하도록 확장되었으나, 테스트는 `assert _normalize_action("retry mirror (99/99)") == ""`라는 과거 고정 계약을 고집하여 실패.
  2. `test_msg_contains_delimiter_is_sanitized`:
     - 로그 메시지에 `│` 구분자가 포함되어도 4컬럼으로 유지되도록 새니타이징되어야 한다고 단언하나, 프로덕션 코드(`log_emitter.py`, `raw_log.py`)에는 해당 새니타이징 구현이 전무하여 컬럼이 5개로 쪼개져 실패 (`assert 5 == 4`).
  3. `test_msg_contains_newline_is_sanitized`:
     - 개행(`\n`)이 제거되어 단일 라인이 유지되어야 한다고 단언하나, 구현이 없어 개행이 그대로 노출되어 실패.
  4. `test_msg_contains_multiple_delimiters`:
     - 다중 구분자 인젝션 방어 단언 실패 (`assert 7 == 4`).
* **결함 내용**:
  - TDD 명목으로 작성되었으나 실제 프로덕션 코드에 구현을 반영하지 않은 채 테스트를 방치하여 전체 테스트 스위트의 신뢰도를 파괴함.

#### 3. 플랫폼 비호환 무단언 실패 (Platform Incompatible Failures)
* **대상 파일**:
  1. [`tests/test_v38_contracts.py`](file:///c:/dev/ChzzkTube/tests/test_v38_contracts.py) (macOS Bottle 테스트 3종):
     - `test_macos_bottle_keys_match_live_formulae`
     - `test_macos_bottle_binaries_are_normalized_to_cache_root`
     - `test_macos_bottle_contract_matches_live_formulae_shape`
     - Windows 환경에서 macOS 전용 POSIX 아카이브 및 실행 퍼미션(`os.access(..., os.X_OK)`)을 검증하려다 실패. `@pytest.mark.skipif(sys.platform != "darwin")` 가드가 누락됨.
  2. [`tests/test_chzzk_live_integration.py`](file:///c:/dev/ChzzkTube/tests/test_chzzk_live_integration.py) -> `test_chzzk_live_real_hls_pipeline`:
     - 시스템 `ffmpeg` 프로세스를 실제 실행하여 임의의 가짜 HLS 스트림을 생성하고 녹화 파이프라인을 돌림.
     - Windows의 프로세스 파이프/경로 차이로 인해 `chzzk live recording failed` 에러를 내며 상시 실패. 외부 종속성이 있는 비격리 테스트.

---

### [유형 4] 아키텍처 불일치 레거시 테스트 (Architectural Mismatch)

* **대상 파일**: [`tests/test_pylib_overlay.py`](file:///c:/dev/ChzzkTube/tests/test_pylib_overlay.py) (6개 테스트)
* **결함 내용**:
  - 과거 앱이 가상환경 없이 동작할 때 런타임에 `.pylib` 폴더를 생성하고 다운로드받은 wheel을 압축 해제해 `sys.path[0]`에 삽입하던 오버레이 메커니즘을 검증함.
  - 현재 프로젝트는 **UV SSOT (`uv run`, `.venv`) 체제로 완전히 전환**되었으며, 런타임 pip 오버레이는 비권장/레거시 상태임. 최신 프로젝트 지침과 상충되는 유물 테스트.

---

### [유형 5] 과도한 Mocking 및 비정상 바인딩 (Hollow / Over-mocked Tests)

1. **파이프라인 전면 Mock 치환**:
   * [`tests/test_download_completion.py`](file:///c:/dev/ChzzkTube/tests/test_download_completion.py) -> `test_completion_once`:
     - `extract`, `expand_targets`, `download_target`, `finalize`, `raw_log.raw`를 모조리 `Mock`으로 덮어씀. 프로덕션 코드는 사실상 0줄 실행되며 `finished_all` 시그널 콜백 리스트의 길이만 확인하는 빈 껍데기.
2. **프라이빗 메서드 억지 바인딩 (Monkey-Binding Test Double)**:
   * [`tests/test_gate_watchdog.py`](file:///c:/dev/ChzzkTube/tests/test_gate_watchdog.py):
     - `MainWindow`를 인스턴스화하지 않고 `SimpleNamespace`에 `MainWindow`의 프라이빗 메서드 11개(`_start_gate_watchdog`, `_stop_gate_watchdog`, `_on_gate_timeout` 등)를 강제로 `method.__get__(view)` 바인딩하여 실행.
     - UI 내부 구조가 조금만 바뀌어도 즉시 깨지는 고위험 결합 테스트.

---

### [유형 6] 실행 지연 및 서브프로세스 격리 파괴 테스트

1. **하드 슬립 (Hard Sleep)**:
   * [`tests/test_ui_startup.py`](file:///c:/dev/ChzzkTube/tests/test_ui_startup.py):
     - `QTest.qWait(1100)`으로 무조건 1.1초를 슬립하여 테스트 스위트 전체 속도를 크게 저하시킴.
2. **인라인 파이썬 서브프로세스 스폰 (Inline Subprocess)**:
   * [`tests/test_window_initialization.py`](file:///c:/dev/ChzzkTube/tests/test_window_initialization.py):
     - 80줄짜리 문자열 `_PROBE`를 작성해 `subprocess.run([sys.executable, "-c", _PROBE])`로 실행.
     - 테스트 실패 시 pytest의 트레이스백이 단절되고 타임아웃 30초 위험이 존재하며, pytest 하네스에서 완전히 격리됨.

---

## 3. 정비 및 정상화 로드맵 (Action Items)

| 우선순위 | 작업 항목 | 대상 모듈 | 기대 효과 |
|:---:|:---|:---|:---|
| **P0** | **상시 FAIL 테스트 9종 즉각 수리** | `test_log_regressions.py`<br>`test_v38_contracts.py`<br>`test_chzzk_live_integration.py` | `pytest tests/` 전체 실행 시 100% 통과(Green) 달성 |
| **P1** | **`smoke_test.py` 전면 개편** | `smoke_test.py` | 비동기 워커 생존 검증, 백그라운드 크래시 감지 하네스 구축 |
| **P2** | **눈속임 소스 텍스트 검사 테스트 5종 퇴출** | `test_defect1_tv_fallback.py`<br>`test_chzzk_auth.py`<br>`test_live_recorder.py`<br>`test_controller_no_duplicates.py` | 텍스트 `grep`을 실제 런타임 동작/시그널 검증 단위 테스트로 전환 |
| **P3** | **자작 인형극 `test_fallback_watchdog.py` 정상화** | `test_fallback_watchdog.py` | 가짜 `_View` 대신 실제 `StartupCoordinator` 상태 머신 검증으로 교체 |
| **P4** | **플랫폼 분기 가드 적용 (`darwin` 전용 격리)** | `test_v38_contracts.py` | Windows/macOS 교차 환경에서 불필요한 실패 방지 |
| **P5** | **레거시 `.pylib` 오버레이 테스트 정리** | `test_pylib_overlay.py` | UV SSOT 원칙에 맞추어 폐기 또는 최신 경로 계약으로 한정 |

---

## 4. 결론

ChzzkTube 테스트 스위트는 양적으로는 풍부하나, 과거 빠른 개발 과정에서 남겨진 **가짜 단언(Sham tests)**, **폐기된 모듈 참조**, **구현 없는 유령 계약**으로 인해 전체 스위트의 신뢰성이 저하되어 있었습니다.

위 로드맵에 따라 **"눈속임 테스트 제거 → 실패 테스트 수리 → smoke_test 비동기 워커 검증 강화"** 3단계 정비를 순차적으로 진행하여 견고한 회귀 방지망을 구축해야 합니다.

