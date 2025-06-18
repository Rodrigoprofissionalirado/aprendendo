# Requisitos: pip install PySide6 mysql-connector-python

import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QHBoxLayout, QGridLayout
)
from PySide6.QtCore import Qt
from db_context import get_cursor

class ProdutosUI(QWidget):
    def __init__(self):
        super().__init__()
        self.dado_selecionado = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Cadastro de Produtos')
        layout_principal = QVBoxLayout()

        form_layout = QGridLayout()

        self.input_nome = QLineEdit()
        self.input_preco = QLineEdit()

        form_layout.addWidget(QLabel('Nome'), 0, 0)
        form_layout.addWidget(self.input_nome, 0, 1)
        form_layout.addWidget(QLabel('Preço Base'), 1, 0)
        form_layout.addWidget(self.input_preco, 1, 1)

        btn_layout = QHBoxLayout()
        self.btn_adicionar = QPushButton('Adicionar')
        self.btn_adicionar.clicked.connect(self.adicionar)
        self.btn_atualizar = QPushButton('Atualizar')
        self.btn_atualizar.clicked.connect(self.atualizar)
        self.btn_excluir = QPushButton('Excluir')
        self.btn_excluir.clicked.connect(self.excluir)
        self.btn_limpar = QPushButton('Limpar')
        self.btn_limpar.clicked.connect(self.limpar)

        btn_layout.addWidget(self.btn_adicionar)
        btn_layout.addWidget(self.btn_atualizar)
        btn_layout.addWidget(self.btn_excluir)
        btn_layout.addWidget(self.btn_limpar)

        self.tabela = QTableWidget()
        self.tabela.setColumnCount(3)
        self.tabela.setHorizontalHeaderLabels(['ID', 'Nome', 'Preço Base'])
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.cellClicked.connect(self.carregar_dado_selecionado)

        layout_principal.addLayout(form_layout)
        layout_principal.addLayout(btn_layout)
        layout_principal.addWidget(self.tabela)

        self.setLayout(layout_principal)

        self.carregar_tabela()

    def carregar_tabela(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT * FROM produtos")
            dados = cursor.fetchall()

        self.tabela.setRowCount(len(dados))
        for i, dado in enumerate(dados):
            self.tabela.setItem(i, 0, QTableWidgetItem(str(dado['id'])))
            self.tabela.setItem(i, 1, QTableWidgetItem(dado['nome']))
            self.tabela.setItem(i, 2, QTableWidgetItem(str(dado['preco_base'])))

    def adicionar(self):
        nome = self.input_nome.text()
        preco = self.input_preco.text()

        if nome and preco:
            try:
                preco = float(preco)
                with get_cursor(commit=True) as cursor:
                    cursor.execute(
                        "INSERT INTO produtos (nome, preco_base) VALUES (%s, %s)",
                        (nome, preco)
                    )
                self.carregar_tabela()
                self.limpar()
            except ValueError:
                QMessageBox.warning(self, 'Erro', 'Preço inválido.')
        else:
            QMessageBox.warning(self, 'Campos obrigatórios', 'Preencha todos os campos.')

    def carregar_dado_selecionado(self, row, column):
        self.dado_selecionado = int(self.tabela.item(row, 0).text())
        self.input_nome.setText(self.tabela.item(row, 1).text())
        self.input_preco.setText(self.tabela.item(row, 2).text())

    def atualizar(self):
        if self.dado_selecionado:
            nome = self.input_nome.text()
            preco = self.input_preco.text()
            try:
                preco = float(preco)
                with get_cursor(commit=True) as cursor:
                    cursor.execute(
                        "UPDATE produtos SET nome=%s, preco_base=%s WHERE id=%s",
                        (nome, preco, self.dado_selecionado)
                    )
                self.carregar_tabela()
                self.limpar()
            except ValueError:
                QMessageBox.warning(self, 'Erro', 'Preço inválido.')

    def excluir(self):
        if self.dado_selecionado:
            with get_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM produtos WHERE id = %s", (self.dado_selecionado,))
            self.carregar_tabela()
            self.limpar()

    def limpar(self):
        self.dado_selecionado = None
        self.input_nome.clear()
        self.input_preco.clear()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    janela = ProdutosUI()
    janela.resize(600, 400)
    janela.show()
    sys.exit(app.exec())
