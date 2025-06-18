import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QStackedWidget, QHBoxLayout
)
from PySide6.QtCore import Qt, QDate

# Importando os módulos
from compras import ComprasUI
from produtos import ProdutosUI
from debitos import DebitosUI
from dados_bancarios import DadosBancariosUI
from fornecedores import FornecedoresUI
from categorias_fornecedor import CategoriasUI

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema de Gestão")
        self.resize(900, 600)

        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layout principal
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)

        # Menu lateral com botões
        menu_layout = QVBoxLayout()
        main_layout.addLayout(menu_layout)

        # Área de conteúdo (telas)
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # Inicializando os módulos
        self.compras_ui = ComprasUI()
        self.produtos_ui = ProdutosUI()
        self.debitos_ui = DebitosUI()
        self.dados_bancarios_ui = DadosBancariosUI()
        self.fornecedores_ui = FornecedoresUI()
        self.categorias_ui = CategoriasUI()

        self.compras_ui.set_janela_debitos(self.debitos_ui)

        # Adicionando os módulos ao stack
        self.stack.addWidget(self.compras_ui)
        self.stack.addWidget(self.produtos_ui)
        self.stack.addWidget(self.debitos_ui)
        self.stack.addWidget(self.dados_bancarios_ui)
        self.stack.addWidget(self.fornecedores_ui)
        self.stack.addWidget(self.categorias_ui)

        # Botões do menu
        botoes = [
            ("Compras", self.compras_ui),
            ("Produtos", self.produtos_ui),
            ("Débitos", self.debitos_ui),
            ("Dados Bancários", self.dados_bancarios_ui),
            ("Fornecedores", self.fornecedores_ui),
            ("Categorias", self.categorias_ui),
        ]

        for i, (nome, widget) in enumerate(botoes):
            btn = QPushButton(nome)
            btn.clicked.connect(lambda _, index=i: self.stack.setCurrentIndex(index))
            menu_layout.addWidget(btn)

        menu_layout.addStretch()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    janela = MainWindow()
    janela.show()
    sys.exit(app.exec())
