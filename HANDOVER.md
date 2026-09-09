# HANDOVER.md — ChzzkTube 인수인계서

> 이 문서는 다음 담당자(사람 또는 AI 에이전트)를 위해 작성된 프로젝트 인수 문서다.
> 코드 수정 전 반드시 **§1.1 개발 방향성**과 **§5 불변식**, **§6 하지 말 것**을 읽을 것.
> 마지막 갱신: v3.1.2+ — 2026-09-10 F12 중복 제거·raw 로그 버스·POT stale 감지 + 자동 리프레시 최신화

---

## 1. 프로젝트 개요

- **ChzzkTube**: YouTube/치지직(Chzzk) 영상 다운로드 Hyper-Minimalist Modern TUI 앱 (macOS / Windows / Linux 호환)
- **버전**: `v3.2.0` — 정의 위치 `config._APP_VERSION` (최신: 2026-09-10 F12 중복 제거·raw 로그 버스·POT stale 감지 + 자동 리프레시 최신화)
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

## 1.1 개발 방향성 및 TUI 표준 (v3.1.0+)

### 1. 핵심 철학 (Core Philosophy)
- **Hyper-Minimalist Modern TUI Media Extractor**: OS 순정 GUI 위젯을 완전히 배제하고, `fzf`·`lazygit` 감성의 모노스페이스 Flat TUI 레이아웃으로 전면 전환.
- **도구의 순수성**: 개인용·비상업적 듀얼유즈 툴로서 미디어 추출 본연의 안정성과 속도에 집중. 외부 우회 로직은 아래 "단계적 우회 계층화" 원칙에 따라 기본을 안전 경로로 고정하고, 차단 시에만 점진적 폴백.

### 2. UI 레이아웃 & 폰트 표준
- **Cascadia Mono 11px 통일**: 박스 드로잉 기호(`█`, `░`)의 베이스라인 및 높낮이 튐 현상을 근본적으로 차단.
- **Flat TUI 3-Layer 구조**:
  - **Configuration Bar (상단)**: 저장 경로 및 클릭 가능한 ASCII 버튼 태그 (`[ F1: Change ]`, `[ F2: Open ]`, `[ F12: Full Log ]`, `[ F3: Settings ]`).
  - **Input & Action Bar (중간)**: 프롬프트(`>`) 기반 URL 입력창. 레거시 `(x)` GUI 버튼을 제거하고 `[ ESC: Clear │ ENTER: Start ]` 단축키 중심 연동.
  - **Live Console Monitor (하단, `stretch=1`)**: 메인 윈도우 면적을 100% 모니터링 로그에 할당. Raw 디버그 로그는 `F12` 독립 서브 윈도우(`QDialog`)로 완전 격리.

### 3. 고정 칼럼 로그 규격 (Column-Aligned Monitor Standard)

#### 3.1 기본 포맷 (v3.1.0+)
- **표준 출력 포맷**:
  `[HH:MM:SS] STAGE │ STATUS │ PLATFORM │ SPEC │ MSG`
  
- **컬럼 역할 분리**:
  - `SPEC`: 순수 미디어 스펙만 출력 (`1080p30`, `h264`, `opus`, `4K`, `2026.8.19` 등) — **채널명·제목·파일명·통계 금지**
  - `MSG`: 가변 정보 (`제목`, `파일명`, `크기`, `속도`, `진행률` 등) — 길이 초과 시 `log_console._render_clamp` 픽셀 단위 절단 적용

#### 3.2 STAGE 값
- `SYS`: 시스템/시작 작업 (DEPS, POT, 업데이트, READY 등)
- `ANAL`: 분석 단계 (비디오/오디오 포맷 분석)
- `DL`: 다운로드 진행
- `LIVE`: 라이브 스트리밍 녹화
- `MERG`: 포맷 병합
- `BATCH`: 배치 작업 완료
- `DEPS`: 의존성 체크 (yt-dlp, streamlink, ffmpeg, node, pot)
- `POT`: PO Token 서버 관련

