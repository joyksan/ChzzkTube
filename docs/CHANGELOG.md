### 2026-09-22 — v3.8.1 : 폴백 완전 제거·URL 검증 게이트·표준 에러 헬퍼·POT 상태 수정 (patch)

#### 배경 (v3.8.0 → v3.8.1)
- **폴백 타이머 완전 제거**: 15초 강제 언락(`force_unlock`) 제거 — deps 수급 실패 시 영구 잠금, 사용자 재시도(ENTER) 대기. 프리웜 중 `defer_fallback_timer()` 제거, `_on_pot_activity()` 연결 해제, `force_unlock()` 완전 삭제.
- **URL 검증 게이트 2중 방어**: `MediaController._is_valid_url()` 순수 게이트 신설(스킴 + 도메인 + `_DOMAIN_EXTRACTORS` SSOT suffix 매치). `MediaController.parse_targets`가 비URL 항목 발견 시 `ValueError("Invalid URL format: …")`로 배치 전체 차단. `toggle_download` 1차 게이트 + `_start_download` 2차 방어선.
- **표준 에러 헬퍼 전면 적용**: `emit_error_standard` / `emit_error_warn` 전면 도입 — 포맷 `원인: <기술적 원인> → 해결: <시도 중인 해결책>` 통일. `fallback`/`timeout` 등 내부 용어 노출 금지, dyld/URLError/traceback 등 저수준 예외 TUI 노출 금지.
- **POT 상태 의미 명확화**: `staged`(prewarm 완료, gate 미시작) ≠ `ready`(gate 완료, 토큰 서빙 중). `staged`를 `ready`로 오해하던 버그 수정, `pot_ready`는 `ready`일 때만 True.
- **폴백 타이머 완전 제거**: 15초 강제 언락(`force_unlock`) 제거 — deps 수급 실패 시 영구 잠금, 사용자 재시도(ENTER) 대기. 프리웜 중 `defer_fallback_timer()` 제거, `_on_pot_activity()` 연결 해제, `force_unlock()` 완전 삭제.

#### 모듈 변경

| 모듈 | 변경 |
|------|------|
| `ui/main_window.py` | 폴백 타이머·유예·강제언락 완전 제거. `deps` 실패 시 `[ ENTER: Retry Setup ]` 버튼으로 재시도. `deps` 에러 시 `ENTER`로 재시도. |
| `control/startup_coordinator.py` | `force_unlock()` 완전 삭제. `report_upgrade`/`report_pot` 실패 시 `emit_error_standard` 사용. `staged` ≠ `ready` 구분 적용. `deps_error_msg` 영구 보관으로 재시도 전까지 READY 차단. |
| `control/startup_state.py` | `deps_error_msg` 필드 추가 — 폴백 제거로 에러 상태 영구 보관. `can_emit_ready()`에 `deps_error_msg` 체크 추가. |
| `control/pot_manager.py` | `_note` 호출을 `emit_error_standard`/`emit_error_warn`로 통일. ffmpeg bind fail 시 표준 에러 헬퍼 사용. |
| `pipeline/target_downloader.py` | 즉시 TUI 발행 금지 — `_emit_error_log`는 기록만, finalizer에서 단일 출력. 즉시 TUI 발행 코드 제거. |
| `pipeline/progress_emitter.py` | `log_success_info` 중간 스트림(.fNNN) 은닉(`to_tui=False`). `pp_hook` 신설 — postprocessor 완료 시 최종 결과물 1줄만 발행. |
| `control/startup_coordinator.py` | `report_upgrade`/`report_pot` 실패 시 `emit_error_standard` 사용. `force_unlock` 호출 제거. |
| `control/pot_manager.py` | ffmpeg/binding 실패 시 표준 에러 헬퍼(`emit_error_standard`/`emit_error_warn`) 사용. bind fail 시 표준 에러 헬퍼. |
| `pipeline/target_downloader.py` | 즉시 TUI 발행 금지 — `_emit_error_log`는 기록만, finalizer에서 단일 출력. 즉시 TUI 발행 코드 제거. |
| `pipeline/progress_emitter.py` | `log_success_info` 중간 스트림(.fNNN) 은닉(`to_tui=False`). `pp_hook` 신설 — postprocessor 완료 시 최종 결과물 1줄만 발행. |
| `control/startup_coordinator.py` | `report_upgrade`/`report_pot` 실패 시 `emit_error_standard` 사용. `force_unlock` 호출 제거. |
| `control/pot_manager.py` | ffmpeg/binding 실패 시 표준 에러 헬퍼(`emit_error_standard`/`emit_error_warn`) 사용. bind fail 시 표준 에러 헬퍼. |
| `pipeline/target_downloader.py` | 즉시 TUI 발행 금지 — `_emit_error_log`는 기록만, finalizer에서 단일 출력. 즉시 TUI 발행 코드 제거. |
| `pipeline/progress_emitter.py` | `log_success_info` 중간 스트림(.fNNN) 은닉(`to_tui=False`). `pp_hook` 신설 — postprocessor 완료 시 최종 결과물 1줄만 발행. |
| `control/startup_coordinator.py` | `report_upgrade`/`report_pot` 실패 시 `emit_error_standard` 사용. `force_unlock` 호출 제거. |
| `control/pot_manager.py` | ffmpeg/binding 실패 시 표준 에러 헬퍼(`emit_error_standard`/`emit_error_warn`) 사용. bind fail 시 표준 에러 헬퍼. |
| `pipeline/target_downloader.py` | 즉시 TUI 발행 금지 — `_emit_error_log`는 기록만, finalizer에서 단일 출력. 즉시 TUI 발행 코드 제거. |
| `pipeline/progress_emitter.py` | `log_success_info` 중간 스트림(.fNNN) 은닉(`to_tui=False`). `pp_hook` 신설 — postprocessor 완료 시 최종 결과물 1줄만 발행. |
| `control/startup_coordinator.py` | `report_upgrade`/`report_pot` 실패 시 `emit_error_standard` 사용. `force_unlock` 호출 제거. |
| `control/pot_manager.py` | ffmpeg/binding 실패 시 표준 에러 헬퍼(`emit_error_standard`/`emit_error_warn`) 사용. bind fail 시 표준 에러 헬퍼. |

