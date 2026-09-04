# HANDOVER.md — ChzzkTube 인수인계서

> 이 문서는 다음 담당자(사람 또는 AI 에이전트)를 위해 작성된 프로젝트 인수 문서다.
> 코드 수정 전 반드시 **§5 불변식**과 **§6 검증 워크플로우**를 읽을 것.
> 마지막 갱신: 로그 정책 개편(간결=요약 1줄) + 분석 정체(GIL 사망)·URL 클리어 잔여 로그·드래그 선택 버그 수리

---

## 1. 프로젝트 개요

- **ChzzkTube**: YouTube/치지직(Chzzk) 영상 다운로더 GUI 앱 (Windows 우선)
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
| FFmpeg | 런타임 필요 (media.py 리먹싱) |
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
| `main` | 진입점 + MainWindow(UI 조립·분석 워커 관리·로그 출력·종료 처리). UI 전환만 담당 |
| `controller` | DownloadController — 다운로드 세션 state 머신, 타겟 파싱, 워커 생명주기 |
| `downloader` | AnalyzeWorker / DownloadWorker(QThread) + YtLoggerBridge + 라이브 공통 녹화 파이프라인(`_record_live_stream`) |
| `dialogs` | ExitConfirm·Settings·CookieSelect·CookieViewer·ActionCountdown 5종 |
| `theme` | 색상 토큰 + QSS 상수 20종 (**QSS 단일 출처**) |
| `log_console` | ConciseLogConsole — 간결 로그 덮어쓰기 파이프라인 |
| `media` | map_res, format_bytes, codec rank, cleanup_temp_files, remux_live_to_container |
| `chzzk_api` | 치지직 클립 공개 API 분석 (yt-dlp 우회 경로) |
| `cookies` | Firefox/Chromium 쿠키 DB 추출 |
| `config` | 경로(frozen/dev), 기본값, 로드/저장 — 제로 의존 leaf |
| `utils` | clean_ansi, get_filename_template, _open_windows_explorer, parse_sec |
| `updater` | 구성요소(yt-dlp/streamlink) 버전 확인(PyPI) 및 pip 업그레이드 — frozen 빌드 거부 |

## 4. 핵심 데이터 구조

### dl_state (DownloadController.state — 워커와 공유)
```python
{"running": bool, "canceled": bool, "skip": bool, "force_discard": bool}
```

### cfg 14키 (config.default_config())
```
download_path, container("mp4"), embed_subtitles, audio_only,
fast_download(True), remove_duplicates(True), auto_open_folder(True),
completion_action("none"), play_sound(True), max_video_res("none"),
filename_prefix("none"), filename_suffix("id"),
browser_cookie("auto"), cookie_file_path("")
```

### Worker ↔ UI 시그널 계약 (downloader.py docstring 원문)
```
AnalyzeWorker:
    result_ready(dict)           : 분석 성공 — 스트림/포맷 정보 딕셔너리
    error_occurred(str)          : 분석 실패 — 오류 메시지
    log_full(str)                : yt-dlp 원본 로그 라인

DownloadWorker(targets, cfg, state_dict, v_sel, a_sel, is_live_hint=False, v_spec=None):
    log_concise(str, bool, bool) : (텍스트, is_status, is_error) 간결 로그
    log_full(str)                : yt-dlp 원본 로그 라인
    finished_all(int, int)       : (성공 수, 실패 수)
    (progress_update/status_update는 [1단계] 진행바 제거와 함께 유적으로 삭제됨)

    is_live_hint : 분석 결과(info.is_live)에서 온 라이브 힌트 — 단일 타겟일
                   때만 UI가 설정한다. a_sel == "integrated"면 통합 포맷을
                   '+ba' 병합 없이 단독으로 받는다.
    v_spec       : 분석 시점 선택 포맷 스펙(height/bitrate/vcodec) — 치지직
                   클립은 다운로드 시점에 API를 재호출하므로 CDN URL 문자열이
                   바뀔 수 있다. URL 매칭 실패 시 이 스펙으로 재매칭하여
                   조용한 최고품질 폴백을 막는다. (UI: _selected_video())
```
UI 프레임워크 교체 시 이 계약표만 맞추면 된다. 연결은 `controller.spawn_worker()`가 수행.

## 5. 불변식 — 절대 깨뜨리지 말 것

1. **state 딕셔너리 동일성**: `DownloadController.state`는 DownloadWorker에
   **참조 그대로** 전달되어 워커 스레드와 공유된다. 복사본을 넘기면 중단/건너뛰기가 죽는다.
2. **`MainWindow.dl_state` 프로퍼티**: `ctrl.state`의 읽기 전용 별칭.
   `smoke_test.py`가 이 경로로 접근한다. 제거 금지.
3. **QSS 단일 출처**: 새 스타일은 `theme.py`에 추가. 위젯에 인라인 setStyleSheet 난립 금지
   (예외: 동적 값 치환은 기존 패턴 `.replace()` 참조).
4. **미러 동기화**: `.py` 수정 후 반드시 `python sync_mirrors.py`.
5. **yt-dlp 라이브 HLS = FFmpegFD 강제**: yt-dlp는 라이브 m3u8을
   external_downloader 지정과 무관하게 ffmpeg 외부 다운로더로 돌린다
   (downloader 선택기의 is_live 분기 — 네이티브 HlsFD는 라이브를 거부).
   이때 progress 훅이 아예 호출되지 않아 후속 로그 0·취소 불가가 된다.
   그래서 유튜브 라이브는 yt-dlp로 포맷 URL만 추출하고 실제 수신은
   `_record_live_stream` 자체 파이프라인(자식 프로세스+감시 루프)이
   담당한다. 이 구조를 yt-dlp in-process 다운로드로 되돌리면 로그와
   취소가 다시 깨진다.
6. **a_sel == "integrated" 신호**: 통합 포맷(비디오+오디오 포함) 선택 시
   UI가 오디오 콤보를 '비디오 스트림에 통합됨'으로 동기화하고, 워커는
   이 값을 보고 `포맷+ba` 병합을 생략한다 (단독 포맷 다운로드).
   미러(.md)는 백업 겸 복구 수단으로 실제 사용된 이력 있음 (§8).
5. **log_concise의 is_status 의미론**: True면 이전 상태 줄을 덮어쓴다(애니메이션).
   False로 한 번 찍히면 히스토리 확정. 이 파이프라인은 log_console 내부에 캡슐화됨.
6. **인코딩**: 모든 파일 입출력 UTF-8 명시. Windows 콘솔 출력은
   `PYTHONIOENCODING=utf-8` 권장.
7. **AnalyzeWorker는 아직 MainWindow 소속**이다 (컨트롤러 미이관 — 의도된 남은 과제).

## 6. 검증 워크플로우 (수정 후 필수 3단계)

```
① uv run python -m py_compile main.py downloader.py dialogs.py utils.py \
   config.py media.py cookies.py chzzk_api.py theme.py log_console.py controller.py \
   bump_version.py sync_mirrors.py updater.py        # ALL = 0
② uv run python smoke_test.py              # headless(Qt offscreen) 실구동 [PASS], exit 0
③ uv run python sync_mirrors.py            # 누락 0 확인
```
> macOS 검증 환경: `uv run` 사용 (Python 3.12.14, `.python-version` 고정).
> 의존성은 `pyproject.toml` + `uv.lock` 단일 출처 (2026-09-02 기준 uv 전환 완료, 스모크 PASS).
> Windows 빌드: `uv sync --group build` → `uv run pyinstaller ChzzkTube.spec`.
smoke_test가 검증하는 것: 전 모듈 import, config 로드, MainWindow 실제 생성,
SettingsDialog 실생성(콤보 초기화·파일명 프리뷰), DownloadWorker 시그널/메서드 계약,
간결 로그 append 반영.
임시 스크립트(`refactor_*.py`, `_t_*.py` 등)는 작업 후 삭제하는 것이 관례.

## 7. 파일 규칙

- `.md` 파일들(`main.md`, `controller.md` 등)은 **동일 이름 .py의 바이트 단위 미러**다.
  수동 편집 대상이 아니며 `sync_mirrors.py --check`로 최신성 확인.
- `versions/` 는 과거 버전 스냅샷 보관함 (git 미추적). 히스토리 참고용, 빌드 불필요.
- 행 종결자: 일부 파일 CRLF→LF 통일된 이력 있음. 커밋 노이즈 방지엔
  `.gitattributes`에 `*.py text eol=lf` 추가 권장 (미작업).

## 8. 최근 수정 이력 요약 (회귀 방지용)

리팩토링 세션에서 구조 개편과 함께 아래 버그들이 수정되었다. 재발 징후 발견 시 이력 확인:

| 버그 | 수정 |
|------|------|
| utils.py `import glob` 누락 → Firefox 쿠키 경로 NameError | glob은 cookies.py로 이관되어 정상 import됨 |
| `remux_ts_to_mp4` 미정의 호출 3곳 | remux_live_to_container / remux_stream로 교체 |
| hook 내 미정의 변수 `is_live_stream` + loop 밖 break | `info_dict.is_live` 조회 + raise로 교체 |
| spec의 존재하지 않는 `dl.py` 참조 | `main.py`로 수정 |
| bump_version.py except 들여쓰기 8칸 | 4칸 정정 |
| 전부 실패 시 `success_cnt` UnboundLocalError | `_finalize()` 선두에서 일괄 계산 |
| failed_urls.txt 이중 기록 블록 | 단일화 |
| QSS 3중복 산재 | theme.py 통합 |

구조 개편 순서: config 분리 → media/cookies/chzzk_api 추출 → run() 분해(506→33줄)
→ theme.py → init_ui 빌더화 → log_console 추출 → DownloadController 추출(toggle_download 75→38줄).

### 로그 폴리시 패스 (v3.0.2, 5점 일괄 + 버그 2건)

| 항목 | 내용 |
|------|------|
| 틱/마감 고정폭 | 라이브 틱·종료 줄의 용량 `rjust(9)` / 속도 `rjust(11)` — 덮어쓰기 지터 제거 |
| 색 위계 | theme.py에 `LOG_COLOR_{SUCCESS,ERROR,INFO,STRUCT,VALUE}` 신설. log_console `_line_segments()`가 한 줄을 (텍스트,색) 세그먼트로 분해해 append — 구조(글리프·라벨)=딤그레이 / 값=화이트 / `[v]`=그린 / 에러=레드 |
| 심볼 문법 | `[!]`은 빨강 에러 전용. 초록 병합 진행·건너뜀 줄은 `[~]`로 전환 (downloader 2곳) |
| 실패 사유 가지 | failed_targets가 `(url, 사유)` 튜플로 변경(3개 append 지점). _finalize에서 ` ├─ 대상` + ` └─ 실패 사유:` 로 출력 — 플립 엔진과 자연 결합 |
| 동적 예산 | `update_tree_budget(text_edit)` — 뷰포트 폭÷글자폭으로 TREE_TOTAL_WIDTH 갱신(40~100 클램프). init_ui 직후 + resizeEvent에서 호출 |
| 버전 정화 | config._APP_VERSION에서 "(PyQt6안정화버전)" 제거 → "v3.0.2". bump_version의 FILE_PATH를 main.py→config.py로 수정 (APP_VERSION 이동 추격) |

