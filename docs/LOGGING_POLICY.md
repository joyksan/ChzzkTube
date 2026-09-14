# ChzzkTube 로그 정책 (v3.4.0)

> 단일 진실: **발행점 라벨링 → LogEvent 운반 → 말단 렌더러에서 1회 조판/스탬프**.
> 이 문서는 `HANDOVER §1.3`과 `§5 불변식`의 해설서다. 충돌 시 코드와 HANDOVER 불변식이 우선한다.

## 1. 포함관계 (채널)

```text
history = 전량 ⊇ F12(full) = 전량 ⊇ TUI(concise) = to_tui=True만
```

- F12가 받지 않는 로그는 존재하지 않는다.
- TUI 노출은 발행자의 `to_tui` 1비트가 유일한 기준이다.
- 콘텐츠 정규식 기반 라우팅은 금지한다.

## 2. 발행 계약 (근원 라벨링)

- 모든 로그는 `raw_log.raw(tag, msg, is_status, is_error, to_tui)`로 수신된다.
- `msg`는 `LogEvent`를 권장한다. 문자열은 `rendered=True`로 정규화된다.
- `stage/status/scope`는 **태어난 곳(발행점)**에서 동봉한다. 렌더 레이어에서 뒤늦게 추론하지 않는다.
- 신규 발행점은 `log_console.emit_event`, `emit_dl`, `emit_err`, `emit_progress`, `emit_component`를 사용한다.
- `log_history.log` 직접 호출은 금지한다. history 적재는 dispatcher 내부 1회가 유일하다.

## 3. 운반 계약 (표준 봉투 + 날것 내용물)

- `LogEvent(timestamp, stage, status, scope, msg, speed, pct, bar_frac, ...)`가 표준 봉투다.
- `platform`과 `spec`은 v3.4.0에서 deprecated 호환 필드다. 신규 발행점에서 사용하지 않는다.
- `spec`은 렌더러가 MSG 전두부 `[tag]`로 흡수한다.
- `msg` 페이로드는 무가공 원문이다. 발행·운반·수집 어디에서도 절단·재포맷하지 않는다.
- 문자열 스탬핑(`[HH:MM:SS]` 손조립)은 금지한다. timestamp는 말단 렌더러에서 1회만 생성한다.

## 4. 말단 계약 (조판·스탬프·절취는 뷰에서 1회)

- 컬럼화(`format_log_line_for_event`)는 TUI 렌더러(`_render_concise`) 전용이다.
- F12(`_mirror_event_full`)는 `event.msg` 원문을 적재한다. 이중 timestamp를 방지한다.
- timestamp는 말단에서 1회만 찍는다: TUI=`_log_ts()`, F12=`_mirror_full_log`, history=파일 포맷.
- 절취(`max_lines/max_width`)는 적재/렌더 시점에만 수행한다. 수집(`cli_raw`, `pump`)은 원문 전량을 반환한다.
- 고정 4칸: `STAGE(5) │ STATUS(5) │ SCOPE(5) │ MSG`.
- `speed/pct/bar`는 별도 컬럼이 아니라 MSG 선두 고정형으로 통합한다.
- 진행률 순서: `PCT(3폭 우측) · SPEED(8폭 우측) GAUGE(10블록) · MSG`.
- 빈 MSG에는 꼬리 구분자(`│`)를 출력하지 않는다.

## 5. 외부툴 래퍼 강제 (tool_log.py)

- 새 기능이 외부툴을 호출할 때는 `tool_log` 경유만 허용한다.
  - yt-dlp Python API → `tool_log.make_ytdlp_logger()` (Injection)
  - subprocess(stderr) → `tool_log.pump()` (Interception, reader 스레드)
  - CLI 일괄 → `tool_log.run_cli()` + `truncate_for_full_log` (적재 시 절취)
- 직접 subprocess 파싱·로거 세팅 코드의 기능별 중복 작성은 금지한다.
- Protocol 3종(`ToolLogger`/`LineRunner`/`TokenProvider`)은 형상 선언만 사용한다.

## 6. 설정 fit 규칙 (client_opts)

- 모든 외부툴 가변 설정은 `config.default_config()` 키가 유일한 스위치다.
- 하드코딩(`"best"` 고정 등)은 금지한다. `_apply_*` 헬퍼가 옵션으로 배선된다.
- 새 키 추가 3점 세트: (1) `default_config` 기본값 (2) `_apply_*` 헬퍼 (3) `dialogs.py` UI.
