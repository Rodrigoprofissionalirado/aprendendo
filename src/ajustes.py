import json
import os
import sys  # Adicionado para reiniciar o app
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QListWidget, QVBoxLayout, QHBoxLayout, QMessageBox, QSpinBox
)

CONFIG_FILE = 'config_bancos.json'
configuracoes = {}
config_ativa = None

def carregar_configs():
    global configuracoes, config_ativa
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            configuracoes = data.get('configuracoes', {})
            config_ativa = data.get('config_ativa')
    else:
        configuracoes = {}
        config_ativa = None

def salvar_configs():
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({'configuracoes': configuracoes, 'config_ativa': config_ativa}, f, indent=4)

def set_config_ativa(nome):
    global config_ativa
    if nome not in configuracoes:
        raise ValueError(f'Configuração {nome} não existe.')
    config_ativa = nome
    salvar_configs()

def adicionar_ou_editar_config(nome, host, user, password, database, port):
    configuracoes[nome] = {
        'host': host,
        'user': user,
        'password': password,
        'database': database,
        'port': port
    }
    salvar_configs()

def remover_config(nome):
    global config_ativa
    if nome in configuracoes:
        configuracoes.pop(nome)
        if config_ativa == nome:
            config_ativa = None
        salvar_configs()

def get_config():
    if config_ativa is None:
        raise RuntimeError("Nenhuma configuração ativa definida.")
    return configuracoes[config_ativa]

def reiniciar_programa():
    """Reinicia o processo Python."""
    python = sys.executable
    os.execl(python, python, *sys.argv)

# Carrega configs ao importar
carregar_configs()

class AjustesUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Configurações de Banco de Dados")
        self.resize(400, 400)

        # Lista das configs
        self.lista_configs = QListWidget()
        self.lista_configs.addItems(configuracoes.keys())
        if config_ativa:
            idx = list(configuracoes.keys()).index(config_ativa)
            self.lista_configs.setCurrentRow(idx)

        self.lista_configs.currentTextChanged.connect(self.on_config_selecionada)

        # Campos para edição/inserção
        self.input_nome = QLineEdit()
        self.input_host = QLineEdit()
        self.input_user = QLineEdit()
        self.input_password = QLineEdit()
        self.input_password.setEchoMode(QLineEdit.Password)
        self.input_database = QLineEdit()
        self.input_port = QSpinBox()
        self.input_port.setRange(1, 65535)
        self.input_port.setValue(3306)

        # Botões
        self.btn_salvar = QPushButton("Salvar")
        self.btn_remover = QPushButton("Remover")
        self.btn_ativar = QPushButton("Ativar")

        self.btn_salvar.clicked.connect(self.salvar_config)
        self.btn_remover.clicked.connect(self.remover_config)
        self.btn_ativar.clicked.connect(self.ativar_config)

        # Layout
        form_layout = QVBoxLayout()
        form_layout.addWidget(QLabel("Nome da Configuração"))
        form_layout.addWidget(self.input_nome)
        form_layout.addWidget(QLabel("Host"))
        form_layout.addWidget(self.input_host)
        form_layout.addWidget(QLabel("Usuário"))
        form_layout.addWidget(self.input_user)
        form_layout.addWidget(QLabel("Senha"))
        form_layout.addWidget(self.input_password)
        form_layout.addWidget(QLabel("Banco de Dados"))
        form_layout.addWidget(self.input_database)
        form_layout.addWidget(QLabel("Porta"))
        form_layout.addWidget(self.input_port)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_salvar)
        btn_layout.addWidget(self.btn_remover)
        btn_layout.addWidget(self.btn_ativar)

        main_layout = QHBoxLayout()
        main_layout.addWidget(self.lista_configs)
        main_layout.addLayout(form_layout)

        layout = QVBoxLayout()
        layout.addLayout(main_layout)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        # Se já existe uma config selecionada, mostra no form
        if self.lista_configs.currentItem():
            self.on_config_selecionada(self.lista_configs.currentItem().text())

    def on_config_selecionada(self, nome):
        if nome in configuracoes:
            c = configuracoes[nome]
            self.input_nome.setText(nome)
            self.input_host.setText(c['host'])
            self.input_user.setText(c['user'])
            self.input_password.setText(c['password'])
            self.input_database.setText(c['database'])
            self.input_port.setValue(c.get('port', 3306))

    def salvar_config(self):
        nome = self.input_nome.text().strip()
        if not nome:
            QMessageBox.warning(self, "Erro", "Informe um nome para a configuração.")
            return
        host = self.input_host.text().strip()
        user = self.input_user.text().strip()
        password = self.input_password.text()
        database = self.input_database.text().strip()
        port = self.input_port.value()
        adicionar_ou_editar_config(nome, host, user, password, database, port)
        if nome not in [self.lista_configs.item(i).text() for i in range(self.lista_configs.count())]:
            self.lista_configs.addItem(nome)
        QMessageBox.information(self, "Sucesso", "Configuração salva com sucesso.")

    def remover_config(self):
        nome = self.input_nome.text().strip()
        if nome and nome in configuracoes:
            remover_config(nome)
            for i in range(self.lista_configs.count()):
                if self.lista_configs.item(i).text() == nome:
                    self.lista_configs.takeItem(i)
                    break
            QMessageBox.information(self, "Sucesso", "Configuração removida.")
        else:
            QMessageBox.warning(self, "Erro", "Selecione uma configuração válida para remover.")

    def ativar_config(self):
        nome = self.input_nome.text().strip()
        global config_ativa
        if nome and nome in configuracoes:
            mudou = (config_ativa != nome)
            set_config_ativa(nome)
            QMessageBox.information(self, "Sucesso", f"Configuração '{nome}' ativada.")
            if mudou:
                QMessageBox.information(self, "Reiniciando", "O sistema será reiniciado para aplicar a nova configuração.")
                self.close()  # Fecha janela antes de reiniciar
                reiniciar_programa()
        else:
            QMessageBox.warning(self, "Erro", "Selecione uma configuração válida para ativar.")