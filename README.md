## ChzzkTube

Hyper-Minimalist Modern TUI 미디어 추출기 — YouTube / 치지직(Chzzk) 영상·라이브 다운로드를 위한 개인용·비상업적 듀얼유즈 도구.

"fzf · lazygit" 감성의 모노스페이스 Flat TUI로, OS 순정 GUI 위젯 없이 콘솔만으로 모든 작업을 처리한다.

**버전**: `v3.12.5` — 테스트 스위트 전수조사 정비·스모크 하네스 비동기 생존 검증·눈속임 테스트 퇴출 및 런타임 전환·오류 로그 새니타이징

### 스택

- Python 3.12.14 (pyenv / `.python-version` 고정) + PySide6
- yt-dlp(독립 실행형 바이너리) + FFmpeg(리먹싱)
- Node.js 22+ (PO Token 서버 — 백그라운드 감시, 필요 시에만 기동)

### 실행

```bash
# 가상환경 권장 (예: .venv)
python main.py            # 루트 씬 런처 → chzzktube.ui.main_window.main()
```

- `F12`: 전체 상세 로그(F12 창) 열기
- `ESC / Enter`: URL 입력창 초기화 / 분석·다운로드 시작
- 설정: `dl_config.json`(CONFIG_DIR) — 저장 경로·포맷·쿠키·업데이트 채널 등 23개 기본 키

### 소스 구조 (레이어 패키지)

```
main.py                      # 씬 런처 (python main.py / PyInstaller 진입점)
chzzktube/
  ui/                        # L3 View (Qt 위젯) — main_window·dialogs·theme·log_console
  control/                   # L2 오케스트레이터 — controller·startup_coordinator·pot_manager
  workers/                   # L1 QThread — downloader·analyze_worker·update_worker
  pipeline/                  # L0.5 파이프라인 함수 — target_downloader·finalizer·live_recorder
  core/                      # L0 도메인/순수 — config·log_emitter(Qt-free)·media·utils 등
  infra/                     # L0 인프라 — po_client·node_provider·pot_server·updater
assets/                      # icon.ico · CascadiaMono 폰트 (spec datas 1:1)
docs/                        # HANDOVER · CHANGELOG · 아키텍처 등
mirrors/                     # sync_mirrors.py 생성 산출물 (.py → .md)
```

### 빌드

- PyInstaller `ChzzkTube.spec` 기반 onedir/onefile 빌드가 구성되어 있다.
- 환경은 `.python-version` 및 프로젝트 의존 패키지를 기준으로 맞춘다.

### PO Token 서버 (PO 우회) — 3계층 파이프라인

- **Layer 1 (순정 네이티브)**: `player_client="auto"` 단일 호출 → yt-dlp 순정 클라이언트 체인(`web_embedded` → `tv_downgraded` → `web_safari` → `mweb`...) + EJS 솔버(deno/node) 자동 작동
  - 공개 영상 & 멤버십(쿠키有): 여기서 1080p+Opus 즉시 해결 ✅ **POT 서버 미기동**
- **Layer 2 (POT 서버)**: `age_limit > 0` (연령제한) **또는** 봇 체크/포맷 상실 감지 시에만 기동
  - **`subscriber_only`(멤버십) 제외** — Layer 1에서 쿠키+EJS로 해결
  - bgutil 서버에서 PO token + visitorData 획득
- **Layer 3 (재시도)**: 토큰 주입하여 동일 순정 호출 1회 재시도 → 1080p+ 분리 포맷(`bv*+ba`) 확보
- 앱 수동 클라이언트 로테이션(`_RETRY_CLIENTS`, `client_chain`) **완전 제거** — CLI와 100% 동일 동작

### 주의사항

