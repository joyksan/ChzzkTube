"""TUI 규격 통합 안내창 계약 — 쿠키 완료 확인창 정렬/버튼 교정.

[배경] 쿠키 설정 완료 안내가 기존 QMessageBox(MSGBOX_QSS)라 텍스트 중앙
정렬이 깨지고 OK 버튼 배치도 다른 다이얼로그(ExitConfirmDialog)와 양식이
달랐다. TuiNoticeDialog로 통일하며, 같은 QMessageBox 계열이던 쿠키 초기화/
브라우저 추출 오류 안내도 동일 규격으로 위임한다.

[계약]
1. 280x125 고정, 칠흑 배경(DIALOG_BG_QSS), 라벨 중앙 정렬 — ExitConfirmDialog 동일.
2. alt_label 지정 시 2버튼(View + OK), done 코드 RESULT_OK=0 / RESULT_ALT=2.
3. show_info_message(detail=None)는 TuiNoticeDialog를 exec한다(QMessageBox 아님).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton

from chzzktube.ui import theme
from chzzktube.ui.dialogs import TuiNoticeDialog, show_info_message


def _labels(dlg):
    return sorted(b.text() for b in dlg.findChildren(QPushButton))


def test_notice_dialog_matches_exit_confirm_geometry():
    dlg = TuiNoticeDialog(text="✓ 쿠키 설정이 완료되었습니다.\n(Cookies.txt 파일)")
    assert dlg.size().width() == 280 and dlg.size().height() == 125
    lbl = dlg.findChild(QLabel)
    assert lbl.alignment() & Qt.AlignmentFlag.AlignHCenter
    assert lbl.alignment() & Qt.AlignmentFlag.AlignVCenter
    assert theme.BG_WINDOW in dlg.styleSheet()


def test_notice_dialog_view_ok_two_buttons():
    dlg = TuiNoticeDialog(text="msg", alt_label="View")
    assert _labels(dlg) == ["OK", "View"]


def test_notice_dialog_result_codes_distinguish_alt():
    dlg = TuiNoticeDialog(text="msg", alt_label="View")
    # 부가 버튼 = RESULT_ALT(2), 기본 accept = RESULT_OK(0)
    btn_view = next(b for b in dlg.findChildren(QPushButton) if b.text() == "View")
    btn_view.click()
    assert dlg.result() == TuiNoticeDialog.RESULT_ALT


def test_show_info_message_delegates_to_notice(monkeypatch):
    seen = {}

    class _Spy(TuiNoticeDialog):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            seen.update(kw)

        def exec(self):
            seen["exec_called"] = True

    monkeypatch.setattr("chzzktube.ui.dialogs.TuiNoticeDialog", _Spy)
    show_info_message(None, "초기화", "쿠키가 초기화되었습니다.")
    assert seen.get("exec_called") is True
    assert seen.get("ok_label") == "OK"
    assert seen.get("text").startswith("✓")
