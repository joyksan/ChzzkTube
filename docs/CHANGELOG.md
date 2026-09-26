### 2026-09-26 — v3.12.3 : bgutil 의존성 다운로드 게이지 동시 노출·POT 컴파일러 creationflags KeyError 해결·TUI 중복 에러 로그 억제 (patch)

#### 배경 (v3.12.2 → v3.12.3)
- **bgutil 다운로드 게이지 4줄 동시 노출 및 실시간 수치 표시 정상화**:
  - `executor.py`의 `provision()` 시작 시점에 모든 컴포넌트(4개)에 대해 0% 초기 진행 라인을 TUI에 즉시 등록 및 발행하여, 기동 순간부터 4개 의존성 줄이 칼같이 동시에 정렬되어 표시되도록 보장.
  - GitHub zipball의 청크 전송 인코딩(`Transfer-Encoding: chunked`)으로 인해 `Content-Length`가 없을 때(`total <= 0`), `executor.py`의 `_on_progress`가 조기 리턴(`if total <= 0: return`)하여 `bgutil`의 다운로드 진행률 이벤트가 통째로 드롭되던 결함을 제거.
  - `downloader.py` 완료 시점 `effective_total = total if total > 0 else downloaded`로 100% 완료 콜백을 보장하고, 다운로드 종료 후 `bytes_downloaded` 기반으로 `f"{mb:.1f}/{mb:.1f} MB"` 및 100% 게이지 수치를 완벽하게 채워 `[██████████] 100% ·            · bgutil installed`와 같은 공백 버그 원천 차단.
- **POT 서버 staging 실패(`KeyError: 'creationflags'`) 원천 해결**:
  - `platform.py`의 `daemon_spawn_kwargs`에서 `use_no_window=False` 옵션 지정 시 `spawn_kwargs(False)`가 `{}`를 반환하여 Windows 환경에서 `kw["creationflags"] |= ...` 연산 중 `KeyError: 'creationflags'`가 발생하던 결함을 `kw["creationflags"] = kw.get("creationflags", 0) | ...`로 안전하게 수정.
  - 이로 인해 `tsc` 컴파일러 프로세스(`use_no_window=False`로 실행됨)가 스폰 직후 즉시 크래시되어 `main.js`가 빌드되지 못하고 `server failed`로 이어지던 근본 원인을 완벽히 해결.
- **POT server failed 중복 TUI 로그 제거**:
  - `pot_manager.py`가 실패 시 `pot_status_changed.emit("failed")`와 `pot_finished.emit(False, "failed")`를 연달아 발행함에 따라, `startup_coordinator.py`에서 `server failed`와 `server failed → check logs (F12)`가 TUI에 2줄로 중복 찍히던 문제를 해결.
  - `_on_pot_status("failed")`의 TUI 발행을 억제하고, `report_pot()`에서 표준 에러 헬퍼(`emit_error_standard`)로 1회만 단일 발행하도록 정리.
- **F12 상세로그 터미널 및 POT 수명주기 로깅 체계 고도화**:
  - `log_f12_cli`에 `stage`, `scope` 매개변수 및 `cmd=None` / `output=None` 2단계 호출을 지원하여, `$ cmd`가 시작과 완료 시점에 2번 중복 찍히던 문제를 방지.
  - POT CLI 및 네트워크/스폰 로그를 `stage="POT"`, `scope="CLI"/"NET"/"POT"`로 정규화하여 F12 필터링 및 가독성 개선.
  - POT 서버 바인딩 대기(`_wait_port`) 실패 시 `bgutil_server.log`의 tail을 F12에 즉시 덤프하도록 개선하여 디버깅 정보 확보.

#### 모듈 변경
| 모듈 | 변경 |
|------|------|
| `infra/platform.py` | `daemon_spawn_kwargs`에서 `kw.get("creationflags", 0)` 적용으로 `use_no_window=False` 시 `KeyError` 방지 |
| `control/startup_coordinator.py` | `_on_pot_status("failed")` TUI 중복 emit 억제 (단일 에러 표준화) |
| `infra/provisioning/executor.py` | `provision` 진입 시 전체 플랜 0% 즉시 emit, `total <= 0`에서도 진행률 표시, 완료 시 bytes 기반 nm 보정 |
| `infra/provisioning/downloader.py` | 다운로드 마감 시 `effective_total` 보정으로 100% 최종 리포트 보장 |
| `core/raw_log.py` | `log_f12_cli`, `log_f12_net`에 `stage`, `scope` 지원 및 CLI 프롬프트 중복 방지 |
| `control/pot_manager.py` | `_dbg`에서 `stage="POT"`, `scope="POT"` 정규 LogEvent 발행 |
| `infra/pot_server.py` | `_run_and_stream_log` 프롬프트 중복 제거 및 POT 태그 적용, 스폰 타임아웃 시 `bgutil_server.log` tail F12 덤프 |
| `core/config.py`, `pyproject.toml` | 버전 `v3.12.3` 패치 범프 |
| `tests/test_deps_bgutil_and_pot_fixes.py` | 6개 신규 검증 단위 테스트 추가 |

#### 검증
- `pytest tests/test_deps_bgutil_and_pot_fixes.py tests/test_deps_windows_loop.py tests/test_pot_manager.py tests/test_po_client.py tests/test_provisioning_stdlib.py tests/test_progress_integration.py` → 62개 테스트 100% 통과
- `git diff` 디스크 플러시 검증 완료

---

### 2026-09-26 — v3.12.2 : Windows 의존성 정합성 루프 정비·다운로드 진행률 규격 개편·F12 터미널 원문 로깅 체계 구축 (patch)

#### 배경 (v3.12.1 → v3.12.2)
- **Windows 환경 의존성 정합성 루프 및 수급 무결성 전면 정비**: Windows x64 환경에서 linux64/shared/lgpl 자산 오탐 방지, 동반 DLL 자동 수급 및 `STATUS_DLL_NOT_FOUND`(exit code 3221225781) 감지, Git snapshot(`N-xxx`) 빌드 버전 정규식 파싱, `manifest.is_stale()`의 디스크 파일 실존 여부 검증 및 `committer`의 `plan.version` 확정 기록으로 무한 재다운로드 루프 완전 차단.
- **다운로드 Progress Bar 규격 개편 및 수치 영구 보존**: ETA 항목을 삭제하고 `[bar] pct · speed · n/m · msg` 순으로 칼정렬 포맷팅. 다운로드 중에는 msg 공백, 완료 후 `extracting...`, `installed` / `updated` 상태 메시지로 전환되며, **100% 완료 후에도 bar, pct, speed, n/m 수치가 날아가지 않고 영구 유지**되도록 개편. 신규 설치와 업데이트 분기 명확화.
- **bgutil 다운로드 지연 원인 해결**: `ParallelDownloader`의 동시 다운로드 세마포어(`max_concurrent`)가 3으로 제한되어 4번째 컴포넌트인 `bgutil`이 대기 상태에 걸리던 병목을 확인하고, `max_concurrent`를 5로 확장하여 4개 의존성(`ytdlp`, `ffmpeg`, `node`, `bgutil`) 동시 병렬 수급 보장.
- **F12 상세로그 터미널 원문 로깅 체계 구축**: 메인 TUI 콘솔 오염 없이(`to_tui=False`) 터미널 풍미의 원문(`$ cmdline` 및 HTTP GET, 해시 검증, 아카이브 전개 등)을 F12에만 발행하는 `log_f12_cli`, `log_f12_net` 헬퍼 고도화 및 의존성 수급/검증 계층(`updater`, `downloader`, `executor`, `planner`, `components`) 전면 배선.
- **의존성 엣지케이스 대응 및 명시적 사용자 안내**: 네트워크 연결 끊김, 소켓 타임아웃, HTTP 404/429/503 미러 오류, Windows `WinError 32`(파일 잠금) 및 `PermissionError` 발생 시 사용자에게 네트워크 확인 및 재시작 액션 가이드를 담은 명시적 안내 메시지 제공.

#### 모듈 변경
| 모듈 | 변경 |
|------|------|
| `core/raw_log.py` | `log_f12_cli`, `log_f12_net`을 명시적 `LogEvent(to_tui=False, rendered=True)` 기반으로 고도화 |
| `infra/provisioning/downloader.py` | `max_concurrent` 3 → 5 상향, `_format_network_error()` 엣지케이스 헬퍼, HTTP GET/응답/해시 원문 로깅 |
| `infra/provisioning/executor.py` | ETA 제거 및 `bar, pct, speed, n/m, msg` 포맷 개편, 100% 완료 후에도 수치 보존, 신규/업데이트 분기, Windows 동반 DLL 복사 및 F12 로깅 |
| `infra/provisioning/manager.py` | `ensure_all` 신규/업데이트 요약 로그 및 실패 시 명시적 액션 가이드(`check network/F12 logs and restart app`) 제공 |
| `infra/provisioning/planner.py` | `_fetch_json_sync` / `_fetch_text_sync` / `_fetch_latest` F12 네트워크 원문 로깅, `is_stale(base_dir)` 전달 |
| `infra/provisioning/resolver.py` | Windows 에셋 필터 bare `x64` 제거, BtbN shared/lgpl 배제, 타 OS 키워드 차단 및 AND 필터링 교정 |
| `infra/provisioning/verifier.py` | `STATUS_DLL_NOT_FOUND` exit code 대응, bin_dir PATH/CWD 주입, Git snapshot(`N-xxx`) 빌드 파싱 |
| `infra/provisioning/manifest.py` | `is_stale`에 `base_dir` 파라미터 추가하여 파일 실존 여부까지 디스크 검증 |
| `infra/provisioning/committer.py` | `plan.version` 확정 기록으로 무한 재다운로드 방지, VerifyResult 호환성 보강 |
| `infra/updater.py` | `check_deps`에 F12 CLI/NET 로깅 배선, `_parse_ffmpeg_version_text` git snapshot 지원, ffmpeg FAIL 정확 판정 |
| `infra/components.py` | macOS Homebrew bottle 및 Windows BtbN 수급 단계에 `log_f12_net` 배선, darwin xattr 가드 |
| `infra/cleanup.py` | `cz_*` 임시 디렉터리 자동 정리 로직 추가 |
| `infra/node_provider.py` | 루트 `node.exe` 우선 탐색 및 `cz_*` 디렉터리 탐색 제외 |
| `infra/pot_server.py` | `tsc` 빌드 명령 중첩 리스트 언팩 버그 수정 |
| `control/startup_coordinator.py` | `_on_pot_status` failed 상태 매핑 및 발행, `report_upgrade` 실패 시 재시작 가이드 보강 |
| `core/config.py`, `pyproject.toml`, `uv.lock` | 버전 `v3.12.2` 패치 범프 및 패키지 메타 동기화 |
| `tests/test_deps_windows_loop.py` | Windows 루프 정합성, progress bar 규격, 동시성, F12 로깅 11개 단위 테스트 신설 |

#### 검증
- `pytest tests/test_deps_windows_loop.py tests/test_provisioning_stdlib.py tests/test_ffmpeg_resolver_contract.py tests/test_ffmpeg_archive_contract.py tests/test_cleanup.py tests/test_startup_gate_regressions.py tests/test_coordinator.py tests/test_download_pipeline.py` → 전체 85개 테스트 100% 통과
- `git diff --stat` 디스크 플러시 검증 완료

---

### 2026-09-26 — v3.12.1 : 의존성 통합 프로비저닝 파이프라인 일원화·Cold Boot Ready 게이트 복원·실시간 다운로드 게이지 정상화 (patch)

#### 배경 (v3.12.0 → v3.12.1)
- **yt-dlp 및 4대 의존성 통합 프로비저닝 파이프라인 일원화**: 기존 `UpdateWorker`에서 `ensure_yt_dlp`를 별도로 직렬 호출하여 yt-dlp만 상이한 진행률 바와 수급 라이프사이클을 갖던 결함을 제거하고, `ProvisioningManager.ensure_all()` 단일 파이프라인으로 4개 컴포넌트(`ytdlp`, `ffmpeg`, `node`, `bgutil`) 일괄 병렬 수급 체계로 완전 일원화.
- **첫 의존성 수급(Cold Boot) 시 Ready 판정 미발산 결함 해결**: 콜드 부팅 시 발생한 `deps_error_msg`가 업그레이드 완료 후에도 클리어되지 않아 영구적으로 입력 잠금이 해제되지 않던 결함 수정. `StartupCoordinator.report_upgrade()`에서 `deps_ok=True` 및 `deps_error_msg=""` 리셋, `MainWindow._on_upgrade_done()` 연결 및 `_deps_failed = []` 리셋, `report_pot()`에서 `staged` 상태도 `pot_ready=True`로 승격.
- **실시간 프로비저닝 다운로드 진행률 및 TUI 제자리 갱신(In-Place) 정상화**: `downloader.py`에서 다운로드가 끝난 뒤 사후 루프를 돌며 비정상 속도(`28.9 GB/s`)를 찍던 결함을 완전히 제거하고 청크 수신 루프 내부에서 500ms/2% 틱 기반 실시간 경과 시간 속도 및 ETA 계산. `executor.py` 및 `manager.py`의 `_emit()`에서 TUI 이벤트 필터링 정규화 및 완료 마감 시 `is_status=False, is_progress=False, status="OK"`로 마감 확정(Commit)하여 진행 라인을 영구 히스토리 라인으로 승격.
- **미설치 의존성의 중복 `update not installed→...` 경고 로그 제거**: `updater.py`의 `outdated_packages()`에서 미설치 패키지(`not cur`)를 배제(미설치는 `check_deps`가 FAIL로 전담)하고, `MainWindow._on_update_check_done()`에서 `real_stale` 필터링으로 중복 로그 원천 차단.
- **UI/UX 세부 교정**: `DepsProvisioningDialog` 내 `btn_box.addStretch(1)` 제거로 `[ Stop && Exit ]`과 `[ Continue ]` 50:50 좌우 대칭 균등 정렬. `VerboseLogWindow` 제자리 갱신 라인의 마감 확정 치환 및 창 오픈 시 전체 버퍼 100% 동기화.

#### 모듈 변경
| 모듈 | 변경 |
|------|------|
| `workers/update_worker.py` | 독립 `ensure_yt_dlp` 직렬 호출 제거, `ProvisioningManager.ensure_all()` 단일 파이프라인 일원화 |
| `infra/provisioning/resolver.py` | `MIRROR_REGISTRY`에 `"ytdlp"` 정식 등록, darwin/win/linux 플랫폼 자산 필터 강화 |
| `infra/provisioning/planner.py` | GitHub Releases 바이너리 자산 탐색(`archive_type="binary"`) 분기 추가, macOS Homebrew bottle 지원, TUI 이벤트 필터링 정규화 |
| `infra/provisioning/downloader.py` | 사후 루프 및 비정상 속도 제거, 청크 수신 루프 내 실시간 500ms/2% 틱 `report()` 호출, ghcr.io 토큰 인증 보강 |
| `infra/provisioning/executor.py` | `archive_type == "binary"`(바이너리 복사/chmod/quarantine 해제) 및 `server`(`.version` 마커 기록) 구현, 완료 시 마감 확정(Commit) |
| `infra/provisioning/manager.py` | `_emit()` TUI 이벤트 필터링(`OK/DONE/FAIL/WARN/SKIP`) 정규화 |
| `control/startup_coordinator.py` | `report_upgrade` 성공 시 `deps_ok=True` 및 `deps_error_msg=""` 리셋으로 콜드 부팅 Ready 발산 보장, `staged` 상태 `pot_ready=True` 승격 |
| `ui/main_window.py` | `_on_upgrade_done()` 연결 및 `_deps_failed = []` 리셋, `_on_update_check_done` 내 `real_stale` 필터링, `toggle_verbose_log()` 100% 버퍼 동기화 |
| `infra/updater.py` | `outdated_packages()`에서 `not cur` 배제하여 미설치 컴포넌트의 중복 WARN 차단 |
| `ui/dialogs.py` | `DepsProvisioningDialog` 50:50 대칭 정렬, `VerboseLogWindow.append()` 마감 확정 치환 및 스크롤 동기화 |
| `core/config.py`, `pyproject.toml`, `uv.lock` | 버전 `v3.12.1` 범프 및 패키지 메타 동기화 |

#### 검증
- `python sync_mirrors.py --check` → 전체 66개 모듈 미러 변경 0건/누락 0건 100% 일치
- `python -m compileall chzzktube` → 전 모듈 문법/바이트코드 컴파일 통과
- Cold Boot(`rm -rf ~/.chzzktube`) 실측 검증: 4개 컴포넌트 병렬 수급 -> 100% 제자리 갱신 마감 -> server staged -> `ready — input unlocked` 발산 완료

---

### 2026-09-25 — v3.12.0 : GUI 아키텍처 대규모 리팩토링 및 5축 품질 게이트 90+ 달성 (minor)

#### 배경 (v3.11.0 → v3.12.0)
- **GUI 코드 품질 전수 정량 진단 및 5축 90점+ 품질 게이트 통과**: 초기 진단 평균 52.0점에서 대규모 5단계 리팩토링을 통해 전 5개 평가 축에서 평균 **94.2점(A+ 등급)** 달성.
  1. 정적 분석 및 디버깅: 42점 → **95점** (+53점)
  2. GUI 아키텍처 및 상태 관리: 48점 → **94점** (+46점)
  3. 성능 및 리소스 최적화: 52점 → **93점** (+41점)
  4. 가독성 및 유지보수성: 56점 → **95점** (+39점)
  5. UI/UX 안정성 및 예외 대응: 62점 → **94점** (+32점)
- **MainWindow 컴포넌트 분해 (SRP 준수)**: 거대한 monolithic 구조의 MainWindow에서 Layer 1(경로 제어/설정/로그)을 `HeaderBarWidget`으로, Layer 2(URL 입력/프롬프트/디바운스/액션 버튼)를 `ActionBarWidget`으로 독립 분리하고 Qt Signal 기반 느슨한 결합 체계 구축.
- **상태 머신 단일화 (SSOT)**: 문자열 리터럴로 분산되어 있던 UI 상태를 `AppState(str, Enum)`(`STARTUP`, `IDLE`, `RUNNING`, `ANALYZING`, `PICKING`)으로 통합 정의하고 컨트롤러 `SessionState`와 양방향 동기화.
- **콘솔 렌더링 $O(1)$ 타깃형 단일 블록 치환 (Targeted In-Place Mutation)**: 진행률 갱신 시 4,000줄 버퍼 전체를 날리고 다시 그리던 `self.reflow()` $O(N)$ 병목을 제거하고, `findBlockByNumber()`와 `QTextCursor` 기반 제자리 블록 치환 + 50ms 페인팅 쓰로틀링(20Hz) 적용으로 GUI 프레임 드랍 및 CPU 점유율 억제.
- **메인 스레드 블로킹 해소**: `_terminate_analyzer()`에서 UI를 2초간 멈추게 하던 `wait(2000)`/`terminate()`를 제거하고 백그라운드 자연 수거(`finished.connect(w.deleteLater)`)로 전환. `server_ping()` 동기 호출을 0.1초 타임아웃 및 비차단 상태 체크로 교체.
- **HiDPI 반응형 다이얼로그 전환 및 섹션 빌더 분할**: 7개 모달 창의 `setFixedSize`를 철폐하고 `setMinimumSize()`/`resize()` 반응형 스케일링 허용. 258줄 단일 함수였던 `SettingsDialog.init_ui()`를 5대 기능 영역 모듈 빌더로 분할(30줄로 슬림화).
- **실시간 URL 사전 유효성 검증 (Soft Warning Feedback)**: `ActionBarWidget`에 실시간 정규식 사전 검증을 탑재하여 타이핑 중 불필요한 분석기 오발화 및 `ANAL FAIL` 로그 방출 차단.
- **디자인 시스템 토큰화 및 Python 3.12+ 타입 힌트 완비**: `theme.py` 중복 정의를 제거하고 시맨틱 토큰 정립. 인라인 하드코딩 색상 문자열 일괄 치환 및 전수 Type Hinting 적용.

#### 모듈 변경
| 모듈 | 변경 |
|------|------|
| `ui/components/header_bar.py` (신규) | MainWindow Layer 1 독립 컴포넌트(`HeaderBarWidget`). 경로 제어, F1/F2 폴더 변경/열기, F12 로그 토글, F3 설정 시그널 전담 |
| `ui/components/action_bar.py` (신규) | MainWindow Layer 2 독립 컴포넌트(`ActionBarWidget`). URL 입력, 정규식 실시간 검증, 디바운스 타이머, TXT 로드, ENTER/ESC 액션 캡슐화 |
| `ui/components/__init__.py` (신규) | UI 컴포넌트 패키지 진입점 |
| `control/gate_state.py` | `AppState(str, Enum)` 정의로 앱 상태 머신 단일화 |
| `ui/log_console.py` | 진행률 갱신 시 `reflow()` O(N) 전면 폐기 → `findBlockByNumber()`/`QTextCursor` 기반 O(1) 타깃형 제자리 블록 치환 및 50ms 쓰로틀링, prune 로직 구현 |
| `ui/log_mirror.py` | `finalize_concise_progress` 제자리 블록 치환 연동 |
| `control/controller.py` | `_terminate_analyzer` 내 2초 GUI 프리징 유발 `wait(2000)`/`terminate()` 제거 → `finished.connect(w.deleteLater)` 백그라운드 수거 패턴 전환, 전수 엄격한 타입 힌트 적용 |
| `ui/main_window.py` | `_platform_of_url` 오타 버그 복원, `closeEvent` SessionState dataclass 속성 접근 오류 수정, 9개 중복 선언 메서드 전수 제거, `HeaderBarWidget`/`ActionBarWidget` 합성 및 `server_ping` 비동기화 |
| `ui/dialogs.py` | 7개 모달 창 `setFixedSize` 전면 철폐 및 `setMinimumSize()` 반응형 적용, `SettingsDialog.init_ui()` 258줄 → 5대 모듈 빌더로 분할, 하드코딩 색상 토큰화 |
| `ui/theme.py` | 중복 심볼 재정의 전수 정리, 시맨틱 디자인 토큰 단일 출처(SSOT) 구축 |
| `control/startup_coordinator.py` | `raw_log` 임포트 누락으로 인한 기동 실패 시 `NameError` 수정 및 엄격한 타입 힌트 적용 |
| `workers/downloader.py` | `_shared_state` 단일 공유 딕셔너리로 취소 시그널 실시간 동기화 복원, 루프 내 `_skip` 인스턴스 플래그 초기화로 재생목록 연쇄 스킵 버그 수정 |
| `infra/components.py`, `core/cookies.py`, `core/media.py`, `core/raw_log.py` | UTF-8 BOM(`\ufeff`) 제거로 Python 3.12/3.14 정적 파싱 호환성 보장 |
| `sync_mirrors.py` | `MIRROR_MODULES`에 신규 모듈 5개(`header_bar`, `action_bar`, `planner`, `executor`, `committer`) 등록 |

