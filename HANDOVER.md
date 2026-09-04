# HANDOVER.md — ChzzkTube 인수인계서

> 이 문서는 다음 담당자(사람 또는 AI 에이전트)를 위해 작성된 프로젝트 인수 문서다.
> 코드 수정 전 반드시 **§5 불변식**과 **§6 하지 말 것**을 읽을 것.
> 마지막 갱신: 전체 구조 재구성 (수정 이력 요약 압축 + 중복 제거)

---

## 1. 프로젝트 개요

- **ChzzkTube**: YouTube/치지직(Chzzk) 영상 다운로드 GUI 앱 (Windows 우선)
- **버전**: `v3.0.2 (PyQt6안정화버전)` — 정의 위치 `config._APP_VERSION`
- **스택**: Python 3.12.14 (pyenv, `.python-version` 고정) + PyQt6 + yt-dlp + streamlink + FFmpeg(리먹싱)
- **진입점**: `main.py` (`python main.py`)
- **빌드**: PyInstaller — `ChzzkTube.spec` (entry: `main.py` ✓ 수정됨)
- **설정 파일**: `dl_config.json` (CONFIG_DIR에 생성, UTF-8 / indent=4)

## 2. 실행 환경

| 항목 | 상태 |
|------|------|
| PyQt6, yt-dlp, streamlink | `uv sync`로 설치 완료 (uv.lock 잠금) |
| pyproject.toml / uv.lock | **의존성 단일 출처** — PyQt6 6.11.0 / yt-dlp 2026.8.19 / streamlink 8.5.0 / bgutil-ytdlp-pot-provider 1.3.2 고정 |
| FFmpeg | 런타임 필요 (media.py 리먹싱) |
| Node.js 22+ | PO Token 서버용 (시스템 우선, 없으면 포터블 다운로드) |
| D2Coding-Regular.ttf | BASE_DIR에 있으면 로드 (콘솔 폰트) |

## 3. 아키텍처 (4계층 · 역방향 참조 0 · 순환 import 0)

```
[View]      main(825) ─ dialogs(799) · theme(283) · log_console(327)
[Control]   controller(117)
[Worker]    downloader(1159)
[Domain]    media(196) · chzzk_api(94) · cookies(76) · config(71) · utils(65) · updater(102)
```

| 모듈 | 책임 |
|------|------|
| `main` | 진입점 + MainWindow(UI 조립·로그 출력·종료 처리). UI 전환만 담당 |
| `controller` | MediaController — 다운로드/분석 세션 state 머신, 타겟 파싱, 워커 생명주기 |
| `downloader` | AnalyzeWorker / DownloadWorker(QThread) + YtLoggerBridge |
| `dialogs` | ExitConfirm·Settings·CookieSelect·CookieViewer·ActionCountdown 5종 |
| `theme` | 색상 토큰 + QSS 상수 20종 (**QSS 단일 출처**) |
| `log_console` | ConciseLogConsole — 간결 로그 덮어쓰기 파이프라인 |
| `media` | map_res, format_bytes, codec rank, cleanup_temp_files, remux_live_to_container |
| `chzzk_api` | 치지직 클립 공개 API 분석 (yt-dlp 우회 경로) |
| `cookies` | Firefox/Chromium 쿠키 DB 추출 |
| `config` | 경로(frozen/dev), 기본값, 로드/저장 — 제로 의존 leaf |
| `utils` | clean_ansi, get_filename_template, _open_windows_explorer, parse_sec |
| `updater` | 구성요소(yt-dlp/streamlink) 버전 확인(PyPI) 및 pip 업그레이드 |

### 하위 모듈 (Worker 계층 분할)

| 모듈 | 책임 |
|------|------|
| `progress_emitter` | 로그 이벤트 포맷팅 |
| `live_recorder` | 라이브 녹화 파이프라인 (ffmpeg/streamlink) |
| `target_downloader` | 개별 URL 다운로드 분기 (VOD/라이브/치지직/Streamlink) |
| `finalizer` | 다운로드 완료 요약 로그 |
| `client_opts` | yt-dlp 옵션 주입 (쿠키, 클라이언트, PO Token, FFmpeg) |
| `speed_window` | 속도 측정 슬라이딩 윈도우 |
| `dl_platform` | URL → 플랫폼/콘텐츠 타입 감별 |
| `playlist` | YouTube 채널 URL 정규화 |

## 4. 핵심 데이터 구조

### dl_state (MediaController.state — 워커와 공유)
```python
{"running": bool, "canceled": bool, "skip": bool, "force_discard": bool, "analyzing": bool}
```

### cfg 14키 (config.default_config())
```
download_path, container("mp4"), embed_subtitles, audio_only,
fast_download(True), remove_duplicates(True), auto_open_folder(True),
completion_action("none"), play_sound(True), max_video_res("none"),
filename_prefix("none"), filename_suffix("id"),
browser_cookie("auto"), cookie_file_path("")
```