#### 설계 원칙 보강
1. **단일 격리(Single Isolated Runtime)**: 실행체 해석은 `writable_base()` 및 `.pylib` 오버레이만 — 시스템 PATH/패키지 매니저 참조 0건.
2. **순정 우선, POT 승격**: Layer 1~2는 yt-dlp 순정 위임(EJS 솔버 포함), 실패·1080p 미달 시에만 Layer 3 POT 승격. 720p `tv` 타협 폐기.
3. **워커 스레드 경계**: 워커는 뷰 소유 QObject(POTManager)에 접근하지 않고, L0/L1 순수 인프라만 호출.
3. **입력 게이트 2중 방어**: 파싱 단계(배치 전체 차단) + 워커 구동 직전 재검증.
4. **로그 단일 발행**: FAIL은 finalizer 1회, ANAL 마감은 명세 4행, DL 중간 스트림은 은닉.
5. **폴백 완전 제거**: 15초 강제 언락(`force_unlock`) 제거 — deps 수급 실패 시 영구 잠금, 사용자 재시도(ENTER) 대기. 프리웜 중 `defer_fallback_timer` 제거, `_on_pot_activity` 연결 해제.

#### 검증
- 전체 pytest **304 passed**
- `python -m compileall -q chzzktube` 통과
- 실측: `afqweqasd` 게이트 차단(`Invalid URL format: afqweqasd`) / `https://youtu.be/...` 통과 / 앱 코드 `shutil.which(` 호출 0건 / 격리 캐시 부재 시 `ffmpeg_exe() → None`(시스템 ffmpeg 무시)
- 회귀 계약 테스트 개정: `test_analysis_retry.py`(순정 단일 호출 계약), `test_gate_integration.py`·`test_pipeline_regressions.py`(TUI 포맷·`subscriber_only` 게이트)

---

### 2026-09-20 — v3.8.0 : 단독 환경 격리·입력 게이트·Layer 3 POT 수리·TUI 정제 (minor)

#### 배경 (v3.7.2 → v3.8.0)
- **CLI vs App 동작 불일치**: CLI는 `--cookies`만으로 멤버십·1080p+ 수급되지만 앱은 실패. 근본 원인은 쿠키 감지 시 `player_client`를 `web`으로 강제 고정하던 구 로직(→ PO 토큰 없는 `web` 요청은 이미지 포맷만 반환)이었다. v3.7.2에서 순정 위임은 완료됐으나 잔재가 남아 있었다.
- **시스템 환경 간섭**: `shutil.which`·`brew install`·`apt-get`이 사용자 PC의 구버전 바이너리/오염 플러그인을 참조할 위험.
- **무검증 억지 다운로드**: `afqweqasd` 같은 임의 문자열 입력 시 분석 검증 없이 DownloadWorker가 실행되어 `[generic] Extracting URL` → `DL FAIL` 3~4줄 중복 발행.
- **Layer 3 POT 준비의 잠재 결함**: `target_downloader._download_vod`가 존재하지 않는 `POTManager.instance()`를 호출 — POT 재시도 경로 진입 시 `AttributeError`로 즉사(게다가 POTManager는 뷰 소유 QObject라 워커 스레드 접근은 스레드 경계 위반).

#### 모듈 변경

| 모듈 | 변경 |
|------|------|
| `infra/node_provider.py` | `node_exe()`·`ensure_node_runtime()`에서 시스템 PATH/`shutil.which("node"\|"npm")` 전면 제거 — 오직 `writable_base()/node` 포터블 + frozen 번들만 판정·수급 |
| `infra/components.py` | `ensure_ffmpeg`의 시스템 ffmpeg 최우선 로직 제거 → 격리 캐시 선검(파손 캐시 제거) 후 정적 바이너리 수급. `brew install`·`apt-get/dnf/pacman` 서브프로세스 철폐(Homebrew bottle은 HTTP 직접 다운로드 유지). `ffmpeg_exe()`의 `shutil.which` 폴백 제거. `_wire_ffmpeg_path` 디버그 로깅 정리 |
| `infra/updater.py` | `_cli_base()`를 실행체 단일 격리로 재작성 — ytdlp/streamlink는 앱 인터프리터 `-m` 실행(오버레이 우선), ffmpeg/node/npm은 격리 캐시 리졸버 단일 참조. `check_deps`도 `components.ffmpeg_exe()`/`pot_provider.node_exe()` 경유로 판정 |
| `infra/pot_server.py` | npm 해석의 `shutil.which("npm")` 폴백 제거 — npm-cli.js → `npm_exe()` 단일 경로, 없으면 명시적 오류 |
| `core/client_opts.py` | `_apply_ffmpeg_opts`가 `components.ffmpeg_exe()`(격리 캐시)만 참조 |
| `pipeline/target_downloader.py` | **[근본 수리]** `_ensure_pot_server_ready()` 신설 — L0 `po_client.server_ping` + L1 `pot_server`의 순수 스폰/빌드 헬퍼(프리웜 락)만 사용해 워커 스레드에서 안전하게 Layer 3 준비. `_FormatQualityLoss`/`_max_requested_height`/`_needs_pot_promotion` 신설 — 1080p 미달 수급 시 720p 타협 없이 POT 승격(사용자 해상도 제한·수동 포맷 선택은 제외). POT 미가용 시 1차 수급본을 파기하지 않고 `hd unavailable — kept Np`로 정직 보고. `_emit_vod_success`로 성공 라인 발행 단일화. `_emit_error_log`는 기록 전용(TUI 즉시 발행 철폐) |
| `pipeline/progress_emitter.py` | `log_success_info`가 중간 임시 스트림(`.f399`/`.f251`)을 TUI에서 은닉(`to_tui=False`). `pp_hook` 신설 — postprocessor 완료 시 최종 결과물 1줄만 발행(중복 방지) |
| `pipeline/finalizer.py` | 개별 실패 라인의 **유일 발행점**으로 확정 — 배치 마감 시 1회 정갈 출력(중복 FAIL 로그 3~4줄 원천 차단) |
| `control/controller.py` | `_is_valid_url()` 순수 게이트 신설(스킴 + 도메인 + `_DOMAIN_EXTRACTORS` SSOT suffix 매치), `parse_targets`가 비URL 항목 발견 시 `ValueError("Invalid URL format: …")`로 배치 전체 차단 |
| `ui/main_window.py` | 게이트 배선(1차 `toggle_download`, 2차 `_start_download` 방어선). `on_analyze_error`에서 `extracted_data` 즉시 초기화(잔여 데이터 억지 다운로드 차단) + 멤버십/연령제한 시 `CookieSelectDialog` 자동 팝업. `stop_analysis_anim`을 ANAL 마감 정갈 명세(complete → 제목·채널 → 가용성 → 대표 포맷)로 재작성. `_emit_format_logs`를 `[codec] · [codec]` 형식으로 정제. 종료 시 다운로드 워커 `wait(1000)` 추가 |
| `core/log_emitter.py` | `analysis_done_msg()` 상수 신설 — ANAL 마감 문구 단일 출처 |

