"""Pure log event builders and text formatting helpers (Qt-free).

pipeline/workers가 백그라운드·테스트 환경에서도 GUI 컨텍스트 없이
가져갈 수 있는 순수 함수만 둔다. Qt 위젯 렌더링은 ui/log_console 담당.
"""
import time
import unicodedata

from chzzktube.core.log_event import STAGES, STATUSES
from chzzktube.core.dl_platform import _short_platform


def display_width(text):
    """콘솔 표시 폭 계산 (한글 등 전각 문자는 2칸)."""
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        for ch in str(text)
    )

def _wrap_by_width(text, max_width):
    """표시 폭 기준 단어 단위 줄바꿈. 단어 자체가 예산보다 길면 강제 분할."""
    lines, cur, cur_w = [], "", 0
    for word in str(text).split(" "):
        while display_width(word) > max_width:
            if cur:
                lines.append(cur)
            cur, cur_w = "", 0
            part, take = "", 0
            for ch in word:
                cw = display_width(ch)
                if take + cw > max_width:
                    break
                part += ch
                take += cw
            lines.append(part)
            word = word[len(part):]
        w = display_width(word)
        cand_w = cur_w + (1 if cur else 0) + w
        if cur and cand_w > max_width:
            lines.append(cur)
            cur, cur_w = word, w
        else:
            cur = word if not cur else cur + " " + word
            cur_w = cand_w
    if cur:
        lines.append(cur)
    return lines

### 트리 라벨 공통 폭 — 콜론(:) 위치를 모든 가지에서 세로로 일치시킨다.
TREE_LABEL_WIDTH = 9  # kv 라벨('저장 완료'·'실패 사유' 등 전각 4자+공백) 기준
TREE_TOTAL_WIDTH = 56  # 간결 로그 창의 실질 가로 예산 (폴백 — ui가 동적 갱신)


### 줄기 없는(' └─') 연속 줄의 선행 공백 폭 — cont_prefix는 prefix 폭(TREE_LABEL_WIDTH+6)만큼의 공백 나열
STEMLESS_CONT_WIDTH = TREE_LABEL_WIDTH + 6

def _flow_lines(line, no_wrap=False):
    """라인 분할 규칙 — Single-Line TUI는 wrap하지 않는다.

    *  no_wrap=True(LogEvent 경유 컬럼/프리포맷 라인): 그대로 한 줄 —
       예산 초과분은 ConciseLogConsole._render_clamp가 '…'로 절단한다.
       (트리 조판 줄은 자식 줄 예산 산정용으로 내부 wrap 유지)
    *  no_wrap=False(큐 호환 bare 문자열·yt-dlp/pip 출력 등 비트리 일반
       라인): 예산 폭으로 wrap한다.
    발행자(raw → 구독자) 플래그가 유일한 분기 기준이며, 문자열 콘텐츠를
    다시 뜯어 판단하지 않는다(정규식 라우팅 제로).
    """
    if no_wrap:
        return [line]
    if line[:2] in (" ├", " └", " │"):
        return [line]
    if line.startswith(" " * STEMLESS_CONT_WIDTH):
        return [line]
    return _wrap_by_width(line, max(20, TREE_TOTAL_WIDTH))

def _pad_label(label, width):
    """라벨을 width칸까지 뒤에 공백을 붙여 확장한다."""
    return str(label) + " " * max(0, width - display_width(label))

def format_tree_item(label, value, branch="├─", indent=" "):
    """트리 가지 한 항목을 '라벨 정렬 + 콜론 정렬 + 값 줄바꿈 시 세로줄 연결'로 조판."""
    padded = _pad_label(label, TREE_LABEL_WIDTH)
    prefix = f"{indent}{branch} {padded}: "
    stem = "│" if branch.startswith("├") else " "
    cont_prefix = indent + stem + " " * (
        display_width(prefix) - display_width(indent) - 1
    )
    chunks = _wrap_by_width(value, TREE_TOTAL_WIDTH - display_width(prefix))
    out = prefix + (chunks[0] if chunks else "")
    for chunk in chunks[1:]:
        out += "\n" + cont_prefix + chunk
    return out

