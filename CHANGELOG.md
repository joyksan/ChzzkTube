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