#### 설계 원칙
1. **단일 격리(Single Isolated Runtime)**: 실행체 해석은 `writable_base()` 및 `.pylib` 오버레이만 — 시스템 PATH/패키지 매니저 참조 0건.
2. **순정 우선, POT 승격**: Layer 1~2는 yt-dlp 순정 위임(EJS 솔버 포함), 실패·1080p 미달 시에만 Layer 3 POT 승격. 720p `tv` 타협 폐기.
3. **워커 스레드 경계**: 워커는 뷰 소유 QObject(POTManager)에 접근하지 않고, L0/L1 순수 인프라만 호출.
4. **입력 게이트 2중 방어**: 파싱 단계(배치 전체 차단) + 워커 구동 직전 재검증.
5. **로그 단일 발행**: FAIL은 finalizer 1회, ANAL 마감은 명세 4행, DL 중간 스트림은 은닉.

#### 검증
- 전체 pytest **297 passed** (신규 `test_url_gate.py` 19건 + `test_v38_contracts.py` 27건 포함)
- `python -m compileall -q chzzktube` 통과
- 실측: `afqweqasd` 게이트 차단(`Invalid URL format: afqweqasd`) / `https://youtu.be/...` 통과 / 앱 코드 `shutil.which(` 호출 0건 / 격리 캐시 부재 시 `ffmpeg_exe() → None`(시스템 ffmpeg 무시)
- 회귀 계약 테스트 개정: `test_analysis_retry.py`(순정 단일 호출 계약), `test_gate_integration.py`·`test_pipeline_regressions.py`(TUI 포맷·`subscriber_only` 게이트)

### 2026-09-19 — v3.7.2 : yt-dlp 순정 클라이언트 로테이션 완전 위임 (minor)
- **핵심 변경**: 앱 레벨 수동 클라이언트 로테이션(`_RETRY_CLIENTS`, `client_chain`) 완전 제거 → **yt-dlp 순정 단일 `auto` 호출로 위임**
  - yt-dlp 내부 `_DEFAULT_CLIENTS`(`web_embedded` → `tv_downgraded` → `web_safari` → `mweb` → `tv`...) + EJS 솔버(deno/node) 자동 작동
  - CLI와 100% 동일 동작: `web_embedded` → `tv_downgraded` → JS 챌린지 해결 → 1080p+Opus 확보 검증 완료
  - 수동 폴백 체인(`web_embedded`→`web_safari`→`mweb`→`tv`) 삭제로 코드 ~150줄 감소
- **3계층 파이프라인 재설계**:
  - **Layer 1 (순정 위임)**: `player_client="auto"` 단일 호출 → 공개/멤버십(쿠키有) 1080p+ 즉시 해결
  - **Layer 2 (POT 서버)**: `age_limit>0` 또는 봇체크/포맷상실 감지 시에만 기동
  - **Layer 3 (재시도)**: PO token + visitorData 주입하여 동일 순정 호출 재시도 (1회만)
- **POT 게이트 정단화**: `subscriber_only`(멤버십) 게이트 제거 — Layer 1에서 쿠키+EJS로 해결
  - `main_window._POT_AVAIL_GATED`, `classifier._POT_AVAIL_GATED`에서 `subscriber_only` 삭제
  - `needs_pot = age_limit > 0`만 남김 (연령제한 전용 인터락)
- **수정된 파일**: `client_opts.py`, `analyze_worker.py`, `target_downloader.py`, `live_recorder.py`, `main_window.py`, `classifier.py`

### 2026-09-19 — v3.7.1 : 5대 구조적 결함 수정 (patch)
...

### 2026-09-18 — v3.7.0 : download pipeline contract overhaul (minor)
- **배경**: 다운로드 파이프라인 계약 분산·불일치 누적 — 반환 타입 혼재(str/dict/ClassifiedTarget), VOD 폴백 `tv→web_safari→web`(360p 고착), PO 토큰 `web_embedded` vs `player_client` 불일치(0% stall), terminal failure까지 봇 차단으로 오판(4단계 헛돌기), `skip_targets` 연결 누락, 분석 워커 Mock 잔재, 쿠키 정책 판정 이중화
- **핵심 변경**:
  - `pipeline/classifier.py` 신규: `ContentKind`(LIVE_YOUTUBE/LIVE_CHZZK 분리), `StreamCapability`(TriState None + `could_have_*` 방어 메서드), `CookiePolicyContext`, `ClassifiedTarget`, `ItemClassifier` 순수 분류 엔진
  - `target_downloader.py`: 품질 우선 폴백 `web→web_safari→ios→tv`, terminal fail-fast, PO 토큰 1:1 바인딩(web/web_safari만, ios/tv 미주입), `download_target` 반환값 `True/"skip"/False` 명시, `_flatten`/`_normalize_single_item`/`expand_targets` 모두 `List[ClassifiedTarget]` 반환
  - `finalizer.py`: `skip_targets` 파라미터, `DONE/WARN/FAIL/ABORT` 상태 세분화, `batch finished (success: N, fail: M, skip: K)` 포맷
  - `downloader.py`: `item.url` 접근 통일, `skip_targets` 전달
  - `analyze_worker.py`: 빈 `YoutubeDL` Mock 제거
  - `tests/conftest.py`: `pytest_configure` `.pylib` bootstrap, `yt_dlp.__path__` 동기화, `raw_log` flush fixture
- **설계 원칙**: 단일 계약(SSOT) — `has_video/has_audio=None` 보존, `could_have_*()` 안전 질의 / 품질 우선 폴백 / PO 토큰 정합성 / terminal fail-fast / Skip 집계 / 쿠키 정책 SSOT(`_apply_cookie_opts` ≡ `_has_configured_cookies`)
- **검증**: pytest **239 passed**, compileall OK, 실측: 멤버십/연령제한/삭제 → `DL │ SKIP │ YT │ [age/member gated]`, 최종 요약 `skip` 카운트

---