주의: `_line_segments`는 log_console.append의 색상 경로다. 새 심볼을 추가하면
여기 분기(`[v]`/`[+][~]`/트리 글리프)도 함께 손봐야 의도한 색이 나온다.

### 로그 통일 패스 (v3.0.2, 유튜브 라이브/VOD/중단 로그)

| 항목 | 내용 |
|------|------|
| 유튜브 라이브 파이프라인 | `_download_youtube_live` 신설 — yt-dlp로 통합 포맷 URL만 추출 후 ffmpeg 자식 프로세스로 `_record_live_stream` 공용 녹화 (치지직과 동일: 킬 가능·부분 저장·실시간 틱) |
| 라이브 공용화 | 치지직 라이브 분기도 `_base_info_opts`/`_prepare_live_paths`/`_record_live_stream`로 분해. 두 라이브 모두 `[+] 라이브 녹화 시작`(제목/화질 트리) 헤더로 통일 |
| VOD 메타데이터 헤더 | hook 최초 1회 `[+] 비디오 다운로드 시작`(제목/화질·ID/길이/예상 용량) 트리 — 기존 'ID·해상도 한 줄' 로그 대체. audio_only는 `[+] 오디오 다운로드 시작` |
| VOD 진행 틱 | hook 0.5초 스로틀 `[+] 다운로드 중 └─ 진행/속도/용량` (라이브 틱과 동일 규격, progress_update도 emit — VOD 진행바가 이제 움직임) |
| 중단 로그 분리 | log_console `_remove_status_blocks` — 상태 블록 n개를 '빈 홈 블록 1개'로 정리해 직전 여백 보존. 기존 n회 병합 방식은 여백을 먹어 중단 로그와 다음 작업 로그가 붙었다 |
| 통합 포맷 동기화 | v_list에 acodec 추가. 비디오 콤보에서 통합 포맷 선택 시 오디오 콤보가 '비디오 스트림에 통합됨 (CODEC)'으로 동기화 → a_sel='integrated' |
| 메타 배지 실스펙화 | 하드코딩 '1080 \| AV01 \| OPUS (예상)' → 선택 포맷의 실제 해상도/코덱 표기 (media.short_codec 신설) |
| 배치 헤더 버그 | `_meta_logged`/`_last_tick_t`를 run() 루프에서 타겟마다 리셋 — 배치 다운로드 2번째 타겟부터 헤더가 누락되던 버그 수정 (구 `_video_logged`는 세션 내 1회만 찍힘) |
| 쿠키 헬퍼 | `_apply_cookie_opts` 모듈 함수로 4곳 중복 제거 |
| requirements.txt | 생성 (4개 패키지 버전 고정 + FFmpeg 외부 의존 주석) |

### 구성요소 자동 업데이트 + 분석 블록 철회 (v3.0.2)

| 항목 | 내용 |
|------|------|
| 자동 업데이트 확인 | 기동 2초 후 `UpdateWorker(upgrade=False)` 비동기 1회 — PyPI JSON으로 최신 버전 조회. 최신이면 준비완료 줄 '다음 줄'에 `[v] 구성요소 최신 (버전)` 출력(`insert_after_ready`, 인사줄이 밀렸으면 `[v]` 일반 로그 폴백), 구버전이면 `upgrade=True` 워커로 pip 자동 진행(진행/결과는 간결 로그) |
| 수동 업데이트 | (제거됨) 설정창 수동 실행 영역은 '자동 확인+자동 설치' 전환으로 삭제 — UpdateWorker와 pip 서브프로세스(600s 타임아웃)는 자동 경로가 그대로 사용 |
| frozen 빌드 | `updater.upgrade_packages`가 `sys.frozen` 감지 시 거부(포터블은 재배포판 교체 안내) |
| 버전 비교 | 문자열 비교 금지 — `_ver_tuple` 수치 비교('2026.8.19' vs '2026.08.19' 오탐 방지) |
| 분석 블록 철회 | `stop_analysis_anim`이 마지막 줄 원문을 추적(`_analysis_last_line`). 링크를 지우거나 새 분석 시작 시 `_discard_analysis_result()`가 `console.remove_last_blocks`로 블록을 흔적 없이 제거 — 이전 분석 가지에 새 로그가 붙는 버그 수정 |
| 철회 안전장치 | 블록이 마지막 콘텐츠가 아니면(다운로드 로그가 뒤에 이어졌으면) 히스토리 보존. `remove_last_blocks`는 문서 첫 블록(초기 안내문) 보존 |
| 자동 배지 | '최고 품질 자동 선택'일 때 배지가 빈 채로 남지 않게 정렬 선두 포맷 스펙 + '(자동)' 표기. 오디오 코덱도 명시 선택 > 선두 순으로 실제 값 표시 |

### 설정창 개편 (v3.0.2 — 찌그러짐 수정 + UX 점검 + 라이브 적용)

| 항목 | 내용 |
|------|------|
| 찌그러짐 원인 | `setFixedSize(460, 550)` 고정인데 업데이트 박스 추가로 콘텐츠 초과 — 쿠키 버튼 3종과 업데이트 박스가 잘려 접근 불가였음 |
| 구조 해결 | 콘텐츠를 `QScrollArea`(widgetResizable, 프레임 없음, 미니 스크롤바) 안으로 — 섹션이 늘어나도 잘리지 않는 안전망. 버튼 바 제거 후 크기 480×640 |
| 쿠키 박스 | 현재 쿠키 소스 상태 라벨 신설('현재: 자동 (브라우저 탐색)' 등 — 보기를 눌러야 알던 간접성 제거). 버튼 3종 균등 폭 + 공통 `_ghost_btn` 헬퍼 |
| 라이브 적용 전환 | 히토미 다운로더 방식 — [취소]/[완료] 버튼 폐지. 모든 컨트롤 시그널 → `_apply_change(key, value)` → 공유 cfg 갱신 + `save_cfg()` 즉시 저장. deep copy 제거(`self.cfg = parent.cfg`), `accept_settings`/`cancel_settings`/`saved`/`_cancelled` 소멸. 초기 주입 중 오발 방지는 `_loading` 플래그 가드. 하단 안내 라벨('변경 사항은 즉시 적용·저장됩니다')은 삭제 — 라이브 적용이 기본 동작이라 군더더기. 닫기(X/Esc)는 그냥 닫기 — closeEvent 할 일 없음 |
| 라이브 적용 안전성 | 실행 중에도 체크박스·콤보 변경 허용 — 공유 cfg 즉시 반영, 워커가 cfg를 읽는 시점(다음 타겟 시작)부터 새 값 적용이라 진행 중 작업은 시작 당시 값으로 유지. audio_only 토글은 `parent_win.update_ui_state()` 즉시 호출로 메인 창 스트림 콤보 잠금까지 동기(running 잠금 우선). 쿠키 버튼만 `is_running` 잠금 유지(안전 경계). 트레이드오프: 되돌리기 부재 — 저위험 옵션 스테이크라 설계 선택 |
| QSS 정리 | 섹션 타이틀/상태 라벨/고스트 버튼/스크롤바 스타일을 theme.py로 이관(`DLG_*`, `SETTINGS_SCROLL_QSS`) — 인라인 QSS 중복 제거, 단일 출처 준수 |
| 섹션 헤더 | 체크박스 그룹에 '다운로드 옵션' 타이틀 추가 — 스캔성 향상 |

### 자동랩 침범 버그 (v3.0.2 핫픽스)

증상: 좁은 창에서 URL/파일명 줄바꿈 시 `│` 줄기 없는 텍스트가 왼쪽에 침범하고,
연속 줄 뒤에서 `└─→├─` 승격이 누락됨.

| 원인 | 수정 |
|------|------|
| te_concise가 기본 WidgetWidth 랩 → 예산 초과 줄을 QTextEdit이 임의로 접어 줄기 없는 줄 생성 | ConciseLogConsole.__init__에서 `setLineWrapMode(NoWrap)` — 줄바꿈은 format_tree_item의 예산 wrap이 유일 |
| 예산이 스플리터 조작을 반영 못 함 — MainWindow.resizeEvent는 콘솔 패널 폭 변화에 호출 안 됨 | `ConciseLogConsole._sync_budget()` — append 직전 (뷰포트 폭, 글자 폭) 캐시 비교 후 변경 시에만 재계산 |
| `_flip_trailing_branch`가 연속 블록을 `startswith("  ")`(공백 2개)로만 수집 → `├─` 항목의 `" │"` 연속 줄에서 수집 실패, 승격 스킵 | 수집 조건을 `"  "` OR `" │"`로 확장, 헤더 탐색에 64블록 상한. `├─` 헤더를 만나면 줄기 정리만 수행 |

부작용 수용: NoWrap이라 화면보다 긴 줄은 가로 스크롤이 생길 수 있으나,
예산 동기화로 대부분 수납된다. 침범(문법 파괴)보다는 낫다.

### 5개 이슈 일괄 수정 (v3.0.2 — 콜론 흐려짐·자동 업그레이드·가로폭·바닥 여백·잠금 해제)

| 항목 | 내용 |
|------|------|
| 제목 콜론 흐려짐 | `_line_segments`가 wrap 연속 줄(`' │'`)도 partition 경로로 태워 값 내부 ': ' 앞부분을 STRUCT 딤색으로 칠함 → 헤더 가지(' ├'/' └')만 분할하고 연속 줄(' │'/들여쓰기)은 stem 2칸만 딤+값 전체 화이트 |
| 인사줄 병기 | `ConciseLogConsole.amend_ready_line(text)` — '준비 완료.' 블록을 찾아 상태 꼬리 삽입. setHtml trailing `<br>`의 U+2028을 건너뛰고 '본문 끝'에 붙여야 같은 줄이 됨(EndOfBlock은 구분자 뒤 = 다음 줄). append를 우회한 유일한 직접 삽입 경로라 예산 관리도 자체 수행 — 진입 시 `_sync_budget()`(기동 직후엔 append가 없어 TREE_TOTAL_WIDTH가 init 시점 과대값으로 남아 첫 청크가 실제 폭을 넘었다), 초과분은 줄기 없는 연속 줄 문법(STEMLESS_CONT_WIDTH 공백)으로 접어 NoWrap 가로 침범 방지, 삽입 후 가로 스크롤 원점 복귀. 인사줄이 밀려났으면 False 반환 → 호출부 일반 로그 폴백. **(→ 이후 `insert_after_ready`(다음 줄 삽입)로 대체 — '클립 통합 동기화 + 인사줄 다음 줄 출력' 섹션 참조)** |
| 자동 업그레이드 전환 | `_on_update_check_done` — stale 있으면 frozen 검사 후 `UpdateWorker(upgrade=True)` 기동(line→간결 로그 중계, upgrade_done→`_on_auto_upgrade_done` 로그 통보, 모달 없음). 설정창 `run_component_update`에 parent_win 워커 isRunning 가드 추가(기동 자동 업그레이드와 수동 업데이트의 이중 pip 방지) |
| 가로폭 초과 | `log_console._flow_lines` — 비트리 일반 라인(pip 출력 등)만 TREE_TOTAL_WIDTH 예산 wrap 강제(공백 없는 초장식 토큰도 강제 분할). 예산 보정 -16→-36px(document margin 8×2 + QSS 좌우 패딩 10×2). 상태 블록 카운트(`last_status_block_count`)는 wrap 포함 실삽입 블록 수로 기록 — 덮어쓰기 소거 정합 유지 |
| 바닥 여백 | QSS padding-bottom(50px)만으론 마지막 줄이 바닥에 붙어 보임 → `TAIL_PADDING_BLOCKS=2` 빈 블록 상시 유지(`_strip_tail_padding`/`_add_tail_padding`). append·add_task_separator·remove_last_blocks 모두 strip→삽입→re-fill 순서. 분석 철회 비교는 `last_content_block_text`(패딩 건너뛰기+U+2028 정규화) 사용 |
| 검증 | `_t5.py` 15케이스 오프스크린 전체 통과 — A순수 함수 / B콘솔 블록 관리 / C인사줄 병기 / D실행 중 설정창 / E자동 업데이트(FakeWorker 주입, 네트워크·pip 미실행) |