- 네트워크 접근이 본질인 도구다(yt-dlp 스트리밍, PO 서버 빌드·갱신 등).
- 로그 설계: 모든 동작 로그는 `raw_log.raw()` 단일 버스 진입 — history·F12는 전량 수신, 메인 TUI는 발행자의 `to_tui` 선택으로 팬아웃한다.
- 스레드 설계: `raw_log`는 표준 라이브러리만 쓰는 순수 dispatcher(bounded queue)이며, GUI 갱신은 `main._GuiLogBridge`의 Qt Signal(QueuedConnection)을 통해 메인 스레드에서만 실행된다 — 워커 스레드의 위젯 직접 접근은 구조적으로 차단된다.
- 로그 규격(v3.4.0): 메인 TUI는 `[HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG`의 4컬럼 고정 폭을 사용한다. `PLATFORM`·`SPEC`은 별도 컬럼으로 출력하지 않으며, 미디어/버전 정보는 MSG 앞 태그로 보존한다.
- 설정 기본값: `download_path`, `container`, `embed_subtitles`, `audio_only`, `fast_download`, `remove_duplicates`, `auto_open_folder`, `completion_action`, `play_sound`, `max_video_res`, `pick_format`, `filename_prefix`, `filename_suffix`, `browser_cookie`, `cookie_file_path`, `yt_player_client`, `update_channel`, `auto_update_check`, `embed_thumbnail`, `embed_chapters`, `subtitle_langs`, `concurrent_fragments`
- CI: push/PR 시 GitHub Actions가 `QT_QPA_PLATFORM=offscreen` 환경에서 전체 pytest를 실행한다. 저장소에는 커밋 전 훅(pre-commit) 설정이 없다 — 검증은 CI와 `pytest tests/` 수동 실행으로 수행한다.

### 전체 계층도 (L0 Launcher → L4 View → L1 Model)

```mermaid
%%{init: {
  'theme': 'dark',
  'themeVariables': {
    'background': 'transparent',
    'clusterBkg': '#161b22',
    'clusterBorder': '#30363d',
    'primaryColor': '#21262d',
    'primaryBorderColor': '#8b949e',
    'primaryTextColor': '#c9d1d9',
    'lineColor': '#58a6ff'
  }
}}%%
flowchart TB
    subgraph L_ROOT["Entry · Root"]
        MAIN["main.py (Scene Launcher)"]
        SMK["smoke_test.py / tests / mirrors"]
    end

    subgraph L4["L4 · View — Qt UI (chzzktube/ui)"]
        direction LR
        MW["MainWindow<br/>(Bus Sub / Watchdog)"]
        DLG["dialogs.py<br/>(Dialogs + F12)"]
        LC["log_console.py<br/>(TUI Log Render)"]
        TH["theme.py<br/>(Dark QSS)"]
    end

    subgraph L3["L3 · Control & Workers — Orchestration"]
        direction TB
        subgraph ORCH["Control (chzzktube/control)"]
            SC["StartupCoordinator<br/>(READY Gate)"]
            SS["StartupState<br/>(Single Truth)"]
            PM["POTManager<br/>(Prewarm / Gate)"]
            MC["MediaController<br/>(Session State)"]
        end
        subgraph WK["Workers (chzzktube/workers)"]
            direction LR
            UW["UpdateWorker"]
            AW["AnalyzeWorker"]
            DW["DownloadWorker"]
            PW["_POTWorker"]
        end
    end

    subgraph L2["L2 · Pipeline / Infra (chzzktube/pipeline & infra)"]
        direction LR
        PL["Pipeline Functions<br/>(target_downloader · live_recorder · finalizer)"]
        INFRA["Infrastructure<br/>(pot_server · node_provider · updater · components)"]
    end

    subgraph L1["L1 · Core / Leaf (chzzktube/core)"]
        direction LR
        RAW["raw_log · log_event<br/>(Bounded Bus)"]
        DOM["config · dl_platform · media<br/>(Pure Domain / Leaf)"]
    end

    MAIN --> MW
    SMK -.-> MW
    MW -->|User Actions| MC
    MW -->|Coordination| SC
    MC -->|Spawn| WK
    PM -->|Spawn| PW
    WK -->|Result Signal| ORCH
    ORCH --> PL
    PL --> INFRA
    PL --> RAW
    INFRA --> DOM
    RAW --> DOM
```

### 기동 시퀀스 (READY 게이트 · 15초 폴백 · 동적 워치독)

```mermaid
%%{init: {
  'theme': 'dark',
  'themeVariables': {
    'actorBkg': '#21262d',
    'actorBorder': '#8b949e',
    'actorTextColor': '#c9d1d9',
    'signalColor': '#8b949e',
    'signalTextColor': '#c9d1d9',
    'labelBoxBkgColor': '#161b22',
    'labelBoxBorderColor': '#30363d',
    'labelTextSize': '13px',
    'loopByBkgColor': '#0d1117'
  }
}}%%
sequenceDiagram
    autonumber
    participant M as MainWindow
    participant UW as UpdateWorker
    participant C as StartupCoordinator
    participant PM as POTManager
    participant PW as _POTWorker

    M->>M: QTimer 500ms → _start_update_check
    M->>M: _fallback_timer 15s 기동
    M->>UW: check(check_done)
    UW-->>M: stale 목록
    M->>C: report_deps(검사완료)
    M->>UW: upgrade(upgrade_done · work_tick)
    M->>PM: ensure_ready(prewarm)
    PM->>PW: 스폰 + heartbeat 연결
    loop 수급 진행 중
        UW-->>M: work_tick → defer_fallback_timer(연장)
        PW-->>M: heartbeat → defer_fallback_timer(연장)
    end
    UW-->>C: upgrade_done
    PW-->>C: staged/ready
    C->>M: READY 1회 + ui_unlocked<br/>(deps_ok ∧ upgrade_done ∧ pot_ready)
    alt 15초 내 미개방 + 체인 실제 동작 중
        M->>M: 유예 3초 1회 후 재판정
    else 15초 내 미개방(정지)
        M->>C: force_unlock (취소 없음)
        C->>M: ready — input unlocked (fallback timeout)
    end
```