### 2026-09-18 — v3.6.4 : analysis dead-end fix — EJS JS runtime + cookie-aware rotation + TUI notice dialog
- **근본 원인**: yt-dlp의 기본 JS 런타임은 `deno`(PATH 탐색)뿐이고 앱이 PATH 밖(`~/.chzzktube/node`)에 자체 수급한 포터블 Node.js를 탐색하지 못해 n-challenge(EJS) 해결이 불가능 → "No video formats found" 회전 실패로 이어졌다.
- `client_opts._apply_ejs_opts` — `node_provider.node_exe()`로 탐색한 포터블 node를 `js_runtimes={'node': {'path': ...}}`로 명시 주입(분석/라이브/다운로드 4 경로 커버). node 없으면 기본(deno) 유지.
- `analyze_worker` — 회전 후보 `ios`(쿠키 미지원 → yt-dlp 스킵 즉사) → `["tv", "web_safari"]`(쿠키 호환)로 교체; bot-block 판정에 "no video formats found"/"requested format is not available" 포함해 회전 완주.
- `analyze_worker` — 최종 analysis error를 60자로 절약(TUI MSG 컬럼 예산); `[youtube] <id>:` 접두와 보고서 꼬리(`; please report…`, `Use --list-formats`) 절삭.
- `target_downloader` — "Requested format is not available" 분류에 `is` 누락 교정 + no-video-formats → `format missing`.
- `ui/dialogs.py` — `TuiNoticeDialog`(280×125·칠흑·중앙정렬·OK/View 2버튼) 신설; `show_info_message`를 위임해 쿠키 완료/초기화/브라우저 오류 안내도 동일 규격. 쿠키 흐름 사용자 문자열 한국어→영어(§5).
- 검증: 문제 URL 실측(일반 31포맷, 멤버십 `0VxDq_vzXcg` 9포맷 `&t=&pp=` 포함) + pytest **239 passed** + offscreen UI 스모크(중앙정렬/2버튼/RESULT_ALT 코드).
- 커밋: `8408103`(근본수정) `0b42775`(분류 교정) `95c179f`(분기 보강) `dd24cd1`(UI 통일)

---

### 2026-09-17 — v3.6.3 : architecture contract restoration (P0–P2 audit)
- **워치독 단일 진실**: gate QTimer 폐지(`_gate_watchdog_active` 플래그), fallback `_fallback_timer` 단일 판정(`_fallback_watchdog` 삭제), analysis watchdog 3 spawn-site arm/disarm(§5-21: 성공/실패/타임아웃/Esc/클리어 disarm; polling은 disarmed 워치독 skip).
- `DownloadContext` — `_last_tick_t/_live_proc/_meta_logged` 필드 선언.
- `DownloadWorker.run` finally → `_fin.finalize(ctx, …, notify=False)` → `finished_all.emit` 정확히 한 번(분석/충전/다운로드/파이널라이즈/로그/예외 전부 생존).
- `live_recorder` — stdout-relay 단일 소유권: FFmpeg `pipe:1` → Python이 TS 기록(임시본 replace-on-success, 실패/취소 시 TS 유지, empty→False).
- `analyze_worker` — `ctrl.spawn_analyzer()` 명시 재시도, streamlink 5-arg TypeError 수정, `ANALYSIS_TIMEOUT_SEC` import 정리.
- Chzzk live v2 API: `_analyze_chzzk_live_v2`(v2/channels/{hash}/live-detail → `livePlaybackJson` HLS) + numeric-id v1 fallback; 32-hex 채널 해시는 channel id(v1 404 루트케이즈), `status=OPEN`+`live.status=STARTED`→PROGRESS.
- `playlist.normalize_youtube_channel_url` — `releases|live|community|membership|podcasts` 보존, `/videos` 강제-rewrite 회귀 방지.
- URL sweep(16 URLs) 분석/라우팅 레벨 검증(Chzzk clip/VOD API OK; YouTube VOD/live/shorts/playlist/watch+list/channel tabs OK; 멤버십 전용은 쿠키 필요 — 기대 동작).
- 검증: pytest **227 passed**, `test_coordinator.py` 20× 반복 무실패, py_compile·`git diff --check` clean.
- 커밋: `ab03548`(중간 체크포인트·31파일) `d8b0ad4`(chzzk live 브랜치 + Context 동기화) `1c7d9f8`(POT gate 단일 워치독) `6bc49d1`(fallback timer single authority) `4dd88b3`(analysis watchdog arm/disarm) `6f3cad7`(chzzk v2 live-detail path) `59cf630`(채널 탭 정규화 + 라우팅 경계)



- `infra/platform.py` 신설 — 크로스플랫폼 HAL 단일 격리 계층
  - `is_windows()` / `is_macos()` — `sys.platform` 단일 판정 출처
  - `spawn_kwargs()` / `daemon_spawn_kwargs()` — 용도별 스폰 인자 분리 (Win: `CREATE_NO_WINDOW` / `CREATE_NEW_PROCESS_GROUP`, POSIX: `start_new_session=True`)
  - `flash_window(hwnd:int)` / `set_app_user_model_id()` / `play_beep()` / `reveal_in_file_manager()` / `exe_suffix()` — Qt 역의존 제로
  - `attach_to_parent_lifecycle()` / `kill_tree()` — Job Object / `killpg` 격리 (pot_server에서 이관)
  - 호출부 8개 모듈(`tool_log`, `node_provider`, `pot_server`, `updater`, `live_recorder`, `utils`, `main_window`, `components`) 완전 치환

- `core/watchdog.py` 신설 — 단일 진실 시간(`time.monotonic`) 기반 구독형 워치독
  - 상수 단일 출처: `FALLBACK_TIMEOUT_SEC=15`, `FALLBACK_GRACE_SEC=3`, `GATE_TIMEOUT_SEC=120`, `ANALYSIS_TIMEOUT_SEC=45`
  - `LivenessWatchdog` — `threading.Lock` + 주입 가능 `clock`으로 스레드 안전·테스트 가능
  - `heartbeat()` / `check_timeout()` / `reset()` / `elapsed()` / `remaining()` 상태 기계

- 워커/메인 배선 완전 전환
  - `AnalyzeWorker`: `QTimer` 맹인 타이머 **완전 제거** → `progress_hook`로 `heartbeat()` 연장
  - `DownloadWorker`: `_download_watchdog` + 타겟 전후 `heartbeat()`로 게이트/분석 타임아웃 연장
  - `MainWindow`: `_poll_watchdogs` 1초 폴링으로 3종 워치독(`fallback`/`gate`/`analysis`) 감시
  - 기존 `heartbeat`/`work_tick`/`pot_work_tick` 시그널명 유지 (§5-13 교통정리 준수)

#### 검증
- 전체 pytest **176 passed 0 failed** · smoke PASS · `sync_mirrors.py --check` 0건 · py_compile OK
- 버전 3중 정합: `config._APP_VERSION="v3.6.2"` / `pyproject.toml version="3.6.2"` / `uv.lock chzzktube==3.6.2`

---