주의: QTextEdit setHtml의 trailing `<br>`은 새 블록이 아니라 같은 블록 안
U+2028 문자로 남는다. 문서 끝 텍스트 비교 시 `\u2028` 정규화 필수.

### kv 콜론 정렬 통일 + pip 중계 침범 수정 + 수동 업데이트 제거 (v3.0.2)

| 항목 | 내용 |
|------|------|
| kv 콜론 정렬 원칙 | `log_console.format_kv_line(symbol, label, value)` — 심볼 3글자+공백이 트리 'branch+공백'과 동일 폭이라 라벨을 TREE_LABEL_WIDTH(9)에 패딩하면 콜론이 모든 트리 가지와 세로 일치. downloader 6곳(건너뜀/중단됨/접근 오류/쿠키 오류/오류 발생/현재 항목 건너뜀→건너뜀) + main 4곳(경로 변경/업데이트 3종) 적용. 라벨이 폭을 초과하면 콜론이 밀리므로 kv 라벨은 전각 4자 이하로 축약('파일 접근 오류'→'접근 오류', '구성요소 업데이트 있음'→'업데이트' 등) |
| kv 긴 값 wrap | 값이 예산을 넘으면 연속 줄을 '콜론 열 아래 공백'으로 접어 트리의 줄기 없는 연속 줄과 동일 문법으로 만든다 — `_flow_lines`가 그 공백 나열(STEMLESS_CONT_WIDTH=TREE_LABEL_WIDTH+6)을 보존해 2차 wrap이 없고 세로 정렬 유지 |
| pip 중계 침범 원인 | UpdateWorker._do_upgrade가 `f"    {l.strip()}"`(4칸 들여쓰기)로 중계 → _flow_lines의 '  ' 프리픽스 판별이 트리 연속 줄로 오판해 wrap 스킵 → 가로 스크롤 발생. 중계에서 들여쓰기 제거 + _flow_lines의 트리 판별을 '줄기 글리프' 또는 '정확히 STEMLESS_CONT_WIDTH칸 공백'으로 강화(2칸/4칸 들여쓰기 텍스트는 전부 wrap 대상) |
| 수동 업데이트 제거 | 설정창 '구성요소 업데이트' 박스(UI + 메서드 5개: _installed_summary/check_component_updates/_on_check_done/run_component_update/_on_upgrade_done) 삭제 — 자동 확인+자동 설치로 대체. UpdateWorker는 main 자동 경로가 사용하므로 유지. pip 중계 summary도 kv 값부에 맞게 재구성('완료 — 적용에는 앱 재시작이 필요합니다' / '실패 (exit code n)') |
| 검증 | `_t6.py` 7케이스 오프스크린 전체 통과 — kv 콜론 열 일치(트리 3종+kv 7종)/들여쓰기 wrap/트리 연속 줄 보존(format_target_url 전 줄)/kv 긴 값 연속 줄 정렬/콘솔 반영/수동 영역 제거/중계 무들여쓰기 |

### 치지직 클립 전면 수리 (v3.0.2 — 쿠키 회귀·로그 중복·제목·fail-fast)

| 항목 | 내용 |
|------|------|
| **근본 원인 (다운로드 실패)** | cookies.py가 `{도메인: {이름: 값}}` 중첩 구조로 바뀌었는데 chzzk_api.py는 구 flat 가정(`"; ".join(f"{k}={v}")`) 그대로 → Cookie 헤더에 딕셔너리 repr → API 인증 실패 → 제목=ID 폴백 + formats 0개 → dl_target=None → 클립 원본 URL이 yt-dlp generic으로 → "Unsupported URL". naver/chzzk 도메인만 평탄화해 수정. **실측으로 검증**: 스크린샷의 클립에서 실제 제목·날짜·720P H.264 CDN URL 반환 |
| 로그 중복/철회 잔존 | AnalyzeWorker의 `[v] 치지직 클립 분석 완료` 별도 emit 삭제 — UI의 `[+] 미디어 스트림 분석 완료`와 이중 출력이었고, 별도 블록이라 분석 철회(_discard_analysis_result)에서도 안 지워짐 |
| 분석 줄 제목 통합 | stop_analysis_anim이 `info.title`를 `[+] 미디어 스트림 분석 완료 (…개수…) — 제목` 형태로 부착(클립·VOD 공통). 길면 기존 예산 wrap이 처리 |
| 분석 단계 fail-fast | 클립 formats가 비면 error_occurred로 분석 실패 처리('[X] …로그인 쿠키 확인') — 빈 성공으로 다운로드 버튼을 활성화하지 않음 |
| 다운로드 단계 fail-fast | `_download_target` 클립 분기에서 formats 비면 `format_kv_line('[!]','클립 오류',…)` + failed_targets 기록 후 return — generic 추출기 낙방 원천 차단 |

### 클립 통합 동기화 + 인사줄 다음 줄 출력 (v3.0.2)

| 항목 | 내용 |
|------|------|
| qfluentwidgets 의존 제거 | `ui_components.py`/`ui_components.md` 삭제(26모듈 체제) — 유일한 qfluentwidgets 소비점이던 `CustomComboBox`를 dialogs.py로 이동+**표준 QComboBox 기반** 재작성(addItem(text, userData, icon) 계약 유지). SettingsDialog QSS에 QComboBox 다크 규칙(입력·드롭다운 뷰) 추가. requirements.txt에서 PyQt6-Fluent-Widgets 제거, venv uninstall(Fluent+Frameless) 후 스모크·다이얼로그 생성 통과로 증명 |
| SettingsDialog 잠복 결함 2건 수리 | ①init_ui에서 `QGroupBox` 미import — [TUI 패널 일체화] 패치 시점부터 잠복(스모크가 다이얼로그를 생성하지 않아 미검출) ②파일명 섹션 `format__flay` 오타 3곳(선언은 `_flay`) — 원 의도(QVBox 라벨 위 + QHBox 콤보줄 아래)대로 수리. 재발 방지: smoke_test에 SettingsDialog 실생성 커버 영구 추가 |
| 종료 방치 로그화 | closeEvent — wait 타임아웃 후에도 미종료인 워커(다운로드/좀비 분석/POT/업데이트)를 `log_history` WARN으로 기록. terminate 금지 원칙은 유지, "방치했음"이 관측 가능해짐 |
| facade 잔재 제거(가독성 최종) | downloader의 위임 wrapper 4종(`normalize_youtube_channel_url`/`_apply_client_opts`/`_apply_cookie_opts`/`_dedupe_by_label`) 제거 — 하위 모듈 직접 import(`as _impl` 별칭 import 소멸), 무의미해진 SpeedWindow 재노출·[모듈 평면화] 주석 삭제. main의 `TUI_STYLE = theme.TUI_STYLE` 별칭 제거(theme 단일 출처 직접 사용). DownloadWorker의 thin wrapper는 분할 모듈 위임 계약이라 유지 |
| 중복·죽은 코드 제거(P1~P3) | `_dl_spec` 이중 정의 → progress_emitter 단일 출처로 통합, downloader의 `_dl_platform`/`detect_content_type` wrapper 제거(하위 모듈 직접 import로). **`format_desc.py` 모듈 전체 삭제**(재노출 체인 외 호출 0건) + 미러 목록 제거(27모듈 체제). 레거시 별칭 `le_url`/`concise_log_text_edit` 제거 → `url_input`/`te_concise` 단일 명명(24곳 교체). 만료 주석 10곳 현행화(`[1단계]`/`[10번]`/`[수정사항 3]` 표기·'이전: cb_video' 참조 제거, '통치하게' 어투 교정) |
| 침묵 실패 증거화 | chzzk_api 3곳(detail/play-info/VOD)·cookies DB 읽기 실패는 흡수 유지 + `log_history` WARN 기록 — '쿠키 있는데 401'류 증상의 추적 단서 확보. `media.remux_stream`(실패해도 원본 ts 삭제하는 미사용 위험 유적, 호출 0건) 삭제, `remux_live_to_container` 실패 print → log_history ERROR(windowed 빌드 print 소멸 대응), downloader 죽은 import(remux_stream/remux_live_to_container) 정리 |
| 유적 정리(죽은 시그널·임시코드) | `DownloadWorker.progress_update/status_update` 전부 제거(정의·connect·emit 5곳·no-op 슬롯 — [1단계] 진행바 제거 잔재), `AnalyzeWorker.log_concise`(정의만 존재) 제거, `stop_download`(F6 유적)·`_reset_stream_ui`/`_all_integrated`(읽는 곳 0)·`_audio_spec` 별칭 제거. `cleanup.py` → `media.cleanup_temp_files` 통합(.f코드 조각 정규식 로직 승격) 후 cleanup.py/md·fix_console.py·out/err.txt 삭제. **[스레드 경계]** closeEvent에 러닝 QThread 회수 wait 추가(좀비/POT/업데이트 워커 — "QThread: Destroyed" 종료 크래시 방지), DownloadController 계약에 단방향 플래그·QueuedConnection 명세 |
| 클립 오디오 콤보 통합 | `update_stream_dropdowns`가 `_all_integrated`(v_list 전체가 acodec 보유 — 치지직 클립·라이브 HLS)로 판정되면 `on_video_stream_changed`로 오디오 콤보를 '비디오 스트림에 통합됨 (CODEC)' 단일 항목(userData='integrated')으로 재구성. 혼합 소스(유튜브 VOD)는 통합 포맷 명시 선택 시에만 동기화(기존 동작 유지). 배지도 '720p \| H264 \| AAC (통합)'로 표기 |
| 클립 API 필드 보강 | chzzk_api — height는 encodingOption.height 직접 사용(name 정규식은 IGNORECASE 폴백, '720P' 대문자 P 대응), bitrate는 rmcnmv v2.0이 이미 kbps 단위라 /1000 금지(구버전 '720p \| 1kbps' 라벨의 원인), acodec='AAC' 명시(클립은 오디오 내장 단일 스트림) → 'None \| H264 (예상)' 배지도 실스펙으로 수정 |
| a_sel='integrated' 내성 | 클립 다운로드 경로는 v_sel(CDN URL) + v_spec 재매칭 기반이라 a_sel을 참조하지 않음 — 통합 동기화와 무관하게 안전. 유튜브 VOD에서는 a_sel='integrated'가 통합 포맷 단독 다운로드 신호('+ba' 병합 금지) |
| 인사줄 다음 줄 출력 | `ConciseLogConsole.insert_after_ready(text)` — amend_ready_line(같은 줄 병기) 폐기. '준비 완료.' 블록 바로 다음에 새 블록으로 삽입. append 우회 경로라 `_sync_budget()` 직접 호출 + 초과분은 줄기 없는 연속 줄(STEMLESS_CONT_WIDTH 공백)로 접음 + 삽입 후 가로 스크롤 원점 복귀. 인사줄이 밀렸으면 False 반환 → 호출부 `[v]` 일반 로그 폴백 |
| 업데이트 로그 부착 검토 | 업데이트 진행(`[~] 업데이트`)/결과(`[v]`·`[!] 업데이트`) kv는 전부 append 경로 — 최신 로그 블록과 합체 없음을 블록 단위 검증으로 확인. 주의: 비트리 flow 라인의 wrap 연속 줄은 열 0(심볼 없는 접힌 줄)으로도 생김 — 블록 탐색 시 공백 나열만 건너뛰면 오판한다 |
| 검증 | `_t10.py` 17케이스 전체 통과 — API 필드 4종(실네트워크)/map_res(None) 배지/클립·VOD 콤보 동기화 3종/insert_after_ready 다음 줄+원본 보존/업데이트 로그 블록 분리 3종/전체 라인 예산 이내. compile 16모듈 + smoke PASS + 미러 변경 4/누락 0 |

