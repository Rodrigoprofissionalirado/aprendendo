import sys
import mysql.connector
from contextlib import contextmanager
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QComboBox, QGridLayout
)
from db_context import get_cursor
from PySide6.QtCore import Qt

class DB:
    def listar_dados_bancarios(self):
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT db.*, f.nome as fornecedor_nome, f.fornecedores_numerobalanca
                FROM dados_bancarios_fornecedor db
                LEFT JOIN fornecedores f ON db.fornecedor_id = f.id
            """)
            return cursor.fetchall()

    def listar_fornecedores(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome, fornecedores_numerobalanca FROM fornecedores")
            return cursor.fetchall()

    def limpar_padrao_anterior(self, fornecedor_id):
        with get_cursor(commit=True) as cursor:
            cursor.execute("UPDATE dados_bancarios_fornecedor SET padrao = 0 WHERE fornecedor_id = %s", (fornecedor_id,))


    def adicionar_dado_bancario(self, fornecedor_id, banco, cpf_cnpj, agencia, conta, padrao, nome_conta):
        with get_cursor(commit=True) as cursor:
            if padrao == 1:
                cursor.execute("UPDATE dados_bancarios_fornecedor SET padrao = 0 WHERE fornecedor_id = %s", (fornecedor_id,))
            cursor.execute(
                """
                INSERT INTO dados_bancarios_fornecedor 
                (fornecedor_id, banco, CPFouCNPJ, agencia, conta, padrao, nome_conta)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (fornecedor_id, banco, cpf_cnpj, agencia, conta, padrao, nome_conta)
            )

    def excluir_dado_bancario(self, dado_id):
        with get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM dados_bancarios_fornecedor WHERE id = %s", (dado_id,))

    def atualizar_dado_bancario(self, dado_id, fornecedor_id, banco, cpf_cnpj, agencia, conta, padrao, nome_conta):
        with get_cursor(commit=True) as cursor:
            if padrao == 1:
                cursor.execute("UPDATE dados_bancarios_fornecedor SET padrao = 0 WHERE fornecedor_id = %s", (fornecedor_id,))
            cursor.execute(
                """
                UPDATE dados_bancarios_fornecedor 
                SET fornecedor_id=%s, nome_conta=%s, banco=%s, CPFouCNPJ=%s, agencia=%s, conta=%s, padrao=%s
                WHERE id=%s
                """,
                (fornecedor_id, nome_conta, banco, cpf_cnpj, agencia, conta, padrao, dado_id)
            )