### Worker ↔ UI 시그널 계약
```
AnalyzeWorker:
    result_ready(dict)           : 분석 성공 — 스트림/포맷 정보 딕셔너리
    error_occurred(str)          : 분석 실패 — 오류 메시지
    log_full(str)                : yt-dlp 원본 로그 라인

DownloadWorker(targets, cfg, state_dict, v_sel, a_sel, is_live_hint=False, v_spec=None):
    log_concise(str, bool, bool) : (텍스트, is_status, is_error) 간결 로그
    log_full(str)                : yt-dlp 원본 로그 라인
    finished_all(int, int)       : (성공 수, 실패 수)
```

## 5. 불변식 (코드 수정 시 절대 위반 금지)

1. **state 딕셔너리 공유**: `MediaController.state`는 `DownloadWorker`에 참조 그대로 전달됨. 복사 금지.
2. **단방향 쓰기**: `canceled/skip/force_discard`는 UI 스레드만 쓰고, 워커는 읽기만. CPython GIL 하에서 원자적.
3. **시그널만 통보**: 워커 → UI 통보는 절대 state가 아니라 Qt 시그널로만. 시그널 emit은 스레드 안전(QueuedConnection).
4. **UI 위직 직접 조작 금지**: 워커에서 UI 위젯 직접 조작 절대 금지. 반드시 시그널을 통해 View에 요청.
5. **좀비 워커 패턴**: 폐기된 워커는 `_zombie_workers`에 넣고 자연 종료 시 `_reap_zombie()`로 소거. `wait()` 호출 금지.
6. **QSS 단일 출처**: 모든 스타일은 `theme.py`에서만 정의. 인라인 스타일 금지.
7. **의존성 단일 출처**: `pyproject.toml`이 유일한 의존성 정의 파일. 수동 설치 금지.

## 6. 하지 말 것 (회귀 방지)

- ❌ `state/cfg` 딕셔너리를 복사해서 워커에 넘기는 것
- ❌ `smoke_test` 통과 없이 리팩토링 커밋하는 것
- ❌ `.md` 미러를 손으로 고치는 것 (항상 `.py`가 원본)
- ❌ GUI 없는 CI 가정으로 Qt 코드를 임포트만으로 검증 끝이라 착각하는 것 — `smoke_test(offscreen)`를 돌릴 것
- ❌ 배포 시의 완벽한 포터블(Portable) 무결성을 침범하는 행위
- ❌ 앵커링 편향(Anchoring Bias) 국소 최적화(Local Optima)
- ❌ Thin Wrapper 메서드 생성 (단순 위임은 모듈 함수 직접 호출로 대체)
- ❌ `except Exception`으로 모든 예외 뭉뚱그리기 (세분화된 예외 처리 적용)
- ❌ 상태 변수 개별 초기화 (초기화 메서드로 통합)
- ❌ View에서 비즈니스 로직 수행 (Controller로 이관)

## 7. 검증 워크플로우 (수정 후 필수 3단계)

1. **py_compile**: 변경된 모듈 전부 `python -m py_compile` 통과
2. **smoke_test**: `python smoke_test.py` 통과 (offscreen 플래그로 CI 가능)
3. **기능 확인**: 실제 다운로드/분석/라이브 녹화 1회씩 정상 동작

## 8. 파일 규칙

| 카테고리 | 규칙 |
|----------|------|
| **Python** | 모든 `.py` 파일 UTF-8, LF. 입출력 명시적 `encoding="utf-8"` |
| **JSON** | `dl_config.json` UTF-8 / indent-4 |
| **Markdown** | `.md` 파일 LF 유지 |
| **바이너리** | 이미지/폰트/실행 파일은 `.gitattributes`에서 binary 지정 |
| **문서 미러** | `.py` docstrings가 원본, `.md` 미러는 자동 생성. 손수정 금지 |

## 9. 수정 히스토리 요약 (최신순, 핵심만)

### 2026-09-05 — 퍼사드 + 전략 패턴 리팩토링

| 모듈 | 변경 |
|------|------|
| `components.py` | `ensure_ffmpeg()` 퍼사드 + `_exe_suffix()`/`_ensure_ffmpeg_by_platform()` 전략 패턴 |
| `downloader.py` | Thin Wrapper 15개 삭제 → `run()`에서 직접 모듈 함수 호출. `_reset_loop_state()` 통합 |
| `target_downloader.py` | 예외 처리 5개 유형 세분화. `_emit_error_log()` 헬퍼 추가 |
| `live_recorder.py` | Thin wrapper 참조 → 직접 모듈 함수 호출 |
| `controller.py` | `on_download_finished()` 추가 (View → Controller 상태 로직 이관) |
| `.gitattributes` | EOL 정규화 (Python/Markdown → LF, 배치 → CRLF) |

### 2026-09-05 — 유튜브 라이브 URL 감지 개선

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

### 2026-09-01 — yt-dlp 2026.8.19 업그레이드 + 봇 체크 회피

| 모듈 | 변경 |
|------|------|
| `client_opts.py` | `_apply_client_opts()` 추가 (web_embedded/ios/tv 폴백) |
| `downloader.py` | AnalyzeWorker `_RETRY_CLIENTS = ["ios", "tv"]` 순차 폴백 |

---

## 10. 참고 문서

- `CLAUDE.md` — AI 에이전트용 행동 규칙
- `CHANGELOG.md` — 버전별 변경 사항
- `README.md` — 프로젝트 소개