### 로그 헤더 개편 + 라벨 저스티파이 + 완료 여백 (v3.0.2)

| 항목 | 내용 |
|------|------|
| 라벨 그리드 9→14 | '비디오 스트림'/'오디오 스트림'(13칸) 라벨 신설에 맞춰 TREE_LABEL_WIDTH=14. STEMLESS_CONT_WIDTH·kv 접기 폭은 파생값이라 자동 추종 |
| 글자 사이 띄어쓰기 | `_pad_label(label, width)` — 짧은 라벨의 패딩을 글자 사이에 균등 분배('대          상')해 라벨~콜론 사이 공백 구멍을 제거. 글자 1개 또는 패딩<간격 수면 뒤 공백 폴백('비디오 스트림 '). format_tree_item·format_kv_line 공통 — 콜론 열은 표시 폭 기준 불변. 주의: 전각 라벨은 문자 수≠표시 폭이라 정렬 검증은 display_width 기준으로 (문자열 index 비교는 오판) |
| 헤더 라벨 개명 | '화질'→'비디오 스트림', '음질'→'오디오 스트림' — VOD/라이브/클립 전 헤더 공통 |
| 오디오 스트림 가지 신설 | VOD 헤더에 'OPUS (ID: 251)' 형태 추가. 병합 다운로드의 훅 info_dict는 yt-dlp가 requested_formats를 del하므로 오디오 포맷 필드가 없다 — UI가 `_audio_stream_desc()`로 계산해 spawn_worker(audio_desc=…)로 전달(명시 선택>자동 선두, 통합은 '(통합)', 분석 없는 배치는 '자동 (병합)'). 라이브는 info.acodec으로 '(통합)' |
| 클립 헤더 자체 조판 | `_emit_clip_header(ch_info, fmt)` 신설 — CDN info_dict 기반 훅 헤더는 제목=rmcnmv UUID·화질 '?p \| ? (ID: mp4)'이므로 호출부가 `_meta_logged=True`로 억제하고 API 결과(실제 제목/생성일/선택 포맷 스펙)로 직접 조판. 선택 폴백 시 selected_fmt도 formats[0]으로 확정(기존엔 URL만 대입) |
| 완료 로그 여백 보증 | '[v] 다운로드 작업 완료 !' 다음 한 칸 — add_task_separator가 `_pending_blank` 플래그를 세우고, 다음 append의 `_strip_tail_padding(keep_one=True)`이 빈 블록을 전부 걷은 뒤 내용 바로 뒤 1개를 재삽입. 보증 없으면 기존대로 인접. (초기 구현의 blockCount()==2 조건은 문서 앞쪽에 내용이 있으면 발동하지 않는 함정 — strip 후 재삽입으로 해결) |
| 분석 줄 제목 철회 | stop_analysis_anim의 제목 부착 제거 — '[+] 미디어 스트림 분석 완료 (개수)' + 대상 가지만 출력. 제목은 다운로드 헤더의 제목 가지가 담당(클립은 이제 실제 제목) |
| 구성요소 최신 간결화 | '[v] 구성요소 최신 (yt-dlp …, streamlink …)' → '[v] 구성요소 최신' — 버전 나열이 wrap을 유발해 제거. 폴백 로그도 동일 문구. main의 미사용 updater import 제거 |
| 검증 | `_t11.py` 30케이스 전체 통과 — 저스티파이 6·콜론 열 2·헤더 4종 13·완료 여백 2·분석 줄 철회 1·최신 간결화 2·audio_desc 계약 3·실삽입 콜론 정렬 1. compile 16 + smoke PASS + 미러 정합 |

### CLI 스타일 포맷 표기 + AAC 세분화 + 라이브 속도 릴레이 계측 (v3.0.2)

| 항목 | 내용 |
|------|------|
| 라이브 속도 근본 치료 | 디스크 파일 크기 차분은 ffmpeg/OS 버퍼의 계단식 플러시를 그대로 반영해 0↔버스트 진동(이동평균으로도 못 살림). **릴레이 계측**으로 전환 — streamlink/ffmpeg stdout을 Python이 256KB 청크로 읽어 실기록하며 카운트 = 네트워크 실수신량. stderr는 별도 스레드로 로그 유지. 취소 시 큐 drain 보강('truncated' 오탐 방지). 이동평균 계산기는 폴백용으로 유지 |
| 비디오 스트림 CLI 표기 | `media.cli_format_desc(f)` — '1920x1080 60fps │ 8.4Mb/s m3u8 │ avc1.64002A' 식 CLI 컬럼 재현(스펙문자열+코드 공백 정규화, fps·TBR은 존재 시만). VOD 헤더 가지 + 클립 API 포맷에 적용. 라벨 ID 제거(전면 (ID: …) 문법 폐지) |
| AAC 프로파일 세분화 | media._CODEC_SHORT_NAMES — mp4a.40.2=AAC-LC, 40.5=HE-AAC v1, 40.29=HE-AAC v2. **주의: 매칭은 순회 순서 기반이라 generic 'mp4a'보다 세분화 항목이 먼저여야 하고**, 부분 문자열 함정(mp4a.40.2 vs 40.29) 때문에 실매칭은 startswith 규칙(40.29→40.5→40.2 순)을 따름 — 신규 코덱 추가 시 규칙 확인할 것 |
| 오디오 표기 스펙 | `media.audio_flat(acodec)`='AAC-LC mp4a.40.2'(헤더 가지·배지용 괄호 없음) / `audio_spec`='AAC-LC (mp4a.40.2)'(독립 문구용). codec_detail은 총칭('AAC')이면 빈값 |
| 통합 오디오 개편 | '(통합)' 표기 폐지. 드롭다운에 실제 코덱 항목(AAC-LC mp4a.40.2 등, 데이터=integrated 센티널 유지), 분석 완료 개수에 [내장] 접미사, 헤더 오디오 가지·클립 헤더도 audio_flat 사용. 워커 계약 불변 — a_sel=='integrated' 번역은 spawn 지점에서만 |
| 검증 | `_verify_all.py` 34케이스 전부 통과 — relaysim 6·cli desc 5·aac 프로파일 7(선행40.29 우승 포함)·audio_flat/spec 3·드롭다운 2·integrated 폭주 1·ID 제거 2·헤더 포맷 3·언어 통일 1·통합로그 1·클립 1·progress 노선 2. compile 16 + smoke PASS(exit 0) + 미러 갱신 2(downloader·media) |

### 치지직 VOD 자체 파이프라인 + 전 소스 속도·포맷 표기 통일 + 유튜브 성인제한 다운그레이드 대응 (v3.1.0)

