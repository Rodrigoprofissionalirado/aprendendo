import sys
import subprocess
import os
import urllib.request
import ajustes
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QStackedWidget, QHBoxLayout, QMessageBox
)
from PySide6.QtCore import Qt, QLocale
from login_dialog import LoginDialog
from utils_permissoes import requer_permissao

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
from src.compras.compras import ComprasUI
from produtos import ProdutosUI
from debitos import DebitosUI
from dados_bancarios import DadosBancariosUI
from fornecedores import FornecedoresUI
from ajustes import AjustesUI
from movimentacoes import MovimentacoesUI
from usuarios import UsuariosUI  # --- USUÁRIOS ---

class MainWindow(QMainWindow):
    def __init__(self, usuario_logado):
        super().__init__()
        self.setWindowTitle("Sistema de Gestão")
        self.resize(900, 600)
        self.usuario_logado = usuario_logado  # Salva o usuário logado

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
        self.movimentacoes_ui = MovimentacoesUI()
        self.ajustes_ui = AjustesUI()
        # --- USUÁRIOS ---
        if self.usuario_logado['nivel'] == 'admin':
            self.usuarios_ui = UsuariosUI(self.usuario_logado)
        else:
            self.usuarios_ui = None

        # Passa o usuário logado para as UIs que precisam de permissões (exemplo)
        for ui in [self.compras_ui, self.produtos_ui, self.debitos_ui,
                   self.dados_bancarios_ui, self.fornecedores_ui,
                   self.movimentacoes_ui, self.ajustes_ui]:
            ui.usuario_logado = self.usuario_logado
        if self.usuarios_ui:
            self.usuarios_ui.usuario_logado = self.usuario_logado

        self.compras_ui.set_janela_debitos(self.debitos_ui)
        self.compras_ui.set_main_window(self)

        # Adicionando os módulos ao stack
        self.stack.addWidget(self.compras_ui)           # 0
        self.stack.addWidget(self.movimentacoes_ui)     # 1
        self.stack.addWidget(self.produtos_ui)          # 2
        self.stack.addWidget(self.debitos_ui)           # 3
        self.stack.addWidget(self.dados_bancarios_ui)   # 4
        self.stack.addWidget(self.fornecedores_ui)      # 5
        self.stack.addWidget(self.ajustes_ui)           # 6
        if self.usuarios_ui:                            # --- USUÁRIOS ---
            self.stack.addWidget(self.usuarios_ui)      # 7

        # Define permissões para cada módulo
        permissoes_modulos = [
            (["admin", "gerente", "operador", "consulta"]),     # Compras
            (["admin", "gerente", "operador", "consulta"]),     # Movimentações
            (["admin", "gerente", "operador"]),                 # Produtos
            (["admin", "gerente", "operador"]),                 # Débitos
            (["admin", "gerente"]),                             # Dados Bancários
            (["admin", "gerente"]),                             # Fornecedores
            (["admin"]),                                        # Ajustes
        ]
        # --- USUÁRIOS ---
        if self.usuarios_ui:
            permissoes_modulos.append(["admin"])                # Usuários

        botoes = [
            ("Compras", 0),
            ("Movimentações", 1),
            ("Produtos", 2),
            ("Débitos", 3),
            ("Dados Bancários", 4),
            ("Fornecedores", 5),
            ("Ajustes", 6),
        ]
        # --- USUÁRIOS ---
        if self.usuarios_ui:
            botoes.append(("Usuários", 7))

        for i, (nome, idx) in enumerate(botoes):
            btn = QPushButton(nome)

            # Define uma função protegida com o decorador para cada botão
            def make_abrir_modulo(index, niveis):
                @requer_permissao(niveis)
                def abrir_modulo(self):
                    self.stack.setCurrentIndex(index)
                return abrir_modulo

            # Vincula a função ao clique do botão
            btn.clicked.connect(lambda _, f=make_abrir_modulo(idx, permissoes_modulos[i]): f(self))
            menu_layout.addWidget(btn)

        menu_layout.addStretch()

def main():
    app = QApplication(sys.argv)
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))

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

    # ==== TELA DE LOGIN ====
    login = LoginDialog()
    if not login.exec():
        sys.exit(0)  # Usuário cancelou o login

    usuario_logado = login.usuario_autenticado
    if not usuario_logado:
        QMessageBox.critical(None, "Erro", "Falha ao autenticar usuário. O programa será encerrado.")
        sys.exit(1)

    if not usuario_logado.get('ativo', 1):
        QMessageBox.critical(None, "Acesso negado", "Usuário inativo. O programa será encerrado.")
        sys.exit(1)

    janela = MainWindow(usuario_logado)
    janela.showMaximized()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()