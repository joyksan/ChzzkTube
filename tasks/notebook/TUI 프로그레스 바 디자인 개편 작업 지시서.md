# 작업 지시서: ChzzkTube TUI 인터랙티브 개편 및 콘솔 렌더링 최적화

**문서 번호:** SPEC-2026-UI-002 (v2.0 갱신본)  
**대상 시스템:** ChzzkTube v3.12.x (PySide6 / Windows 기반)  
**작업 유형:** TUI/UX 모던화, 정보 위계 재설계, 폰트 렌더링 결함(세로줄/색번짐) 해결  
**디자인 콘셉트:** Frameless Minimalist Console & Sleek Dash & Head Indicator  

---

## 1. 개편 배경 및 목표

### 1.1 현상 및 문제점 진단
1. **폰트 서브픽셀 렌더링 결함:** 풀 블록(`█`, U+2588) 문자 사용 시 DirectWrite의 ClearType 필터링으로 인해 무지개색 세로선 및 1px 틈새가 발생함.
2. **첫 실행(포터블 수급) 공포감 유발:** 포터블 버전 특성상 필수 도구가 없는 것은 정상 수순임에도 `FAIL`(적색) 로그가 대거 출력되어 시스템 에러로 오인됨.
3. **일반 실행 시 과도한 로그 노이즈:** 매 실행마다 10줄 이상의 정상 헬스체크 및 화면을 넘어가는 긴 파일 경로(`C:\Users\...\AppData\...`)가 출력되어 실제 작업 공간(Canvas)을 낭비함.
4. **상태 피드백 부재 및 시각적 피로:** 백그라운드 준비 중 인풋 활성화 여부가 불분명하며, 상단 바의 대괄호(`[ ]`)와 파이프(`|`) 중복 사용으로 시선이 분산됨.

### 1.2 핵심 개편 목표
* **안정감 있는 온보딩 UX:** 첫 실행 시 `FAIL` 대신 `FETCH`/`SETUP` 태그를 부여하고 고정 4행에서 인플레이스(In-place) 다운로드 게이지를 갱신.
* **극도의 미니멀리즘 (Default View):** 일반 실행 시 10줄의 헬스체크를 단 한 줄의 성공 뱃지로 압축하고, 세부 파일 경로는 `F12: Full Log`로 격리.
* **모던 바 디자인:** 양 끝 괄호가 없는 프레임리스 투톤 트랙(`━`, `╸`, `┈`) 적용.
* **직관적인 인풋 인터랙션:** 런타임 준비 중에는 인풋을 비활성화하고 상태 안내 문구를 플레이스홀더에 노출.

---

## 2. 화면 상태(State)별 디자인 명세

### State 1: 첫 실행 (의존성 수급 단계)
* **UX 정책:** 
  * 실패(`FAIL`)가 아닌 단계별 프로비저닝(`FETCH`, `QUEUE`)으로 명명.
  * 다운로드 로그가 아래로 계속 밀리지 않고, 4개의 컴포넌트가 제자리에서 부드럽게 게이지를 채우도록 인플레이스 갱신.
  * 상단 인풋 필드는 딤(Dim) 처리하여 입력 잠금을 직관적으로 안내.

```text
ChzzkTube v3.12.3
Path  C:\Users\JinsanKim\Downloads\asmr    F1 Change · F2 Open · F12 Log · F3 Settings

> Initializing portable runtime environment... (ESC Cancel)
──────────────────────────────────────────────────────────────────────────────────────────
 FETCH  yt-dlp     ━━━━━━━━━━━━╸┈┈┈   72% ·  6.1 MB/s · 17.0 MB
 FETCH  ffmpeg     ━━━━━━━╸┈┈┈┈┈┈┈┈   45% ·  9.4 MB/s · 186.9 MB
 QUEUE  node       ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈    0% ·  waiting
 QUEUE  bgutil     ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈    0% ·  waiting
```

---

### State 2: 일반 실행 (의존성 완료 후 기본 화면)
* **UX 정책:** 
  * 긴 절대 경로는 콘솔 메인 뷰에서 완전히 걷어냄 (`F12 Full Log`에서만 열람).
  * 10줄의 텍스트 홍수를 **원라이너(Single-Line) 요약 뱃지** 하나로 치환.
  * 하단 콘솔 캔버스를 깨끗하게 비워두어 사용자가 다음 작업을 명확히 인지하게 유도.

```text
ChzzkTube v3.12.3
Path  C:\Users\JinsanKim\Downloads\asmr    F1 Change · F2 Open · F12 Log · F3 Settings

> URL, playlist, or channel URL...         F4 Load .txt · ESC Clear · ↵ Start
──────────────────────────────────────────────────────────────────────────────────────────
 ✔ Environment ready  (ytdlp 2026.08 · ffmpeg 7.1 · node v22 · pot active)

 
```

---

### State 3: 작업 다운로드 진행 중 (Active Task)
* **UX 정책:** 세로 구분선(파이프)을 절제하고 여백 기반으로 컬럼을 정렬하여 가독성 극대화.

```text
ChzzkTube v3.12.3
Path  C:\Users\JinsanKim\Downloads\asmr    F1 Change · F2 Open · F12 Log · F3 Settings

> https://chzzk.naver.com/video/123456...   [ESC] Abort · [F12] Detailed Log
──────────────────────────────────────────────────────────────────────────────────────────
 [19:45:10] DOWN  video_1080p   ━━━━━━━━━━━━╸┈┈┈   75% · 12.4 MB/s · ETA 00:32
 [19:45:12] MERGE audio_track   ━━━━╸┈┈┈┈┈┈┈┈┈┈┈   25% · muxing...
```

