from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QLabel, QPushButton, QMessageBox

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login")
        layout = QVBoxLayout()
        self.username = QLineEdit()
        self.username.setPlaceholderText("Usuário")
        self.password = QLineEdit()
        self.password.setPlaceholderText("Senha")
        self.password.setEchoMode(QLineEdit.Password)
        self.btn = QPushButton("Entrar")
        self.btn.clicked.connect(self.login)
        layout.addWidget(QLabel("Usuário:"))
        layout.addWidget(self.username)
        layout.addWidget(QLabel("Senha:"))
        layout.addWidget(self.password)
        layout.addWidget(self.btn)
        self.setLayout(layout)
        self.usuario_autenticado = None

    def login(self):
        usuario = self.username.text().strip()
        senha = self.password.text().strip()
        if not usuario or not senha:
            QMessageBox.warning(self, "Erro", "Preencha usuário e senha!")
            return
        from db_context import get_cursor
        with get_cursor() as cursor:
            cursor.execute("SELECT * FROM usuarios WHERE username = %s AND ativo = 1", (usuario,))
            user = cursor.fetchone()
        if not user:
            QMessageBox.warning(self, "Erro", "Usuário não encontrado ou inativo!")
            return
        from auth_utils import checar_senha
        if not checar_senha(senha, user['senha_hash']):
            QMessageBox.warning(self, "Erro", "Senha incorreta!")
            return
        self.usuario_autenticado = user
        self.accept()