## ChzzkTube

Hyper-Minimalist Modern TUI 미디어 추출기 — YouTube / 치지직(Chzzk) 영상·라이브 다운로드를 위한 개인용·비상업적 듀얼유즈 도구.

"fzf · lazygit" 감성의 모노스페이스 Flat TUI로, OS 순정 GUI 위젯 없이 콘솔만으로 모든 작업을 처리한다.

### 스택

- Python 3.12.14 (pyenv / `.python-version` 고정) + PySide6
- yt-dlp + streamlink + FFmpeg(리먹싱)
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

### PO Token 서버 (PO 우회)

- 앱은 백그라운드에서 PO Token 서버를 준비하되, 일반 공개 영상은 PO 없이도 진행된다.
- 기동 직후 prewarm으로 **디스크 스테이징만** 수행(RAM 0MB·포트 미점유), 연령 제한·멤버십·게이트 영상에서 필요한 시점에만 gate로 서버를 기동한다(lazy-on-demand).
- READY 게이트는 DEPS + 업데이트 + POT 사전 스테이징이 모두 완료된 실완료 토큰(`staged`/`ready`)으로만 개방되며, 기존 서버가 이미 응답 중이면 스폰 없이 즉시 재사용한다.
- 서버 프로토콜/빌드는 bgutil 계열 서버 소스를 사용하며, 로컬 포트(127.0.0.1)만 사용한다.
- `po_client`는 표준 라이브러리만 쓰는 L0 리프 — 서버 생존은 순수 HTTP /ping만으로 판정하고 상위 계층의 내부(락 파일 등)를 참조하지 않는다.

### 주의사항

- 네트워크 접근이 본질인 도구다(yt-dlp 스트리밍, PO 서버 빌드·갱신 등).
- 로그 설계: 모든 동작 로그는 `raw_log.raw()` 단일 버스 진입 — history·F12는 전량 수신, 메인 TUI는 발행자의 `to_tui` 선택으로 팬아웃한다.
- 스레드 설계: `raw_log`는 표준 라이브러리만 쓰는 순수 dispatcher(bounded queue)이며, GUI 갱신은 `main._GuiLogBridge`의 Qt Signal(QueuedConnection)을 통해 메인 스레드에서만 실행된다 — 워커 스레드의 위젯 직접 접근은 구조적으로 차단된다.
- 로그 규격(v3.4.0): 메인 TUI는 `[HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG`의 4컬럼 고정 폭을 사용한다. `PLATFORM`·`SPEC`은 별도 컬럼으로 출력하지 않으며, 미디어/버전 정보는 MSG 앞 태그로 보존한다.
- 설정 기본값: `download_path`, `container`, `embed_subtitles`, `audio_only`, `fast_download`, `remove_duplicates`, `auto_open_folder`, `completion_action`, `play_sound`, `max_video_res`, `pick_format`, `filename_prefix`, `filename_suffix`, `browser_cookie`, `cookie_file_path`, `yt_player_client`, `update_channel`, `auto_update_check`, `streamlink_quality`, `embed_thumbnail`, `embed_chapters`, `subtitle_langs`, `concurrent_fragments`
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
%% ChzzkTube Architecture: GitHub Optimized Vertical Stack
%% ══════════════════════════════════════════════════════════════════

    %% [Layer 3: UI View]
    subgraph L3 ["Layer 3: View (chzzktube/ui/)"]
        direction TB
        subgraph L3_CORE ["Presentation Core"]
            MW["MainWindow<br/>(Event Loop & State Sync)"]
            LC["ConciseLogConsole<br/>(In-place status & Pixel Clamp)"]
            DLG["Dialogs (Settings / F12 Verbose)"]
            MW --> LC
            MW --> DLG
        end
        BRIDGE["_GuiLogBridge<br/>(QObject QueuedConnection Boundary)"]
        BRIDGE -. "tui_signal / full_signal" .-> MW
    end

    %% [Layer 2: Control & Orchestration]
    subgraph L2 ["Layer 2: Control & Orchestration (chzzktube/control/)"]
        direction TB
        subgraph L2_ORCH ["State Machines & Lifecycle"]
            direction LR
            CTRL["MediaController<br/>(Session State)"]
            COORD["StartupCoordinator<br/>(Sequence Gates)"]
            STATE["StartupState<br/>(RLock Protected)"]
            POTM["POTManager<br/>(Single Spawn Guard)"]
        end
        COORD <--> STATE
        COORD <--> POTM
    end

    %% [Layer 1: Workers]
    subgraph L1 ["Layer 1: Workers (chzzktube/workers/)"]
        direction LR
        W_UPD["UpdateWorker<br/>(DEPS / Upgrade)"]
        W_ANA["AnalyzeWorker<br/>(Light Extraction)"]
        W_DL["DownloadWorker<br/>(Batch Execution)"]
        W_POT["_POTWorker<br/>(Staging / Build)"]
    end

    %% [Layer 0.5: Pipeline]
    subgraph L05 ["Layer 0.5: Pipeline Execution (chzzktube/pipeline/)"]
        direction TB
        CTX["DownloadContext (Pipeline Data Contract)"]
        subgraph L05_PIPE ["Execution Modules"]
            direction LR
            TDL["target_downloader<br/>(Target Dispatcher)"]
            LREC["live_recorder<br/>(Relay Pipe 256KB)"]
            PEMIT["progress_emitter<br/>(0.5s Throttle Tick)"]
            FIN["finalizer<br/>(Summary & txt)"]
        end
        CTX --> TDL
        TDL --> LREC
        TDL --> PEMIT
        CTX --> FIN
    end

    %% [Layer 0: Core Domain & Log SSOT]
    subgraph L0_CORE ["Layer 0: Core Domain & Log SSOT (chzzktube/core/)"]
        direction TB
        subgraph L0_LOG ["Unified Log Bus"]
            RLOG["raw_log.raw()<br/>(SSOT Dispatcher & Bounded Queue)"]
            HIST["log_history.py<br/>(Daily File Append)"]
            RLOG --> HIST
        end
        subgraph L0_MEDIA ["Domain & Utility Models"]
            direction LR
            MEDIA["media.py<br/>(Codec Rank)"]
            CHZZK["chzzk_api.py<br/>(Clip/VOD/LIVE)"]
            OPTS["client_opts.py<br/>(Option Builder)"]
            DLP["dl_platform.py<br/>(URL Routing)"]
            WDOG["watchdog.py<br/>(LivenessWatchdog)"]
        end
    end

    %% [Layer 0: Infra & External Runtime]
    subgraph L0_INFRA ["Layer 0: Infra & Runtime Provisioning (chzzktube/infra/)"]
        direction TB
        FACADE["pot_provider.py (Re-export Facade)"]
        subgraph L0_INFRA_LEAF ["Runtime Leaf Implementations"]
            direction LR
            POC["po_client.py<br/>(Pure HTTP /ping)"]
            POTS["pot_server.py<br/>(Lifecycle & Lock)"]
            NODE["node_provider.py<br/>(Node 22+ Runtime)"]
            COMP["components.py<br/>(FFmpeg Auto)"]
            UPDR["updater.py<br/>(PyPI / Wheel)"]
        end
        FACADE -.-> POC
        FACADE -.-> POTS
        FACADE -.-> NODE
    end
```
