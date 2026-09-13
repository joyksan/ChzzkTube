# v3.4.0 레거시·모순 전수조사 (2026-09-13)

> 목적: HANDOVER/LOGGING_POLICY/README가 선언한 아키텍처·불변식과 현행 소스를 일대일 대조해
> **로직적·아키텍처적 모순점**을 실측으로 확정한다. 문항 등급:
> - P0 = 즉시 수리 (이번 패치로 완료)
> - P1 = 다음 패치에서 수리 권장 (사용자 영향·크래시 가능)
> - P2 = 정리 대상 (죽은 코드·문서/코드 어긋남·계약 위반)
> - P3 = 개선 후보 (리팩터/방향성 조율)
>
> 방법: `grep`+소스 정독, git 이력(`git log -S`)으로 회귀 지점 특정. 전체 pytest 126 passed 기준.

> **수리 현황 (2026-09-13 패치 1·2 반영)**: A1·A2(패치 1), P0-1~3(finalizer/downloader
> `_dl_platform` import·`_chzzk_filename` 복구), A3(스테일 기반 rebuild), A4
> (`kill_live_process` 계약), B1~B5+B8(죽은 코드·죽은 import), C1(발행 절단 제거),
> D1(requirements.txt 삭제), D2(루트 잔재 9종 제거), B7(HANDOVER §3 표기),
> E1(`_needs_pot` 단일화), A5(F12 증분 동기화) **완료**.
> 잔여: D3(README pre-commit), D4(CI paths-ignore), D5(주석), E2/E3 — 다음 패치 후보.

---

## A. 런타임 버그 / 로직 모순

### A1. [P0 · 수리완료] ENTER 잠금 — 분석 완료 후 `state["analyzing"]` 영구 고정
- **증상**: URL 분석 성공 직후 `POT │ RUN │ POT │ gated=False ...` 로그가 찍힌 다음부터 입력·ENTER가 무반응.
- **원인**: `controller.spawn_analyzer`가 `state["analyzing"]=True`를 세팅하지만 성공/실패 어디에서도 `False`로 복귀하지 않음 (`controller._abandon_analyzer` 유기 경로에만 존재). `a18639b`(State-Button Matrix) 이후 `get_current_app_state()`가 `ANALYZING`을 하드 차단 → `toggle_download`의 `state != "IDLE"` 조기 반환.
- **회귀 지점**: `a18639b` (9/10) — 이전 `toggle_download`는 `running`/`picking`만 검사해 누락이 표면화되지 않음.
- **수리**: `on_analyze_success`/`on_analyze_error`에 `self.ctrl.state["analyzing"] = False` (stale 검사 통과 직후). `_is_stale_analyze_signal` docstring("완료 시 analyzing=False") 계약 복원. 포맷 고르기(PICKING) 흐름도 `ANALYZING`에 가려지지 않게 수리됨.
- **테스트**: `tests/test_analyze_state.py` 5건 신규.

### A2. [P0 · 수리완료] URL 클리어 시 AttributeError 크래시
- `on_url_changed`의 클리어 분기가 MVC 이관(`94f1ee4`)에서 삭제된 `self._abandon_analyze_worker()`를 호출 (정의 0건) → `clear_status_line`/`_discard_analysis_result` 미실행.
- **수리**: `self.ctrl._abandon_analyzer()`로 교체.

### A3. [P2 · 수리완료] 프리웜이 매 기동 시 `npm ci` + `tsc` 강제 재실행
- `pot_manager._run` (prewarm): `have_build = built_server_js() is not None` → `ensure_node_server(..., rebuild=have_build)`.
  `ensure_node_server`는 `js is None or rebuild:`면 항상 `npm ci --no-audit` + `tsc`를 실행 (기존 빌드 존재 시 `rebuild=True`).
- **모순**: HANDOVER/README의 "prewarm = 디스크 스테이징만 (RAM 0MB·포트 미점유)" 경량성 주장과 대치. 서버가 살아있지 않은 깨끗한 기동에서는 매 앱 시작마다 npm 의존성 재설치가 일어난다.
- **제안**: 스테일 감지(`latest_server_ver` vs `server_installed_ver`) 기반으로만 rebuild 하거나 `rebuild=False`로 변경.

