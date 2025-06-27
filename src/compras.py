import sys
import mysql.connector
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QComboBox, QDateEdit, QLineEdit,
    QSpinBox, QTableWidget, QTableWidgetItem, QMessageBox, QTabWidget,
    QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, QTimer, QDate, QLocale
from decimal import Decimal, ROUND_HALF_UP
from db_context import get_cursor
from status_delegate_combo import StatusComboDelegate
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import black, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os, platform

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

STATUS_LIST = [
    "Criada", "Emitindo nota", "Efetuando pagamento", "Finalizada", "Concluída"
]

class ComprasUI(QWidget):
    def __init__(self):
        super().__init__()
        self.STATUS_COLORS = {
            "Criada": "#e0e0e0",
            "Emitindo nota": "#fff2cc",
            "Efetuando pagamento": "#ffe599",
            "Finalizada": "#b6d7a8",
            "Concluída": "#93c47d"
        }
        self.itens_compra = []
        self.item_edit_index = None
        self.compra_edit_id = None
        self.locale = QLocale(QLocale.Portuguese, QLocale.Brazil)
        self.init_ui()
        self.carregar_fornecedores()
        self.carregar_produtos()

    # ---- Métodos DB ----

    def listar_fornecedores(self):
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT id, nome FROM fornecedores ORDER BY nome
            """)
            return cursor.fetchall()

    def listar_contas_do_fornecedor(self, fornecedor_id):
        if not fornecedor_id:
            return []
        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT id, banco, agencia, conta, nome_conta, padrao
                           FROM dados_bancarios_fornecedor
                           WHERE fornecedor_id = %s
                           ORDER BY padrao DESC, nome_conta, banco
                           """, (fornecedor_id,))
            rows = cursor.fetchall()
            return [
                {
                    'id': row['id'],
                    'apelido': row['nome_conta'] or row['banco'],
                    'banco': row['banco'],
                    'agencia': row['agencia'],
                    'conta': row['conta'],
                    'padrao': row['padrao'],
                }
                for row in rows
            ]

    def listar_produtos(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome, preco_base FROM produtos ORDER BY nome")
            return cursor.fetchall()

    def obter_produto(self, produto_id):
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome, preco_base FROM produtos WHERE id = %s", (produto_id,))
            return cursor.fetchone()

    def listar_compras(self, status=None, status_not=None, data_de=None, data_ate=None, fornecedor_id=None):
        query = """
            SELECT c.id, c.data_compra AS data, c.valor_abatimento, c.total, f.nome AS fornecedor_nome, c.status
            FROM compras c
            JOIN fornecedores f ON c.fornecedor_id = f.id
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND c.status = %s"
            params.append(status)
        if status_not:
            query += " AND c.status != %s"
            params.append(status_not)
        if data_de:
            query += " AND c.data_compra >= %s"
            params.append(data_de)
        if data_ate:
            query += " AND c.data_compra <= %s"
            params.append(data_ate)
        if fornecedor_id:
            query += " AND f.id = %s"
            params.append(fornecedor_id)
        query += " ORDER BY c.data_compra DESC"

        with get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def adicionar_compra(self, fornecedor_id, data_compra, valor_abatimento, itens_compra, status):
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO compras (fornecedor_id, data_compra, valor_abatimento, status) VALUES (%s, %s, %s, %s)",
                (fornecedor_id, data_compra, valor_abatimento, status)
            )
            compra_id = cursor.lastrowid

            for item in itens_compra:
                cursor.execute(
                    "INSERT INTO itens_compra (compra_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)",
                    (compra_id, item['produto_id'], item['quantidade'], item['preco'])
                )

            cursor.execute("""
                           UPDATE compras
                           SET total = (SELECT SUM(quantidade * preco_unitario)
                                        FROM itens_compra
                                        WHERE compra_id = %s)
                           WHERE id = %s
                           """, (compra_id, compra_id))

            # ADICIONE ESTE BLOCO:
            if valor_abatimento and valor_abatimento > 0:
                cursor.execute(
                    """
                    INSERT INTO debitos_fornecedores (fornecedor_id, compra_id, data_lancamento, descricao, valor, tipo)
                    VALUES (%s, %s, %s, %s, %s, 'abatimento')
                    """,
                    (fornecedor_id, compra_id, data_compra, 'Abatimento em compra', abs(valor_abatimento))
                )

        return compra_id

    def atualizar_compra(self, compra_id, fornecedor_id, data_compra, valor_abatimento, itens_compra, status):
        with get_cursor(commit=True) as cursor:
            # Atualiza a compra e os itens
            cursor.execute("""
                           UPDATE compras
                           SET fornecedor_id=%s,
                               data_compra=%s,
                               valor_abatimento=%s,
                               status=%s
                           WHERE id = %s
                           """, (fornecedor_id, data_compra, valor_abatimento, status, compra_id))

            cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))

            for item in itens_compra:
                cursor.execute(
                    "INSERT INTO itens_compra (compra_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)",
                    (compra_id, item['produto_id'], item['quantidade'], item['preco'])
                )

            cursor.execute("""
                           UPDATE compras
                           SET total = (SELECT SUM(quantidade * preco_unitario)
                                        FROM itens_compra
                                        WHERE compra_id = %s)
                           WHERE id = %s
                           """, (compra_id, compra_id))

    def atualizar_campo_texto_copiavel(self):
        compra_id = self.obter_compra_id_selecionado()
        if not compra_id:
            self.campo_texto_copiavel.setText("")
            return
        with get_cursor() as cursor:
            # Primeiro tenta pegar a conta personalizada (da compra)
            cursor.execute("""
                           SELECT c.total, dbf.banco, dbf.agencia, dbf.conta, dbf.nome_conta, dbf.CPFouCNPJ
                           FROM compras c
                                    LEFT JOIN dados_bancarios_fornecedor dbf ON c.dados_bancarios_id = dbf.id
                           WHERE c.id = %s
                           """, (compra_id,))
            row = cursor.fetchone()
            if row and row['banco']:
                valor = f"{row['total']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                tipo_doc = "CNPJ" if row['CPFouCNPJ'] and len(row['CPFouCNPJ']) > 14 else "CPF"
                texto = (
                    f"{row['nome_conta'] or row['banco']} - R$ {valor}\n"
                    f"{row['banco']} (Ag: {row['agencia']}, Conta: {row['conta']})\n"
                    f"{tipo_doc}: {row['CPFouCNPJ']}"
                )
                self.campo_texto_copiavel.setText(texto)
            else:
                # Se não houver conta personalizada, busca a padrão do fornecedor com o mesmo formato
                cursor.execute("""
                               SELECT dbf.banco, dbf.agencia, dbf.conta, dbf.nome_conta, dbf.CPFouCNPJ, c.total
                               FROM compras c
                                        JOIN dados_bancarios_fornecedor dbf
                                             ON dbf.fornecedor_id = c.fornecedor_id AND dbf.padrao = 1
                               WHERE c.id = %s LIMIT 1
                               """, (compra_id,))
                row = cursor.fetchone()
                if row:
                    valor = f"{row['total']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    tipo_doc = "CNPJ" if row['CPFouCNPJ'] and len(row['CPFouCNPJ']) > 14 else "CPF"
                    texto = (
                        f"{row['nome_conta'] or row['banco']} - R$ {valor}\n"
                        f"{row['banco']} (Ag: {row['agencia']}, Conta: {row['conta']})\n"
                        f"{tipo_doc}: {row['CPFouCNPJ']}"
                    )
                    self.campo_texto_copiavel.setText(texto)
                else:
                    self.campo_texto_copiavel.setText("")

    def atualizar_status_compra(self, compra_id, novo_status):
        with get_cursor(commit=True) as cursor:
            cursor.execute("UPDATE compras SET status = %s WHERE id = %s", (novo_status, compra_id))

    def listar_itens_compra(self, compra_id):
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT p.nome AS produto_nome, i.produto_id, i.quantidade, i.preco_unitario, (i.quantidade * i.preco_unitario) AS total
                FROM itens_compra i
                JOIN produtos p ON i.produto_id = p.id
                WHERE i.compra_id = %s
            """, (compra_id,))
            return cursor.fetchall()

    def obter_compra_id_selecionado(self, tabela=None):
        if tabela is None:
            tabela = self.tabela_compras_aberto
        linha = tabela.currentRow()
        if linha < 0:
            return None
        item = tabela.item(linha, 0)
        return int(item.text()) if item else None

    def obter_fornecedor_id_da_compra(self, compra_id):
        if not compra_id:
            return None
        with get_cursor() as cursor:
            cursor.execute("SELECT fornecedor_id FROM compras WHERE id = %s", (compra_id,))
            row = cursor.fetchone()
            if row:
                # Se row for dict: row['fornecedor_id'], se for tupla: row[0]
                return row['fornecedor_id']
        return None

    def obter_detalhes_compra(self, compra_id):
        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT f.id   AS fornecedor_id,
                                  f.nome AS fornecedor,
                                  f.fornecedores_numerobalanca,
                                  c.data_compra,
                                  c.valor_abatimento
                           FROM compras c
                                    JOIN fornecedores f ON c.fornecedor_id = f.id
                           WHERE c.id = %s
                           """, (compra_id,))
            compra = cursor.fetchone()

            cursor.execute("""
                           SELECT p.nome                            AS produto_nome,
                                  i.quantidade,
                                  i.preco_unitario,
                                  (i.quantidade * i.preco_unitario) AS total
                           FROM itens_compra i
                                    JOIN produtos p ON i.produto_id = p.id
                           WHERE i.compra_id = %s
                           """, (compra_id,))
            itens = cursor.fetchall()
        return compra, itens

    # ---- Categoria Fallback ("Padrão") ----

    def obter_id_categoria_padrao(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT id FROM categorias_fornecedor_por_fornecedor WHERE nome = %s LIMIT 1", ('Padrão',))
            cat = cursor.fetchone()
            return cat['id'] if cat else None

    def obter_categorias_do_fornecedor(self, fornecedor_id):
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT id, nome FROM categorias_fornecedor_por_fornecedor WHERE fornecedor_id = %s ORDER BY nome",
                (fornecedor_id,))
            cats = cursor.fetchall()
            if not cats:
                cursor.execute("SELECT id, nome FROM categorias_fornecedor_por_fornecedor WHERE nome = %s LIMIT 1", ('Padrão',))
                cat_padrao = cursor.fetchone()
                if cat_padrao:
                    cats = [cat_padrao]
            return cats

    # ---- UI e lógica ----

    def init_ui(self):
        layout_principal = QVBoxLayout()

        # --------------------- Filtros (compartilhados entre abas) ---------------------
        layout_filtros = QHBoxLayout()

        self.filtro_numero_balanca = QLineEdit()
        self.filtro_numero_balanca.setPlaceholderText("Número da balança")
        layout_filtros.addWidget(QLabel("Número da Balança:"))
        layout_filtros.addWidget(self.filtro_numero_balanca)

        self.filtro_combo_fornecedor = QComboBox()
        self.filtro_combo_fornecedor.addItem("Todos os Fornecedores", None)
        for f in self.listar_fornecedores():
            self.filtro_combo_fornecedor.addItem(f"{f['nome']} (ID {f['id']})", f['id'])
        layout_filtros.addWidget(QLabel("Fornecedor:"))
        layout_filtros.addWidget(self.filtro_combo_fornecedor)

        self.filtro_combo_status = QComboBox()
        self.filtro_combo_status.addItem("Todos", None)
        for s in STATUS_LIST:
            self.filtro_combo_status.addItem(s, s)
        layout_filtros.addWidget(QLabel("Status:"))
        layout_filtros.addWidget(self.filtro_combo_status)

        self.filtro_data_de = QDateEdit()
        self.filtro_data_de.setCalendarPopup(True)
        self.filtro_data_de.setDate(QDate.currentDate().addMonths(-1))
        layout_filtros.addWidget(QLabel("De:"))
        layout_filtros.addWidget(self.filtro_data_de)

        self.filtro_data_ate = QDateEdit()
        self.filtro_data_ate.setCalendarPopup(True)
        self.filtro_data_ate.setDate(QDate.currentDate())
        layout_filtros.addWidget(QLabel("Até:"))
        layout_filtros.addWidget(self.filtro_data_ate)

        btn_aplicar_filtro = QPushButton("Aplicar Filtro")
        btn_aplicar_filtro.clicked.connect(self.atualizar_tabelas)
        layout_filtros.addWidget(btn_aplicar_filtro)

        btn_limpar_filtro = QPushButton("Limpar Filtro")
        btn_limpar_filtro.clicked.connect(self.limpar_filtro_compras)
        layout_filtros.addWidget(btn_limpar_filtro)

        layout_principal.addLayout(layout_filtros)
        # ---------------------- Fim dos filtros -----------------

        self.tabs = QTabWidget()
        layout_principal.addWidget(self.tabs)

        # ===================== TAB EM ABERTO =====================
        self.tab_em_aberto = QWidget()
        self.tab_concluidas = QWidget()
        self.tabs.addTab(self.tab_em_aberto, "Em aberto")
        self.tabs.addTab(self.tab_concluidas, "Concluídas")

        # Layout Em Aberto
        layout_em_aberto = QHBoxLayout()
        self.tab_em_aberto.setLayout(layout_em_aberto)
        # ... aqui continua normalmente o layout da esquerda, meio e direita da aba em aberto ...

        # ===================== TAB CONCLUÍDAS =====================
        layout_concluidas = QVBoxLayout()
        self.tab_concluidas.setLayout(layout_concluidas)
        self.tabela_compras_concluidas = QTableWidget()
        self.tabela_compras_concluidas.setColumnCount(6)
        self.tabela_compras_concluidas.setHorizontalHeaderLabels([
            "ID", "Fornecedor", "Data", "Total dos produtos (R$)", "Valor com abatimento/adiantamento", "Status"
        ])
        self.tabela_compras_concluidas.setEditTriggers(QTableWidget.DoubleClicked)
        self.tabela_compras_concluidas.cellClicked.connect(
            lambda row, col: self.mostrar_itens_da_compra(row, col, tabela=self.tabela_compras_concluidas)
        )
        layout_concluidas.addWidget(self.tabela_compras_concluidas)

        # ===================== ENTRADA DE DADOS - ESQUERDA =====================
        layout_entrada = QVBoxLayout()
        layout_dados = QGridLayout()

        # Número da balança
        self.combo_fornecedor = QComboBox()
        self.combo_fornecedor.setEditable(True)
        self.input_numero_balanca = QLineEdit()
        self.input_numero_balanca.setPlaceholderText("Número balança")
        self.input_numero_balanca.editingFinished.connect(
            lambda: self.selecionar_fornecedor_por_numero_balanca(self.input_numero_balanca, self.combo_fornecedor)
        )

        layout_dados.addWidget(QLabel("Número na Balança"), 1, 0)
        layout_dados.addWidget(self.input_numero_balanca, 1, 1)

        # Fornecedor e data
        self.input_data = QDateEdit()
        self.input_data.setDate(QDate.currentDate())
        self.input_data.setCalendarPopup(True)
        layout_dados.addWidget(QLabel("Fornecedor"), 0, 0)
        layout_dados.addWidget(self.combo_fornecedor, 0, 1)
        self.combo_fornecedor.currentIndexChanged.connect(self.ao_mudar_fornecedor)
        self.label_saldo_fornecedor = QLabel("Saldo: R$ 0,00")
        self.label_saldo_fornecedor.setStyleSheet(
            "font-weight: bold; color: #b22222; font-size: 13px; text-decoration: underline; cursor: pointer;"
        )
        self.label_saldo_fornecedor.setCursor(Qt.PointingHandCursor)
        self.label_saldo_fornecedor.mousePressEvent = self.on_saldo_label_clicked
        layout_dados.addWidget(self.label_saldo_fornecedor, 2, 0, 1, 2)
        layout_dados.addWidget(QLabel("Data da Compra"), 3, 0)
        layout_dados.addWidget(self.input_data, 3, 1)

        self.combo_categoria_temporaria = QComboBox()
        self.combo_categoria_temporaria.addItem("Selecione uma categoria", 0)
        layout_dados.addWidget(QLabel("Categoria (para esta compra)"), 4, 0)
        layout_dados.addWidget(self.combo_categoria_temporaria, 4, 1)

        # ========== ABAIXO: ComboBox + QLineEdit para Abatimento/Adiantamento ==========
        self.combo_tipo_lancamento = QComboBox()
        self.combo_tipo_lancamento.addItem("Abatimento", "abatimento")
        self.combo_tipo_lancamento.addItem("Adiantamento", "adiantamento")
        self.combo_tipo_lancamento.setCurrentIndex(0)
        self.combo_tipo_lancamento.currentIndexChanged.connect(self.atualizar_total_compra)

        self.input_valor_lancamento = QLineEdit()
        self.input_valor_lancamento.setPlaceholderText("Valor")
        self.input_valor_lancamento.textChanged.connect(self.atualizar_total_compra)

        layout_lancamento = QHBoxLayout()
        layout_lancamento.addWidget(self.combo_tipo_lancamento)
        layout_lancamento.addWidget(self.input_valor_lancamento)

        layout_dados.addWidget(QLabel("Abatimento/Adiantamento"), 5, 0)
        layout_dados.addLayout(layout_lancamento, 5, 1)
        # ========== FIM NOVO CAMPO ==========

        # Status da compra
        self.combo_status = QComboBox()
        for s in STATUS_LIST:
            self.combo_status.addItem(s)
        layout_dados.addWidget(QLabel("Status"), 6, 0)
        layout_dados.addWidget(self.combo_status, 6, 1)

        layout_entrada.addLayout(layout_dados)

        layout_produto = QGridLayout()
        self.combo_produto = QComboBox()
        self.combo_produto.currentIndexChanged.connect(self.zerar_quantidade)
        self.input_quantidade = QSpinBox()
        self.input_quantidade.setMinimum(1)
        self.input_quantidade.setMaximum(9999)
        layout_produto.addWidget(QLabel("Produto"), 0, 0)
        layout_produto.addWidget(self.combo_produto, 0, 1)
        layout_produto.addWidget(QLabel("Quantidade"), 1, 0)
        layout_produto.addWidget(self.input_quantidade, 1, 1)

        self.btn_adicionar_item = QPushButton("Adicionar Produto")
        self.btn_adicionar_item.clicked.connect(self.adicionar_item)
        layout_produto.addWidget(self.btn_adicionar_item, 2, 0, 1, 2)

        layout_entrada.addLayout(layout_produto)

        self.tabela_itens_adicionados = QTableWidget()
        self.tabela_itens_adicionados.setColumnCount(4)
        self.tabela_itens_adicionados.setHorizontalHeaderLabels(["Produto", "Qtd", "Preço Unit.", "Total"])
        self.tabela_itens_adicionados.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tabela_itens_adicionados.cellChanged.connect(self.atualizar_item_editado)
        self.tabela_itens_adicionados.setSelectionBehavior(QTableWidget.SelectRows)

        layout_entrada.addWidget(QLabel("Itens da Compra (antes de finalizar):"))
        layout_entrada.addWidget(self.tabela_itens_adicionados)

        self.label_total_compra = QLabel("Total: R$ 0,00")
        layout_entrada.addWidget(self.label_total_compra)

        self.btn_remover_item = QPushButton("Remover Item Selecionado")
        self.btn_remover_item.clicked.connect(self.remover_item)
        layout_entrada.addWidget(self.btn_remover_item)

        self.btn_limpar_itens = QPushButton("Limpar Itens")
        self.btn_limpar_itens.clicked.connect(self.limpar_itens)
        layout_entrada.addWidget(self.btn_limpar_itens)

        self.btn_finalizar = QPushButton("Finalizar Compra")
        self.btn_finalizar.clicked.connect(self.finalizar_compra)
        layout_entrada.addWidget(self.btn_finalizar)

        self.btn_editar_compra = QPushButton("Editar Compra Finalizada Selecionada")
        self.btn_editar_compra.clicked.connect(self.editar_compra_finalizada)
        layout_entrada.addWidget(self.btn_editar_compra)

        self.btn_excluir_compra = QPushButton("Excluir Compra Finalizada Selecionada")
        self.btn_excluir_compra.clicked.connect(self.excluir_compra_finalizada)
        layout_entrada.addWidget(self.btn_excluir_compra)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.acao_cancelar)
        layout_entrada.addWidget(self.btn_cancelar)

        # Botão para alterar status
        self.btn_alterar_status = QPushButton("Alterar Status da Compra Selecionada")
        self.btn_alterar_status.clicked.connect(self.alterar_status_compra)
        layout_entrada.addWidget(self.btn_alterar_status)

        layout_em_aberto.addLayout(layout_entrada, 3)

        # Filtros e tabela - meio
        layout_compras_com_filtros = QVBoxLayout()
        layout_em_aberto.addLayout(layout_compras_com_filtros, 5)

        layout_compras_com_filtros.addWidget(QLabel("Número da Balança:"))
        self.filtro_numero_balanca = QLineEdit()
        self.filtro_numero_balanca.setPlaceholderText("Digite o número da balança")
        layout_compras_com_filtros.addWidget(self.filtro_numero_balanca)

        layout_compras_com_filtros.addWidget(QLabel("Fornecedor:"))
        self.filtro_combo_fornecedor = QComboBox()
        self.filtro_combo_fornecedor.addItem("Todos os Fornecedores", None)
        for f in self.listar_fornecedores():
            self.filtro_combo_fornecedor.addItem(f"{f['nome']} (ID {f['id']})", f['id'])
        layout_compras_com_filtros.addWidget(self.filtro_combo_fornecedor)

        layout_compras_com_filtros.addWidget(QLabel("Status:"))
        self.filtro_combo_status = QComboBox()
        self.filtro_combo_status.addItem("Todos", None)
        for s in STATUS_LIST:
            self.filtro_combo_status.addItem(s, s)
        layout_compras_com_filtros.addWidget(self.filtro_combo_status)

        self.filtro_numero_balanca.editingFinished.connect(
            lambda: self.selecionar_fornecedor_por_numero_balanca(
                self.filtro_numero_balanca, self.filtro_combo_fornecedor
            )
        )

        linha_datas_e_botoes = QHBoxLayout()
        linha_datas_e_botoes.addWidget(QLabel("De:"))
        self.filtro_data_de = QDateEdit()
        self.filtro_data_de.setCalendarPopup(True)
        self.filtro_data_de.setDate(QDate.currentDate().addMonths(-1))
        linha_datas_e_botoes.addWidget(self.filtro_data_de)

        linha_datas_e_botoes.addWidget(QLabel("Até:"))
        self.filtro_data_ate = QDateEdit()
        self.filtro_data_ate.setCalendarPopup(True)
        self.filtro_data_ate.setDate(QDate.currentDate())
        linha_datas_e_botoes.addWidget(self.filtro_data_ate)

        btn_aplicar_filtro = QPushButton("Aplicar Filtro")
        btn_aplicar_filtro.clicked.connect(self.aplicar_filtro_compras)
        linha_datas_e_botoes.addWidget(btn_aplicar_filtro)

        btn_limpar_filtro = QPushButton("Limpar Filtro")
        btn_limpar_filtro.clicked.connect(self.limpar_filtro_compras)
        linha_datas_e_botoes.addWidget(btn_limpar_filtro)

        layout_compras_com_filtros.addLayout(linha_datas_e_botoes)

        self.tabela_compras_aberto = QTableWidget()
        self.tabela_compras_aberto.setColumnCount(6)
        self.tabela_compras_aberto.setHorizontalHeaderLabels([
            "ID", "Fornecedor", "Data", "Total dos produtos (R$)", "Valor com abatimento/adiantamento", "Status"
        ])
        self.tabela_compras_aberto.setEditTriggers(QTableWidget.DoubleClicked)
        self.tabela_compras_aberto.cellClicked.connect(lambda row, col: self.mostrar_itens_da_compra(row, col, tabela=self.tabela_compras_aberto))
        self.tabela_compras_aberto.itemSelectionChanged.connect(self.atualizar_campo_texto_copiavel)
        layout_compras_com_filtros.addWidget(self.tabela_compras_aberto)

        # Área direita, igual antes
        layout_direita = QVBoxLayout()
        layout_em_aberto.addLayout(layout_direita, 3)
        self.tabela_itens_compra = QTableWidget()
        self.tabela_itens_compra.setColumnCount(4)
        self.tabela_itens_compra.setHorizontalHeaderLabels(["Produto", "Qtd", "Preço Unit.", "Total"])
        self.tabela_itens_compra.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_direita.addWidget(self.tabela_itens_compra)

        self.label_total_com_abatimento = QLabel("Total com Abatimento: R$ 0,00")
        self.label_total_com_abatimento.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 5px;")
        layout_direita.addWidget(self.label_total_com_abatimento)

        self.campo_texto_copiavel = QLineEdit()
        self.campo_texto_copiavel.setReadOnly(True)
        self.campo_texto_copiavel.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout_direita.addWidget(self.campo_texto_copiavel)
        self.campo_texto_copiavel.mousePressEvent = self.copiar_campo_texto_copiavel

        # --- NOVO BOTÃO PARA TROCAR CONTA DO FORNECEDOR ---
        self.btn_trocar_conta_fornecedor = QPushButton("Trocar conta do fornecedor (só para esta compra)")
        self.btn_trocar_conta_fornecedor.clicked.connect(self.abrir_dialog_troca_conta_fornecedor)
        layout_direita.addWidget(self.btn_trocar_conta_fornecedor)
        # ---------------------------------------------------

        self.btn_exportar_pdf = QPushButton("Exportar PDF")
        self.btn_exportar_pdf.clicked.connect(self.exportar_compra_pdf)
        layout_direita.addWidget(self.btn_exportar_pdf)

        self.btn_exportar_jpg = QPushButton("Exportar JPG")
        self.btn_exportar_jpg.clicked.connect(self.exportar_compra_jpg)
        layout_direita.addWidget(self.btn_exportar_jpg)

        self.setLayout(layout_principal)
        self.itens_compra = []
        self.atualizar_tabela_itens_adicionados()
        self.atualizar_tabelas()
        self.status_delegate = StatusComboDelegate(self.STATUS_COLORS, STATUS_LIST, self.tabela_compras_aberto)
        self.tabela_compras_aberto.setItemDelegateForColumn(5, self.status_delegate)
        self.tabela_compras_concluidas.setItemDelegateForColumn(5, self.status_delegate)
        self.tabela_compras_aberto.itemChanged.connect(self.on_status_item_changed)
        self.tabela_compras_concluidas.itemChanged.connect(self.on_status_item_changed)

    def carregar_dados(self):
        self.atualizar_tabelas()
        self.combo_produto.blockSignals(True)
        self.combo_produto.clear()
        for p in self.listar_produtos():
            self.combo_produto.addItem(p['nome'], p['id'])
        self.combo_produto.setCurrentIndex(-1)
        self.combo_produto.blockSignals(False)
        self.atualizar_tabelas()

    def abrir_dialog_troca_conta_fornecedor(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox, QComboBox, QLabel, QMessageBox

        compra_id = self.obter_compra_id_selecionado()
        if not compra_id:
            QMessageBox.warning(self, "Atenção", "Selecione uma compra primeiro.")
            return

        fornecedor_id = self.obter_fornecedor_id_da_compra(compra_id)
        if not fornecedor_id:
            QMessageBox.warning(self, "Erro", "Não foi possível identificar o fornecedor da compra selecionada.")
            return

        contas_do_fornecedor = self.listar_contas_do_fornecedor(fornecedor_id)
        if not contas_do_fornecedor:
            QMessageBox.information(self, "Sem contas", "Este fornecedor não possui contas bancárias cadastradas.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Escolher conta do fornecedor para esta compra")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Selecione a conta bancária:"))

        combo_contas = QComboBox(dialog)
        for conta in contas_do_fornecedor:
            texto = f"{conta['apelido']} - {conta['banco']} Ag:{conta['agencia']} Conta:{conta['conta']}"
            if conta.get('padrao'):
                texto += " (padrão)"
            combo_contas.addItem(texto, conta['id'])

        layout.addWidget(combo_contas)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        def on_ok():
            conta_id = combo_contas.currentData()
            compra_id_local = self.obter_compra_id_selecionado()
            if conta_id and compra_id_local:
                with get_cursor() as cursor:
                    # Atualiza a conta da compra
                    cursor.execute(
                        "UPDATE compras SET dados_bancarios_id = %s WHERE id = %s",
                        (conta_id, compra_id_local)
                    )
                # Chama o méodo para atualizar o campo copiável
                self.atualizar_campo_texto_copiavel()
            dialog.accept()

        def on_cancel():
            dialog.reject()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(on_cancel)

        dialog.exec()

    def atualizar_tabelas(self):
        status_filtro = self.filtro_combo_status.currentData()
        fornecedor_id = self.filtro_combo_fornecedor.currentData()
        data_de = self.filtro_data_de.date().toPython()
        data_ate = self.filtro_data_ate.date().toPython()

        # Em aberto: todas exceto concluída
        compras_aberto = self.listar_compras(
            status=None if status_filtro == "Concluída" else status_filtro,
            status_not="Concluída",
            data_de=data_de,
            data_ate=data_ate,
            fornecedor_id=fornecedor_id
        )
        # Concluídas: só concluída
        compras_concluidas = self.listar_compras(
            status="Concluída",
            data_de=data_de,
            data_ate=data_ate,
            fornecedor_id=fornecedor_id
        )
        self.preencher_tabela_compras(self.tabela_compras_aberto, compras_aberto)
        self.preencher_tabela_compras(self.tabela_compras_concluidas, compras_concluidas)

    def preencher_tabela_compras(self, tabela, compras):
        tabela.blockSignals(True)
        tabela.setRowCount(len(compras))
        for i, c in enumerate(compras):
            tabela.setItem(i, 0, QTableWidgetItem(str(c['id'])))
            tabela.setItem(i, 1, QTableWidgetItem(c['fornecedor_nome']))
            tabela.setItem(i, 2, QTableWidgetItem(str(c['data'])))
            total_produtos = self.obter_total_produtos(c['id'])
            tabela.setItem(i, 3, QTableWidgetItem(self.locale.toString(float(total_produtos), 'f', 2)))
            valor_final = self.obter_valor_com_abatimento_adiantamento(c['id'], total_produtos)
            tabela.setItem(i, 4, QTableWidgetItem(self.locale.toString(float(valor_final), 'f', 2)))
            tabela.setItem(i, 5, QTableWidgetItem(c['status']))
        tabela.blockSignals(False)

    def obter_total_produtos(self, compra_id):
        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT SUM(quantidade * preco_unitario) as total_produtos
                           FROM itens_compra
                           WHERE compra_id = %s
                           """, (compra_id,))
            row = cursor.fetchone()
            return row["total_produtos"] if row and row["total_produtos"] is not None else 0

    def obter_valor_com_abatimento_adiantamento(self, compra_id, total_produtos=None):
        if total_produtos is None:
            total_produtos = self.obter_total_produtos(compra_id)
        with get_cursor() as cursor:
            # Pega abatimento
            cursor.execute("SELECT valor_abatimento FROM compras WHERE id = %s", (compra_id,))
            row = cursor.fetchone()
            abatimento = Decimal(str(row["valor_abatimento"])) if row and row["valor_abatimento"] else Decimal('0.0')
            # Pega adiantamento/inclusao
            cursor.execute("""
                           SELECT COALESCE(SUM(valor), 0) as adiantamento
                           FROM debitos_fornecedores
                           WHERE compra_id = %s
                             AND tipo = 'inclusao'
                           """, (compra_id,))
            row = cursor.fetchone()
            adiantamento = Decimal(str(row["adiantamento"])) if row and row["adiantamento"] else Decimal('0.0')
        total_produtos = Decimal(str(total_produtos))
        if adiantamento > 0:
            return total_produtos + adiantamento
        else:
            return total_produtos - abatimento

    def on_status_item_changed(self, item):
        if item.column() == 5:
            row = item.row()
            tabela = item.tableWidget()
            compra_id = int(tabela.item(row, 0).text())
            novo_status = item.text()
            self.atualizar_status_compra(compra_id, novo_status)
            self.atualizar_tabelas()

    def aplicar_filtro_compras(self):
        self.atualizar_tabelas()

    def limpar_filtro_compras(self):
        self.filtro_combo_fornecedor.setCurrentIndex(0)
        self.filtro_combo_status.setCurrentIndex(0)
        self.filtro_data_de.setDate(QDate.currentDate().addMonths(-1))
        self.filtro_data_ate.setDate(QDate.currentDate())
        self.atualizar_tabelas()

    def zerar_quantidade(self):
        self.input_quantidade.setValue(1)

    def obter_saldo_devedor_fornecedor(self, fornecedor_id):
        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT valor, tipo
                           FROM debitos_fornecedores
                           WHERE fornecedor_id = %s
                           """, (fornecedor_id,))
            saldo = Decimal('0.00')
            for row in cursor.fetchall():
                if row["tipo"] in ("inclusao", "adiantamento"):
                    saldo += Decimal(str(row["valor"]))
                else:
                    saldo -= Decimal(str(row["valor"]))
            return saldo

    def atualizar_saldo_fornecedor(self):
        fornecedor_id = self.combo_fornecedor.currentData()
        if not fornecedor_id:
            self.label_saldo_fornecedor.setText("Saldo devedor: R$ 0,00")
            self.label_saldo_fornecedor.setStyleSheet(
                "font-weight: bold; color: #808080; font-size: 13px; text-decoration: underline; cursor: pointer;")
            return
        saldo = self.obter_saldo_devedor_fornecedor(fornecedor_id)
        self.label_saldo_fornecedor.setText(f"Saldo: R$ {self.locale.toString(float(saldo), 'f', 2)}")

        # Atualiza cor de acordo com saldo
        if saldo > 0:
            cor = "#b22222"  # vermelho
        elif saldo < 0:
            cor = "#228B22"  # verde
        else:
            cor = "#808080"  # cinza
        self.label_saldo_fornecedor.setStyleSheet(
            f"font-weight: bold; color: {cor}; font-size: 13px; text-decoration: underline; cursor: pointer;"
        )

    def on_saldo_label_clicked(self, event):
        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id and hasattr(self, 'janela_debitos'):
            if hasattr(self.janela_debitos, "filtrar_por_fornecedor"):
                self.janela_debitos.filtrar_por_fornecedor(fornecedor_id)
            if hasattr(self, "main_window"):
                index = self.main_window.stack.indexOf(self.janela_debitos)
                self.main_window.stack.setCurrentIndex(index)

    def set_main_window(self, main_window):
        self.main_window = main_window

    def copiar_campo_texto_copiavel(self, event):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.campo_texto_copiavel.text())
        self.campo_texto_copiavel.setStyleSheet("background-color: #b2f2b4; font-weight: bold; font-size: 13px;")
        QTimer.singleShot(350, lambda: self.campo_texto_copiavel.setStyleSheet("font-weight: bold; font-size: 13px;"))
        QLineEdit.mousePressEvent(self.campo_texto_copiavel, event)

    def carregar_categorias_para_fornecedor(self, fornecedor_id):
        self.combo_categoria_temporaria.blockSignals(True)
        self.combo_categoria_temporaria.clear()
        self.combo_categoria_temporaria.addItem("Selecione uma categoria", 0)
        categorias = self.obter_categorias_do_fornecedor(fornecedor_id)
        for c in categorias:
            self.combo_categoria_temporaria.addItem(c['nome'], c['id'])
        self.combo_categoria_temporaria.setCurrentIndex(1 if self.combo_categoria_temporaria.count() > 1 else 0)
        self.combo_categoria_temporaria.blockSignals(False)

    def ao_mudar_fornecedor(self):
        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id is not None:
            self.carregar_categorias_para_fornecedor(fornecedor_id)
            self.selecionar_categoria_do_fornecedor(fornecedor_id)
            self.atualizar_saldo_fornecedor()

    def adicionar_item(self):
        produto_id = self.combo_produto.currentData()
        quantidade = self.input_quantidade.value()
        if produto_id is None or quantidade <= 0:
            QMessageBox.warning(self, "Erro", "Selecione um produto e uma quantidade válida.")
            return

        produto = self.obter_produto(produto_id)
        if produto is None:
            QMessageBox.critical(self, "Erro", "Produto não encontrado.")
            return

        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id is None:
            QMessageBox.warning(self, "Erro", "Selecione um fornecedor.")
            return

        categoria_id = self.combo_categoria_temporaria.currentData()
        if categoria_id is None or categoria_id == 0:
            categoria_id = self.obter_id_categoria_padrao()
            if categoria_id is None:
                QMessageBox.warning(self, "Erro", "Selecione uma categoria válida para esta compra.")
                return

        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT ajuste_fixo
                           FROM ajustes_fixos_produto_fornecedor_categoria
                           WHERE produto_id = %s
                             AND categoria_id = %s
                           """, (produto_id, categoria_id))
            ajuste = cursor.fetchone()

        ajuste_fixo = Decimal(str(ajuste["ajuste_fixo"])) if ajuste else Decimal('0.00')

        preco = Decimal(str(produto["preco_base"])) + ajuste_fixo
        total = Decimal(str(quantidade)) * preco

        self.itens_compra.append({
            "produto_id": produto_id,
            "nome": produto["nome"],
            "quantidade": quantidade,
            "preco": preco,
            "total": total
        })

        self.atualizar_tabela_itens_adicionados()
        self.combo_produto.setCurrentIndex(-1)

    def atualizar_tabela_itens_adicionados(self):
        self.tabela_itens_adicionados.blockSignals(True)
        self.tabela_itens_adicionados.setRowCount(len(self.itens_compra))
        for i, item in enumerate(self.itens_compra):
            self.tabela_itens_adicionados.setItem(i, 0, QTableWidgetItem(item["nome"]))
            self.tabela_itens_adicionados.setItem(i, 1, QTableWidgetItem(str(item["quantidade"])))
            preco_formatado = self.locale.toString(float(item['preco']), 'f', 2)
            total_formatado = self.locale.toString(float(item['total']), 'f', 2)
            self.tabela_itens_adicionados.setItem(i, 2, QTableWidgetItem(preco_formatado))
            self.tabela_itens_adicionados.setItem(i, 3, QTableWidgetItem(total_formatado))
        self.tabela_itens_adicionados.blockSignals(False)
        total = sum(item['total'] for item in self.itens_compra)
        total_formatado = self.locale.toString(float(total), 'f', 2)
        self.label_total_compra.setText(f"Total: R$ {total_formatado}")

    def remover_item(self):
        selected = self.tabela_itens_adicionados.currentRow()
        if selected >= 0:
            del self.itens_compra[selected]
            self.atualizar_tabela_itens_adicionados()

    def limpar_itens(self):
        self.itens_compra = []
        self.atualizar_tabela_itens_adicionados()

    def atualizar_total_compra(self):
        valor_texto = self.input_valor_lancamento.text().replace(',', '.')
        try:
            valor = Decimal(valor_texto) if valor_texto else Decimal('0.00')
        except Exception:
            valor = Decimal('0.00')
        tipo = self.combo_tipo_lancamento.currentData()
        total = sum(Decimal(str(item['total'])) for item in self.itens_compra)
        if tipo == "abatimento":
            total_final = total - valor
        else:  # adiantamento
            total_final = total + valor
        total_formatado = self.locale.toString(float(total_final), 'f', 2)
        self.label_total_compra.setText(f"Total: R$ {total_formatado}")

    def finalizar_compra(self):
        if not self.itens_compra:
            QMessageBox.warning(self, "Erro", "Adicione pelo menos um item antes de finalizar.")
            return

        fornecedor_id = self.combo_fornecedor.currentData()
        data_compra = self.input_data.date().toPython()
        try:
            valor_lancamento = Decimal(self.input_valor_lancamento.text().replace(',',
                                                                                  '.')) if self.input_valor_lancamento.text() else Decimal(
                '0.00')
        except ValueError:
            QMessageBox.warning(self, "Erro", "Valor de abatimento/adiantamento inválido.")
            return

        tipo_lancamento = self.combo_tipo_lancamento.currentData()
        status = self.combo_status.currentText()

        valor_abatimento = valor_lancamento if tipo_lancamento == "abatimento" else Decimal('0.00')
        valor_inclusao = valor_lancamento if tipo_lancamento == "adiantamento" else Decimal('0.00')

        if self.compra_edit_id is None:
            compra_id = self.adicionar_compra(
                fornecedor_id, data_compra, valor_abatimento, self.itens_compra, status
            )
            if tipo_lancamento == "adiantamento" and valor_inclusao > 0:
                with get_cursor(commit=True) as cursor:
                    cursor.execute(
                        """
                        INSERT INTO debitos_fornecedores
                            (fornecedor_id, compra_id, data_lancamento, descricao, valor, tipo)
                        VALUES (%s, %s, %s, %s, %s, 'inclusao')
                        """,
                        (fornecedor_id, compra_id, data_compra, 'Inclusão em compra', abs(valor_inclusao))
                    )
            QMessageBox.information(self, "Sucesso", "Compra cadastrada com sucesso.")
        else:
            # Remover lançamentos antigos de abatimento/adiantamento
            with get_cursor(commit=True) as cursor:
                cursor.execute(
                    "DELETE FROM debitos_fornecedores WHERE compra_id = %s AND (tipo = 'abatimento' OR tipo = 'inclusao')",
                    (self.compra_edit_id,)
                )
                # Atualiza valor_abatimento na compra
                cursor.execute("UPDATE compras SET valor_abatimento = %s WHERE id = %s",
                               (valor_abatimento, self.compra_edit_id))

                # Insere o lançamento correto, se houver valor
                if tipo_lancamento == "adiantamento" and valor_inclusao > 0:
                    cursor.execute(
                        """
                        INSERT INTO debitos_fornecedores
                            (fornecedor_id, compra_id, data_lancamento, descricao, valor, tipo)
                        VALUES (%s, %s, %s, %s, %s, 'inclusao')
                        """,
                        (fornecedor_id, self.compra_edit_id, data_compra, 'Inclusão em compra', abs(valor_inclusao))
                    )
                elif tipo_lancamento == "abatimento" and valor_abatimento > 0:
                    cursor.execute(
                        """
                        INSERT INTO debitos_fornecedores
                            (fornecedor_id, compra_id, data_lancamento, descricao, valor, tipo)
                        VALUES (%s, %s, %s, %s, %s, 'abatimento')
                        """,
                        (fornecedor_id, self.compra_edit_id, data_compra, 'Abatimento em compra', abs(valor_abatimento))
                    )

            # Atualiza os dados da compra e itens normalmente
            self.atualizar_compra(
                self.compra_edit_id,
                fornecedor_id,
                data_compra,
                valor_abatimento,
                self.itens_compra,
                status
            )
            QMessageBox.information(self, "Sucesso", "Compra editada com sucesso.")

        # Limpa e atualiza UI
        self.limpar_campos()
        self.atualizar_tabelas()
        self.limpar_itens()
        self.carregar_fornecedores()
        self.carregar_produtos()
        if hasattr(self, 'janela_debitos'):
            self.janela_debitos.atualizar()

    def editar_compra_finalizada(self):
        linha = self.tabela_compras_aberto.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Editar Compra", "Selecione uma compra para editar.")
            return
        compra_id_item = self.tabela_compras_aberto.item(linha, 0)
        if compra_id_item is None:
            return
        compra_id = int(compra_id_item.text())

        with get_cursor() as cursor:
            cursor.execute("""
                SELECT fornecedor_id, data_compra, valor_abatimento, status
                FROM compras WHERE id = %s
            """, (compra_id,))
            compra = cursor.fetchone()

            cursor.execute("""
                SELECT p.nome AS produto_nome, i.produto_id, i.quantidade, i.preco_unitario, (i.quantidade * i.preco_unitario) AS total
                FROM itens_compra i
                JOIN produtos p ON i.produto_id = p.id
                WHERE i.compra_id = %s
            """, (compra_id,))
            itens = cursor.fetchall()

            # Busca adiantamento (inclusao)
            cursor.execute("""
                SELECT COALESCE(SUM(valor),0) as valor_adiantamento
                FROM debitos_fornecedores
                WHERE compra_id = %s AND tipo = 'inclusao'
            """, (compra_id,))
            adiantamento_row = cursor.fetchone()
            valor_adiantamento = float(adiantamento_row["valor_adiantamento"]) if adiantamento_row else 0.0

        if compra is None:
            QMessageBox.warning(self, "Erro", "Compra não encontrada.")
            return

        idx_fornecedor = self.combo_fornecedor.findData(compra['fornecedor_id'])
        self.combo_fornecedor.setCurrentIndex(idx_fornecedor if idx_fornecedor >= 0 else 0)
        self.input_data.setDate(QDate(compra['data_compra']))

        # Atualiza combo e campo de valor conforme o tipo de lançamento
        if valor_adiantamento > 0:
            self.combo_tipo_lancamento.setCurrentIndex(1)  # Adiantamento
            self.input_valor_lancamento.setText(str(valor_adiantamento))
        else:
            self.combo_tipo_lancamento.setCurrentIndex(0)  # Abatimento
            self.input_valor_lancamento.setText(str(compra['valor_abatimento']))

        idx_status = self.combo_status.findText(compra['status'])
        self.combo_status.setCurrentIndex(idx_status if idx_status >= 0 else 0)

        self.itens_compra = []
        for item in itens:
            self.itens_compra.append({
                "produto_id": item['produto_id'],
                "nome": item['produto_nome'],
                "quantidade": item['quantidade'],
                "preco": item['preco_unitario'],
                "total": item['total']
            })

        self.compra_edit_id = compra_id
        self.atualizar_tabela_itens_adicionados()

    def alterar_status_compra(self):
        tabela = self.tabela_compras_aberto if self.tabs.currentIndex() == 0 else self.tabela_compras_concluidas
        compra_id = self.obter_compra_id_selecionado(tabela=tabela)
        if compra_id is None:
            QMessageBox.warning(self, "Alterar Status", "Selecione uma compra para alterar o status.")
            return

        novo_status, ok = QComboBox.getItem(self, "Alterar Status", "Selecione o novo status:", STATUS_LIST, 0, False)
        if ok and novo_status:
            self.atualizar_status_compra(compra_id, novo_status)
            self.atualizar_tabelas()
            QMessageBox.information(self, "Sucesso", f"Status alterado para {novo_status}.")
        # Se status for "Concluída", a compra irá automaticamente para a aba de concluídas na próxima atualização.

    def excluir_compra_finalizada(self):
        linha = self.tabela_compras_aberto.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Excluir Compra", "Selecione uma compra para excluir.")
            return

        compra_id_item = self.tabela_compras_aberto.item(linha, 0)
        if compra_id_item is None:
            return

        compra_id = int(compra_id_item.text())
        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT id
                           FROM debitos_fornecedores
                           WHERE compra_id = %s
                             AND tipo = 'abatimento'
                           """, (compra_id,))
            abatimento = cursor.fetchone()

        if abatimento:
            confirm = QMessageBox.question(
                self,
                "Confirmar Exclusão",
                "Esta compra possui um abatimento lançado nos débitos do fornecedor.\n"
                "Se você continuar, o lançamento do abatimento também será excluído dos débitos.\n"
                "Deseja excluir mesmo assim?",
                QMessageBox.Yes | QMessageBox.No
            )
        else:
            confirm = QMessageBox.question(
                self,
                "Confirmar Exclusão",
                f"Tem certeza que deseja excluir a compra ID {compra_id}?",
                QMessageBox.Yes | QMessageBox.No
            )

        if confirm != QMessageBox.Yes:
            return

        try:
            with get_cursor(commit=True) as cursor:
                # Exclua TODOS os débitos relacionados à compra (não só abatimento)
                cursor.execute("DELETE FROM debitos_fornecedores WHERE compra_id = %s", (compra_id,))
                cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))
                cursor.execute("DELETE FROM compras WHERE id = %s", (compra_id,))
            QMessageBox.information(self, "Sucesso", "Compra excluída com sucesso.")
            self.atualizar_tabelas()
            self.tabela_itens_compra.setRowCount(0)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao excluir compra: {e}")

        if hasattr(self, 'janela_debitos'):
            self.janela_debitos.atualizar()

    def selecionar_fornecedor_por_numero_balanca(self, campo_input: QLineEdit, combo_fornecedor: QComboBox):
        numero = campo_input.text().strip()
        if not numero:
            return

        with get_cursor() as cursor:
            cursor.execute("SELECT id FROM fornecedores WHERE fornecedores_numerobalanca = %s", (numero,))
            resultado = cursor.fetchone()

        if resultado:
            idx = combo_fornecedor.findData(resultado['id'])
            if idx >= 0:
                combo_fornecedor.setCurrentIndex(idx)
                if hasattr(self, 'selecionar_categoria_do_fornecedor'): self.selecionar_categoria_do_fornecedor(idx)
        else:
            QMessageBox.warning(self, "Fornecedor não encontrado", f"Nenhum fornecedor com número de balança {numero}.")
            self.input_numero_balanca.clear()

    def limpar_campos(self):
        self.combo_fornecedor.setCurrentIndex(0)
        self.input_numero_balanca.clear()
        self.input_data.setDate(QDate.currentDate())
        self.input_valor_lancamento.clear()
        self.combo_tipo_lancamento.setCurrentIndex(0)
        self.combo_produto.setCurrentIndex(-1)
        self.input_quantidade.setValue(1)
        self.item_edit_index = None
        self.compra_edit_id = None
        self.combo_status.setCurrentIndex(0)

    def acao_cancelar(self):
        self.limpar_campos()
        self.limpar_itens()
        self.carregar_fornecedores()
        self.carregar_produtos()

    def mostrar_itens_da_compra(self, row, column, tabela=None):
        if tabela is None:
            tabela = self.tabela_compras_aberto
        compra_id_item = tabela.item(row, 0)
        if compra_id_item is None:
            return

        compra_id = int(compra_id_item.text())
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT p.nome AS produto_nome,
                       i.produto_id,
                       i.quantidade,
                       i.preco_unitario,
                       (i.quantidade * i.preco_unitario) AS total
                FROM itens_compra i
                JOIN produtos p ON i.produto_id = p.id
                WHERE i.compra_id = %s
            """, (compra_id,))
            itens = cursor.fetchall()

            # Busca valores de abatimento e adiantamento (inclusao)
            cursor.execute("SELECT valor_abatimento FROM compras WHERE id = %s", (compra_id,))
            compra = cursor.fetchone()

            cursor.execute("""
                SELECT COALESCE(SUM(valor),0) AS valor_adiantamento
                FROM debitos_fornecedores
                WHERE compra_id = %s AND tipo = 'inclusao'
            """, (compra_id,))
            adiantamento_row = cursor.fetchone()

        valor_abatimento = float(compra["valor_abatimento"]) if compra else 0.0
        valor_adiantamento = float(adiantamento_row["valor_adiantamento"]) if adiantamento_row else 0.0

        subtotal = float(sum(item["total"] for item in itens))

        # Mostra linhas dos itens
        linhas_extra = 1  # sempre terá abatimento ou adiantamento
        self.tabela_itens_compra.setRowCount(len(itens) + linhas_extra)
        for i, item in enumerate(itens):
            self.tabela_itens_compra.setItem(i, 0, QTableWidgetItem(item['produto_nome']))
            self.tabela_itens_compra.setItem(i, 1, QTableWidgetItem(str(item['quantidade'])))
            preco_formatado = self.locale.toString(float(item['preco_unitario']), 'f', 2)
            total_formatado = self.locale.toString(float(item['total']), 'f', 2)
            self.tabela_itens_compra.setItem(i, 2, QTableWidgetItem(preco_formatado))
            self.tabela_itens_compra.setItem(i, 3, QTableWidgetItem(total_formatado))

        # Linha para abatimento ou adiantamento
        if valor_adiantamento > 0:
            self.tabela_itens_compra.setItem(len(itens), 0, QTableWidgetItem("Adiantamento"))
            self.tabela_itens_compra.setItem(len(itens), 1, QTableWidgetItem(""))
            self.tabela_itens_compra.setItem(len(itens), 2, QTableWidgetItem(""))
            self.tabela_itens_compra.setItem(len(itens), 3, QTableWidgetItem(f"+{self.locale.toString(valor_adiantamento, 'f', 2)}"))
            total_final = subtotal + valor_adiantamento
            self.label_total_com_abatimento.setText(
                f"Total com Adiantamento: R$ {self.locale.toString(total_final, 'f', 2)}"
            )
        else:
            self.tabela_itens_compra.setItem(len(itens), 0, QTableWidgetItem("Abatimento"))
            self.tabela_itens_compra.setItem(len(itens), 1, QTableWidgetItem(""))
            self.tabela_itens_compra.setItem(len(itens), 2, QTableWidgetItem(""))
            self.tabela_itens_compra.setItem(len(itens), 3, QTableWidgetItem(f"-{self.locale.toString(valor_abatimento, 'f', 2)}"))
            total_final = subtotal - valor_abatimento
            self.label_total_com_abatimento.setText(
                f"Total com Abatimento: R$ {self.locale.toString(total_final, 'f', 2)}"
            )
        self.atualizar_campo_texto_copiavel()

    def buscar_nome_conta_padrao(self, fornecedor_id):
        try:
            with get_cursor() as cursor:
                cursor.execute("""
                               SELECT nome_conta
                               FROM dados_bancarios_fornecedor
                               WHERE fornecedor_id = %s
                                 AND padrao = 1 LIMIT 1
                               """, (fornecedor_id,))
                row = cursor.fetchone()
                return row["nome_conta"] if row else "Conta não cadastrada"
        except mysql.connector.Error as e:
            print(f"Erro ao buscar conta padrão: {e}")
            return "Erro ao buscar conta"

    def carregar_fornecedores(self):
        self.combo_fornecedor.clear()
        self.filtro_combo_fornecedor.clear()
        self.filtro_combo_fornecedor.addItem("Todos os Fornecedores", None)
        for f in self.listar_fornecedores():
            self.combo_fornecedor.addItem("", None)
            self.combo_fornecedor.addItem(f["nome"], f["id"])
            self.filtro_combo_fornecedor.addItem(f["nome"], f["id"])

    def carregar_produtos(self):
        self.combo_produto.blockSignals(True)
        self.combo_produto.clear()
        self.combo_produto.setEditable(True)
        produtos = self.listar_produtos()
        produtos.sort(key=lambda p: p["nome"])
        for p in produtos:
            self.combo_produto.addItem(p['nome'], p['id'])
        self.combo_produto.setCurrentIndex(-1)
        self.combo_produto.blockSignals(False)

    def atualizar_item_editado(self, row, column):
        if row < 0 or row >= len(self.itens_compra):
            return

        try:
            if column == 1:  # Quantidade
                nova_qtd = int(self.tabela_itens_adicionados.item(row, 1).text())
                self.itens_compra[row]['quantidade'] = nova_qtd
            elif column == 2:  # Preço unitário
                novo_preco_str = self.tabela_itens_adicionados.item(row, 2).text().replace(',', '.')
                novo_preco = float(novo_preco_str)
                self.itens_compra[row]['preco'] = novo_preco

            qtd = self.itens_compra[row]['quantidade']
            preco = self.itens_compra[row]['preco']
            self.itens_compra[row]['total'] = qtd * preco

            self.atualizar_tabela_itens_adicionados()

        except Exception:
            QMessageBox.warning(self, "Erro", "Valor inválido. Digite um número válido.")

    def set_janela_debitos(self, janela_debitos):
        self.janela_debitos = janela_debitos

    def exportar_compra_pdf(self):
        linha = self.tabela_compras_aberto.currentRow()
        if linha < 0:
            QMessageBox.warning(self, "Exportar PDF", "Selecione uma compra na tabela para exportar.")
            return

        compra_id_item = self.tabela_compras_aberto.item(linha, 0)
        if not compra_id_item:
            return

        compra_id = int(compra_id_item.text())

        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT f.id   as fornecedor_id,
                                  f.nome AS fornecedor,
                                  f.fornecedores_numerobalanca,
                                  c.data_compra,
                                  c.valor_abatimento
                           FROM compras c
                                    JOIN fornecedores f ON c.fornecedor_id = f.id
                           WHERE c.id = %s
                           """, (compra_id,))
            compra = cursor.fetchone()

            cursor.execute("""
                           SELECT p.nome                            AS produto_nome,
                                  i.quantidade,
                                  i.preco_unitario,
                                  (i.quantidade * i.preco_unitario) AS total
                           FROM itens_compra i
                                    JOIN produtos p ON i.produto_id = p.id
                           WHERE i.compra_id = %s
                           """, (compra_id,))
            itens = cursor.fetchall()

        if not compra:
            QMessageBox.warning(self, "Exportar PDF", "Compra não encontrada.")
            return

        # Saldo do fornecedor
        saldo = self.obter_saldo_devedor_fornecedor(compra['fornecedor_id'])

        filename = f"compra_{compra_id}.pdf"
        c = canvas.Canvas(filename, pagesize=A4)
        width, height = A4

        y = height - 30 * mm
        c.setFont("Helvetica-Bold", 14)
        c.drawString(20 * mm, y, f"Compra ID: {compra_id}")
        y -= 8 * mm
        c.setFont("Helvetica", 12)
        c.drawString(20 * mm, y, f"Fornecedor: {compra['fornecedor']}")
        y -= 6 * mm
        c.drawString(20 * mm, y, f"Data da Compra: {compra['data_compra'].strftime('%d/%m/%Y')}")
        y -= 10 * mm

        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, y, "Produtos")

        y -= 6 * mm
        c.setFont("Helvetica-Bold", 11)
        c.drawString(20 * mm, y, "Produto")
        c.drawString(90 * mm, y, "Qtd")
        c.drawString(110 * mm, y, "Unitário")
        c.drawString(140 * mm, y, "Total")

        altura_cabecalho = 6 * mm
        y_linha_cabecalho = y - 2 * mm
        c.line(20 * mm, y_linha_cabecalho, 190 * mm, y_linha_cabecalho)

        y -= 8 * mm
        altura_linha = 6 * mm

        altura_tabela = altura_linha * (len(itens) + (1 if float(compra['valor_abatimento']) != 0 else 0))
        x_inicio = 20 * mm
        x_fim = 190 * mm
        y_topo = y
        self.adicionar_marca_dagua_pdf_area(
            c,
            texto=str(compra['fornecedores_numerobalanca']),
            x_inicio=x_inicio,
            x_fim=x_fim,
            y_topo=y_topo,
            altura=altura_tabela,
            tamanho_fonte=30,
            cor=(0.8, 0.8, 0.8),
            angulo=25
        )

        total = 0
        for item in itens:
            if y < 30 * mm:
                c.showPage()
                y = height - 30 * mm
            c.setFont("Helvetica", 11)
            c.drawString(20 * mm, y, item['produto_nome'])
            c.drawString(90 * mm, y, str(item['quantidade']))
            c.drawString(110 * mm, y, f"R$ {item['preco_unitario']:.2f}")
            c.drawString(140 * mm, y, f"R$ {item['total']:.2f}")
            total += float(item['total'])
            y -= altura_linha

        # Mostrar abatimento/adiantamento na tabela
        if float(compra['valor_abatimento']) != 0:
            c.setFont("Helvetica-Oblique", 11)
            c.drawString(20 * mm, y, "Abatimento/Adiantamento")
            c.drawString(140 * mm, y, f"- R$ {compra['valor_abatimento']:.2f}")
            y -= altura_linha

        y_linha_final = y + altura_linha / 2
        c.line(20 * mm, y_linha_final, 190 * mm, y_linha_final)

        y -= 10 * mm
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, y, f"Subtotal: R$ {total:.2f}")
        y -= 6 * mm
        total_com_abatimento = total - float(compra['valor_abatimento'])
        c.drawString(20 * mm, y, f"Total Final: R$ {total_com_abatimento:.2f}")

        # Exibir saldo do fornecedor ao final
        y -= 10 * mm
        c.setFont("Helvetica-Bold", 11)
        if saldo <= 0:
            c.drawString(20 * mm, y, f"Saldo positivo do fornecedor: R$ {-saldo:.2f}")
        else:
            c.drawString(20 * mm, y, f"Saldo devedor do fornecedor: R$ {abs(saldo):.2f}")

        y -= 20 * mm
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(20 * mm, y, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

        c.save()

        QMessageBox.information(self, "Exportar PDF", f"PDF gerado com sucesso:\n{filename}")

        if platform.system() == "Windows":
            os.startfile(filename)
        elif platform.system() == "Darwin":
            os.system(f"open '{filename}'")
        else:
            os.system(f"xdg-open '{filename}'")

    def adicionar_marca_dagua_pdf_area(self, c, texto, x_inicio, x_fim, y_topo, altura, tamanho_fonte=30, cor=(0.8, 0.8, 0.8), angulo=25):
        try:
            pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'))
            fonte_nome = 'Arial'
        except:
            fonte_nome = 'Helvetica'
        c.saveState()
        c.setFont(fonte_nome, tamanho_fonte)
        c.setFillColor(Color(*cor))

        largura_texto = pdfmetrics.stringWidth(texto, fonte_nome, tamanho_fonte)
        step_x = largura_texto + 40
        step_y = tamanho_fonte * 2

        y = y_topo
        while y > y_topo - altura:
            x = x_inicio
            while x < x_fim:
                c.saveState()
                c.translate(x, y)
                c.rotate(angulo)
                c.drawString(0, 0, texto)
                c.restoreState()
                x += step_x
            y -= step_y
        c.restoreState()

    def exportar_compra_jpg(self):
        compra_id = self.obter_compra_id_selecionado()
        if compra_id is None:
            QMessageBox.warning(self, "Exportar JPG", "Selecione uma compra para exportar.")
            return

        compra, itens = self.obter_detalhes_compra(compra_id)
        if not compra:
            QMessageBox.warning(self, "Exportar JPG", "Compra não encontrada.")
            return

        # Obter saldo do fornecedor
        saldo = self.obter_saldo_devedor_fornecedor(compra['fornecedor_id'])

        largura, altura = 800, 600 + (len(itens) + 1) * 25  # +1 para abatimento se houver
        imagem = Image.new("RGB", (largura, altura), "white")
        draw = ImageDraw.Draw(imagem)

        try:
            fonte = ImageFont.truetype("arial.ttf", 16)
            fonte_bold = ImageFont.truetype("arialbd.ttf", 18)
            fonte_mono = ImageFont.truetype("arial.ttf", 14)
        except IOError:
            fonte = fonte_bold = fonte_mono = ImageFont.load_default()

        y = 20
        draw.text((30, y), f"Compra ID: {compra_id}", fill="black", font=fonte_bold)
        y += 30
        draw.text((30, y), f"Fornecedor: {compra['fornecedor']}", fill="black", font=fonte)
        y += 25
        draw.text((30, y), f"Data: {compra['data_compra'].strftime('%d/%m/%Y')}", fill="black", font=fonte)
        y += 40

        y_cabecalho = y
        draw.text((30, y_cabecalho), "Produto", fill="black", font=fonte_bold)
        draw.text((400, y_cabecalho), "Qtd", fill="black", font=fonte_bold)
        draw.text((470, y_cabecalho), "Unit.", fill="black", font=fonte_bold)
        draw.text((570, y_cabecalho), "Total", fill="black", font=fonte_bold)

        altura_cabecalho = 20
        y_linha_cabecalho = y_cabecalho + altura_cabecalho
        draw.line((30, y_linha_cabecalho, 750, y_linha_cabecalho), fill="black", width=1)

        y = y_linha_cabecalho + 10
        altura_linha = 25
        colunas_x = [30, 400, 470, 570, 750]

        total = 0
        for item in itens:
            draw.text((30, y), item['produto_nome'], fill="black", font=fonte_mono)
            draw.text((400, y), str(item['quantidade']), fill="black", font=fonte_mono)
            draw.text((470, y), f"{item['preco_unitario']:.2f}", fill="black", font=fonte_mono)
            draw.text((570, y), f"{item['total']:.2f}", fill="black", font=fonte_mono)
            total += float(item['total'])
            y += altura_linha

        # Adiciona linha de abatimento/adiantamento na tabela, se houver
        if float(compra['valor_abatimento']) != 0:
            draw.text((30, y), "Abatimento/Adiantamento", fill="black", font=fonte_mono)
            draw.text((570, y), f"-{float(compra['valor_abatimento']):.2f}", fill="black", font=fonte_mono)
            y += altura_linha

        y_tabela_fim = y + 30
        linhas_y = [y_linha_cabecalho]
        linhas_y += [y_linha_cabecalho + 25 + i * altura_linha for i in
                     range(len(itens) + (1 if float(compra['valor_abatimento']) != 0 else 0) + 1)]

        for linha_y in linhas_y:
            draw.line((colunas_x[0], linha_y, colunas_x[-1], linha_y), fill="black", width=1)
        for x in colunas_x:
            draw.line((x, linhas_y[0], x, linhas_y[-1]), fill="black", width=1)

        y = y_tabela_fim
        draw.text((30, y), f"Subtotal: R$ {total:.2f}", fill="black", font=fonte_bold)
        y += 25
        total_com_abatimento = total - float(compra['valor_abatimento'])
        draw.text((30, y), f"Total Final: R$ {total_com_abatimento:.2f}", fill="black", font=fonte_bold)
        y += 25

        # Saldo do fornecedor ao final
        if saldo <= 0:
            draw.text((30, y), f"Saldo positivo do fornecedor: R$ {-saldo:.2f}", fill="black", font=fonte_bold)
        else:
            draw.text((30, y), f"Saldo devedor do fornecedor: R$ {abs(saldo):.2f}", fill="black", font=fonte_bold)
        y += 40

        draw.text((30, y), f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", fill="gray", font=fonte)

        # Marca d'água na área da tabela
        imagem = self.adicionar_marca_dagua_area(
            imagem,
            texto=str(compra['fornecedores_numerobalanca']),
            x_inicio=30,
            x_fim=750,
            y_inicio=y_linha_cabecalho,
            altura=altura_linha * (len(itens) + (1 if float(compra['valor_abatimento']) != 0 else 0)),
            fonte_path="arial.ttf",
            tamanho_fonte=30,
            opacidade=80,
            angulo=25
        )

        nome_arquivo = f"compra_{compra_id}.jpg"
        imagem.save(nome_arquivo)

        QMessageBox.information(self, "Exportar JPG", f"Relatório gerado com sucesso:\n{nome_arquivo}")

        if platform.system() == "Windows":
            os.startfile(nome_arquivo)
        elif platform.system() == "Darwin":
            os.system(f"open '{nome_arquivo}'")
        else:
            os.system(f"xdg-open '{nome_arquivo}'")

    def adicionar_marca_dagua_area(self, imagem, texto, x_inicio, x_fim, y_inicio, altura, fonte_path="arial.ttf", tamanho_fonte=30, opacidade=80, angulo=25):
        try:
            fonte = ImageFont.truetype(fonte_path, tamanho_fonte)
        except IOError:
            fonte = ImageFont.load_default()
        marca = Image.new("RGBA", imagem.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(marca)

        bbox = draw.textbbox((0, 0), texto, font=fonte)
        texto_largura = bbox[2] - bbox[0]
        texto_altura = bbox[3] - bbox[1]

        step_x = texto_largura + 40
        step_y = tamanho_fonte * 2

        for y in range(int(y_inicio), int(y_inicio + altura), int(step_y)):
            for x in range(int(x_inicio), int(x_fim), int(step_x)):
                txt_img = Image.new("RGBA", (texto_largura + 20, texto_altura + 20), (255, 255, 255, 0))
                txt_draw = ImageDraw.Draw(txt_img)
                txt_draw.text((10, 10), texto, font=fonte, fill=(200, 200, 200, opacidade))
                txt_img = txt_img.rotate(angulo, expand=1, resample=Image.BICUBIC)
                px = int(x)
                py = int(y)
                marca.alpha_composite(txt_img, (px, py))
        resultado = Image.alpha_composite(imagem.convert("RGBA"), marca)
        return resultado.convert("RGB")

    def selecionar_categoria_do_fornecedor(self, fornecedor_id):
        with get_cursor() as cursor:
            cursor.execute("SELECT id FROM categorias_fornecedor_por_fornecedor WHERE fornecedor_id = %s ORDER BY nome", (fornecedor_id,))
            result = cursor.fetchone()
            if result:
                categoria_id = result["id"]
                index = self.combo_categoria_temporaria.findData(categoria_id)
                if index != -1:
                    self.combo_categoria_temporaria.setCurrentIndex(index)
            else:
                cursor.execute("SELECT id FROM categorias_fornecedor_por_fornecedor WHERE nome = %s LIMIT 1", ('Padrão',))
                cat_padrao = cursor.fetchone()
                if cat_padrao:
                    index = self.combo_categoria_temporaria.findData(cat_padrao["id"])
                    if index != -1:
                        self.combo_categoria_temporaria.setCurrentIndex(index)

    def showEvent(self, event):
        super().showEvent(event)
        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id is not None:
            self.carregar_categorias_para_fornecedor(fornecedor_id)
            self.atualizar_saldo_fornecedor()

if __name__ == "__main__":
    app = QApplication([])
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    window = ComprasUI()
    window.resize(1200, 600)
    window.show()
    sys.exit(app.exec())