#### 3.3 STATUS 값
- `OK`: 작업 성공
- `READY`: 시스템 준비 완료 (시작 신호)
- `RUN`: 작업 중 (진행률 표시)
- `DONE`: 작업 완료
- `ABORT`: 사용자 취소
- `FAIL`: 작업 실패
- `WARN`: 경고
- `SKIP`: 작업 건너뛰기
- `END`: 스트림 종료 (라이브)

#### 3.4 PLATFORM 값 (3-8자 축약)
- 외부 의존성: `YTDL`, `STRE`, `FFMP`, `NODE`, `POT`
- 영상 플랫폼: `YT`, `CHZK`, `NFX`, `TIKT` 등 (media.py `_EXTRACTOR_SHORT_STATIC` 참조)
- 내부 구분: `VIDEO`, `AUDIO`, `SYS`

#### 3.5 예시 로그

[13:34:23] DEPS  │ OK   │ YTDL  │ 2026.8.19 │ 
[13:34:23] DEPS  │ OK   │ STRE  │ 8.5.0     │ 
[13:34:23] DEPS  │ OK   │ FFMP  │ 9.0.1     │ 
[13:34:23] DEPS  │ OK   │ NODE  │ v22       │ 
[13:34:23] DEPS  │ OK   │ POT   │ running   │ 
[13:34:23] SYS   │ READY│ SYS   │     -     │ ready
[13:34:24] ANAL  │ OK   │ YT    │ 1080p30   │ stream analyzed · YTN · "제목"
[13:34:25] ANAL  │ OK   │ VIDEO │ h264      │ 
[13:34:25] ANAL  │ OK   │ AUDIO │ opus      │ 
[13:34:26] DL    │ RUN  │ YT    │ 1080p30   │ 12.4M/s · 65% · [█⋯░]
[13:34:30] DL    │ OK   │ YT    │     -     │ video.mp4 (11.56 MB) · YTN

### 4. 시각적 디테일 및 영문 미니멀화
- **파스텔 톤 에러 컬러**: 눈 피로도를 높이는 원색 Red(`#FF0000`)를 Soft Pastel Red(`#E06C75` / `#F87171`)로 교체.
- **MSG 영문 미니멀화**: 서술형 한글 문장을 배제하고 1~3단어 수준의 소문자 영문 CLI 태그로 축소 (`deps ok`, `pot server bound`, `stream analyzed`, `download canceled by user`).

### 5. 단계적 우회 계층화 (Tiered Bypass Architecture)
YouTube 차단 회피는 "항상 공격"이 아니라 "방어적 폴백"으로 설계한다. 기본 레이어만 항상 가동하고, 상위 레이어는 차단 신호가 명확할 때만 순차적으로 활성화한다.

- **Tier 1 (기본, 항상 가동)**: 경량 추출(매니페스트 미열거). 이 앱의 주 통로.
- **PO Token 서버 (선택적 가동)**: `pot_provider`는 실행 초기 DEPS 체크 때 가동여부만 판단 후 **필요 시에만** 가동한다.
  - 가동 조건: `age_limit > 0` (연령 제한) 또는 `availability` in ('needs_auth', 'premium_only', 'subscriber_only', 'private')
  - 일반 공개 영상은 PO 서버 없이 다운로드 → 리소스 절약
  - 분석(`AnalyzeWorker`) 완료 후 판단, 필요 시 `[POT] RUN — starting...` 로그 출력