### 상태·워치독 관계 (게이트 · 큐 · 재시도)

```mermaid
%%{init: {
  'theme': 'dark',
  'themeVariables': {
    'background': 'transparent',
    'clusterBkg': '#161b22',
    'clusterBorder': '#30363d',
    'primaryColor': '#21262d',
    'primaryBorderColor': '#8b949e',
    'primaryTextColor': '#c9d1d9',
    'lineColor': '#58a6ff'
  }
}}%%
flowchart TB
    START_NODE((●)) --> STARTUP["<b>STARTUP</b><br/>기동 게이트 대기"]

    STARTUP -->|"[Gate Open] READY 1회"| IDLE["<b>IDLE</b><br/>입력 대기 · ReadyForInput"]
    STARTUP -->|"[Fallback] 15s 타임아웃 / 유예"| IDLE

    IDLE -->|"ENTER [URL 분석]"| ANALYZING["<b>ANALYZING</b><br/>스트림 · 메타 분석"]
    IDLE -->|"포맷 고르기 모드"| PICKING["<b>PICKING</b><br/>포맷 번호 선택 대기"]

    PICKING -->|"ESC / 취소"| IDLE
    PICKING -->|"포맷 번호 선택"| RUN_CHECK

    ANALYZING -->|"분석 완료 / 일반 실패"| IDLE
    ANALYZING -->|"봇 체크 감지"| POT_QUEUE["<b>POT_QUEUE</b><br/>봇 체크 우회 대기"]
    POT_QUEUE -->|"POT ready 후 1회 재분석"| ANALYZING

    IDLE -->|"ENTER [직접 다운로드]"| RUN_CHECK

    subgraph RUNNING_BOX["<b>RUNNING</b> · 세션 파이프라인"]
        direction TB
        RUN_CHECK{"게이트 판정"}
        POT_WAIT["<b>POT_WAIT</b><br/>POT 서버 기동 대기"]
        DOWNLOADING["<b>DOWNLOADING</b><br/>VOD · 라이브 스트림 수신"]
        RUN_END((◎))

        RUN_CHECK -->|"연령제한 / 게이트 영상"| POT_WAIT
        RUN_CHECK -->|"일반 공개 영상"| DOWNLOADING
        POT_WAIT -->|"120s 워치독 만료"| RUN_END
        POT_WAIT -->|"POT 바인드 완료"| DOWNLOADING
        DOWNLOADING -->|"다운로드 완료 / 중단"| RUN_END
    end

    RUN_END -->|"IDLE 복귀"| IDLE
```


