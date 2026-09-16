## 🗺️ Mermaid 아키텍처 다이어그램 (2026-09-16 실측 — v3.6.0)

> GitHub / VS Code / Mermaid Live Editor에서 직접 렌더된다. 노드 텍스트의 특수문자는
> 코드 실물과 대조해 갱신할 것(아스키 화살표·박스도는 렌더러가 처리한다).

### 1) 전체 계층도 (L4 View → L0 Leaf, 단방향)

```mermaid
flowchart TB
    subgraph L4["L4 · View — Qt 위젯 보유"]
        direction TB
        MW["MainWindow<br/>(ui/main_window.py)<br/>진입 조립·버스 구독 2점·게이트 워치독"]
        DLG["dialogs.py<br/>6종 다이얼로그 + F12"]
        LC["log_console.py<br/>컬럼 포맷·클램프 렌더"]
        TH["theme.py<br/>QSS 단일 출처"]
    end
    subgraph L3["L3 · Control — 조정·게이트"]
        direction TB
        SC["StartupCoordinator<br/>READY 게이트 1회 발산"]
        SS["StartupState<br/>게이트 단일 진실"]
        PM["POTManager<br/>prewarm·gate 단일 스폰"]
        MC["MediaController<br/>세션 state 머신"]
    end
    subgraph L2["L2 · Service / Pipeline — plain"]
        direction TB
        PE["progress_emitter<br/>LogEvent 빌더"]
        TD["target_downloader<br/>VOD·라이브·치지직"]
        FN["finalizer · live_recorder<br/>마감·녹화"]
        UP["updater · components<br/>버전·수급"]
        PS["pot_server · node_provider<br/>bgutil 빌드·기동"]
    end
    subgraph L1["L1 · Model — 순수"]
        direction TB
        RL["raw_log<br/>단일 진입 raw()"]
        LE["log_event · log_history<br/>이벤트·파일 기록"]
        CF["config · dl_platform<br/>설정·URL 판정"]
        MD["media · chzzk_api · cookies<br/>도메인 로직"]
    end
    subgraph L0["L0 · Leaf — 진입·검증 (import 대상 아님)"]
        direction TB
        MAIN["main.py<br/>씬 런처"]
        SMK["smoke_test.py"]
        TST["tests/ · sync_mirrors.py"]
    end
    subgraph WK["QThread 워커 (결과·게이트 시그널만)"]
        direction LR
        UW["UpdateWorker"]
        AW["AnalyzeWorker"]
        DW["DownloadWorker"]
        PW["_POTWorker"]
    end

    L4 -->|report_* 호출| L3
    L3 -->|ensure_ready · spawn| WK
    WK -->|결과 시그널| L3
    L3 --> L2
    L2 --> L1
    L0 --> L4
```

### 2) 기동 시퀀스 (READY 게이트 · 15초 폴백 · 동적 워치독)

```mermaid
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
stateDiagram-v2
    [*] --> STARTUP: 창 생성
    STARTUP --> IDLE: ui_unlocked (READY 1회)
    STARTUP --> IDLE: 15초 폴백 (게이트 미개방)
    STARTUP --> IDLE: 유예 후 폴백 (체인 동작 중)
    IDLE --> PICKING: 포맷 고르기
    IDLE --> ANALYZING: ENTER 분석
    PICKING --> IDLE: 선택 완료·취소
    ANALYZING --> IDLE: 분석 성공
    ANALYZING --> POTQUEUE: 분석 실패가 봇 체크 마커
    POTQUEUE --> ANALYZING: POT ready 후 재분석 (URL당 1회)
    ANALYZING --> IDLE: 분석 실패(재시도 소진)
    IDLE --> RUNNING: 다운로드 개시
    state RUNNING {
        [*] --> POTWAIT: POT 게이트 필요시 큐잉
        POTWAIT --> [*]: POT ready → 실행
        POTWAIT --> [*]: 120초 워치독 → 트리 종료 + 큐 해제
    }
    RUNNING --> IDLE: 완료·취소
```