- **Tier 2 (명시적 폴백, 차단 시에만)**: 클라이언트 회전(`ios` → `tv`), JS 런타임 Solver(`ejs:github` + deno), 브라우저 쿠키 주입. `_RETRY_CLIENTS` 폴백 루프가 이에 해당하며, 성공 즉시 상위 레이어 중단.
- **운용 경계**: `cfg["yt_player_client"]`가 `"auto"`일 때만 Tier 2 폴백이 활성화된다. 사용자가 특정 클라이언트를 지정하면 Tier 1 해당 클라이언트 1회 시도 후 즉시 실패 처리(폴백 무한 방지).
- **측정**: 어떤 Tier로 다운로드가 성공했는지 상세 로그(F12)에 기록(`[client retry] bot check — X → Y`). 이는 "왜 폴백이 발동했는지" 추적하는 유일한 증거이며, 로컬 전용(간결 로그 미노출).

> 원칙: **기본은 Tier 1, PO 서버는 필요 시에만, Tier 2는 명시적 폴백**. 핵심 코어(`media`/`downloader` 추출 파이프라인)와 우회 로직(`client_opts`)의 결합도를 헬퍼 모듈로 분리해, 우회 로직 변경이 코어에 영향을 주지 않도록 한다.

### 6. 렌더링 엔진 정책 (Rendering Engine Policy)
**PySide6 (Qt 엔진) 유지.** 렌더링 주권(폰트 강제, 픽셀 단위 정렬)과 크로스플랫폼 마우스/클립보드를 동시에 확보하기 위해 TTY 계열(curses/Textual)은 배제한다.

- **Qt 엔진 유지 이유**: 폰트 종류/크기/행간 강제 제어, 박스 드로잉 픽셀 정렬, OS 레벨 마우스/클립보드/포커스 지원을 모두 충족하는 유일한 선택.
- **라이선스**: PySide6 (LGPL) — 상용/비상업 가리지 않고 자유롭게 사용 가능. PyQt6 대비 법적 리스크 없음.
- **핵심 로직 분리**: `media`(포맷/코덱/비트레이트), `log_console`(컬럼 포맷·트리 조판), `downloader`/`target_downloader`(추출 파이프라인), `client_opts`(옵션 빌드)는 **프레임워크 비의존**으로 분리. 향후 렌더러 교체 시 이 모듈들은 수정 불포함.
- **In-Place Overwrite (제자리 갱신)**: `DL │ RUN` 및 `LIVE │ RUN` 틱 로그는 매 틱마다 새 줄을 만들지 않고 커서 조작을 통해 마지막 줄을 제자리 갱신.
- **상태 및 스테이지 코드**:
  - `LIVE` 스테이지 코드 신설 (VOD 다운로드 `DL`과 라이브 녹화 구분).
  - 사용자 취소는 `DL │ ABORT`로 독립 표기 (`FAIL` 오류와 명확히 분리).

---

## 2. 실행 환경

| 항목 | 상태 |
|------|------|
| Python | 3.12.14 (pyenv, `.python-version` 고정) |
| 의존성 단일 출처 | `pyproject.toml` / `uv.lock` — PyQt6 6.11.0 · yt-dlp 2026.8.19 · streamlink 8.5.0 고정. build 그룹엔 pyinstaller (Windows 빌드용) |
| FFmpeg | 런타임 수급 — `components.ensure_ffmpeg()` 퍼사드 (시스템 PATH 우선 → GitHub 릴리스 → macOS Homebrew 전략) |
| Node.js 22+ | PO Token 서버용 (`pot_provider`) — 시스템 우선, 없으면 포터블 다운로드 |
| 콘솔 폰트 | `CascadiaMono-VariableFont_wght.ttf` (BASE_DIR, 11px — theme.py 단일 출처). `D2Coding-Regular.ttf`는 레거시 잔재(미로드) |
| 히스토리 로그 | `logs/chzzktube_YYYY-MM-DD.log` (`log_history`, 날짜별 append, 30일 보존, thread-safe) |
| 스모크 | `smoke_test.py` — `QT_QPA_PLATFORM=offscreen` 강제로 CI 가능 |

## 3. 아키텍처 (역방향 참조 0 · 순환 import 0 — 실측 검증됨)