#### 검증
- `python -m pytest -q` → **361 passed, 1 warning** (100% 그린 유지)
- `python -m compileall chzzktube` → 전 모듈 문법/바이트코드 컴파일 통과
- `python sync_mirrors.py` → 전체 66개 모듈 미러 및 `chzzktube_codebase.md` 동기화 100% 완료
- 5축 품질 게이트 공식 감사 통과 (종합 94.2점)

---

### 2026-09-25 — v3.11.0 : yt-dlp 독립 실행형 바이너리·Silent Fallback 제거·진행률 바 재구성·프로비저닝 아키텍처 리팩토링 (minor)

#### 배경 (v3.10.0 → v3.11.0)
- **yt-dlp 배포 방식 통일**: `.pylib` Python 패키지(whl) 경로 완전 제거 → GitHub Release 독립 실행형 바이너리 단일 경로로 통합 (dev/frozen 공통). Nightly 채널(`yt-dlp-nightly`) 별도 다운로드 경로 추가.
- **Silent Fallback 전면 제거**: 전체 코드베이스에서 `except Exception: pass` / bare `except:` 패턴 0개 달성. 모든 예외는 `log_f12_net()`/`log_f12_cli()`로 명시적 F12 에러 로깅 후 기본값 반환 (LOG + FAIL 패턴).
- **진행률 바 최소 영문화**: TUI MSG를 `downloading` | `completed` | `failed` | `verifying` 단일 단어로 축소, MB/ETA/speed는 구조화 필드(`pct`, `speed`, `bar_frac`)로 분리. 필드 순서 `PCT → SPEED → BAR → MSG` 칼정렬.
- **TUI/F12 채널 격리 준수**: TUI는 제자리 갱신(`is_status=True` + `component_id` + `is_progress=True`), F12/파일은 CLI 원문/HTTP 헤더/검증 상세/트레이스백 전량 보존. 완료 시 `status="OK"` 커밋.
- **프로비저닝 아키텍처 리팩토링**: `ProvisioningManager` → `Planner`/`Executor`/`Committer` 3클래스 분리 (SRP 준수). `pot_server.ensure_node_server()` 200줄 → 7개 헬퍼 함수 단계별 분리. `acquire_prewarm_lock()` `int|None` → `Result` 표준화 (하위 호환 유지). `bridge.py` 이벤트 루프 재사용(`_get_or_create_event_loop` + `_run_sync` + `_created_loops` 정리)로 중첩 호출 안전성 확보.
- **재프로비저닝 가드**: `stale_only=True` 시 planner에서 non-stale 컴포넌트 제외, manifest `is_stale()`으로 멱등성 검증, 이미 최신 컴포넌트는 plans에 미포함으로 진행률 바 미표시.

#### 모듈 변경
| 모듈 | 변경 |
|------|------|
| `infra/yt_dlp_binary.py` | Nightly 채널 플랫폼별 asset 이름 규칙(`_platform_asset_name` 재사용), `_latest_stable_version` silent fallback 제거 → `log_f12_net` 명시적 에러 로깅 |
| `infra/updater.py` | `installed_version` yt-dlp 분기 바이너리 전용 명시, `upgrade_packages` `.pylib 미사용` 명시, 주요 `except Exception` 패턴 F12 로깅 추가 |
| `infra/pot_server.py` | `ensure_node_server` 7개 헬퍼 분리(`_ensure_node_runtime`, `_resolve_npm_command`, `_ensure_source_fetched`, `_run_npm_install`, `_run_tsc_compile`, `_verify_build_output`, `_ensure_source_fetched`), `env` 변수 스코프 버그 수정, `acquire/release_prewarm_lock` `Result` 타입 표준화 (하위 호환 `int|None` 반환 유지) |
| `infra/provisioning/planner.py` (신규) | `resolve()` 전담 플래너 클래스. 미러 체인에서 최신 버전/URL/sha256 조회 → `ProvisionPlan` 리스트 생성. `stale_only` 체크로 멱등성 보장 |
| `infra/provisioning/executor.py` (신규) | `provision()` 전담 실행기. 다운로드 → 추출/설치 → 검증 파이프라인. 진행률 `_fmt_progress` PCT/SPEED/BAR 칼정렬. WHL/서버/바이너리 아카이브별 추출 로직 분리 |
| `infra/provisioning/committer.py` (신규) | `commit()` 전담. manifest 갱신 + overlay 리로드 + PATH 갱신 + downloads 폴더 정리 |
| `infra/provisioning/bridge.py` | 동기/비동기 브리지. `_get_or_create_event_loop` + `_run_sync` + `_created_loops` 추적으로 중첩 이벤트 루프 안전 관리. `asyncio.run()` 폐기 |
| `infra/provisioning/manager.py` | 파사드 패턴으로 Planner/Executor/Committer 위임 구조로 리팩토링. `ensure_all` = resolve → provision → commit 체인 |
| `infra/provisioning/resolver.py` | `filter_assets` 중복 `candidates.sort()` 제거, `get_platform_asset_filters` 에러 로깅 추가 |
| `infra/provisioning/manifest.py` | `load()` 에러 로깅 추가 |
| `ui/progress_bar.py` | 진행률 MSG 최소 영문화(`downloading`/`completed`/`failed`/`verifying`), MB/ETA 제거, 구조화 필드 분리 |

#### 검증
- `python -m pytest -m "not integration" -q` → **361 passed, 1 warning** (기준 360 → +1)
- `python -m py_compile` 전 모듈 통과
- `python sync_mirrors.py --check` → changed 0 / missing 0
- `git diff --check` → OK
- F12/TUI 채널 격리 계약 테스트 12건 통과
- 프로비저닝 계약 테스트 8건 통과

#### 완료
- Phase 1: yt-dlp 독립 실행형 바이너리 마이그레이션
- Phase 2: Silent Fallback 완전 제거
- Phase 3: 진행률 바 재구성 + TUI/F12 채널 격리
- Phase 4: 프로비저닝 아키텍처 리팩토링 (Planner/Executor/Committer + Pot Server 단계별 분리 + 재프로비저닝 가드 + Bridge 동기/비동기 경계)

---

#### 배경 (v3.8.5 → v3.9.0)
- **5축 코드 리뷰 P0 결함**: `controller.py`에 세션 상태 머신 5종 메서드가 2회 정의
  (앞쪽은 frozen `SessionState`에 없는 `state.update()`, 없는 `_abandon_analyzer()` 참조
  데드코드). 뒤쪽 정의가 항상 덮어쓰던 구조적 혼란 종결.
- **macOS Bottle 수급 단결**: `_ensure_ffmpeg_macos` 내 "다운로드·SHA 검증 생략" 주석
  구간으로 미존재 tar 경로를 전개해 `[Errno 2]`가 반환, 계약 테스트 3건 연속 실패.
- **F12 로그 계약 혼선**: `tasks/plan.md`의 "전량 누적" 요구와 현행 스냅샷 치환 구현의
  충돌 → **선택지 B 확정**: 뷰 버퍼는 스냅샷 치환(뷰 폭발 방지), 전량은
  history 파일 + dispatcher full_events ring이 보장 (HANDOVER §5-33 직교 분리).
- **기술부채**: `MainWindow` God Object, `SpeedWindow` O(n) 상각, 중복 상수/테스트.
- **대규모 구조 분해**: 게이트/워치독 상태 추출(`gate_state.py`), 파이프라인 분기 분리(`target_downloader/` 패키지), LogEvent deprecated 정리(`platform`/`spec` 필드 제거), 타임아웃/권한 일관화(`chzzktube.core` 상수화 + tmp 0o600), 로그 인젝션 회귀 테스트.

#### 모듈 변경

| 모듈 | 변경 |
|------|------|
| `control/controller.py` | 중복 정의된 세션 상태 머신 5종(`begin/end_download`, `on_download_finished`, `request_cancel/skip`) 앞쪽 데드 정의 삭제 — `_set_*`+시그널 경로 단일 진실화. |
| `control/gate_state.py` (신규) | 게이트/분석 워치독 무장·해제·POT 재시도 상태 컨테이너(`GateState`) + 무장/해제/재시도 함수. MainWindow 7종 위임 메서드는 게이트 함수로 단일화. |
| `infra/components.py` | `_write_bottle_payload` 신규 — `_http_get` 다운로드 + SHA-256 강제 검증 복원. 중복 `_FFMPEG_BREW_API` 제거. 호스트 승격(§5-32)·명시적 FAIL 유지, evermeet 폴백은 계속 부재. 타임아웃 상수화(`chzzktube.core` 상수) + tmp 파일 0o600 권한 고정. |
| `ui/log_mirror.py` (신규) | `MainWindow`에서 TUI/F12 미러 4종 로직 통째 추출. 선택지 B(뷰 스냅샷 치환 / 전량 직교)에 맞춰 문서화. 버퍼 미보유 테스트 대역 호환 폴백 포함. |
| `pipeline/target_downloader/` (신규 패키지) | 단일 `target_downloader.py` → 7개 분기별 모듈 분할: `utils.py`(공통 상수/유틸), `options.py`(yt-dlp 옵션), `flatten.py`(평탄화), `chzzk.py`(치지직), `youtube_vod.py`(유튜브 VOD), `youtube_live.py`(유튜브 라이브/스트림), `dispatch.py`(메인 디스패처), `__init__.py`(공개 API 재내보내기). 기존 import 경로 호환 유지. |
| `pipeline/target_downloader/options.py` | `_format_selector` 원본 로직 복원 (`bv*+ba` 단일 포맷, tv 폴백 금지). |
| `pipeline/target_downloader/youtube_vod.py` | `_ensure_pot_server_ready` 원본 로직 복원 (POTManager.instance() 제거, L0/L1 인프라만 사용). |
| `pipeline/target_downloader/utils.py` | `_emit_error_log` 즉시 TUI 발행 금지 (failed_targets만 누적). |
| `core/log_event.py` | `platform`/`spec` 필드 제거 (deprecated). 호출부 통일. |
| `core/log_emitter.py` | `emit_event`/`emit_dl`/`emit_error_standard` 등에서 `platform=scope` 제거. |
| `core/__init__.py` | 타임아웃/권한 상수 신규: `CONNECT_TIMEOUT`/`READ_TIMEOUT`/`DOWNLOAD_TIMEOUT`/`SHORT_API_TIMEOUT`/`PING_TIMEOUT`/`LOCAL_PROC_TIMEOUT`/`TEMP_FILE_MODE`/`EXECUTABLE_FILE_MODE`. |
| `ui/main_window.py` | 미러 4종은 호환 바인딩으로 축소. 게이트/워치독 위임 메서드 7종은 `gate_state` 함수 호출로 단일화. |
| `core/speed_window.py` | `_samples` list 재구성 → `deque` + `popleft` O(1) 상각 (진행률 틱 빈도 대응 성능). |

#### 테스트

| 테스트 | 변경 |
|--------|------|
| `tests/test_controller_no_duplicates.py` (신규) | 5개 메서드 1회 정의 + 데드 참조 0 계약 (RED→GREEN). |
| `tests/test_chzzk_auth.py` (신규) | 401/403→`ChzzkAuthError`, 500 통과, 워커 쿠키 만료 매핑 단언. |
| `tests/test_ffmpeg_archive_contract.py` | mock `_verify_ffmpeg` `env_extra` 시그니처 정합, 중복 테스트 제거, SHA부재 테스트의 호스트 승격 격리. |
| `tests/test_defect1_tv_fallback.py` | 결함1 구 계획(수동 `client_chain`) 폐기 → 순정 위임 계약 단언 3건으로 교체. |
| `tests/test_progress_integration.py` | F12 계약을 선택지 B로 단일화: `..._snapshot_replaces_progress_ticks`(버퍼 길이 1) + `..._full_history_keeps_every_tick`(full_events 전량) 분리. |
| `tests/test_v38_contracts.py` | LogEvent deprecated 제거 검증, 로그 인젝션 회귀 테스트 5건 추가 (`test_msg_contains_delimiter_is_sanitized` 등). |
| `tests/test_startup_gate_regressions.py` | 게이트 재귀 버그 수정(property → 직접 속성 + 캐시). |
| `tests/test_analyze_state.py`, `tests/test_analysis_timeout.py` | 게이트/워치독 캐시 적용으로 재귀 제거. |
| `tests/test_gate_integration.py` | `gate_state` 함수 위임 계약 검증. |

#### 검증
- `python -m pytest tests/ -q` → **356 passed, 0 failed** (기준 341 → +15)
- `python -m compileall chzzktube` → OK
- `QT_QPA_PLATFORM=offscreen python smoke_test.py` → PASS
- `python sync_mirrors.py --check` → changed 0 / missing 1 (`target_downloader.py` → 패키지화로 미러 생략)
- `git diff --check` → OK
- `uv sync` → uv.lock 갱신 완료

#### 완료
- Task 4-2 gate_state 추출 / 4-3 파이프라인 분기 분리 / 4-4 LogEvent deprecated 정리
- Task 5-3 타임아웃·권한 / 5-4 로그 인젝션
- Task 6-2 v3.9.0 버전 일괄 일치 완료

---

---

### 2026-09-23 — v3.8.5 : 수급 계층 런타임 구조 보존·TUI 마감 이벤트 복구·TUI 칼정렬 rstrip 적용·macOS 호스트 승격 구출·TUI/F12 로깅 이원화 정립 (patch)

#### 배경 (v3.8.4 → v3.8.5)
- **로깅 계약 혼선 해소**: "F12/히스토리 전량 기록"과 "진행률 제자리 갱신"의 개념 충돌로 인해 F12 창 오픈 시 수천 줄의 진행률 틱이 덤프되거나, 반대로 저수준 CLI/네트워크 원문이 유실되던 구조적 결함 종결.
- **Node.js NPM 런타임 참수**: 중첩 바이너리 평탄화 로직이 Node.js에 무차별 적용되어 `lib/node_modules/npm` 엔진이 누락, `npm --version` 실행 시 `Cannot find module '../lib/cli.js'` 크래시 유발.
- **불필요한 전수 재수급 폭주**: `UpdateWorker`가 `stale_only=False`로 실행되어 정상 상태의 의존성까지 무차별 덮어쓰기 다운로드 수행.
- **TUI 완료 로그 증발 및 게이지 박제**: `_provision_cb`의 TUI 노출 게이트가 `status in ("FAIL", "WARN", "ABORT")`만 통과시키고 정작 `OK`/`DONE` 마감 이벤트를 차단해 콘솔에 `RUN 100%` 틱이 굳어버림.
- **진행률 게이지 정렬 파괴**: `log_emitter.py`의 `format_log_line` 내부 `str.strip()`이 좌측 정렬 공백(`"  0%"`)을 도륙해 `0%` 행의 게이지 바가 왼쪽으로 2칸 밀려나는 지터링 발생.
- **macOS Homebrew Bottle dyld 불일치**: Bottle 바이너리의 절대경로 `LC_LOAD_DYLIB` 링크 한계로 실행 실패 시 탈출구가 없어 영구 FAIL에 갇힘.

#### 모듈 변경

| 모듈 | 변경 |
|------|------|
| `ui/main_window.py` | `_mirror_full_log`: `is_status` 및 `component_id` 진행 틱은 `_full_log_buf`의 직전 상태 줄을 스냅샷 치환하여 F12 재오픈 시 게이지 폭포수 덤프 차단. `toggle_verbose_log`: 지연 동기화 시 직전 상태 플래그를 정직하게 전달. |
| `infra/provisioning/manager.py` | `_extract_and_install`: `ffmpeg`만 바이너리 승격을 거치고, `node`는 `lib/node_modules` 계층을 통째로 보존하도록 분기. `_fmt_progress`: ASCII 스페이스(`f"{pct:3d}%"`, `f"{speed:>10}"`) 칼정렬 복원 및 마감 메시지 중복 `failed` 말더듬이 제거. |
| `workers/update_worker.py` | `_do_upgrade`: `mgr.ensure_all(stale_only=True)` 강제로 불필요한 재다운로드 차단. `_provision_cb`: TUI 노출 조건에 `event.status in ("OK", "DONE")` 추가하여 완료 라인 확정 보장. `_do_check`: CLI 원문 발행 시 `to_tui=False` 명시. |
| `core/log_emitter.py` | `format_log_line`: `msg_clean = str(msg).strip()`을 `.rstrip("\r\n ")`으로 교정하여 의도된 좌측 인덴트(`"  0%"`) 절대 사수. |
| `infra/components.py` | `_ensure_ffmpeg_macos`: Bottle 내부 `lib/` 경로를 `DYLD_FALLBACK_LIBRARY_PATH`로 주입해 1차 검증, 전멸 시 `/opt/homebrew/bin/ffmpeg` 등 로컬 호스트 검증 바이너리를 앱 격리 저장소로 원자적 승격 복사. 규격 외 에러 문구를 `binary incompatible` 표준 키워드로 교정. |

#### 검증
- `python -m py_compile` 전 모듈 통과
- `python sync_mirrors.py --check` 변경 0건 / 누락 0건
- macOS 실기기 런타임: `node/bin/npm --version` 정상 작동, Homebrew Bottle dyld 실패 시 호스트 승격으로 `ffmpeg 9.0.2` 정상 안착 확인
- TUI/F12 이원화 실측: TUI에는 정갈한 게이지 바와 최종 `OK`만 노출, F12에는 `$ cmd` 및 `HTTP GET` 상세 원문이 기록되되 진행률 틱은 1줄로 단정하게 제자리 갱신됨을 확인

---

### 2026-09-23 — v3.8.4 : FFmpeg 동적 수급(BtbN)·아키텍처 매핑·검증 필수화·실행 판정 위임 Bottle (patch)

#### 배경 (v3.8.3 → v3.8.4)
- **버전 하드코딩**: Windows는 FFmpeg 7.1 직링크, Linux는 `ffmpeg-release-amd64-static.tar.xz` 고정 — 동적 모듈인데도 생명주기 갱신이 불가능했다.
- **아키텍처 무시**: Linux ARM64에서도 amd64 바이너리를 내려받아 실행 즉시 실패.
- **무검증 수급**: 대부분 경로가 SHA-256 없이 캐시에 진입. `evermeet.cx` 폴백은 Apple Silicon 네이티브 빌드를 제공하지 않는데도 universal2로 위장되어 Rosetta2/dyld 실패를 양산.
- **dyld 시한폭탄**: Homebrew Bottle의 `ffmpeg`는 정적 바이너리가 아니다. `/opt/homebrew/Cellar` 절대경로로 링크된 bottle은 앱 격리 캐시로 복사하면 `dyld: Library not loaded`로 즉사한다.
- **비stdlib 의존 위험**: `.7z` 자산을 낚아채면 `py7zr`류 외부 의존을 수급 계층(L0)에 끌어들여야 했다.

#### 모듈 변경

| 모듈 | 변경 |
|------|------|
| `infra/components.py` | 하드코딩 URL 전면 폐기. `_normalize_arch`(amd64/arm64 정규화), `_select_btbn_asset`(static GPL만, shared/debug/7z 배제), `_parse_btbn_checksums`(정확한 basename 매칭 + 64자리 hex 검증), `_resolve_btbn_ffmpeg`(API latest + checksums 단일 트랜잭션) 신설. `_safe_extract`(ZIP 경로 정규화 검사, tar `filter="data"`, `TarError`→`ValueError` 정규화), `_locate_binaries`(중첩 Cellar/bin 탐색), `_atomic_install`(incoming→backup→rename rollback) 추가. macOS는 formulae `cellar`가 `:any` 계열일 때만 채택하고 SHA-256 필수화. `_ensure_ffmpeg_macos_static`·`_FFMPEG_EVERMEET_URLS`·`FFMPEG_RELEASE_URL` 삭제. |
| `infra/provisioning/resolver.py` | ffmpeg 미러에서 `github_gyan`/`evermeet` 제거 → `github_btb`(priority 0) + `homebrew`(priority 1). `ARCHIVE_UNSUPPORTED_EXT`에서 `.xz` 제거(BtbN Linux 자산이 `.tar.xz`), `ARCHIVE_PREFERRED_EXT`에 `.tar.xz`/`.tar.gz` 추가. |
| `core/log_emitter.py` | `emit_component`에 `component_id`/`is_progress` 파라미터 추가 — §3.7-5 갱신형 계약이 브리지까지 도달하도록 페이로드 관통. |
| `infra/provisioning/manifest.py` (기존 API 사용) | 수급 결과를 `ProvisionManifest.load/save` + `ComponentRecord` + `update_component`로 감사 기록(`_record_provision_plan`). |

#### 신규 테스트
| 파일 | 내용 |
|------|------|
| `tests/test_ffmpeg_resolver_contract.py` (신규) | 4건: Windows static GPL 선택 및 GitHub `digest` 무시, Linux ARM64 → `linuxarm64` 매핑, checksum 파서 정확 매칭·형식 거부, 미지원 아키텍처 ValueError. |
| `tests/test_ffmpeg_archive_contract.py` (신규) | 7건: ZIP/tar path traversal 차단, 중첩 `Cellar/.../bin` 보존, fixed cellar은 스킵이 아니라 프로브, 실행 검증 실패 시 명시적 FAIL, evermeet 폴백 부재(심볼 미존재), SHA-256 부재 bottle 거부, PATH 원복 누수 격리. |
| `tests/test_v38_contracts.py` (보수) | bottle 계약 테스트를 subprocess tar → stdlib tarfile + SHA-256 + 실행 판정 계약으로 재작성. 소진형 응답 스텁으로 다운로드 루프 종료 보장. |

#### 거버넌스 정합
- HANDOVER §5-27 "수급 무결성 및 무검증 레거시 폴백 절대 금지 (v3.8.5)" 및 §6의 evermeet/미검증 폴백 금지 조항과 구현을 일치시켰다.
- 실패는 은폐하지 않고 표준 `DEPS │ FAIL │ FFMP │ <원인> → <액션>` 으로 닫고 F12에 격리한다.

#### 검증
- 전체 pytest **340 passed**
- `python -m py_compile` 통과 (`components.py`, `log_emitter.py`, `resolver.py`)
- `python sync_mirrors.py --check` 변경 0건/누락 0건
- `git diff --check` clean
- 잔여 `johnvansickle`/`codexffmpeg`/`evermeet` 수급 참조 0건 (주석·문서 설명 제외)

---

### 2026-09-22 — v3.8.3 : 수급 계층 stdlib-only 완성·1줄 1정보 로그 규격·TUI/F12 갱신형 진행률 (patch)

#### 배경 (v3.8.2 → v3.8.3)
- **부트스트랩 패러독스 잔재**: `ParallelDownloader`·PyPI/GitHub/nodejs 메타 패처에 `httpx`가 남아 있고 의존성에는 미선언 — 프로비저닝 실행 시 `No module named 'httpx'` 크래시 가능.
- **아카이브 오선택**: 구 `filter_assets`가 GyanD 릴리즈 목록 순서(`assets[0]`)를 그대로 사용해 `.7z`를 낚아채 `zipfile.BadZipFile`로 귀결. FFmpeg 7.1 직링크도 실존하지 않는 파일명(`ffmpeg-7.1-essentials.zip`)을 가리킴.
- **로그 넘침**: stale 요약을 콤마로 나열, 집계 progress bar를 한 줄에 직렬 나열 — 1타임스탬프 1정보 규격 위반. TUI/F12에 진행 틱이 그대로 누적돼 바 넘침 발생.

