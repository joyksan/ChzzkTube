## 🗺️ Mermaid 아키텍처 다이어그램 (2026-09-16 실측 — v3.6.0)

> GitHub / VS Code / Mermaid Live Editor에서 직접 렌더된다. 노드 텍스트의 특수문자는
> 코드 실물과 대조해 갱신할 것(아스키 화살표·박스도는 렌더러가 처리한다).

### 1) 전체 계층도 (L0 Launcher → L4 View → L1 Model)

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

### 2) 기동 시퀀스 (READY 게이트 · 15초 폴백 · 동적 워치독)

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

### 3) 상태·워치독 관계 (게이트 · 큐 · 재시도)

```mermaid
%%{init: {
  'theme': 'dark',
  'themeVariables': {
    'stateBkg': '#21262d',
    'stateBorder': '#8b949e',
    'labelTextColor': '#c9d1d9',
    'compositeStateBkg': '#161b22',
    'compositeStateBorder': '#30363d',
    'transitionLineColor': '#58a6ff',
    'transitionLabelColor': '#c9d1d9'
  }
}}%%
stateDiagram-v2
    [*] --> STARTUP : App Launch
    
    STARTUP --> IDLE : [Gate Open] READY 1회
    STARTUP --> IDLE : [Fallback] 15s Timeout / Grace

    state IDLE {
        direction LR
        [*] --> ReadyForInput
    }

    IDLE --> ANALYZING : ENTER [URL Analysis]
    IDLE --> PICKING : Format Select Mode

    PICKING --> IDLE : Cancel / Esc
    PICKING --> RUNNING : Select Format

    ANALYZING --> IDLE : Analysis Done / Fail
    ANALYZING --> POT_QUEUE : Bot Check Detected
    POT_QUEUE --> ANALYZING : POT Server Ready (1회 재시도)

    IDLE --> RUNNING : ENTER [Direct Download]
    
    state RUNNING {
        direction TB
        [*] --> CheckGate
        CheckGate --> POT_Wait : Gated Video
        CheckGate --> Downloading : Normal Video
        POT_Wait --> Downloading : POT Bound
        POT_Wait --> [*] : 120s Timeout
        Downloading --> [*] : Complete / Abort
    }

    RUNNING --> IDLE : Finish / User Cancel
```