### 레이어별 구조 (4계층 + L0 Leaf)

```
LAYER 3: View (Qt Widgets)
  main.py · dialogs.py · theme.py · log_console.py
LAYER 2: Orchestrators
  startup_coordinator.py · controller.py
LAYER 1: Worker Threads (QThread)
  downloader.py · analyze_worker.py · update_worker.py · pot_provider.py
LAYER 0.5: Pipeline Functions (ctx 기반, 비스레드)
  target_downloader.py · progress_emitter.py · live_recorder.py · finalizer.py · dl_context.py
LAYER 0: Domain / Helpers / Infra (Leaf)
  media.py · chzzk_api.py · cookies.py · config.py · updater.py · utils.py
  worker_context.py · yt_logger_bridge.py · dl_platform.py · speed_window.py · playlist.py
  po_client.py(L0) · node_provider.py(L0) · pot_server.py(L1) ·
  components.py · log_history.py · smoke_test.py · sync_mirrors.py
```

### 시그널 방향 트리

```
StartupCoordinator._on_update_check_done → upgrade → _on_auto_upgrade_done → report_upgrade → report_ready(1회)
POTProviderWorker.finished → coordinator.report_pot
UpdateWorker.check_done → DEPS 5줄 출력 + upgrade 기동 + report_deps 플래그
MediaController: analyze_result_ready → View 포워딩 (Signal-to-Signal)
DownloadWorker: log_concise → append_concise_log (is_status=True 틱)
```

### 모듈 목록 (34개)

| 분류 | 모듈 | 핵심 책임 |
|------|------|----------|
| View | main | 진입점 + MainWindow |
| View | dialogs | 6종 Dialog + ComboBox + UpdateWorker(이전) |
| View | theme | QSS/컬러 토큰 |
| View | log_console | 컬럼 포맷 규격(format_log_line/emit_dl/emit_err) |
| Control | controller | MediaController(state 머신 + 워커 생명주기) |
| Control | startup_coordinator | 시작 시퀀스 게이트(READY 1회 발산) |
| Worker | downloader | DownloadWorker + YtLoggerBridge |
| Worker | analyze_worker | AnalyzeWorker(QThread) — 경량 분석 |
| Worker | update_worker | UpdateWorker(QThread) — DEPS/업그레이드 |
| Worker | pot_provider | POTProviderWorker + 3개 모듈 재수출 facade |
| Pipeline | target_downloader | VOD/라이브/치지직/Streamlink 분기 |
| Pipeline | progress_emitter | emit_dl/emit_err — 진행 틱/헤더/완료 |
| Pipeline | live_recorder | ffmpeg/streamlink 라이브 녹화 |
| Pipeline | finalizer | 배치 마감 요약 |
| Pipeline | dl_context | DownloadContext dataclass (파이프라인 계약) |
| Shared | yt_logger_bridge | 공용 로거 어댑터 |
| Infra | po_client | L0 leaf — PO Token HTTP 클라이언트 |
| Infra | node_provider | L0 leaf — Node.js 런타임 수급 |
| Infra | pot_server | L1 — bgutil 서버 빌드/기동 |
| Domain | media | map_res, format_bytes, codec rank |
| Domain | chzzk_api | 치지직 클립/VOD API 분석 |
| Domain | cookies | 브라우저 쿠키 DB 추출 |
| Domain | config | 경로/기본값/로드/저장 |
| Domain | updater | 구성요소 버전 확인/PyPI 업그레이드 |
| Domain | utils | 문자열/윈도우 헬퍼 |
| Domain | dl_platform | URL → 플랫폼/콘텐츠 타입 |
| Domain | speed_window | 속도 측정 슬라이딩 윈도우 |
| Domain | playlist | YouTube 채널 URL 정규화 |
| Infra | components | ffmpeg 런타임 수급 퍼사드 |
| Infra | log_history | thread-safe 히스토리(30일 보존) |
| Infra | worker_context | Worker 컨텍스트 헬퍼 |
| Infra | smoke_test | offscreen 기동 검증 하네스 |
| Infra | sync_mirrors | docstring → .md 미러 동기화 |

