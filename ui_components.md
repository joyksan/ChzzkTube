# 커스텀 위젯

from qfluentwidgets import ComboBox


class CustomComboBox(ComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)

    def addItem(self, text, userData=None, icon=None):
        super().addItem(text, icon=icon, userData=userData)