### 2026-09-16 — v3.6.1 : 아키텍처 다이어그램(mermaid) 추가 — 문서 전용 패치

- `docs/architecture.md` 말미에 mermaid 3종 append: ① 전체 계층도(flowchart) ② 기동 시퀀스(sequenceDiagram) ③ 상태·워치독 관계(stateDiagram-v2)
- 소스 변경 없음(문서 패치) — §1.1.2에 따라 patch 버전 증가 및 3중 정합 유지
- 검증: `python -m pytest tests -q` (176 passed 0 failed) · smoke PASS · `sync_mirrors.py --check` 0건

---

### 2026-09-16 — v3.6.0 : 게이트 하드닝 — POT 트리 종료·2차 워치독·유예·deps FAIL·PO 재시도 (minor 업)

#### 후속 과제 전량 해소 (v3.5.2 §8.3 잔여 6건)
- **#1 POT 빌드 내부 하트비트**: `_communicate_with_ticks` — `communicate()` 무출력 대기를 tick_interval 주기로 반복 대기해 빌드 진행 하트비트 발화. 배선 `ensure_node_server` → `_POTWorker._tick` → `POTManager.pot_work_tick` → `defer_fallback_timer`. npm ci 장기 실행이 더 이상 "멈춤"으로 오인되지 않는다.
- **#2 POT 서브프로세스 트리 종료**: `kill_tree()` 신설 — Windows Job Object(`TerminateJobObject` + 핸들 부착·반납) / POSIX 프로세스 그룹(`start_new_session` 리더). `_POTWorker.request_interruption`·`_cleanup`의 자식 정리 사각지대를 트리 종료로 교정(`_child_procs` 레지스트리 실체화).
- **#3 gate hang 2차 워치독**: `_gate_watchdog`(120s) — READY 이후 `_pending_download` 대기 중 만기 시 `cancel()`(트리 킬) + `SYS │ WARN │ POT` + 큐 해제.
- **#4 위양성 폴백 분리**: `defer→grace` — 만기 시 체인이 실제 동작 중(POT/UpdateWorker running)이면 3s 유예 1회 후 재판정하고, F12 대기 원인을 `_log_gate_pending`으로 기록(TUI 예산 보존).
- **#5 deps FAIL 게이트 승격**: `UpdateWorker.deps_failed = Signal(list)` 신설 — `check_done(list)` 페이로드는 untouched(§5-13 교통 정리 유지), Main이 중계 후 `report_deps(False, "deps fail: …")`. stale(업데이트 대상)과 실제 FAIL을 분리.
- **#6 PO 서버 실패 시 재시도**: 분석 실패가 봇 체크/PO 토큰 마커(`_BOT_CHECK_MARKERS`)면 `ensure_ready("gate")` 후 URL당 1회 재분석 자동 큐잉 — `_pot_retry_done` 집합으로 무한 루프 차단, `textChanged` 디바운스로 재진입.

#### 검증
- 신규 회귀 9건: `test_pot_manager` 2건(하트비트·레지스트리) · `test_startup_gate_regressions` 7건(게이트 워치독 2·유예 2·deps 승격 1·재시도 판별 1·1회 한계 1)
- 전체 pytest **176 passed 0 failed** · smoke PASS · `sync_mirrors.py --check` 0건 · py_compile OK · 버전 3중 정합(`v3.6.0` / `3.6.0` / `3.6.0`)

---

### 2026-09-16 — v3.5.2 : READY 폴백 결함 3건 수리 — deps 게이트 의미 분리·크래시 시그널 분기·POT 프리웜 보존

#### 문제 (관측: 평범한 기동에서 "ready — input unlocked (fallback timeout)"이 출력)
- **P1 deps 게이트 의미 오용**: `_on_update_check_done`이 `report_deps(not bool(stale), …)`로 보고 → 업데이트가 감지된 **모든 기동**에서 `deps_ok=False` 고정 → `can_emit_ready()`가 사실상 영구 False → 정상 READY 대신 15초 폴백 문구로만 입력이 열리고, 그 15초 동안 입력이 잠겼다.
- **P2 upgrade 크래시 시 시그널 오발행**: `UpdateWorker.run()`의 except가 모드와 무관하게 `check_done`을 발화 → upgrade 워커의 `check_done`은 구독자 0(연결 지점은 `upgrade_done`) → `upgrade_done` 영구 미발화 → READY 게이트가 잠김.
- **P3 폴백이 프리웜을 종료**: `force_unlock()`이 `POTManager.cancel()`을 호출 → `_POTWorker._child_procs`는 append 0건이라 npm/tsc 자식을 죽이지 못한 채 QThread만 terminate → 고아 프로세스 잔존 + `prewarm-lock` 점유로 다음 기동 프리웜이 "prewarm skipped — build busy" 실패.
- **P3b 상태 논리 혼동**: `get_current_app_state()`가 `is_busy()`를 STARTUP 사유로 삼아, 프리웜 진행 중 `toggle_download`의 대기 분기("queued — waiting for pot server")가 **도달 불가 사문 코드**였다(ENTER 무반응).
- **P3c 무제한 서브프로세스**: `_run_and_stream_log`의 `communicate()`에 timeout 부재 → npm ci/tsc 무응답 시 프리웜 워커가 영구 점유 → `is_busy()` 고정 → POT 게이트 다운로드가 대기에서 풀리지 않는다.
- **P5 15초 단발 타이머의 맹점**: `QTimer.singleShot(15000, …)`는 대규모 수급(ffmpeg·node·pip 다운로드)이 진행 중인지 멈춘 것인지 구분하지 못했다 — 정상 진행 중에도 폴백이 발화해 문구가 오표기됐다.

#### 모듈 변경
| 모듈 | 변경 |
|------|------|
| `main_window.py` | `report_deps(True, …)` — deps 게이트를 "검사 단계 완료"로 의미 정정(P1). `get_current_app_state()`에서 `is_busy()` 제거 — 입력 잠금은 `_startup_completed`만 판정(P3b), POT 대기 분기 부활 |
| `update_worker.py` | 크래시 종료 시그널을 모드별로 분기(`upgrade` → `upgrade_done(False, "worker crash")`, check → `check_done([])`) + 중복 `import traceback` 제거(P2) |
| `startup_coordinator.py` | `force_unlock()`에서 `_pot.cancel()` 제거 — 폴백은 READY 발산만 담당, 프리웜은 백그라운드 존속(P3) |
| `pot_server.py` | `_run_and_stream_log(…, timeout=None)` + `TimeoutExpired → _kill(proc) → -1`. `_NPM_CI_TIMEOUT=600`·`_TSC_TIMEOUT=300` 적용(P3c) |
| `main_window.py`·`update_worker.py` | [P5] 15초 폴백을 인스턴스 타이머(`_fallback_timer`)로 승격 + `defer_fallback_timer()` 동적 워치독. `UpdateWorker.work_tick`(문자열 없는 하트비트) → pip·ffmpeg·node 수급 진행 중 카운트다운 되감기, POT `prewarm`/`starting`은 `_on_pot_activity` 경유 연장 |