| 항목 | 내용 |
|------|------|
| 치지직 VOD 깨짐 근본 원인 | 2026년부터 재생 API(neonplayer vodplay v2)가 MPD를 **JSON 직렬화**로 돌려 yt-dlp XML(SMIL/MPD) 파서가 깨짐 → 대표 증상 `KeyError('sourceURL')`(common.py SMIL 파서의 속성 탐색 실패). 유저 재현 '치지직 VOD 오류'의 원인 |
| VOD 자체 파이프라인 | `chzzk_api.analyze_chzzk_vod_api()` 신설 — meta(v2/videos)+playback JSON-MPD에서 첫 adaptationSet의 **progressive MP4**(baseURL .mp4, 클립과 동일 VOD_ALPHA CDN)를 추출. 실측 1080p60 8.19Mbps/720p60 3.19Mbps/144p 헤더 200 영상/mp4. 클립과 동일한 다운로드 분기(m_clip or m_vod)로 흡수 — AnalyzeWorker·_download_target 공통. videoTitle의 '.mp4' 컨테이너 확장자 오염 제거 |
| 속도 계측 통일 | **`SpeedWindow`(10초 이동평균) 신설** — 다운로드 source와 무관하게 '네트워크에서 실제 흐른 바이트'만 샘플: 라이브=릴레이 파이프 계수, VOD=yt-dlp `downloaded_bytes`(HTTP 실수신량). VOD 틱의 yt-dlp `speed` 필드(자체 스무딩 얹힘)와 라이브 인라인 이동평균 로직을 둘 다 이 공용 계산기로 대체. 스트림 전환(비디오→오디오)·타겟 전환 시 윈도우 리셋. 디스크 파일 크기 차분은 어디에도 사용 안 함 |
| 포맷 표기 단일 출처 | `media.cli_format_desc(f)`가 유튜브 -F 표 컬럼 재현('mp4 \| 1080p 60fps \| 8190k https \| H264 \| AAC-LC (mp4a.40.2)')의 **유일한 출처**. downloader `_cli_fmt_desc`·(ID: …) 구버전 문법 폐기, AnalyzeWorker 라벨·VOD/클립 헤더·라이브 헤더 전부 이 함수로 통일. fragment(fps/tbr/proto)는 존재 시만, 오디오 전용에도 audio_spec(상세) 적용 |
| 통합 포맷 중복 제거 | 유튜브 progressive(itag 18 등 v+a 내장)에서 'AAC-LC'가 비디오·오디오 둘 다에 중복 표기되던 문제 수정 — cli_format_desc가 코덱을 비디오 줄에 1회 결합. `_emit_download_header`·`_emit_live_header`·`_emit_chzzk_header` 모두 통합 포맷은 오디오 가지 미표기, 분리 병합만 audio_desc(CLI 라벨) 표기. main._audio_stream_desc는 통합전용 시 '' 반환으로 개편 |
| 유튜브 성인제한 360p 한정 | 근본 원인 확정: 쿠키 감지 시 유튜브가 'tv downgraded' 플레이어로 강제 전환해 SABR 스트리밍만 남김 → itag 18(360p) 하나로 수렴(yt-dlp 이슈 #16226, 미해결). 우회 = 쿠키 + player_client 명시. `_apply_client_opts()` 신설 + cfg `yt_player_client`(기본 auto): tv/web_safari/tv_simply/mweb 선택. Analyze·_base_info_opts·일반 VOD·라이브 전 경로 적용, 설정창 컴보 추가. 실측: 그러므로 '성인 게이트 통과 여부'가 360p의 본질 — 브라우저에서 영상 재생(세션 갱신) 후 재시도가 핵심 |
| 검증 | `_v_new.py` 11/11 PASS(cli 단일출처 v+muxed/v-only/a-only/치지직형·SpeedWindow avg/reset·clip/vod api fn·client tv/auto·vod url regex) + `_v_vod.py` 실측 14873912 → title/date/duration/progressive 3포맷(1080p60 8190kbps, 720p60, 144p) 정상 + compile 무결 + smoke PASS + chzzk_api vocab 정리(_chzzk_headers/_get_json 공용화) |

### 유튜브 PO Token(bgutil) 프로바이더 — 설계 결함 수리 + 포터블 무결 (v3.1.x)

**표면 증상**: 앱 시작 시 `[!] PO Token 프로바이더 서버 기동 실패` (bgutil 백그라운드 작동 실패)

**근본 원인 (설계 결함)**: `pot_provider.py`가 bgutil v1.x 구조를 오해.
1. `plugin_installed()`가 `find_spec("bgutil_ytdlp_pot_provider")`를 검사했지만, **1.x 플러그인은 `yt_dlp_plugins/extractor/getpot_bgutil*.py` 네임스페이스로만 존재**하고 `bgutil_ytdlp_pot_provider` 파이썬 패키지는 아예 없다 → 설치돼 있어도 항상 '미설치' 오판.
2. `_spawn_server()`가 `python -m bgutil_ytdlp_pot_provider.server`로 서버를 띄우려 했지만 **그런 모듈은 존재하지 않음**.
3. 더 근본적으로 **bgutil HTTP 서버는 TypeScript/Node.js(또는 Docker) 전용**이다. (Dockerfile ENTRYPOINT `node build/main.js`, 빌드 산출물 `server/build/main.js`) — 파이썬 기동 불가능.
4. `server_running()`이 TCP 프로브만 수행 → 다른 프로그램이 4416 점유 시 오판.

**진단(재현) 방법**: `im.version("bgutil-ytdlp-pot-provider")`=1.3.2 설치 확인, `find_spec("bgutil_ytdlp_pot_provider")`=None, 배포 휠 내 파일 = `yt_dlp_plugins/extractor/getpot_bgutil*.py`만 존재.

**해결 설계 (`pot_provider.py` 재작성)**:
- `server_running()` → `/ping` HTTP 프로브 기반 `probe_server()` 3-state(`ok`/`conflict`/`down`) — 포트 점유 오판 제거.
- `plugin_installed()` → 패키지 메타데이터 + `yt_dlp_plugins.extractor.getpot_bgutil` 네임스페이스 검사.
- 기동 파이프라인 (QThread, **구성요소 업데이트/업그레이드 완료 뒤에만 `main._start_pot_provider` 호출** → 실행 순서 보장):
  1) `probe_server()` ok → "감지됨" 종료  2) `conflict` → 포트 충돌 안내
  3) 플러그인 부재 → 미설치 안내  4) 준비된 서버를 `node`로 기동(`_spawn_existing`)
  5) 부재 시 원본 실행에서만 소스 zipball 다운로드 → `npm ci` → `npx tsc` 1회 빌드 → 기동
  6) 실패 시 안내 로그만 — PO 토큰 없이 진행(기능 저하). 실측 기동 5.6초 후 `/ping 200 {"version":"1.3.2"}`.

**로그 UX (기존 콘솔 패턴과 통일)**:
- `POTProviderWorker.line` 시그널을 `(str, is_status, is_error)`로 확장. `main._start_pot_provider`가 QTimer(200ms)로 `[~] PO Token 서버 구동 중...` 상태줄 마침표 애니메이션.
- 최종 판정은 `outcome(state, msg)` — **실제 서버 준비 성공일 때만 `[v]`**, 실패/충돌/미설치는 `[!]`. (기존의 무조건적 `[v] 준비 완료.` 박제는 폐지)
- 완료 후 `add_concise_task_separator()`로 여백 보장.

**포터블 무결 (exe 배포) — node.exe 번들까지 완결 (v3.1.x 후속)**:
- `_is_portable()`(`sys.frozen`) 감지: 포터블에선 `%USERPROFILE%` 등 **앱 폴더 밖을 절대 쓰지 않음**. `server_home()` = 원본 실행 `%USERPROFILE%\bgutil-ytdlp-pot-provider` / 포터블 `<exe>\_internal\bgutil-ytdlp-pot-provider`(번들 서버만 사용).
- 포터블 자동 빌드 금지(`ensure_node_server`가 frozen이면 거부) — 자동 npm은 원본 실행 전용.
- `ChzzkTube.spec` 번들 3종 (spec 시점 스테이징):
  1. **서버(프루닝)**: `_stage_pruned_server()` — `server/build` + `package.json` + `node_modules` 중 **런타임 deps만**(dependencies/optionalDependencies/peerDependencies 를 고정점까지 추적) 복사. `npm ci`가 설치한 devDeps(typescript 23MB/@swc 27MB/prettier/jsdom/canvas 등) 제외 → 서버 번들 165.9MB→87MB, dist 389→310MB.
  2. **node.exe**: 시스템 node 바이너리를 `_internal\node.exe` 로 심고 `pot_provider.node_exe()` 가 최우선 사용 → **시스템 Node 미설치 포터블에서도 자동 기동 완결**. (node.exe 단독으로 서버 기동 가능 — npm/npx 불필요)
  3. **플러그인 폴더**: `yt_dlp_plugins` 네임스페이스 폴더 전체를 `_internal` 에 심음. frozen 에서 PEP420 네임스페이스의 PYZ `find_spec` 이 실패해 **서버 스폰 전 '플러그인 미설치' 게이트에서 조기 종료하던 1차 결함** 해소. `_MEIPASS`(sys.path) 파일시스템 탐색 + yt-dlp 플러그인 로더 탐색 모두 커버.
- `plugin_installed()` 보강: frozen 에서 PYZ 네임스페이스 탐색 실패 대비 `_internal/yt_dlp_plugins/extractor/getpot_bgutil*.py` 파일 존재 검사 추가(2차 안전망).
- `_spawn_node_server` 포트 대기 20s→**45s**(첫 실행 시 AV가 번들 node_modules 수천 파일을 스캔해 기동이 늦어질 수 있음).
- `dialogs._do_check`: frozen에서 bgutil-ytdlp-pot-provider 검사 스킵 — 포터블은 pip 설치 대상이 아니므로 '미설치 감지 → 자동 설치' 오표시 노이즈 제거.
- Docker 로컬 이미지/컨테이너 있으면 자동 사용(자동 pull 없음). `pyproject.toml`에 `bgutil-ytdlp-pot-provider==1.3.2`(원본 실행 의존성 명시).

| 검증 | **e2e 실측(재빌드 dist)**: frozen exe 기동 → 업데이트 체크 완료 후 자동 스폰 → 번들 node.EXE 프로세스로 `/ping 200 {"server_uptime":..,"version":"1.3.2"}` → **`POST /get_pot`(v1.3.2 라우트 — 옛 문서의 `/get_pot_token`은 0.x API로 404) 200, 실제 poToken 발급 확인**. `yt_dlp_plugins/extractor` 번들 확인, dist 310.3MB, py_compile + smoke PASS |

### PO 서버 Node 22 재구성 + 로그 히스토리 패스 (2026-08-31)

| 항목 | 내용 |
|------|------|
| 근본 원인 | PO 서버 기동 실패 = bgutil 서버의 `require(esm)` 요구(Node ≥ 22) — 구버전 `ensure_node_runtime`이 Node v20.18.0을 받아 `ERR_REQUIRE_ESM` 크래시. 빌드 산출물 존재 시 `ensure_node_server`가 무조건 조기 리턴해 사유 로그도 0건 |
| Node 22 수급 | pot_provider: `NODE_MIN_MAJOR=22`, `node_exe()`가 전 후보 버전 검사 후 미달 배제(판별 전면 실패 시 첫 후보 폴백 — 무한 재설치 방지), `latest_lts_node_url()` nodejs.org dist index 최신 v22(조회 실패 시 폴백 v22.23.2), `ensure_node_runtime` 재구성 + `_prune_outdated_node_dirs`로 구형 node-v20.* 캐시 정리 |
| 조기 리턴 결함 | `ensure_node_server` 빌드 존재 분기에 `node_ok()` 게이트 추가 — 기존 빌드 + Node 미달/부재 케이스가 err=None으로 무음 실패하던 것 수리 |
| 실패 원인 가시화 | `_spawn_node_server` 스폰 실패 사유(main.js 부재/node 부재/45s ping 타임아웃)를 log_full로 출력 + err 유무와 무관하게 `read_server_log_tail(6)`(bgutil_server.log) 테일 노출 |
| ffmpeg 자동 수급 | `components.ensure_ffmpeg` 신설 — 시스템 which 우선, 없으면 BtbN GitHub latest zip → `<writable_base>/ffmpeg/bin`, `_wire_ffmpeg_path`로 세션 PATH 선두 연결(media/downloader의 bare `'ffmpeg'` subprocess 대응). POT 워커 `_run` 선두에서 호출 |
| 로그 히스토리 | `log_history.py` 신설 — `config.LOG_DIR`/`chzzktube_YYYY-MM-DD.log`(하루 1파일 UTF-8 append, 세션 마커, 30일 자동 정리, 스레드 세이프, 실패 흡수). main: `session_begin`(MainWindow init)/`excepthook`(미처리 예외 전체 트레이스백)/`session_end`(closeEvent), `append_concise_log`에서 전건 이중 기록(상세탭 te_full + 히스토리) — 상세탭이 yt-dlp/streamlink 원본만 담던 결함 보완. POT 워커 line/log_full·UpdateWorker line도 히스토리 연결 |
| UpdateWorker 결함 | `_start_update_check`의 확인 모드 line 시그널 미연결 — '[v] pkg 최신/미설치 감지/버전 확인 실패' 로그가 전건 증발하던 것 수리(업그레이드 모드만 연결돼 있었음) |
| 경로 단일화 | `config.writable_base()` 신설(pot_provider 위임), `config.LOG_DIR` 추가. 미러 목록에 components/log_history 추가 |
| 검증 | e2e 실측: Node v22.23.2 수급 → bgutil v1.3.2 스폰 → `probe_server()=('ok','')`. ffmpeg 시스템 감지 스킵 확인. py_compile 18종 ALL=0, smoke PASS, 미러 동기화 완료. 개발 런 히스토리는 `<repo>/logs/`(gitignore)에 기록 |

