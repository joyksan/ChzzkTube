# Implementation Plan: ChzzkTube GUI 대규모 리팩토링 (5축 90점+ 달성)

## Overview
본 계획서는 ChzzkTube GUI 프로젝트 정량 진단에서 도출된 5대 취약점(정적 분석 및 디버깅: 42점, 아키텍처 및 상태 관리: 48점, 성능 및 리소스: 52점, 가독성/유지보수성: 56점, UI/UX 안정성: 62점)을 전면 개선하여 모든 평가 축에서 90점 이상을 달성하기 위한 원자적(15-30분 단위) 작업 분해 계획서입니다.
치명적 런타임 크래시를 우선 제거하고, 진행률 렌더링 병목을 수술하며, 1,800라인 단일 클래스를 수직 분해하고, HiDPI 반응형 다이얼로그와 타입 시스템을 완비합니다.

---

## Architecture Decisions

1. **단일 진실 공급원(SSOT) 상태 동기화 계약**:
   - `MediaController.state` (불변 `SessionState`), `DownloadWorker._shared_state` (가변 공유 딕셔너리), `DownloadContext.state` 간의 참조 분리 현상을 단일 인스턴스 참조 보장 모델로 통일한다.
   - `canceled_signal` 및 `skip_signal` 수신 시 내부 상태 플래그와 파이프라인 컨텍스트 딕셔너리를 원자적으로 동시 갱신한다.

2. **콘솔 로그 렌더러의 타깃형 단일 블록 치환 (Targeted In-Place Mutation)**:
   - 진행률 틱 수신 시 콘솔 전체를 날리고 4,000줄을 재삽입하는 `reflow()` 호출을 전면 폐기한다.
   - `component_id` 기반 갱신은 `QTextDocument.findBlockByNumber()`와 `QTextCursor` 블록 범위 교체(Targeted In-Place)를 적용하여 O(1) 수준의 렌더링 성능을 확보한다.
   - 초당 20회 이상의 고주파 진행률 틱은 50ms 디바운스/쓰로틀링을 적용해 GUI 렌더링 프레임을 60fps로 방어한다.

3. **MainWindow의 모듈형 수직 분해 (MVC/MVVM 지향)**:
   - 1,797라인 `MainWindow`를 400라인 이하의 루트 오케스트레이터로 축소한다.
   - `HeaderBarWidget` (경로/설정/로그 버튼), `ActionBarWidget` (URL 입력/디바운스/실행), `KeybindManager` (단축키 필터링 및 디스패치)로 책임을 위임 분리한다.

4. **HiDPI 반응형 다이얼로그 레이아웃 표준화**:
   - 모든 팝업 다이얼로그(`ExitConfirmDialog`, `SettingsDialog`, `TuiNoticeDialog` 등)의 `setFixedSize()`를 제거하고, `setMinimumSize()` + `sizeHint()` + `QLayout` 크기 제약 조건으로 전환하여 125%~200% 디스플레이 배율에서도 텍스트 잘림을 방지한다.

5. **비차단 비동기 I/O 및 좀비 워커 안전 수거**:
   - GUI 메인 스레드에서 직접 동기 호출하던 `server_ping()` (HTTP)과 파일 I/O를 비차단 백그라운드 태스크로 전환한다.
   - 분석 워커 교체 시 메인 스레드를 2초간 멈추는 `w.wait(2000)` 및 `terminate()` 강제 중단을 제거하고, `finished.connect(deleteLater)` 기반 비동기 좀비 수거 패턴을 복원한다.

---

## Dependency Graph

```
[Phase 1: Foundation (Crash & State Bugs)]
    ├── Task 1.1: MainWindow _platform_of_url & closeEvent Fix
    ├── Task 1.2: StartupCoordinator raw_log NameError Fix
    ├── Task 1.3: DownloadWorker State Sync & Playlist Skip Fix
    └── Task 1.4: MainWindow Duplicate Methods & BOM Purge
            │
            ▼
[Phase 2: Performance Optimization (Console & I/O)]
    ├── Task 2.1: Targeted Block Mutation in ConciseLogConsole
    ├── Task 2.2: Decouple GUI Blocking I/O & Safe Worker Reap
    └── Task 2.3: Progress Tick Throttling (50ms Window)
            │
            ▼
[Phase 3: Architecture Decomposition (Modular UI)]
    ├── Task 3.1: Extract HeaderBarWidget (L1 Config Layer)
    ├── Task 3.2: Extract ActionBarWidget (L2 Input Layer)
    ├── Task 3.3: AppState Enum & Thin-Wrapper Property Purge
    └── Task 3.4: MainWindow Slim Orchestrator (< 400 lines)
            │
            ▼
[Phase 4: Robustness & Responsive Layouts (HiDPI)]
    ├── Task 4.1: Responsive Layout Migration for Dialogs
    ├── Task 4.2: SettingsDialog Modular Section Builders
    └── Task 4.3: Real-Time Input Validation & Error Boundaries
            │
            ▼
[Phase 5: Maintainability & Quality Gate (Audit)]
    ├── Task 5.1: Unified Palette & Theme Conflict Resolution
    ├── Task 5.2: Type Hints Completion across GUI & Control
    └── Task 5.3: Automated Regression Suite & 5-Axis 90+ Audit
```

