"""操作画面の入力欄の並び。"""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QFormLayout


class CenteredForm(QFormLayout):
    """項目名を、背の高い入力欄（一覧・入力欄）の縦の真ん中にそろえる。

    QFormLayout は項目名を欄の上端寄りに置くので、並べ終えたあとで縦だけ動かす。
    """

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 (Qt の名前)
        super().setGeometry(rect)
        for row in range(self.rowCount()):
            label = self.itemAt(row, QFormLayout.ItemRole.LabelRole)
            field = self.itemAt(row, QFormLayout.ItemRole.FieldRole)
            if label is None or field is None or label.widget() is None:
                continue
            placed = label.geometry()
            target = field.geometry()
            if target.height() <= placed.height():
                continue
            top = target.top() + (target.height() - placed.height()) // 2
            label.widget().setGeometry(placed.x(), top, placed.width(), placed.height())
