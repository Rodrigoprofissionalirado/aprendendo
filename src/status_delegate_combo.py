from PySide6.QtWidgets import QStyledItemDelegate, QComboBox
from PySide6.QtGui import QColor, QBrush
from PySide6.QtCore import Qt

class StatusComboDelegate(QStyledItemDelegate):
    def __init__(self, status_colors, status_list, parent=None):
        super().__init__(parent)
        self.status_colors = status_colors
        self.status_list = status_list

    def paint(self, painter, option, index):
        status = index.data()
        color = QColor(self.status_colors.get(status, "#ffffff"))

        # Pinta o fundo
        painter.save()
        painter.fillRect(option.rect, color)

        # Decide a cor do texto conforme o fundo (contraste)
        def luminancia(c):
            # fórmula para luminância relativa (perceptual brightness)
            return 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        text_color = Qt.black if luminancia(color) > 186 else Qt.white
        painter.setPen(QColor(text_color))

        # Desenha o texto centralizado na célula
        text = index.data()
        painter.drawText(option.rect, Qt.AlignCenter, text)
        painter.restore()

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItems(self.status_list)
        return combo

    def setEditorData(self, editor, index):
        value = index.data()
        idx = self.status_list.index(value) if value in self.status_list else 0
        editor.setCurrentIndex(idx)

    def setModelData(self, editor, model, index):
        novo_status = editor.currentText()
        model.setData(index, novo_status)