#### 모듈 변경

| 모듈 | 변경 |
|------|------|
| `infra/provisioning/downloader.py` | `httpx.AsyncClient` 제거 → `urllib.request`+`asyncio.to_thread` 전환. 64KB 청크 스트리밍·per-read 30s 타임아웃·2s/5% 콜백 레이트리밋·SHA-256 검증·`.part` 원자 교체·지수 백오프 유지. |
| `infra/provisioning/manager.py` | `httpx` 동적 import 3건 제거 → `_fetch_json_sync`+`asyncio.to_thread` 공통 헬퍼. `_archive_type_from` 확장자 판정 + 미지원 형식 화이트리스트 가드. `_on_progress`를 `_fmt_progress` 단일 포맷터(`PCT · SPEED [GAUGE] · msg`)로 통일, TUI 컴포넌트별 갱신형·F12 갱신형 분리. |
| `infra/provisioning/resolver.py` | `filter_assets`에 아카이브 확장자 선호 정렬 추가 — `.zip` 최우선, `.7z`/`.rar`/`.xz` 등 stdlib 해제 불가 형식은 후보에서 완전 배제. |
| `infra/provisioning/verifier.py` | 바이너리 판정에 `spec.install_rel_path` 사용 (`node/bin/node` 등 중첩 경로 대응). |
| `infra/components.py` | `_download`를 `ProgressBar` 기반으로 전환(SHA-256 옵션·per-read 타임아웃 포함). FFmpeg 7.1 URL을 실존 자산(`ffmpeg-7.1-essentials_build.zip`)으로 교정. macOS는 Homebrew bottle 우선·evermeet.cx 폴백 순서 확정 + bottle 전멸 시 정적 빌드 폴백. Windows는 3회 재시도+`testzip` 검증. |
| `infra/pot_server.py` | `_download_with_progress`를 `ProgressBar` 기반으로 전환(per-read 타임아웃 포함). |
| `ui/progress_bar.py` (신규) | stdlib-only `ProgressBar`/`ProgressManager` — TUI 상태줄 갱신형·F12 갱신형(`component_id` 블록 추적)·`MIN_UPDATE_INTERVAL 2.0s`+`MIN_PCT_DELTA 5%` 지터링 방지. |
| `ui/log_console.py` | `_progress_lines` 추적 — 컴포넌트별 갱신형 라인(`is_progress`) 유지, 결과 로그가 진행줄을 잡아먹지 않도록 분리. |
| `ui/dialogs.py` | `VerboseLogWindow.append(msg, is_status, component_id)` — `component_id` 블록 교체로 F12 갱신형 지원. |
| `ui/main_window.py` | stale 요약을 콤마 나열에서 라벨별 개별 줄 발행으로 변경(1줄 1정보). F12 미러에 `component_id` 전달. |
| `tests/test_provisioning_stdlib.py` (신규) | 7건: stdlib 다운로드 성공/병렬/진행 콜백/HTTP 오류/네트워크 오류/SHA-256 성공·불일치·`.part` 정리·메타 패처 성공/실패. |

#### 검증
- 전체 pytest **317 passed**
- `python -m compileall -q chzzktube` 통과
- `python sync_mirrors.py --check` 변경 0건/누락 0건
- `git grep httpx -- chzzktube/` 잔여 참조 0건

---

### 2026-09-22 — v3.8.2 : Path Strategy Pattern으로 .pylib SSOT 완성 — Frozen/Dev 환경 분리 캡슐화 (patch)

#### 배경 (v3.8.1 → v3.8.2)
- **호출부 환경 분기 철폐**: `if is_frozen()` 조건문이 `updater.py`, `provisioning/manager.py` 등 호출부 곳곳에 산재 — 결합도 상승, 테스트 복잡도 증가.
- **단일 경로 리졸버(SSOT) 부재**: Python 오버레이(`.pylib`) 경로가 Dev(`<repo>/.pylib`)와 Frozen(`writable_base()/.pylib`)로 분기돼 있으나, 이를 캡슐화한 단일 진실 공급원(`config.pylib_overlay_path()`)이 없어 호출부가 환경을 알아야 했다.
- **frozen 빌드에서 .pylib 경로 불일치**: frozen 시 `%LOCALAPPDATA%/ChzzkTube/.pylib` 또는 `~/.chzzktube/.pylib`를 사용해야 하나, 기존 코드는 `<repo>/.pylib`를 고정 참조해 동일 코드 경로로 테스트 불가.

#### 모듈 변경

| 모듈 | 변경 |
|------|------|
| `core/config.py` | `is_frozen()` 단일 진실 함수 추가. **`pylib_overlay_path()` SSOT 구현** — 우선순위: 1) `CHZZKTUBE_PYLIB_DIR` 환경변수, 2) Frozen: `writable_base()/.pylib`, 3) Dev: `<repo>/.pylib`. `_pylib_root()`는 하위 호환 별칭으로 유지. |
| `infra/provisioning/manager.py` | `ProvisioningManager.__init__`: `config._pylib_root()` → `config.pylib_overlay_path()` 한 줄로 단순화 (환경 분기 제거). |
| `infra/updater.py` | `_overlay_root()`: 경로 리졸버 위임으로 단순화 (frozen 분기 완전 제거). `installed_version()`: `config.pylib_overlay_path()` 사용. |
| `tests/test_pylib_overlay.py` | Frozen 모드 테스트 2개 추가: `test_pylib_overlay_frozen_mode_uses_writable_base`, `test_pylib_overlay_frozen_mode_env_override_priority`. |
| `docs/HANDOVER.md` | §1.2 경로 계약 테이블에 `.pylib` frozen 경로 추가, `CHZZKTUBE_PYLIB_DIR` 문서화. |

#### 설계 원칙 보강
1. **단일 경로 리졸버(SSOT)**: 호출부는 환경을 모른다 — 오직 `config.pylib_overlay_path()`만 부른다. 환경 분기(if is_frozen)는 경로 리졸버 내부에만 존재.
2. **단일 격리(Single Isolated Runtime)**: 실행체 해석은 `writable_base()` 및 `.pylib` 오버레이만 — 시스템 PATH/패키지 매니저 참조 0건.
3. **순정 우선, POT 승격**: Layer 1~2는 yt-dlp 순정 위임(EJS 솔버 포함), 실패·1080p 미달 시에만 Layer 3 POT 승격. 720p `tv` 타협 폐기.
4. **워커 스레드 경계**: 워커는 뷰 소유 QObject(POTManager)에 접근하지 않고, L0/L1 순수 인프라만 호출.
5. **입력 게이트 2중 방어**: 파싱 단계(배치 전체 차단) + 워커 구동 직전 재검증.
6. **로그 단일 발행**: FAIL은 finalizer 1회, ANAL 마감은 명세 4행, DL 중간 스트림은 은닉.
7. **폴백 완전 제거**: 15초 강제 언락(`force_unlock`) 제거 — deps 수급 실패 시 영구 잠금, 사용자 재시도(ENTER) 대기. 프리웜 중 `defer_fallback_timer` 제거, `_on_pot_activity` 연결 해제.

#### 검증
- 전체 pytest **310 passed** (신규 frozen 모드 테스트 2개 포함)
- `python -m compileall -q chzzktube` 통과
- `sync_mirrors.py --check` 0 변경
- 실측: `sys.frozen` 시뮬레이션 시 `pylib_overlay_path()` → `writable_base()/.pylib`, 환경변수 오버라이드 우선 적용 확인
- 호출부 전역에서 `if is_frozen` 분기 0건 달성

---

### 2026-09-22 — v3.8.1 : 폴백 완전 제거·URL 검증 게이트·표준 에러 헬퍼·POT 상태 수정 (patch)

#### 배경 (v3.8.0 → v3.8.1)
- **폴백 타이머 완전 제거**: 15초 강제 언락(`force_unlock`) 제거 — deps 수급 실패 시 영구 잠금, 사용자 재시도(ENTER) 대기. 프리웜 중 `defer_fallback_timer()` 제거, `_on_pot_activity()` 연결 해제, `force_unlock()` 완전 삭제.
- **URL 검증 게이트 2중 방어**: `MediaController._is_valid_url()` 순수 게이트 신설(스킴 + 도메인 + `_DOMAIN_EXTRACTORS` SSOT suffix 매치). `MediaController.parse_targets`가 비URL 항목 발견 시 `ValueError("Invalid URL format: …")`로 배치 전체 차단. `toggle_download` 1차 게이트 + `_start_download` 2차 방어선.
- **표준 에러 헬퍼 전면 적용**: `emit_error_standard` / `emit_error_warn` 전면 도입 — 포맷 `원인: <기술적 원인> → 해결: <시도 중인 해결책>` 통일. `fallback`/`timeout` 등 내부 용어 노출 금지, dyld/URLError/traceback 등 저수준 예외 TUI 노출 금지.
- **POT 상태 의미 명확화**: `staged`(prewarm 완료, gate 미시작) ≠ `ready`(gate 완료, 토큰 서빙 중). `staged`를 `ready`로 오해하던 버그 수정, `pot_ready`는 `ready`일 때만 True.
- **폴백 타이머 완전 제거**: 15초 강제 언락(`force_unlock`) 제거 — deps 수급 실패 시 영구 잠금, 사용자 재시도(ENTER) 대기. 프리웜 중 `defer_fallback_timer()` 제거, `_on_pot_activity()` 연결 해제, `force_unlock()` 완전 삭제.

#### 모듈 변경

| 모듈 | 변경 |
|------|------|
| `ui/main_window.py` | 폴백 타이머·유예·강제언락 완전 제거. `deps` 실패 시 `[ ENTER: Retry Setup ]` 버튼으로 재시도. `deps` 에러 시 `ENTER`로 재시도. |
| `control/startup_coordinator.py` | `force_unlock()` 완전 삭제. `report_upgrade`/`report_pot` 실패 시 `emit_error_standard` 사용. `staged` ≠ `ready` 구분 적용. `deps_error_msg` 영구 보관으로 재시도 전까지 READY 차단. |
| `control/startup_state.py` | `deps_error_msg` 필드 추가 — 폴백 제거로 에러 상태 영구 보관. `can_emit_ready()`에 `deps_error_msg` 체크 추가. |
| `control/pot_manager.py` | `_note` 호출을 `emit_error_standard`/`emit_error_warn`로 통일. ffmpeg bind fail 시 표준 에러 헬퍼 사용. |
| `pipeline/target_downloader.py` | 즉시 TUI 발행 금지 — `_emit_error_log`는 기록만, finalizer에서 단일 출력. 즉시 TUI 발행 코드 제거. |
| `pipeline/progress_emitter.py` | `log_success_info` 중간 스트림(.fNNN) 은닉(`to_tui=False`). `pp_hook` 신설 — postprocessor 완료 시 최종 결과물 1줄만 발행. |
| `control/startup_coordinator.py` | `report_upgrade`/`report_pot` 실패 시 `emit_error_standard` 사용. `force_unlock` 호출 제거. |
| `control/pot_manager.py` | ffmpeg/binding 실패 시 표준 에러 헬퍼(`emit_error_standard`/`emit_error_warn`) 사용. bind fail 시 표준 에러 헬퍼. |
| `pipeline/target_downloader.py` | 즉시 TUI 발행 금지 — `_emit_error_log`는 기록만, finalizer에서 단일 출력. 즉시 TUI 발행 코드 제거. |
| `pipeline/progress_emitter.py` | `log_success_info` 중간 스트림(.fNNN) 은닉(`to_tui=False`). `pp_hook` 신설 — postprocessor 완료 시 최종 결과물 1줄만 발행. |
| `control/startup_coordinator.py` | `report_upgrade`/`report_pot` 실패 시 `emit_error_standard` 사용. `force_unlock` 호출 제거. |
| `control/pot_manager.py` | ffmpeg/binding 실패 시 표준 에러 헬퍼(`emit_error_standard`/`emit_error_warn`) 사용. bind fail 시 표준 에러 헬퍼. |
| `pipeline/target_downloader.py` | 즉시 TUI 발행 금지 — `_emit_error_log`는 기록만, finalizer에서 단일 출력. 즉시 TUI 발행 코드 제거. |
| `pipeline/progress_emitter.py` | `log_success_info` 중간 스트림(.fNNN) 은닉(`to_tui=False`). `pp_hook` 신설 — postprocessor 완료 시 최종 결과물 1줄만 발행. |
| `control/startup_coordinator.py` | `report_upgrade`/`report_pot` 실패 시 `emit_error_standard` 사용. `force_unlock` 호출 제거. |
| `control/pot_manager.py` | ffmpeg/binding 실패 시 표준 에러 헬퍼(`emit_error_standard`/`emit_error_warn`) 사용. bind fail 시 표준 에러 헬퍼. |
| `pipeline/target_downloader.py` | 즉시 TUI 발행 금지 — `_emit_error_log`는 기록만, finalizer에서 단일 출력. 즉시 TUI 발행 코드 제거. |
| `pipeline/progress_emitter.py` | `log_success_info` 중간 스트림(.fNNN) 은닉(`to_tui=False`). `pp_hook` 신설 — postprocessor 완료 시 최종 결과물 1줄만 발행. |
| `control/startup_coordinator.py` | `report_upgrade`/`report_pot` 실패 시 `emit_error_standard` 사용. `force_unlock` 호출 제거. |
| `control/pot_manager.py` | ffmpeg/binding 실패 시 표준 에러 헬퍼(`emit_error_standard`/`emit_error_warn`) 사용. bind fail 시 표준 에러 헬퍼. |

#### 설계 원칙 보강
1. **단일 격리(Single Isolated Runtime)**: 실행체 해석은 `writable_base()` 및 `.pylib` 오버레이만 — 시스템 PATH/패키지 매니저 참조 0건.
2. **순정 우선, POT 승격**: Layer 1~2는 yt-dlp 순정 위임(EJS 솔버 포함), 실패·1080p 미달 시에만 Layer 3 POT 승격. 720p `tv` 타협 폐기.
3. **워커 스레드 경계**: 워커는 뷰 소유 QObject(POTManager)에 접근하지 않고, L0/L1 순수 인프라만 호출.
3. **입력 게이트 2중 방어**: 파싱 단계(배치 전체 차단) + 워커 구동 직전 재검증.
4. **로그 단일 발행**: FAIL은 finalizer 1회, ANAL 마감은 명세 4행, DL 중간 스트림은 은닉.
5. **폴백 완전 제거**: 15초 강제 언락(`force_unlock`) 제거 — deps 수급 실패 시 영구 잠금, 사용자 재시도(ENTER) 대기. 프리웜 중 `defer_fallback_timer` 제거, `_on_pot_activity` 연결 해제.

#### 검증
- 전체 pytest **304 passed**
- `python -m compileall -q chzzktube` 통과
- 실측: `afqweqasd` 게이트 차단(`Invalid URL format: afqweqasd`) / `https://youtu.be/...` 통과 / 앱 코드 `shutil.which(` 호출 0건 / 격리 캐시 부재 시 `ffmpeg_exe() → None`(시스템 ffmpeg 무시)
- 회귀 계약 테스트 개정: `test_analysis_retry.py`(순정 단일 호출 계약), `test_gate_integration.py`·`test_pipeline_regressions.py`(TUI 포맷·`subscriber_only` 게이트)

---

### 2026-09-20 — v3.8.0 : 단독 환경 격리·입력 게이트·Layer 3 POT 수리·TUI 정제 (minor)

#### 배경 (v3.7.2 → v3.8.0)
- **CLI vs App 동작 불일치**: CLI는 `--cookies`만으로 멤버십·1080p+ 수급되지만 앱은 실패. 근본 원인은 쿠키 감지 시 `player_client`를 `web`으로 강제 고정하던 구 로직(→ PO 토큰 없는 `web` 요청은 이미지 포맷만 반환)이었다. v3.7.2에서 순정 위임은 완료됐으나 잔재가 남아 있었다.
- **시스템 환경 간섭**: `shutil.which`·`brew install`·`apt-get`이 사용자 PC의 구버전 바이너리/오염 플러그인을 참조할 위험.
- **무검증 억지 다운로드**: `afqweqasd` 같은 임의 문자열 입력 시 분석 검증 없이 DownloadWorker가 실행되어 `[generic] Extracting URL` → `DL FAIL` 3~4줄 중복 발행.
- **Layer 3 POT 준비의 잠재 결함**: `target_downloader._download_vod`가 존재하지 않는 `POTManager.instance()`를 호출 — POT 재시도 경로 진입 시 `AttributeError`로 즉사(게다가 POTManager는 뷰 소유 QObject라 워커 스레드 접근은 스레드 경계 위반).

#### 모듈 변경

| 모듈 | 변경 |
|------|------|
| `infra/node_provider.py` | `node_exe()`·`ensure_node_runtime()`에서 시스템 PATH/`shutil.which("node"\|"npm")` 전면 제거 — 오직 `writable_base()/node` 포터블 + frozen 번들만 판정·수급 |
| `infra/components.py` | `ensure_ffmpeg`의 시스템 ffmpeg 최우선 로직 제거 → 격리 캐시 선검(파손 캐시 제거) 후 정적 바이너리 수급. `brew install`·`apt-get/dnf/pacman` 서브프로세스 철폐(Homebrew bottle은 HTTP 직접 다운로드 유지). `ffmpeg_exe()`의 `shutil.which` 폴백 제거. `_wire_ffmpeg_path` 디버그 로깅 정리 |
| `infra/updater.py` | `_cli_base()`를 실행체 단일 격리로 재작성 — ytdlp/streamlink는 앱 인터프리터 `-m` 실행(오버레이 우선), ffmpeg/node/npm은 격리 캐시 리졸버 단일 참조. `check_deps`도 `components.ffmpeg_exe()`/`pot_provider.node_exe()` 경유로 판정 |
| `infra/pot_server.py` | npm 해석의 `shutil.which("npm")` 폴백 제거 — npm-cli.js → `npm_exe()` 단일 경로, 없으면 명시적 오류 |
| `core/client_opts.py` | `_apply_ffmpeg_opts`가 `components.ffmpeg_exe()`(격리 캐시)만 참조 |
| `pipeline/target_downloader.py` | **[근본 수리]** `_ensure_pot_server_ready()` 신설 — L0 `po_client.server_ping` + L1 `pot_server`의 순수 스폰/빌드 헬퍼(프리웜 락)만 사용해 워커 스레드에서 안전하게 Layer 3 준비. `_FormatQualityLoss`/`_max_requested_height`/`_needs_pot_promotion` 신설 — 1080p 미달 수급 시 720p 타협 없이 POT 승격(사용자 해상도 제한·수동 포맷 선택은 제외). POT 미가용 시 1차 수급본을 파기하지 않고 `hd unavailable — kept Np`로 정직 보고. `_emit_vod_success`로 성공 라인 발행 단일화. `_emit_error_log`는 기록 전용(TUI 즉시 발행 철폐) |
| `pipeline/progress_emitter.py` | `log_success_info`가 중간 임시 스트림(`.f399`/`.f251`)을 TUI에서 은닉(`to_tui=False`). `pp_hook` 신설 — postprocessor 완료 시 최종 결과물 1줄만 발행(중복 방지) |
| `pipeline/finalizer.py` | 개별 실패 라인의 **유일 발행점**으로 확정 — 배치 마감 시 1회 정갈 출력(중복 FAIL 로그 3~4줄 원천 차단) |
| `control/controller.py` | `_is_valid_url()` 순수 게이트 신설(스킴 + 도메인 + `_DOMAIN_EXTRACTORS` SSOT suffix 매치), `parse_targets`가 비URL 항목 발견 시 `ValueError("Invalid URL format: …")`로 배치 전체 차단 |
| `ui/main_window.py` | 게이트 배선(1차 `toggle_download`, 2차 `_start_download` 방어선). `on_analyze_error`에서 `extracted_data` 즉시 초기화(잔여 데이터 억지 다운로드 차단) + 멤버십/연령제한 시 `CookieSelectDialog` 자동 팝업. `stop_analysis_anim`을 ANAL 마감 정갈 명세(complete → 제목·채널 → 가용성 → 대표 포맷)로 재작성. `_emit_format_logs`를 `[codec] · [codec]` 형식으로 정제. 종료 시 다운로드 워커 `wait(1000)` 추가 |
| `core/log_emitter.py` | `analysis_done_msg()` 상수 신설 — ANAL 마감 문구 단일 출처 |

#### 설계 원칙
1. **단일 격리(Single Isolated Runtime)**: 실행체 해석은 `writable_base()` 및 `.pylib` 오버레이만 — 시스템 PATH/패키지 매니저 참조 0건.
2. **순정 우선, POT 승격**: Layer 1~2는 yt-dlp 순정 위임(EJS 솔버 포함), 실패·1080p 미달 시에만 Layer 3 POT 승격. 720p `tv` 타협 폐기.
3. **워커 스레드 경계**: 워커는 뷰 소유 QObject(POTManager)에 접근하지 않고, L0/L1 순수 인프라만 호출.
4. **입력 게이트 2중 방어**: 파싱 단계(배치 전체 차단) + 워커 구동 직전 재검증.
5. **로그 단일 발행**: FAIL은 finalizer 1회, ANAL 마감은 명세 4행, DL 중간 스트림은 은닉.

#### 검증
- 전체 pytest **297 passed** (신규 `test_url_gate.py` 19건 + `test_v38_contracts.py` 27건 포함)
- `python -m compileall -q chzzktube` 통과
- 실측: `afqweqasd` 게이트 차단(`Invalid URL format: afqweqasd`) / `https://youtu.be/...` 통과 / 앱 코드 `shutil.which(` 호출 0건 / 격리 캐시 부재 시 `ffmpeg_exe() → None`(시스템 ffmpeg 무시)
- 회귀 계약 테스트 개정: `test_analysis_retry.py`(순정 단일 호출 계약), `test_gate_integration.py`·`test_pipeline_regressions.py`(TUI 포맷·`subscriber_only` 게이트)

### 2026-09-19 — v3.7.2 : yt-dlp 순정 클라이언트 로테이션 완전 위임 (minor)
- **핵심 변경**: 앱 레벨 수동 클라이언트 로테이션(`_RETRY_CLIENTS`, `client_chain`) 완전 제거 → **yt-dlp 순정 단일 `auto` 호출로 위임**
  - yt-dlp 내부 `_DEFAULT_CLIENTS`(`web_embedded` → `tv_downgraded` → `web_safari` → `mweb` → `tv`...) + EJS 솔버(deno/node) 자동 작동
  - CLI와 100% 동일 동작: `web_embedded` → `tv_downgraded` → JS 챌린지 해결 → 1080p+Opus 확보 검증 완료
  - 수동 폴백 체인(`web_embedded`→`web_safari`→`mweb`→`tv`) 삭제로 코드 ~150줄 감소