def format_kv_line(symbol, label, value):
    """'[!] 건너뜀   : 값' — 트리 가지와 같은 콜론 열에 정렬된 단일 kv 라인."""
    padded = _pad_label(label, TREE_LABEL_WIDTH)
    prefix = f"{symbol} {padded}: "
    chunks = _wrap_by_width(value, max(10, TREE_TOTAL_WIDTH - display_width(prefix)))
    out = prefix + (chunks[0] if chunks else "")
    cont = " " * display_width(prefix)
    for chunk in chunks[1:]:
        out += "\n" + cont + chunk
    return out

def format_target_url(url, max_len=50):
    """URL을 트리 가지 형태로 출력. 길면 '│' 세로줄로 이어지는 정렬된 줄바꿈."""
    return format_tree_item("대상", url, branch="└─")

def format_analysis_counts(v_count, a_count):
    """분석 완료 로그의 포맷 개수 요약 문자열."""
    if v_count and a_count:
        return f" (v:{v_count}, a:{a_count})"
    if v_count:
        return f" (v:{v_count})"
    if a_count:
        return f" (a:{a_count})"
    return ""


def format_pick_menu(v_list, a_list, max_rows=40):
    """[포맷 직접 고르기] 비디오/오디오 목록을 번호 매긴 선택 메뉴로 변환.

    각 항목 라벨은 v/a 분석 워커가 만든 파이프 컬럼 식이므로
    앞에 1-based 인덱스만 붙여 출력한다. UX 규칙 — 빈 입력 = 최고 품질,
    'N' = 비디오 N, 'N.M' = 비디오 N + 오디오 M.
    """
    lines = []
    if v_list:
        lines.append("video formats")
        for idx, f in enumerate(v_list[:max_rows], 1):
            label = f.get("label") or f.get("id") or "?"
            lines.append(f"  {idx:>2}  {label}")
        if len(v_list) > max_rows:
            lines.append(f"  ... {len(v_list) - max_rows} more")
    if a_list:
        lines.append("audio formats")
        for idx, f in enumerate(a_list[:max_rows], 1):
            label = f.get("label") or f.get("id") or "?"
            lines.append(f"  {idx:>2}  {label}")
        if len(a_list) > max_rows:
            lines.append(f"  ... {len(a_list) - max_rows} more")
    return lines

### ──────────────────────────────────────────────────────────────
### 컬럼 로그 라인 — TUI 스타일 고정 칼럼 포맷 (v3.4.0 4칸 미니멀)
### ──────────────────────────────────────────────────────────────
# 포맷: [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG
#   STAGE   : SYS / DEPS / ANAL / DL / LIVE / MERG / BATCH / POT (5폭)
#   STATUS  : READY / RUN / OK / DONE / SKIP / WARN / FAIL / ABORT / END (5폭)
#   SCOPE   : 발생지·대상 (엔진 YTDL/STRE/FFMP/NODE/POT, 플랫폼 YT/CHZ/TW/TIKT…,
#             시스템 MAIN — 5폭, media.platform_short 실측값)
#   MSG     : [tag] 전두 + 진행률 고정형(PCT 3폭우측 · SPEED 8폭우측 + GAUGE 10블록)

def _log_ts():
    """현재 시각 — [HH:MM:SS] 형식."""
    return time.strftime("[%H:%M:%S]")

def is_tui_line(msg):
    """[호환 shim] 구버전 콘텐츠 판정 — 렌더 레이어에서는 더 이상 사용하지 않는다.

    줄바꿈 결정은 발행자(raw → 구독자) 플래그(_flow_lines no_wrap)가 유일한
    기준이다. 외부 호출부 호환용으로만 남겨두며, 구조적(non-regex) 판정은 유지한다.
    """
    s = str(msg).strip()
    # [HH:MM:SS] : 위치/숫자 구조 검증 (regex 없음)
    if not (len(s) >= 12 and s[0] == "[" and s[3] == ":"
            and s[6] == ":" and s[9] == "]" and s[10] == " "
            and s[1:3].isdigit() and s[4:6].isdigit() and s[7:9].isdigit()):
        return False
    # 컬럼 구분자 │ : 타임스탬프 뒤에 1글자 이상, 뒤에 1글자 이상
    idx = s.find("│", 11)
    return idx > 11 and idx < len(s) - 1