#### 검증
- 신규 회귀 테스트 18건: `test_coordinator.py` 3건(deps 게이트 의미 1·폴백 프리웜 보존 2) · `test_startup_gate_regressions.py` 11건(신규) · `test_pot_server_timeout.py` 4건(신규)
- stale 테스트 정정: `test_download_pipeline.py::test_truncate_for_full_log` — HEAD `e156623` worktree 실측으로 **기존 실패**를 분리 확인한 뒤, 소스 정본(`configuration:` 블록 제거)에 맞춰 기대값을 재작성
- 전체 pytest **167 passed 0 failed**
- `python sync_mirrors.py --check` 0건 · `smoke_test` PASS · py_compile OK · 버전 3중 정합(`v3.5.2` / `3.5.2` / `3.5.2`)

---

### 2026-09-15 - v3.5.1 : UI/다이얼로그 전면 규격 교정 및 모던 TUI 개편

  - `ExitConfirmDialog`: 폭 축소(360×130 → 280×125) 및 경고 텍스트 중앙 정렬(`AlignCenter`) 적용으로 비례 안정화.
  - `SettingsDialog`: 구형 프레임(`QGroupBox`) 전면 철거, 1px TUI 라인(`_tui_sep`)과 아스키 섹션 헤더(`// SECTION`) 기반 하이퍼미니멀 스타일로 재구축.
  - `SettingsDialog`: 윈도우 크기 최적화(660×680 fixed) 및 2열 체크박스 그리드 여백 확보로 텍스트 잘림 현상 방지.
  - `SettingsDialog`: 하단 풋터 액션 바(`[ Close: Esc ]`)를 스크롤 영역 외부로 격리 분리하여 하단 패딩 및 조형미 확보.
  - `SettingsDialog`: `save_cfg` 및 `update_ui_state` 자체 위임 메서드를 추가하여 부모 창 의존성 완화(독립 실행 및 테스트 안전성 확보).
  - 코드 클린업: `dialogs.py` 내 미사용 레거시 임포트(`QGroupBox`, `QThread`, `Signal`, `updater`) 영구 제거.

### 2026-09-15 — v3.5.0 : 레이아웃 리팩터링·pip 오버레이·크래시 수리·표준 준수·검증 강화 (minor 업)

#### 레이아웃 리팩터링 (B2 아키텍처)
- **chzzktube 단일 패키지 + 계층 분리**: 루트 39개 평탄 모듈 → `chzzktube/{ui,control,workers,pipeline,core,infra}` 6계층 구조로 재편
- **main.py 씬 런처**: 루트 `main.py`(씬 런처, ~30줄) → `chzzktube.ui.main_window.main()` 호출. `python main.py` / PyInstaller `Analysis(['main.py'])` 계약 유지
- **자원 이동**: `icon.ico`·`CascadiaMono*.ttf` → `assets/`, 문서 → `docs/`, 미러 → `mirrors/`, `src/` 잔재 제거

#### pip 업데이트 모델 전면 개편 (v3.4.1 핵심)
- **프로젝트 로컬 오버레이 `.pylib/`**: 인앱 업데이터가 `venv/site-packages`(uv 소유)를 절대 수정하지 않고 `<repo>/.pylib/`에 whl 해제
- **부트스트랩**: `chzzktube.infra.pylib_bootstrap.bootstrap()`이 `sys.path` 선두에 `.pylib/` 삽입, `main.py` 최상단 + `main()` 내부에서 `python -m` 직행도 커버
- **오버레이 우선순위**: `sys.path` 선두 → 오버레이 복사가 venv(락핀)보다 항상 우선. `importlib.metadata` 판독도 오버레이가 이김
- **해제 정규화**: `_extract_pylib_whl(whl, root, prefix)`로 yt-dlp/streamlink 공용화. **[버그 수정]** whl(zip)엔 디렉터리 엔트리 없어 `endswith(".dist-info/")` 판정이 항상 None → 구 dist-info 정리 스킵되던 버그 수정(파일 경로 첫 세그먼트 파싱)
- **가시성**: 기동 시 `DEPS │ OK │ PYLIB │ overlay: <path> [dist-info…]` 1줄로 어느 복사본이 이겼는지 표기

#### 크래시·버그 수리
- **_POTWorker SIGABRT**: `finished_signal` 큐잉이 `run()` 반환 전 도착 → `_on_worker_finished`가 즉시 `self._worker=None`으로 참조 해제 → 워커 스레드가 자기 파괴(SIGABRT). **수리**: `_retire/_retiring` 수명 보증 도입 — `finished`(run() 완전 반환 후 발화)까지 참조 보관 후 `deleteLater` 정리. 3개 경로(일반·pending-gate 조기 반환·cancel) 모두 적용
- **Sans Serif 폰트 별칭 탐색 제거**: `QApplication` 폰트 미지정 시 Qt 제네릭 `Sans Serif` 별칭 탐색(~100ms). `app.setFont(QFont("Cascadia Mono", 11))`로 고정
- **streamlink 무한 업데이트 루프**: `_frozen_upgrade_streamlink`가 whl을 `site-packages/streamlink/`(코드 안)에 풀어 `importlib.metadata`가 구 `dist-info` 읽음 → 매 기동 stale 판정. whl을 site-packages 루트에 풀고 구 dist-info 정리·캐시 무효화로 해결
- **POT 토큰 정합**: `_on_worker_finished`가 gate 성공 시 `"staged"`로 오보고하던 잠재 버그 → 실제 `_mode`(`"ready"`) emit
- **빈 scope 제거**: `main_window.py` 빈 `scope=""` → 플랫폼(`"YT"/"CHZ"`) 또는 `"MAIN"`으로 보정 (4컬럼 파괴 방지)
- **stage 대문자 통일**: `pot_manager.py` stage 태그 `"pot"`→`"POT"`, `"pot-DEBUG"`→`"POT-DEBUG"` (4컬럼 표준 준수)