## 4. 핵심 데이터 구조
```python
{"running": bool, "canceled": bool, "skip": bool, "analyzing": bool}
```

### cfg (config.default_config() 15키 — 로드 시 dl_config.json 병합)
```python
download_path, container("mp4"), embed_subtitles, audio_only,
fast_download(True), remove_duplicates(True), auto_open_folder(True),
completion_action("none"), play_sound(True), max_video_res("none"),
filename_prefix("none"), filename_suffix("id"),
browser_cookie("auto"), cookie_file_path(""), yt_player_client("auto")
```
> 런타임 cfg = `default_config()` + `dl_config.json` 통째 병합(`load_config`의 `cfg.update`).
> 기존 설정 파일에 남은 레거시 키(`use_cut`/`cut_start`/`cut_end`/`max_res`/`use_date`/
> `use_uploader`/`use_title`/`use_id`/`filename_format`/`auto_shutdown`)는 보존되지만
> **현재 어떤 모듈도 읽지 않는다(데드 키)** — 제거 시 깔끔해진다.

### Worker ↔ UI 시그널 계약
```
AnalyzeWorker(target_url, cfg):
    result_ready(dict) : 성공 — {info, v_list, a_list, is_chzzk:False, yt_client}
                         또는 {info, v_list, a_list, is_chzzk:True}
                         또는 {is_playlist:True, title, count, v_list:[], a_list:[]}
    error_occurred(str): 실패 — 미니멀 영문 오류 코드
    log_full(str)      : yt-dlp 원본 로그 라인

DownloadWorker(targets, cfg, state_dict, v_sel, a_sel, is_live_hint=False,
               v_spec=None, audio_desc="", yt_client="auto"):
    log_concise(str, bool, bool) : (텍스트, is_status, is_error) — 위치 인자 3개
    log_full(str)                : yt-dlp 원본 로그 라인
    finished_all(int, int)       : (성공 수, 실패 수)
```
> `yt_client`(분석에서 실증·통과한 player_client)는 다운로드가 분석과 같은
> 클라이언트로 0% 스톨 경로를 재진입하지 않도록 강제하는 핵심 값.

## 5. 불변식 (코드 수정 시 절대 위반 금지)

0. **표준 status**: `format_log_line`의 status로 허용되는 값: `OK / READY / RUN / DONE / ABORT / FAIL / END / SKIP / WARN`. **비표준 사용 금지**: `MISSING` / `?` / 그 외 표준 외 값 사용 금지. DEPS 체크 실패 → `FAIL` + msg에 사유("not found" 등). **msg 비어있으면 세로줄 누락됨**: `format_log_line`이 falsy msg를 무시하므로 `None`/`""` 대신 명시적 문자열 사용.
1. **state 딕셔너리 공유**: `MediaController.state`는 `DownloadWorker`에 참조 그대로 전달됨. 복사 금지.
2. **단방향 쓰기**: `canceled/skip`는 UI 스레드만 쓰고, 워커는 읽기만. CPython GIL 하에서 원자적.
3. **시그널만 통보**: 워커 → UI 통보는 절대 state가 아니라 Qt 시그널로만. 시그널 emit은 스레드 안전(QueuedConnection).
4. **UI 위젯 직접 조작 금지**: 워커에서 UI 위젯 직접 조작 절대 금지. 반드시 시그널을 통해 View에 요청.
5. **좀비 워커 패턴**: 폐기된 워커는 `_zombie_workers`에 넣고 자연 종료 시 `_reap_zombie()`로 소거. `wait()` 호출 금지.
6. **QSS 단일 출처**: 모든 스타일은 `theme.py`에서만 정의. 인라인 스타일 금지.
7. **의존성 단일 출처**: `pyproject.toml`이 유일한 의존성 정의 파일. 수동 설치 금지.
8. **emit 위치 인자 계약**: PyQt 시그널 emit은 **키워드 인자 절대 금지** (`log_concise.emit(msg, False, True)`). 키워드 인자는 런타임
   `TypeError: pyqtBoundSignal.emit() takes no keyword arguments` → 시그널 미도착 → `running` 잔류로 이어지는 실사고 이력 있음
   (2026-09-06 finalizer/progress_emitter/live_recorder 광역 수리).
