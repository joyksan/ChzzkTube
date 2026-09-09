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
python main.py
```

- `F12`: 전체 상세 로그(F12 창) 열기
- `ESC / Enter`: URL 입력창 초기화 / 분석·다운로드 시작
- 설정: `dl_config.json`(CONFIG_DIR) — 저장 경로·포맷·쿠키·업데이트 채널 등

### 빌드

- PyInstaller `ChzzkTube.spec` 기반 onedir/onefile 빌드가 구성되어 있다.
- 환경은 `.python-version` 및 프로젝트 의존 패키지를 기준으로 맞춘다.

### PO Token 서버 (PO 우회)

- 앱은 백그라운드에서 PO Token 서버를 준비하되, 일반 공개 영상은 PO 없이도 진행된다.
- 연령 제한·멤버십·게이트 영상에서 필요한 시점에만 서버를 기동/재기동한다(lazy-on-demand).
- 서버 프로토콜/빌드는 bgutil 계열 서버 소스를 사용하며, 로컬 포트(127.0.0.1)만 사용한다.

### 주의사항

- 네트워크 접근이 본질인 도구다(yt-dlp 스트리밍, PO 서버 빌드·갱신 등).
- 로그 채널 분리 설계: raw 동작 로그는 단일 버스, 화면(F12 포함)·상세·영구 파일은 각 모듈이 필터링한다.
- 커밋 전 훅: 이 저장소는 pre-commit 훅이 활성화돼 있다. 우회 커밋이 필요하면 `deploy(no-verify)` 옵션을 사용한다.