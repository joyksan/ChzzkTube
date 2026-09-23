### log_console.py - 간결 로그 콘솔 렌더러
"""간결 로그 QTextEdit의 렌더링 책임을 MainWindow로부터 분리한 모듈.
상태 줄 덮어쓰기(진행률 갱신), 색상 출력, 작업 구분 여백을 담당하며, MainWindow는 이 모듈에 로그 출력만 위임한다. """
from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from chzzktube.core.log_emitter import (
    STEMLESS_CONT_WIDTH,
    TREE_TOTAL_WIDTH,
    _flow_lines,
    _wrap_by_width,
)
from chzzktube.ui.theme import (
    LOG_COLOR_ACCENT,
    LOG_COLOR_DIM,
    LOG_COLOR_ERROR,
    LOG_COLOR_INFO,
    LOG_COLOR_STRUCT,
    LOG_COLOR_SUCCESS,
    LOG_COLOR_VALUE,
    LOG_COLOR_WARN,
)


class ConciseLogConsole:
    """간결 로그 패널 전용 렌더러."""

    def __init__(self, text_edit):
        self.te = text_edit
        # 직전 로그가 덮어쓰기용 상태 로그였는지 기록하는 플래그
        self.last_log_was_status = False
        self.last_status_block_count = 1
        # 작업 종료 시 보증한 여백(add_task_separator) — 다음 append가 살린다
        self._pending_blank = False
        # [버그 수정] 상태 블록 제거 직후 플래그 — 다음 메시지가 새 블록에서 시작하도록 보장
        self._just_removed_status = False
        # [핵심] 자동 워드랩 금지 — QTextEdit이 임의로 줄을 접으면 '│' 줄기 없는
        # 침범 줄이 생겨 트리 문법이 파괴된다. 줄바꿈은 format_tree_item의
        # 예산 기반 wrap이 유일해야 하며, 화면 초과분은 가로로 흘러버리는 것을
        # 방지하기 위해 가로 스크롤로 흘린다.
        self.te.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        # [가로 스크롤 금지] 넘치는 내용은 '…' 절단이 처리 — 스크롤바가 생기지 않는다.
        self.te.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 예산 동기화 캐시 — (뷰포트 폭, 글자 폭)이 바뀐 때만 재계산
        self._budget_key = None
        # [리플로우 대비] 원본 로그 버퍼 — msg는 잘리지 않은 전체를 보관하고,
        # 화면에는 렌더 시점 예산으로 잘라서 그린다. 창 폭 변경 시 재구성 루트.
        # list[dict] = {msg, is_status, is_error, fg_color, no_wrap, component_id, is_progress}
        self._buffer = deque(maxlen=4096)
        # 진행률 갱신형 라인 추적: component_id -> buffer index
        self._progress_lines: dict[str, int] = {}

    def _sync_budget(self):
        """로그를 찍는 시점 기준으로 트리 줄바꿈 예산을 재동기화한다.

        init_ui 시점엔 레이아웃이 실행 전이라 뷰포트 폭이 부정확하고,
        스플리터로 콘솔 폭을 조정하면 MainWindow.resizeEvent 자체가
        호출되지 않는다. append 직전에 폭/폰트를 검사해 바뀌었을 때만
        재계산하므로 비용은 사실상 없다.

        [리플로우] 예산이 실제로 바뀌면 _buffer의 원본 로그들을 새 예산으로
        전체 재구성한다 — 창을 가로로 늘리면 기존 로그까지 펼쳐진다.
        """
        self.on_resize()

    def on_resize(self):
        """콘솔 뷰포트 폭/폰트 변화 감시 — 바뀌면 예산 갱신 + 전체 reflow."""
        vp_w = self.te.viewport().width()
        char_w = self.te.fontMetrics().horizontalAdvance(" ")
        key = (vp_w, char_w)
        if key != self._budget_key:
            self._budget_key = key
            update_tree_budget(self.te)
            if self._buffer:
                self.reflow()

    def append(self, msg, is_status=False, is_error=False, fg_color=None, no_wrap=False, 
           component_id: str = None, is_progress: bool = False):
        """빈 줄 생성 차단 및 정밀 문단 삭제 파이프라인.

        [진행률 갱신형 계약] 진행률/진행 중 상태 로그는 반드시 is_status=True로
        호출할 것 — ConciseLogConsole이 직전 상태 블록을 같은 줄에 덮어쓴다
        (Single-Line In-Place Status, HANDOVER §6). is_status=False로 emit하면
        매 틱 새 줄이 쌓여 '한 행 = 한 정보' 규칙을 위반한다. DL/LIVE 틱,
        DEPS 다운로드 %, PO 서버 진행 등 모든 반복 로그가 해당.

        [다중 컴포넌트 진행률 갱신형] component_id와 is_progress=True로 호출하면
        해당 컴포넌트의 기존 진행 라인을 갱신한다 (여러 컴포넌트 동시 갱신형 지원).
        이 라인은 is_status 로그에 의해 지워지지 않으며, 완료 시 is_progress=False로
        호출하면 히스토리로 확정된다.

        [줄바꿈 계약] 줄바꿈 결정은 발행자(raw() 경유 LogEvent → 구독자) 측의
        no_wrap 플래그를 그대로 따르며, 렌더 레이어에서 문자열 내용을 다시
        뜯어 판단하지 않는다(정규식 라우팅 제로). LogEvent 경유분(컬럼 포맷·
        프리포맷)은 True, 큐 호환용 bare 문자열은 False다.
        """
        self._sync_budget()  # 현재 뷰포트/폰트 기준 예산 보장 — 자동랩 침범 방지
        clean_msg = str(msg)     # 인자로 들어온 msg를 함수 진입 즉시 안전한 문자열로 바인딩

        # 진행률 갱신형: 기존 라인 갱신
        if component_id and is_progress:
            self._update_progress_line(component_id, clean_msg, is_error, fg_color, no_wrap)
            return

        # 진행률 완료: 진행 중이던 기존 버퍼 엔트리의 is_progress를 False로 잠그고 제자리 확정
        if component_id and not is_progress and component_id in self._progress_lines:
            idx = self._progress_lines.pop(component_id)
            if 0 <= idx < len(self._buffer):
                self._buffer[idx]["msg"] = clean_msg
                self._buffer[idx]["is_progress"] = False
                self._buffer[idx]["is_status"] = False
                self._buffer[idx]["is_error"] = is_error
            # 버퍼 제자리 라인을 완료 메시지로 갱신한 뒤 즉시 화면에 확정 박제!
            self.reflow()
            return

        # [리플로우 대비] 원본 로그를 버퍼에 보관
        self._buffer.append(
            {"msg": clean_msg, "is_status": is_status, "is_error": is_error,
             "fg_color": fg_color, "no_wrap": bool(no_wrap),
             "component_id": component_id, "is_progress": is_progress}
        )
        doc = self.te.document()
        cursor = self.te.textCursor()

        # 0. 바닥 여백용 빈 블록을 치운다 — 새 로그는 항상 내용 위에 붙고,
        #    여백은 삽입 완료 후 다시 깔린다(상시 유지). 직전에 작업 종료
        #    여백이 보증됐다면(add_task_separator) 빈 블록 '한 줄'은 살려
        #    둔다 — 완료 로그와 다음 로그 사이의 한 칸 띄우기.
        keep_blank = self._pending_blank
        self._pending_blank = False
        self._strip_tail_padding(keep_one=keep_blank)

        # 1. 직전 로그가 상태 메시지(is_status=True)였다면 상태 블록을 정리한다.
        #    이때 마지막 블록은 '빈 홈 블록'으로 남긴다 — 상태 줄의 첫 블록을
        #    직전 블록(작업 구분 여백)에 병합하면 여백이 먹혀 중단 로그와
        #    다음 작업 로그가 붙어버리는 문제의 원인이었다.
        if self.last_log_was_status and not doc.isEmpty():
            self._remove_status_blocks()
            self.last_log_was_status = False
            self._just_removed_status = True  # 빈 홈 재사용 좌표 시그널

        # 2. 커서 최하단 이동 (문서가 비어있지 않고 줄 시작점이 아니면 1줄 개행).
        #    커서가 '보증된 여백' 빈 블록 위에 서 있으면 그 블록을 내용으로
        #    채우지 않고 한 줄 더 개행해 여백을 살린다.
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self._just_removed_status and not doc.isEmpty() and not doc.lastBlock().text():
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        on_kept_blank = (
            keep_blank
            and not doc.isEmpty()
            and cursor.atBlockStart()
            and not doc.lastBlock().text()
        )
        # [핵심] 블록 삽입 판정 — Single-Line In-Place Status를 지킨다.
        # 재사용 중(빈 홈 시작점)이면 insertBlock 생략 → 같은 블록에 텍스트 삽입
        reuse_status_home = (
            self._just_removed_status
            and not doc.isEmpty()
            and not doc.lastBlock().text()
            and cursor.atBlockStart()
        )
        if not doc.isEmpty() and not reuse_status_home and (
            not cursor.atBlockStart()
            or on_kept_blank
            or doc.lastBlock().text()
        ):
            cursor.insertBlock()
        self._just_removed_status = False  # 플래그 소비

        # 3. [핵심] 줄바꿈(\n) 사이에만 insertBlock()을 호출하여 문장 끝 불필요한 빈 줄 생성 완전 차단
        #    비트리 일반 라인(pip 출력 등)은 예산 폭을 넘기면 여기서 wrap한다 —
        #    NoWrap 콘솔에서 화면 초과분이 가로로 흘러버리는 것을 방지.
        #    [리플로우] 렌더 시점 예산으로 msg를 잘라서 그린다 (원본은 버퍼 보존).
        inserted = self._insert_clamped(
            cursor, clean_msg, is_status, is_error, fg_color, bool(no_wrap)
        )

        # 4. 상태 플래그 및 블록 수 기록 — wrap 포함 실제 삽입 블록 수
        self.last_log_was_status = is_status
        self.last_status_block_count = max(1, inserted)

        # 5. 바닥 여백 상시 유지 — 마지막 로그와 콘솔 바닥 사이 2줄 간격
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._add_tail_padding(cursor)

        self.te.moveCursor(QTextCursor.MoveOperation.End)
        sb = self.te.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _update_progress_line(self, component_id: str, msg: str, is_error: bool, fg_color: str, no_wrap: bool):
        """특정 컴포넌트의 진행률 라인을 갱신 (buffer 교체 + reflow)."""
        idx = self._progress_lines.get(component_id)
        if idx is not None and 0 <= idx < len(self._buffer):
            # 기존 버퍼 엔트리 갱신
            self._buffer[idx] = {
                "msg": msg,
                "is_status": False,
                "is_error": is_error,
                "fg_color": fg_color,
                "no_wrap": bool(no_wrap),
                "component_id": component_id,
                "is_progress": True,
            }
        else:
            # 새 진행 라인 추가
            self._buffer.append({
                "msg": msg,
                "is_status": False,
                "is_error": is_error,
                "fg_color": fg_color,
                "no_wrap": bool(no_wrap),
                "component_id": component_id,
                "is_progress": True,
            })
            self._progress_lines[component_id] = len(self._buffer) - 1
        
        # 전체 reflow로 갱신 반영
        self.reflow()

    def add_task_separator(self):
        """하나의 다운로드 작업이 완전히 종료되었을 때만 1줄 여백 추가.

        삽입한 빈 블록은 다음 append of _strip_tail_padding에서 걷히지 않게
        _pending_blank로 보증한다 — '완료 로그 다음 한 칸 띄우기'.
        """
        doc = self.te.document()
        if not doc.isEmpty():
            self._strip_tail_padding()
            cursor = self.te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertBlock()
            self._add_tail_padding(cursor)
            self.last_log_was_status = False
            self._pending_blank = True

    def clear_status_line(self):
        """남아있는 애니메이션 상태 로그 블록을 깔끔하게 삭제.

        블록 자체는 빈 홈으로 남긴다 — 상태 줄이 차지했던 자리가 원래
        작업 구분 여백이었다면 원상복구되어야 하기 때문이다.
        """
        if self.last_log_was_status:
            self._remove_status_blocks()
            self.last_log_was_status = False
            self._just_removed_status = True

    def _remove_status_blocks(self):
        """상태 로그 블록 last_status_block_count개를 '빈 홈 블록 1개'로 정리.

        블록 경계는 (n-1)개만 병합하고 마지막 블록은 텍스트만 지워 빈 채로
        남긴다. 기존 방식(n회 clear+병합)은 상태 줄의 첫 블록을 직전 블록에
        병합해버려서, 직전 블록이 작업 구분 여백(빈 줄)이면 여백이 먹혔다 —
        '중단 로그 바로 아래에 다음 작업 로그가 붙는' 현상의 원인.
        """
        cursor = self.te.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for _ in range(max(0, self.last_status_block_count - 1)):
            cursor.movePosition(
                QTextCursor.MoveOperation.StartOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            if not cursor.atStart():
                cursor.deletePreviousChar()
            cursor.movePosition(QTextCursor.MoveOperation.End)
        # 마지막 남은 상태 블록의 텍스트만 제거 (블록/여백은 유지)
        cursor.movePosition(
            QTextCursor.MoveOperation.StartOfBlock,
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.removeSelectedText()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # [버그 수정] 상태 블록 제거 직후 — 다음 append가 새 블록을 삽입하도록 플래그 설정
        self._just_removed_status = True

    def reset_status_flag(self):
        """상태 로그를 히스토리로 확정 보존(덮어쓰기 중단)."""
        self.last_log_was_status = False

    def _render_clamp(self, line):
        """렌더 시점 절단 — 마지막 ' │ ' 이후 msg를 viewport 우측까지 픽셀 정렬.

        원본(msg 전체)은 _buffer에 보존되고, 이 함수는 화면 표시만
        viewport 픽셀 폭에 맞춰 '…'로 자른다. 핵심은 display_width
        (east_asian_width 기반 문자 단위 추정)가 아니라 fontMetrics의
        horizontalAdvance로 *실제 픽셀 폭*을 재는 것이다 — Cascadia Mono는
        한글 2칸·latin 1칸·'│'(U+2502, Ambiguous)는 폰트에 따라 1칸이
        되는 비일관성이 있어, 문자 단위 추론만으로는 짤림 위치가 들쭉날쭉
        해진다. 픽셀 단위 절단으로 폰트/Ambiguous 폭/한영 혼용에 무관하게
        viewport 우측에서 일정하게 끝난다.

        우측에는 RIGHT_PADDING_PX 만큼 가독성 여백을 남긴다 — 글자
        가장자리가 프레임에 붙는 것을 막아 위 압박감을 줄인다.
        """
        fm = self.te.fontMetrics()
        viewport_px = self.te.viewport().width()
        if viewport_px <= 0:
            # 위젯이 아직 실측되지 않은 시점(초기화 직후) — 보수적으로 원본 유지
            return line
        if " │ " not in line:
            # TUI 가 아닌 라인 — viewport 폭에서 우측 패딩을 뺀 만큼 통째로 자른다
            return _truncate_by_pixels(line, viewport_px - RIGHT_PADDING_PX, fm)
        head, _, msg = line.rpartition(" │ ")
        if not head:
            return line
        # head + 마지막 ' │ ' 까지의 실제 픽셀 폭을 잰다 — '│'의 Ambiguous
        # 폭(1칸/2칸)과 Cascadia Mono의 한글/라틴 폭 차이를 그대로 반영한다.
        head_px = fm.horizontalAdvance(head + " │ ")
        msg_budget_px = viewport_px - head_px - RIGHT_PADDING_PX
        return head + " │ " + _truncate_by_pixels(msg, msg_budget_px, fm)

    def _insert_clamped(self, cursor, msg, is_status, is_error, fg_color, no_wrap=False):
        """한 로그(다중 줄 허용)를 렌더 클램프 후 삽입. (삽입 블록 수 반환)

        append와 reflow가 공유하는 유일한 삽입 경로 — 파이프라인 중복 제거.
        no_wrap 플래그를 _flow_lines에 그대로 전달한다.
        """
        inserted = 0
        lines = msg.split("\n")
        for idx, raw in enumerate(lines):
            for f_idx, line in enumerate(_flow_lines(raw, no_wrap)):
                if idx > 0 or f_idx > 0:
                    cursor.insertBlock()
                inserted += 1
                line = self._render_clamp(line)
                if fg_color is not None:
                    fmt = QTextCharFormat()
                    fmt.setFont(self.te.font())
                    fmt.setForeground(QColor(fg_color))
                    cursor.insertText(line, fmt)
                else:
                    for seg, color in _line_segments(line, is_error, is_status):
                        fmt = QTextCharFormat()
                        fmt.setFont(self.te.font())
                        fmt.setForeground(QColor(color))
                        cursor.insertText(seg, fmt)
        return inserted

    def reflow(self):
        """창 폭 변경 시 전체 재렌더링 — 버퍼의 원본 로그를 새 예산으로 다시 그린다.

        상태 로그는 연속 그룹의 마지막 것만 그려 Single-Line In-Place를 유지한다.
        진행률 라인(is_progress=True)은 모두 보존한다.
        """
        buf = self._buffer
        if not buf:
            return
        self.te.clear()
        self.last_log_was_status = False
        self.last_status_block_count = 1
        self._pending_blank = False
        self._just_removed_status = False

        # 상태 로그 연속 그룹의 마지막만, 진행률 라인은 모두 렌더링 대상으로 추려낸다
        entries = []
        i = 0
        while i < len(buf):
            e = buf[i]
            if e.get("is_status"):
                j = i
                while j + 1 < len(buf) and buf[j + 1].get("is_status"):
                    j += 1
                entries.append(buf[j])
                i = j + 1
            elif e.get("is_progress"):
                # 진행률 라인은 모두 포함
                entries.append(e)
                i += 1
            else:
                entries.append(e)
                i += 1

        doc = self.te.document()
        cursor = self.te.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for idx, e in enumerate(entries):
            if idx > 0 or not doc.isEmpty():
                cursor.insertBlock()
            self._insert_clamped(
                cursor, e["msg"], e.get("is_status", False), e.get("is_error", False), e.get("fg_color"),
                e.get("no_wrap", False),
            )

        # 바닥 여백 상시 유지
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._add_tail_padding(cursor)

        self.te.moveCursor(QTextCursor.MoveOperation.End)
        sb = self.te.verticalScrollBar()
        sb.setValue(sb.maximum())

    def remove_last_blocks(self, count):
        """마지막 count개 블록을 흔적 없이 제거 (분석 결과 블록 철회용).

        _remove_status_blocks가 '빈 홈'을 남기는 것과 달리 블록 경계까지
        완전히 삭제한다 — '없었던 일'로 만드는 것이 목적. 문서 첫 블록
        (초기 안내문)은 항상 남긴다.
        """
        doc = self.te.document()
        if count <= 0 or doc.isEmpty():
            return
        self._strip_tail_padding()
        count = min(count, doc.blockCount() - 1)
        if count <= 0:
            return
        cursor = self.te.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for _ in range(count):
            cursor.movePosition(
                QTextCursor.MoveOperation.StartOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            if not cursor.atStart():
                cursor.deletePreviousChar()
            cursor.movePosition(QTextCursor.MoveOperation.End)
        self._add_tail_padding()
        self.last_log_was_status = False

    def _strip_tail_padding(self, keep_one=False):
        """문서 끝의 여백용 빈 블록을 제거한다 (내용 블록이 마지막이 되도록).

        첫 블록은 어떤 경우에도 남긴다 — 문서 전체가 빈 블록뿐일 때는
        그 상태를 유지해야 QTextEdit '빈 문서' 판정(isEmpty)이 유효하기 때문.
        keep_one=True면 내용 블록 바로 뒤의 빈 블록 한 개는 남긴다 —
        작업 종료 시 보증된 여백(add_task_separator)이다.
        """
        doc = self.te.document()
        while doc.blockCount() > 1:
            b = doc.lastBlock()
            if b.text():
                break
            cursor = self.te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.movePosition(
                QTextCursor.MoveOperation.StartOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            if not cursor.atStart():
                cursor.deletePreviousChar()
        # keep_one — 마지막 내용 블록 바로 뒤 of 빈 블록 '한 개'를 보증한다.
        # (strip은 문서 앞쪽 크기와 무관하게 전부 걷으므로, 보증은 재삽입으로)
        if keep_one and not doc.isEmpty():
            b = doc.lastBlock()
            if b.text():
                cursor = self.te.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertBlock()

    def _add_tail_padding(self, cursor=None):
        """콘솔 바닥에 2줄 여백을 깐다 — 마지막 로그가 테두리에 붙지 않게.

        QSS padding-bottom(정적 여백)과 달리 문서 블록이라 스크롤 범위에
        포함되며, 새 로그 삽입 직전 _strip_tail_padding으로 걷어낸다.
        """
        if cursor is None:
            cursor = self.te.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
        for _ in range(TAIL_PADDING_BLOCKS):
            cursor.insertBlock()

    def last_content_block_text(self):
        """바닥 여백 빈 블록을 건너뛴 마지막 내용 블록의 텍스트.

        setHtml 산출 블록은 줄구분자(U+2028)·공백 꼬리를 가질 수 있어
        toPlainText 기반 문자열과 비교 가능하도록 잘라낸다.
        """
        b = self.te.document().lastBlock()
        while b.isValid() and not b.text():
            b = b.previous()
        return b.text().rstrip("\u2028 \t") if b.isValid() else ""

    def insert_after_ready(self, text):
        """기동 인사줄('[ChzzkTube vX.Y.Z] by Miorine') 바로 다음 줄에 로그를 삽입."""
        self._sync_budget()
        b = self.te.document().lastBlock()
        for _ in range(4):
            if not b.isValid():
                break
            t = b.text()
            if "by Miorine" in t:
                body = t.rstrip("\u2028 \t")
                cursor = QTextCursor(b)
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.MoveAnchor,
                    len(body),
                )
                fmt = QTextCharFormat()
                fmt.setFont(self.te.font())
                # 심볼별 색 — append 파이프라인의 색 위계와 동일하게
                if text.startswith("[v]"):
                    fmt.setForeground(QColor(LOG_COLOR_SUCCESS))
                elif text.startswith("[!]"):
                    fmt.setForeground(QColor(LOG_COLOR_ERROR))
                else:
                    fmt.setForeground(QColor(LOG_COLOR_INFO))
                # 인사줄 '다음 줄'에 새 블록으로 삽입한다(같은 줄 병기 아님).
                # 예산 초과분은 줄기 없는 연속 줄 문법(공백 나열)으로 접지
                # 않으면 NoWrap 콘솔에서 가로로 침범한다.
                chunks = _wrap_by_width(text, TREE_TOTAL_WIDTH)
                joined = "\n" + ("\n" + " " * STEMLESS_CONT_WIDTH).join(chunks)
                cursor.insertText(joined, fmt)
                # 삽입 후 커서가 남아 가로 스크롤을 밀지 않게 원점 복귀
                hsb = self.te.horizontalScrollBar()
                hsb.setValue(0)
                return True
            b = b.previous()
        return False

TAIL_PADDING_BLOCKS = 2  # 콘솔 바닥에 상시 유지하는 여백 빈 블록 수
RIGHT_PADDING_PX = 20  # 픽셀 기반 절단 시 viewport 우측에 남기는 가독성 여백 (한글 1자 너비)


def update_tree_budget(text_edit):
    """콘솔 뷰포트 폭을 글자 폭으로 나눠 트리 줄바꿈 예산을 동적 갱신한다.

    상한(100)을 두지 않는다 — 창을 가로로 늘리면 잘려 보이던 로그가
    유연하게 펼쳐진다. 초과분은 format_log_line의 '…' 절단이 처리한다.
    """
    from chzzktube.core import log_emitter
    char_w = text_edit.fontMetrics().horizontalAdvance(" ")
    if char_w > 0:
        # document margin(8px × 2) + QSS 프레임 여백을 제외한 실제 텍스트 폭
        cols = (text_edit.viewport().width() - 16) // char_w
        log_emitter.TREE_TOTAL_WIDTH = max(40, int(cols))


def _truncate_by_pixels(msg, budget_px, fm):
    """msg를 fontMetrics 기반 *실제 픽셀 폭*으로 절단 — 초과 시 '…' 부착."""
    if budget_px <= 0:
        return "…"
    ellipsis_px = fm.horizontalAdvance("…")
    if budget_px <= ellipsis_px:
        return "…"
    out = []
    for ch in msg:
        candidate = "".join(out) + ch + "…"
        if fm.horizontalAdvance(candidate) > budget_px:
            break
        out.append(ch)
    result = "".join(out)
    if len(result) < len(msg):
        result += "…"
    return result


def _line_segments(line, is_error, is_status=False):
    """간결 로그 한 줄의 색 위계 — 구조는 딤, 값은 화이트, 상태만 액센트."""
    if is_error:
        return [(line, LOG_COLOR_ERROR)]
    if is_status or " | 용량:" in line:
        return [(line, LOG_COLOR_INFO)]
    if line.startswith("[v]"):
        if "PO Token" in line:
            return [(line, LOG_COLOR_VALUE)]
        return [(line, LOG_COLOR_SUCCESS)]
    if line.startswith(("[+]", "[~]")):
        return [(line, LOG_COLOR_INFO)]
    if line[:2] in (" ├", " └"):
        head, sep, tail = line.partition(": ")
        if sep:
            return [(head + sep, LOG_COLOR_STRUCT), (tail, LOG_COLOR_VALUE)]
        return [(line[:2], LOG_COLOR_STRUCT), (line[2:], LOG_COLOR_VALUE)]
    if line[:2] in (" │", "  "):
        # 줄기/들여쓰기 2칸만 딤 — 나머지는 전부 값(화이트)
        return [(line[:2], LOG_COLOR_STRUCT), (line[2:], LOG_COLOR_VALUE)]
    return [(line, LOG_COLOR_VALUE)]


def _log_line_segments(line):
    """컬럼 로그 라인의 색상 — STATUS 기반 단색 분기 (v3.4.0 5폭)."""
    if " │ FAIL " in line or " │ FAIL│" in line or line.rstrip().endswith(" │ FAIL"):
        return [(line, LOG_COLOR_ERROR)]
    if " │ WARN " in line or line.rstrip().endswith(" │ WARN"):
        return [(line, LOG_COLOR_WARN)]
    if " │ ABORT" in line:
        return [(line, LOG_COLOR_WARN)]
    if " │ DONE " in line or " │ OK   " in line or " │ END  " in line or " │ READY" in line:
        return [(line, LOG_COLOR_SUCCESS)]
    if " │ SKIP " in line:
        return [(line, LOG_COLOR_DIM)]
    if " │ RUN  " in line:
        return [(line, LOG_COLOR_ACCENT)]
    return [(line, LOG_COLOR_INFO)]