9. **extractor_args 병합 규칙**: youtube 추출 옵션 주입은 반드시 `setdefault` 기반 병합(`client_opts` 계열 헬퍼 경유).
   player_client/skip/po_token을 통째로 덮어쓰면 다운로드 일관성(0% 스톨)이 깨진다.
10. **경량 분석/무거운 다운로드 분리**: `AnalyzeWorker`는 항상 `youtube:skip=[hls,dash]`(매니페스트 미열거), `DownloadWorker`는 항상
    매니페스트 재열거. 분석 옵션을 다운로드에 재사용 금지. **포맷 선택 UI 도입 시에도 분석 결과의 v_list/a_list를 다운로드
    포맷으로 직접 신뢰 금지** — 다운로드 경로에서 재열거된 `info` 기준으로 다시 매칭해야 한다.

## 6. 하지 말 것 (회귀 방지)

- ❌ `state/cfg` 딕셔너리를 복사해서 워커에 넘기는 것
- ❌ `smoke_test` 통과 없이 리팩토링 커밋하는 것
- ❌ `.md` 미러를 손으로 고치는 것 (항상 `.py`가 원본)
- ❌ GUI 없는 CI 가정으로 Qt 코드를 임포트만으로 검증 끝이라 착각하는 것 — `smoke_test(offscreen)`를 돌릴 것
- ❌ 로그 채널을 각 호출점이 수동으로 흩뿌리기 — raw 버스(🤖 `raw_log.py`) 단일 진입만 유지. F12/메인/역사 팬아웃은 버스, 필터링은 각 모듈
- ❌ POT 워커가 포그라운드/히스토리를 직접 import 하는 것 — L0 `log_func` 콜백으로 연결 (계층 역전 방지)
- ❌ laziness를 굳히는 것 — "언제든 작동 가능한 준비 상태" 유지를 위해 stale 빌드를 FAIL로 닫지 말고 자동 리프레시로 따라간다
- ❌ 시그널 다중 emit/중복 판정 — F12 2중 공판, standby 2중 출력의 직접적 원인 (판정+로그는 단일 호출로 끝낼 것)
- ❌ Thin Wrapper 메서드 생성 (단순 위임은 모듈 함수 직접 호출로 대체)
- ❌ `except Exception`으로 모든 예외 뭉뚱그리기 (세분화된 예외 처리 적용)
- ❌ 상태 변수 개별 초기화 (초기화 메서드로 통합)
- ❌ View에서 비즈니스 로직 수행 (Controller로 이관)
- ❌ `log_console.emit_event/format_log_line`을 거치지 않고 컬럼 로그 문자열(`[HH:MM:SS] STAGE │ ...`)을 직접 조립하는 것 — TUI 규격 단일 출처 위반
- ❌ `.emit(..., is_status=..., is_error=...)` 키워드 인자 시그니처로 되돌리는 것 (커밋 전 `grep -n 'is_status=' '*.py'` 스팟체크)
- ❌ 분석(경량) 결과의 v_list/a_list를 '실제 다운로드 가능 포맷'으로 간주해 다운로드 포맷 선택에 그대로 쓰는 것

## 7. 검증 워크플로우 (수정 후 필수 3단계 + 플랫폼 후속)

