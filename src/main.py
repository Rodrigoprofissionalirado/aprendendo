import sys
import subprocess
import os
import urllib.request
import ajustes
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QStackedWidget, QHBoxLayout, QMessageBox
)
from PySide6.QtCore import Qt

def instalar_pip():
    url = "https://bootstrap.pypa.io/get-pip.py"
    script = "get-pip.py"
    urllib.request.urlretrieve(url, script)
    subprocess.check_call([sys.executable, script])
    os.remove(script)

def instalar_dependencias():
    try:
        import PySide6
    except ImportError:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        except FileNotFoundError:
            print("Pip não encontrado. Tentando instalar pip automaticamente...")
            instalar_pip()
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

instalar_dependencias()

# Importando os módulos
from compras import ComprasUI
from produtos import ProdutosUI
from debitos import DebitosUI
from dados_bancarios import DadosBancariosUI
from fornecedores import FornecedoresUI
from ajustes import AjustesUI

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
        self.ajustes_ui = AjustesUI()

        self.compras_ui.set_janela_debitos(self.debitos_ui)

        # Adicionando os módulos ao stack
        self.stack.addWidget(self.compras_ui)
        self.stack.addWidget(self.produtos_ui)
        self.stack.addWidget(self.debitos_ui)
        self.stack.addWidget(self.dados_bancarios_ui)
        self.stack.addWidget(self.fornecedores_ui)
        self.stack.addWidget(self.ajustes_ui)

        # Botões do menu
        botoes = [
            ("Compras", self.compras_ui),
            ("Produtos", self.produtos_ui),
            ("Débitos", self.debitos_ui),
            ("Dados Bancários", self.dados_bancarios_ui),
            ("Fornecedores", self.fornecedores_ui),
            ("Ajustes", self.ajustes_ui),
        ]

        for i, (nome, widget) in enumerate(botoes):
            btn = QPushButton(nome)
            btn.clicked.connect(lambda _, index=i: self.stack.setCurrentIndex(index))
            menu_layout.addWidget(btn)

        menu_layout.addStretch()


def main():
    app = QApplication(sys.argv)

    # Verifica se há configuração ativa
    try:
        ajustes.get_config()
    except RuntimeError:
        # Se não existir, abre interface ajustes para inserir dados iniciais
        ajustes_ui = AjustesUI()
        ajustes_ui.setWindowModality(Qt.ApplicationModal)
        ajustes_ui.show()
        app.exec()  # espera o usuário finalizar a config

        # Depois de fechar, verifica novamente
        try:
            ajustes.get_config()
        except RuntimeError:
            QMessageBox.critical(None, "Erro", "Nenhuma configuração ativa definida. O programa será encerrado.")
            sys.exit(1)

    # Se tudo ok, abre a janela principal
    janela = MainWindow()
    janela.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