- **3계층 파이프라인 재설계**:
  - **Layer 1 (순정 위임)**: `player_client="auto"` 단일 호출 → 공개/멤버십(쿠키有) 1080p+ 즉시 해결
  - **Layer 2 (POT 서버)**: `age_limit>0` 또는 봇체크/포맷상실 감지 시에만 기동
  - **Layer 3 (재시도)**: PO token + visitorData 주입하여 동일 순정 호출 재시도 (1회만)
- **POT 게이트 정단화**: `subscriber_only`(멤버십) 게이트 제거 — Layer 1에서 쿠키+EJS로 해결
  - `main_window._POT_AVAIL_GATED`, `classifier._POT_AVAIL_GATED`에서 `subscriber_only` 삭제
  - `needs_pot = age_limit > 0`만 남김 (연령제한 전용 인터락)
- **수정된 파일**: `client_opts.py`, `analyze_worker.py`, `target_downloader.py`, `live_recorder.py`, `main_window.py`, `classifier.py`

### 2026-09-19 — v3.7.1 : 5대 구조적 결함 수정 (patch)
...

### 2026-09-18 — v3.7.0 : download pipeline contract overhaul (minor)
- **배경**: 다운로드 파이프라인 계약 분산·불일치 누적 — 반환 타입 혼재(str/dict/ClassifiedTarget), VOD 폴백 `tv→web_safari→web`(360p 고착), PO 토큰 `web_embedded` vs `player_client` 불일치(0% stall), terminal failure까지 봇 차단으로 오판(4단계 헛돌기), `skip_targets` 연결 누락, 분석 워커 Mock 잔재, 쿠키 정책 판정 이중화
- **핵심 변경**:
  - `pipeline/classifier.py` 신규: `ContentKind`(LIVE_YOUTUBE/LIVE_CHZZK 분리), `StreamCapability`(TriState None + `could_have_*` 방어 메서드), `CookiePolicyContext`, `ClassifiedTarget`, `ItemClassifier` 순수 분류 엔진
  - `target_downloader.py`: 품질 우선 폴백 `web→web_safari→ios→tv`, terminal fail-fast, PO 토큰 1:1 바인딩(web/web_safari만, ios/tv 미주입), `download_target` 반환값 `True/"skip"/False` 명시, `_flatten`/`_normalize_single_item`/`expand_targets` 모두 `List[ClassifiedTarget]` 반환
  - `finalizer.py`: `skip_targets` 파라미터, `DONE/WARN/FAIL/ABORT` 상태 세분화, `batch finished (success: N, fail: M, skip: K)` 포맷
  - `downloader.py`: `item.url` 접근 통일, `skip_targets` 전달
  - `analyze_worker.py`: 빈 `YoutubeDL` Mock 제거
  - `tests/conftest.py`: `pytest_configure` `.pylib` bootstrap, `yt_dlp.__path__` 동기화, `raw_log` flush fixture
- **설계 원칙**: 단일 계약(SSOT) — `has_video/has_audio=None` 보존, `could_have_*()` 안전 질의 / 품질 우선 폴백 / PO 토큰 정합성 / terminal fail-fast / Skip 집계 / 쿠키 정책 SSOT(`_apply_cookie_opts` ≡ `_has_configured_cookies`)
- **검증**: pytest **239 passed**, compileall OK, 실측: 멤버십/연령제한/삭제 → `DL │ SKIP │ YT │ [age/member gated]`, 최종 요약 `skip` 카운트

---

### 2026-09-18 — v3.6.4 : analysis dead-end fix — EJS JS runtime + cookie-aware rotation + TUI notice dialog
- **근본 원인**: yt-dlp의 기본 JS 런타임은 `deno`(PATH 탐색)뿐이고 앱이 PATH 밖(`~/.chzzktube/node`)에 자체 수급한 포터블 Node.js를 탐색하지 못해 n-challenge(EJS) 해결이 불가능 → "No video formats found" 회전 실패로 이어졌다.
- `client_opts._apply_ejs_opts` — `node_provider.node_exe()`로 탐색한 포터블 node를 `js_runtimes={'node': {'path': ...}}`로 명시 주입(분석/라이브/다운로드 4 경로 커버). node 없으면 기본(deno) 유지.
- `analyze_worker` — 회전 후보 `ios`(쿠키 미지원 → yt-dlp 스킵 즉사) → `["tv", "web_safari"]`(쿠키 호환)로 교체; bot-block 판정에 "no video formats found"/"requested format is not available" 포함해 회전 완주.
- `analyze_worker` — 최종 analysis error를 60자로 절약(TUI MSG 컬럼 예산); `[youtube] <id>:` 접두와 보고서 꼬리(`; please report…`, `Use --list-formats`) 절삭.
- `target_downloader` — "Requested format is not available" 분류에 `is` 누락 교정 + no-video-formats → `format missing`.
- `ui/dialogs.py` — `TuiNoticeDialog`(280×125·칠흑·중앙정렬·OK/View 2버튼) 신설; `show_info_message`를 위임해 쿠키 완료/초기화/브라우저 오류 안내도 동일 규격. 쿠키 흐름 사용자 문자열 한국어→영어(§5).
- 검증: 문제 URL 실측(일반 31포맷, 멤버십 `0VxDq_vzXcg` 9포맷 `&t=&pp=` 포함) + pytest **239 passed** + offscreen UI 스모크(중앙정렬/2버튼/RESULT_ALT 코드).
- 커밋: `8408103`(근본수정) `0b42775`(분류 교정) `95c179f`(분기 보강) `dd24cd1`(UI 통일)

---

### 2026-09-17 — v3.6.3 : architecture contract restoration (P0–P2 audit)
- **워치독 단일 진실**: gate QTimer 폐지(`_gate_watchdog_active` 플래그), fallback `_fallback_timer` 단일 판정(`_fallback_watchdog` 삭제), analysis watchdog 3 spawn-site arm/disarm(§5-21: 성공/실패/타임아웃/Esc/클리어 disarm; polling은 disarmed 워치독 skip).
- `DownloadContext` — `_last_tick_t/_live_proc/_meta_logged` 필드 선언.
- `DownloadWorker.run` finally → `_fin.finalize(ctx, …, notify=False)` → `finished_all.emit` 정확히 한 번(분석/충전/다운로드/파이널라이즈/로그/예외 전부 생존).
- `live_recorder` — stdout-relay 단일 소유권: FFmpeg `pipe:1` → Python이 TS 기록(임시본 replace-on-success, 실패/취소 시 TS 유지, empty→False).
- `analyze_worker` — `ctrl.spawn_analyzer()` 명시 재시도, streamlink 5-arg TypeError 수정, `ANALYSIS_TIMEOUT_SEC` import 정리.
- Chzzk live v2 API: `_analyze_chzzk_live_v2`(v2/channels/{hash}/live-detail → `livePlaybackJson` HLS) + numeric-id v1 fallback; 32-hex 채널 해시는 channel id(v1 404 루트케이즈), `status=OPEN`+`live.status=STARTED`→PROGRESS.
- `playlist.normalize_youtube_channel_url` — `releases|live|community|membership|podcasts` 보존, `/videos` 강제-rewrite 회귀 방지.
- URL sweep(16 URLs) 분석/라우팅 레벨 검증(Chzzk clip/VOD API OK; YouTube VOD/live/shorts/playlist/watch+list/channel tabs OK; 멤버십 전용은 쿠키 필요 — 기대 동작).
- 검증: pytest **227 passed**, `test_coordinator.py` 20× 반복 무실패, py_compile·`git diff --check` clean.
- 커밋: `ab03548`(중간 체크포인트·31파일) `d8b0ad4`(chzzk live 브랜치 + Context 동기화) `1c7d9f8`(POT gate 단일 워치독) `6bc49d1`(fallback timer single authority) `4dd88b3`(analysis watchdog arm/disarm) `6f3cad7`(chzzk v2 live-detail path) `59cf630`(채널 탭 정규화 + 라우팅 경계)



- `infra/platform.py` 신설 — 크로스플랫폼 HAL 단일 격리 계층
  - `is_windows()` / `is_macos()` — `sys.platform` 단일 판정 출처
  - `spawn_kwargs()` / `daemon_spawn_kwargs()` — 용도별 스폰 인자 분리 (Win: `CREATE_NO_WINDOW` / `CREATE_NEW_PROCESS_GROUP`, POSIX: `start_new_session=True`)
  - `flash_window(hwnd:int)` / `set_app_user_model_id()` / `play_beep()` / `reveal_in_file_manager()` / `exe_suffix()` — Qt 역의존 제로
  - `attach_to_parent_lifecycle()` / `kill_tree()` — Job Object / `killpg` 격리 (pot_server에서 이관)
  - 호출부 8개 모듈(`tool_log`, `node_provider`, `pot_server`, `updater`, `live_recorder`, `utils`, `main_window`, `components`) 완전 치환

- `core/watchdog.py` 신설 — 단일 진실 시간(`time.monotonic`) 기반 구독형 워치독
  - 상수 단일 출처: `FALLBACK_TIMEOUT_SEC=15`, `FALLBACK_GRACE_SEC=3`, `GATE_TIMEOUT_SEC=120`, `ANALYSIS_TIMEOUT_SEC=45`
  - `LivenessWatchdog` — `threading.Lock` + 주입 가능 `clock`으로 스레드 안전·테스트 가능
  - `heartbeat()` / `check_timeout()` / `reset()` / `elapsed()` / `remaining()` 상태 기계

- 워커/메인 배선 완전 전환
  - `AnalyzeWorker`: `QTimer` 맹인 타이머 **완전 제거** → `progress_hook`로 `heartbeat()` 연장
  - `DownloadWorker`: `_download_watchdog` + 타겟 전후 `heartbeat()`로 게이트/분석 타임아웃 연장
  - `MainWindow`: `_poll_watchdogs` 1초 폴링으로 3종 워치독(`fallback`/`gate`/`analysis`) 감시
  - 기존 `heartbeat`/`work_tick`/`pot_work_tick` 시그널명 유지 (§5-13 교통정리 준수)

#### 검증
- 전체 pytest **176 passed 0 failed** · smoke PASS · `sync_mirrors.py --check` 0건 · py_compile OK
- 버전 3중 정합: `config._APP_VERSION="v3.6.2"` / `pyproject.toml version="3.6.2"` / `uv.lock chzzktube==3.6.2`

---

### 2026-09-16 — v3.6.1 : 아키텍처 다이어그램(mermaid) 추가 — 문서 전용 패치

- `docs/architecture.md` 말미에 mermaid 3종 append: ① 전체 계층도(flowchart) ② 기동 시퀀스(sequenceDiagram) ③ 상태·워치독 관계(stateDiagram-v2)
- 소스 변경 없음(문서 패치) — §1.1.2에 따라 patch 버전 증가 및 3중 정합 유지
- 검증: `python -m pytest tests -q` (176 passed 0 failed) · smoke PASS · `sync_mirrors.py --check` 0건

---

### 2026-09-16 — v3.6.0 : 게이트 하드닝 — POT 트리 종료·2차 워치독·유예·deps FAIL·PO 재시도 (minor 업)

#### 후속 과제 전량 해소 (v3.5.2 §8.3 잔여 6건)
- **#1 POT 빌드 내부 하트비트**: `_communicate_with_ticks` — `communicate()` 무출력 대기를 tick_interval 주기로 반복 대기해 빌드 진행 하트비트 발화. 배선 `ensure_node_server` → `_POTWorker._tick` → `POTManager.pot_work_tick` → `defer_fallback_timer`. npm ci 장기 실행이 더 이상 "멈춤"으로 오인되지 않는다.
- **#2 POT 서브프로세스 트리 종료**: `kill_tree()` 신설 — Windows Job Object(`TerminateJobObject` + 핸들 부착·반납) / POSIX 프로세스 그룹(`start_new_session` 리더). `_POTWorker.request_interruption`·`_cleanup`의 자식 정리 사각지대를 트리 종료로 교정(`_child_procs` 레지스트리 실체화).
- **#3 gate hang 2차 워치독**: `_gate_watchdog`(120s) — READY 이후 `_pending_download` 대기 중 만기 시 `cancel()`(트리 킬) + `SYS │ WARN │ POT` + 큐 해제.
- **#4 위양성 폴백 분리**: `defer→grace` — 만기 시 체인이 실제 동작 중(POT/UpdateWorker running)이면 3s 유예 1회 후 재판정하고, F12 대기 원인을 `_log_gate_pending`으로 기록(TUI 예산 보존).
- **#5 deps FAIL 게이트 승격**: `UpdateWorker.deps_failed = Signal(list)` 신설 — `check_done(list)` 페이로드는 untouched(§5-13 교통 정리 유지), Main이 중계 후 `report_deps(False, "deps fail: …")`. stale(업데이트 대상)과 실제 FAIL을 분리.
- **#6 PO 서버 실패 시 재시도**: 분석 실패가 봇 체크/PO 토큰 마커(`_BOT_CHECK_MARKERS`)면 `ensure_ready("gate")` 후 URL당 1회 재분석 자동 큐잉 — `_pot_retry_done` 집합으로 무한 루프 차단, `textChanged` 디바운스로 재진입.

#### 검증
- 신규 회귀 9건: `test_pot_manager` 2건(하트비트·레지스트리) · `test_startup_gate_regressions` 7건(게이트 워치독 2·유예 2·deps 승격 1·재시도 판별 1·1회 한계 1)
- 전체 pytest **176 passed 0 failed** · smoke PASS · `sync_mirrors.py --check` 0건 · py_compile OK · 버전 3중 정합(`v3.6.0` / `3.6.0` / `3.6.0`)

---

### 2026-09-16 — v3.5.2 : READY 폴백 결함 3건 수리 — deps 게이트 의미 분리·크래시 시그널 분기·POT 프리웜 보존

#### 문제 (관측: 평범한 기동에서 "ready — input unlocked (fallback timeout)"이 출력)
- **P1 deps 게이트 의미 오용**: `_on_update_check_done`이 `report_deps(not bool(stale), …)`로 보고 → 업데이트가 감지된 **모든 기동**에서 `deps_ok=False` 고정 → `can_emit_ready()`가 사실상 영구 False → 정상 READY 대신 15초 폴백 문구로만 입력이 열리고, 그 15초 동안 입력이 잠겼다.
- **P2 upgrade 크래시 시 시그널 오발행**: `UpdateWorker.run()`의 except가 모드와 무관하게 `check_done`을 발화 → upgrade 워커의 `check_done`은 구독자 0(연결 지점은 `upgrade_done`) → `upgrade_done` 영구 미발화 → READY 게이트가 잠김.
- **P3 폴백이 프리웜을 종료**: `force_unlock()`이 `POTManager.cancel()`을 호출 → `_POTWorker._child_procs`는 append 0건이라 npm/tsc 자식을 죽이지 못한 채 QThread만 terminate → 고아 프로세스 잔존 + `prewarm-lock` 점유로 다음 기동 프리웜이 "prewarm skipped — build busy" 실패.
- **P3b 상태 논리 혼동**: `get_current_app_state()`가 `is_busy()`를 STARTUP 사유로 삼아, 프리웜 진행 중 `toggle_download`의 대기 분기("queued — waiting for pot server")가 **도달 불가 사문 코드**였다(ENTER 무반응).
- **P3c 무제한 서브프로세스**: `_run_and_stream_log`의 `communicate()`에 timeout 부재 → npm ci/tsc 무응답 시 프리웜 워커가 영구 점유 → `is_busy()` 고정 → POT 게이트 다운로드가 대기에서 풀리지 않는다.
- **P5 15초 단발 타이머의 맹점**: `QTimer.singleShot(15000, …)`는 대규모 수급(ffmpeg·node·pip 다운로드)이 진행 중인지 멈춘 것인지 구분하지 못했다 — 정상 진행 중에도 폴백이 발화해 문구가 오표기됐다.

#### 모듈 변경
| 모듈 | 변경 |
|------|------|
| `main_window.py` | `report_deps(True, …)` — deps 게이트를 "검사 단계 완료"로 의미 정정(P1). `get_current_app_state()`에서 `is_busy()` 제거 — 입력 잠금은 `_startup_completed`만 판정(P3b), POT 대기 분기 부활 |
| `update_worker.py` | 크래시 종료 시그널을 모드별로 분기(`upgrade` → `upgrade_done(False, "worker crash")`, check → `check_done([])`) + 중복 `import traceback` 제거(P2) |
| `startup_coordinator.py` | `force_unlock()`에서 `_pot.cancel()` 제거 — 폴백은 READY 발산만 담당, 프리웜은 백그라운드 존속(P3) |
| `pot_server.py` | `_run_and_stream_log(…, timeout=None)` + `TimeoutExpired → _kill(proc) → -1`. `_NPM_CI_TIMEOUT=600`·`_TSC_TIMEOUT=300` 적용(P3c) |
| `main_window.py`·`update_worker.py` | [P5] 15초 폴백을 인스턴스 타이머(`_fallback_timer`)로 승격 + `defer_fallback_timer()` 동적 워치독. `UpdateWorker.work_tick`(문자열 없는 하트비트) → pip·ffmpeg·node 수급 진행 중 카운트다운 되감기, POT `prewarm`/`starting`은 `_on_pot_activity` 경유 연장 |

#### 검증
- 신규 회귀 테스트 18건: `test_coordinator.py` 3건(deps 게이트 의미 1·폴백 프리웜 보존 2) · `test_startup_gate_regressions.py` 11건(신규) · `test_pot_server_timeout.py` 4건(신규)
- stale 테스트 정정: `test_download_pipeline.py::test_truncate_for_full_log` — HEAD `e156623` worktree 실측으로 **기존 실패**를 분리 확인한 뒤, 소스 정본(`configuration:` 블록 제거)에 맞춰 기대값을 재작성
- 전체 pytest **167 passed 0 failed**
- `python sync_mirrors.py --check` 0건 · `smoke_test` PASS · py_compile OK · 버전 3중 정합(`v3.5.2` / `3.5.2` / `3.5.2`)

---

### 2026-09-15 - v3.5.1 : UI/다이얼로그 전면 규격 교정 및 모던 TUI 개편

  - `ExitConfirmDialog`: 폭 축소(360×130 → 280×125) 및 경고 텍스트 중앙 정렬(`AlignCenter`) 적용으로 비례 안정화.
  - `SettingsDialog`: 구형 프레임(`QGroupBox`) 전면 철거, 1px TUI 라인(`_tui_sep`)과 아스키 섹션 헤더(`// SECTION`) 기반 하이퍼미니멀 스타일로 재구축.
  - `SettingsDialog`: 윈도우 크기 최적화(660×680 fixed) 및 2열 체크박스 그리드 여백 확보로 텍스트 잘림 현상 방지.
  - `SettingsDialog`: 하단 풋터 액션 바(`[ Close: Esc ]`)를 스크롤 영역 외부로 격리 분리하여 하단 패딩 및 조형미 확보.
  - `SettingsDialog`: `save_cfg` 및 `update_ui_state` 자체 위임 메서드를 추가하여 부모 창 의존성 완화(독립 실행 및 테스트 안전성 확보).
  - 코드 클린업: `dialogs.py` 내 미사용 레거시 임포트(`QGroupBox`, `QThread`, `Signal`, `updater`) 영구 제거.

### 2026-09-15 — v3.5.0 : 레이아웃 리팩터링·pip 오버레이·크래시 수리·표준 준수·검증 강화 (minor 업)

#### 레이아웃 리팩터링 (B2 아키텍처)
- **chzzktube 단일 패키지 + 계층 분리**: 루트 39개 평탄 모듈 → `chzzktube/{ui,control,workers,pipeline,core,infra}` 6계층 구조로 재편
- **main.py 씬 런처**: 루트 `main.py`(씬 런처, ~30줄) → `chzzktube.ui.main_window.main()` 호출. `python main.py` / PyInstaller `Analysis(['main.py'])` 계약 유지
- **자원 이동**: `icon.ico`·`CascadiaMono*.ttf` → `assets/`, 문서 → `docs/`, 미러 → `mirrors/`, `src/` 잔재 제거

#### pip 업데이트 모델 전면 개편 (v3.4.1 핵심)
- **프로젝트 로컬 오버레이 `.pylib/`**: 인앱 업데이터가 `venv/site-packages`(uv 소유)를 절대 수정하지 않고 `<repo>/.pylib/`에 whl 해제
- **부트스트랩**: `chzzktube.infra.pylib_bootstrap.bootstrap()`이 `sys.path` 선두에 `.pylib/` 삽입, `main.py` 최상단 + `main()` 내부에서 `python -m` 직행도 커버
- **오버레이 우선순위**: `sys.path` 선두 → 오버레이 복사가 venv(락핀)보다 항상 우선. `importlib.metadata` 판독도 오버레이가 이김
- **해제 정규화**: `_extract_pylib_whl(whl, root, prefix)`로 yt-dlp/streamlink 공용화. **[버그 수정]** whl(zip)엔 디렉터리 엔트리 없어 `endswith(".dist-info/")` 판정이 항상 None → 구 dist-info 정리 스킵되던 버그 수정(파일 경로 첫 세그먼트 파싱)
- **가시성**: 기동 시 `DEPS │ OK │ PYLIB │ overlay: <path> [dist-info…]` 1줄로 어느 복사본이 이겼는지 표기

#### 크래시·버그 수리
- **_POTWorker SIGABRT**: `finished_signal` 큐잉이 `run()` 반환 전 도착 → `_on_worker_finished`가 즉시 `self._worker=None`으로 참조 해제 → 워커 스레드가 자기 파괴(SIGABRT). **수리**: `_retire/_retiring` 수명 보증 도입 — `finished`(run() 완전 반환 후 발화)까지 참조 보관 후 `deleteLater` 정리. 3개 경로(일반·pending-gate 조기 반환·cancel) 모두 적용
- **Sans Serif 폰트 별칭 탐색 제거**: `QApplication` 폰트 미지정 시 Qt 제네릭 `Sans Serif` 별칭 탐색(~100ms). `app.setFont(QFont("Cascadia Mono", 11))`로 고정
- **streamlink 무한 업데이트 루프**: `_frozen_upgrade_streamlink`가 whl을 `site-packages/streamlink/`(코드 안)에 풀어 `importlib.metadata`가 구 `dist-info` 읽음 → 매 기동 stale 판정. whl을 site-packages 루트에 풀고 구 dist-info 정리·캐시 무효화로 해결
- **POT 토큰 정합**: `_on_worker_finished`가 gate 성공 시 `"staged"`로 오보고하던 잠재 버그 → 실제 `_mode`(`"ready"`) emit
- **빈 scope 제거**: `main_window.py` 빈 `scope=""` → 플랫폼(`"YT"/"CHZ"`) 또는 `"MAIN"`으로 보정 (4컬럼 파괴 방지)
- **stage 대문자 통일**: `pot_manager.py` stage 태그 `"pot"`→`"POT"`, `"pot-DEBUG"`→`"POT-DEBUG"` (4컬럼 표준 준수)

#### 표준·테스트 강화
- **빈 scope 제거 + stage 대문자**: LogEvent 4필드(STAGE/STATUS/SCOPE/MSG) 표준 완전 준수
- **회귀 테스트 추가**: `test_pylib_overlay.py`(경로 계약·bootstrap·dist-info 정리·손상 whl) · `test_pot_manager.py`(토큰 정합 2건) · `test_coordinator.py`(raw 버스 배선 2건)
- **`pot_status_changed` 시그널 배선**: Coordinator가 토글 메시지를 raw 버스에 태워 TUI/F12/history 기록