---

## Task List

### Phase 1: Foundation — 크리티컬 버그 수정 및 안정성 확보 (점수 42점 -> 80점)
- [ ] **Task 1.1**: `main_window.py`의 `_platform_of_url` 누락 및 `closeEvent` `SessionState.get()` 예외 수정
- [ ] **Task 1.2**: `startup_coordinator.py`의 `raw_log` `NameError` 및 예외 로깅 복구
- [ ] **Task 1.3**: `downloader.py`의 `_canceled` 신호 동기화 및 `skip` 상태 리셋 결함 수정
- [ ] **Task 1.4**: `main_window.py` 내 9개 중복 메서드 제거, `dialogs.py` 데드코드 정리 및 BOM 제거
- [ ] **Checkpoint 1: Foundation**: 크리티컬 크래시 0건 검증 (`pytest tests/test_ui_startup.py tests/test_analysis_timeout.py tests/test_window_initialization.py`)

### Phase 2: Performance — 콘솔 렌더링 병목 및 블로킹 I/O 해소 (점수 52점 -> 90점)
- [ ] **Task 2.1**: `log_console.py`의 `_update_progress_line` 타깃형 단일 블록 치환 구현 (`reflow` 호출 제거)
- [ ] **Task 2.2**: 메인 스레드 동기 `server_ping` 비동기화 및 분석 워커 `wait(2000)` 블로킹 제거
- [ ] **Task 2.3**: 고주파 진행률 틱 50ms 쓰로틀링 및 버퍼 관리 최적화
- [ ] **Checkpoint 2: Performance**: 대량 로그/진행 틱 발생 시 GUI 60fps 유지 및 CPU 점유율 안정화 검증

### Phase 3: Architecture — MainWindow 모듈 분해 및 상태 머신 단일화 (점수 48점 -> 92점)
- [ ] **Task 3.1**: 상단 경로/설정/로그 바 분리 (`chzzktube/ui/components/header_bar.py`)
- [ ] **Task 3.2**: URL 입력 및 액션 바 분리 (`chzzktube/ui/components/action_bar.py`)
- [ ] **Task 3.3**: 상태 머신 일원화 (`AppState` Enum 도입 및 `MainWindow` 80줄 보일러플레이트 제거)
- [ ] **Task 3.4**: `main_window.py` 400라인 미만 슬림 오케스트레이터 재조립
- [ ] **Checkpoint 3: Architecture**: 분리된 컴포넌트 간 Signal 바인딩 및 기존 통합 테스트 전원 통과

### Phase 4: Robustness — 반응형 HiDPI 다이얼로그 및 입력 예외 방어 (점수 62점 -> 92점)
- [ ] **Task 4.1**: 7개 모달 다이얼로그의 `setFixedSize` 제거 및 반응형 레이아웃 전환
- [ ] **Task 4.2**: `SettingsDialog` 258라인 UI 조립부를 섹션별 모듈 빌더로 분할
- [ ] **Task 4.3**: URL 입력 실시간 유효성 검증 및 예외 바운더리 강화
- [ ] **Checkpoint 4: Robustness**: 150%/200% 배율 환경 다이얼로그 렌더링 및 비정상 입력 방어 검증

### Phase 5: Maintainability — 클린 코드, 타입 완비 및 90+ 게이트 감사 (점수 56점 -> 95점)
- [ ] **Task 5.1**: `theme.py` 스타일 충돌 정리 및 하드코딩 색상 시맨틱 토큰화
- [ ] **Task 5.2**: GUI/Control 계층 전수 Type Hints (`mypy`/`pyright` 무결성 달성)
- [ ] **Task 5.3**: 5개 평가 축 전수 검증 및 회귀 테스트 스위트 최종 통과
- [ ] **Checkpoint 5: Quality Gate**: 5축 종합 평가 90점 이상 달성 확인

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `MainWindow` 컴포넌트 분리 시 기존 테스트 대역(`_FakeMain`) 깨짐 | High | 기존 프로퍼티 및 메서드 인터페이스를 유지하는 파사드(Facade) 바인딩 제공 |
| `QTextEdit` 블록 교체 시 개행/줄바꿈 문법 불일치 | Medium | `VerboseLogWindow`에서 실증된 블록 탐색(`findBlockByNumber`) 및 앵커 선택 방식 재사용 |
| QThread 비동기 종료 시 Python 프로세스 종료 지연 | Medium | `closeEvent`에서 협조적 취소 플래그 + 타임아웃 300ms 폴링 후 즉시 종료 |
| PySide6 시스템 폰트 메트릭 차이로 인한 레이아웃 깨짐 | Low | 고정 크기 대신 `QSizePolicy`와 `minimumSize` 기반 자동 팽창 적용 |

---

## Open Questions
- 없음 (진단 보고서 및 코드 정적 분석을 통해 모든 버그 위치와 리팩토링 타깃이 100% 특정됨).

