### log_console.py - 간결 로그 콘솔 렌더러
"""간결 로그 QTextEdit의 렌더링 책임을 MainWindow로부터 분리한 모듈.
상태 줄 덮어쓰기(진행률 갱신), 색상 출력, 작업 구분 여백을 담당하며, MainWindow는 이 모듈에 로그 출력만 위임한다. """
import re
import time
import unicodedata
import theme
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QTextEdit

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
        self._buffer = []  # list[dict] = {msg, is_status, is_error, fg_color}

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

    def append(self, msg, is_status=False, is_error=False, fg_color=None):
        """빈 줄 생성 차단 및 정밀 문단 삭제 파이프라인."""
        self._sync_budget()  # 현재 뷰포트/폰트 기준 예산 보장 — 자동랩 침범 방지
        # [리플로우 대비] 원본 로그를 버퍼에 보관 (렌더 시점 절단을 위해 잘리지 않음)
        self._buffer.append(
            {"msg": msg, "is_status": is_status, "is_error": is_error, "fg_color": fg_color}
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
        # [핵심] 상태 틱 종료/업데이트 → 빈 홈 블록 시작점으로 재사용(같은 줄)
        #    상태 틱 재사용도 허용(not is_status 한정 X) — 퍼센트 업데이트가
        #    매번 새 줄에 나오는 '붙어나오는 퍼센트 로그' 버그 예방.
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

        clean_msg = msg

        # 3. [핵심] 줄바꿈(\n) 사이에만 insertBlock()을 호출하여 문장 끝 불필요한 빈 줄 생성 완전 차단
        #    비트리 일반 라인(pip 출력 등)은 예산 폭을 넘기면 여기서 wrap한다 —
        #    NoWrap 콘솔에서 화면 초과분이 가로로 흘러버리는 것을 방지.
        #    [리플로우] 렌더 시점 예산으로 msg를 잘라서 그린다 (원본은 버퍼 보존).
        inserted = self._insert_clamped(
            cursor, clean_msg, is_status, is_error, fg_color
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
        """렌더 시점 예산으로 마지막 ' │ ' 이후 msg를 절단 — 창 폭에 맞는 표시.

        원본(msg 전체)은 버퍼에 보존되어 있고, 화면 표시만 이 함수로
        예산에 맞게 '…' 절단한다. 창을 가로로 늘리면 예산이 커져 더 길게
        펼쳐진다.
        """
        if " │ " not in line:
            return line
        head, sep, msg = line.rpartition(" │ ")
        if not head or not msg:
            return line
        budget = max(4, TREE_TOTAL_WIDTH - display_width(head) - len(sep))
        return head + sep + _truncate_msg(msg, budget)

    def _insert_clamped(self, cursor, msg, is_status, is_error, fg_color):
        """한 로그(다중 줄 허용)를 렌더 클램프 후 삽입. (삽입 블록 수 반환)

        append와 reflow가 공유하는 유일한 삽입 경로 — 파이프라인 중복 제거.
        """
        inserted = 0
        lines = msg.split("\n")
        for idx, raw in enumerate(lines):
            for f_idx, line in enumerate(_flow_lines(raw)):
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
        """
        buf = self._buffer
        if not buf:
            return
        self.te.clear()
        self.last_log_was_status = False
        self.last_status_block_count = 1
        self._pending_blank = False
        self._just_removed_status = False

        # 상태 로그 연속 그룹의 마지막만 렌더링 대상으로 추려낸다
        entries = []
        i = 0
        while i < len(buf):
            e = buf[i]
            if e["is_status"]:
                j = i
                while j + 1 < len(buf) and buf[j + 1]["is_status"]:
                    j += 1
                entries.append(buf[j])
                i = j + 1
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
                cursor, e["msg"], e["is_status"], e["is_error"], e["fg_color"]
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
                    fmt.setForeground(QColor(theme.LOG_COLOR_SUCCESS))
                elif text.startswith("[!]"):
                    fmt.setForeground(QColor(theme.LOG_COLOR_ERROR))
                else:
                    fmt.setForeground(QColor(theme.LOG_COLOR_INFO))
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

def _line_segments(line, is_error, is_status=False):
    """간결 로그 한 줄의 색 위계 — 구조는 딤, 값은 화이트, 상태만 액센트."""
    if is_error:
        return [(line, theme.LOG_COLOR_ERROR)]
    if is_status or " | 용량:" in line:
        return [(line, theme.LOG_COLOR_INFO)]
    if line.startswith("[v]"):
        if "PO Token" in line:
            return [(line, theme.LOG_COLOR_VALUE)]
        return [(line, theme.LOG_COLOR_SUCCESS)]
    if line.startswith(("[+]", "[~]")):
        return [(line, theme.LOG_COLOR_INFO)]
    if line[:2] in (" ├", " └"):
        head, sep, tail = line.partition(": ")
        if sep:
            return [(head + sep, theme.LOG_COLOR_STRUCT), (tail, theme.LOG_COLOR_VALUE)]
        return [(line[:2], theme.LOG_COLOR_STRUCT), (line[2:], theme.LOG_COLOR_VALUE)]
    if line[:2] in (" │", "  "):
        # 줄기/들여쓰기 2칸만 딤 — 나머지는 전부 값(화이트)
        return [(line[:2], theme.LOG_COLOR_STRUCT), (line[2:], theme.LOG_COLOR_VALUE)]
    return [(line, theme.LOG_COLOR_VALUE)]

### 트리 라벨 공통 폭 — 콜론(:) 위치를 모든 가지에서 세로로 일치시킨다.
TREE_LABEL_WIDTH = 9  # kv 라벨('저장 완료'·'실패 사유' 등 전각 4자+공백) 기준
TREE_TOTAL_WIDTH = 56  # 간결 로그 창의 실질 가로 예산 (폴백 — update_tree_budget으로 갱신)
TAIL_PADDING_BLOCKS = 2  # 콘솔 바닥에 상시 유지하는 여백 빈 블록 수

def update_tree_budget(text_edit):
    """콘솔 뷰포트 폭을 글자 폭으로 나눠 트리 줄바꿈 예산을 동적 갱신한다.

    상한(100)을 두지 않는다 — 창을 가로로 늘리면 잘려 보이던 로그가
    유연하게 펼쳐진다. 초과분은 format_log_line의 '…' 절단이 처리한다.
    """
    global TREE_TOTAL_WIDTH
    char_w = text_edit.fontMetrics().horizontalAdvance(" ")
    if char_w > 0:
        # document margin(8px × 2) + QSS 프레임 여백을 제외한 실제 텍스트 폭
        cols = (text_edit.viewport().width() - 16) // char_w
        TREE_TOTAL_WIDTH = max(40, int(cols))

### 줄기 없는(' └─') 연속 줄의 선행 공백 폭 — cont_prefix는 prefix 폭(TREE_LABEL_WIDTH+6)만큼의 공백 나열
STEMLESS_CONT_WIDTH = TREE_LABEL_WIDTH + 6

def _flow_lines(line):
    """라인 분할 규칙 — Single-Line TUI는 wrap하지 않는다.

    *  TUI 컬럼 라인([HH:MM:SS] STAGE │ ...)과 트리 조판 줄은 그대로 한 줄 —
       예산 초과분은 ConciseLogConsole._render_clamp가 '…'로 절단한다.
    *  그 외 비트리 일반 라인(yt-dlp/pip 출력 등)만 예산 폭으로 wrap한다.
    """
    if is_tui_line(line) or line[:2] in (" ├", " └", " │"):
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
        return f" (비디오 {v_count}개, 오디오 {a_count}개)"
    if v_count:
        return f" (통합 포맷 {v_count}개)"
    if a_count:
        return f" (오디오 {a_count}개)"
    return ""

### ──────────────────────────────────────────────────────────────
### 컬럼 로그 라인 — TUI 스타일 고정 칼럼 포맷
### ──────────────────────────────────────────────────────────────
# 포맷: [HH:MM:SS] STAGE │ STATUS │ PLATFORM │ SPEC │ PERCENT │ [BAR] │ MSG
#   STAGE   : SYS / ANAL / DL / MERG / BATCH
#   STATUS  : OK / READY / RUN / DONE / ABORT / FAIL / END
#   BAR     : 텍스트 진행 바 (bar_frac 0.0~1.0)

def _log_ts():
    """현재 시각 — [HH:MM:SS] 형식."""
    return time.strftime("[%H:%M:%S]")

_TUI_RE = re.compile(r"^\s*\[\d{2}:\d{2}:\d{2}\] .+│.+")


def is_tui_line(msg):
    """TUI 컬럼 포맷 라인인지 판별 — 모든 로그 경로의 단일 판별 기준.

    *  True  : [HH:MM:SS] STAGE │ STATUS │ ... 형태의 컬럼 로그
    *  False : raw 텍스트 (yt-dlp 출력, pip 출력, 플레인 메시지 등)
    이중 포맷(메시지 내부에 타임스탬프가 또 겹친 라인)도 여기서 잡아낸다.
    """
    s = str(msg).strip()
    if not s:
        return False
    if len(s) < 18 or "│" not in s:
        return False
    head = s.split("│", 1)[0].strip()
    # 헤더가 [HH:MM:SS] STAGE 형태일 때만 TUI로 인정
    return _TUI_RE.match(s) is not None

def _log_pct(pct):
    """퍼센트 컬럼 — None 이면 '-', 아니면 '42.1%'."""
    if pct is None:
        return "-"
    try:
        return f"{float(pct):5.1f}%"
    except (TypeError, ValueError):
        return "-"

def _log_bar(bar_frac, width=10):
    """텍스트 진행 바 — None 이면 '-', 아니면 '[████░░░░░░]'."""
    if bar_frac is None:
        return "-"
    try:
        frac = min(max(float(bar_frac), 0.0), 1.0)
    except (TypeError, ValueError):
        return "-"
    filled = int(round(frac * width))
    return f"[{'█' * filled}{'░' * (width - filled)}]"

def _truncate_msg(msg, max_width):
    """msg를 max_width 표시폭으로 절단 — 초과 시 '…' 부호 부착."""
    if max_width < 4:
        max_width = 4
    w = 0
    out = []
    for ch in msg:
        ch_w = 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        if w + ch_w + 1 > max_width:  # +1 for ellipsis
            break
        out.append(ch)
        w += ch_w
    result = "".join(out)
    if len(result) < len(msg):
        result += "…"
    return result


def format_log_line(stage, status, platform="", spec="", pct=None, bar_frac=None, msg=""):
    """TUI 스타일 컬럼 로그 라인 — 단일 라인, 고정 칼럼 정렬.

    인자:
        stage    : SYS / ANAL / DL / MERG / BATCH
        status   : OK / READY / RUN / DONE / ABORT / FAIL / END
        platform : chzzk / youtube / streamlink / yt-dlp 등
        spec     : 해상도·속도 등 사양 문자열
        pct      : 진행률 (0~100, None 가능)
        bar_frac : 진행 바 (0.0~1.0, None 가능)
        msg      : 제목·부가 메시지 (예산 초과 시 자동 절단)
    """
    stage_s = str(stage).upper()[:8].ljust(8)
    status_s = str(status).upper()[:8].ljust(8)
    plat_s = (str(platform) or "-")[:12].ljust(12)
    spec_s = str(spec or "-")
    pct_s = _log_pct(pct)
    bar_s = _log_bar(bar_frac)
    head = _log_ts() + " " + stage_s
    rest = [status_s, plat_s]
    if str(spec or "-") not in ("-", ""):
        rest.append(spec_s)
    if pct is not None:
        rest.append(pct_s)
        rest.append(bar_s)
    fixed = head + " │ " + " │ ".join(rest)
    if msg:
        # [리플로우] 생성 시점에 자르지 않는다 — msg 전체를 라인에 넣고,
        # 화면 표시는 ConciseLogConsole._render_clamp가 예산에 맞춰 절단한다.
        # 그래야 창을 가로로 늘렸을 때 기존 로그도 펼쳐진다.
        return fixed + " │ " + msg
    return fixed

def _log_line_segments(line):
    """컬럼 로그 라인의 색상 — STATUS 기반 단색 분기."""
    if " │ FAIL" in line:
        return [(line, theme.LOG_COLOR_ERROR)]
    if " │ WARN" in line:
        return [(line, theme.LOG_COLOR_WARN)]
    if " │ ABORT" in line:
        return [(line, theme.LOG_COLOR_WARN)]
    if " │ DONE" in line or " │ OK " in line or " │ END" in line or " │ READY" in line:
        return [(line, theme.LOG_COLOR_SUCCESS)]
    if " │ RUN" in line:
        return [(line, theme.LOG_COLOR_ACCENT)]
    return [(line, theme.LOG_COLOR_INFO)]


# ════════════════════════════════════════════════════════════════════════
# 새 TUI 컬럼 로그 — emit_event / emit_progress / emit_component
# 메인/워커에서 호출하면 [HH:MM:SS] STAGE │ STATUS │ PLATFORM │ ... 한 줄 출력
# ════════════════════════════════════════════════════════════════════════

def emit_event(stage, status, platform="-", msg=""):
    """단순 이벤트 1줄 — POT/Update/사용자 액션/에러 모두 공통."""
    return format_log_line(
        stage=stage, status=status, platform=platform, spec="-", pct=None, bar_frac=None, msg=msg,
    )


def emit_progress(stage, status, platform="-", spec="-", pct=None, bar_frac=None, msg=""):
    """진행률 표시 라인 — ANAL/DL 단계."""
    return format_log_line(
        stage=stage, status=status, platform=platform, spec=spec, pct=pct, bar_frac=bar_frac, msg=msg,
    )


def emit_component(stage, status, platform, msg):
    """컴포넌트/워커 결과 — DEPS / POT / READY 등 system 단계.

    [16:20:01] SYS  │ OK   │ DEPS  │ Components up-to-date
    """
    return format_log_line(
        stage=stage, status=status, platform=platform, spec="-", pct=None, bar_frac=None, msg=msg,
    )