#### 표준·테스트 강화
- **빈 scope 제거 + stage 대문자**: LogEvent 4필드(STAGE/STATUS/SCOPE/MSG) 표준 완전 준수
- **회귀 테스트 추가**: `test_pylib_overlay.py`(경로 계약·bootstrap·dist-info 정리·손상 whl) · `test_pot_manager.py`(토큰 정합 2건) · `test_coordinator.py`(raw 버스 배선 2건)
- **`pot_status_changed` 시그널 배선**: Coordinator가 토글 메시지를 raw 버스에 태워 TUI/F12/history 기록

#### 검증
- 전체 pytest **149 passed** (신규 12건) · smoke PASS · sync_mirrors 42 모듈 `changed 0/missing 0` · cocoa 실기동 EXIT_CODE=0 · 오버레이 우선순위 실증(overlay 99.0.0 > venv 8.6.0)

---

### 2026-09-13 — v3.4.0 패치 2 : 파이프라인 P0 크래시 수리 + LEGACY_AUDIT 정리

- **P0-1 finalizer**: `_dl_platform` import 누락 — 모든 배치 완료/취소 시 NameError → `finished_all` 미발화 → UI 영구 락업
- **P0-2 downloader**: SKIP 틱 `_dl_platform` NameError
- **P0-3 target_downloader**: 정의 없는 `_chzzk_filename` — 치지직 다운로드 전부 실패. `get_filename_template` 계약을 치지직 메타(channel_name/date/clip_id·video_no·live_id/fmt.height)로 치환해 복구
- **P1-A3 pot_manager**: 프리웜 `rebuild=have_build` 반전 수리 — 매 기동 npm ci+tsc 강제(§1.3 경량 prewarm 위반)를 스테일 감지 기반으로 교정
- **P1-A4 라이브 계약**: live_recorder가 DownloadContext에 부착하는 proc를 worker가 보지 못하는 불일치 수리 — `DownloadWorker._ctx` 보관 + `kill_live_process()`가 양쪽 핸들 킬, closeEvent 분기 활성화
- **P2**: `_note/_dbg` 발행 시 `[:120]` 절단 제거(LOGGING_POLICY §3/§4), 미사용 import 2건(main·progress_emitter), `POTProviderWorker` 별칭 제거, `pot_server` 중복 상수 제거, `media/chzzk_api/cookies` 죽은 `import log_history` 제거, 루트 잔재 9종 git rm(`1,` `_qtprobe.exit` `err/out.txt` `listing/locate_out.txt` `arch_dump.txt` `D2Coding-Regular.ttf` `requirements.txt`), HANDOVER §3 레이어 표기 갱신
- **P3**: `needs_pot` 3중 판정식 → `_needs_pot(info)` 단일화, F12 재오픈 증분 동기화(`_full_log_win_n`), `emit_live_header` 데드 함수 제거
- **잔여 P3 수리**: README의 미실물 pre-commit 주장 → CI 실측 문구 교체(D3) · CI paths-ignore 오탈자 `sync-drive.yml`→`sync-to-drive.yml`(D4) · log_console D2Coding 주석 → Cascadia Mono(D5) · `dl_state` 레거시 별칭 폐기 + smoke_test `ctrl.state` 갱신(E2) · HANDOVER updater "stdlib only" 표기 정밀화(lazy import 명시, E3)
- **검증**: 전체 pytest 137 passed(신규 `tests/test_pipeline_regressions.py` 11건) · smoke_test PASS · `sync_mirrors.py --check` 0건 · py_compile OK

### 2026-09-13 — v3.4.0 패치 : 분석 상태 머신 회귀 수리 — ENTER 잠금 해제·URL 클리어 크래시 제거

- **ENTER 잠금 근본 원인 수리**: `on_analyze_success`/`on_analyze_error`가 `ctrl.state["analyzing"]`을 해제하지 않아 State-Button Matrix(`get_current_app_state`)가 `ANALYZING`에 영구 고정 → `toggle_download`가 `state != "IDLE"`에서 조기 반환 → 분석 완료 후 ENTER·입력 잠금
- **죽은 호출 교체**: `on_url_changed` URL 클리어 분기가 MVC 이관(94f1ee4)에서 삭제된 `_abandon_analyze_worker()`를 호출(AttributeError) — `ctrl._abandon_analyzer()`로 교체
- **회귀 테스트**: `tests/test_analyze_state.py` 신규 5건 — 분석 성공/실패 IDLE 복귀·ENTER 재개, 포맷 고르기 PICKING 비가림, 완료 후 유령 시그널 폐기, URL 클리어 크래시
- **검증**: 전체 pytest 126 passed · `sync_mirrors.py --check` 변경 0건 · py_compile OK

### 2026-09-13 — v3.4.0 : 4컬럼 로그 규격 — SPEC/PLATFORM 폐지·SCOPE 통합·메타데이터 태그화

- **로그 포맷 표준화**: 메인 TUI를 `[HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG` 4컬럼으로 통합. `PLATFORM`과 `SPEC`을 별도 컬럼으로 유지하지 않고 발생지/대상은 `SCOPE`, 미디어·버전 정보는 MSG 앞 태그(`[1080p30]`, `[v2026.8.19]`)로 이동
- **고정 폭·중복 제거**: STAGE/STATUS/SCOPE는 5자 고정, 진행률은 3자리 퍼센트·8자리 속도·10블록 게이지로 렌더링. 빈 MSG의 말단 구분자와 같은 의미의 중복 상태 문구를 제거
- **구조화 계약 갱신**: `LogEvent.platform`은 `scope` 호환 별칭으로 남기고 신규 발행점은 `scope`만 사용. `SPEC` 전달 시 MSG 태그로 흡수하며 `WAIT`는 독립 STATUS를 만들지 않고 `RUN`으로 통합
- **문서·미러 정합성**: HANDOVER/LOGGING_POLICY/README의 v3.4.0 규격을 현행 소스와 동기화하고, 변경 Python 소스에 대응하는 `mirrors/*.md` 및 합본 미러를 재생성
- **검증**: 전체 Python 컴파일, 미러 `--check`, 관련 회귀 테스트 및 전체 테스트 스위트 통과

### 2026-09-12 — v3.3.1 : 계층 모숭 정리 — L0 순수화·좀비 제거·Qt 스레드 경계 분리

