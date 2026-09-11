### 2026-09-12 — v3.3.0 : 로그 버스 단일화 — raw 단일 경로·플래그 라우팅·레거시 제거

- **버스 단일화**: `raw_log.raw(tag, msg, to_tui)` 단일 진입 확정 — `log_bus.py` 삭제, `log_history.log` 직접 호출 10곳 버스 reroute(`to_tui=False`), 워커 로그 시그널 0건 실측
- **플래그 라우팅**: TUI 노출=`to_tui` 비트, 줄바꿈=`no_wrap` 플래그 — `_flow_lines` 콘텐츠 판정(`is_tui_line`) 렌더 퇴출(호환 shim 강등), resize reflow도 버퍼 플래그로 유지
- **근원 라벨링**: 분석 성공 등 발행점에서 LogEvent 동봉 — `_render_concise`가 컬럼화, `append_concise_log`는 bus shim(호출부 20곳 무수정), `append_full_log` 제거
- **기동 게이트 문서화**: DEPS→upgrade→prewarm→READY 체인, POT prewarm/gate `_pending_gate` 승격, `can_emit_ready()` 멱등식 — HANDOVER §5 불변식 11~15 편입, §3 아키텍처 40개 모듈 실측 최신화
- **검증**: py_compile 전체 + pytest 32 passed (신규 `TestFlowLinesNoWrapFlag` 6건)


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
- 고정 칼럼 로그 규격([HH:MM:SS] STAGE │ STATUS │ PLATFORM │ SPEC │ MSG) + 파스텔 톤 에러 컬러
- MSG 영문 미니멀화 (1~3단어 CLI 태그), live 콘솔 모니터 stretch=1 분리