### 로그 정책 개편(요약 1줄) + 콘솔·분석 버그 3건 수리 (2026-08-31)

**로그 정책(단일 출처)**: 간결 로그 = "요약 1줄"(유저가 매 실행 봐야 할 판정만),
상세 로그·히스토리 파일 = "전체". 구성요소별 `[v] ~최신/건너뜀` 루틴 라인은 간결 생략하고
`[v] 구성요소 최신` 요약 1줄만 남긴다(`_on_update_check_done`, 구버전 감지 시엔
업데이트 진행 라인이 이미 간결에 떠서 도장깨기 안 함). 설치·업데이트·오류 라인은 간결 통과.

| 항목 | 내용 |
|------|------|
| `_component_line` 필터 | main.py의 단일 관문 — UpdateWorker.line·POTProviderWorker.line 연결을 `append_concise_log` 직행에서 이 필터 경유로 변경. 루틴 '최신/건너뜀' 라인은 `te_full`(상세)+`log_history`(히스토리)만 기록하고 간결 스킵, 그 외는 `append_concise_log` 위임 |
| 히스토리 단일 기록점 | `append_concise_log` 내부 log_history 기록을 유일 기록점으로 통합(별도 어댑터 폐지). components.py는 각 ensure_* 내부에서 log_history 기록하므로 line 시그널의 log_history 직결은 제거 — 이중 기록 방지 |
| URL 삭제 잔여 로그 | `clear_status_line`이 `_remove_status_blocks`를 바로 호출해 **바닥 여백 빈 블록 2개를 상태 블록으로 오인 삭제** → '분석중' 텍스트 잔존. `_strip_tail_padding` 선행으로 수리(append 경로와 전제 일치) |
| 분석 정체(GIL 사망) | 재분석/URL 삭제 시 `QThread.terminate()`가 **GIL 보유 상태로 파이썬 스레드 강제 종료** → 죽은 스레드가 GIL을 영원히 미반환 → GUI 전체 파이썬 실행 정지("미디어 스트림 분석중"에서 다운로드 불능). `_abandon_analyze_worker()` zombie 패턴(시그널 차단 후 자연 종료·회수) + `_discard_analysis_result()`로 대체. **`from downloader import AnalyzeWorker, DownloadWorker` import 유실도 복구**(이것만으로도 분석 자체가 죽는 상태였음) |
| 드래그 선택 보존 v2 | 2겹 결함: ①렌더러가 사용자 커서를 끌어다 써서 선택이 문서 끝까지 늘어남 → `_end_cursor()` 독립 커서 격리 ②그래도 '선택 끝 == 문서 끝' 순간 삽입 시 Qt 커서 자동조정이 선택 끝을 삽입물 뒤로 밀어냄 → append 진입 시 선택 절대 오프셋 스냅샷, finally에서 `_restore_user_selection` 복원(+과선택 클램프). `add_task_separator`·`clear_status_line` 문서 변경자에도 공통 적용 |
| 검증 | PASS 1(드래그 중 로그 유입 시 선택 불변)·1b(문서 변경자 선택 보존)·2(URL 클리어 잔여물 0)·3(클리어 직후 재분석 수용 — 정체 부재), smoke PASS, py_compile ALL=0, 미러 17개 동기화(변경 0) |

### uv 전환 + Python 3.12 마이그레이션 (v3.1.0)

| 항목 | 내용 |
|------|------|
| uv 도입 | `requirements.txt` 제거 → `pyproject.toml` + `uv.lock` 단일 출처. `uv sync`로 설치, `uv run`으로 실행(활성화 불필요). Windows 해시 28건 포함 → macOS에서 잠그면 Windows가 동일 조합. `[dependency-groups] build = ["pyinstaller"]` — Windows 빌드는 `uv sync --group build` → `uv run pyinstaller ChzzkTube.spec` |
| Python 3.12.14 | `.python-version` 생성(pyenv 자동 고정). 3.10에서 마이그레이션 — 제거된 모듈(`distutils`/`imp`/`asynchat` 등) 사용 0건으로 소스 수정 불필요. venv 재구성 후 전 의존성 cp312 휠 설치 검증 |
| pyobjc 제거 검증 | `uv sync`에서 `pyobjc-framework-*` 제거됨 — PyQt6는 pyobjc 없이 macOS에서 정상 동작(`import PyQt6.QtWidgets` + 스모크 PASS로 증명). pip도 uv venv에 존재(`updater.updater_packages` 동작 유지) |
| 검증 | py_compile 전체 OK · smoke PASS · 미러 26개 변경 3/누락 0 |

## 9. 남은 과제 (우선순위순)

1. **`.gitattributes` eol 정규화** — diff 노이즈 제거
2. **AnalyzeWorker의 컨트롤러 이관** — DownloadController와 대칭 완성 (선택)
3. **MainWindow 잔여 상태 로직**(on_download_finished의 요약/사운드 분기 등) 컨트롤러화 — 회귀 리스크 大, 신중히
4. `versions/` 정리 및 git 태그화 여부 결정
5. 유튜브 라이브: 배치(txt) 안의 watch?v= 라이브 URL은 힌트가 없어 VOD
   경로로 감(다운로드 자체는 되지만 ffmpeg 강제 다운로더 문제가 재발).
   필요 시 다운로드 전 경량 is_live 프리체크 도입을 검토할 것.
   (→ 구 PO Token node 번들 과제는 §8 'node.exe 번들까지 완결'로 **완료**)

## 10. 하지 말 것

- state/cfg 딕셔너리를 복사해서 워커에 넘기는 것
- smoke_test 통과 없이 리팩토링 커밋하는 것
- .md 미러를 손으로 고치는 것 (항상 .py가 원본)
- GUI 없는 CI 가정으로 Qt 코드를 임포트만으로 검증 끝이라 착각하는 것 — smoke_test(offscreen)를 돌릴 것
- 배포 시의 완벽한 포터블(Portable) 무결성을 침범하는 행위

---

## 11. TUI 레이아웃 + 로그 미니멀화 (2026-09-03)

| 항목 | 내용 |
|------|------|
| 폰트 통일 | 전체 `JetBrains Mono` → `Cascadia Mono 11px`. `theme.py` / `main.py` / `progress_emitter.py` 모든 QSS와 QFont 참조 수정 |
| Flat 레이아웃 | `QGroupBox` 보더/반경 제거 → flat. 섹션 타이틀 투명 처리. 1px 구분선(`QFrame.tui-separator`)으로 섹션 구분 |
| 세로 정렬 | 모든 레이아웃의 `left margin: 0`, `main_layout`의 `left margin: 12px`로 `Path`/`>`/`[10:54:14]` 정렬 통일 |
| 프롬프트 | `Input & Action`에 `>` 프롬프트 라벨 추가 (Cascadia Mono Bold, 액센트 색상) |
| 입력 필드 | `QLineEdit#url_input` 언더라인 스타일 (1px border-bottom, 포커스 시 액센트) |
| MSG 미니멀화 | 모든 `emit_event`/`emit_dl`/`format_log_line` MSG를 영어 1-3단어로 축소 (한국어 → 영어) |
| PLATFORM 칼럼 | `finalizer.py` / `live_recorder.py` / `downloader.py`의 하드코딩 `"-"`를 `_dl_platform()` 호출로 교체 |
| SPEC 칼럼(라이브) | 라이브 진행 틱에서 파일명(SPEC) → MSG로 이동, SPEC에 `-` |
| format_analysis_counts | `(비디오 3개, 오디오 2개)` → `(v:3, a:2)` |

### MSG 대조표 (Before → After)

| 위치 | Before | After |
|------|--------|-------|
| main.py:408 | `로드 완료 — {n}개 URL` | `{n} URLs` |
| main.py:415 | `파일 읽기 실패` | `read fail` |
| main.py:425 | `사용자에 의해 중단 요청됨` | `user abort` |
| main.py:449 | `경로 변경 → {path}` | `path → {path}` |
| main.py:527 | `구성요소 확인 지연 — 입력 선개방` | `deps delayed — unlock` |
| main.py:544 | `Components up-to-date` | `deps ok` |
| main.py:567 | `Server bind failed — ...` (길게) | `bind fail — age-only` |
| main.py:574 | `Ready for download` | `ready` |
| main.py:625,918 | `분석 시작...` | `analyzing...` |
| main.py:662 | `분석 완료{counts} — {url}` | `analysis ok{counts}` |
| main.py:705 | `업데이트 가능 — {summary}` | `update — {summary}` |
| main.py:714 | `DEPS 확인 완료` | `deps ok` |
| main.py:735 | `업데이트 {summary}` | `update {summary}` |
| main.py:864 | `상세 로그 버퍼 비어 있음 — ...` | `empty buffer` |
| main.py:908 | `입력 파싱 오류: {e}` | `parse error: {e}` |
| main.py:943 | `현재 항목 건너뛰기 요청됨` | `skip request` |
| progress_emitter.py:100 | `"{title}"` | `{title}` (따옴표 제거) |
| progress_emitter.py:114 | `완료 — {bn} ({sz})` | `{bn} ({sz})` |
| progress_emitter.py:132 | `다운로드 시작 — {title}` | `{title}` |
| progress_emitter.py:146 | `라이브 녹화 시작 — {title}` | `live — {title}` |
| progress_emitter.py:161 | `치지직 다운로드 시작 — {title}` | `chzzk — {title}` |
| progress_emitter.py:184 | `라이브 녹화 완료` | `live done` |
| finalizer.py:17 | `사용자 중단` | `abort` |
| finalizer.py:46 | `종료 — 성공 N개, 실패 M개` | `done — {s}/{total}` |
| live_recorder.py:70 | `녹화 종료 코드 오류` | `exit code error` |
| live_recorder.py:89 | `라이브 저장 완료 — {bn}` | `saved — {bn}` |
| live_recorder.py:160 | `라이브 녹화 중` | `recording — {spec}` |
| live_recorder.py:198 | `{tag} 라이브 녹화 실패` | `{tag} fail` |
| downloader.py:49 | `비디오와 오디오 스트림 병합 중...` | `merging` |
| downloader.py:63 | `건너뜀 — 이미 존재하는 파일 ({bn})` | `skip — exists ({bn})` |
| downloader.py:154 | `치지직 스트림 정보를 가져오지 못했습니다 (...)` | `chzzk stream fail (cookie)` |
| downloader.py:283 | `미디어 정보를 가져오지 못했습니다.` | `media info fail` |
| downloader.py:293 | `연령 제한/멤버십...` (4줄) | `age/membership restricted` |
| downloader.py:298 | `분석 오류 발생: {ex}` | `analysis error: {ex}` |
| target_downloader.py:78 | `치지직 스트림 정보를...` (길게) | `chzzk stream fail (cookie)` |
| target_downloader.py:82 | `치지직 다운로드 URL 없음` | `chzzk URL missing` |
| target_downloader.py:118 | `동영상 정보 추출 실패` | `info extract fail` |
| live_recorder.py:40 | `라이브 정보 추출 실패` | `live info fail` |
| live_recorder.py:44 | `라이브 스트림 URL 없음` | `live URL missing` |
| controller.py:55 | `TXT 읽기 실패: {e}` | `TXT read fail: {e}` |