def _log_pct(pct):
    """진행률 — None이면 빈 문자열, 아니면 3폭 우측 정렬 (' 65%', '100%').

    지터링 방지: 게이지 시작 인덱스 고정을 위해 항상 동일한 폭을 차지한다.
    """
    if pct is None:
        return ""
    try:
        return f"{min(max(float(pct), 0.0), 100.0):3.0f}%"
    except (TypeError, ValueError):
        return ""


def _log_speed(speed):
    """속도 — '-'·빈 값이면 빈 문자열, 아니면 8폭 우측 정렬 (' 12.4M/s').

    지터링 방지: '9.1M/s'와 '12.4M/s'가 같은 폭을 차지해 게이지가 흔들리지 않는다.
    """
    s = str(speed or "").strip()
    if not s or s == "-":
        return ""
    return s[-8:].rjust(8)


def _log_bar(bar_frac, width=10):
    """텍스트 진행 바 — None이면 빈 문자열, 아니면 고정 10블록 '[████░░░░░░]'."""
    if bar_frac is None:
        return ""
    try:
        frac = min(max(float(bar_frac), 0.0), 1.0)
    except (TypeError, ValueError):
        return ""
    filled = int(round(frac * width))
    return f"[{'█' * filled}{'░' * (width - filled)}]"

def format_log_line(stage, status, scope="", msg="", spec="", speed="", pct=None,
                    bar_frac=None):
    """TUI 스타일 컬럼 로그 라인 — v3.4.0 4칸 미니멀 고정 정렬.

    표준 포맷:
        [HH:MM:SS] STAGE │ STATUS │ SCOPE │ MSG

    특징:
    - 고정 4칸: STAGE(5) · STATUS(5) · SCOPE(5) · MSG(가변). SPEC 컬럼 폐지.
    - spec(deprecated): 비어 있지 않으면 MSG 전두부 태그로 흡수 — "[1080p30] msg".
      '-'·빈 값은 버린다. 새 발행점에서 spec= 전달 금지.
    - 진행률 고정형: "[tag]  65% ·  12.4M/s [██████░░░░] · msg" —
      PCT 3폭 우측 · SPEED 8폭 우측 · GAUGE 10블록 고정으로 지터링 방지.
      extra가 비어 있으면 구분자 '·'도 찍지 않는다.
    - Zero Redundancy: msg 비어 있으면 꼬리 구분자(│) 미출력.

    인자:
        stage    : SYS / DEPS / ANAL / DL / LIVE / MERG / BATCH / POT (8종)
        status   : READY / RUN / OK / DONE / SKIP / WARN / FAIL / ABORT / END (9종)
        scope    : 발생지·대상 (엔진/플랫폼/MAIN — 5폭, media.platform_short 실측값)
        msg      : 영문 소문자 CLI 태그 (제목 등 데이터 제외하고 영문화)
        spec     : deprecated — [tag] 흡수용으로만 사용, 신규 전달 금지
        speed    : 네트워크 속도 (예: 12.4M/s) — MSG 고정형으로 통합
        pct      : 진행률 (0~100, None 가능) — MSG 고정형으로 통합
        bar_frac : 진행 바 (0.0~1.0, None 가능) — MSG 고정형으로 통합
    """
    stage_s = str(stage).upper()[:5].ljust(5)
    status_s = str(status).upper()[:5].ljust(5)
    scope_raw = str(scope or "").strip()
    if scope_raw in ("", "-", "NONE"):
        scope_s = "     "
    else:
        scope_upper = scope_raw.upper()
        # v3.4.0 표준 약자(YTDL/FFMP/NODE/POT/YT/CHZ/TW/TIKT 등)는 재축약 금지.
        # 플랫폼 이름(youtube/chzzk 등)만 media.platform_short로 축약한다.
        scope_s = (scope_upper if scope_upper in STAGES or scope_upper in STATUSES or scope_upper in {
            "YTDL", "STRE", "FFMP", "NODE", "POT", "MAIN", "RAW", "QUEUE", "DISK"
        } else _short_platform(scope_raw))[:5].ljust(5)

    # [SPEC 흡수] deprecated spec → MSG 전두부 [tag]. '-'·빈 값은 버린다.
    tag = ""
    spec_clean = str(spec or "").strip()
    if spec_clean and spec_clean != "-":
        tag = f"[{spec_clean[:24]}]"

    # [진행률 고정형] PCT(3폭) · SPEED(8폭) + GAUGE(10블록) — 지터링 방지.
    gauge_parts = []
    pct_s = _log_pct(pct)
    speed_s = _log_speed(speed)
    bar_s = _log_bar(bar_frac)
    if pct_s:
        gauge_parts.append(pct_s)
    if speed_s:
        gauge_parts.append(speed_s)
    gauge = " · ".join(gauge_parts)
    if bar_s:
        gauge = f"{gauge} {bar_s}" if gauge else bar_s

    msg_clean = str(msg or "").strip()
    head_parts = [p for p in (tag, gauge, msg_clean) if p]
    head = _log_ts() + " " + stage_s
    fixed = head + " │ " + " │ ".join((status_s, scope_s))
    if not head_parts:
        return fixed
    return fixed + " │ " + " · ".join(head_parts)


