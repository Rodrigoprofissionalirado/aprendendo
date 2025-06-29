from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout

class DiferencaCompraDialog(QDialog):
    def __init__(self, diferenca, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diferença de valor detectada")
        self.resultado = None

        layout = QVBoxLayout(self)
        sinal = "-" if diferenca < 0 else "+"
        label = QLabel(f"Diferença detectada: {sinal}R$ {abs(diferenca):.2f}\n\n"
                       "O que deseja fazer?")
        layout.addWidget(label)

        botoes = QHBoxLayout()
        btn_somente_alterar = QPushButton("Apenas alterar valor")
        btn_converter_abate = QPushButton("Converter diferença em abate/adiantamento")
        botoes.addWidget(btn_somente_alterar)
        botoes.addWidget(btn_converter_abate)
        layout.addLayout(botoes)

        btn_somente_alterar.clicked.connect(self.somente_alterar)
        btn_converter_abate.clicked.connect(self.converter_abate)

    def somente_alterar(self):
        self.resultado = "somente_alterar"
        self.accept()

    def converter_abate(self):
        self.resultado = "converter_abate"
        self.accept()