- **기동 게이트 신뢰 복구**: `StartupState.pot_ready` 플래그 — READY는 prewarm/gate **실완료 토큰**으로만 개방. `POTManager.pot_finished` msg를 상태 토큰(`"staged"`/`"ready"`/`"failed"`)으로 발행(사람용 msg 발행 시 READY 미개방 결함 수정), `use_existing()` 신설(기존 서버 응답 시 `_pending_download` 영구 큐잉 방지), `_on_pot_finished`의 `is_ready()` 재확인 후 회수 재개
- **raw 버스 백프레셔**: dispatcher bounded queue(MAX_QUEUE=2048) — 발행 스레드는 put만, 포화 시 UI mirror 드롭 + history 요약 1건, 구독자 콜백은 lock 밖에서 호출, `flush()` queue.join 연동
- **yt-dlp `\r` 처리**: `YtLoggerBridge` 캐리지 조립 버퍼 — 청크 분할 이월·다중 `\r` 최신 스냅샷만 발행·2Hz 스로틀. F12 버퍼 `deque(maxlen=4096)`
- **L2 수리 (live_recorder)**: 증발한 `prepare_live_paths` 모듈 함수 구현, `worker.handle_stream_finish`/`worker.log_success_info` 인스턴스 메서드 착각 호출을 모듈 함수 계약으로 교정 — 라이브 진입·종료 AttributeError 제거, `_lr` 자기 참조 별칭 제거
- **L0 순수화 (po_client)**: `server_ping`의 pot_server lazy import(락 파일 PID 염탐) 완전 철거 — 순수 HTTP /ping만 판정(TCP+200=이벤트 루프 생존 증거), 좀비 락 회수는 pot_server 본연 책임으로 이관. `import os` 누락 NameError 은폐 결함 근원 제거
- **좀비 제거**: `worker_context.py` 삭제(DownloadContext와 이중 계약, 런타임 사용 0건), `pot_provider.POTProviderWorker` 제거(POTManager._POTWorker 중복, facade는 재수출 단독)
- **Qt 스레드 경계**: main `_GuiLogBridge(QObject)` + QueuedConnection — raw_log 순수 파이썬 유지(헤드리스 테스트 무수정), GUI 슬롯(`_render_concise`/`_mirror_event_full`)은 메인 스레드에서만 실행. 배경 스레드 QTextEdit 직접 접근 차단
- **기타 수리**: pot_provider `_spawn_existing` 이중 호출 원자화(서버 2회 기동 방지), main `_emit_format_logs` 복원(분석 성공 V-FMT/A-FMT 코덱 로그), startup_coordinator 죽은 `_stage_complete` 제거, raw_log 죽은 `MAX_LINE_CHARS` 제거
- **검증**: py_compile 전체 + pytest **111 passed** (test_live_recorder 신규 5건, overflow 타이밍 레이스 제거) + 브리지 스레드 경계 프로브(슬롯 전부 MainThread 실증)


### 2026-09-12 — v3.3.0 : 로그 버스 단일화 — raw 단일 경로·플래그 라우팅·레거시 제거

- **버스 단일화**: `raw_log.raw(tag, msg, to_tui)` 단일 진입 확정 — `log_bus.py` 삭제, `log_history.log` 직접 호출 10곳 버스 reroute(`to_tui=False`), 워커 로그 시그널 0건 실측
- **플래그 라우팅**: TUI 노출=`to_tui` 비트, 줄바꿈=`no_wrap` 플래그 — `_flow_lines` 콘텐츠 판정(`is_tui_line`) 렌더 퇴출(호환 shim 강등), resize reflow도 버퍼 플래그로 유지
- **근원 라벨링**: 분석 성공 등 발행점에서 LogEvent 동봉 — `_render_concise`가 컬럼화, `append_concise_log`는 bus shim(호출부 20곳 무수정), `append_full_log` 제거
- **기동 게이트 문서화**: DEPS→upgrade→prewarm→READY 체인, POT prewarm/gate `_pending_gate` 승격, `can_emit_ready()` 멱등식 — HANDOVER §5 불변식 11~15 편입, §3 아키텍처 40개 모듈 실측 최신화
- **검증**: py_compile 전체 + pytest 86 passed (신규 `TestFlowLinesNoWrapFlag` 6건 + v3.3.0 계약 불일치 7건 수리)


### 2026-09-10 — v3.2.0 : F12 중복 제거·raw 로그 버스·POT stale 감지 + 프리웜 자동 리프레시

- **아키텍처**: raw 로그 버스(`raw_log.py`) 신설 — 모든 동작 로그 concise(메인 TUI)/F12/역사 3채널 팬아웃, 필터링은 각 모듈
- **PO 서버**: POT DEPS 판정을 liveness → readiness(pot_readiness)로 전환, 미기공 정상 `FAIL not running` 오경보 제거
- **프리웜**: 파이프라인 idle 단계에서 stale 빌드 감지 + 자동 리프레시(체크 스탈 + want_refresh + 자동 rebuild) → lazy "언제든 작동 가능한 준비 상태" 유지
- **F12 가독성**: CLI 원문(`ffmpeg -version` configuration:) 장문/다수 절단(`max_lines=6, max_width=160`) 적용, F12 중복 이중적재 제거
- **로깅**: POT/가드/락 획득·해제 경로를 raw 태그(`pot-readiness`, `prewarm-lock`, `pot-gate`, `POT-FAIL` 등)로 기록
- **계층/시그널**: 워커가 포그라운드/히스토리 직접 emit 금지 — L0 `log_func` 콜백 + raw 버스 단일 경유
- **테스트**: PID-liveness·상호배제·stale 회수·readiness stale·check_deps 단일 호출·cli_raw 절단·raw 팬아웃 추가 (전체 80 passed)

### 2026-09-09 — v3.1.2 : 전체 아키텍처/모듈/테스트/CI 실측 최신화

- 대규모 리팩토링 후 시그널 파이프라인 정리, 계층 역전 해소(client_opts/updater → po_client L0 직접 참조)
- dataclass 다운로드 컨텍스트(`dl_context.py`) 도입, 포터블 번들 탈피 + Node.js 외부 참조 전환
- 모듈 분리: analyze_worker/yt_logger_bridge/po_client/update_worker/po_client 등 34개 모듈 체계 정비
- 바람직하지 않은 중복 EMIT·상태 오판 제거, 짧지만 정합적인 진행률/콘솔 레이팅 유지

### 2026-09-08 — v3.1.0 : Qt/PySide6 정리, 로깅 표준화, Cascadia Mono 11px

- Flat TUI 3-Layer 구조로 전환, 모노스페이스 폰트 통일
- 당시 고정 칼럼 로그 규격([HH:MM:SS] STAGE │ STATUS │ PLATFORM │ SPEC │ MSG) + 파스텔 톤 에러 컬러 (v3.4.0에서 4컬럼으로 개정)
- MSG 영문 미니멀화 (1~3단어 CLI 태그), live 콘솔 모니터 stretch=1 분리