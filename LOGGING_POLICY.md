# ChzzkTube 로그 정책 (LOGGING_POLICY)

> 단일 진실: **생성(raw 단일 진입) → 운반(LogEvent 표준 봉투) → 말단 조판/스탬프 1회**.
> 이 문서는 `HANDOVER §5 불변식 11·12`의 해설서다. 충돌 시 HANDOVER 불변식이 우선.

## 1. 포함관계 (채널)

```
history = 전량 ⊇ F12(full) = 전량 ⊇ TUI(concise) = to_tui=True만
```

- "F12가 안 받는 로그"는 존재하지 않는다.
- TUI 노출은 발행자의 `to_tui` 1비트가 유일한 기준. 콘텐츠 정규식 판정 금지.

## 2. 발행 계약 (근원 라벨링)

- 모든 로그는 `raw_log.raw(tag, msg, is_status, is_error, to_tui)` 경유.
- `msg`는 `LogEvent` 권장. 문자열은 `rendered=True`로 정규화된다.
- `stage/status/platform/spec`은 **태어난 곳(발행점)**에서 동봉한다.
  렌더 레이어에서 뒤늦게 추론하지 않는다.
- 팩토리 강제: `log_console.emit_event / emit_dl / emit_err / emit_component`
  경유 — 새 기능에서 `LogEvent(...)` 직접 조립·`raw_log.raw` 직접 호출 금지.
- `log_history.log` 직접 호출 금지 — history 적재는 dispatcher 내부 1회가 유일.

## 3. 운반 계약 (표준 봉투 + 날것 내용물)

- `LogEvent` envelope(timestamp·stage·status·platform·spec·speed·pct·bar)은 표준.
- `msg` 페이로드는 **무가공 원문**. 발행·운반·수집 어디에서도 절단·재포맷 금지.
- 문자열 스탬핑(`[HH:MM:SS]` 손조립) 금지 — timestamp는 envelope 필드.

## 4. 말단 계약 (조판·스탬프·절취는 뷰에서 1회)

- 컬럼화(`format_log_line_for_event`)는 **TUI 렌더러(`_render_concise`) 전용**.
  F12(`_mirror_event_full`)는 `event.msg` 원문을 적재한다 — 이중 ts 방지.
- 타임스탬프는 말단에서 1회: TUI=`_log_ts()`, F12=`_mirror_full_log`,
  history=파일 포맷. 2곳 이상에서 찍지 않는다.
- 절취(`max_lines/max_width`)는 **적재/렌더 시점**에만.
  수집(`cli_raw`·`pump`)은 원문 전량 반환. 수집에서 자르면 영구 소실.
- 고정 5칸: `STAGE(8) │ STATUS(8) │ PLATFORM(8) │ SPEC(12) │ MSG`.
  `speed/pct/bar`는 별도 컬럼이 아니라 MSG 선두 extra로 통합.

## 5. 외부툴 래퍼 강제 (tool_log.py)

- 새 기능이 외부툴을 호출할 때는 **`tool_log` 경유만 허용**:
  - yt-dlp Python API → `tool_log.make_ytdlp_logger()` (Injection)
  - subprocess(stderr) → `tool_log.pump()` (Interception, reader 스레드)
  - CLI 일괄 → `tool_log.run_cli()` + `truncate_for_full_log` (적재 시 절취)
- 직접 `subprocess` 파싱·로거 세팅 코드의 기능별 중복 작성 금지.
- Protocol 3종(`ToolLogger`/`LineRunner`/`TokenProvider`)은 형상 선언만 —
  무거운 추상 계층 선행 금지.

## 6. 설정 fit 규칙 (client_opts)

- 모든 외부툴 가변 설정은 `config.default_config()` 키가 유일한 스위치.
  하드코딩(`"best"` 고정 등) 금지 — `_apply_*` 헬퍼가 옵션으로 배선.
- 새 키 추가 3점 세트: (1) `default_config` 기본값 (2) `_apply_*` 헬퍼
  (3) `dialogs.py` 체크박스/콤보. 하나라도 빠지면 미완성.