### 검증
- `smoke_test.py` PASS
- `py_compile` 전체 OK

---

## 12. DEPS 로그 영문화 + PLATFORM 축약 + 폰트 통일 (2026-09-03)

| 항목 | 내용 |
|------|------|
| raw 로그 타임스탬프 | `main.py _mirror_full_log()` — 모든 raw 로그 라인에 `[HH:MM:SS]` 자동 부착. 다중 라인 메시지 모든 줄에 동일 타임스탬프. F12 창 + 히스토리 버퍼 모두 적용. `import time` 추가 |
| 폰트 통일 | `D2Coding-Regular.ttf` → `CascadiaMono-VariableFont_wght.ttf` 로드. `theme.py` 전체 QSS 폰트 체인 `'Cascadia Mono', monospace` (Consolas 제거). `main.py` setFamilies `["Cascadia Mono"]` 단일 폰트 |
| dialog 영문화 | `dialogs.py` 전체 UI 라벨 영문화 — ExitConfirmDialog("Exit"/"Cancel"/경고문), CookieSelectDialog("Error" + 브라우저 쿠키 로드 실패 메시지), ActionCountdownDialog("Run Now"/"Cancel"/"Post-Download Action"/초 카운트다운), CookieViewerDialog("Close"), SettingsDialog(컨테이너/쿠키/유튜브 클라이언트/옵션 체크박스 라벨 전부) |
| updater.PACKAGES 재구성 | `[("ytdlp", "yt-dlp"), ("streamlink", "streamlink"), ("bgutil", "bgutil-ytdlp-pot-provider")]` — 로그용 짧은 라벨 + PyPI 실명 분리. `dialogs._do_check`의 frozen 스킵도 `pypi_name` 기반으로 수정 |
| main.py 툴팁 영문화 | F1~F12 버튼 tooltip, URL placeholder, QFileDialog 제목("Select Download Folder", "Select TXT File"), exit 콘솔 로그("shutdown: download worker not stopped...") 전부 영문화 |
| pot_provider 영문화 보강 | `"Node.js 런타임 구성 후에도 요구 버전 미충족"` → `"Node.js still below requirement (>= 22) after configure"` 포함 8건 추가 수정. `probe_server` 리턴 디테일, `_spawn_node_server` 실패 사유, `download_and_install_source` RuntimeError 등 |
| progress_emitter 제목 폴백 | `동영상` → `video` / `치지직` → `untitled` |
| downloader.py | `재생목록/채널` → `playlist/channel` / `포맷 분석 시작` → `format analysis start` |
| live_recorder.py | `프로세스 종료 코드` → `process exit code` |
| cookies.py | `쿠키 DB 읽기 실패` → `cookie DB read failed` |
| 검증 | `smoke_test.py` PASS, `py_compile` 11개 모듈 ALL OK |

---

## 13. 로그 컬럼 표준화 + LIVE 스테이지 분리 + 비주얼 폴리시 (2026-09-03)

### 표준 포맷 (v3)
```
[HH:MM:SS] STAGE │ STATUS │ PLATFORM │ SPEC │ SPEED │ PCT │ BAR │ MSG
```
- **SPEED 칼럼 신설**: SPEC(스트림 속성 `1080p30`)과 SPEED(네트워크 `12.4M/s`) 분리.
  기존 `emit_dl`이 spec 뒤에 speed를 문자열 병합하던 것을 `format_log_line(speed=)` 파라미터로 분리.
  SPEC/SPEED 모두 `"-"`면 칼럼 자체를 생략(조건부 칼럼 유지).
- **LIVE 스테이지 신설**: 라이브 녹화 틱/헤더/종료/실패가 `DL` 재사용하지 않고 `LIVE` 사용.
  - `progress_emitter.emit_live_header` — 해상도는 SPEC, 제목은 MSG
  - `progress_emitter.emit_live_final_stats` — 용량은 MSG `live done (1.2 GB)`, 평균속도는 SPEED
  - `live_recorder` 4개 emit_dl 호출 전부 `stage="LIVE"`
- **SPEC/MSG 엄격 매핑**: SPEC=스트림 속성 전용, MSG=제목·파일명·시스템 메시지 전용.
  - `live_recorder.handle_stream_finish` DONE 라인: SPEC의 파일 크기 → MSG `saved — {name} ({size})` 이동
  - `finalizer`: 배치 결론 라인의 SPEC(`batch done`)/SPEED(`1/3`) 오염 제거 → MSG `batch finished (success: N, fail: M)` 통합

### 비주얼 폴리시
| 항목 | 변경 |
|------|------|
| 소프트 레드 | `theme.ERROR` `#f44747` → `#e06c75` (Atom One Dark pastel). `LOG_COLOR_ERROR`/`BTN_DANGER_QSS` 자동 파생 |
| (x) 버튼 제거 | `url_input.setClearButtonEnabled(False)` + `installEventFilter` — url_input 내부 ESC 입력 감지 |
| ESC 컨텍스트 액션 | `_esc_action()`: 실행 중 → abort, 대기 중 → `url_input.clear()`. 전역 keyPressEvent와 eventFilter 양쪽 바인딩 |
| 힌트 갱신 | 버튼 행: `[ F4: Load .txt ] │ [ ESC: Clear │ ENTER: Start ]` — 딤 `│` QLabel 구분자(`_tui_sep`) 추가. ESC 버튼 라벨은 `update_ui_state`에서 동적 갱신(`[ ESC: Abort ]` ↔ `[ ESC: Clear ]`) |
| 영문 매핑 적용 | `deps check delayed — opening input` / `node.js >= 22 missing — downloading portable runtime` / `pot server bound (127.0.0.1:4416)` / `stream analyzed (v:21, a:4)` / `download canceled by user` / `batch finished (success: N, fail: M)` |


---

## 14. URL 분석 유령 로그 수리 + 인식 디바운스 (2026-09-03)

### 증상
URL 입력을 지울 때마다 `analysis` 로그가 한 번 더 출력됨. 타이핑 중에도 부분 URL로 분석이 점화.

### 근본 원인 (경쟁상태)
AnalyzeWorker의 `result_ready`/`error_occurred`는 워커 스레드 → GUI 스레드 **queued connection**.
`_abandon_analyze_worker()`의 `disconnect()`는 '이후' 방출만 차단할 뿐 **이미 이벤트 큐에
적재된 전달은 취소하지 못한다**. 지우기 직전 큐잉된 결과가 슬롯에 도착해
`stop_analysis_anim` → `stream analyzed` 라인이 남았던 것이 유령 로그의 정체.

### 수정 (main.py)
| 항목 | 내용 |
|------|------|
| `_is_stale_analyze_signal()` 신설 | `on_analyze_success`/`on_analyze_error` 입구 가드. ① `self.sender() is not self.worker_analyze` → 유기된 워커의 큐잉 시그널 폐기. ② `url_input`이 비었으면(분석 도중 지워짐) 폐기. 폐기 시 `extracted_data` 오염도 차단 (stale URL의 `live_hint` 오염 부수 수리) |
| 디바운스 500ms → 900ms | 모듈 상수 `_ANALYZE_DEBOUNCE_MS = 900` — 타이핑 멈춤 기준 지연 상향 |
| URL 형태 가드 | `on_url_changed`에서 텍스트에 `://` 또는 `.`이 없으면 타이머 미가동 — 부분 타이핑/'그냥 단어'에 analyzing 점화 방지 |

### 검증
- 큐잉 경쟁상태 재현 테스트: 유기 워커 시그널 → 드랍(confirm), 활성 워커 시그널 → 정상 처리 — 둘 다 PASS
- 타이핑/벌크 입력 판별 테스트: 키 입력 900ms, 붙여넣기/드롭/TXT 로드 150ms, 도메인 미완성 가드 차단 — 전부 PASS
- `py_compile` OK, `smoke_test.py` PASS

### 타이핑 인식 가드 (추가 보완)

**이론적 한계**: "사용자가 타이핑을 끝냈다"는 미래 입력 부재를 감지해야만 알 수 있으므로
키 입력 경로의 침묵 대기(디바운스)는 구조상 불가피하다. 단, 붙여넣기·드래그&
드롭·TXT 로드는 한 이벤트에 텍스트가 통째로 들어오므로 **입력 증분(delta)으로
즉시 식별 가능**하다.

| 항목 | 내용 |
|------|------|
| `_BULK_INPUT_DELAY_MS = 150` | 벌크 입력(붙여넣기/드롭/TXT) 즉시 분석 — 0ms 대신 150ms는 프로그램적 다중 setText 병합용 |
| 입력 증분 판별 | `on_url_changed`에서 `len(text) - _last_input_len > 1` → 벌크 입력으로 판정, 짧은 지연 적용. 1글자 증분이면 키 입력 → 900ms 디바운스 유지 |
| URL 형태 가드 강화 | 기존 `":"` 또는 `"."` → `re.search(r"\S\.\S", text)` (도메인 형태) + `"://"` — 부분 타이핑에서의 불필요한 점화 차단 |
| 검증 | 키 입력 900ms / 벌크 150ms / 도메인 미완성 가드 차단 — 전부 PASS |

### 검증
- `py_compile` 9개 모듈 OK, `smoke_test.py` PASS
- `is_tui_line`이 SPEED 칼럼 포함 신규 라인도 정상 인식 (raw 로그 미러링/필터 무영향)
- 샘플 렌더 확인: VOD 틱(SPEC/SPEED 분리), LIVE 틱/종료, 배치 결론, FAIL, 분석 라인 전부 규격 준수

---

## 15. MVC 4계층 완성 리팩토링 (2026-09-04)

### 배경
- **문제점 1**: `DownloadWorker`는 `controller.py`가 관리하지만, `AnalyzeWorker`는 `main.py`에 직접 붙어있었음 → 모듈 역할 분리 위반
- **문제점 2**: 좀비 스레드 수용소(`_zombie_workers`)가 View(`main.py`)에 있어 스레드 생명주기가 View에 종속됨
- **문제점 3**: `_abandon_analyze_worker()`, `_reap_zombie_worker()` 등 스레드 관리 로직이 View에 노출됨

### 수정 내용