class DadosBancariosUI(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DB()
        self.silenciar_sync = False  # flag para evitar loop de sinais
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Dados Bancários dos Fornecedores')
        layout_principal = QVBoxLayout()

        # Filtros
        filtro_layout = QHBoxLayout()
        self.input_filtro_nome = QLineEdit()
        self.input_filtro_nome.setPlaceholderText("Filtrar por nome ou número balança")
        self.btn_aplicar_filtro = QPushButton("Aplicar Filtro")
        self.btn_limpar_filtro = QPushButton("Limpar Filtro")
        self.btn_aplicar_filtro.clicked.connect(self.carregar_tabela)
        self.btn_limpar_filtro.clicked.connect(self.limpar_filtro)
        filtro_layout.addWidget(QLabel("Filtro:"))
        filtro_layout.addWidget(self.input_filtro_nome)
        filtro_layout.addWidget(self.btn_aplicar_filtro)
        filtro_layout.addWidget(self.btn_limpar_filtro)

        form_layout = QGridLayout()

        # Combo do nome do fornecedor
        self.combo_fornecedor_nome = QComboBox()
        form_layout.addWidget(QLabel('Fornecedor'), 0, 0)
        form_layout.addWidget(self.combo_fornecedor_nome, 0, 1)

        # Campo texto para número da balança (digitável)
        self.input_num_balanca = QLineEdit()
        form_layout.addWidget(QLabel('Nº Balança'), 1, 0)
        form_layout.addWidget(self.input_num_balanca, 1, 1)

        self.input_nome_conta = QLineEdit()
        self.input_banco = QLineEdit()
        self.input_cpf_cnpj = QLineEdit()
        self.input_agencia = QLineEdit()
        self.input_conta = QLineEdit()
        self.input_padrao = QComboBox()
        self.input_padrao.addItems(['Não', 'Sim'])

        form_layout.addWidget(QLabel('Nome Conta'), 2, 0)
        form_layout.addWidget(self.input_nome_conta, 2, 1)
        form_layout.addWidget(QLabel('Banco'), 3, 0)
        form_layout.addWidget(self.input_banco, 3, 1)
        form_layout.addWidget(QLabel('CPF ou CNPJ'), 4, 0)
        form_layout.addWidget(self.input_cpf_cnpj, 4, 1)
        form_layout.addWidget(QLabel('Agência'), 5, 0)
        form_layout.addWidget(self.input_agencia, 5, 1)
        form_layout.addWidget(QLabel('Conta'), 6, 0)
        form_layout.addWidget(self.input_conta, 6, 1)
        form_layout.addWidget(QLabel('Padrão'), 7, 0)
        form_layout.addWidget(self.input_padrao, 7, 1)

        self.btn_adicionar = QPushButton('Adicionar')
        self.btn_adicionar.clicked.connect(self.adicionar)

        self.btn_atualizar = QPushButton('Atualizar')
        self.btn_atualizar.clicked.connect(self.atualizar)

        self.btn_excluir = QPushButton('Excluir')
        self.btn_excluir.clicked.connect(self.excluir)

        self.btn_limpar = QPushButton('Limpar')
        self.btn_limpar.clicked.connect(self.limpar)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_adicionar)
        btn_layout.addWidget(self.btn_atualizar)
        btn_layout.addWidget(self.btn_excluir)
        btn_layout.addWidget(self.btn_limpar)

        self.tabela = QTableWidget()
        self.tabela.setColumnCount(9)
        self.tabela.setHorizontalHeaderLabels([
            'ID', 'Fornecedor', 'Nº Balança', 'Nome Conta', 'Banco', 'CPF/CNPJ', 'Agência', 'Conta', 'Padrão'
        ])
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.cellClicked.connect(self.carregar_dado_selecionado)

        layout_principal.addLayout(filtro_layout)
        layout_principal.addLayout(form_layout)
        layout_principal.addLayout(btn_layout)
        layout_principal.addWidget(self.tabela)

        self.setLayout(layout_principal)

        # Carregar fornecedores e dados
        self.carregar_fornecedores()
        self.carregar_tabela()
        self.dado_selecionado = None

        # Conectar sinais para sincronização
        self.combo_fornecedor_nome.currentIndexChanged.connect(self.combo_fornecedor_alterado)
        self.input_num_balanca.textEdited.connect(self.num_balanca_editado)

    def carregar_fornecedores(self):
        self.combo_fornecedor_nome.clear()
        self.fornecedores = self.db.listar_fornecedores()
        for f in self.fornecedores:
            self.combo_fornecedor_nome.addItem(f"{f['nome']}", f["id"])

    def carregar_tabela(self):
        filtro = self.input_filtro_nome.text().lower()
        dados = self.db.listar_dados_bancarios()
        if filtro:
            dados = [d for d in dados if filtro in d['fornecedor_nome'].lower() or filtro in str(d['fornecedores_numerobalanca'])]

        self.tabela.setRowCount(len(dados))
        for i, dado in enumerate(dados):
            self.tabela.setItem(i, 0, QTableWidgetItem(str(dado['id'])))
            self.tabela.setItem(i, 1, QTableWidgetItem(dado['fornecedor_nome']))
            self.tabela.setItem(i, 2, QTableWidgetItem(str(dado['fornecedores_numerobalanca'])))
            self.tabela.setItem(i, 3, QTableWidgetItem(dado.get('nome_conta', '')))  # nome_conta aqui
            self.tabela.setItem(i, 4, QTableWidgetItem(dado['banco']))
            self.tabela.setItem(i, 5, QTableWidgetItem(dado['CPFouCNPJ']))
            self.tabela.setItem(i, 6, QTableWidgetItem(dado['agencia']))
            self.tabela.setItem(i, 7, QTableWidgetItem(dado['conta']))
            self.tabela.setItem(i, 8, QTableWidgetItem('Sim' if dado['padrao'] else 'Não'))

    def limpar_filtro(self):
        self.input_filtro_nome.clear()
        self.carregar_tabela()

    def adicionar(self):
        fornecedor_id = self.combo_fornecedor_nome.currentData()
        nome_conta = self.input_nome_conta.text()
        banco = self.input_banco.text()
        cpf_cnpj = self.input_cpf_cnpj.text()
        agencia = self.input_agencia.text()
        conta = self.input_conta.text()
        padrao = 1 if self.input_padrao.currentText() == 'Sim' else 0

        if nome_conta and banco and cpf_cnpj and agencia and conta and fornecedor_id is not None:
            self.db.adicionar_dado_bancario(fornecedor_id, banco, cpf_cnpj, agencia, conta, padrao, nome_conta)
            self.carregar_tabela()
            self.limpar()
        else:
            QMessageBox.warning(self, 'Campos obrigatórios', 'Preencha todos os campos corretamente.')

    def carregar_dado_selecionado(self, row, column):
        self.dado_selecionado = int(self.tabela.item(row, 0).text())
        nome_forn = self.tabela.item(row, 1).text()
        num_balanca = self.tabela.item(row, 2).text()

        # Atualiza combo e campo num balança sem disparar sincronização
        self.silenciar_sync = True
        # Seleciona combo pelo nome exato
        for i in range(self.combo_fornecedor_nome.count()):
            if self.combo_fornecedor_nome.itemText(i) == nome_forn:
                self.combo_fornecedor_nome.setCurrentIndex(i)
                break
        else:
            self.combo_fornecedor_nome.setCurrentIndex(-1)

        self.input_num_balanca.setText(num_balanca)

        self.input_nome_conta.setText(self.tabela.item(row, 3).text())
        self.input_banco.setText(self.tabela.item(row, 4).text())
        self.input_cpf_cnpj.setText(self.tabela.item(row, 5).text())
        self.input_agencia.setText(self.tabela.item(row, 6).text())
        self.input_conta.setText(self.tabela.item(row, 7).text())
        self.input_padrao.setCurrentText(self.tabela.item(row, 8).text())
        self.silenciar_sync = False

    def atualizar(self):
        if self.dado_selecionado:
            fornecedor_id = self.combo_fornecedor_nome.currentData()
            nome_conta = self.input_nome_conta.text()
            banco = self.input_banco.text()
            cpf_cnpj = self.input_cpf_cnpj.text()
            agencia = self.input_agencia.text()
            conta = self.input_conta.text()
            padrao = 1 if self.input_padrao.currentText() == 'Sim' else 0

            if fornecedor_id is None:
                QMessageBox.warning(self, 'Erro', 'Fornecedor inválido.')
                return

            self.db.atualizar_dado_bancario(self.dado_selecionado, fornecedor_id, banco, cpf_cnpj, agencia, conta, padrao, nome_conta)
            self.carregar_tabela()
            self.limpar()

    def excluir(self):
        if self.dado_selecionado:
            self.db.excluir_dado_bancario(self.dado_selecionado)
            self.carregar_tabela()
            self.limpar()

    def limpar(self):
        self.dado_selecionado = None
        self.silenciar_sync = True
        self.combo_fornecedor_nome.setCurrentIndex(-1)
        self.input_num_balanca.clear()
        self.input_nome_conta.clear()
        self.input_banco.clear()
        self.input_cpf_cnpj.clear()
        self.input_agencia.clear()
        self.input_conta.clear()
        self.input_padrao.setCurrentIndex(0)
        self.tabela.clearSelection()
        self.silenciar_sync = False

    # Sincronização bidirecional

    def combo_fornecedor_alterado(self, index):
        if self.silenciar_sync:
            return
        self.silenciar_sync = True
        if 0 <= index < len(self.fornecedores):
            numero = str(self.fornecedores[index]['fornecedores_numerobalanca'])
            self.input_num_balanca.setText(numero)
        else:
            self.input_num_balanca.setText('')
        self.silenciar_sync = False

    def num_balanca_editado(self, texto):
        if self.silenciar_sync:
            return
        self.silenciar_sync = True
        texto = texto.strip()
        indice_encontrado = -1
        for i, f in enumerate(self.fornecedores):
            if str(f['fornecedores_numerobalanca']) == texto:
                indice_encontrado = i
                break
        if indice_encontrado != -1:
            self.combo_fornecedor_nome.setCurrentIndex(indice_encontrado)
        else:
            self.combo_fornecedor_nome.setCurrentIndex(-1)
        self.silenciar_sync = False

if __name__ == '__main__':
    app = QApplication(sys.argv)
    janela = DadosBancariosUI()
    janela.resize(1000, 600)
    janela.show()
    sys.exit(app.exec())
