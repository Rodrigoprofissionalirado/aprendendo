import sys
import mysql.connector
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView
)
from PySide6.QtCore import Qt, QDate

class DB:
    def __init__(self):
        self.conn = mysql.connector.connect(
            host='rodrigopirata.duckdns.org',
            port=3306,
            user='rodrigo',
            password='Ro220199@mariadb',
            database='Trabalho'
        )
        self.cursor = self.conn.cursor(dictionary=True)

    # ----- CATEGORIAS -----
    def listar_categorias(self):
        self.cursor.execute("SELECT * FROM categorias_fornecedor")
        return self.cursor.fetchall()

    def adicionar_categoria(self, nome):
        self.cursor.execute(
            "INSERT INTO categorias_fornecedor (nome) VALUES (%s)", (nome,)
        )
        self.conn.commit()

    def atualizar_categoria(self, categoria_id, nome):
        self.cursor.execute(
            "UPDATE categorias_fornecedor SET nome=%s WHERE id=%s", (nome, categoria_id)
        )
        self.conn.commit()

    def excluir_categoria(self, categoria_id):
        self.cursor.execute("DELETE FROM categorias_fornecedor WHERE id = %s", (categoria_id,))
        self.conn.commit()

    # ----- AJUSTES -----
    def listar_produtos_ajustes(self, categoria_id):
        self.cursor.execute("""
            SELECT p.id, p.nome,
                   COALESCE(a.ajuste_fixo, 0) AS ajuste_fixo
            FROM produtos p
            LEFT JOIN ajustes_fixos_produto_categoria a
              ON p.id = a.produto_id AND a.categoria_id = %s
            ORDER BY p.nome
        """, (categoria_id,))
        return self.cursor.fetchall()

    def salvar_ajuste(self, categoria_id, produto_id, ajuste_fixo):
        # Tenta atualizar primeiro
        self.cursor.execute("""
            INSERT INTO ajustes_fixos_produto_categoria (categoria_id, produto_id, ajuste_fixo)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE ajuste_fixo = VALUES(ajuste_fixo)
        """, (categoria_id, produto_id, ajuste_fixo))
        self.conn.commit()


class CategoriasUI(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DB()
        self.categoria_selecionada = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Cadastro de Categorias de Cliente')
        layout_principal = QVBoxLayout()

        # ----- FORM CATEGORIA -----
        form_layout = QGridLayout()
        self.input_nome = QLineEdit()
        form_layout.addWidget(QLabel('Nome da Categoria'), 0, 0)
        form_layout.addWidget(self.input_nome, 0, 1)

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

        # ----- TABELA CATEGORIAS -----
        self.tabela_categorias = QTableWidget()
        self.tabela_categorias.setColumnCount(2)
        self.tabela_categorias.setHorizontalHeaderLabels(['ID', 'Nome'])
        self.tabela_categorias.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_categorias.cellClicked.connect(self.carregar_categoria)

        # ----- TABELA AJUSTES -----
        self.tabela_ajustes = QTableWidget()
        self.tabela_ajustes.setColumnCount(3)
        self.tabela_ajustes.setHorizontalHeaderLabels(['ID Produto', 'Nome Produto', 'Ajuste Fixo'])
        self.tabela_ajustes.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.btn_salvar_ajustes = QPushButton('Salvar Ajustes')
        self.btn_salvar_ajustes.clicked.connect(self.salvar_ajustes)
        self.btn_salvar_ajustes.setEnabled(False)

        # Layout final
        layout_principal.addLayout(form_layout)
        layout_principal.addLayout(btn_layout)
        layout_principal.addWidget(QLabel("Categorias"))
        layout_principal.addWidget(self.tabela_categorias)
        layout_principal.addWidget(QLabel("Ajustes de Preço por Produto"))
        layout_principal.addWidget(self.tabela_ajustes)
        layout_principal.addWidget(self.btn_salvar_ajustes)

        self.setLayout(layout_principal)
        self.carregar_tabela()

    def carregar_tabela(self):
        dados = self.db.listar_categorias()
        self.tabela_categorias.setRowCount(len(dados))
        for i, dado in enumerate(dados):
            self.tabela_categorias.setItem(i, 0, QTableWidgetItem(str(dado['id'])))
            self.tabela_categorias.setItem(i, 1, QTableWidgetItem(dado['nome']))

    def adicionar(self):
        nome = self.input_nome.text()
        if nome:
            self.db.adicionar_categoria(nome)
            self.carregar_tabela()
            self.limpar()
        else:
            QMessageBox.warning(self, 'Erro', 'Informe o nome da categoria.')

    def carregar_categoria(self, row, column):
        self.categoria_selecionada = int(self.tabela_categorias.item(row, 0).text())
        self.input_nome.setText(self.tabela_categorias.item(row, 1).text())
        self.carregar_ajustes()
        self.btn_salvar_ajustes.setEnabled(True)

    def atualizar(self):
        if self.categoria_selecionada:
            nome = self.input_nome.text()
            self.db.atualizar_categoria(self.categoria_selecionada, nome)
            self.carregar_tabela()
            self.limpar()

    def excluir(self):
        if self.categoria_selecionada:
            self.db.excluir_categoria(self.categoria_selecionada)
            self.carregar_tabela()
            self.limpar()
            self.tabela_ajustes.setRowCount(0)
            self.btn_salvar_ajustes.setEnabled(False)

    def limpar(self):
        self.categoria_selecionada = None
        self.input_nome.clear()
        self.tabela_categorias.clearSelection()
        self.tabela_ajustes.setRowCount(0)
        self.btn_salvar_ajustes.setEnabled(False)

    def carregar_ajustes(self):
        dados = self.db.listar_produtos_ajustes(self.categoria_selecionada)
        self.tabela_ajustes.setRowCount(len(dados))
        for i, dado in enumerate(dados):
            self.tabela_ajustes.setItem(i, 0, QTableWidgetItem(str(dado['id'])))
            self.tabela_ajustes.setItem(i, 1, QTableWidgetItem(dado['nome']))
            item = QTableWidgetItem(str(dado['ajuste_fixo']))
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.tabela_ajustes.setItem(i, 2, item)

    def salvar_ajustes(self):
        for i in range(self.tabela_ajustes.rowCount()):
            produto_id = int(self.tabela_ajustes.item(i, 0).text())
            try:
                ajuste = float(self.tabela_ajustes.item(i, 2).text())
                self.db.salvar_ajuste(self.categoria_selecionada, produto_id, ajuste)
            except ValueError:
                QMessageBox.warning(self, 'Erro', f'Ajuste inválido na linha {i + 1}.')
        QMessageBox.information(self, 'Sucesso', 'Ajustes salvos com sucesso.')

if __name__ == '__main__':
    from PySide6.QtCore import Qt
    app = QApplication(sys.argv)
    janela = App()
    janela.resize(800, 600)
    janela.show()
    sys.exit(app.exec())