### A4. [P2 · 수리완료] 라이브 프로세스 정리 계약 불일치
- `live_recorder.record_live_stream`이 `worker._live_proc = proc`을 부착하지만 이때 `worker`는 **DownloadContext** (target_downloader가 ctx 전달). 실제 `DownloadWorker._live_proc`(downloader.py)는 항상 `None`이다.
- `main.closeEvent`의 `kill_live_process` 분기(229행)는 DownloadWorker에 존재하지 않는 메서드 → 실행 불가 죽은 가지.
- 안전성은 `state["canceled"]` 공유 dict 경유 루프 내 kill로 확보되나, 명시적 계약(워커 소유 핸들)과 어긋남. `_live_proc`를 DownloadContext로 승격하거나 폐기할 것. 

### A5. [P3 · 수리완료] F12 재오픈 시 닫혀 있던 구간 로그 미반영
- `toggle_verbose_log`는 `set_content`를 최초 생성 시 1회만 수행. 닫힌 동안의 로그는 `_full_log_buf`에만 쌓이고 창은 재오픈 시 이전 내용+열린 동안의 append분만 표시.
- **제안**: 재오픈 시 `_full_log_buf`에서 재동기화.

---

## B. 계층/구조 위반·좀비 인터페이스

### B1. [P2 · 수리완료] `main.py:45 import pot_provider` 미사용
- `pot_provider.` 역참조 0건. DEPS 표기의 흔적으로 보임 — 제거 권장.

### B2. [P2 · 수리완료] `progress_emitter.py:33` client_opts 미사용 import
- `_apply_client_opts/_apply_cookie_opts` 역참조 0건 — 제거 권장.

### B3. [P2 · 수리완료] `pot_manager.py:248 POTProviderWorker = _POTWorker` 잔존
- CHANGELOG(v3.3.1) "pot_provider.POTProviderWorker 제거"와 표면 모순 (제거는 pot_provider facade 기준 성립). 런타임 사용 0건. 별칭 자체 제거 권장.

### B4. [P2 · 수리완료] `pot_server.py` 중복 상수 (두 병합 잔재)
- `_SERVER_FALLBACK_VER = "1.3.2"` 35행·152행, `_TAG_ZIP` 32행·153행 이중 정의. 나중 정의가 최종값(동일)이라 동작 영향 없으나 파일이 2개 소스를 접합한 흔적 — 정리 권장.

### B5. [P3 · 수리완료] `progress_emitter.emit_live_header` 죽은 함수
- 호출 0건. `res_label` 인자 분기(135/142행)가 사실상 동일 출력 — 삭제 또는 실제 사용처 배선.

### B6. [P3 · 수리완료] `main.closeEvent` `kill_live_process` 가드 (A4와 동일 계열)
- `hasattr(..."kill_live_process")` 항상 False. DownloadWorker에는 `terminate()`(자체 `_live_proc`)만 존재.

### B7. [문서 어긋남 · 수리완료] HANDOVER §3/§7 표기
- §3 LAYER 1에 `pot_provider.py`를 워커로 분류 — 현재는 po_client/node_provider/pot_server 순수 재수출 facade (워커 없음). → §3 트리·모듈 테이블을 facade(L0/Infra) 기준으로 갱신 완료.
- §7/수정 테이블의 `Main._maybe_prewarm_pot` — 코드에 없음 (실제는 `_on_update_check_done → POTManager.ensure_ready("prewarm")`). 히스토리 서술이므로 현행 트리만 갱신.

### B8. [P2 · 수리완료] `media.py`/`chzzk_api.py`/`cookies.py` 죽은 `import log_history`
- 세 모듈 모두 `log_history.` 사용 0건 — v3.3.0 raw 버스 이관 잔재(HANDOVER §5-15 언급분). 제거 완료.
---

## C. 로그 계약 위반 (LOGGING_POLICY 대비)

### C1. [P2 · 수리완료] `pot_manager._note/_dbg`가 발행 시 `msg[:120]` 절단
- LOGGING_POLICY §3 "msg는 무가공 원문… 절단 금지", §4 "절취는 적재/렌더 시점에만" 위반. F12/history가 POT 상세 원문 일부를 영구 손실.
- `_render_concise` 등 뷰 절취(4096 등)로는 충분 — 발행점 절단 제거 권장.