def format_log_line_for_event(event):
    """구조화된 LogEvent → TUI 컬럼 문자열 (뷰 전용 컬럼화 — 정규식 판정 제로).

    렌더링 책임은 View(메인로그 모듈)에 있고, LogEvent는 모델이다.
    rendered=True면 msg가 이미 표시 완성형이므로 재포맷하지 않는다.
    scope는 event.scope를 그대로 사용한다 (v3.4.0).
    """
    from chzzktube.core.log_event import LogEvent  # lazy import (순환 참조 방지)
    if not isinstance(event, LogEvent):
        return str(event)
    if event.rendered:
        return event.msg
    scope = event.scope
    return format_log_line(
        stage=event.stage,
        status=event.status,
        scope=scope,
        msg=event.msg,
        spec=event.spec,
        speed=event.speed,
        pct=event.pct,
        bar_frac=event.bar_frac,
    )


def emit_event(stage, status, scope="-", msg="", is_status=False, is_error=False):
    """단순 이벤트 1건."""
    from chzzktube.core.log_event import LogEvent  # lazy import
    return LogEvent(
        stage=stage, status=status, scope=scope, platform=scope, msg=msg,
        is_status=is_status, is_error=is_error,
    )


def emit_dl(status, scope="", msg="", speed="", pct=None, bar_frac=None,
            stage="DL", is_status=False, is_error=False):
    """DL 진행률/완료 이벤트."""
    from chzzktube.core.log_event import LogEvent  # lazy import
    return LogEvent(
        stage=stage, status=status, scope=scope, platform=scope, msg=msg,
        speed=speed, pct=pct, bar_frac=bar_frac,
        is_status=is_status, is_error=is_error,
    )


def emit_err(msg):
    """에러 1건 — FAIL 상태, 스코프 빈칸."""
    from chzzktube.core.log_event import LogEvent  # lazy import (순환 참조 방지)
    return LogEvent(stage="DL", status="FAIL", msg=msg, is_error=True)


def emit_progress(stage, status, scope="-", msg="", speed="", pct=None,
                  bar_frac=None, is_status=False, is_error=False):
    """진행률 표시 이벤트 — ANAL/DL/LIVE 단계."""
    from chzzktube.core.log_event import LogEvent  # lazy import
    return LogEvent(
        stage=stage, status=status, scope=scope, platform=scope, msg=msg,
        speed=speed, pct=pct, bar_frac=bar_frac,
        is_status=is_status, is_error=is_error,
    )


def emit_component(stage, status, scope, msg="", is_status=False, is_error=False):
    """컴포넌트/워커 결과 — DEPS / POT / READY 등."""
    from chzzktube.core.log_event import LogEvent  # lazy import
    return LogEvent(
        stage=stage, status=status, scope=scope, platform=scope, msg=msg,
        is_status=is_status, is_error=is_error,
    )
