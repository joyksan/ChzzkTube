# 커스텀 위젯

from PyQt6.QtWidgets import QComboBox, QListView
from PyQt6.QtCore import pyqtProperty, QPropertyAnimation, QEasingCurve, Qt
from PyQt6.QtGui import QPainter, QPen, QColor

class CustomComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setView(QListView())
        self._arrow_angle = 0.0

        self.anim_arrow = QPropertyAnimation(self, b"arrow_angle")
        self.anim_arrow.setDuration(180)
        self.anim_arrow.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._is_hiding = False

    def get_arrow_angle(self):
        return self._arrow_angle

    def set_arrow_angle(self, angle):
        self._arrow_angle = angle
        self.update()

    arrow_angle = pyqtProperty(float, get_arrow_angle, set_arrow_angle)

    def showPopup(self):
        self._is_hiding = False
        self.anim_arrow.stop()
        self.anim_arrow.setStartValue(self._arrow_angle)
        self.anim_arrow.setEndValue(-180.0)
        self.anim_arrow.start()

        popup = self.view().window()
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        popup.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)

        self.anim_fade = QPropertyAnimation(popup, b"windowOpacity")
        self.anim_fade.setDuration(180)
        self.anim_fade.setStartValue(0.0)
        self.anim_fade.setEndValue(1.0)
        self.anim_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        super().showPopup()
        popup.move(self.mapToGlobal(self.rect().bottomLeft()))
        self.anim_fade.start()

    def hidePopup(self):
        if hasattr(self, '_is_hiding') and self._is_hiding:
            super().hidePopup()
            return

        self._is_hiding = True
        popup = self.view().window()

        self.anim_arrow.stop()
        self.anim_arrow.setStartValue(self._arrow_angle)
        self.anim_arrow.setEndValue(0.0)
        self.anim_arrow.start()

        self.anim_fade = QPropertyAnimation(popup, b"windowOpacity")
        self.anim_fade.setDuration(150)
        self.anim_fade.setStartValue(popup.windowOpacity())
        self.anim_fade.setEndValue(0.0)
        self.anim_fade.setEasingCurve(QEasingCurve.Type.InCubic)
        self.anim_fade.finished.connect(self._finish_hide)
        self.anim_fade.start()

    def _finish_hide(self):
        if hasattr(self, '_is_hiding') and self._is_hiding:
            super().hidePopup()
            self._is_hiding = False

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        x = rect.width() - 15
        y = rect.height() / 2

        painter.save()
        painter.translate(x, y)
        painter.rotate(self._arrow_angle)

        pen = QPen(QColor("#d4d4d4"), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        painter.drawLine(-4, -2, 0, 2)
        painter.drawLine(0, 2, 4, -2)

        painter.restore()