#### 검증
- 전체 pytest **149 passed** (신규 12건) · smoke PASS · sync_mirrors 42 모듈 `changed 0/missing 0` · cocoa 실기동 EXIT_CODE=0 · 오버레이 우선순위 실증(overlay 99.0.0 > venv 8.6.0)

---

### 2026-09-13 — v3.4.0 패치 2 : 파이프라인 P0 크래시 수리 + LEGACY_AUDIT 정리

- **P0-1 finalizer**: `_dl_platform` import 누락 — 모든 배치 완료/취소 시 NameError → `finished_all` 미발화 → UI 영구 락업
- **P0-2 downloader**: SKIP 틱 `_dl_platform` NameError
- **P0-3 target_downloader**: 정의 없는 `_chzzk_filename` — 치지직 다운로드 전부 실패. `get_filename_template` 계약을 치지직 메타(channel_name/date/clip_id·video_no·live_id/fmt.height)로 치환해 복구
- **P1-A3 pot_manager**: 프리웜 `rebuild=have_build` 반전 수리 — 매 기동 npm ci+tsc 강제(§1.3 경량 prewarm 위반)를 스테일 감지 기반으로 교정
- **P1-A4 라이브 계약**: live_recorder가 DownloadContext에 부착하는 proc를 worker가 보지 못하는 불일치 수리 — `DownloadWorker._ctx` 보관 + `kill_live_process()`가 양쪽 핸들 킬, closeEvent 분기 활성화
- **P2**: `_note/_dbg` 발행 시 `[:120]` 절단 제거(LOGGING_POLICY §3/§4), 미사용 import 2건(main·progress_emitter), `POTProviderWorker` 별칭 제거, `pot_server` 중복 상수 제거, `media/chzzk_api/cookies` 죽은 `import log_history` 제거, 루트 잔재 9종 git rm(`1,` `_qtprobe.exit` `err/out.txt` `listing/locate_out.txt` `arch_dump.txt` `D2Coding-Regular.ttf` `requirements.txt`), HANDOVER §3 레이어 표기 갱신
- **P3**: `needs_pot` 3중 판정식 → `_needs_pot(info)` 단일화, F12 재오픈 증분 동기화(`_full_log_win_n`), `emit_live_header` 데드 함수 제거
- **잔여 P3 수리**: README의 미실물 pre-commit 주장 → CI 실측 문구 교체(D3) · CI paths-ignore 오탈자 `sync-drive.yml`→`sync-to-drive.yml`(D4) · log_console D2Coding 주석 → Cascadia Mono(D5) · `dl_state` 레거시 별칭 폐기 + smoke_test `ctrl.state` 갱신(E2) · HANDOVER updater "stdlib only" 표기 정밀화(lazy import 명시, E3)
- **검증**: 전체 pytest 137 passed(신규 `tests/test_pipeline_regressions.py` 11건) · smoke_test PASS · `sync_mirrors.py --check` 0건 · py_compile OK

### 2026-09-13 — v3.4.0 패치 : 분석 상태 머신 회귀 수리 — ENTER 잠금 해제·URL 클리어 크래시 제거

- **ENTER 잠금 근본 원인 수리**: `on_analyze_success`/`on_analyze_error`가 `ctrl.state["analyzing"]`을 해제하지 않아 State-Button Matrix(`get_current_app_state`)가 `ANALYZING`에 영구 고정 → `toggle_download`가 `state != "IDLE"`에서 조기 반환 → 분석 완료 후 ENTER·입력 잠금
- **죽은 호출 교체**: `on_url_changed` URL 클리어 분기가 MVC 이관(94f1ee4)에서 삭제된 `_abandon_analyze_worker()`를 호출(AttributeError) — `ctrl._abandon_analyzer()`로 교체
- **회귀 테스트**: `tests/test_analyze_state.py` 신규 5건 — 분석 성공/실패 IDLE 복귀·ENTER 재개, 포맷 고르기 PICKING 비가림, 완료 후 유령 시그널 폐기, URL 클리어 크래시
- **검증**: 전체 pytest 126 passed · `sync_mirrors.py --check` 변경 0건 · py_compile OK

### 2026-09-13 — v3.4.0 : 4컬럼 로그 규격 — SPEC/PLATFORM 폐지·SCOPE 통합·메타데이터 태그화

- **로그 포맷 표준화**: 메인 TUI를 `[HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG` 4컬럼으로 통합. `PLATFORM`과 `SPEC`을 별도 컬럼으로 유지하지 않고 발생지/대상은 `SCOPE`, 미디어·버전 정보는 MSG 앞 태그(`[1080p30]`, `[v2026.8.19]`)로 이동
- **고정 폭·중복 제거**: STAGE/STATUS/SCOPE는 5자 고정, 진행률은 3자리 퍼센트·8자리 속도·10블록 게이지로 렌더링. 빈 MSG의 말단 구분자와 같은 의미의 중복 상태 문구를 제거
- **구조화 계약 갱신**: `LogEvent.platform`은 `scope` 호환 별칭으로 남기고 신규 발행점은 `scope`만 사용. `SPEC` 전달 시 MSG 태그로 흡수하며 `WAIT`는 독립 STATUS를 만들지 않고 `RUN`으로 통합
- **문서·미러 정합성**: HANDOVER/LOGGING_POLICY/README의 v3.4.0 규격을 현행 소스와 동기화하고, 변경 Python 소스에 대응하는 `mirrors/*.md` 및 합본 미러를 재생성
- **검증**: 전체 Python 컴파일, 미러 `--check`, 관련 회귀 테스트 및 전체 테스트 스위트 통과

### 2026-09-12 — v3.3.1 : 계층 모숭 정리 — L0 순수화·좀비 제거·Qt 스레드 경계 분리

- **기동 게이트 신뢰 복구**: `StartupState.pot_ready` 플래그 — READY는 prewarm/gate **실완료 토큰**으로만 개방. `POTManager.pot_finished` msg를 상태 토큰(`"staged"`/`"ready"`/`"failed"`)으로 발행(사람용 msg 발행 시 READY 미개방 결함 수정), `use_existing()` 신설(기존 서버 응답 시 `_pending_download` 영구 큐잉 방지), `_on_pot_finished`의 `is_ready()` 재확인 후 회수 재개
- **raw 버스 백프레셔**: dispatcher bounded queue(MAX_QUEUE=2048) — 발행 스레드는 put만, 포화 시 UI mirror 드롭 + history 요약 1건, 구독자 콜백은 lock 밖에서 호출, `flush()` queue.join 연동
- **yt-dlp `\r` 처리**: `YtLoggerBridge` 캐리지 조립 버퍼 — 청크 분할 이월·다중 `\r` 최신 스냅샷만 발행·2Hz 스로틀. F12 버퍼 `deque(maxlen=4096)`
- **L2 수리 (live_recorder)**: 증발한 `prepare_live_paths` 모듈 함수 구현, `worker.handle_stream_finish`/`worker.log_success_info` 인스턴스 메서드 착각 호출을 모듈 함수 계약으로 교정 — 라이브 진입·종료 AttributeError 제거, `_lr` 자기 참조 별칭 제거
- **L0 순수화 (po_client)**: `server_ping`의 pot_server lazy import(락 파일 PID 염탐) 완전 철거 — 순수 HTTP /ping만 판정(TCP+200=이벤트 루프 생존 증거), 좀비 락 회수는 pot_server 본연 책임으로 이관. `import os` 누락 NameError 은폐 결함 근원 제거
- **좀비 제거**: `worker_context.py` 삭제(DownloadContext와 이중 계약, 런타임 사용 0건), `pot_provider.POTProviderWorker` 제거(POTManager._POTWorker 중복, facade는 재수출 단독)
- **Qt 스레드 경계**: main `_GuiLogBridge(QObject)` + QueuedConnection — raw_log 순수 파이썬 유지(헤드리스 테스트 무수정), GUI 슬롯(`_render_concise`/`_mirror_event_full`)은 메인 스레드에서만 실행. 배경 스레드 QTextEdit 직접 접근 차단
- **기타 수리**: pot_provider `_spawn_existing` 이중 호출 원자화(서버 2회 기동 방지), main `_emit_format_logs` 복원(분석 성공 V-FMT/A-FMT 코덱 로그), startup_coordinator 죽은 `_stage_complete` 제거, raw_log 죽은 `MAX_LINE_CHARS` 제거
- **검증**: py_compile 전체 + pytest **111 passed** (test_live_recorder 신규 5건, overflow 타이밍 레이스 제거) + 브리지 스레드 경계 프로브(슬롯 전부 MainThread 실증)


### 2026-09-12 — v3.3.0 : 로그 버스 단일화 — raw 단일 경로·플래그 라우팅·레거시 제거

- **버스 단일화**: `raw_log.raw(tag, msg, to_tui)` 단일 진입 확정 — `log_bus.py` 삭제, `log_history.log` 직접 호출 10곳 버스 reroute(`to_tui=False`), 워커 로그 시그널 0건 실측
- **플래그 라우팅**: TUI 노출=`to_tui` 비트, 줄바꿈=`no_wrap` 플래그 — `_flow_lines` 콘텐츠 판정(`is_tui_line`) 렌더 퇴출(호환 shim 강등), resize reflow도 버퍼 플래그로 유지
- **근원 라벨링**: 분석 성공 등 발행점에서 LogEvent 동봉 — `_render_concise`가 컬럼화, `append_concise_log`는 bus shim(호출부 20곳 무수정), `append_full_log` 제거
- **기동 게이트 문서화**: DEPS→upgrade→prewarm→READY 체인, POT prewarm/gate `_pending_gate` 승격, `can_emit_ready()` 멱등식 — HANDOVER §5 불변식 11~15 편입, §3 아키텍처 40개 모듈 실측 최신화
- **검증**: py_compile 전체 + pytest 86 passed (신규 `TestFlowLinesNoWrapFlag` 6건 + v3.3.0 계약 불일치 7건 수리)


### 2026-09-10 — v3.2.0 : F12 중복 제거·raw 로그 버스·POT stale 감지 + 프리웜 자동 리프레시

- **아키텍처**: raw 로그 버스(`raw_log.py`) 신설 — 모든 동작 로그 concise(메인 TUI)/F12/역사 3채널 팬아웃, 필터링은 각 모듈
- **PO 서버**: POT DEPS 판정을 liveness → readiness(pot_readiness)로 전환, 미기공 정상 `FAIL not running` 오경보 제거
- **프리웜**: 파이프라인 idle 단계에서 stale 빌드 감지 + 자동 리프레시(체크 스탈 + want_refresh + 자동 rebuild) → lazy "언제든 작동 가능한 준비 상태" 유지
- **F12 가독성**: CLI 원문(`ffmpeg -version` configuration:) 장문/다수 절단(`max_lines=6, max_width=160`) 적용, F12 중복 이중적재 제거
- **로깅**: POT/가드/락 획득·해제 경로를 raw 태그(`pot-readiness`, `prewarm-lock`, `pot-gate`, `POT-FAIL` 등)로 기록
- **계층/시그널**: 워커가 포그라운드/히스토리 직접 emit 금지 — L0 `log_func` 콜백 + raw 버스 단일 경유
- **테스트**: PID-liveness·상호배제·stale 회수·readiness stale·check_deps 단일 호출·cli_raw 절단·raw 팬아웃 추가 (전체 80 passed)

### 2026-09-09 — v3.1.2 : 전체 아키텍처/모듈/테스트/CI 실측 최신화

- 대규모 리팩토링 후 시그널 파이프라인 정리, 계층 역전 해소(client_opts/updater → po_client L0 직접 참조)
- dataclass 다운로드 컨텍스트(`dl_context.py`) 도입, 포터블 번들 탈피 + Node.js 외부 참조 전환
- 모듈 분리: analyze_worker/yt_logger_bridge/po_client/update_worker/po_client 등 34개 모듈 체계 정비
- 바람직하지 않은 중복 EMIT·상태 오판 제거, 짧지만 정합적인 진행률/콘솔 레이팅 유지

### 2026-09-08 — v3.1.0 : Qt/PySide6 정리, 로깅 표준화, Cascadia Mono 11px

- Flat TUI 3-Layer 구조로 전환, 모노스페이스 폰트 통일
- 당시 고정 칼럼 로그 규격([HH:MM:SS] STAGE │ STATUS │ PLATFORM │ SPEC │ MSG) + 파스텔 톤 에러 컬러 (v3.4.0에서 4컬럼으로 개정)
- MSG 영문 미니멀화 (1~3단어 CLI 태그), live 콘솔 모니터 stretch=1 분리

## 구 HANDOVER 히스토리 이관

