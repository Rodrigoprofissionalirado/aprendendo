from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QCheckBox
)
from utils_permissoes import requer_permissao
from db_context import get_cursor
from auth_utils import hash_senha

NIVEIS = ["admin", "gerente", "operador", "consulta"]

class UsuariosUI(QWidget):
    def __init__(self, usuario_logado):
        super().__init__()
        self.usuario_logado = usuario_logado
        self.setWindowTitle("Gestão de Usuários")
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        form = QHBoxLayout()
        self.input_nome = QLineEdit()
        self.input_nome.setPlaceholderText("Nome")
        self.input_usuario = QLineEdit()
        self.input_usuario.setPlaceholderText("Login")
        self.input_senha = QLineEdit()
        self.input_senha.setPlaceholderText("Senha")
        self.input_senha.setEchoMode(QLineEdit.Password)
        self.combo_nivel = QComboBox()
        self.combo_nivel.addItems(NIVEIS)
        self.check_ativo = QCheckBox("Ativo")
        self.check_ativo.setChecked(True)

        form.addWidget(QLabel("Nome:"))
        form.addWidget(self.input_nome)
        form.addWidget(QLabel("Usuário:"))
        form.addWidget(self.input_usuario)
        form.addWidget(QLabel("Senha:"))
        form.addWidget(self.input_senha)
        form.addWidget(QLabel("Nível:"))
        form.addWidget(self.combo_nivel)
        form.addWidget(self.check_ativo)

        self.btn_adicionar = QPushButton("Adicionar Usuário")
        self.btn_adicionar.clicked.connect(self.adicionar_usuario)
        form.addWidget(self.btn_adicionar)

        layout.addLayout(form)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Nome", "Usuário", "Nível", "Ativo"])
        layout.addWidget(self.table)

        self.carregar_usuarios()

    @requer_permissao(['admin'])
    def adicionar_usuario(self):
        nome = self.input_nome.text().strip()
        usuario = self.input_usuario.text().strip()
        senha = self.input_senha.text()
        nivel = self.combo_nivel.currentText()
        ativo = 1 if self.check_ativo.isChecked() else 0

        if not nome or not usuario or not senha:
            QMessageBox.warning(self, "Erro", "Preencha todos os campos.")
            return

        with get_cursor(commit=True) as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE username = %s", (usuario,))
            if cursor.fetchone():
                QMessageBox.warning(self, "Erro", "Já existe um usuário com esse login.")
                return

            senha_hash = hash_senha(senha)
            cursor.execute(
                "INSERT INTO usuarios (username, senha_hash, nome, nivel, ativo) VALUES (%s, %s, %s, %s, %s)",
                (usuario, senha_hash, nome, nivel, ativo)
            )
        self.input_nome.clear()
        self.input_usuario.clear()
        self.input_senha.clear()
        self.combo_nivel.setCurrentIndex(0)
        self.check_ativo.setChecked(True)
        self.carregar_usuarios()
        QMessageBox.information(self, "Sucesso", "Usuário cadastrado!")

    @requer_permissao(['admin'])
    def carregar_usuarios(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome, username, nivel, ativo FROM usuarios")
            usuarios = cursor.fetchall()
        self.table.setRowCount(len(usuarios))
        for i, user in enumerate(usuarios):
            self.table.setItem(i, 0, QTableWidgetItem(str(user["id"])))
            self.table.setItem(i, 1, QTableWidgetItem(user["nome"]))
            self.table.setItem(i, 2, QTableWidgetItem(user["username"]))
            self.table.setItem(i, 3, QTableWidgetItem(user["nivel"]))
            self.table.setItem(i, 4, QTableWidgetItem("Sim" if user["ativo"] else "Não"))