1. **py_compile**: 변경된 모듈 전부 `python -m py_compile` 통과
2. **smoke_test**: `python smoke_test.py` 통과 (offscreen 플래그로 CI 가능)
3. **기능 확인**: 실제 다운로드/분석/라이브 녹화 1회씩 정상 동작
4. **플랫폼 교차 검증 (후속 과제)**: 이 앱은 macOS/Windows에서 동작하지만, 개발 머신에서는 **타깃 플랫폼 전용 분기를 직접 실행할 수 없다**.
   - macOS 개발 시 Windows 전용 분기(`winsound`, `CREATE_NO_WINDOW`, `JobObject`, `AppUserModelID`, Windows 브라우저 쿠키 경로, Gyan ffmpeg 수급)는 **import 가드(`try/except`, `platform.system()`) 검증만 가능**하고 실제 동작 검증 불가.
   - Windows 개발 시 macOS 전용 분기(Homebrew ffmpeg, POSIX 신호) 역시 검증 불가.
   - **원칙**: 플랫폼 비의존 코드(분석/다운로드/포맷 로직)는 현재 머신에서 전부 검증. 플랫폼 의존 코드는 반드시 **해당 플랡폼에서 수동 확인** 필요.
   - **수동 테스트 체크리스트 (배포 전)**:
     - [ ] Windows: 종료 확인 다이얼로그 알림음 + 작업표시줄 반짝임, 완료 비프, AppUserModelID 아이콘 그룹핑
     - [ ] Windows: `CREATE_NO_WINDOW` 자식 창 억제, JobObject 프로세스 트리 정리
     - [ ] macOS: Homebrew ffmpeg 수급 경로
     - [ ] 양쪽: `python -c "import main, downloader, live_recorder, pot_provider, dialogs, cookies"` 임포트 성공

> 핵심: **"돌아간다" ≠ "양쪽 다 돌아간다"**. CI는 offscreen(macOS) 기준이며, Windows 전용 동작은 릴라이즈 전 반드시 Windows 머신에서 직접 확인할 것.

## 8. 빌드 및 배포 (PyInstaller)

### 8.1 체리피킹 원칙
PySide6 전체 패키지는 수십 MB이므로, **빌드 시 실제 사용하는 Qt 모듈만 포함하고 나머지는 반드시 제거**한다. 개발 중 전체 설치는 어쩔 수 없으나, 배포 바이너리는 `--exclude-module`로 최소화한다.

- **제거 대상 모듈** (런타임 사용 0, PyInstaller 빌드 시 `--exclude-module` 적용):
  - `PySide6.QtWebEngine`, `PySide6.QtMultimedia`, `PySide6.Qt3D*`, `PySide6.QtCharts`, `PySide6.QtDataVisualization`, `PySide6.QtNetworkAuth`, `PySide6.QtBluetooth`, `PySide6.QtNfc`, `PySide6.QtRemoteObjects`
  - 사용 모듈은 코드 변경 시 `grep -rn 'PySide6.Qt' --include='*.py'`로 확인 후 목록 갱신.
- **효과**: 전체 포함 시 ~80-100MB → 체리피킹 시 ~50-60MB (30-40% 감소).
- **원칙**: "안 쓰는 모듈은 빌드에 넣지 않는다" — 구체 목록보다 **원칙을 우선**하며, 새 Qt 모듈 추가 시 이 섹션의 사용 모듈 목록도 함께 갱신할 것.

### 8.2 자동 업데이트 정책 (Nightly Channel)
포터블 빌드에서도 yt-dlp 자동 업데이트를 지원한다. 네트워크 의존은 이 앱에서 본질적이다 (웹 미디어 추출기).