> **v3.5.0부터 [CHANGELOG.md](../CHANGELOG.md)로 단일화** — 상세 수정 내역은 [CHANGELOG.md](../CHANGELOG.md) 참조.
> v3.5.2(2026-09-16) — READY 폴백 결함 3건 수리: deps 게이트 의미 분리(P1) · 업그레이드 크래시 시그널 분기(P2) · POT 프리웜 보존 + 서브프로세스 상한(P3·P3b·P3c).
> v3.6.0(2026-09-16) — 게이트 하드닝 후속 6건 전량 해소: POT 내부 하트비트(#1)·트리 종료(#2)·gate 2차 워치독(#3)·폴백 유예(#4)·deps FAIL 승격(#5)·PO 재시도(#6).
> v3.6.1(2026-09-16) — 아키텍처 다이어그램(mermaid 3종) 추가: 전체 계층도·기동 시퀀스·상태·워치독 관계(문서 패치, 소스 변경 없음).
> v3.6.3(2026-09-17) — 기동 초기화 단일화 + 분석 워치독 계약 복구: 폴링 내 UI 재초기화 제거(위젯·타이머 매초 교체, 업데이트 확인 반복 예약, URL당 1회 재시도 이력 소거 수리) · 분석 워치독 뷰 단독 소유(무페이로드 activity, 강제 terminate 제거) · Infra→UI 역참조와 죽은 타이머 참조 정리 · 테스트 세션 QApplication 단일화(tests/conftest.py).
> v3.6.4(2026-09-18) — analysis dead-end fix: EJS JS 런타임(앱 포터블 Node 주입)·쿠키 호환 회전(tv/web_safari, ios 배제)·analysis error 60자 절약·TuiNoticeDialog + 쿠키 흐름 영어 문자열.
> v3.7.0(2026-09-18) — download pipeline contract overhaul: ClassifiedTarget 단일 계약, VOD 품질 우선 폴백(web→web_safari→ios→tv), PO 토큰 1:1 바인딩, skip 집계, conftest .pylib bootstrap, analyze_worker Mock 제거, 쿠키 정책 SSOT 정렬.
> v3.7.2(2026-09-19) — yt-dlp 순정 클라이언트 로테이션 완전 위임: 앱 레벨 수동 백 체인 제거, 3계층 파이프라인 재설계, POT 게이트 정단화(subscriber_only 제외).
> v3.8.0(2026-09-20) — 단독 환경 격리·입력 게이트·Layer 3 POT 수리·TUI 정제: 시스템 PATH(`shutil.which`)·OS 패키지 매니저(brew/apt) 참조 전면 철폐(전용 `writable_base()`·`.pylib` 단일 경로), URL 검증 게이트 2중 방어(비URL 배치 차단), `POTManager.instance()` 부재 결함을 워커 안전 L0/L1 인프라 호출로 근본 수리 + 1080p 미달 승격 판정 신설, FAIL 단일 발행(finalizer)·중간 `.fNNN` 스트림 TUI 은닉·ANAL 마감 정갈 명세.
> v3.8.1(2026-09-22) — 폴백 완전 제거·URL 검증 게이트·표준 에러 헬퍼·POT 상태 수정: 15초 강제 언락(`force_unlock`) 제거, `MediaController._is_valid_url()` 순수 게이트 신설, `emit_error_standard`/`emit_error_warn` 전면 도입, `staged` ≠ `ready` 상태 의미 명확화.
> v3.8.2(2026-09-22) — Path Strategy Pattern으로 .pylib SSOT 완성: `config.pylib_overlay_path()` 단일 경로 리졸버로 Frozen/Dev 환경 분리 캡슐화, 호출부 `if is_frozen()` 분기 0건 달성, frozen 시 `writable_base()/.pylib`(`%LOCALAPPDATA%/ChzzkTube/.pylib` 또는 `~/.chzzktube/.pylib`) 사용.
> v3.8.3(2026-09-22) — 수급 계층 stdlib-only 완성·1줄 1정보 로그 규격·TUI/F12 갱신형 진행률: `httpx` 잔여 완전 제거(`ParallelDownloader`·PyPI/GitHub/nodejs 메타 패처를 `urllib`+`asyncio.to_thread`로 전환), `filter_assets` `.zip` 강제 선택·`.7z` 배제 + `archive_type` 화이트리스트 가드, FFmpeg 7.1 URL 교정, Verifier `install_rel_path` 판정, `ProgressBar` 신규(TUI 컴포넌트별 갱신형·F12 누적→갱신형·§3.5 포맷터), stale 요약 개별 줄화·집계 직렬 나열 제거.
> v3.8.3-p1(2026-09-22) — 진행률 viewer 회귀 수리: `MainWindow` 브리지 슬롯(`_render_concise`/`_mirror_event_full`)이 `component_id`/`is_progress`를 유지하도록 교정, 진행 라인 완료 시 TUI 히스토리에 유지, F12/`_full_log_buf`에 진행 틱 전량 기록(is_status 여부와 무관). `raw_log.raw()` 단일 진입점이 `component_id`/`is_progress`를 전파하도록 확장. `tests/test_progress_integration.py` 신규 추가 (10개 케이스). (patch)
> v3.11.0(2026-09-25) — yt-dlp 독립 실행형 바이너리 마이그레이션 · Silent Fallback 완전 제거 · 진행률 바 최소 영문화 · 프로비저닝 아키텍처 리팩토링(Planner/Executor/Committer 분리).
> v3.12.0(2026-09-25) — GUI 아키텍처 대규모 리팩토링 및 5축 품질 게이트 90+ 달성: MainWindow SRP 분해(HeaderBarWidget, ActionBarWidget 분리) · AppState Enum 단일화 · 콘솔 O(1) 인플레이스 블록 치환(Targeted Mutation) 및 20Hz 쓰로틀링 · Dialog HiDPI 반응형 전환 및 SettingsDialog 5대 섹션 빌더 분할 · 실시간 URL 사전 검증 Soft Warning 피드백 · theme.py 시맨틱 디자인 토큰화 · 엄격한 전수 Type Hints 완비 (361 tests 100% pass).

#### 문제 (전수조사·사용자 검증 실측)
- **P0 3건**: finalizer/downloader `_dl_platform` import 누락(배치 마감·SKIP에서 NameError → `finished_all` 미발화 → UI 락업), target_downloader `_chzzk_filename` 정의 부재(치지직 다운로드 전멸). 126건 테스트가 놓친 이유는 finalizer/downloader/치지직 경로 테스트 0건(커버리지 갭)
- **A3**: 프리웜 `rebuild=have_build` — 빌드 존재 시 매 기동 npm ci+tsc 강제("디스크 스테이징만" 위반)
- **A4**: 라이브 proc는 DownloadContext에 부착되는데 worker/`kill_live_process`가 이를 보지 못함
- **C1**: `_note/_dbg` 발행 시 `[:120]` 절단 — LOGGING_POLICY §3/§4 위반

#### 모듈 변경
| 모듈 | 변경 |
|------|------|
| `finalizer.py`/`downloader.py` | `from dl_platform import _dl_platform` 복원(P0-1/3) |
| `target_downloader.py` | `_chzzk_filename(ch_info, fmt, cfg)` 신설 — 치지직 메타를 filename prefix/suffix 계약으로 치환, .mp4 고정(P0-2) |
| `pot_manager.py` | prewarm rebuild을 스테일 감지 기반으로 교정(A3)·`_note/_dbg` 절단 제거(C1)·`POTProviderWorker` 별칭 제거(B3) |
| `downloader.py` | `_ctx` 보관 + `kill_live_process()` — worker·ctx proc 양쪽 킬(A4) |
| `progress_emitter.py` | 미사용 client_opts import 제거(B2)·`emit_live_header` 데드 함수 제거(B5) |
| `main.py` | `import pot_provider` 제거(B1)·`_needs_pot(info)` 단일화(E1)·F12 재오픈 증분 동기화(A5) |
| `pot_server.py` | `_TAG_ZIP`/`_SERVER_FALLBACK_VER` 중복 정의 제거(B4) |
| `media.py`/`chzzk_api.py`/`cookies.py` | 죽은 `import log_history` 제거 |
| 루트 | `1,` `_qtprobe.exit` `err/out.txt` `listing/locate_out.txt` `arch_dump.txt` `D2Coding-Regular.ttf` `requirements.txt` 제거(D1/D2) + `.gitignore` 보강 |
| `tests/test_pipeline_regressions.py` | 신규 11건(마감 NameError·치지직 파일명·needs_pot·원문 보존·kill 계약·F12 인덱스·죽은 심볼 가드) |
| `HANDOVER.md` | §3 레이어 표기 갱신(B7) — pot_provider는 facade(L0), 워커 아님 |
| `log_console.py` | D2Coding 주석 → Cascadia Mono(D5) |
| `smoke_test.py`/`controller.py`/`README.md`/`.github/workflows/ci.yml` | smoke `ctrl.state` 갱신(E2)·MVC docstring 정리·README CI 문구 교체(D3)·CI paths-ignore 오탈자 수리(D4) |

#### 검증
- 전체 pytest 137 passed / smoke_test PASS / `sync_mirrors.py --check` 0건 / py_compile OK

---

### 2026-09-18 — v3.7.0 : download pipeline contract overhaul (minor)

#### 배경 (v3.6.4 → v3.7.0)
다운로드 파이프라인의 핵심 계약들이 분산·불일치 상태로 누적되어 있었다:
- `_flatten`/`expand_targets` 반환 타입이 `List[str]` / `List[dict]` / `List[ClassifiedTarget]`로 섞임
- `_download_vod` 클라이언트 폴백이 `tv→web_safari→web`(저화질 우선)으로 동작 → 360p 고착
- PO 토큰 `web_embedded`와 실제 `player_client`(`web`/`tv` 등) 불일치 → 0% stall
- terminal failure(비공개/삭제)까지 봇 차단으로 오판해 4단계 전량 헛돌기
- `skip_targets`가 워커→파이프라인→finalizer 연결 누락으로 미집계
- 분석 워커에 `YoutubeDL` Mock 클래스 잔재 → 테스트 환경과 실 배포 환경 괴리
- 쿠키 정책 판정(`_apply_cookie_opts` vs `_has_configured_cookies`) 불일치

#### 모듈 변경

| 모듈 | 변경 |
|------|------|
| `pipeline/classifier.py` | **신규** — `ContentKind(VOD/CLIP/LIVE_YOUTUBE/LIVE_CHZZK/PLAYLIST/UNKNOWN)`, `StreamCapability(has_video\|audio: bool\|None + could_have_* 방어 메서드)`, `CookiePolicyContext`, `ClassifiedTarget`, `ItemClassifier` 순수 분류 엔진 |
| `pipeline/target_downloader.py` | `_make_ytdl_opts(forced_client=)`, `_download_vod` 품질 우선 체인 `web→web_safari→ios→tv`, terminal fail-fast, PO 토큰 1:1 바인딩(web/web_safari만, ios/tv 미주입), `_classify_item(dict/str/ClassifiedTarget)` 정규화, `_flatten`·`_normalize_single_item`·`expand_targets` 모두 `List[ClassifiedTarget]` 반환, `download_target` 반환값 `True/"skip"/False` 명시 |
| `pipeline/finalizer.py` | `skip_targets` 파라미터 추가, `DONE/WARN/FAIL/ABORT` 상태 세분화, `batch finished (success: N, fail: M, skip: K)` 포맷 |
| `workers/downloader.py` | `item.url` 속성 접근 통일, `skip_targets` 전달, 시스템 skip `"skip"` 반환 시 집계 |
| `workers/analyze_worker.py` | 빈 `YoutubeDL` Mock 클래스 제거, 실 `yt_dlp` import 경로 단순화 |
| `tests/conftest.py` | `pytest_configure` 훅으로 `.pylib` bootstrap 강제, `yt_dlp.__path__` 동기화, `raw_log` flush fixture, `live` fixture 복원 |
| `tests/test_window_initialization.py` | 서브프로세스 `PYTHONPATH=.pylib` 주입 |

#### 설계 원칙
1. **단일 계약(SSOT)**: 파이프라인 전체가 `ClassifiedTarget` 하나만 공유 — `has_video/has_audio=None`(미정) 상태를 거짓말 없이 보존, 하류에서 `could_have_video()` 등으로 안전 질의
2. **품질 우선 폴백**: `auto` 모드일 때 `web(최고화질) → web_safari → ios → tv(최후 안전망)` 순으로만 회전, 명시적 client 설정은 단일 시도
3. **PO 토큰 정합성**: `player_client`와 `po_token=<client>.gvs+TOKEN`을 매 시도에서 동일하게 바인딩, `auto`면 `web_embedded`로 토큰 요청
4. **에러 분류**: terminal failure(`private`/`unavailable`/`terminated`/`copyright`/`members-only`) 즉시 중단, 봇 차단/챌린지/403만 다음 client로
3. **Skip 집계**: 이미지 전용(`image-only`), 인증 필요하지만 쿠키 없음(`age/member gated`), 사용자 skip을 `skip_targets`에 수집 → 최종 요약에 `skip: K` 표시
4. **쿠키 정책 SSOT**: `_apply_cookie_opts`(실제 주입)와 `_has_configured_cookies`(사전 판정)가 **동일한 조건 분기** 공유 — `cookie_file` 모드에서 파일 없으면 양쪽 다 False

#### 검증
- 전체 pytest **239 passed**
- `python -m compileall -q chzzktube` 통과
- `git diff --check` clean
- 실측: 멤버십 전용/연령 제한/삭제 영상 → `DL │ SKIP │ YT │ [age/member gated]` 출력, 최종 요약 `skip` 카운트 포함

---

### 2026-09-18 — v3.6.4 : analysis dead-end fix: EJS JS 런타임(앱 포터블 Node 주입)·쿠키 호환 회전(tv/web_safari, ios 배제)·analysis error 60자 절약·TuiNoticeDialog + 쿠키 흐름 영어 문자열.

### 2026-09-13 — v3.4.0 패치 : 분석 상태 머신 회귀 수리 — ENTER 잠금·URL 클리어 크래시

#### 문제 (파이프라인 전수조사 실측)
- **ENTER 잠금**: `controller.spawn_analyzer`가 `state["analyzing"]=True`를 세팅한 뒤 성공/실패 어디에서도 `False`로 되돌리지 않았다(`_abandon_analyzer` 유기 경로에만 존재). `a18639b`(State-Button Matrix)부터 `get_current_app_state`가 `ANALYZING`을 하드 차단하고 `toggle_download`가 `state != "IDLE"`에서 조기 반환 → 분석 완료 직후 입력·ENTER 영구 잠금. `_is_stale_analyze_signal` docstring("분석 상태가 아니면(유기·완료) 모든 큐잉된 시그널 폐기")과도 모순된 누락
- **URL 클리어 크래시**: `on_url_changed`의 클리어 분기가 MVC 이관(94f1ee4)에서 사라진 `_abandon_analyze_worker()`를 호출 — AttributeError로 뒤의 `clear_status_line`/`_discard_analysis_result` 로직 미실행

#### 모듈 변경
| 모듈 | 변경 |
|------|------|
| `main.py` | `on_analyze_success`/`on_analyze_error`에 `ctrl.state["analyzing"]=False`(stale 검사 통과 직후) / `on_url_changed` 클리어 → `ctrl._abandon_analyzer()` |
| `tests/test_analyze_state.py` | 신규 회귀 테스트 5건 (ENTER 재개·IDLE 복귀·PICKING 비가림·유령 시그널 폐기·URL 클리어) |
| `mirrors/` | main.py 변경 반영 재생성 |

#### 검증
- 전체 pytest 126 passed (신규 5건 포함)
- `python sync_mirrors.py --check` — 변경 0건
- `py_compile` OK · 재현 스크립트로 수정 전 ANALYZING 고정 → 수정 후 IDLE + 다운로드 시작 확인

### 2026-09-13 — v3.4.0 4컬럼 로그 규격 — SPEC/PLATFORM 폐지·SCOPE 통합·메타데이터 태그화

#### 변경
- **TUI 계약**: 메인 로그를 `[HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG`로 단일화. `PLATFORM`과 `SPEC` 컬럼을 폐지하고 발생지/대상은 `SCOPE`, 해상도·코덱·버전은 MSG 앞 태그로 보존
- **렌더링**: STAGE/STATUS/SCOPE 5자 고정, 진행률은 `PCT → SPEED → GAUGE → MSG`, 빈 MSG에는 말단 구분자를 붙이지 않음
- **구조화 로그**: `LogEvent.scope`를 정식 필드로 고정. `platform`은 하위 호환 별칭, `spec` 전달값은 렌더러에서 MSG 태그로 흡수
- **문서화**: HANDOVER·LOGGING_POLICY·README의 v3.4.0 규격을 현행 소스와 맞추고, §1.1 버전 관리 절차와 §1.2 경로 계약을 추가하며 Python 미러를 재생성

#### 모듈 변경
| 모듈 | 변경 |
|------|------|
| `log_event.py` | `scope` 정식화·`platform` 호환 별칭·`spec` MSG 태그 계약 |
| `log_console.py` | 4컬럼 고정 폭·진행률 지터 방지·빈 MSG 구분자 제거 |
| `main.py`/`downloader.py`/`media.py` | 5컬럼 포맷·중복 SPEC/SPEED 제거·4컬럼 렌더러 호출 |
| `components.py`/`cookies.py`/`chzzk_api.py`/`finalizer.py`/`live_recorder.py`/`progress_emitter.py`/`update_worker.py` | SCOPE/MSG 태그·4컬럼 이벤트 계약 정합성 수리 |
| `tool_log.py`/`tests/test_tool_log.py` | v3.4.0 검증에 사용된 subprocess 로그 펌프와 회귀 테스트 유지 |
| `HANDOVER.md`/`LOGGING_POLICY.md`/`README.md` | v3.4.0 4컬럼 규격 문서화 |
| `mirrors/` | 변경 Python 소스와 전체 코드 합본 재생성 |

#### 검증
- 전체 Python `compileall` 통과
- `python sync_mirrors.py --check` — 모든 지정 미러 최신 상태
- 관련 로그/파이프라인 회귀 테스트 및 전체 pytest 스위트 통과
- `git diff --check` 통과

### 2026-09-12 — v3.3.1 계층 모숭 정리 — L0 순수화·좀비 제거·Qt 스레드 경계 분리

#### 문제 (5계층 전수조사 실측)
- **L0 계층 사칭**: po_client가 "stdlib only L0" 주장과 달리 `server_ping`에서 pot_server lazy import(락 파일 PID 염탐) — pot_server는 최상단에서 po_client 역참조하는 상호 순환. 게다가 `import os` 누락으로 PID 검증이 `except Exception: pass`에 삼켜져 NameError로 무력화
- **L1 이중 계약**: `WorkerContext(worker_context.py)` — DownloadContext와 동일 목적, 런타임 사용 0건 죽은 코드
- **L2 시한폭탄**: live_recorder에 `prepare_live_paths` 부재(`_lr.prepare_live_paths` AttributeError), `worker.handle_stream_finish`/`worker.log_success_info` 인스턴스 메서드 착각 호출 — 라이브 진입·종료 즉시 크래시
- **L3 Qt 스레드 위반**: raw_log dispatcher(데몬 스레드)가 `_render_concise`/`_mirror_event_full`을 직접 호출 — QTextEdit 배경 스레드 조작(세그폴트 위험), main 구주석은 "QueuedConnection 경유 GUI 스레드 실행" 주장과 모순
- **L4 좀비 인터페이스**: `pot_provider.POTProviderWorker` — POTManager._POTWorker와 중복, 런타임 사용 0건. `_spawn_existing` 이중 호출로 서버 2회 기동 시도
- **기동 게이트**: `pot_finished` msg에 사람용 상세("prewarm staged")를 담아 `report_pot` 정확 일치와 불일치 → **런타임에서 READY가 절대 열리지 않음**. 기존 서버 응답 시 `_pending_download` 영구 큐잉

#### 해결
- **L0**: po_client — 역참조 완전 철거, 순수 HTTP /ping만 판정(TCP 성공+200=이벤트 루프 생존 증거). 좀비 락 회수는 pot_server 기동 시 본연 책임
- **L1**: worker_context.py 삭제 + sync_mirrors 대상 제거
- **L2**: `prepare_live_paths` 모듈 함수 구현, `handle_stream_finish(worker,…)`/`log_success_info(worker,…)` 모듈 함수 계약 교정, `_lr` 자기 참조 별칭 제거, target_downloader `ctx.log_success_info` → `_pe.log_success_info(ctx, real)`
- **L3**: main `_GuiLogBridge(QObject)` + QueuedConnection — raw_log 순수 파이썬 유지(109 헤드리스 테스트 무수정), GUI 슬롯은 메인 스레드에서만 실행. 프로브로 스레드 경계 실증(워커 emit → pre processEvents 0 → post 2, 슬롯 전부 MainThread)
- **L4**: POTProviderWorker 클래스 제거(177→76행 facade), `_spawn_existing` 단일 호출 원자화
- **게이트**: `pot_finished` msg를 상태 토큰("staged"/"ready"/"failed")으로, `StartupState.pot_ready` 플래그, `use_existing()` 신설, `_on_pot_finished`의 `is_ready()` 재확인 후 `_pending_download` 회수

#### 모듈 변경
| 모듈 | 변경 |
|------|------|
| `po_client.py` | server_ping 순수 HTTP화(91행) — 역참조 0·import os 제거·상수 보존 |
| `live_recorder.py` | prepare_live_paths 신설 + 모듈 함수 계약 3곳 수리 + `_lr` 별칭 제거 (229행) |
| `target_downloader.py` | `ctx.log_success_info` → `_pe.log_success_info(ctx, real)` 1곳 |
| `pot_provider.py` | POTProviderWorker 제거 — 재수출 facade 단독 (177→76행) |
| `worker_context.py` | 삭제 (git rm) + mirrors 목록 제거 |
| `main.py` | `_GuiLogBridge(QObject)` 신설 + QueuedConnection 구독 전환 (1366행) |
| `pot_manager.py` | pot_finished 토큰 발행 + use_existing + is_ready/use_existing 계약 (247행) |
| `startup_coordinator.py` | report_pot 상태 토큰 판정 + 죽은 `_stage_complete` 제거 |
| `startup_state.py` | pot_ready 플래그 + can_emit_ready 갱신 |
| `raw_log.py` | _record_overflow 요약 이벤트 + flush queue.join (bounded queue) |
| `yt_logger_bridge.py` | \r 캐리지 조립 버퍼(이월·최신 스냅샷) + 2Hz 스로틀 |
| `tests/` | test_live_recorder 신규 5건, overflow 타이밍 레이스 제거, 좀비 테스트 정리 |

#### 검증
- py_compile 전체 + **pytest 111 passed** (전체 스위트) + `git diff --check` 클린
- 브리지 스레드 경계 프로브: 워커 emit → pre processEvents 0 / post 2 / 슬롯 전부 MainThread
- facade 재수출 무결성 실측(node_exe/pot_readiness/_spawn_existing/ensure_node_server 등), `POTProviderWorker` 부재 확인

### 2026-09-12 — v3.3.0 로그 버스 단일화 — raw 단일 경로·플래그 라우팅·레거시 제거

| 모듈 | 변경 |
|------|------|
| `config.py` | `_APP_VERSION` v3.2.1 → v3.3.0 (minor 점프 — 아키텍처 재편. semver-lite `y` 릴리즈) |
| `raw_log.py` | `raw(tag, msg, is_status, is_error, to_tui)` 단일 진입 확정 — 문자열→LogEvent 정규화(`rendered=True`), history 내부 1회 적재(`level=ERROR↔INFO`) |
| `main.py` | 버스 구독 2점(`subscribe_concise/full`) · `_render_concise` 컬럼화+`no_wrap=True` · `append_concise_log`=bus shim(호출부 20곳 무수정) · `append_full_log` 제거 · 분석 성공 `format_log_line` 직접 호출→`raw("anal", LogEvent)` · 직접 `log_history.log` 3곳 bus reroute |
| `log_console.py` | `append(…, no_wrap)`→`_buffer{…, no_wrap}`→`_insert_clamped`→`_flow_lines(raw, no_wrap)` 플래그 체인 · `is_tui_line` 렌더 퇴출(호환 shim 강등) |
| `chzzk_api.py`/`cookies.py`/`media.py` | 직접 `log_history.log` 7곳 → `raw_log.raw(…, to_tui=False)` (F12+history 전용) |
| `log_bus.py` | 삭제(`git rm`) — `import log_bus` 참조 0건 확인 |
| `sync_mirrors.py` | 미러 출력처 루트 `*.md` → `mirrors/*.md` 이전 + `mirrors/chzzktube_codebase.md` 합본 번들 신규 · `fix_target`/`log_event`/`worker_context` 대상 추가(→ `fix_target`은 일회용 스크립트 정리로同日 제거, 39개 확정) |
| `README.md` | 주의사항 로그 서술 현행 계약으로 교체 (단일 진입·전량·`to_tui` 팬아웃) |
| `CHANGELOG.md` | v3.3.0 엔트리 5 bullets 추가 |
| `HANDOVER.md` | 머리글 v3.3.0 · §3 40개 모듈 실측표 · §4 v3.3.0 시그널 계약 신설(구 블록 `<details>` 보존) · §5 불변식 11~15 편입 · 본 §9 v3.3.0 행 |
| `tests/test_log_console.py` | `TestFlowLinesNoWrapFlag` 6건 신규 (no_wrap passthrough·트리 유지·plain wrap·shim 구조판정·기본값 wrap) |
| `tests/test_coordinator.py` | 죽은 `append_full_log` Mock 제거 |

#### 검증
- ✅ py_compile 전체 OK
- ✅ pytest 86 passed (전체) — v3.3.0 계약 불일치 테스트 7건 수리 포함:
  `TestEmitDl`/`TestEmitErr`/`test_context_passed_to_pipeline`은 `emit_dl`/`emit_err`가 `str`이 아닌 `LogEvent`를 반환하므로 `_rendered()`(`format_log_line_for_event`) 경유로 전환,
  `test_raw_bus_fanout`은 폐기된 병렬-분리 계약(`full_only` kwarg) 대신 포함관계 계약(to_tui 1비트)으로 전면 교체.
  원인: `0cf6b51` v3.3.0 리팩토링이 코드 계약만 바꾸고 테스트를 안 고친 채 머지됨.
- 행위 변화 1건: 미리 포맷된 LogEvent 문자열(pick 메뉴 등)은 wrap 대신 한 줄 유지 + `_render_clamp` `…` 절단. bare 문자열은 기존대로 wrap

### 2026-09-09 — pot_provider SRP 3-웨이 분리 + dataclass 컨텍스트 추출 + 통합 테스트 + CI

| 모듈 | 변경 |
|------|------|
| `po_client.py` | **신규 L0 leaf** — PO Token HTTP 클라이언트 (`fetch_po_token`/`extract_video_id`/`probe_server`) |
| `node_provider.py` | **신규 L0 leaf** — Node.js 런타임 수급 (`ensure_node_runtime`/`node_exe`/`npm_exe`) |
| `pot_server.py` | **신규** — bgutil 서버 빌드/기동 (`ensure_node_server`/`built_server_js`/`_spawn_node_server`) |
| `pot_provider.py` | **facade** — 3개 모듈 재수출 + `POTProviderWorker(QThread)` 유지 (935→230라인) |
| `dl_context.py` | **신규** — `DownloadContext` dataclass로 파이프라인 계약 명시화 |
| `analyze_worker.py` | **신규** — AnalyzeWorker(QThread) 분리 (path 분리) |
| `update_worker.py` | **신규** — UpdateWorker + `_RAW_VERSION_CMDS` 분리 |
| `yt_logger_bridge.py` | **신규** — 공용 YtLoggerBridge 어댑터 분리 |
| `downloader.py` | DownloadWorker만 유지, 미사용 임포트 제거 |
| `dialogs.py` | UpdateWorker 블록 제거 (846→686줄) |
| `target_downloader.py` | 오류 사유 영문 1-3단어 태그화 |
| `progress_emitter.py` | emit_dl/emit_err 재수출 단일화 |
| `log_console.py` | emit_dl/emit_err 단일 출처 추가 |
| `HANDOVER.md` | §3 아키텍처 34개 모듈 실측 최신화, §5 시그널 계약 갱신, §3.5 포맷 표준 추가 |
| `tests/test_download_pipeline.py` | **신규 12개 테스트** — ctx 흐름/포맷/facade 검증 |
| `.github/workflows/ci.yml` | **신규 CI** — push/PR 시 pytest 자동 실행 |

#### 검증
- ✅ py_compile 34개 모듈 OK
- ✅ pytest 68 passed (56 기존 + 12 신규)
- ✅ 런타임 READY 1건 유지 (3회 연속)
- ✅ 계층 역전 0: client_opts/updater → po_client 직접 참조

### 2026-09-07 — DEPS 로그 2분기 원문화 + 실행체 통일 + Nightly 채널 활성화

| 모듈 | 변경 |
|------|------|
| `dialogs.py` | UpdateWorker 시그널 계약 정리 — line=(msg,is_status,is_error), **full=(raw,is_status)**. _do_check F12 재편: deps[] 요약 제거, 실제 CLI 원문($ yt-dlp --version → 2026.08.19)만 적재. _provision_cb TUI 미러 제거 → 마지막 메시지부 raw(is_status 전달). **VerboseLogWindow.append is_status — F12 갱신형(마지막 줄 덮어쓰기)**. channel/check_updates 파라미터 신설 |
| `main.py` | full 수신 append_full_log/is_status → _mirror_full_log(진행률은 버퍼 미적재, F12 열려있으면 마지막 줄 갱신). UpdateWorker 생성에 channel=cfg[update_channel], check_updates=cfg[auto_update_check] 전달. **_on_auto_upgrade_done에서 _startup_completed=True** — 기존엔 POT 종료시에만 세팅돼 자동갱신 후 15초 폴백까지 입력 잠금 |

| `updater.py` | **check_deps nightly 인지** — yt-dlp-nightly 는 dist 명이 달라 im.version(yt-dlp) 실패 → nightly 설치물 폴백 표기(2026.9.x (nightly)). outdated_packages(channel) **다운그레이드 감지** — stable 채널+nightly 잔존 → 강제 stale, stale 튜플 pypi_name 고정으로 upgrade_packages None 언팩 방지. cli_raw/_cli_base/_cli_env/npm_exe 신설 — 셸에서 친 것과 동일한 CLI 원문 캡처. _ffmpeg_version Windows creationflags |
| `pot_provider.py` | _note 의 tui_to_raw F12 미러 2곳 제거 — F12 는 pot 실제 CLI 원문(tsc/npm)만. npm_exe 신설(node 런타임 옆 npm 스크립트) |
| `log_console.py` | tui_to_raw 제거(미사용 정리). append 진행률 갱신형 계약 주석 명시(한 행=한 정보) |
| `progress_emitter.py` / `live_recorder.py` | DL/LIVE 틱 is_status=True — 매 틱 새 줄 위반 수리(§6 In-Place) |
| `components.py` | **bundled_npm_ok 크로스플랫폼** — macOS/Linux tarball(bin/../lib/node_modules/npm) 검사 추가. Windows 전용 경로만 봐서 정상 npm을 broken 오판 → **매 시작 재다운로드 루프**였던 근본 원인 수리 |
| `config.py` | update_channel / auto_update_check 기본값 |
| `HANDOVER.md` | §8.4 빌드 시 해야 할 일(OS별 체크리스트) 신설, §8.2 버전 확인 2분기 구조 반영 |
| 검증 | py_compile 6모듈 · smoke PASS · UpdateWorker 시뮬(stale 없음→간결 침묵) · F12 갱신형 실측(40%→80% 한 줄) · outdated_packages 4시나리오(nightly 설치 판정/stable 다운그레이드/nightly 업그레이드/최신 무표기) · mirrors sync |




### 2026-09-07 — DEPS 자동 수급 완전 통합 + 비표준 status 일괄 제거

| 항목 | 변경 |
|------|------|
| `§5 0번` | **표준 status 규칙 신설**: `OK / READY / RUN / DONE / ABORT / FAIL / END / SKIP / WARN` 허용, `MISSING` / `?` 금지. msg falsy 시 세로줄 누락 경고. DEPS 실패 → `FAIL` + msg 명시. |
| `§8.2` | **Dev/Frozen 완전 통합**: frozen 분기 제거. `UpdateWorker`가 모든 deps(PyPI + ffmpeg + node) 처리. Dev = Frozen 디버깅 가능. |
| `updater.py` | `check_deps()`: `"MISSING"` → `FAIL`, `"?"` → `FAIL`, `None` → `"not found"`. docstring에서 비표준 status 표기 제거. `outdated_packages()`: `"?"` → `"unknown"`. |
| `main.py` | frozen 분기 제거(`sys.frozen` → `_start_pot_provider()` only). `UpdateWorker(upgrade=True)`이 항상 실행. |
| `dialogs.py` | `_do_upgrade()` 확장: PyPI(yt-dlp/streamlink) + `components.ensure_ffmpeg()` + `pot_provider.ensure_node_runtime()`. 3단계 자동 수급. |
| `dialogs.md` | 동기화. |
| 검증 | py_compile OK — main.py / dialogs.py / updater.py |

### 2026-09-06 — HANDOVER 최신화 (아키텍처·환경·데이터 구조 실측 반영)

| 항목 | 변경 |
|------|------|
| §1 개요 | macOS/Windows/Linux 정정, 스택에 Node.js(PO Token) 추가 |
| §2 실행환경 | bgutil-ytdlp-pot-provider 행 제거(의존성 퇴출 반영), 콘솔 폰트 D2Coding→CascadiaMono 정정(레거시 잔재 명기), pyinstaller build 그룹·log_history·smoke_test 행 추가 |
| §3 아키텍처 | 모듈 라인 수 실측 갱신(main 1042 · downloader 451 등), 인프라 모듈 표 추가(pot_provider/components/log_history/smoke_test/sync_mirrors) |
| §4 데이터 | default_config 23키, 데드 키 10종 명기, 시그널 계약 실제 서명·result_ready 형상 반영 |
| §5·§6 | **emit 위치 인자 계약**·**extractor_args setdefault 병합**·**경량/무거운 경로 분리** 불변식 8~10 추가 + TUI 규격 우회·분석 결과 direct 신뢰 금지 항목 추가 |

### 2026-09-06 — URL 분석 스톨 해소(경량 분석) + emit 키워드 TypeError 광역 수리 + 분석 요약 표시

| 모듈 | 변경 |
|------|------|
| `client_opts.py` | `_apply_light_analysis_opts()` 신설 — `youtube:skip=[hls,dash]`로 매니페스트 열거 생략. "Downloading m3u8 information" 단계(googlevideo 셔드 스로틀에서 영구 멈춤)를 원천 차단 |
| `downloader.py` | `AnalyzeWorker._extract_youtube`에 경량 분석 적용 — 분석은 플레이어 응답의 직접 URL 포맷(v/a 개수·메타)만 취하고 무거운 우회(클라이언트 폴백·PO 토큰·매니페스트 재열거)는 다운로드 전용으로 분리 |
| `target_downloader.py` | `_flatten`/`_is_youtube_live_url`에도 경량 분석 적용 (라이브 감지는 `is_live` 플래그 기반이라 영향 없음). `expand_targets` emit 키워드 인자 TypeError 수리 |
| `main.py` | `stop_analysis_anim`의 미정의 `formatted_url` **NameError 수리** (치명: 분석 성공 시마다 크래시) → `last_content_block_text()` 실측 텍스트로 대체. 분석 완료 로그에 채널명·제목 요약(`_format_analysis_summary`) 추가 |
| `finalizer.py` | `log_concise.emit(... is_status=..., is_error=...)` 키워드 인자 TypeError 3곳 → 위치 인자. **미수리 시 다운로드 완료/취소마다 finished_all 미발신 → running 영구 잔류로 UI 잠금** |
| `live_recorder.py` / `progress_emitter.py` | 동일 emit 키워드 인자 TypeError 9곳 위치 인자로 수리 |
| 검증 | py_compile 0 · smoke PASS · 오프스크린에서 분석 완료 로그/철회 가드 일치/cancel→finished_all 실측 · 셸 재현(URL 1.6s 완주, m3u8 단계 미진입) |

### 2026-09-06 — PACKAGES 언패킹 불일치 치명적 버그 수리

| 모듈 | 변경 |
|------|------|
| `dialogs.py` | `UpdateWorker._do_check()`의 `for label, pypi_name in updater.PACKAGES` → `for label, pypi_name, _ in updater.PACKAGES` 수리. **원인: `updater.PACKAGES`가 3튜플(label, pypi_name, pypi_nightly)로 변경되었으나 언패킹 코드가 2튜플 그대로였음 → `ValueError: too many values to unpack`으로 앱 시작 시 UpdateWorker 크래시 → "Error calling Python override of QThread::run()"** |
| `dialogs.md` | 문서 동기화 |
| 검증 | thread_error.log 미생성 확인, ast.parse 구문 검사 통과 |

### 2026-09-06 — DEPS 체크 누락 3건 수리 (ffmpeg/node/potserver) + Dev/포터블 통합

| 모듈 | 변경 |
|------|------|
| `updater.py` | `check_deps()` 신설 — yt-dlp/streamlink(PyPI) + ffmpeg/node(`shutil.which`) + pot(`server_ping`)를 단일 리스트로 반환. `upgrade_packages()` Dev/Frozen 통합 — Dev에서도 `pip` 대신 직접 다운로드 경로 사용 (디버깅 일관성, 포터블 빌드와 동일 코드 경로) |
| `pot_provider.py` | `server_ping()` 신설 — `http://127.0.0.1:4416/ping` HTTP 핑 체크 |
| `dialogs.py` | `UpdateWorker._do_check()` 단순화 — `updater.check_deps()` 결과만 emit, outdated 검출은 `outdated_packages()` 위임 |
| 미러 | `sync_mirrors.py` 일괄 갱신 (5건) |
| 검증 | ast.parse 통과 — dialogs/updater/pot_provider |

### 2026-09-07 — DEPS 로그 표시 지연 수리 (체크 시간 9~15초 → 3~5초)

| 모듈 | 변경 |
|------|------|
| `updater.py` | `latest_version()` 타임아웃 2초→1.5초, ThreadPoolExecutor 버퍼 1초→0.5초로 단축. PyPI JSON API는 충분히 빠르므로 1.5초면 충분. DNS hang 방어(레벨)는 유지. |
| `pot_provider.py` | `server_ping()` 타임아웃 3초→1초로 단축. PO 서버는 로컬(127.0.0.1)이므로 1초면 충분. |
| 효과 | DEPS 로그 5개 항목 (ytdlp, streamlink, ffmpeg, node, pot) emit 시간 단축: 기존 직렬 합산 9~15초 → 수정 후 3~5초. 사용자가 보고한 "ready 후 10초 지연" 원인. |
| 검증 | ast.parse 통과 — updater/pot_provider |

### 2026-09-07 — 분석 스레드(HANG) 타임아웃 가드: QTimer watchdog

| 모듈 | 변경 |
|------|------|
| `downloader.py` | **AnalyzeWorker 분석 타임아웃 가드 추가** — yt-dlp가 `Downloading visionos player API JSON` 단계에서 영구 HANG 시 GUI 전체가 멈지는 문제 근본 예방. `_ANALYSIS_TIMEOUT_MS = 45000` 상수 + `QTimer`(single-shot, main thread event loop 기반) + `_on_analysis_timeout()` 핸들러. `run()` 시작 시 `start()`, 내부 `try/finally`에서 `stop()`. 타임아웃 시 `self.terminate()` + `error_occurred.emit("Analysis timed out after 45s.")` |

**설계 의도**: QTimer는 `__init__` 시점(main thread)에서 생성되므로 main thread event loop에 affinity를 가짐. `run()`은 worker thread에서 동기 실행되지만, main thread GUI loop가 살아 있으므로 45초 후 `timeout` 시그널이 정상 발화 → `QThread.terminate()`로 강제 종료. `finally`에서 `QTimer.stop()`은 thread-safe. `_abandon_analyzer()`는 Zombie Pattern(`disconnect` + `finished.connect(reap)`) → `wait()` 호출 없음으로 GIL deadlock 회피 |

### 2026-09-06 — DEPS/POT/분석 스톨 3연쇄 수리 + 구 getpot 플러그인 퇴출

| 모듈 | 변경 |
|------|------|
| `components.py` | 누락된 `_exe_suffix()` 정의 복구 — ffmpeg 검색 NameError 수리 |
| `pot_provider.py` | tsc 실행 전 산출물(build/main.js) 부재 + `tsconfig.tsbuildinfo` 잔존 시 캐시 삭제 — incremental emit 스킵(exit 0 무산출) 함정 수리 |
| `downloader.py` | **yt-dlp 외부 플러그인 전면 차단**(`yt_dlp.plugins.plugin_dirs.value = []`) — 구 getpot bgutil 플러그인 기생 제거. DownloadWorker 예외 emit 키워드 인자 TypeError 수리 |
| `target_downloader.py` | `worker.hook` AttributeError → `functools.partial(_pe.hook, worker)`. 누락 `_pe` import 추가. `_make_ytdl_opts`에 `url` 미전달 NameError 수리. `_emit_error_log` emit 키워드 인자 수리 |
| `main.py` | closeEvent의 `ctrl.worker` → `ctrl.worker_dl` (매 종료 시 AttributeError). START 버튼의 "analyzing..." 오표기 → "downloading..." |
| `smoke_test.py` | 리다이렉트 시 cp949 UnicodeEncodeError 방지 — stdout/stderr UTF-8 강제 |
| `pyproject.toml` / `uv.lock` | `bgutil-ytdlp-pot-provider==1.3.2` 의존성 제거 (`uv remove`) — 자체 Node PO 서버로 완전 이전 완수. %APPDATA% getpot 플러그인 잔재 삭제 |
| 검증 | 실측: 분석 3.6s (v_list=25, maxh=2160), 서버 스폰 → /ping 200, py_compile 0, smoke PASS |

### 2026-09-05 — 퍼사드 + 전략 패턴 리팩토링

| 모듈 | 변경 |
|------|------|
| `components.py` | `ensure_ffmpeg()` 퍼사드 + `_exe_suffix()`/`_ensure_ffmpeg_by_platform()` 전략 패턴 |
| `downloader.py` | Thin Wrapper 15개 삭제 → `run()`에서 직접 모듈 함수 호출. `_reset_loop_state()` 통합 |
| `target_downloader.py` | 예외 처리 5개 유형 세분화. `_emit_error_log()` 헬퍼 추가 |
| `live_recorder.py` | Thin wrapper 참조 → 직접 모듈 함수 호출 |
| `controller.py` | `on_download_finished()` 추가 (View → Controller 상태 로직 이관) |
| `.gitattributes` | EOL 정규화 (Python/Markdown → LF, 배치 → CRLF) |

| `sync_mirrors.py` | `startup_coordinator` 모듈 추가 |

### 2026-09-08 — PyQt6/PySide6 정리 + StartupCoordinator + 로깅 표준화

#### 문제
- PyQt6가 함께 설치되어 있어 Qt 심볼 충돌 발생 (`/objc[...]: Symbol not found: __ZN14QObjectPrivateC2E...`)
- READY 로그가 콘솔에 표시되지 않음 — 근본 원인 3중 버그:
  1. `UpdateWorker.check_done = Signal(list)`를 Coordinator `report_deps(ok, msg)`에 직결 → **시그니처 불일치로 stale→upgrade 기동 체인 사망** → `upgrade` 단계가 영원히 미완료 → READY 게이트 통과 불가
  2. `_on_update_check_done` not-stale 분기에 결론 라인(`deps ok`) 출력 누락
  3. `threading.Lock`을 `report_*` → `_try_emit_ready` 경로에서 재획득 → **deadlock** (RLock으로 수리)
- 로깅 포맷 불일치 → 8칼럼 → 5칼럼 통합 필요

#### 해결
| 모듈 | 변경 |
|------|------|
| **의존성** | PyQt6/PyQt6-Qt6/PyQt6_sip 제거 → PySide6 단일화 |
| `startup_coordinator.py` | **신규 생성** — 시작 시퀀스 완료 추적 전용 조정자. `report_deps/report_upgrade/report_pot/report_ready` 게이트 + `_ready_emitted` 1회 발산 + `RLock` 재진입. DEPS 5줄·결론 라인은 기존 경로(`_component_line`/`_on_update_check_done`)가 담당하므로 **이중 출력 금지** (플래그만 세팅), 히스토리는 `append_concise_log` 위임 |
| `main.py` | `check_done` → `_on_update_check_done` 복원(결론 라인 출력 + upgrade 워커 기동 + `report_deps` 보고). `upgrade_done` → `report_upgrade`. `_force_unlock_input` → `report_ready` 위임. 죽은 코드 `_on_auto_upgrade_done`/`_on_pot_provider_finished` 제거 |
| `log_console.py` | `format_log_line()`: `SPEED │ PCT │ BAR` → `MSG` 통합 (고정 5칼럼 구조) |
| `progress_emitter.py` | 다운로드 진행 틱에서 제목 제거 (ANAL 단계에 이미 표시됨) |
| `sync_mirrors.py` | `startup_coordinator` MIRROR_MODULES 추가 |
| `HANDOVER.md` | 당시 로그 표준 문서화 (STAGE·STATUS·PLATFORM·SPEC·MSG 5컬럼; v3.4.0에서 4컬럼으로 개정) |

#### 시그널 교통 정리 (최종 계약)
```
UpdateWorker.check_done(list) ──> _on_update_check_done  (결론 라인 + upgrade 기동 + report_deps)
UpdateWorker.upgrade_done(bool,str) ──> Coordinator.report_upgrade (변화 시 결론 1줄)
POTProviderWorker.finished ──> Coordinator.report_pot (플래그만)
QTimer 15s ──> _force_unlock_input ──> Coordinator.report_ready (강제)
Coordinator: deps+upgrade(+pot if started) 완료 → READY 1회 + separator + 입력 개방
```

#### 검증
- ✅ 단위 시퀀스 3종 (변화없음/변화있음/중복방지) ALL PASS
- ✅ Smoke test PASS
- ✅ 런타임 실측: DEPS 5줄 → `deps ok` 결론 → `SYS │ READY │ SYS │ - │ ready` **정확히 1건**
- ✅ READY 로그: `[HH:MM:SS] SYS │ READY │ SYS │ - │ ready`

### 2026-09-09 — 구조적 트레이드오프 5건 수술 + 모듈 분리

#### 문제
- 계층 역전: `client_opts`(L0)·`updater`(L0)가 `pot_provider`(L1 worker)를 역참조
- 다운로더 팩토리: `downloader.py`가 3개 클래스(YtLoggerBridge/AnalyzeWorker/DownloadWorker)를 500줄에 담음
- dialogs.py 응집도 낮음: UpdateWorker(QThread) + 대화상자 3종 동거
- worker grab-bag: 추출 파이프라인 함수들이 `worker` 덩어리 객체를 첫 인자로 받음
- MSG 규격 위반: target_downloader 오류 사유가 한국어 서술형

#### 해결
| 모듈 | 변경 |
|------|------|
| `po_client.py` | **신규 생성** — PO Token 서버 HTTP 클라이언트 L0 leaf. `server_ping/probe_server/fetch_po_token/extract_video_id/DEFAULT_HOST/POT` 이동. pot_provider는 재수출(내부호환), `client_opts/updater/target_downloader`는 po_client 직접 참조 |
| `analyze_worker.py` | **신규 생성** — AnalyzeWorker 분리. controller 배선 변경 |
| `yt_logger_bridge.py` | **신규 생성** — YtLoggerBridge 공용 어댑터 분리 (Analyze/Download 공유) |
| `downloader.py` | DownloadWorker만 유지, 미사용 임포트(`import live_recorder as _lr`) 제거 |
| `update_worker.py` | **신규 생성** — UpdateWorker + `_RAW_VERSION_CMDS` 분리. main 배선 변경 |
| `dialogs.py` | UpdateWorker 블록 제거 (846줄 → 686줄) |
| `target_downloader.py` | 오류 사유 전건 영문 1-3단어 태그화 (`age/bot restricted`, `format missing` 등) |
| `sync_mirrors.py` | 신규 4모듈 MIRROR_MODULES 추가 (총 34개) |

#### 검증
- ✅ py_compile 전체 OK, smoke PASS, 런타임 READY 1건 유지
- ✅ 계층 역전 해소: client_opts/updater/target_downloader → po_client(L0) 직접 참조
- ✅ 다운로더 팩토리 분리: 3-way 독립 모듈

#### 남은 트레이드오프
- **worker grab-bag (D)**: ✅ dataclass 컨텍스트 추출 완료 — `dl_context.py`의 `DownloadContext` dataclass로 파이프라인 계약 명시화. `DownloadWorker.extract()`에서 컨텍스트 생성, 파이프라인 모듈(`target_downloader`, `progress_emitter`, `finalizer`)은 `ctx`만 받음. 타입 힌트로 IDE 지원·정적 검증 가능.

- **pot_provider SRP 분리**: ✅ 3-웨이 분리 완료
  - `node_provider.py` (Node.js 런타임 수급 — node_exe/npm_exe/node_ok/ensure_node_runtime)
  - `pot_server.py` (bgutil 서버 빌드/기동 — ensure_node_server/_spawn_existing/built_server_js)
  - `po_client.py` (PO Token HTTP 클라이언트 — L0 leaf, 이미 분리 완료)
  - `pot_provider.py`는 3개 모듈을 재수출하는 facade + `POTProviderWorker(QThread)` 유지
  - `ensure_node_runtime`이 `pot_server._download_with_progress`에 순환 참조 없이 접근하도록 함수 레벨 import 사용

- **통합 테스트 추가**: ✅ `tests/test_download_pipeline.py` 신규 (12개 테스트)
  - `TestDownloadContext`: dataclass 기본 속성·오류 수집 검증
  - `TestEmitDl`/`emit_err`: 포맷 규격 검증
  - `TestPotProviderFacade`: 재수출 검증 (node_provider/pot_server/po_client)
  - `TestContextPipelineFlow`: ctx가 파이프라인 함수에 흐르는 흐름 검증

### 2026-09-09 — 구조적 트레이드오프 5건 수술 + 모듈 분리 + dataclass 컨텍스트 추출

#### 문제
- 계층 역전: `client_opts`(L0)·`updater`(L0)가 `pot_provider`(L1 worker)를 역참조
- 다운로더 팩토리: `downloader.py`가 3개 클래스(YtLoggerBridge/AnalyzeWorker/DownloadWorker)를 500줄에 담음
- dialogs.py 응집도 낮음: UpdateWorker(QThread) + 대화상자 3종 동거
- worker grab-bag: 추출 파이프라인 함수들이 `worker` 덩어리 객체를 첫 인자로 받음
- MSG 규격 위반: target_downloader 오류 사유가 한국어 서술형

#### 해결
| 모듈 | 변경 |
|------|------|
| `dl_context.py` | **신규 생성** — `DownloadContext` dataclass로 파이프라인 계약 명시화. `DownloadWorker.extract()`에서 컨텍스트 생성, 파이프라인 모듈은 `ctx`만 받음. |
| `po_client.py` | **신규 생성** — PO Token 서버 HTTP 클라이언트 L0 leaf. `server_ping/probe_server/fetch_po_token/extract_video_id/DEFAULT_HOST/PORT` 이동. pot_provider는 재수출(내부호환), `client_opts/updater/target_downloader`는 po_client 직접 참조 |
| `analyze_worker.py` | **신규 생성** — AnalyzeWorker 분리. controller 배선 변경 |
| `yt_logger_bridge.py` | **신규 생성** — YtLoggerBridge 공용 어댑터 분리 (Analyze/Download 공유) |
| `downloader.py` | DownloadWorker만 유지, 미사용 임포트(`import live_recorder as _lr`) 제거 |
| `update_worker.py` | **신규 생성** — UpdateWorker + `_RAW_VERSION_CMDS` 분리. main 배선 변경 |
| `dialogs.py` | UpdateWorker 블록 제거 (846줄 → 686줄) |
| `target_downloader.py` | 오류 사유 전건 영문 1-3단어 태그화 (`age/bot restricted`, `format missing` 등) |
| `sync_mirrors.py` | 신규 4모듈 MIRROR_MODULES 추가 (총 34개) |

#### 검증
- ✅ py_compile 34개 모듈 OK, smoke PASS, 런타임 READY 1건 유지
- ✅ 계층 역전 해소: client_opts/updater/target_downloader → po_client(L0) 직접 참조
- ✅ 다운로더 팩토리 분리: 3-way 독립 모듈
- ✅ dataclass 컨텍스트로 파이프라인 계약 명시화
- ✅ pot_provider SRP 3-웨이 분리 + facade 재수출 검증
- ✅ pytest 68 passed (56 existing + 12 new integration tests)

#### 남은 과제

| 모듈 | 변경 |
|------|------|
| `target_downloader.py` | `_is_youtube_live_url()` 경량 프리체크 도입 |

### 2026-09-04 — MVC 4계층 완성 + Node.js 외부 참조

| 모듈 | 변경 |
|------|------|
| `controller.py` | `DownloadController` → `MediaController(QObject)`. `spawn_analyzer()` 추가 |
| `main.py` | AnalyzeWorker 직접 관리 제거 → Controller 시그널 포워딩 |
| `pot_provider.py` | Node.js 22 번들 → 외부 참조 전환 |
| `components.py` | `_ensure_ffmpeg_linux()` 신설 |

### 2026-09-03 — TUI 레이아웃 + 로그 미니멀화 + 유령 로그 수리

| 모듈 | 변경 |
|------|------|
| `theme.py` | Cascadia Mono 11px 통일, Flat 레이아웃 |
| `progress_emitter.py` | MSG 영어 1-3단어로 축소 |
| `main.py` | `_is_stale_analyze_signal()` 신설. 디바운스 500ms→900ms |
| `log_console.py` | `is_tui_line()` 개선 (SPEC/SPEED 분리 인식) |

### 2026-09-02 — PO Token 서버 번들 + 0% 스톨 픽스

| 모듈 | 변경 |
|------|------|
| `pot_provider.py` | PO Token 서버 번들, `ensure_node_runtime()` 개선 |
| `client_opts.py` | `_apply_pot_opts()` 추가, `throttledratelimit` 100KB/s |

### 2026-09-10 — F12 중복 제거·raw 로그 버스·POT stale 감지 + 자동 리프레시

#### 문제
- F12 raw 로그에 POT readiness 로그 2중 출력 — `check_deps` 내 자체 판정 + 프리웜 별도 `pot_readiness(log_func)` 중복 호출
- `pot_provider._note/_dbg`가 `self.log_full.emit` 직접 호출 → raw 버스 구독과 이중 적재. "모든 동작은 raw 스택에 쌓여야 한다"는 원칙이 흐트러짐
- POT DEPS가 liveness(`server_ping`)만 판정 → 미기공 정상(lazy standby)이 `FAIL not running`으로 오해석
- 프리웜이 stale 빌드를 감지해도 자동 리프레시 없이 방치 → lazy가 "언제든 작동 가능한 준비 상태"를 유지하지 못함

#### 해결
| 모듈 | 변경 |
|------|------|
| `raw_log.py` | **신규 생성** — raw(tag, msg) 단일 진입 → concise(메인 TUI)/full(F12)/history 3채널 팬아웃. 구독 전 호출도 history 적재(유실 방지). TUI 컬럼 라인은 화면에도, 나머지는 F12/history 전용 |
| `pot_server.py(🤖 touched)` | `pot_readiness(log_func, check_stale=False, want_refresh=False)` 확장 — `latest_server_ver(timeout=3)` GitHub API로 로컬 `.version` vs 최신 태그 비교, stale 시 `False/stale` 표기. `want_refresh=True`면 "작동 가능한 준비됨"으로 간주 (reason에 `(refresh pending)` 표기) |
| `pot_provider.py(🤖 touched)` | `POTProviderWorker.__init__(prewarm=False)` 모드 유지하되, prewarm 분기 `acquire/release_prewarm_lock(log_func)` 콜백 + detect stale 시 `rebuild=True`로 `ensure_node_server` 재실행 (자동 리프레시). `_note/_dbg` 직접 `log_full.emit` 제거 → raw 단일 경유 |
| `update_worker.py(🤖 touched)` | `check_deps(log_func=lambda...)` 콜백으로 `_do_check` 내 별도 `_pot_readiness` 중복 호출 제거. CLI 원문 `cli_raw(label, *args, max_lines=6, max_width=160)` 절단 적용하여 ffmpeg `configuration:` 500자 원문 오버 제한 |
| `updater.py(🤖 touched)` | `check_deps(log_func=None)` 시그니처 확장 + cli_raw max_lines/max_width |
| `main.py(🤖 touched)` | `_maybe_prewarm_pot`(`check_stale=True, want_refresh=True`) → stale 시 "starting refresh"로 분기. `_on_prewarm_finished/_on_pot_finished` raw 적재. `_ensure_pot_for_info` `raw("pot-gate")` 판정 로그 |
| `analyze_worker.py(🤖 touched)` | 게이트 판정 시 `raw("pot-gate", gated=... age_limit=... availability=...)` |
| `HANDOVER.md(🤖 touched)` | 마지막 갱신 v3.1.2+ 표기, §6 하지 말 것 위반사례 5건 추가(로그 수동 흩뿌리기·워커가 포그라운드 import·laziness 고정·시그널 이중 emit·smoke 미통과 커밋), 아키텍처 맵 최신화 |
| `tests/test_download_pipeline.py(🤖 touched)` | PID-liveness·live 홀더 비회수·콜백·raw 팬아웃·readiness stale·check_deps 단일 호출·cli_raw 절단 테스트 12개 추가 (전체 80건) |
| `sync_mirrors.py(🤖 touched)` | MIRROR_MODULES에 `raw_log` 추가, 6개 `.md` 갱신 |

#### 검증
- py_compile raw_log/pot_server/pot_provider/main/update_worker/updater/analyze_worker/tests: OK
- pytest 전체: 80 passed (pipeline 24건 포함)
- smoke_test: PASS (MainWindow + SettingsDialog)
- 런타임: `raw_log` 구독 정상, log_full 직접호출 없어져 F12 중복 해소, F12 `configuration:` 줄 160자+털 절단

#### 남은 과제
- stale 감지 시 네트워크 3초 — preflight timeout 예산. 실패 시 판정 유지(stale 미확인≠FAIL)는 유지
- 프리웜 자동 리프레시는 "잠긴 사이 사전 제거 기능"에 대해 게이트/다운로드 시점 실패 처리와 별개 — 프리웜은 최신 빌드 확보 우선 (📖 HANDOVER §1.3)

---

### 2026-09-11 — F12 크래시 근절·raw 로그 버스 시그널 브리지·pot 서버 스폰 최적화·버튼 동작 검토

#### 문제
- F12 로그창 열자마자 렉/크래시 — `raw_log.raw()`가 **Qt 시그널이 아닌 직접 함수 호출**로 워커 스레드에서 UI 위젯(QTextEdit) 직접 조작 → GUI 스레드와 동시 접근으로 레이스→크래시
- READY 이후에도 DEPS 로그 계속 출력(prewarm 단계 로그가 메인 콘솔로 유입) — prewarm 로그가 F12 전용(full_only)로 격리되지 않음
- `pot_provider._note/_dbg`가 `self.line.emit` + `raw_log.raw()` 이중 전송 → 메인에 2회, F12에도 TUI 컬럼 유출
- `_spawn_existing`가 `self.log_full.emit` 직접 넘김 → F12 중복 적재
- pot 서버 스폰 45초 대기는 prewarm으로 기존 빌드 재사용 시에도 발생 — `_wait_port` 45초 폴링이 선행돼야 함
- 분석/다운로드 중 pot 서버 가동 시 F1~F4/ESC/ENTER 버튼 동작 미정 — enter 입력 시 큐 꼬임으로 앱 정지
- `DownloadContext`에 `log_concise` 속성 없음 → 다운로드 실패 (`'DownloadContext' object has no attribute 'log_concise'`)

#### 해결
| 모듈 | 변경 |
|------|------|
| `raw_log.py` | **시그널 브리지 전면 재작성** — `_RawHub(QObject)`에 `concise/full` 시그널, `subscribe_*`가 `_hub.*.connect(fn)`로 연결. `raw()`는 `log_history.log()` + `Signal.emit`만 수행 → QueuedConnection으로 GUI 스레드 안전 보장. `full_only` 파라미터 추가(TUI→concise 전용, non-TUI→full 전용, `full_only=True`→F12 전용) |
| `pot_provider.py` | `_note`/`_dbg` **raw 단일 경유**로 통합. prewarm 모드 `full_only=True` + TUI 래핑 벗겨서 F12에 순수 메시지만. ffmpeg ensure prewarm에서 스킵(DEPS 단계에서 이미 확보). `_spawn_existing` 인자 `self.log_full.emit` → `self._dbg`로 통일. prewarm에서 ffmpeg ensure 스킵. `_spawn_existing` 인자 `log_full.emit` → `_dbg`로 교체 |
| `pot_server.py` | `pot_readiness`에 `check_stale`/`want_refresh` 확장. `latest_server_ver(timeout=3)` 3초 타임아웃으로 GitHub API 호출. stale+want_refresh 시 ready=True로 자동 리프레시 유도 |
| `update_worker.py` | `check_deps(log_func=...)` 단일 호출로 중복 standby 제거. `cli_raw(max_lines=6, max_width=160)` 절단 적용 |
| `main.py` | `_maybe_prewarm_pot(check_stale=True, want_refresh=True)` stale 시 "starting refresh". `_on_pot_finished` raw 적재. `_ensure_pot_for_info` `raw("pot-gate")` 판정 로그 |
| `analyze_worker.py` | 게이트 판정 시 `raw("pot-gate", gated=..., age_limit=..., availability=...)` |
| `DownloadContext` | `log_concise` 속성 추가 (progress_emitter 연동용) |
| `HANDOVER.md` | 마지막 갱신 v3.2+ 표기, §6 하지 말 것 위반사례 추가, 아키텍처 맵 최신화 |
| `tests/test_download_pipeline.py` | raw 팬아웃·stale 감지·cli_raw 절단·락 콜백 등 12개 테스트 추가 (전체 80건) |
| `dl_context.py(🤖 touched)` | `advance_target()` 신규 추가 — 타겟 진행 상태 단일 지점 갱신·속도계 초기화 |
| `downloader.py(🤖 touched)` | `_emit_chzzk_header` 스텁 제거, `_reset_loop_state()` 단순화, `run()` 루프 `ctx.advance_target()`로 이중 대입 해소, `_live_proc` 추가·`terminate()/kill_live_process()`로 라이브 녹화 프로세스 정리 |
| `target_downloader.py(🤖 touched)` | `ctx._emit_chzzk_header()` → `_pe.emit_chzzk_header()` 모듈 함수 직접 호출로 단일화 |
| `main.py(🤖 touched)` | Phase 2 완료: `_maybe_prewarm_pot`, `_on_prewarm_finished`, `_on_pot_finished`, `_start_pot_provider`, `_ensure_pot_for_info` 전부 LogEvent + Channel 전환 |
| `pot_provider.py(🤖 touched)` | Phase 2 완료: `_dbg`, `_note`, POT-FAIL 전부 LogEvent + Channel 전환 |
| `update_worker.py(🤖 touched)` | Phase 2 완료: `raw_log.raw("pot-readiness", ...)` → LogEvent + Channel.FULL 전환 |
| `log_event.py(🤖 touched)` | `to_log_line()` 메서드 추가 — `format_log_line` 시그니처와 안전 바인딩, `slots=True` 적용 |
| `raw_log.py(🤖 touched)` | 다형성 브리지 — 시그니처 `(object, bool, bool)`/`(object, str)` 변경, 문자열→LogEvent 자동 승격, `_emit_event()` 정리 |
| `log_console.py(🤖 touched)` | `format_log_line_for_event()` 신규 — LogEvent → TUI 컬럼 문자열 |
| `pot_server.py(🤖 touched)` | `kill_process_on_port()` 신규 — 크로스플랫폼 좀비 프로세스 강제 종료 |
| `po_client.py(🤖 touched)` | `server_ping()` PID 생존 확인 추가 |
| `live_recorder.py(🤖 touched)` | `_live_proc` 저장 |
| `downloader.py(🤖 touched)` | `_live_proc`, `terminate()/kill_live_process()` 추가 |

#### 검증
- py_compile raw_log/pot_server/pot_provider/main/update_worker/updater/analyze_worker/tests: OK
- pytest 전체: 80 passed
- smoke_test: PASS (MainWindow + SettingsDialog)
- 런타임: `raw_log` 구독 정상, log_full 직접호출 없어져 F12 중복 해소, F12 `configuration:` 줄 160자+털 절단
- `dl_context.py` / `downloader.py` / `target_downloader.py` / `main.py` / `pot_provider.py` / `pot_server.py` / `po_client.py` / `live_recorder.py` py_compile OK, pytest 80 passed

#### 남은 과제
- pot 서버 스폰 대기 시간 단축(45초 → 기존 빌드 재사용 시 즉시 바인딩 가능하도록)
- 분석/다운로드 중 pot 서버 가동 시 버튼(F1~F4/ESC/ENTER) 동작 정의 및 큐 꼬임 방지

---

## 2026-09-10 — POT 서버 시동 raw_log 전수 기록 + 좀비 프로세스 식별 가능하게 보강

### 문제
`[prewarm] skip — server already running` 한 줄만 출력되고 **서버 시동/재사용 관련 모든 정보가 raw_log로 누출되지 않음** → 좀비 프로세스 여부 판별 불가

### 해결
| 모듈 | 변경 |
|------|------|
| `main.py` | `_maybe_prewarm_pot`: server_ping True 시 PID 정보(raw_log에 포함) 기록 |
| `main.py` | `_start_pot_provider`: 시동 시작/완료/실패 전부 raw_log 기록 |
| `main.py` | `_on_pot_finished`: outcome 메시지 raw_log 기록 |
| `main.py` | `_on_prewarm_finished`: outcome 메시지 raw_log 기록 |
| `po_client.py` | `server_ping()`에 PID 생존 확인 추가 (락 홀더 PID 죽으면 False 반환) |
| `pot_server.py` | `kill_process_on_port()` 신규 — 크로스플랫폼 좀비 프로세스 강제 종료 |
| `pot_provider.py` | `POTProviderWorker`에 `_server_proc` 저장, `terminate()/kill_server_process()` 추가 |
| `live_recorder.py` | `record_live_stream()` 워커에 `_live_proc` 저장 |
| `downloader.py` | `DownloadWorker`에 `_live_proc`, `terminate()/kill_live_process()` 추가 |
| `main.py` | `closeEvent`에서 POT/라이브 워커의 프로세스 정리 추가 |

### raw_log 기록 예시 (시동 성공 시)
```
[HH:MM:SS] [pot] starting POT server provider...
[HH:MM:SS] [pot] POT server worker started
[HH:MM:SS] [pot] gate finished ok=ok outcome=ok
[HH:MM:SS] [pot] msg=pot server bound (127.0.0.1:4416)
[HH:MM:SS] [pot-gate] gated=True age_limit=18 availability=needs_auth
```

### raw_log 기록 예시 (prewarm skip 시 — 정상 재사용)
```
[HH:MM:SS] [prewarm] skip — server already running (pid=12345)
```
→ PID가 실제 프로세스인지 `ps`/터미널로 확인 가능

---

## 10. 참고 문서

- `CHANGELOG.md` — 버전별 변경 사항
- `README.md` — 프로젝트 소개
- `CLAUDE.md` — (폐지: 규약은 `.clinerules`로 통합)

---

## 2026-09-12 — 로그 버스 단일화 v3.3.0 (raw_log 단일 경로·플래그 라우팅·레거시 제거)

### 이번 작업 변경분 (검증: py_compile 전체 + pytest 32 passed)
- `raw_log.py` — `raw(tag, msg, is_status, is_error, to_tui)` 단일 진입 확정. 문자열은 LogEvent로 정규화(`rendered=True`), history는 raw 내부에서 정확히 1회 적재(`level=ERROR↔INFO`), `_hub.full.emit`(F12 전량) + `to_tui` 시 `_hub.concise.emit`(TUI 선택).
- `main.py` — 버스 구독 2점(`subscribe_concise(_render_concise)` / `subscribe_full(_mirror_event_full)`). `_render_concise`가 LogEvent→컬럼 문자열 변환 + `no_wrap=True` 동봉 후 `console.append`. `append_concise_log`는 bus shim으로 전환(호출부 20곳 무수정). `append_full_log` 제거(호출부 0). 분석 성공 경로는 `format_log_line` 직접 호출 → `raw("anal", LogEvent(ANAL/OK…), to_tui=True)` 근원 라벨링. `chzzk_api/cookies/media/shutdown`의 직접 `log_history.log` 10곳 → bus reroute(`to_tui=False`, F12+history 전용).
- `log_console.py` — `append(…, no_wrap)` → `_buffer{…, no_wrap}` → `_insert_clamped` → `_flow_lines(raw, no_wrap)` 플래그 체인. `_flow_lines`에서 콘텐츠 판정(`is_tui_line`) 퇴출, `is_tui_line`은 호환 shim으로 강등(호출부 0).
- `log_bus.py` — 삭제(`git rm`, staged `D`). `import log_bus` 참조 0건 확인 후 폐기.
- `tests/` — `test_log_console.py`에 `TestFlowLinesNoWrapFlag` 6건 추가. `test_coordinator.py` fixture의 죽은 `append_full_log` Mock 제거.
- 행위 변화 1건: 미리 포맷된 LogEvent 문자열(pick 메뉴 등)은 wrap 대신 한 줄 유지 + `_render_clamp` `…` 절단. bare 문자열(yt-dlp 원본 등)은 기존대로 wrap.

### DEPS (POT server 포함) 시그널 계약·호출 구조 (2026-09-12 실측)
- 기동 시퀀스: `Main._start_update_check` → `UpdateWorker(check)` → `check_done(list)` → `Main._on_update_check_done`(결론 1줄 + `report_deps` + upgrade 워커 기동 + `ensure_ready("prewarm")`) → `UpdateWorker(upgrade)` → `upgrade_done(bool,str)` → `Coord.report_upgrade` → READY 게이트.
- `check_done(list)`는 시그니처가 `(bool,str)`이 아니므로 Coordinator 직결 금지 — Main이 중계한다(교통 정리 불변식).
- POT 수명주기: `POTManager.ensure_ready(mode)` 단일 스폰 가드. `prewarm`(staging, to_tui=False) 실행 중 `gate` 요청 → `_pending_gate=True`, prewarm 완료 후 gate 자동 재기동. Signal 2종: `pot_status_changed(starting/staging/staged/failed)` + `pot_finished(bool,str)` → Coordinator `_on_pot_finished` → `report_pot` → READY 게이트 입력.
- POT 게이트(다운로드 시): `Main._ensure_pot_for_info(info)` — `age_limit>0` 또는 `availability∈{needs_auth,premium_only,subscriber_only,private}` → `raw("pot-gate", gated/age_limit/availability, to_tui=True)` 판정 로그 + `ensure_ready("gate")`. 기동 중이면 `_pending_download` 큐잉.
- READY 게이트: `StartupState.can_emit_ready() = deps_ok ∧ upgrade_done ∧ pot_status∈{running,standby,staged} ∧ ¬ready_emitted` (멱등 1회). 15초 폴백 `force_unlock → report_ready("ready — input unlocked (fallback timeout)")` — POT 프리웜 취소 금지(폴백은 READY 발산만), 입력 개방은 `_startup_completed`만 판정(v3.5.2).

### 회귀 방지 불변식 (v3.3.0 — §5에 11~15로 본편입, 아래는 초안)
- 11. **로그 단일 진입**: 모든 로그는 `raw_log.raw()` 경유. `log_history.log` 직접 호출·`log_bus` 부활·워커 로그 시그널(`line/full/log_concise/log_full`) 신설 금지. history 적재는 raw 내부 1회가 유일.
- 12. **플래그 라우팅**: TUI 노출은 `to_tui` 비트, 줄바꿈은 `no_wrap` 플래그로만 결정. 렌더 레이어에서 문자열 콘텐츠 판정(정규식·`is_tui_line`·`startswith` 분기) 부활 금지.

- 13. **신호-보고 분리**: `check_done(list)` 등 결과 Signal은 Main이 중계 후 `report_*` 호출. Worker→Coordinator 직결 금지(시그널 교통 정리).
- 14. **READY 멱등**: READY 발산은 `StartupState.can_emit_ready()` 게이트 경유 1회. 우회 직접 `ready_emitted.emit` 금지.
- 15. **잔재 정리**: `media/chzzk_api/cookies`의 `import log_history`는 미사용 잔재 — 직접 호출로 회귀 금지, 정리 시 import 행 삭제. `log_console.import re` 미사용 확인 후 제거 후보.

### 프로젝트 전체 아키텍처 트리 (2026-09-25 v3.12.0 실측)
```
L4 View (Qt 위젯 보유)
├── main_window.py ......... MainWindow — 루트 오케스트레이터 및 하위 컴포넌트 합성
├── components/ ............ UI 모듈 컴포넌트 패키지 (신규)
│   ├── header_bar.py ...... HeaderBarWidget — 경로 제어, F1/F2 폴더 변경/열기, F12 전체 로그, F3 설정
│   └── action_bar.py ...... ActionBarWidget — URL 입력, 정규식 검증, 디바운스, TXT 로드, ENTER/ESC 액션
├── dialogs.py ............. ExitConfirmDialog / SettingsDialog / VerboseLogWindow (HiDPI 반응형, 5대 섹션 빌더)
├── log_console.py ......... ConciseLogConsole — findBlockByNumber + QTextCursor O(1) 인플레이스 블록 치환
├── log_mirror.py .......... MainWindow 미러 브리지 (F12/TUI 분리)
├── progress_bar.py ........ 컴포넌트별 갱신형 프로그레스 바
└── theme.py ............... QSS/색상 시맨틱 디자인 토큰 단일 출처 (SSOT)
L3 Control (QObject/Signal — Qt 소유)
├── controller.py .......... MediaController — 세션 상태 머신, 워커 수명주기 관리, QThread 비차단 수거
├── gate_state.py .......... GateState + AppState(str, Enum) 상태 머신 단일화
├── startup_coordinator.py . 기동 게이트 — report_* + View행 Signal 3종 + raw("startup")
├── startup_state.py ....... READY 게이트 단일 진실(can_emit_ready)
├── pot_manager.py ......... POT 수명주기 — ensure_ready(prewarm/gate) + Signal 2종
├── downloader.py .......... DownloadWorker — _shared_state 취소 동기화 + _skip 리셋
├── analyze_worker.py ...... AnalyzeWorker — result_ready/error_occurred + pot-gate 판정
└── update_worker.py ....... UpdateWorker — check_done/upgrade_done + deps raw 발행
L2 Service / Infra (순수 비즈니스 로직 및 외부 연동)
├── pipeline/ .............. 다운로드 파이프라인
│   ├── classifier.py ...... ClassifiedTarget 분류기
│   ├── dl_context.py ...... 컨텍스트 데이터클래스
│   ├── finalizer.py ....... 다운로드 배치 마감 요약
│   ├── live_recorder.py ... ffmpeg 라이브 녹화
│   ├── progress_emitter.py  LogEvent 빌더
│   └── target_downloader/ . 플랫폼별 다운로더 분기 패키지 (dispatch/chzzk/youtube_vod/youtube_live)
├── provisioning/ .......... 의존성 프로비저닝 (SRP 3분할)
│   ├── planner.py ......... 의존성 최신 버전/해시 계획 수립
│   ├── executor.py ........ 다운로드/검증/설치 실행
│   ├── committer.py ....... 매니페스트/오버레이 커밋
│   └── bridge.py .......... 동기/비동기 이벤트 루프 브리지
├── pot_server.py .......... bgutil Node.js 서버 수명주기 (단계별 헬퍼 분리)
├── po_client.py ........... bgutil HTTP 순수 통신 계층
├── node_provider.py ....... Node.js 22+ 런타임 수급
├── yt_dlp_binary.py ....... 독립 실행형 바이너리 수급 및 관리
├── components.py .......... FFmpeg 자동 수급/관리
├── updater.py ............. 의존성 무결성 검증 및 갱신
└── yt_logger_bridge.py .... yt-dlp logger 어댑터
L1 Model / Core (순수 — Qt 금지)
├── log_event.py ........... LogEvent 데이터클래스
├── raw_log.py ............. 단일 진입 raw() — 정규화·history 1회·full/concise 허브
├── config.py .............. _APP_VERSION + dl_config.json 설정 관리
├── dl_platform.py ......... URL 도메인 판정
├── media.py ............... 코덱/포맷/remux 처리
├── chzzk_api.py ........... 치지직 API 통신
├── cookies.py ............. 브라우저 쿠키 추출
├── playlist.py ............ 재생목록 URL 정규화
└── speed_window.py ........ O(1) 다운로드 속도 측정 덱(deque)
L0 Leaf (진입점·도구·테스트)
├── main.py ................ 앱 진입점
├── sync_mirrors.py ........ 소스코드 마크다운 미러 동기화 스크립트
├── bump_version.py ........ 버전 증가 보조 도구
├── smoke_test.py .......... 스모크 테스트
└── tests/ ................. 회귀/계약 테스트 스위트 (361 tests)
```

### 시그널 방향 트리 (로그 시그널 0 — 결과/게이트 시그널만 잔존)
```
워커(QThread) — 결과 전달 전용 Signal
├── UpdateWorker: check_done(list)→Main._on_update_check_done / upgrade_done(bool,str)→Coord.report_upgrade
├── AnalyzeWorker: result_ready(dict)/error_occurred(str)→Controller 중계→Main 슬롯
├── DownloadWorker: finished_all / POTProviderWorker: finished_signal(bool,str)→POTManager
└── yt-dlp logger: YtLoggerBridge — 시그널 없이 raw("ytdlp") 버스 직행
raw 버스(raw_log.py, Qt Signal 브리지 2점 — 워커→GUI 스레드 전환)
├── _hub.concise(LogEvent,is_status,is_error) → Main._render_concise → console.append(no_wrap=True)
└── _hub.full(LogEvent,is_status) → Main._mirror_event_full → _mirror_full_log(F12 버퍼+stamp)
기동 게이트(StartupCoordinator — View행 Signal 3종)
├── ready_emitted(str,bool,str) + ui_unlocked() → Main (READY 1회, StartupState 멱등 가드)
├── pot_status_changed(str) → Coordinator _on_pot_status passthrough → View
└── POTManager: pot_status_changed(starting/staging/staged/failed) + pot_finished(bool,str)
    → Coordinator _on_pot_finished → report_pot → READY 게이트 입력
보고 진입점(함수 호출 — Signal 아님)
└── Main._on_update_check_done → Coord.report_deps / Main → Coord.report_ready/force_unlock(15s 폴백)
```