---

## 3. UI 컴포넌트 세부 규격

### 3.1 핫키 내비게이션 및 상단 바
* **Before:** `[ F1: Change ] | [ F2: Open ] | [ F12: Full Log ] | [ F3: Settings ]`
* **After:** `F1 Change · F2 Open · F12 Log · F3 Settings`
  * 대괄호와 파이프를 제거하고 미들 닷(`·`, `U+00B7`)으로 여백 분할.
  * 키 심볼(예: `F1`)은 밝은 회색(`#E5E5E5`), 액션 텍스트는 보조 회색(`#8A8A8A`) 적용.

### 3.2 상태 태그 (Tag System)

| 상태 (Status) | 태그명 | 폰트 컬러 | 시각적 의미 |
| :--- | :--- | :--- | :--- |
| **의존성 다운로드** | `FETCH` | `#00D8B4` (민트/시안) | 정상 동작 중인 수급 단계 |
| **의존성 대기** | `QUEUE` | `#707070` (딤드 그레이) | 대기 중인 큐 |
| **정상 완료** | `✔` / `OK` | `#00D8B4` (민트) | 안정적인 헬스 상태 |
| **치명적 에러** | `ERR` | `#FF5555` (소프트 레드) | 실제 네트워크 끊김, 파일 쓰기 실패 시에만 제한적 사용 |

### 3.3 프로그레스 바 글리프 사양 (Sleek Dash & Head)

* **Filled Track (`━`, U+2501):** `#E5E5E5` (볼드 수평선)
* **Indicator Head (`╸`, U+2578):** `#00D8B4` (진행 방향을 지시하는 끝단 화살머리)
* **Empty Track (`┈`, U+2508):** `#383838` (미세 점선 트랙)
* **너비:** 16칸 (모노스페이스 기준 정렬 고정)

---

## 4. 기술 구현 가이드 (PySide6)

### 4.1 DPI 배율 및 폰트 렌더러 설정 (`main.py`)
DirectWrite의 그리드 피팅 및 서브픽셀 컬러 번짐을 원천 차단합니다.

```python
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

# 1. 윈도우 배율(125%, 150%) 반올림 오차 방지
QApplication.setHighDpiScaleFactorRoundingPolicy(
    Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
)

app = QApplication(sys.argv)

# 2. 콘솔 폰트 엔진 보정
font = QFont("Cascadia Mono", 10)
font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
font.setStyleStrategy(
    QFont.StyleStrategy.NoSubpixelAntialias | QFont.StyleStrategy.PreferAntialias
)
font.setWeight(QFont.Weight.Medium)
font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.0)

app.setFont(font)
```

### 4.2 프로그레스 바 문자열 생성 모듈 (`progress_renderer.py`)

```python
def render_sleek_bar_ansi(current: float, total: float, width: int = 16) -> str:
    """Sleek Dash & Head ANSI 프로그레스 바 포맷터"""
    ratio = max(0.0, min(1.0, current / total)) if total > 0 else 0.0
    fill_count = int(round(ratio * width))
    empty_count = width - fill_count

    COLOR_FILL = "\033[38;2;229;229;229m"
    COLOR_HEAD = "\033[38;2;0;216;180m"
    COLOR_TRACK = "\033[38;2;56;56;56m"
    RESET = "\033[0m"

    if fill_count == 0:
        bar = f"{COLOR_TRACK}{'┈' * width}{RESET}"
    elif fill_count >= width:
        bar = f"{COLOR_FILL}{'━' * width}{RESET}"
    else:
        body = "━" * (fill_count - 1)
        bar = f"{COLOR_FILL}{body}{COLOR_HEAD}╸{COLOR_TRACK}{'┈' * empty_count}{RESET}"

    return bar
```

### 4.3 로그 출력 라우팅 정책 (노이즈 격리)

* **콘솔 메인 뷰 (`ConsoleWidget`):**
  * 의존성 수급 단계: 고정 4행 업데이트 (`FETCH` / `QUEUE`)
  * 초기화 완료 후: `✔ Environment ready (ytdlp 2026.08 · ffmpeg 7.1 · node v22 · pot active)` 단일 요약 행 출력 후 대기
* **상세 로그 팝업 (`F12 FullLogDialog`):**
  * 컴포넌트 실제 설치 경로 (`C:\Users\...\AppData\Local\...`)
  * 세부 소켓 바인딩 및 포트 스테이징 로그
  * 전체 HTTP 요청/응답 헤더

---

## 5. 검증 체크리스트 (QA)

| 구분 | 검증 항목 | 합격 기준 |
| :--- | :--- | :--- |
| **UX 흐름** | 첫 실행 시 공포감 배제 | `FAIL`, 적색 텍스트가 노출되지 않고 `FETCH` 및 프로그레스 바가 뜨는가? |
| **인터랙션** | 인풋 락(Lock) 명확성 | 의존성 수급 및 서버 스테이징 중 인풋 필드가 비활성화되어 있는가? |
| **정보 밀도** | 일반 실행 시 여백 확보 | 런타임 완료 후 10줄의 텍스트 대신 단 한 줄의 성공 요약만 남는가? |
| **시각적 정렬** | 글리프 폭 일치 | 0%, 50%, 100% 진행 상황에서도 프로그레스 바의 전체 문자 폭이 16자로 고정되는가? |
| **렌더링** | 서브픽셀 아티팩트 제거 | 윈도우 디스플레이 125%/150% 배율에서 선 사이에 무지개색 줄무늬가 없는가? |