```mermaid
flowchart TB
%% ══════════════════════════════════════════════════════════════════
%% ChzzkTube Architecture: Strict 1-Column Vertical Stack
%% ══════════════════════════════════════════════════════════════════

    %% [Layer 3: UI View]
    subgraph L3 ["Layer 3: View (chzzktube/ui/)"]
        MW["MainWindow<br/>(Event Loop & Master)"]
        DLG["Dialogs<br/>(Settings / F12 / Exit)"]
        LC["ConciseLogConsole<br/>(In-place Status)"]
        BRIDGE["_GuiLogBridge<br/>(QueuedConnection Boundary)"]

        MW --> DLG
        MW --> LC
        LC --> BRIDGE
        DLG ~~~ BRIDGE
    end

    %% [Layer 2: Control]
    subgraph L2 ["Layer 2: Control (chzzktube/control/)"]
        CTRL["MediaController<br/>(Session State Machine)"]
        COORD["StartupCoordinator<br/>(Sequence Gatekeeper)"]
        STATE["StartupState<br/>(RLock Protected)"]
        POTM["POTManager<br/>(Single Spawn Lifecycle)"]

        CTRL --> STATE
        CTRL --> COORD
        COORD --> POTM
        STATE ~~~ POTM
    end

    %% [Layer 1: Workers]
    subgraph L1 ["Layer 1: Workers (chzzktube/workers/)"]
        W_DL["DownloadWorker<br/>(Batch Execution)"]
        W_UPD["UpdateWorker<br/>(DEPS / Bin Upgrade)"]
        W_ANA["AnalyzeWorker<br/>(Light Manifest Extraction)"]
        W_POT["_POTWorker<br/>(Node Staging & Build)"]

        W_DL --> W_ANA
        W_UPD --> W_POT
        W_DL ~~~ W_UPD
        W_ANA ~~~ W_POT
    end

    %% [Layer 0.5: Pipeline Execution]
    subgraph L05 ["Layer 0.5: Pipeline (chzzktube/pipeline/)"]
        CTX["DownloadContext<br/>(Explicit Data Contract)"]
        TDL["target_downloader<br/>(Dispatcher: VOD/Live/Chzzk)"]
        LREC["live_recorder<br/>(ffmpeg Pipe 256KB)"]
        PEMIT["progress_emitter<br/>(0.5s Throttle Tick)"]
        FIN["finalizer<br/>(Batch Summary & failed_urls)"]

        CTX --> TDL
        TDL --> LREC
        TDL --> PEMIT
        TDL --> FIN
        LREC ~~~ PEMIT ~~~ FIN
    end

    %% [Layer 0: Core Domain]
    subgraph L0_CORE ["Layer 0: Core Domain (chzzktube/core/)"]
        CHZZK["chzzk_api.py<br/>(Clip / VOD / LIVE)"]
        OPTS["client_opts.py<br/>(Option Builder)"]
        RLOG["raw_log.raw<br/>(SSOT Bus Dispatcher)"]
        WDOG["watchdog.py<br/>(LivenessWatchdog)"]
        MEDIA["media.py<br/>(Codec Rank & Remux)"]
        HIST["log_history.py<br/>(Daily Disk Append)"]

        CHZZK --> WDOG
        OPTS --> MEDIA
        RLOG --> HIST
        CHZZK ~~~ OPTS ~~~ RLOG
        WDOG ~~~ MEDIA ~~~ HIST
    end

    %% [Layer 0: Infra & Runtime]
    subgraph L0_INFRA ["Layer 0: Infra & Runtime (chzzktube/infra/)"]
        POTP["pot_provider.py<br/>(Re-export Facade)"]
        COMP["components.py<br/>(FFmpeg Auto)"]
        POTS["pot_server.py<br/>(Server Lifecycle)"]
        UPDR["updater.py<br/>(PyPI / Wheel)"]
        NODE["node_provider.py<br/>(Node 22+ Runtime)"]
        POC["po_client.py<br/>(Pure HTTP /ping)"]

        POTP --> POTS
        POTS --> NODE
        POTS --> POC
        COMP --> UPDR
        POTP ~~~ COMP
        NODE ~~~ POC ~~~ UPDR
    end

%% ══════════════════════════════════════════════════════════════════
%% 수직 박스 고정 앵커 (계단 현상 방지: 상단 박스 바닥 -> 하단 박스 천장)
%% ══════════════════════════════════════════════════════════════════
    %% L3 바닥 -> L2 천장
    DLG ~~~ CTRL
    BRIDGE ~~~ COORD

    %% L2 바닥 -> L1 천장
    STATE ~~~ W_DL
    POTM ~~~ W_UPD

    %% L1 바닥 -> L0.5 천장
    W_ANA ~~~ CTX
    W_POT ~~~ CTX

    %% L0.5 바닥 -> L0 Core 천장
    LREC ~~~ CHZZK
    PEMIT ~~~ OPTS
    FIN ~~~ RLOG

    %% L0 Core 바닥 -> L0 Infra 천장
    MEDIA ~~~ POTP
    HIST ~~~ COMP

%% ══════════════════════════════════════════════════════════════════
%% 비즈니스 데이터 플로우 (대칭 수직 연결)
%% ══════════════════════════════════════════════════════════════════
    MW ==> |"1. User Action"| CTRL
    MW -.-> |"Startup Sync"| COORD

    CTRL ==> |"2. Spawns"| W_DL
    CTRL -.-> W_ANA
    COORD -.-> W_UPD
    POTM -.-> W_POT

    W_DL ==> |"3. Delegates"| CTX

    TDL ==> |"4. Extract & Mux"| OPTS
    TDL -.-> CHZZK

    MEDIA ==> |"5. Runtime Integration"| POTP
    MEDIA -.-> COMP
    OPTS -.-> UPDR
```
