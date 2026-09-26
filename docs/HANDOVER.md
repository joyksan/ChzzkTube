# HANDOVER.md — ChzzkTube 인수인계서

> 이 문서는 다음 담당자(사람 또는 AI 에이전트)를 위해 작성된 프로젝트 인수 문서다.
> 코드 수정 전 반드시 **§1.1 버전 관리 절차**, **§1.2 경로 계약**, **§1.3 개발 방향성 및 TUI 표준**, **§5 불변식**, **§6 하지 말 것**을 읽을 것.
> 마지막 갱신: 2026-09-26 - v3.12.4 — pot_server DEFAULT_HOST re-export 누락 회귀 복구·POT 워커 크래시 F12 추적 보강·에러 버스 배선 안정화
---
## 목차

- [1. 프로젝트 개요](#1-프로젝트-개요)
- [2. 버전 관리 절차](#2-버전-관리-절차)
  - [2.1 버전 진실 공급원과 정책](#21-버전-진실-공급원과-정책)
  - [2.2 버전 증가 절차](#22-버전-증가-절차)
  - [2.3 `bump_version.py` 제한](#23-bump_versionpy-제한)
- [3. 기술 스택 및 디펜던시](#3-기술-스택-및-디펜던시)
- [4. 폴더 구조 및 경로 계약](#4-폴더-구조-및-경로-계약)
  - [4.1 기본 디렉터리](#41-기본-디렉터리)
  - [4.2 런타임 캐시·외부 구성요소](#42-런타임-캐시·외부-구성요소)
  - [4.3 경로 관련 불변식](#43-경로-관련-불변식)
- [5. 아키텍처 상세 및 모듈 명세](#5-아키텍처-상세-및-모듈-명세)
  - [5.1 레이어별 구조 (4계층 + L0 Leaf) — v3.4.0 레이아웃 리팩터링(`chzzktube/` 단일 패키지)](#51-레이어별-구조-4계층--l0-leaf-—-v340-레이아웃-리팩터링chzzktube/-단일-패키지)
  - [5.2 모듈 목록 (95개 루트 .py — 2026-09-25 `find *.py` 실측. `tool_log.py` 포함. [상세 트리](‍#2026-09-12--로그-버스-단일화-v330-raw_log-단일-경로플래그-라우팅레거시-제거) 참조)](#52-모듈-목록-95개-루트-py-—-2026-09-25-find-*py-실측-tool_logpy-포함-[상세-트리]‍#2026-09-12--로그-버스-단일화-v330-raw_log-단일-경로플래그-라우팅레거시-제거-참조)
- [6. 개발 방향성 및 TUI 표준](#6-개발-방향성-및-tui-표준)
  - [6.1 핵심 철학 (Core Philosophy)](#61-핵심-철학-core-philosophy)
  - [6.2 UI 레이아웃 & 폰트 표준](#62-ui-레이아웃-&-폰트-표준)
  - [6.3 팝업/다이얼로그 규격 및 설정창 아키텍처 (v3.5.1+)](#63-팝업/다이얼로그-규격-및-설정창-아키텍처-v351)
  - [6.4 시각적 디테일 및 영문 미니멀화](#64-시각적-디테일-및-영문-미니멀화)
- [7. 로깅 규격 및 작성 가이드](#7-로깅-규격-및-작성-가이드)
  - [7.1 고정 칼럼 로그 규격 (v3.4.0+)](#71-고정-칼럼-로그-규격-v340)
  - [7.2 신규 기능 개발 시 로그 작성 및 추가 규약 (Logging Guidelines)](#72-신규-기능-개발-시-로그-작성-및-추가-규약-logging-guidelines)
- [8. 파이프라인 및 우회 전략](#8-파이프라인-및-우회-전략)
  - [8.1 3계층 우회 파이프라인 (Three-Layer Bypass Pipeline)](#81-3계층-우회-파이프라인-three-layer-bypass-pipeline)
  - [8.2 분석/다운로드 단계별 동작 상세](#82-분석/다운로드-단계별-동작-상세)
  - [8.3 렌더링 엔진 정책 (Rendering Engine Policy)](#83-렌더링-엔진-정책-rendering-engine-policy)
- [9. 주요 컴포넌트 및 시그널 계약](#9-주요-컴포넌트-및-시그널-계약)
  - [9.1 log_console.py (ConciseLogConsole)](#91-log_consolepy-conciselogconsole)
  - [9.2 dialogs.py](#92-dialogspy)
  - [9.3 ui/components/ (v3.12.0 신설)](#93-ui/components/-v3120-신설)
  - [9.4 기동 시퀀스·POT 구동 로직·시그널 계약 트리 (v3.12.0 실측)](#94-기동-시퀀스·pot-구동-로직·시그널-계약-트리-v3120-실측)
  - [9.5 Worker ↔ UI 시그널 계약 (v3.12.0 — 로그 시그널 0, 결과/게이트만 잔존. 2026-09-25 실측)](#95-worker-↔-ui-시그널-계약-v3120-—-로그-시그널-0-결과/게이트만-잔존-2026-09-25-실측)
- [10. 핵심 데이터 구조](#10-핵심-데이터-구조)
  - [10.1 cfg (config.default_config() 23키 — 로드 시 dl_config.json 병합)](#101-cfg-configdefault_config-23키-—-로드-시-dl_configjson-병합)
- [11. 빌드 및 배포(CI/CD) 절차](#11-빌드-및-배포ci/cd-절차)
  - [11.1 체리피킹 원칙](#111-체리피킹-원칙)
  - [11.2 자동 업데이트 정책 (Nightly Channel)](#112-자동-업데이트-정책-nightly-channel)
  - [11.3 선택 과제 (향후)](#113-선택-과제-향후)
  - [11.4 빌드 시 해야 할 일 (OS별 체크리스트) — v3.1.1 신설](#114-빌드-시-해야-할-일-os별-체크리스트-—-v311-신설)
- [12. 주요 이슈 및 유지보수 포인트](#12-주요-이슈-및-유지보수-포인트)
- [13. 불변식 (코드 수정 시 절대 위반 금지)](#13-불변식-코드-수정-시-절대-위반-금지)
- [14. 하지 말 것 (회귀 방지)](#14-하지-말-것-회귀-방지)
- [15. 검증 워크플로우](#15-검증-워크플로우)
  - [15.1 마무리 — 링크 깨짐 확인 완료·체리피킹 요약 (v3.5.0)](#151-마무리-—-링크-깨짐-확인-완료·체리피킹-요약-v350)
- [16. 파일 규칙](#16-파일-규칙)


## 1. 프로젝트 개요

- **ChzzkTube**: YouTube/치지직(Chzzk) 영상 다운로드 Hyper-Minimalist Modern TUI 앱 (macOS / Windows / Linux 호환)
- **버전**: `v3.12.4` — 정의 위치 `config._APP_VERSION`; 메타 참고값은 `pyproject.toml` `version = "3.12.4"` (최신: 2026-09-26 pot_server DEFAULT_HOST re-export 누락 회귀 복구·POT 워커 크래시 F12 추적 보강·에러 버스 배선 안정화)
- **버전 정책 (비공개 개발, semver-lite)**:
  - `x` major: 공개/외부 인터페이스·빌드 산출물 계약·진입점 손상 시
  - `y` minor: 기능 추가·대형 리팩토링·아키텍처 재편 등 사용자/호출부 관점의 기능 지평 변화 시
  - `z` patch: 버그 수정·로그/색상/판정 문구·성능 다듬기 등 기능 지평 변화 없는 안정 작업
  - 비공개 개발이므로 `y` 단위로 릴리즈하고, `z`는 중간 커밋 구분용. 공개/배포 마일스톤에서만 `x`·`1.0.0` 레이블을 의미에 맞게 사용. 버전 변경 사유는 HANDOVER §9 변경 테이블 + CHANGELOG에 동기화.
- **스택**: Python 3.12.14 (pyenv, `.python-version` 고정) + PySide6 + yt-dlp + streamlink + FFmpeg(리먹싱) + Node.js 22+(PO Token 서버)
- **진입점**: `main.py` (`python main.py`)
- **빌드**: PyInstaller — `ChzzkTube.spec`
- **설정 파일**: `dl_config.json` (CONFIG_DIR에 생성, UTF-8 / indent=4)

---

## 2. 버전 관리 절차

### 2.1 버전 진실 공급원과 정책

- 앱이 표시하는 버전의 단일 진실 공급원은 `config._APP_VERSION`임. 현재 값은 `v3.12.0`임.
- `pyproject.toml`의 `version`과 `uv.lock`의 루트 프로젝트 버전은 패키지/빌드 메타 참고값이며 앱 실행 버전을 대체하지 않음. 세 값은 항상 숫자 부분을 동일하게 유지함.
- 비공개 개발은 semver-lite를 따른다.
  - `major`: 공개/외부 인터페이스, 빌드 산출물 계약, 진입점 호환성이 깨질 때
  - `minor`: 기능 추가, 대형 리팩토링, 아키텍처 재편 등 사용자/호출부 관점의 기능 지평이 바뀔 때
  - `patch`: 버그 수정, 로그·색상·판정 문구, 성능 다듬기 등 기능 지평 변화 없는 안정 작업
- 비공개 개발은 patch 단위로 커밋/중간 상태를 구분하고, 외부 공개 또는 배포 마일스톤에서 major/minor 레이블을 의미에 맞게 붙인다.
- 버전 변경 사유는 `HANDOVER.md` §9 변경 테이블과 `CHANGELOG.md` 최신 엔트리에 함께 기록함.

### 2.2 버전 증가 절차

1. 변경 성격에 따라 `major`/`minor`/`patch` 증가를 결정함.
2. `config.py`의 `_APP_VERSION`를 먼저 수정함. 앱 화면, 부트 로그, 히스토리 세션 마커는 이 값을 사용함.
3. `pyproject.toml`의 `version`과 `uv.lock`의 루트 `[[package]] name = "chzzktube"` 버전을 같은 숫자로 맞춘다.
4. `HANDOVER.md` 머리글/개요/최신 변경 이력과 `CHANGELOG.md` 최신 엔트리를 갱신함.
5. `python sync_mirrors.py`로 `mirrors/config.md`와 `mirrors/chzzktube_codebase.md`를 재생성함.
6. 다음 정합성 조건을 확인함.
   - `config._APP_VERSION == "v" + pyproject.toml version`
   - `uv.lock` 루트 프로젝트 버전이 `pyproject.toml`과 동일
   - `HANDOVER.md`, `CHANGELOG.md`, README의 현재 버전 표기가 동일
   - `python sync_mirrors.py --check`가 전체 등록 모듈(`MIRROR_MODULES`, `chzzktube.infra.provisioning.*` 포함) 기준으로 변경 0건/누락 0건을 반환
   - 신규 `.py` 모듈은 반드시 `MIRROR_MODULES`에 등록함. basename이 기존 미러와 충돌하면 `provisioning_<name>.md`처럼 패키지 접두사를 붙인다

### 2.3 `bump_version.py` 제한

- `bump_version.py`는 `config.py`의 `_APP_VERSION`에서 patch 숫자만 `+1`하는 보조 스크립트다.
- `major`/`minor` 증가는 지원하지 않으며, `pyproject.toml`, `uv.lock`, `HANDOVER.md`, `CHANGELOG.md`, `README.md`, Python 미러는 자동 갱신하지 않음.
- 따라서 릴리스/배포 버전 변경 시에는 위 §1.1.2 절차를 수동으로 완수해야 하며, `python bump_version.py` 실행 후 `config.py`만 바뀌었다고 완료 처리하면 안 됨.

## 3. 기술 스택 및 디펜던시

| 항목 | 상태 |
|------|------|
| Python | 3.12.14 (pyenv, `.python-version` 고정) |
| 의존성 단일 출처 | `pyproject.toml` / `uv.lock` — PyQt6 6.11.0 · streamlink 8.5.0 고정. build 그룹엔 pyinstaller (Windows 빌드용) |
| FFmpeg | 런타임 수급 — 시스템 폴백 없이 `writable_base()/ffmpeg` 단일 경로 사용 (macOS Homebrew, Windows/Linux BtbN) |
| Node.js 22+ | PO Token 서버용 (`pot_provider`) — 포터블 다운로드 단독 의존 (시스템 폴백 X) |
| 콘솔 폰트 | `CascadiaMono-VariableFont_wght.ttf` (BASE_DIR, 11px — theme.py 단일 출처). `D2Coding-Regular.ttf`는 레거시 잔재(미로드) |
| 히스토리 로그 | `logs/chzzktube_YYYY-MM-DD.log` (`log_history`, 날짜별 append, 30일 보존, thread-safe) |
| 스모크 | `smoke_test.py` — `QT_QPA_PLATFORM=offscreen` 강제로 CI 가능 |
| yt-dlp | 독립 실행형 바이너리 런타임 수급 — GitHub 릴리스 단일 출처 (Nightly 채널 지원) |

## 4. 폴더 구조 및 경로 계약

### 4.1 기본 디렉터리

| 경로/상수 | 소스(Dev) | PyInstaller(frozen/onedir) | 용도 |
|---|---|---|---|
| `BASE_DIR` | 프로젝트 루트 | `sys._MEIPASS` | 번들 리소스·파이썬 모듈 탐색 |
| `CONFIG_DIR` | 프로젝트 루트 | 실행 파일(`sys.executable`) 디렉터리 | `dl_config.json`과 설정 저장 |
| `CONFIG_FILE` | `<repo>/dl_config.json` | `<exe-dir>/dl_config.json` | UTF-8, indent=4 설정 파일 |
| `LOG_DIR` | `<repo>/logs/` | `<exe-dir>/logs/` | `chzzktube_YYYY-MM-DD.log`, 30일 보존 |
| `ICON_PATH` | `<BASE_DIR>/icon.ico` | `<BASE_DIR>/icon.ico` | 창 아이콘 |
| `writable_base()` | `$HOME/.chzzktube` | Windows는 `%LOCALAPPDATA%/ChzzkTube`, 그 외는 `$HOME/.chzzktube` | 쓰기 보장 사용자 데이터/캐시 루트 |

- `CONFIG_DIR`는 설정 저장 위치이며, `download_path`의 기본값으로도 사용됨. 사용자는 `dl_config.json`에서 별도 다운로드 경로를 지정할 수 있다.
- 의존성 바이너리들은 `writable_base()` 하위 경로로 통일되며, Dev와 Frozen 환경 모두 동일하게 적용됨.

### 4.2 런타임 캐시·외부 구성요소

`writable_base()` 아래의 주요 경로는 다음 계약을 따른다.

| 경로 | 소유/용도 |
|---|---|
| `ffmpeg/bin/` | `components.py`의 ffmpeg 수급·검증 캐시. `ffmpeg`·`ffprobe`를 함께 배치한다 (동일 디렉터리 계약) |
| `ffmpeg/bin_incoming`, `ffmpeg/bin_backup` | 원자 교체용 임시/백업 디렉터리. 교체 성공·실패 후 반드시 제거된다 |
| `node/` | `node_provider.py`의 Node.js 22+ 포터블 런타임과 npm 무결성 관리 |
| `bgutil-ytdlp-pot-provider/` | `pot_server.server_home()`의 PO 서버 소스/빌드. `server/.version`으로 설치 버전 판정 |
| `bgutil_server.log` | PO 서버 기동/빌드 진단 로그 |
| `.prewarm.lock` | PO 서버 프리웜 상호배제 락. 죽은 PID + 30분 초과 시 stale 회수 |
| `yt_dlp_plugins/` | 구 PO 플러그인 잔재 제거 대상. 현행 자체 Node 서버와는 별도 정리 경로 |
| `provision_manifest.json` | 수급 감사 기록. `ProvisioningManager`가 `ProvisionManifest.load/save`로 관리 |

- Node 런타임 다운로드 아카이브는 일시적으로 `writable_base()/node_portable.zip` 또는 `node_portable.tar.gz`에 저장한 뒤 전개함.
- PO 서버 소스 갱신은 `tempfile.mkdtemp(prefix="chzzktube_bgutil_")`의 임시 디렉터리에서 수행하고, 완료 후 `server_home()`으로 원자적으로 반영함.
- ffmpeg 수급은 `*.part`/임시 디렉터리를 사용하고 성공 시 최종 경로로 교체함. 실패한 기존 캐시는 경고 후 재수급함.
- frozen 빌드의 PO 서버 번들 자료는 PyInstaller `_MEIPASS` 아래 `bgutil-ytdlp-pot-provider/`를 우선 참조하되, 쓰기 가능한 사용자 경로가 이미 존재하면 해당 경로를 서버 홈으로 사용함.

### 4.3 경로 관련 불변식

- 설정/로그/외부 구성요소의 기본 경로는 `config.py`의 상수와 `writable_base()`를 단일 출처로 사용함.
- frozen과 Dev의 경로 차이는 `config.resolve_dirs()`와 각 구성요소 헬퍼에서만 해석함. UI/워커가 직접 절대 경로를 조립하지 않음.
- `CHZZKTUBE_COMPONENTS_DIR`는 배포/테스트 경로 오버라이드용이며, 설정 파일의 `download_path`와는 독립적임.
- 캐시/락/임시 파일은 재시작·실패·stale 판정을 고려해 소유 모듈이 정리함. 수동 삭제는 `server_home()`, `components_root()`, `writable_base()` 계약을 먼저 확인함.

## 5. 아키텍처 상세 및 모듈 명세
### 5.1 레이어별 구조 (4계층 + L0 Leaf) — v3.4.0 레이아웃 리팩터링(`chzzktube/` 단일 패키지)

```
LAYER 3: View (Qt Widgets) — chzzktube/ui/
  main_window.py(main.py 씬 런처) · components/header_bar.py · components/action_bar.py · dialogs.py · theme.py · log_console.py · log_mirror.py
LAYER 2: Orchestrators — chzzktube/control/
  startup_coordinator.py · controller.py · startup_state.py · pot_manager.py · gate_state.py
LAYER 1: Worker Threads (QThread) — chzzktube/workers/
  downloader.py · analyze_worker.py · update_worker.py
LAYER 0.5: Pipeline Functions (ctx 기반, 비스레드) — chzzktube/pipeline/
  target_downloader/ · progress_emitter.py · live_recorder.py · finalizer.py · dl_context.py
LAYER 0: Domain / Helpers / Infra (Leaf)
  chzzktube/core/: media.py · chzzk_api.py · cookies.py · config.py · utils.py
    yt_logger_bridge.py · dl_platform.py · speed_window.py · playlist.py
    log_event.py · log_history.py · raw_log.py · tool_log.py · log_emitter.py(Qt-free 순수 조판)
  chzzktube/infra/: po_client.py(stdlib only) · node_provider.py · pot_server.py
    pot_provider.py(순수 재수출 facade) · components.py · updater.py
    provisioning/: planner.py · executor.py · committer.py · bridge.py · manager.py · manifest.py · resolver.py · verifier.py · downloader.py
  루트: main.py(씬 런처) · smoke_test.py · sync_mirrors.py · bump_version.py
```

### 5.2 모듈 목록 (95개 루트 .py — 2026-09-25 `find *.py` 실측. `tool_log.py` 포함. [상세 트리](‍#2026-09-12--로그-버스-단일화-v330-raw_log-단일-경로플래그-라우팅레거시-제거) 참조)

| 분류 | 모듈 | 핵심 책임 |
|------|------|----------|
| View | main | 진입점 + MainWindow (1366) — `_GuiLogBridge` QueuedConnection 구독, append_concise_log=bus shim |
| View | dialogs | 6종 Dialog + ComboBox + UpdateWorker 연동 |
| View | theme | QSS/컬러 토큰 |
| View | log_console | ConciseLogConsole 렌더러 (833) — append(no_wrap)→_flow_lines 플래그 체인 |
| Control | controller | MediaController — spawn_worker/spawn_analyzer + URL 파싱 (217) |
| Control | startup_coordinator | 기동 게이트 (124) — report_* + View행 Signal 3종 + raw("startup") |
| Control | startup_state | READY 단일 진실 (69) — `can_emit_ready()` 멱등 가드 + pot_ready |
| Control | pot_manager | POT 수명주기 (247) — `ensure_ready(prewarm/gate)` + `use_existing` + Signal 2종 |
| Worker | downloader | DownloadWorker — `finished_all`만 잔존, 로그 시그널 0 (164) |
| Worker | analyze_worker | AnalyzeWorker (354) — result_ready/error_occurred + pot-gate 판정, **순정 단일 호출** |
| Worker | update_worker | UpdateWorker (201) — check_done/upgrade_done + deps raw 발행 |
| Infra | pot_provider | PO Token 3개 모듈 재수출 facade (75) — 워커 없음(스폰은 POTManager 단독), POTProviderWorker는 v3.3.1 제거 |
| Pipeline | progress_emitter | LogEvent 빌더 단일 출처 (182) — emit_event/emit_dl/emit_err/… |
| Pipeline | target_downloader | 다운로드 실행부 (318) — `raw("dl"/"ytdlp"/"live")`, **순정 단일 호출 + POT 1회 재시도** |
| Pipeline | live_recorder | ffmpeg 라이브 녹화 (229) — `prepare_live_paths`/`handle_stream_finish` 모듈 함수 계약, **순정 위임** |
| Pipeline | finalizer | `_finalize` 분할 — TUI 컬럼 마무리 |
| Pipeline | dl_context | DownloadContext dataclass (86) — 파이프라인 명시적 계약 |
| Pipeline | speed_window | 속도 측정 슬라이딩 윈도우 |
| Shared | yt_logger_bridge | yt-dlp logger → `raw("ytdlp")` 어댑터 (150) — `\r` 캐리지 조립 + 2Hz 스로틀 |
| Infra | tool_log | subprocess STDOUT/STDERR 비블로킹 펌프 + 종료·타임아웃·잔여 출력 정리 |
| Shared | updater | PyPI 조회+pip 업그레이드 (423, 최상단 stdlib only — node/npm·ffmpeg CLI 원문 캡처용 경로는 pot_provider·components lazy import) |
| Infra | po_client | bgutil HTTP 순수 계층 (91) — 순수 HTTP 핑만, 상위 역참조 0 |
| Infra | node_provider | Node.js 런타임 수급 (314) |
| Infra | pot_server | bgutil 서버 수명주기 (760) — 수급/빌드/기동/락/kill |
| Domain | media | 코덱랭크/포맷설명/remux/cleanup (348) |
| Domain | chzzk_api | 치지직 clip/vod/live 분석 (363) |
| Domain | cookies | 브라우저 쿠키 추출 (85) |
| Domain | config | `default_config()` 23키 + `_APP_VERSION` + 병합 |
| Domain | playlist | YT 채널 URL 정규화 |
| Domain | client_opts | player_client/쿠키/PO Token 옵션 주입 (125) — **`auto` 시 강제 지정 없이 순정 위임** |
| Domain | dl_platform | URL 판정 + `_short_platform`/`_dl_platform` (111) |
| Infra | components | ffmpeg 자동 수급/관리 (522) |
| Infra | log_history | 파일 로그 단일 소유자 (95) — 직접 호출 금지, raw 경유만 |
| Infra | smoke_test | offscreen 기동 검증 하네스 · tests/*.py 12종 · logs/ 일자 산출물 |

> 구 분류표의 `cookie.py`(단수)·`pot_manager alivede progress`·`startup_coordinator 시퀀스 스텝 실행기` 서술은 2026-09-12 실측으로 정정 — 실제 파일은 `cookies.py`, POTManager=수명주기 관리자, Coordinator=게이트+보고 중계. 구 34행 분류표는 아래 v3.3.0 실측 시그널 계약으로 대체.

## 6. 개발 방향성 및 TUI 표준
### 6.1 핵심 철학 (Core Philosophy)
- **Hyper-Minimalist Modern TUI Media Extractor**: OS 순정 GUI 요소를 배제하고, `fzf`·`lazygit` 감성의 모노스페이스 Flat TUI 레이아웃을 유지함.
- **도구의 순수성**: 미디어 추출 본연의 안정성과 속도에 집중함. 우회 로직은 단계적 폴백 원칙을 따른다.
- **Zero Redundancy & Clean Termination**:
  - 단일 라인 내 같은 의미의 단어/상태를 중복 출력하지 않음.
  - 내용 없는 빈 컬럼(`-`)과 행 말단의 방치된 구분자(`│`)를 배제함.
  - 타임스탬프와 컬럼 조판은 말단 렌더러(TUI/F12)에서 1회만 수행함.

### 6.2 UI 레이아웃 & 폰트 표준
- **Cascadia Mono 11px 통일**: 박스 드로잉 기호(`█`, `░`)의 베이스라인과 높낮이 튐을 차단함.
- **Flat TUI 3-Layer 구조**:
  - **Configuration Bar (상단)**: 저장 경로와 단축키 배지 (`[ F1: Change ]`, `[ F2: Open ]`, `[ F3: Settings ]`, `[ F12: Full Log ]`).
  - **Input & Action Bar (중간)**: 프롬프트(`>`) 기반 URL 입력창. `[ ESC: Clear │ ENTER: Start ]` 단축키를 사용함.
  - **Live Console Monitor (하단, `stretch=1`)**: 메인 로그를 표시함. Raw 디버그 로그는 `F12` 독립 서브 윈도우로 격리함.

### 6.3 팝업/다이얼로그 규격 및 설정창 아키텍처 (v3.5.1+)

#### 4.1 다이얼로그 규격 단일 진실 (SSOT)
모든 다이얼로그는 `Cascadia Mono, 11px` 및 다크 팔레트(`#0d0d0d`)를 준수하며 모던 TUI 규칙에 따라 렌더링됨.

| 클래스명 | 크기 (px) | 레이아웃 특징 | 비고 |
|---|---|---|---|
| `ExitConfirmDialog` | `Fixed: 280×125` | 텍스트 중앙 정렬, 위험(빨강)/중립(회색) 2열 버튼 | 앱 종료 경고창 |
| `SettingsDialog` | `Fixed: 660×680` | 스크롤 바디 + 하단 고정 풋터 분리형 TUI | 설정 패널 (F3) |
| `CookieSelectDialog` | `Fixed: 320×220` | 브라우저별 선택 버튼 수직 스택 | 쿠키 소스 지정 |
| `CookieViewerDialog` | `Fixed: 650×480` | 읽기 전용 텍스트 에디트 + 우하단 Close 태그 | 쿠키 덤프 뷰어 |
| `VerboseLogWindow` | `Resize: 760×480`| 미러링 라인 카운터 상태 바 + Close | F12 상세 로그 |
| `ActionCountdownDialog`| `Fixed: 300×125` | 60초 카운트다운 타이머 + 즉시실행/취소 | 사후 동작 확인 |
| `TuiNoticeDialog` | `Fixed: 280×125` | 텍스트 중앙 정렬, OK/보조(View) 2버튼(alt) | `show_info_message` 기본 안내창·쿠키 설정 완료 확인 |

#### 4.2 SettingsDialog 모던 TUI 조립 규칙
- **프레임리스 섹션**: 무거운 `QGroupBox` 대신 `_sec_header("// TITLE")` 라벨과 `_tui_sep()`(1px HLine, `#1a1a1a`) 조합 사용.
- **고정 풋터(Footer) 분리**: `QScrollArea` 바닥에 닫기 버튼을 두지 않고, 메인 `outer` 레이아웃 하단에 독립 위젯(`footer`)으로 고정 배치하여 일정한 하단 여백 유지.
- **방어적 위임 패턴**: `self.parent_win`의 유무와 관계없이 `save_cfg()` 호출 시 부모 윈도우 또는 `config.save_config()`로 자동 폴백되도록 캡슐화되어 단독 단위 테스트 가능.

### 6.4 시각적 디테일 및 영문 미니멀화
- **파스텔 팔레트는 현행 유지**: `SUCCESS #6a9955`, `ERROR #e06c75`, `WARN #e5c07b`.
- `MSG`는 영문 소문자 CLI 태그를 원칙으로 함.
- **팝업·다이얼로그 문구도 영문 소문자**로 통일한다(설정값 키·사용자 데이터 제외). §4.1 `TuiNoticeDialog`가 SSOT이며 `show_info_message`는 이를 위임한다(한국어 사용자 문자열 배제).
- 채널명/영상 제목 같은 사용자 데이터는 번역하지 않음.
- TUI와 F12 모두 발행된 원문을 동일하게 보존함.

## 7. 로깅 규격 및 작성 가이드
### 7.1 고정 칼럼 로그 규격 (v3.4.0+)

#### 3.1 기본 포맷
```text
[HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG
```

- `TIMESTAMP`: `[HH:MM:SS]` 10자 고정, 단일 스탬프
- `STAGE`: 5자 고정 좌측 정렬
- `STATUS`: 5자 고정 좌측 정렬
- `SCOPE`: 5자 고정 좌측 정렬
- `MSG`: 가변 텍스트, 초과 시 픽셀 단위 절단
- `SPEC` 컬럼 폐지: 미디어/버전 메타데이터는 MSG 전두부 태그(`[1080p30]`, `[v2026.8.19]`)로 흡수
- 빈 MSG에는 꼬리 구분자(`│`)를 출력하지 않는다

#### 3.2 STAGE 값 (5자 규격)
- `SYS`: 시스템 생명주기
- `DEPS`: 의존성 검증 및 무결성 체크
- `ANAL`: 메타데이터/스트림 분석
- `DL`: 다운로드 파이프라인
- `LIVE`: 실시간 녹화
- `MERG`: 스트림 믹싱/컨테이너 변환
- `BATCH`: 배치 처리
- `POT`: PO Token 서버

`MEDIA`, `CHZ`, `CK`, `API`는 독립 STAGE로 추가하지 않음.
- `media.remux` 실패 → `MERG`
- `chzzk_api` 경고 → `ANAL`
- 쿠키 오류 → `SYS`
- API는 작업 단계가 아니라 발생 수단이므로 STAGE가 아닌 SCOPE/MSG로 표현

#### 3.3 STATUS 값 (5자 규격)
- `READY`: 준비 완료/입력 대기
- `RUN`: 진행 중(대기/큐잉 포함)
- `OK`: 단위 작업 성공
- `DONE`: 전체 시퀀스 정상 종료
- `SKIP`: 건너뛰기
- `WARN`: 비치명적 경고
- `FAIL`: 작업 실패
- `ABORT`: 사용자 취소
- `END`: 스트림 세션 종료

`WAIT`는 독립 STATUS로 추가하지 않고 `RUN`으로 통합함.

#### 3.4 SCOPE 값 (발생지/대상, 5자 규격)
- 외부 엔진: `YTDL`, `STRE`, `FFMP`, `NODE`, `POT`
- 미디어 플랫폼: `YT`, `CHZ`, `TW`, `TIKT`, `IG`, `X`, `BILI`, `AFTV`
- 시스템 도메인: `MAIN`, `RAW`, `QUEUE`, `DISK`
- 미지원 값은 확장 예약이며 신규 발행점을 만들지 않음.
- 스트림 코덱/미디어 속성은 SCOPE가 아닌 MSG 내부 태그로 위임함.

#### 3.5 진행률 바 지터링 방지 규격
```text
[tag] <PCT>% · <SPEED> <GAUGE> · <MSG>
```

- `PCT`: 3자리 우측 정렬(` 65%`, `100%`)
- `SPEED`: 8자리 우측 정렬(` 12.4M/s`, ` 980.2K/s`)
- `GAUGE`: 고정 10블록(`[██████░░░░]`)
- 순서: `PCT → SPEED → GAUGE → MSG`

#### 3.6 예시 로그
```text
[03:17:20] DEPS │ OK   │ YTDL │ [v2026.8.19] verified
[03:17:20] DEPS │ OK   │ STRE │ [v8.5.0] verified
[03:17:20] DEPS │ OK   │ FFMP │ [v9.0.1] verified
[03:17:20] DEPS │ OK   │ NODE │ [v22.23.2] verified
[03:17:20] DEPS │ OK   │ POT  │ [running] port 4416
[03:17:21] SYS  │ READY│ MAIN │ ready - input unlocked
[03:17:22] ANAL │ RUN  │ YT   │ analying... -> analyzing complete!
[03:17:22] ANAL │ OK   │ YT   │ [제목] · [채널명]
[03:17:22] ANAL │ OK   │ POT  │ [public] (또는 [gated: age\_limit=19], [members-only])
[03:17:22] ANAL │ OK   │ YTDL │ [1080p60] [av01.0.08M.08] [3280k https] [29.88MiB]
[03:17:22] ANAL │ OK   │ YTDL │ [opus] [160k https] [7.64MiB]
[03:17:23] DL   │ RUN  │ YT   │   65% ·  12.4M/s [██████░░░░]
[03:17:23] DL   │ RUN  │ YT   │  100% ·   4.1M/s [██████████]
[03:17:24] MERG │ RUN  │ FFMP │ muxing audio and video streams...
[03:17:25] DL   │ OK   │ YT   │ saved · video.mp4 (11.56MB)
```

### 7.2 신규 기능 개발 시 로그 작성 및 추가 규약 (Logging Guidelines)

신규 기능을 추가할 때 발생하는 모든 동작 로그는 반드시 아래 8가지 철칙을 준수해야 함.

#### 1. 로그 발행 단일 진입점 (Single Entry Point)
* **`raw_log.raw()` 경유 필수**: 워커/서비스/UI 어디서든 모든 로그는 반드시 `chzzktube.core.raw_log.raw()` 단일 버스를 통해서만 발행함.
* **금지 사항**:
  - `log_history.log()` 직접 호출 금지 (버스가 파일 기록을 자동 수행함)
  - UI 위젯(`QTextEdit`)에 직접 `append()` 또는 스레드 간 UI 파이프라인 신설 금지
  - 워커 스레드에 새로운 로그 전용 Qt Signal(`log_full`, `log_concise` 등) 추가 금지

#### 2. 4컬럼 규격 및 상수 엄격 준수 (`LogEvent` SSOT)
* **포맷**: `[HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG`
* **STAGE (5자 고정)**: `SYS`, `DEPS`, `ANAL`, `DL`, `LIVE`, `MERG`, `BATCH`, `POT` 8종만 허용.
* **STATUS (5자 고정)**: `READY`, `RUN`, `OK`, `DONE`, `SKIP`, `WARN`, `FAIL`, `ABORT`, `END` 9종만 허용. (비표준 값 `MISSING`, `?` 등 금지)
* **SCOPE (5자 고정)**:
  - 외부 엔진: `YTDL`, `STRE`, `FFMP`, `NODE`, `POT`
  - 미디어 플랫폼: `YT`, `CHZ`, `TW`, `TIKT`, `IG`, `X`, `BILI`, `AFTV`
  - 시스템 도메인: `MAIN`, `RAW`, `QUEUE`, `DISK`
* **SPEC 컬럼 폐지**: 미디어 코덱/해상도/버전 등 사양 정보는 `SPEC` 컬럼으로 전달하지 않고 `MSG` 전두부 태그(`[1080p60]`, `[v3.9.0]`)로 위임함.

#### 3. TUI vs F12 채널 격리 및 전량 보존 계약 (Storage vs View)
* **메인 TUI (`to_tui=True`)**:
  - 사용자 중심의 핵심 상태 변화, 마일스톤 완료(`OK`/`DONE`), 제자리 갱신형 게이지 바(`RUN`), 치명적 오류(`FAIL`)만 통과.
  - TUI 콘솔 폭 보호를 위해 영문 소문자 중심 최대 **55자 내외**로 제한.
* **F12 상세 로그 및 디스크 파일 (전량 보존, SSOT)**:
  - 저수준 CLI 실행문(`$ python -m yt_dlp --version`), HTTP 요청/응답 헤더, 아카이브 전개 및 검증 상세, 예외 트레이스백은 `to_tui=False`로 발행되어 메인 콘솔을 더럽히지 않고 F12와 파일 로그에 100% 영구 보존됨.
* **[핵심 불변식] 저장 전량성(Storage)과 뷰 갱신(View)의 분리**:
  - **영구 기록 (File/Storage)**: 모든 CLI 명령어와 결과, 네트워크 트랜잭션은 단 한 줄의 누락 없이 파일(`logs/chzzktube_*.log`)에 순차 append됨.
  - **화면 표시 (GUI View)**: F12 창(`VerboseLogWindow`)과 내부 버퍼(`_full_log_buf`)는 '전량 기록'을 이유로 진행률 틱을 수천 줄의 새 줄로 개행하지 않음. `component_id`가 부여된 진행 틱은 뷰 계층에서 반드시 **동일 라인 제자리 갱신(In-place Overwrite)**으로 처리하여 GUI 프리징과 스크롤 폭발을 원천 차단함.

#### 4. 1타임스탬프 1정보 (Single Information per Line)
* 한 줄의 로그에 여러 상태나 콤마로 연결된 긴 배열을 한꺼번에 찍지 않음. (예: `stale updates: a, b, c` ❌ ➔ 라벨별 개별 줄 발행 ⭕)
* 진행률 바 나열 시 직렬 연결 금지 — 갱신형 진행률 기능을 활용함.

#### 5. 제자리 갱신형 및 다중 컴포넌트 로그 (`is_status`, `component_id`, `is_progress`)
* **단일 틱 제자리 갱신 (Single-Line In-Place Status)**:
  - 진행 퍼센트, 속도 측정 등 지속적으로 발생하는 틱은 `is_status=True`로 발행되어 뷰 렌더러의 최하단 줄을 덮어쓴다.
* **다중 컴포넌트 갱신형 (`component_id` & `is_progress`)**:
  - 여러 컴포넌트가 병렬로 진행될 때는 `component_id="deps_ffmpeg"`, `is_progress=True`로 발행하여 TUI/F12 양쪽 모두에서 해당 컴포넌트 블록만 제자리 갱신되도록 함.
* **마감 확정 (Commit)**:
  - 작업 완료 시 반드시 `is_progress=False`, `is_status=False`, `status="OK"`로 마감하여 해당 진행 라인을 덮어쓰기 불가능한 영구 히스토리 라인으로 승격 확정함.

#### 6. 에러 로그 표준 규격 (`emit_error_standard` / `emit_error_warn`)
* 에러 로그 발행 시 임의 문자열 대신 `chzzktube.core.log_emitter`의 표준 헬퍼를 사용함.
* **포맷**: `[HH:MM:SS] STAGE │ STATUS │ SCOPE │ &lt;간결 원인&gt; → &lt;진행/액션&gt;`
  - 예시: `[03:07:29] DEPS │ WARN │ FFMP │ binary incompatible → retry mirror (1/3)`
  - 예시: `[03:07:49] SYS  │ FAIL │ MAIN │ all mirrors exhausted → check network (F12)`
* **원문 격리**: C/Python 저수준 예외(dyld, URLError, Stack Trace)는 TUI에 직접 출현시키지 않고 F12 상세 로그 및 히스토리 버퍼로 전량 격리함.

#### 7. 워커 스레드 타입 가드 (`safe_log_msg`)
* `UpdateWorker`나 파이프라인에서 수신한 `LogEvent` 객체의 메시지를 다시 로깅하거나 파싱할 때 `log.lower()`를 직접 호출하면 `'LogEvent' object has no attribute 'lower'` 크래시가 유발됨.
* 반드시 `chzzktube.core.log_event.safe_log_msg(obj)` 헬퍼를 경유하여 안전하게 `str`로 변환 후 다룬다.

#### 8. 실패 및 마감 로그 단일 발행 원칙
* 배치 작업 실행 중 개별 실패 내역은 워커 내부 루프에서 즉시 `to_tui=True`로 다중 발행하지 않음.
* `failed_targets` 목록에 수집해 두었다가 **`finalizer.finalize()` 단 한 곳에서 마감 요약과 함께 단일 발행**하여 콘솔에 중복 FAIL 라인이 연속으로 찍히는 촌극을 방지함.

## 8. 파이프라인 및 우회 전략
### 8.1 3계층 우회 파이프라인 (Three-Layer Bypass Pipeline)
YouTube 차단 회피는 yt-dlp 순정 로직을 최우선 존중하고, 앱 레벨 수동 로테이션을 완전히 제거함. 3계층으로 구성되며 상위 계층은 하위가 **실제로 차단되었을 때만** 가동됨.

- **Layer 1: 순정 네이티브 모드 (기본, 항상 가동)**
  - `player_client="auto"` 단일 호출 → yt-dlp 순정 클라이언트 체인 완전 위임
  - 내부 로테이션: `web_embedded` → `tv_downgraded` → `web_safari` → `mweb` → `tv` → `ios`...
  - EJS JS 솔버(deno/node) 자동 실행 + 쿠키 있으면 인증 클라 우선
  - **공개 영상 & 멤버십(쿠키有)**: 여기서 1080p+Opus 즉시 해결 ✅ (POT 서버 미기동)

- **Layer 2: POT 서버 기동 (조건부 가동)**
  - 가동 조건: `age_limit > 0` (연령제한) **또는** 분석/다운로드 중 실제 봇 체크/포맷 상실 마커 감지 시
  - **`subscriber_only`(멤버십) 제외** — Layer 1에서 쿠키+EJS로 해결되므로 POT 게이트에서 제거
  - bgutil 서버(`pot_provider`)에서 PO token + visitorData 획득

- **Layer 3: PO Token 주입 재시도 (최종 보루, 1회만)**
  - Layer 1 실패 + Layer 2 토큰 확보 시 → 동일 순정 호출(`player_client="auto"`)에 PO token 주입하여 1회 재시도
  - 연령제한/봇체크 뚫고 1080p+ 분리 포맷(`bv*+ba`) 확보 ✅

> **핵심 원칙**:
> - **yt-dlp 순정 로직 최우선 존중** — 앱 수동 클라 로테이션(`_RETRY_CLIENTS`, `client_chain`) 완전 제거
> - **EJS 솔버 + 내장 클라 체인**이 1차 방어선, POT 서버는 2차 방어선(연령제한/봇체크 전용)
> - **멤버십은 Layer 1에서 해결** — `subscriber_only` POT 게이트에서 제거
> - **tv 클라이언트(720p) 시도 없음** — 순정이 `tv_downgraded`까지만 사용, 1080p+ 보장

### 8.2 분석/다운로드 단계별 동작 상세

| 단계 | Layer 1 (순정) | Layer 2 (POT) | Layer 3 (재시도) |
|------|----------------|---------------|------------------|
| **분석** (`AnalyzeWorker`) | `auto` 단일 호출 → 순정 로테이션 + EJS | `age_limit>0` 시 POT 기동 | 토큰 주입 후 재분석 (1회) |
| **다운로드** (`_download_vod`) | `auto` 단일 호출 → 순정 로테이션 | 봇체크/포맷상실 시 POT 기동 | 토큰 주입 후 재다운로드 (1회) |
| **라이브 프리체크** | `auto` 단일 호출 | — | — |

> **수동 클라이언트 지정 시**: `cfg["yt_player_client"] != "auto"`면 해당 클라 1회만 시도 (폴백 없음) — 기존 동작 유지

### 8.3 렌더링 엔진 정책 (Rendering Engine Policy)
**PySide6 (Qt 엔진) 유지.** 렌더링 주권(폰트 강제, 픽셀 단위 정렬)과 크로스플랫폼 마우스/클립보드를 동시에 확보하기 위해 TTY 계열(curses/Textual)은 배제함.

- **Qt 엔진 유지 이유**: 폰트 종류/크기/행간 강제 제어, 박스 드로잉 픽셀 정렬, OS 레벨 마우스/클립보드/포커스 지원을 모두 충족하는 유일한 선택.
- **라이선스**: PySide6 (LGPL) — 상용/비상업 가리지 않고 자유롭게 사용 가능. PyQt6 대비 법적 리스크 없음.
- **핵심 로직 분리**: `media`(포맷/코덱/비트레이트), `log_console`(컬럼 포맷·트리 조판), `downloader`/`target_downloader`(추출 파이프라인), `client_opts`(옵션 빌드)는 **프레임워크 비의존**으로 분리. 향후 렌더러 교체 시 이 모듈들은 수정 불포함.
- **In-Place Overwrite (제자리 갱신)**: `DL │ RUN` 및 `LIVE │ RUN` 틱 로그는 매 틱마다 새 줄을 만들지 않고 커서 조작을 통해 마지막 줄을 제자리 갱신.
- **상태 및 스테이지 코드**:
  - `LIVE` 스테이지 코드 신설 (VOD 다운로드 `DL`과 라이브 녹화 구분).
  - 사용자 취소는 `DL │ ABORT`로 독립 표기 (`FAIL` 오류와 명확히 분리).

---

## 9. 주요 컴포넌트 및 시그널 계약
### 9.1 log_console.py (ConciseLogConsole)
- **책임**: TUI 규격에 맞춘 메인 콘솔의 **순수 렌더링 엔진**.
- **로직 특성 (v3.12.0+)**:
  - **Single-Line In-Place Status**: `findBlockByNumber()`와 `QTextCursor` 기반으로 $O(1)$ 타깃형 제자리 블록 치환 수행 (기존 `reflow()` O(N) 전면 폐기). 20Hz(50ms) 페인팅 쓰로틀링으로 GUI 프레임 드랍 차단.
  - **NoWrap과 Pixel-perfect Clamp**: `QTextEdit`의 자체 자동 줄바꿈을 끄고(`NoWrap`), `fontMetrics().horizontalAdvance()`를 사용해 실제 픽셀 폭 단위로 예산 측정 후 초과 시 `…`으로 정밀 절단함.

### 9.2 dialogs.py
- **책임**: 앱 내에서 발생하는 모든 독립된 팝업 대화상자(Dialog)들의 컬렉션.
- **로직 특성 (v3.12.0+)**:
  - 7개 모달 창의 `setFixedSize` 철폐 후 `setMinimumSize()` 기반 반응형 스케일링 허용.
  - `SettingsDialog`는 5대 기능 영역 모듈 빌더로 분할하여 단일 함수 비대화 방지.
  - **SSOT 규격**: 안내창은 `TuiNoticeDialog` 규격 준수.

### 9.3 ui/components/ (v3.12.0 신설)
- **책임**: `MainWindow`의 복잡도를 낮추기 위해 역할별로 분리된 컴포넌트 뷰.
- **HeaderBarWidget**: 경로 제어, 설정, 로그 토글 등 1계층 UI 담당.
- **ActionBarWidget**: URL 입력창, 실시간 정규식 사전 검증(Soft Warning), 디바운스, 다운로드/분석 액션 트리거 담당.

### 9.4 기동 시퀀스·POT 구동 로직·시그널 계약 트리 (v3.12.0 실측)

```
[기동 시퀀스 — DEPS → upgrade → prewarm → READY]
main.py (MainWindow)
 └─ _start_update_check → UpdateWorker(check)
      └─ check_done(list) ──→ Main._on_update_check_done 중계 (Coordinator 직결 금지)
           ├─ DEPS 결론 1줄 raw("deps", emit_component) + Coord.report_deps(ok)
           ├─ UpdateWorker(upgrade) 기동 ─→ upgrade_done(bool,str) → Coord.report_upgrade(ok)
           └─ POTManager.ensure_ready("prewarm")   # 기동 즉시 — 디스크 스테이징, 스폰 없음

[POT 서버 수명주기 — POTManager 단일 진실 (_POTWorker 유일 스폰)]
POTManager.ensure_ready(mode)                 # 스폰 가드: 실행 중 워커 있으면 중복 스폰 없음
 ├─ "prewarm" (기동 직후): 빌드 스테이징만 — Popen 없음, RAM 0MB·포트 미점유
 │    └─ ok → _mode="staged" → pot_finished(True, "staged") ─→ report_pot → pot_ready=True
 ├─ "gate" (분석/다운로드 게이트): 연령제한·프라이빗만 서버 기동
 │    ├─ prewarm 실행 중 요청 → _pending_gate=True → 완료 후 QTimer singleShot gate 자동 재기동
 │    ├─ probe_server()=="ok" → 기존 서버 바인드 → pot_finished(True, "ready")
 │    └─ 실패 → _mode="failed" → pot_finished(False, "failed")
 └─ use_existing()  # server_ping()==True(기존 서버 응답) → 스폰 없이 즉시 ready 승격
                    # (이 경로는 pot_finished가 없으므로 대기 다운로드 영구 큐잉 방지용)

[READY 게이트 — StartupState 멱등 1회]
can_emit_ready() = deps_ok ∧ upgrade_done ∧ pot_ready ∧ ¬ready_emitted
 ├─ 충족 시: raw("startup", READY, to_tui=True) 1건 + ui_unlocked() → 입력 잠금 해제
 └─ 15초 폴백: Main._force_unlock_input → force_unlock() → report_ready()

[다운로드 게이트 — PO 필요 영상 (연령제한·프라이빗)]
toggle_download: needs_pot = age_limit>0 ∨ availability∈{needs_auth,premium_only,subscriber_only,private}
 ├─ POTManager.is_busy() → _pending_download 큐잉 + "queued — waiting for POT server"
 ├─ server_ping()==True  → use_existing() → 즉시 진행
 ├─ is_ready()==False    → _pending_download 큐잉 → pot_finished(ok, "ready") 시 Main._on_pot_finished가
 │                         is_ready() 재확인 후 회수 → _start_download 재개
 └─ PO 토큰: client_opts._apply_pot_opts → po_client.fetch_po_token (게이트 완료 보장 후 워커에서 실행)

[시그널 계약 — 결과/게이트만, 워커 로그 시그널 0]
POTManager (_POTWorker 유일 스폰):
  pot_status_changed(str) : starting/staging/staged/failed → Coordinator passthrough → View
  pot_finished(bool,str)  : (ok, 상태 토큰 "staged"/"ready"/"failed") — 사람용 msg 발행 금지(v3.3.1)
    → Coordinator.report_pot → READY 게이트 입력
    → Main._on_pot_finished → is_ready() 확인 → _pending_download 회수 → _start_download
StartupCoordinator (View행 3종):
  ready_emitted(str,bool,str) · pot_status_changed(str) passthrough · ui_unlocked()
  보고 진입점(함수 호출): report_deps / report_upgrade / report_pot / report_ready / force_unlock
UpdateWorker : check_done(list)(Main 중계) · upgrade_done(bool,str)
AnalyzeWorker: result_ready(dict) · error_occurred(str)
DownloadWorker: finished_all(int,int) — 유일 잔존 Signal

[로그 채널 — raw 버스 단일 진입 + 스레드 경계]
워커/파이프라인/UI → raw_log.raw(tag, LogEvent, to_tui)
  ├─ bounded queue(MAX_QUEUE=2048): 발행 스레드는 put만 — 포화 시 UI mirror 드롭 + history 요약 1건
  └─ dispatcher 데몬 스레드: history 파일 I/O + full_events ring(4096) 적재
스레드 경계 (v3.3.1): dispatcher ──Signal.emit──→ main._GuiLogBridge(QObject)
  ├─ tui_signal(object,bool,bool) ─QueuedConnection─→ Main._render_concise   (GUI 스레드)
  └─ full_signal(object,bool)     ─QueuedConnection─→ Main._mirror_event_full (GUI 스레드)
raw_log는 표준 라이브러리만 — Qt 링크 없음. 스레드 경계 책임은 GUI를 점유한 수신층(main.py).
```

### 9.5 Worker ↔ UI 시그널 계약 (v3.12.0 — 로그 시그널 0, 결과/게이트만 잔존. 2026-09-25 실측)

```
AnalyzeWorker(target_url, cfg):                        # 결과 전달 전용 — 로그 시그널 없음
    result_ready(dict) : 성공 — {info, v_list, a_list, is_chzzk:False, yt_client}
                         또는 {info, v_list, a_list, is_chzzk:True}
                         또는 {is_playlist:True, title, count, v_list:[], a_list:[]}
    error_occurred(str): 실패 — 미니멀 영문 오류 코드
   로그: logger=YtLoggerBridge → raw("ytdlp") 버스 직행 + raw("analyze"/"pot-gate", LogEvent)

DownloadWorker(targets, cfg, state_dict, v_sel, a_sel, is_live_hint=False,
               v_spec=None, audio_desc="", yt_client="auto"):  # 로그 시그널 없음
    finished_all(int, int)       : (성공 수, 실패 수) — 유일 잔존 Signal
   로그: logger=YtLoggerBridge → raw("ytdlp") + raw("dl", emit_dl/emit_err, to_tui=True)

UpdateWorker(parent, upgrade, stale_updates, channel, check_updates):  # 로그 시그널 없음
    check_done(list)             : [stale …] — Main._on_update_check_done이 중계 (Coordinator 직결 금지)
    upgrade_done(bool, str)      : (ok, summary) — Coord.report_upgrade 직결
   로그(check): raw("deps", emit_component DEPS, to_tui=True) 결론 1줄 + raw("deps-cli"/"pip"/"pypi", str) F12+history 전용
   로그(upgrade): _provision_cb(show 플래그) → raw("deps", event, to_tui=show)

POTManager:                                                # 수명주기 단일 스폰 가드 (_POTWorker 유일 스폰)
    pot_status_changed(str)      : starting/staging/staged/failed → Coordinator._on_pot_status (passthrough)
    pot_finished(bool, str)      : (ok, 상태 토큰 "staged"/"ready"/"failed") → Coordinator._on_pot_finished
                                   → report_pot(READY 게이트) + Main._on_pot_finished(_pending_download 회수)
    ensure_ready(mode): prewarm 실행 중 gate 요청 → _pending_gate=True → 완료 후 QTimer singleShot gate 자동 재기동
    use_existing()   : server_ping()==True(기존 서버) → 스폰 없이 즉시 ready 승격 (영구 큐잉 방지)
   로그: _POTWorker._note/_dbg → raw("pot"/"pot-DEBUG", …) — prewarm은 to_tui=False (TUI 오염 방지)
   ※ v3.3.1: pot_finished msg는 상태 토큰만 — 사람용 상세("prewarm staged" 등)는 버스 로그로 남긴다.

StartupCoordinator:                                        # 기동 게이트 — View행 Signal 3종
    ready_emitted(str, bool, str): (stage, is_status, msg) — READY 1회 (StartupState 멱등 가드)
    pot_status_changed(str)      : View passthrough
    ui_unlocked()                : 입력 잠금 해제
    _emit(stage,status,msg): raw("startup", LogEvent SYS, to_tui=True) — 기동 라인 버스 발행
    보고 진입점(함수 호출, Signal 아님): report_deps / report_upgrade / report_pot / report_ready / force_unlock(15s 폴백)

raw 버스(raw_log.py — 순수 파이썬 bounded-queue dispatcher, Qt 링크 없음):
    발행 스레드: raw() → queue.put (포화 시 UI mirror 드롭 + history 요약 1건)
    dispatcher 데몬 스레드: history 파일 I/O + full_events ring(4096) 적재 → 구독자 호출
    스레드 경계: dispatcher → main._GuiLogBridge Signal.emit ─QueuedConnection─→ GUI 스레드
        tui_signal(object,bool,bool) → Main._render_concise → console.append(no_wrap=True)
        full_signal(object,bool)     → Main._mirror_event_full → _mirror_full_log(F12 버퍼+stamp)
```

> 구 계약표의 `POTProviderWorker(mode)` 행은 v3.3.1에서 삭제 — POTManager._POTWorker와 중복된 좀비 인터페이스였다(런타임 사용 0건 실측). pot_provider.py는 3개 모듈 재수출 facade만 남음. `pot_finished` msg는 상태 토큰("staged"/"ready"/"failed")만 사용 — 사람용 상세는 버스 로그로.

## 10. 핵심 데이터 구조
```python
{"running": bool, "canceled": bool, "skip": bool, "analyzing": bool}
```

### 10.1 cfg (config.default_config() 23키 — 로드 시 dl_config.json 병합)
```python
download_path, container("mp4"), embed_subtitles, audio_only,
fast_download(True), remove_duplicates(True), auto_open_folder(True),
completion_action("none"), play_sound(True), max_video_res("none"),
filename_prefix("none"), filename_suffix("id"),
browser_cookie("auto"), cookie_file_path(""), yt_player_client("auto")
```
> 런타임 cfg = `default_config()` + `dl_config.json` 통째 병합(`load_config`의 `cfg.update`).

## 11. 빌드 및 배포(CI/CD) 절차

### 11.1 체리피킹 원칙
PySide6 전체 패키지는 수십 MB이므로, **빌드 시 실제 사용하는 Qt 모듈만 포함하고 나머지는 반드시 제거**함. 개발 중 전체 설치는 어쩔 수 없으나, 배포 바이너리는 `--exclude-module`로 최소화함.

- **제거 대상 모듈** (런타임 사용 0, PyInstaller 빌드 시 `--exclude-module` 적용):
  - `PySide6.QtWebEngine`, `PySide6.QtMultimedia`, `PySide6.Qt3D*`, `PySide6.QtCharts`, `PySide6.QtDataVisualization`, `PySide6.QtNetworkAuth`, `PySide6.QtBluetooth`, `PySide6.QtNfc`, `PySide6.QtRemoteObjects`
  - 사용 모듈은 코드 변경 시 `grep -rn 'PySide6.Qt' --include='*.py'`로 확인 후 목록 갱신.
- **효과**: 전체 포함 시 ~80-100MB → 체리피킹 시 ~50-60MB (30-40% 감소).
- **원칙**: "안 쓰는 모듈은 빌드에 넣지 않는다" — 구체 목록보다 **원칙을 우선**하며, 새 Qt 모듈 추가 시 이 섹션의 사용 모듈 목록도 함께 갱신할 것.

### 11.2 자동 업데이트 정책 (Nightly Channel)
모든 빌드 환경에서 동일하게 yt-dlp 자동 업데이트를 지원함. 네트워크 의존은 이 앱에서 본질적이다 (웹 미디어 추출기).

- **Stable 채널** (기본): GitHub 릴리스 기준 안정 버전 수급
- **Nightly 채널** (선택): GitHub nightly-builds 기준 최신 우회 로직 수급
- **업데이트 방식 (Dev/Frozen 통합)**: 모든 환경에서 `writable_base()`를 사용하는 단일 다운로드 경로 사용. (`pip install` 및 Python 패키지 의존 완전 폐기)
  - 독립 실행형 바이너리(yt-dlp) 단일 경로 사용. GitHub Releases 직접 다운로드 (Stable/Nightly 모두 동일 방식)
  - 이유: Dev와 포터블이 동일한 코드 경로를 타야 디버깅 가능. 환경이 분기되면 사용자 기기에서만 발생하는 버그를 재현하지 못함.
  - **포터블 원칙 정합성**: 바이너리(yt-dlp, node, ffmpeg, PO 서버) 모두 `writable_base()`에 설치되어 실행 폴더 밖을 오염시키지 않음.
- **버전 확인**: `updater.check_deps` 단일화. F12는 raw 원문 전용, 메인은 TUI 컬럼 가공으로 이중 출력 방지. Nightly 채널은 설정 UI에서 실제 반영되며 다운그레이드 감지 포함.
- **업데이트 실패 시**: 기존 버전 유지, 다음 실행 시 재시도.
- **bgutil (PO 토큰 서버)**: GitHub 태그 릴리즈에서 자동 수급, pot_provider가 별도 관리.

### 11.3 선택 과제 (향후)
- ✅ **PO 서버 실패 시 재시도** (v3.6.0 #6 완료): 봇 체크 마커 감지 시 `ensure_ready("gate")` 후 URL당 1회 재분석 큐잉 — `_pot_retry_done`으로 루프 차단
- ✅ **POT 서브프로세스 트리 종료** (v3.6.0 #2 완료): `kill_tree()` — Windows Job Object(`TerminateJobObject`) / POSIX 프로세스 그룹(`start_new_session`)
- ✅ **POT gate hang 2차 워치독** (v3.6.0 #3 완료): `_gate_watchdog`(120s) — 만료 시 `cancel()`(트리 킬) + 대기 큐 해제
- ✅ **위양성 폴백 분리** (v3.6.0 #4 완료): 체인 동작 중이면 3초 유예 1회 후 재판정 + `_log_gate_pending` 원인 기록
- ✅ **deps FAIL의 게이트 승격** (v3.6.0 #5 완료): `UpdateWorker.deps_failed = Signal(list)` 신설 — `check_done` untouched, Main 중계 후 `report_deps(False)` 승격
- ✅ **POT 빌드 내부 하트비트** (v3.6.0 #1 완료): `_communicate_with_ticks` + `pot_work_tick` 릴레이 — npm ci 장기 실행을 수급 진행으로 인식
- ✅ **설정 UI**: 업데이트 채널 (Stable/Night) 선택 다이얼로그 — 완료
- ✅ **streamlink 직접 다운로드**: 포터블 빌드에서 streamlink whl 직접 수급 — 완료

### 11.4 빌드 시 해야 할 일 (OS별 체크리스트) — v3.1.1 신설

포터블 빌드는 OS별로 각각 수행한다 (spec 의 _bundle_node_exe 가 빌드 OS 의 node 를
번들하므로 교차 빌드 불가 — macOS 빌드는 macOS 에서, Windows 빌드는 Windows 에서).

| 확인 항목 | 내용 | 미충족 시 동작 |
|---|---|---|
| node 번들 | `shutil.which("node")` 가 잡히는지 — _internal/node.exe 로 심김 | 포터블 캐시(node/) 최초 수급 |
| ffmpeg | 시스템 PATH 또는 writable_base/ffmpeg 캐시 | 최초 실행 시 플랫폼별 수급(win=zip, mac=bottle, linux=static) |
| yt-dlp / streamlink | **독립 exe 아님** — PYZ 내부 모듈 임베드. CLI 실행 불가 | 검사=importlib.metadata 폴백, 업데이트=whl 직접 교체(_frozen_upgrade_*) |
| bgutil 서버 | `~/bgutil-ytdlp-pot-provider/server/build/main.js` 존재 시 스테이징 | 최초 실행 시 GitHub 릴리스에서 수급 |
| icon | spec 은 icon.ico 고정 — macOS/Linux 빌드 시 아이콘 별도 검토 | 기본 아이콘 |

실행체 해석은 updater._cli_base / components.ffmpeg_exe / pot_provider.node_exe 로
단일화되어 있으며, dev(.venv/bin/yt-dlp 등) 와 frozen(importlib 폴백) 의 차이는
이 계층에만 존재한다 — 검사·갱신·설치·로그 파이프라인은 동일 코드를 탄다.

## 12. 주요 이슈 및 유지보수 포인트

## 13. 불변식 (코드 수정 시 절대 위반 금지)

- [ ] 0. **표준 status**: `format_log_line`의 status로 허용되는 값: `OK / READY / RUN / DONE / ABORT / FAIL / END / SKIP / WARN`. **비표준 사용 금지**: `MISSING` / `?` / 그 외 표준 외 값 사용 금지. DEPS 체크 실패 → `FAIL` + msg에 사유("not found" 등). **msg 비어있으면 세로줄 누락됨**: `format_log_line`이 falsy msg를 무시하므로 `None`/`""` 대신 명시적 문자열 사용.
- [ ] 1. **state 딕셔너리 공유**: `MediaController.state`는 `DownloadWorker`에 참조 그대로 전달됨. 복사 금지.
- [ ] 2. **단방향 쓰기**: `canceled/skip`는 UI 스레드만 쓰고, 워커는 읽기만. CPython GIL 하에서 원자적.
- [ ] 3. **시그널만 통보**: 워커 → UI 통보는 절대 state가 아니라 Qt 시그널로만. 시그널 emit은 스레드 안전(QueuedConnection).
- [ ] 4. **UI 위젯 직접 조작 금지**: 워커에서 UI 위젯 직접 조작 절대 금지. 반드시 시그널을 통해 View에 요청.
- [ ] 5. **좀비 워커 패턴**: 폐기된 워커는 `_zombie_workers`에 넣고 자연 종료 시 `_reap_zombie()`로 소거. `wait()` 호출 금지.
- [ ] 6. **QSS 단일 출처**: 모든 스타일은 `theme.py`에서만 정의. 인라인 스타일 금지.
- [ ] 7. **의존성 단일 출처**: `pyproject.toml`이 유일한 의존성 정의 파일. 수동 설치 금지.
- [ ] 8. **emit 위치 인자 계약**: PyQt 시그널 emit은 **키워드 인자 절대 금지** (`log_concise.emit(msg, False, True)`). 키워드 인자는 런타임
   `TypeError: pyqtBoundSignal.emit() takes no keyword arguments` → 시그널 미도착 → `running` 잔류로 이어지는 실사고 이력 있음
   (2026-09-06 finalizer/progress_emitter/live_recorder 광역 수리).
- [ ] 9. **extractor_args 병합 규칙**: youtube 추출 옵션 주입은 반드시 `setdefault` 기반 병합(`client_opts` 계열 헬퍼 경유).
   player_client/skip/po_token을 통째로 덮어쓰면 다운로드 일관성(0% 스톨)이 깨진다.
- [ ] 10. **경량 분석/무거운 다운로드 분리**: `AnalyzeWorker`는 항상 `youtube:skip=[hls,dash]`(매니페스트 미열거), `DownloadWorker`는 항상
    매니페스트 재열거. 분석 옵션을 다운로드에 재사용 금지. **포맷 선택 UI 도입 시에도 분석 결과의 v_list/a_list를 다운로드
    포맷으로 직접 신뢰 금지** — 다운로드 경로에서 재열거된 `info` 기준으로 다시 매칭해야 함.
- [ ] 11. **로그 단일 진입 (v3.3.0)**: 모든 로그는 `raw_log.raw(tag, msg, is_status, is_error, to_tui)` 경유. `log_history.log` 직접 호출·`log_bus` 부활·워커 로그 시그널(`line/full/log_concise/log_full`) 신설 금지. history 적재는 raw 내부 1회가 유일 — 구독자(`_render_concise`/`_mirror_event_full`)에서 history 호출 금지.
- [ ] 12. **플래그 라우팅 (v3.3.0)**: TUI 노출은 `to_tui` 비트, 줄바꿈은 `no_wrap` 플래그로만 결정. 렌더 레이어(`log_console.append`→`_insert_clamped`→`_flow_lines`→`_render_clamp`)에서 문자열 콘텐츠 판정(정규식·`is_tui_line`·`startswith` 분기) 부활 금지. `is_tui_line`은 호환 shim — 호출부 신설 금지.
- [ ] 13. **신호-보고 분리 (v3.3.0)**: `check_done(list)` 등 결과 Signal은 Main이 중계 후 `report_*` 호출. Worker→Coordinator 직결 금지(시그널 교통 정리 — `check_done` 시그니처가 `(bool,str)`이 아니라 직결 시 오동작).
- [ ] 14. **READY 멱등 (v3.3.1 갱신)**: READY 발산은 `StartupState.can_emit_ready()`(= `deps_ok ∧ upgrade_done ∧ pot_ready ∧ ¬ready_emitted`) 게이트 경유 1회. 우회 직접 `ready_emitted.emit` 금지. `pot_ready`는 `report_pot`이 **상태 토큰**("staged"/"ready"/"standby")만 True로 세운다. **`deps_ok`의 의미는 "의존성 검사 단계 완료"** — stale(업데이트 대상) 존재는 게이트 사유가 아니며 `report_deps(True, …)`가 정본이다(v3.5.2 수리: 종전 `not bool(stale)` 보고가 업데이트가 있는 모든 기동을 15초 폴백으로 몰았다).
- [ ] 15. **잔재 정리 (v3.3.0)**: `media/chzzk_api/cookies`의 `import log_history`는 미사용 잔재 — 직접 호출로 회귀 금지, 정리 시 import 행 삭제. `log_console`의 `import re`는 `is_tui_line` 퇴출 후 미사용이므로 제거 후보(타 용도 전수 확인 후).
- [ ] 16. **L0 순수성 (v3.3.1)**: `po_client`는 표준 라이브러리만 — 상위 계층(pot_server) lazy import·락 파일 역참조 금지. 생존 판정은 순수 HTTP /ping만. 서버 수명주기/좀비 락 회수는 pot_server·POTManager 본연 책임.
- [ ] 17. **상태 토큰 계약 (v3.3.1)**: `POTManager.pot_finished`의 msg는 반드시 `"staged"`/`"ready"`/`"failed"` 토큰 — `StartupCoordinator.report_pot`이 정확 일치로 READY를 판정함. 사람용 상세 메시지("prewarm staged", "pot server bound ...")를 emit하면 **READY가 절대 열리지 않는다**(v3.3.1 이전 실제 결함).
- [ ] 18. **스레드 경계 (v3.3.1)**: raw_log dispatcher(데몬 스레드)에서 GUI 슬롯을 직접 호출하는 회귀 금지 — 반드시 `main._GuiLogBridge` Signal.emit + QueuedConnection으로 GUI 스레드에 위임. raw_log에 Qt 링크 금지(순수 파이썬 유지), 스레드 경계 책임은 수신층(main.py).
- [ ] 19. **POT 서버 단일 스폰 (v3.3.1)**: 서버 기동 진실의 근원은 `POTManager._POTWorker` 단독. `_spawn_existing` 등 스폰 함수는 1회만 호출(조건 평가+핸들 할당 원자화) — 이중 호출로 서버 2회 기동 방지. `pot_provider.POTProviderWorker` 재생성 금지.
- [ ] 20. **기동 폴백 계약 (v3.5.2)**: 15초 폴백(`force_unlock`)은 **READY 발산만** 한다 — POT 프리웜 취소 금지(`POTManager.cancel()`은 closeEvent 종료 정리 전용). 입력 잠금 판정(`get_current_app_state`)에 `_pot_manager.is_busy()`를 넣지 말 것(POT 대기 다운로드는 `toggle_download`의 `_pending_download` 큐가 담당). POT 빌드 서브프로세스(npm ci/tsc)는 반드시 timeout 상한(`_NPM_CI_TIMEOUT`/`_TSC_TIMEOUT`)을 가진다 — 무제한 대기는 `is_busy()`를 고정해 큐를 영구히 잠근다. 15초 폴백 타이머는 **동적**이다 — 실제 수급 하트비트(`UpdateWorker.work_tick` / POT `prewarm`·`starting` 전이)가 오면 `defer_fallback_timer()`가 카운트다운을 되감는다(`QTimer.singleShot` 단발로의 회귀 금지).
- [ ] 21. **하트비트·워치독·재시도 계약 (v3.6.0)**: (가) 하트비트(`work_tick`/`heartbeat`/`pot_work_tick`)는 **무페이로드**만 허용 — 문자열을 실으면 로그 시그널(§5-11)이 되므로 하드 금지. (나) 15초 폴백 발화 전 체인이 실제 동작 중이면 **유예 1회**(`_FALLBACK_GRACE_MS`) 후 재판정한다 — 재판정 없이 직접 발화 금지. (다) gate 대기(`_pending_download`)에는 **120초 2차 워치독**을 반드시 건다 — 만료 시 `cancel()`(트리 킬) + 큐 해제. (라) 봇 체크 재시도는 **URL당 1회**(`_pot_retry_done`) — 재실패 시 FAIL로 마무리, 루프 금지.
- [ ] 23. **입력 검증 게이트 (v3.8.0)**: `MediaController.parse_targets`를 우회해 URL 문자열을 워커에 직접 전달하는 경로 신설 금지. 비URL/미분석 입력은 `_is_valid_url`(스킴 + `dl_platform._DOMAIN_EXTRACTORS` SSOT suffix 매치)로 **배치 단위 차단**하고 `ANAL │ FAIL │ Invalid URL format` 1줄만 남긴다. 분석 실패(`on_analyze_error`) 시 `extracted_data`는 반드시 즉시 초기화함.
- [ ] 24. **워커에서 POTManager 접근 금지 (v3.8.0)**: `POTManager`는 뷰 소유 QObject다 — 워커 스레드에서 싱글톤 같은 존재하지 않는 API로 인스턴스에 접근하는 회귀 금지(`AttributeError` + 스레드 경계 위반). Layer 3 준비는 L0(`po_client.server_ping`)·L1(`pot_server` 스폰/빌드 헬퍼 + 프리웜 락)만 사용하는 `target_downloader._ensure_pot_server_ready()` 단일 경로로만 수행함.
- [ ] 25. **FAIL·완료 로그 단일 발행 (v3.8.0)**: 개별 실패 라인의 발행점은 `finalizer.finalize()` **단 1곳**이다 — `target_downloader` 등에서 즉시 `to_tui=True`로 중복 발행하는 회귀 금지. DL 중간 임시 스트림(`.fNNN`)은 `to_tui=False`로 은닉하고, 최종 결과물 1줄은 `progress_emitter.pp_hook`(postprocessor 훅)만 발행함.

- [ ] 26. **오류 로그 출력 규격 (v3.8.0)**: 모든 DEPS/UPGRADE/POT 오류는 4컬럼 단일 규격(`STAGE │ STATUS │ SCOPE │ MSG`)을 준수하며, `emit_component`/`LogEvent` 경유만 허용한다 (`raw_log.raw` 직접 호출 금지).
    * **TUI 포맷**: `[HH:MM:SS] STAGE │ STATUS │ SCOPE │ <간결 원인> → <시도 중인 해결책 또는 사용자 액션>`
      - TUI 폭 예산(Budget) 보호를 위해 `MSG`는 최대 55자 내외로 제한하며, 불필요한 라벨(`원인:`, `해결:`) 및 비표준 구분자(`::`) 사용을 금지함.
      - 저수준 C/Python 예외 원문(dyld, URLError, 스택 트레이스)은 TUI에 노출하지 않고 F12(상세 로그)/히스토리 버퍼로만 전량 격리 수용함.
    * **예시**:
      - 복구 시도: `[03:07:29] DEPS │ WARN │ FFMP │ binary incompatible → retry mirror (2/3)`
      - 최종 실패: `[03:07:49] SYS  │ FAIL │ MAIN │ all mirrors exhausted → check network (F12)`
      - 권한 오류: `[03:07:50] SYS  │ FAIL │ DIRS │ permission denied → check folder permissions`
    * **구성 요소**:
      - `<간결 원인>`: 기술적 원인 요약 (binary incompatible, all mirrors exhausted, checksum mismatch, permission denied 등)
      - `<진행/액션>`: 현재 자동 복구 시도 상태(`retry mirror (N/M)`) 또는 사용자 유도 조치(`check network (F12)`, `check folder permissions` 등)
    * **금지 사항**:
      - `raw_log.raw` 직접 호출 금지 (반드시 `emit_component` / `LogEvent` 단일 출처 사용)
      - TUI에 플랫폼/라이브러리 원시 예외(`dyld: Symbol not found`, `URLError` 등) 직접 덤프 금지
      - `fallback`, `timeout` 등 내부 엔진 구현 용어 노출 금지
      - 원인만 명시하고 후속 진행/액션을 누락하는 단발성 실패 로그 금지

- [ ] 27. **수급 무결성 및 무검증 레거시 폴백 절대 금지 (v3.9.0)**: 외부 의존성(FFmpeg, Node.js 등) 수급 시, 단일 출처의 SHA-256 무결성 검증을 통과하지 못하거나 타깃 아키텍처(Apple Silicon 등)를 네이티브로 지원하지 못하는 레거시 공급원(evermeet.cx, 비공식 미러 등)으로의 묵시적·단계적 폴백 체인 구성을 엄격히 금지함. Primary 공급자(macOS Homebrew Bottle, Windows/Linux BtbN)의 수급 및 `_verify_ffmpeg` 실행 검증에 실패할 경우, 시스템을 오염시키는 임의 바이너리로 도망치지 말고 반드시 `emit_error_standard` 규격을 통한 **명시적 FAIL**로 즉시 파이프라인을 닫고 사용자 개입(F12 안내)을 대기해야 함. '어떻게든 실행되게 만든다'는 명목의 무검증 우회는 시스템 무결성을 파괴하는 악성 퇴행임.

- [ ] 28. **FFmpeg 동적 수급 계약과 아키텍처 매핑 (v3.8.4)**: `components.py`의 FFmpeg 수급은 공급자 API를 매 트랜잭션 재해석한다 — 버전·URL을 하드코딩하지 않음.

    | 항목 | 계약 |
    |---|---|
    | Windows/Linux 공급자 | `BtbN/FFmpeg-Builds` `releases/latest` 단일 API |
    | Windows 자산 | `<...>-win64-gpl.zip` / `-winarm64-gpl.zip` (static, non-shared) |
    | Linux 자산 | `<...>-linux64-gpl.tar.xz` / `-linuxarm64-gpl.tar.xz` (static) |
    | 아키텍처 매핑 | `_normalize_arch`: `x86_64`/`amd64` → `amd64`, `aarch64`/`arm64` → `arm64`, 그 외 `ValueError` |
    | 무결성 | GitHub asset `digest` 필드는 **존재하지 않는다** — 별도 `checksums.sha256` 텍스트를 받아 정확한 basename 매칭으로만 SHA-256을 얻는다 |
    | zip 배제 | `.7z`/`.rar`/`.zst`는 7z 의존 회피를 위해 후보에서 제외한다 (`py7zr`류 L0 유입 금지) |
    | macOS 공급자 | `formulae.brew.sh` bottle. SHA-256 필수. `cellar` 메타데이터로는 **선제 거부하지 않고**, 최종 판정은 `_verify_ffmpeg` 실측 실행에 위임 |
    | macOS 정적 폴백 | **존재하지 않음.** evermeet.cx는 Apple Silicon 빌드를 제공하지 않는다 |
    | 전개 | ZIP은 정규화 경로 prefix 검사, tar는 `filter="data"`. `TarError`는 `ValueError`로 정규화 |
    | 설치 | `bin_incoming` → `bin_backup` → `os.replace` 로 교체하고 실패 시 backup 복원. `ffmpeg`·`ffprobe` 둘 다 필요 |
    | 기록 | `_record_provision_plan`이 `ProvisionManifest.load/save` + `ComponentRecord`로 감사 기록 (best-effort) |

    진행 틱은 `_ffmpeg_progress_event`(`component_id="ffmpeg"`, `is_progress=True`)로, 마감은 `_ffmpeg_done_event`(`is_progress=False`)로 발행한다 — 이 두 플래그가 브리지(TUI/F12)의 동일 라인 제자리 갱신을 성립시킨다.

- [ ] 29. **런타임 아카이브 전개 무결성 (Node.js/NPM 참수 금지) (v3.9.0)**: 외부 아카이브 전개 시 단일 실행 파일만 임의 색출해 승격시키는 행위는 의존 라이브러리(`lib/`)가 필요한 런타임에서 전면 금지됨.
    - `ffmpeg`는 중첩 디렉터리(`Cellar/.../bin`) 평탄화 승격 대상이지만, `node`는 실행 셸 스크립트(`bin/npm`)가 참조하는 내부 엔진(`lib/node_modules/npm/`)을 반드시 원본 계층 그대로 보존해야 함.
    - 런타임 모듈 전개 시 디렉터리 루트를 온전히 보존하지 않고 바이너리만 솎아내는 편의적 축약 전개는 엄격히 금지됨.

- [ ] 30. **수급 워커 단일 조회 및 마감 이벤트 TUI 관통 보장 (v3.9.0)**: `UpdateWorker` 및 프로비저닝 파이프라인은 대역폭 낭비와 UI 상태 동결을 방지하기 위해 다음 두 규칙을 강제함.
    - `mgr.ensure_all()` 호출 시 반드시 `stale_only=True`를 강제함. 정상 기동 중 검증 완료된 패키지를 무조건 전수 재다운로드(`stale_only=False`)하여 트래픽을 낭비하는 것을 금지함.
    - `_provision_cb`의 TUI 노출 판정(`show`) 조건에 `status in ("OK", "DONE")`을 반드시 포함함. 성공/마감 이벤트를 오류 상태가 아니라는 이유로 필터링하여 TUI에 `100% RUN` 상태가 화석처럼 고착되는 렌더링 누수를 영구 차단함.

- [ ] 31. **TUI 칼정렬 인덴트 보존 (format_log_line rstrip 원칙) (v3.9.0)**: 콘솔 조판 레이어(`format_log_line`)는 사용자가 의도한 좌측 정렬 공백(예: `"  0%"`)을 임의로 훼손해서는 안 됨.
    - `clean_msg = str(msg).strip()` 사용을 영구 금지하고, 반드시 우측 개행 및 공백만 제거하는 `clean_msg = str(msg).rstrip("\r\n ")`을 적용함.
    - 유니코드 표준 공백(`\u00a0` 포함)을 무차별 제거하여 `0%`와 `100%`의 게이지 시작 좌표가 어긋나는 시각적 지터링을 원천 방지함.

- [ ] 32. **macOS 격리 수급 호스트 승격(Bootstrap) 계약 (v3.9.0)**: Homebrew Bottle이 고정 경로 `LC_LOAD_DYLIB` 및 미설치 dylib 부재로 실행 검증(`_verify_ffmpeg`)에 전멸했을 때, 임의의 미검증 외부 아카이브로 도피하지 않음.
    - 1차: `DYLD_FALLBACK_LIBRARY_PATH`로 아카이브 내 동봉 `lib/`를 주입해 실행 프로브를 완수함.
    - 2차: 최종 실패 시, 호스트 시스템(`/opt/homebrew/bin/ffmpeg` 등)에 이미 존재하는 '정상 실행 검증된 바이너리'를 앱 격리 저장소(`writable_base()/ffmpeg/bin/`)로 원자적 복사(승격)하여 앱 단독 자산화함.
    - 호스트 바이너리 승격 시에도 `_verify_ffmpeg` 검증은 필수이며, 승격 실패 시에만 `emit_error_standard` 규격을 통한 명시적 FAIL로 파이프라인을 닫음.

- [ ] 33. **로그 저장 전량성과 뷰 제자리 갱신의 직교 분리 (v3.9.0)**: "F12/히스토리 전량 기록"과 "진행률 제자리 갱신"은 상호 배타적이지 않다.
    - CLI 명령어 원문(`$ cmd`), HTTP 트랜잭션, 아카이브 전개, 검증 실패 원인 등 저수준 시스템 행위는 영구 스토리지에 무삭제 순차 기록되어야 함.
    - 그러나 GUI 뷰(`VerboseLogWindow`) 및 메모리 링 버퍼(`_full_log_buf`)에서 다운로드 진행률 틱(`is_status=True` 또는 `component_id` 보유)을 단순 개행으로 무차별 적재하는 행위는 엄격히 금지함.
    - F12 창이 열려 있을 때는 `win.append(..., component_id)`를 통한 실시간 제자리 치환을, 창이 닫혀 있을 때는 `_full_log_buf`의 상태 줄 스냅샷 치환을 강제하여 F12 오픈 시 수천 줄의 게이지 잔해가 덤프되는 뷰 폭발을 방지해야 함.

- [ ] 34. **re-export 심볼 보존 및 F401 린트 자동 삭제 금지 (v3.12.4)**: 하위 모듈이 타 계층 심볼(예: `pot_server.py`의 `DEFAULT_HOST`, `DEFAULT_PORT`)을 재수출하는 경우 `__all__`을 명시하여 F401 자동 삭제로 인한 `ImportError` 런타임 크래시를 원천 차단. 호출부는 가급적 원천 모듈(`po_client.py`)을 직접 import.
- [ ] 35. **워커 스레드 예외의 F12 Traceback 강제 발행 (v3.12.4)**: `_POTWorker` 등 QThread의 `run()` 최상위 예외 블록(`except Exception`)에서 예외 문자열만 `outcome`에 격리하고 버스에 남기지 않는 은폐 패턴 절대 금지. 반드시 F12 전용 채널(`log_f12_cli`, `raw_log.raw` 등)로 전체 Traceback을 물리적으로 발행해 진단성 유지.
- [ ] 36. **스폰 인자 딕셔너리 방어적 초기화 (v3.12.4)**: `daemon_spawn_kwargs` 등 플랫폼 HAL에서 옵션(`use_no_window=False`)에 따라 빈 dict가 반환될 수 있으므로, OS 종속 키 조작 시 `kw["creationflags"] |= ...`가 아닌 `kw["creationflags"] = kw.get("creationflags", 0) | ...` 방어적 패턴을 강제하여 `KeyError` 방지.

## 14. 하지 말 것 (회귀 방지)

- [ ] ❌ `state/cfg` 딕셔너리를 복사해서 워커에 넘기는 것
- [ ] ❌ `smoke_test` 통과 없이 리팩토링 커밋하는 것
- [ ] ❌ `mirrors/*.md` 미러를 손으로 고치는 것 (항상 `.py`가 원본 — `python sync_mirrors.py`로 재생성)
- [ ] ❌ GUI 없는 CI 가정으로 Qt 코드를 임포트만으로 검증 끝이라 착각하는 것 — `smoke_test(offscreen)`를 돌릴 것
- [ ] ❌ 로그 채널을 각 호출점이 수동으로 흩뿌리기 — raw 버스(🤖 `raw_log.py`) 단일 진입만 유지. F12/메인/역사 팬아웃은 버스, 필터링은 각 모듈
- [ ] ❌ POT 워커가 포그라운드/히스토리를 직접 import 하는 것 — L0 `log_func` 콜백으로 연결 (계층 역전 방지)
- [ ] ❌ laziness를 굳히는 것 — "언제든 작동 가능한 준비 상태" 유지를 위해 stale 빌드를 FAIL로 닫지 말고 자동 리프레시로 따라간다
- [ ] ❌ 시그널 다중 emit/중복 판정 — F12 2중 공판, standby 2중 출력의 직접적 원인 (판정+로그는 단일 호출로 끝낼 것)
- [ ] ❌ Thin Wrapper 메서드 생성 (단순 위임은 모듈 함수 직접 호출로 대체)
- [ ] ❌ `except Exception`으로 모든 예외 뭉뚱그리기 (세분화된 예외 처리 적용)
- [ ] ❌ 상태 변수 개별 초기화 (초기화 메서드로 통합)
- [ ] ❌ View에서 비즈니스 로직 수행 (Controller로 이관)
- [ ] ❌ `log_console.emit_event/format_log_line`을 거치지 않고 컬럼 로그 문자열(`[HH:MM:SS] STAGE │ ...`)을 직접 조립하는 것 — TUI 규격 단일 출처 위반
- [ ] ❌ `.emit(..., is_status=..., is_error=...)` 키워드 인자 시그니처로 되돌리는 것 (커밋 전 `grep -n 'is_status=' '*.py'` 스팟체크)
- [ ] ❌ 분석(경량) 결과의 v_list/a_list를 '실제 다운로드 가능 포맷'으로 간주해 다운로드 포맷 선택에 그대로 쓰는 것
- [ ] ❌ **무검증·레거시 수급처(evermeet, SHA-256 미제공 소스 등)로의 폴백 체인 신설**: "실패 시 기존 정적 빌드 시도" 따위의 안일한 타협으로 검증되지 않은 바이너리나 Rosetta2 의존 바이너리를 앱 캐시에 유입시키는 행위 전면 금지. 실패는 숨겨야 할 흉측한 결함이 아니라, 격리하고 보고해야 할 시스템 계약임.
- [ ] ❌ **Homebrew Bottle 검증 실패 시 미검증 아카이브로 도피하는 것**: Bottle 실행 실패(dylib 불일치 등)가 발생했을 때 레거시 정적 빌드로 땜질하지 말고, 즉시 표준 에러 규격으로 실패 원인을 명시하고 프로세스를 중단할 것.
- [ ] ❌ **Node.js 압축 해제 시 `lib/` 폴더를 유기하는 행위**: Node.js 아카이브를 `ffmpeg`와 동일하게 취급하여 `bin/`만 쏙 빼오고 `lib/node_modules/`를 소각해 `Cannot find module '../lib/cli.js'`를 유발하는 행위 전면 금지.
- [ ] ❌ **의존성 정상 판정 후 전수 재다운로드 폭주(`stale_only=False`)**: 앞단 DEPS 검사가 통과했음에도 무조건 전체를 다시 받아 디스크와 대역폭을 낭비하는 게으른 호출 금지.
- [ ] ❌ **TUI 이벤트 게이트에서 `OK`/`DONE` 상태 차단**: `_provision_cb` 등 로그 브리지에서 에러/상태 틱만 통과시키고 정작 완료 마감(`OK`) 이벤트를 드롭시켜 TUI에 미완료 게이지 바를 방치하는 것.
- [ ] ❌ **`format_log_line`에서 무자비한 `.strip()`으로 좌측 패딩 제거**: 메시지 좌측 공백을 파괴하여 자릿수 고정(`  0%` vs `100%`)을 무너뜨리는 무신경한 문자열 정리 금지.
- [ ] ❌ **표준 에러 헬퍼에 임의 문자열을 넘겨 `unknown error`로 뭉개는 것**: `emit_error_warn` 등에 정규화 규격에 없는 문장을 던져 TUI를 오염시키지 말고, 허용된 표준 키워드(`binary incompatible` 등)만 엄격히 사용할 것.
- [ ] ❌ **'전량 기록'을 핑계로 F12 뷰에 수천 줄의 진행 틱을 개행 누적하는 것**: 디스크 파일 기록과 GUI 뷰 렌더링을 혼동하여 F12 창을 쓸모없는 게이지 바 폭포수로 마비시키는 행위 전면 금지.
- [ ] ❌ **'제자리 갱신'을 핑계로 CLI/네트워크 감사 원문을 파일에서 누락하는 것**: 화면을 정돈하겠답시고 `$ cmd` 실행문이나 HTTP 요청 원문 자체를 발행 단계에서 드롭시키는 행위 금지.
- [ ] ❌ **F401 린트 자동 수정 후 런타임 import 테스트 없이 커밋**: re-export 전용 심볼이 Ruff/린터의 unused import 제거(`--fix`)로 삭제되어 실행 시 `ImportError` 크래시를 유발하는 참사 방지.
- [ ] ❌ **QThread `run()` 예외 은폐 및 무음 크래시**: 워커 스레드의 최상위 예외 핸들러에서 에러를 내부 변수(`outcome`)에만 담고 F12 로깅 없이 조용히 종료하여 디버깅을 불가능하게 만드는 것.
- [ ] ❌ **플랫폼 스폰 딕셔너리의 무방비 키 접근 (`kw['creationflags']`)**: 플랫폼별 옵션에 따라 키가 존재하지 않을 수 있으므로 `.get()` 없이 직접 인덱싱하여 `KeyError`로 자식 프로세스 생성을 무너뜨리는 것.

## 15. 검증 워크플로우

- [ ] 1. **py_compile**: 변경된 모듈 전부 `python -m py_compile` 통과
- [ ] 2. **smoke_test**: `python smoke_test.py` 통과 (offscreen 플래그로 CI 가능)
- [ ] 3. **기능 확인**: 실제 다운로드/분석/라이브 녹화 1회씩 정상 동작
- [ ] 4. **플랫폼 교차 검증 (후속 과제)**: 이 앱은 macOS/Windows에서 동작하지만, 개발 머신에서는 **타깃 플랫폼 전용 분기를 직접 실행할 수 없다**.
   - macOS 개발 시 Windows 전용 분기(`winsound`, `CREATE_NO_WINDOW`, `JobObject`, `AppUserModelID`, Windows 브라우저 쿠키 경로, Gyan ffmpeg 수급)는 **import 가드(`try/except`, `platform.system()`) 검증만 가능**하고 실제 동작 검증 불가.
   - Windows 개발 시 macOS 전용 분기(Homebrew ffmpeg, POSIX 신호) 역시 검증 불가.
   - **원칙**: 플랫폼 비의존 코드(분석/다운로드/포맷 로직)는 현재 머신에서 전부 검증. 플랫폼 의존 코드는 반드시 **해당 플랡폼에서 수동 확인** 필요.
   - **수동 테스트 체크리스트 (배포 전)**:
     - [ ] Windows: 종료 확인 다이얼로그 알림음 + 작업표시줄 반짝임, 완료 비프, AppUserModelID 아이콘 그룹핑
     - [ ] Windows: `CREATE_NO_WINDOW` 자식 창 억제, JobObject 프로세스 트리 정리
     - [ ] macOS: Homebrew ffmpeg 수급 경로
     - [ ] 양쪽: `python -c "import main, downloader, live_recorder, pot_provider, dialogs, cookies"` 임포트 성공

> 핵심: **"돌아간다" ≠ "양쪽 다 돌아간다"**. CI는 offscreen(macOS) 기준이며, Windows 전용 동작은 릴라이즈 전 반드시 Windows 머신에서 직접 확인할 것.

---

### 15.1 마무리 — 링크 깨짐 확인 완료·체리피킹 요약 (v3.5.0)

- **링크 깨짐 점검**: 모든 내부 링크(`§`, `§§`, `[링크](#anchor)`) 정상 동작. 앵커(`###`, `####`)와 문서 내 참조(`HANDOVER §x.y`, `CHANGELOG 2026-09-15`) 정합. `mirrors/` 미러는 `sync_mirrors.py`로 동기화.
- **체리피킹(§8.1) 요약**: PySide6 사용 모듈(`QtCore/Widgets/Gui/Core/DBus` 등)만 포함, 미사용 모듈(WebEngine/Multimedia/3D/Charts 등) `--exclude-module`로 제거. 빌드 크기 ~80-100MB → ~50-60MB (30-40%↓). 사용 모듈은 `grep -rn 'PySide6.Qt'`로 확인 후 이 섹션 목록 갱신.
- **문서 동기화 완료**: `HANDOVER`·`CHANGELOG`·`README`·`mirrors/` 전체 동기화 완료. `sync_mirrors.py --check` 0건.

## 16. 파일 규칙

| 카테고리 | 규칙 |
|----------|------|
| **Python** | 모든 `.py` 파일 UTF-8, LF. 입출력 명시적 `encoding="utf-8"` |
| **JSON** | `dl_config.json` UTF-8 / indent-4 |
| **Markdown** | `.md` 파일 LF 유지 |
| **바이너리** | 이미지/폰트/실행 파일은 `.gitattributes`에서 binary 지정 |
| **문서 미러** | `.py`가 원본, `mirrors/*.md` + `mirrors/chzzktube_codebase.md` 합본은 `python sync_mirrors.py` 자동 생성. 손수정 금지 |