#### controller.py — MediaController로 확장
| 항목 | 변경 |
|------|------|
| 클래스명 | `DownloadController` → `MediaController(QObject)` |
| 상태 추가 | `state["analyzing"]` — 분석 중 플래그 |
| 워커 소유 | `worker_dl` (다운로드) + `worker_analyze` (분석) |
| 좀비 무덤 | `_zombie_workers` — Controller가 소유 (View에서 이관) |
| 시그널 추가 | `analyze_result_ready`, `analyze_error_occurred`, `analyze_log_full` (View 포워딩용) |
| 메서드 추가 | `spawn_analyzer()`, `_abandon_analyzer()`, `_reap_zombie()` |
| 이름 명확화 | `begin()` → `begin_download()`, `end()` → `end_download()` |
| 하위 호환성 | `DownloadController = MediaController` 별칭 유지 |

#### main.py — View 순수성 회복
| 항목 | 변경 |
|------|------|
| import 정리 | `from downloader import AnalyzeWorker` 제거 |
| 컨트롤러 | `DownloadController(self)` → `MediaController(self)` |
| 워커 소유 제거 | `self.worker_analyze = None` 삭제 |
| 시그널 바인딩 | `ctrl.analyze_result_ready.connect(on_analyze_success)` 등 3개 추가 |
| 메서드 제거 | `_abandon_analyze_worker()`, `_reap_zombie_worker()` → Controller로 이관 |
| `run_analysis()` | `self.ctrl.spawn_analyzer(url, self.cfg)` 호출만 (1줄로 간소화) |
| `_is_stale_analyze_signal()` | `self.worker_analyze` → `self.ctrl.worker_analyze` |

### 아키텍처 변경

**Before**:
```
[View]      main.py ── AnalyzeWorker 직접 관리 (좀비 스레드 수용소 보유)
[Control]   controller.py ── DownloadWorker만 관리 (AnalyzeWorker 누락!)
```

**After (MVC 4계층 완성)**:
```
[View]      main.py ── 시그널 바인딩만 (Controller 포워딩 수신)
[Control]   controller.py ── MediaController: DownloadWorker + AnalyzeWorker 통합 관리
[Worker]    downloader.py ── AnalyzeWorker + DownloadWorker 정의 (변경 없음)
```

### 검증
- `py_compile` 3개 모듈 OK (controller.py, main.py, downloader.py)
- 좀비 워커 패턴 유지: `spawn_analyzer()` 호출 시 기존 워커 자동 유기
- 시그널 포워딩 패턴: Controller가 Worker 시그널을 View에 중개 (직접 노출 차단)

---

## 16. Node.js 22 런타임 번들 → 외부 참조 전환 (2026-09-04)

### 배경
- **문제점**: 포터블 빌드에 Node.js 22 런타임 전체가 번들되어 용량이 큼
- **해결**: 번들이 아닌 외부 라이브러리 참조로 전환. 시스템 Node.js 22+ 우선 사용 → 없으면 로컬 포터블 → 마지막으로 다운로드

### 수정 내용

#### pot_provider.py — node_exe() 및 ensure_node_runtime()
| 항목 | 변경 |
|------|------|
| `node_exe()` 후보 순서 | 캐시된 포터블 → **시스템 PATH → 캐시된 포터블 → frozen 번들** |
| `ensure_node_runtime()` | 시스템 Node.js 22+ 우선 확인 → 있으면 즉시 반환 (npm도 함께 확인) |
| 다운로드 트리거 | 시스템/로컬 모두 없을 때만 다운로드 (기존 로직 유지) |
| 포터블 빌드 | 첫 실행시 다른 DEPS와 함께 다운로드 (번들 제거) |

### 런타임 탐색 순서

**Before**:
```
1. 캐시된 포터블 node (번들)
2. frozen 번들
3. 시스템 PATH (폴백)
```

**After**:
```
1. 시스템 PATH (shutil.which("node") 또는 shutil.which("node.exe") — 22+ 확인)
   - Windows: shutil.which("node")가 실패할 수 있어 node.exe도 시도
2. 캐시된 포터블 node (로컬 다운로드, OS별 exe_name 구분)
3. frozen 번들 (레거시)
4. 둘 다 없으면 다운로드 트리거
```

### 검증
- `py_compile` OK (pot_provider.py)
- 시스템 Node.js 22+ 존재 시 즉시 반환 (npm도 함께 확인)
- 시스템 Node.js 미설치 시 기존 로직 (로컬 → 다운로드) 유지
- Windows/macOS 모두 호환 (node.exe / node 자동 인식)

---

## 17. 다른 DEPS OS 호환성 검토 및 수정 (2026-09-04)

### 배경
- Node.js 22 외부 참조 전환에 맞춰 다른 의존성(FFmpeg)의 OS 호환성도 검토
- Windows에서 `shutil.which("ffmpeg")`가 실패할 수 있어 `ffmpeg.exe`도 시도해야 함
- Linux용 ffmpeg 자동 수급 기능 추가 (기존에는 Windows/macOS만 지원)

### 수정 내용

#### client_opts.py — _apply_ffmpeg_opts()
| 항목 | 변경 |
|------|------|
| ffmpeg 검색 | `shutil.which("ffmpeg")` → `shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")` |
| 호환성 | Windows/macOS/Linux 모두 지원 |

#### components.py — ensure_ffmpeg()
| 항목 | 변경 |
|------|------|
| 시스템 ffmpeg 검색 | `shutil.which("ffmpeg")` → `shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")` |
| OS별 분기 | `sys.platform` 기반으로 Windows/macOS/Linux 명시적 분기 |
| Linux 지원 추가 | `_ensure_ffmpeg_linux()` 함수 신설 |

#### components.py — _ensure_ffmpeg_linux() (신규)
| 항목 | 내용 |
|------|------|
| 1순위 | 시스템 패키지 매니저 (apt/dnf/pacman) 자동 감지 및 설치 |
| 2순위 | johnvansickle.com 정적 빌드 다운로드 (amd64) |
| 압축 해제 | tar.xz 형식, ffmpeg/ffprobe만 선별 추출 |
| 실행 권한 | `os.chmod(0o755)` 자동 부여 |

### OS별 DEPS 호환성 현황

| DEPS | Windows | macOS | Linux |
|------|---------|-------|-------|
| Node.js 22 | `node.exe` / `node` | `node` | `node` |
| FFmpeg | `ffmpeg.exe` / `ffmpeg` | `ffmpeg` | `ffmpeg` |
| yt-dlp | Python 패키지 (OS 무관) | Python 패키지 | Python 패키지 |
| streamlink | Python 패키지 (OS 무관) | Python 패키지 | Python 패키지 |

### 검증
- `py_compile` OK (client_opts.py, components.py)
- Windows에서 `ffmpeg.exe` 자동 인식
- Linux에서 시스템 패키지 매니저 자동 감지 (apt/dnf/pacman)


---

## 16. components.py 퍼사드 + 전략 패턴 리팩토링 (2026-09-05)

### 배경
- **문제점 1**: `ensure_ffmpeg()` 내부에 Windows 다운로드 로직이 인라인으로 존재 → OS별 로직 분리 실패
- **문제점 2**: `shutil.which("ffmpeg.exe")`를 macOS/Linux에서도 무지성 호출 → 플랫폼 의존성 흩어짐
- **문제점 3**: 확장자 하드코딩이 여러 곳에 분산 → 유지보수성 저하

### 수정 내용 (퍼사드 + 전략 패턴 적용)

#### 아키텍처 변경

**Before**:
```python
def ensure_ffmpeg(log, force=False):
    # Windows 로직이 인라인으로 존재
    if sys.platform == "darwin":
        return _ensure_ffmpeg_macos(log, force)
    elif sys.platform == "linux":
        return _ensure_ffmpeg_linux(log, force)
    # ... Windows 코드 직접 구현 ...
```

**After (퍼사드 + 전략 패턴)**:
```python
# [퍼사드] 외부 호출용 단일 진입점
def ensure_ffmpeg(log, force=False):
    """OS를 전혀 신경 쓰지 않아도 되는 깔끔한 인터페이스"""
    # 1. 시스템 탐색 → 2. 로컬 캐시 확인 → 3. 전략에 위임
    return _ensure_ffmpeg_by_platform(log, force)

# [유틸리티] 확장자 하드코딩 중앙 집중화
def _exe_suffix() -> str:
    return ".exe" if sys.platform == "win32" else ""

# [디스패처] OS별 전략에 작업을 위임
def _ensure_ffmpeg_by_platform(log, force):
    if sys.platform == "win32":    return _ensure_ffmpeg_windows(log, force)
    elif sys.platform == "darwin":  return _ensure_ffmpeg_macos(log, force)
    elif sys.platform.startswith("linux"): return _ensure_ffmpeg_linux(log, force)

# [전략 함수들] 각 OS별 완전히 캡슐화된 구현
def _ensure_ffmpeg_windows(log, force): ...  # 신규 생성
def _ensure_ffmpeg_macos(log, force): ...    # 기존 유지
def _ensure_ffmpeg_linux(log, force): ...    # 기존 유지
```

#### 신규 추가 함수

| 함수명 | 책임 | 위치 |
|--------|------|------|
| `_exe_suffix()` | OS별 실행 파일 확장자 반환 (`.exe` / `""`) | 181번 줄 |
| `_ensure_ffmpeg_by_platform()` | 플랫폼 감지 후 적절한 전략 함수에 위임 | 186번 줄 |
| `_ensure_ffmpeg_windows()` | Windows 전용: GitHub GyanD/codexffmpeg 다운로드 로직 | 199번 줄 |

#### ensure_ffmpeg() 간소화

| 항목 | 변경 |
|------|------|
| 시스템 탐색 | `_exe_suffix()` 사용하여 OS별 확장자 자동 처리 |
| 로컬 캐시 확인 | `ffmpeg_exe()` 호출 (공통 로직) |
| OS별 분기 | `_ensure_ffmpeg_by_platform()` 호출로 완전 위임 |
| Windows 로직 | 제거 (별도 함수로 분리) |

### 핵심 개선 포인트

| 항목 | 기존 | ✅ 개선 후 |
|------|------|-----------|
| **확장자 분기** | `sys.platform == "win32"` 분기가 여러 곳에 흩어짐 | `_exe_suffix()` **단일 함수**로 중앙 집중화 |
| **Windows 로직** | `ensure_ffmpeg()`에 인라인으로 존재 | `_ensure_ffmpeg_windows()`로 **완전 분리** |
| **확장성** | if-elif 수동 분기 추가 필요 | `_ensure_ffmpeg_by_platform()` 디스패처에 분기만 추가 |
| **에러 처리** | `RuntimeError` 발생 가능성 | 문자열 반환으로 기존 일관성 유지 |

### 부가 효과

- **테스트 용이성**: 각 OS 전략을 독립적으로 모킹 가능
- **단일 책임 원칙**: 한 함수가 한 역할만 수정
- **개방-폐쇄 원칙**: 새로운 OS 추가 시 디스패처에 분기만 넣으면 됨
- **코드 가독성**: 퍼사드는 입구 역할만, 실제 작업은 전략 함수에서 처리

### 검증
- `py_compile` OK (components.py)
- Windows/macOS/Linux 각 플랫폼 시뮬레이션 테스트 PASS
- `_exe_suffix()` 정상 동작 확인 (win32 → `.exe`, 나머지 → `""`)
- `_ensure_ffmpeg_by_platform()` 분기 정상 동작 확인