### C2. [확인-정상] LOGGING_POLICY §2 "신규 발행점은 emit_* 사용"
- `log_full`/`append_full_log`/`tui_to_raw` 잔재 0건 (controller 주석·`pot_server`의 `log_full_func` 파라미터명은 코멘트/로컬명으로 무해). 비표준 STATUS(`WAIT`/`MISSING`/`?`)도 소스·모듈 없음.

---

## D. 의존성/문서/릴리즈 잔재

### D1. [P1 · 수리완료] `requirements.txt` — 방향성과 모순된 오래된 의존성
- PyQt6·PyQt6-Fluent-Widgets·bgutil-ytdlp-pot-provider 고정 + "v3.0.2 실행 환경 (Windows)" 헤더.
- 현행 단일 출처는 `pyproject.toml`/`uv.lock` (PySide6 6.11.0). README/HANDOVER의 "# 유튜브 PO Token 플러그인" 설명도 퇴출 완료 상태와 불일치.
- **제안**: 삭제하거나 현행 스택으로 재작성.

### D2. [P2 · 수리완료] 루트 추적 잔재 파일 (git 저장소에 커밋됨)
- `1,`(리다이렉트 산물), `_qtprobe.exit`, `err.txt`, `out.txt`(UTF-16 콘솔 덤프), `listing.txt`, `locate_out.txt`, `arch_dump.txt`(Windows 경로 덤프), `D2Coding-Regular.ttf`(4.2MB, 미로드 — HANDOVER도 "레거시 잔재" 명시).
- **제안**: 삭제 + `.gitignore` 보강 (`1,`, `*.exit`, `*_dump.txt` 등).

### D3. [P2 · 수리완료] README "커밋 전 훅 활성화" 주장 — 실물 없음
- `.pre-commit-config.yaml` 부재, `.git/hooks`는 샘플뿐, `core.hooksPath` 미설정. 주장 유지 시 훅 구성 필요, 아니면 문구 제거.

### D4. [P3 · 수리완료] CI paths-ignore 파일명 오류
- `.github/workflows/ci.yml` → `paths-ignore: '.github/workflows/sync-drive.yml'`이지만 실제 파일은 `sync-to-drive.yml` — 매칭 안 됨.

### D5. [P3 · 수리완료] 주석·라벨 잔재
- `log_console.py:223/244/681` "D2Coding" 주석 — 현행 폰트는 Cascadia Mono. 영향은 주석뿐.
- `requirements.txt` 헤더 버전/플랫폼 표기 (D1).

---

## E. 단일화/리팩터 후보

### E1. [P3 · 수리완료] `needs_pot` 판정 3중 중복
- `main._ensure_pot_for_info` / `toggle_download` / `_wait_pot_if_needed`에 동일 판정식(age_limit ∨ availability∈…)이 중복. 드리프트 방지 위해 `_needs_pot(info)` 모듈 함수 단일화 권장. 게이트 상수 목록은 `HANDOVER §3 다운로드 게이트`와도 함께 관리.

### E2. [P3 · 수리완료] `MainWindow.dl_state` 레거시 프로퍼티
- `ctrl.state` 별칭. `smoke_test.py` 호환용으로 유지 중 — 폐기 시 smoke 대사 갱신 필요.

### E3. [P3 · 수리완료] `updater.py`의 "stdlib only" 표기 vs lazy `pot_provider`/`components` import
- 모듈 최상단은 stdlib 전부 맞음 (여전히 L0 경량성 준수). 다만 `pot_provider.node_exe/npm_exe`는 node_provider 재수출 경유 — 표기만 정밀화하면 됨.

---

## 검증 현황

- 패치 2 기준: 전체 pytest **137 passed**(`tests/test_pipeline_regressions.py` 11건 포함), smoke_test **PASS**, `python sync_mirrors.py --check` **변경 0건**, `py_compile` OK.
- 잔여 항목 **전소화 완료** — D3(README CI 문구), D4(CI paths-ignore), D5(D2Coding 주석), E2(`dl_state` 폐기), E3(updater 표기 정밀화)까지 패치 2에서 반영.