- **Stable 채널** (기본): PyPI 릴리즈 기준, 안정 버전 수급
- **Nightly 채널** (선택): yt-dlp-nightly 패키지, 최신 우회 로직 포함
- **업데이트 방식 (Dev/Frozen 통합)**: 모든 환경에서 동일한 직접 다운로드 경로 사용. `pip install`은 빌드 시(PyInstaller)만 사용.
  - Dev 환경: `_frozen_upgrade_ytdlp()`, `_frozen_upgrade_streamlink()` 직접 호출
  - 포터블(PyInstaller): PyPI whl에서 yt-dlp 바이너리 직접 다운로드 후 교체 (Stable) / GitHub nightly-builds release 다운로드 (Nightly)
  - 이유: Dev와 포터블이 동일한 코드 경로를 타야 디버깅 가능. Frozen과 Dev가 분기되면, 사용자에게서만 발생하는 버그를 Dev에서 재현하지 못함.
- **버전 확인 (2분기 구조, v3.1.1)**: dev 는 실제 CLI 실행(.venv/bin/yt-dlp --version → 원문 F12), frozen 은 PYZ 임베드라 importlib.metadata 폴백 — 판정 로직은 updater.check_deps 단일화. **F12 = raw 원문 전용(갱신형 포함), 메인 = TUI 컬럼 가공**. 두 로그가 같은 정보를 이중으로 띄우지 않는다 (교체 원칙). Nightly 채널은 설정 UI 에서 실제 반영 — stale 채널 전환 시 다운그레이드 감지 포함.
- **업데이트 실패 시**: 기존 버전 유지, 다음 실행 시 재시도
- **bgutil (PO 토큰 서버)**: GitHub 태그 릴리즈에서 자동 수급, pot_provider가 별도 관리
- **적용 범위**: yt-dlp only (streamlink은 Stable only, Nightly 미지원)
- **DEPS 로그 확장** (v3.1.0 추가): `check_deps()`는 PyPI 패키지뿐 아니라 외부 바이너리(ffmpeg, node)와 PO 토큰 서버도 확인. `shutil.which()`로 존재 여부, `pot_provider`로 PO 서버 핑 체크.

### 8.3 선택 과제 (향후)
- ❌ **PO 서버 실패 시 폴백**: 봇 체크 실패 시 PO 서버 가동 후 재시도 (현재는 info 사전 감지만 적용)
- ✅ **설정 UI**: 업데이트 채널 (Stable/Night) 선택 다이얼로그 — 완료
- ✅ **streamlink 직접 다운로드**: 포터블 빌드에서 streamlink whl 직접 수급 — 완료

### 8.4 빌드 시 해야 할 일 (OS별 체크리스트) — v3.1.1 신설

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


## 9. 파일 규칙

| 카테고리 | 규칙 |
|----------|------|
| **Python** | 모든 `.py` 파일 UTF-8, LF. 입출력 명시적 `encoding="utf-8"` |
| **JSON** | `dl_config.json` UTF-8 / indent-4 |
| **Markdown** | `.md` 파일 LF 유지 |
| **바이너리** | 이미지/폰트/실행 파일은 `.gitattributes`에서 binary 지정 |
| **문서 미러** | `.py` docstrings가 원본, `.md` 미러는 자동 생성. 손수정 금지 |

## 9. 수정 히스토리 요약 (최신순, 핵심만)

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
| §4 데이터 | default_config 15키(+yt_player_client), 데드 키 10종 명기, 시그널 계약 실제 서명·result_ready 형상 반영 |
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
| `HANDOVER.md` | 로그 표준 문서화 (STAGE·STATUS·PLATFORM·SPEC·MSG 5컬럼) |

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
- 프리웜 자동 리프레시는 "잠긴 사이 사전 제거 기능"에 대해 게이트/다운로드 시점 실패 처리와 별개 — 프리웜은 최신 빌드 확보 우선 (📖 HANDOVER §1.1)

---

## 10. 참고 문서

- `CHANGELOG.md` — 버전별 변경 사항
- `README.md` — 프로젝트 소개
- `CLAUDE.md` — (폐지: 규약은 `.clinerules`로 통합)
