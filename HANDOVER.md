# HANDOVER.md — ChzzkTube 인수인계서

> 이 문서는 다음 담당자(사람 또는 AI 에이전트)를 위해 작성된 프로젝트 인수 문서다.
> 코드 수정 전 반드시 **§5 불변식**과 **§6 검증 워크플로우**를 읽을 것.
> 마지막 갱신: 설정창 라이브 적용 전환 (변경 즉시 저장 — 취소/완료 버튼 폐지)

---

## 1. 프로젝트 개요

- **ChzzkTube**: YouTube/치지직(Chzzk) 영상 다운로더 GUI 앱 (Windows 우선)
- **버전**: `v3.0.2 (PyQt6안정화버전)` — 정의 위치 `config._APP_VERSION`
- **스택**: Python + PyQt6 + qfluentwidgets(Dark 테마) + yt-dlp + streamlink + FFmpeg(리먹싱)
- **진입점**: `main.py` (`python main.py`)
- **빌드**: PyInstaller — `ChzzkTube.spec` (entry: `main.py` ✓ 수정됨)
- **설정 파일**: `dl_config.json` (CONFIG_DIR에 생성, UTF-8 / indent=4)

## 2. 실행 환경

| 항목 | 상태 |
|------|------|
| PyQt6, PyQt6-Fluent-Widgets, yt-dlp | 현재 환경에 설치 완료 |
| streamlink | 설치됨 (8.5.0) |
| requirements.txt | **생성 완료** — PyQt6 6.11.0 / PyQt6-Fluent-Widgets 1.11.3 / yt-dlp 2026.8.19 / streamlink 8.5.0 고정 |
| FFmpeg | 런타임 필요 (media.py 리먹싱) |
| D2Coding-Regular.ttf | BASE_DIR에 있으면 로드 (콘솔 폰트) |

## 3. 아키텍처 (4계층 · 역방향 참조 0 · 순환 import 0)

```
[View]      main(825) ─ dialogs(799) · theme(283) · log_console(327) · ui_components(11)
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
| `media` | map_res, format_bytes, codec rank, remux_stream, remux_live_to_container |
| `chzzk_api` | 치지직 클립 공개 API 분석 (yt-dlp 우회 경로) |
| `cookies` | Firefox/Chromium 쿠키 DB 추출 |
| `config` | 경로(frozen/dev), 기본값, 로드/저장 — 제로 의존 leaf |
| `utils` | clean_ansi, get_filename_template, _open_windows_explorer, parse_sec |
| `ui_components` | CustomComboBox |
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
    log_concise(str, bool, bool) : (텍스트, is_status, is_error) 간결 로그
    log_full(str)                : yt-dlp 원본 로그 라인

DownloadWorker(targets, cfg, state_dict, v_sel, a_sel, is_live_hint=False, v_spec=None):
    progress_update(float, str)  : (진행률 %, 속도 문자열)
    status_update(int, int, str) : (현재 인덱스, 전체 수, 현재 URL)
    log_concise / log_full       : 동일
    finished_all(int, int)       : (성공 수, 실패 수)

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
① python -m py_compile main.py downloader.py dialogs.py utils.py ui_components.py \
   config.py media.py cookies.py chzzk_api.py theme.py log_console.py controller.py \
   bump_version.py sync_mirrors.py updater.py        # ALL = 0
② python smoke_test.py                    # headless(Qt offscreen) 실구동 [PASS], exit 0
③ python sync_mirrors.py                  # 누락 0 확인
```
smoke_test가 검증하는 것: 전 모듈 import, config 로드, MainWindow 실제 생성,
DownloadWorker 시그널/메서드 계약, 간결 로그 append 반영.
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

## 9. 남은 과제 (우선순위순)
## 9. 남은 과제 (우선순위순)

1. **`.gitattributes` eol 정규화** — diff 노이즈 제거
2. **AnalyzeWorker의 컨트롤러 이관** — DownloadController와 대칭 완성 (선택)
3. **MainWindow 잔여 상태 로직**(on_download_finished의 요약/사운드 분기 등) 컨트롤러화 — 회귀 리스크 大, 신중히
4. `versions/` 정리 및 git 태그화 여부 결정
5. 유튜브 라이브: 배치(txt) 안의 watch?v= 라이브 URL은 힌트가 없어 VOD
   경로로 감(다운로드 자체는 되지만 ffmpeg 강제 다운로더 문제가 재발).
   필요 시 다운로드 전 경량 is_live 프리체크 도입을 검토할 것.

## 10. 하지 말 것

- state/cfg 딕셔너리를 복사해서 워커에 넘기는 것
- smoke_test 통과 없이 리팩토링 커밋하는 것
- .md 미러를 손으로 고치는 것 (항상 .py가 원본)
- GUI 없는 CI 가정으로 Qt 코드를 임포트만으로 검증 끝이라 착각하는 것 — smoke_test(offscreen)를 돌릴 것
- 배포 시의 완벽한 포터블(Portable) 무결성을 침범하는 행위
