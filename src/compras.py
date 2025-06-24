import sys
import mysql.connector
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QComboBox, QDateEdit, QLineEdit,
    QSpinBox, QTableWidget, QTableWidgetItem, QMessageBox
)
from PySide6.QtCore import QTimer, QDate, QLocale
from db_context import get_cursor
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import black, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os, platform

class ComprasUI(QWidget):
    def __init__(self):
        super().__init__()
        self.itens_compra = []
        self.item_edit_index = None
        self.compra_edit_id = None
        self.locale = QLocale(QLocale.Portuguese, QLocale.Brazil)
        self.init_ui()

    # ---- Métodos DB ----

    def listar_fornecedores(self):
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT id, nome FROM fornecedores ORDER BY nome
            """)
            return cursor.fetchall()

    def listar_produtos(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome, preco_base FROM produtos ORDER BY nome")
            return cursor.fetchall()

    def obter_produto(self, produto_id):
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome, preco_base FROM produtos WHERE id = %s", (produto_id,))
            return cursor.fetchone()

    def listar_compras(self):
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT c.id, c.data_compra AS data, c.valor_abatimento, c.total, f.nome AS fornecedor_nome
                FROM compras c
                JOIN fornecedores f ON c.fornecedor_id = f.id
                ORDER BY c.data_compra DESC
            """)
            return cursor.fetchall()

    def adicionar_compra(self, fornecedor_id, data_compra, valor_abatimento, itens_compra):
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO compras (fornecedor_id, data_compra, valor_abatimento) VALUES (%s, %s, %s)",
                (fornecedor_id, data_compra, valor_abatimento)
            )
            compra_id = cursor.lastrowid

            for item in itens_compra:
                cursor.execute(
                    "INSERT INTO itens_compra (compra_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)",
                    (compra_id, item['produto_id'], item['quantidade'], item['preco'])
                )

            cursor.execute("""
                UPDATE compras
                SET total = (
                    SELECT SUM(quantidade * preco_unitario)
                    FROM itens_compra
                    WHERE compra_id = %s
                )
                WHERE id = %s
            """, (compra_id, compra_id))

        return compra_id

    def atualizar_compra(self, compra_id, fornecedor_id, data_compra, valor_abatimento, itens_compra):
        with get_cursor(commit=True) as cursor:
            cursor.execute("""
                UPDATE compras
                SET fornecedor_id=%s, data_compra=%s, valor_abatimento=%s
                WHERE id=%s
            """, (fornecedor_id, data_compra, valor_abatimento, compra_id))

            cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))

            for item in itens_compra:
                cursor.execute(
                    "INSERT INTO itens_compra (compra_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)",
                    (compra_id, item['produto_id'], item['quantidade'], item['preco'])
                )

            cursor.execute("""
                UPDATE compras
                SET total = (
                    SELECT SUM(quantidade * preco_unitario)
                    FROM itens_compra
                    WHERE compra_id = %s
                )
                WHERE id = %s
            """, (compra_id, compra_id))

    def listar_itens_compra(self, compra_id):
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT p.nome AS produto_nome, i.produto_id, i.quantidade, i.preco_unitario, (i.quantidade * i.preco_unitario) AS total
                FROM itens_compra i
                JOIN produtos p ON i.produto_id = p.id
                WHERE i.compra_id = %s
            """, (compra_id,))
            return cursor.fetchall()

    def obter_compra_id_selecionado(self):
        linha = self.tabela_compras.currentRow()
        if linha < 0:
            return None
        item = self.tabela_compras.item(linha, 0)
        return int(item.text()) if item else None

    def obter_detalhes_compra(self, compra_id):
        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT f.nome AS fornecedor,
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
        self.setWindowTitle("Registro de Compras")
        layout_principal = QHBoxLayout()

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
        layout_dados.addWidget(QLabel("Data da Compra"), 2, 0)
        layout_dados.addWidget(self.input_data, 2, 1)

        self.combo_categoria_temporaria = QComboBox()
        self.combo_categoria_temporaria.addItem("Selecione uma categoria", 0)
        layout_dados.addWidget(QLabel("Categoria (para esta compra)"), 3, 0)
        layout_dados.addWidget(self.combo_categoria_temporaria, 3, 1)

        self.input_abatimento = QLineEdit()
        layout_dados.addWidget(QLabel("Abatimento"), 4, 0)
        layout_dados.addWidget(self.input_abatimento, 4, 1)

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

        layout_compras_com_filtros = QVBoxLayout()
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

        self.tabela_compras = QTableWidget()
        self.tabela_compras.setColumnCount(4)
        self.tabela_compras.setHorizontalHeaderLabels(["ID", "Fornecedor", "Data", "Total"])
        self.tabela_compras.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_compras.cellClicked.connect(self.mostrar_itens_da_compra)
        layout_compras_com_filtros.addWidget(self.tabela_compras)

        layout_direita = QVBoxLayout()
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

        self.btn_exportar_pdf = QPushButton("Exportar PDF")
        self.btn_exportar_pdf.clicked.connect(self.exportar_compra_pdf)
        layout_direita.addWidget(self.btn_exportar_pdf)

        self.btn_exportar_jpg = QPushButton("Exportar JPG")
        self.btn_exportar_jpg.clicked.connect(self.exportar_compra_jpg)
        layout_direita.addWidget(self.btn_exportar_jpg)

        layout_principal.addLayout(layout_entrada, 3)
        layout_principal.addLayout(layout_compras_com_filtros, 3)
        layout_principal.addLayout(layout_direita, 3)

        self.setLayout(layout_principal)
        self.carregar_dados()
        self.itens_compra = []
        self.atualizar_tabela_itens_adicionados()

    def carregar_dados(self):
        self.atualizar_tabela_compras()
        self.combo_produto.blockSignals(True)
        self.combo_produto.clear()
        for p in self.listar_produtos():
            self.combo_produto.addItem(p['nome'], p['id'])
        self.combo_produto.setCurrentIndex(-1)
        self.combo_produto.blockSignals(False)
        self.atualizar_tabela_compras()

    def zerar_quantidade(self):
        self.input_quantidade.setValue(1)

    def copiar_campo_texto_copiavel(self, event):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.campo_texto_copiavel.text())
        # Muda cor de fundo rapidamente (verde claro)
        self.campo_texto_copiavel.setStyleSheet("background-color: #b2f2b4; font-weight: bold; font-size: 13px;")
        QTimer.singleShot(350, lambda: self.campo_texto_copiavel.setStyleSheet("font-weight: bold; font-size: 13px;"))
        # Chama o evento padrão para manter o foco
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

        ajuste_fixo = float(ajuste["ajuste_fixo"]) if ajuste else 0.0

        preco = float(produto["preco_base"]) + float(ajuste_fixo)
        total = quantidade * preco

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

    def finalizar_compra(self):
        if not self.itens_compra:
            QMessageBox.warning(self, "Erro", "Adicione pelo menos um item antes de finalizar.")
            return
        fornecedor_id = self.combo_fornecedor.currentData()
        data_compra = self.input_data.date().toPython()
        try:
            valor_abatimento = float(self.input_abatimento.text().replace(',', '.')) if self.input_abatimento.text() else 0.0
        except ValueError:
            QMessageBox.warning(self, "Erro", "Valor de abatimento inválido.")
            return

        if self.compra_edit_id is None:
            self.adicionar_compra(fornecedor_id, data_compra, valor_abatimento, self.itens_compra)
            QMessageBox.information(self, "Sucesso", "Compra cadastrada com sucesso.")
        else:
            self.atualizar_compra(self.compra_edit_id, fornecedor_id, data_compra, valor_abatimento, self.itens_compra)
            QMessageBox.information(self, "Sucesso", "Compra atualizada com sucesso.")
            self.compra_edit_id = None

        self.limpar_campos()
        self.atualizar_tabela_compras()
        self.limpar_itens()
        if hasattr(self, 'janela_debitos'):
            self.janela_debitos.atualizar()

    def atualizar_tabela_compras(self):
        compras = self.listar_compras()
        self.tabela_compras.setRowCount(len(compras))
        for i, c in enumerate(compras):
            self.tabela_compras.setItem(i, 0, QTableWidgetItem(str(c['id'])))
            self.tabela_compras.setItem(i, 1, QTableWidgetItem(c['fornecedor_nome']))
            self.tabela_compras.setItem(i, 2, QTableWidgetItem(str(c['data'])))
            total_formatado = self.locale.toString(float(c['total']), 'f', 2)
            self.tabela_compras.setItem(i, 3, QTableWidgetItem(total_formatado))

    def mostrar_itens_da_compra(self, row, column):
        compra_id_item = self.tabela_compras.item(row, 0)
        if compra_id_item is None:
            return

        compra_id = int(compra_id_item.text())

        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT p.nome                            AS produto_nome,
                                  i.produto_id,
                                  i.quantidade,
                                  i.preco_unitario,
                                  (i.quantidade * i.preco_unitario) AS total
                           FROM itens_compra i
                                    JOIN produtos p ON i.produto_id = p.id
                           WHERE i.compra_id = %s
                           """, (compra_id,))
            itens = cursor.fetchall()

            cursor.execute("SELECT valor_abatimento FROM compras WHERE id = %s", (compra_id,))
            compra = cursor.fetchone()

        valor_abatimento = float(compra["valor_abatimento"]) if compra else 0.0
        subtotal = float(sum(item["total"] for item in itens))
        total_final = subtotal - valor_abatimento
        self.tabela_itens_compra.setRowCount(len(itens) + 1)
        for i, item in enumerate(itens):
            self.tabela_itens_compra.setItem(i, 0, QTableWidgetItem(item['produto_nome']))
            self.tabela_itens_compra.setItem(i, 1, QTableWidgetItem(str(item['quantidade'])))
            preco_formatado = self.locale.toString(float(item['preco_unitario']), 'f', 2)
            total_formatado = self.locale.toString(float(item['total']), 'f', 2)
            self.tabela_itens_compra.setItem(i, 2, QTableWidgetItem(preco_formatado))
            self.tabela_itens_compra.setItem(i, 3, QTableWidgetItem(total_formatado))

        self.tabela_itens_compra.setItem(len(itens), 0, QTableWidgetItem("Abatimento"))
        self.tabela_itens_compra.setItem(len(itens), 1, QTableWidgetItem(""))
        self.tabela_itens_compra.setItem(len(itens), 2, QTableWidgetItem(""))
        self.tabela_itens_compra.setItem(len(itens), 3, QTableWidgetItem(f"-{self.locale.toString(valor_abatimento, 'f', 2)}"))

        self.label_total_com_abatimento.setText(
            f"Total com Abatimento: R$ {self.locale.toString(total_final, 'f', 2)}"
        )

        with get_cursor() as cursor:
            cursor.execute("SELECT fornecedor_id FROM compras WHERE id = %s", (compra_id,))
            compra_info = cursor.fetchone()

        if compra_info:
            fornecedor_id = compra_info["fornecedor_id"]
            nome_conta = self.buscar_nome_conta_padrao(fornecedor_id)
            texto_copiavel = f"{nome_conta} - R$ {self.locale.toString(total_final, 'f', 2)}"
            self.campo_texto_copiavel.setText(texto_copiavel)
            self.campo_texto_copiavel.setStyleSheet("color: black; font-weight: bold; font-size: 13px;")
        else:
            self.campo_texto_copiavel.setText("Conta não encontrada")
            self.campo_texto_copiavel.setStyleSheet("color: red; font-weight: bold; font-size: 13px;")


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

    def editar_compra_finalizada(self):
        linha = self.tabela_compras.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Editar Compra", "Selecione uma compra para editar.")
            return
        compra_id_item = self.tabela_compras.item(linha, 0)
        if compra_id_item is None:
            return
        compra_id = int(compra_id_item.text())

        with get_cursor() as cursor:
            cursor.execute("""
                SELECT fornecedor_id, data_compra, valor_abatimento
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

        if compra is None:
            QMessageBox.warning(self, "Erro", "Compra não encontrada.")
            return

        idx_fornecedor = self.combo_fornecedor.findData(compra['fornecedor_id'])
        self.combo_fornecedor.setCurrentIndex(idx_fornecedor if idx_fornecedor >= 0 else 0)
        self.input_data.setDate(QDate(compra['data_compra']))
        self.input_abatimento.setText(str(compra['valor_abatimento']))

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

    def excluir_compra_finalizada(self):
        linha = self.tabela_compras.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Excluir Compra", "Selecione uma compra para excluir.")
            return

        compra_id_item = self.tabela_compras.item(linha, 0)
        if compra_id_item is None:
            return

        compra_id = int(compra_id_item.text())

        confirm = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            f"Tem certeza que deseja excluir a compra ID {compra_id}?",
            QMessageBox.Yes | QMessageBox.No
        )

        if confirm == QMessageBox.Yes:
            try:
                with get_cursor(commit=True) as cursor:
                    cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))
                    cursor.execute("DELETE FROM compras WHERE id = %s", (compra_id,))

                QMessageBox.information(self, "Sucesso", "Compra excluída com sucesso.")
                self.atualizar_tabela_compras()
                self.tabela_itens_compra.setRowCount(0)
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao excluir compra: {e}")

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
        self.input_abatimento.clear()
        self.combo_produto.setCurrentIndex(-1)
        self.input_quantidade.setValue(1)
        self.item_edit_index = None
        self.compra_edit_id = None

    def acao_cancelar(self):
        self.limpar_campos()
        self.limpar_itens()

    def aplicar_filtro_compras(self):
        fornecedor_id = self.filtro_combo_fornecedor.currentData()
        data_de = self.filtro_data_de.date().toPython()
        data_ate = self.filtro_data_ate.date().toPython()

        query = """
                SELECT c.id, c.data_compra AS data, c.valor_abatimento, c.total, f.nome AS fornecedor_nome
                FROM compras c
                         JOIN fornecedores f ON c.fornecedor_id = f.id
                WHERE c.data_compra BETWEEN %s AND %s
                """
        params = [data_de, data_ate]

        if fornecedor_id:
            query += " AND f.id = %s"
            params.append(fornecedor_id)

        query += " ORDER BY c.data_compra DESC"

        with get_cursor() as cursor:
            cursor.execute(query, params)
            compras = cursor.fetchall()

        self.tabela_compras.setRowCount(len(compras))
        for i, c in enumerate(compras):
            self.tabela_compras.setItem(i, 0, QTableWidgetItem(str(c['id'])))
            self.tabela_compras.setItem(i, 1, QTableWidgetItem(c['fornecedor_nome']))
            self.tabela_compras.setItem(i, 2, QTableWidgetItem(str(c['data'])))
            self.tabela_compras.setItem(i, 3, QTableWidgetItem(f"{c['total']:.2f}"))

    def limpar_filtro_compras(self):
        self.filtro_combo_fornecedor.setCurrentIndex(0)
        self.filtro_data_de.setDate(QDate.currentDate().addMonths(-1))
        self.filtro_data_ate.setDate(QDate.currentDate())
        self.atualizar_tabela_compras()

    def carregar_fornecedores(self):
        self.combo_fornecedor.clear()
        self.filtro_combo_fornecedor.clear()
        self.filtro_combo_fornecedor.addItem("Todos os Fornecedores", None)
        for f in self.listar_fornecedores():
            # Só nome, sem ID
            self.combo_fornecedor.addItem(f["nome"], f["id"])
            self.filtro_combo_fornecedor.addItem(f["nome"], f["id"])

    def carregar_produtos(self):
        self.combo_produto.blockSignals(True)
        self.combo_produto.clear()
        self.combo_produto.setEditable(True)  # Permite digitação!
        produtos = self.listar_produtos()
        # Garantir ordenação alfabética se vier de outro métod
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
        linha = self.tabela_compras.currentRow()
        if linha < 0:
            QMessageBox.warning(self, "Exportar PDF", "Selecione uma compra na tabela para exportar.")
            return

        compra_id_item = self.tabela_compras.item(linha, 0)
        if not compra_id_item:
            return

        compra_id = int(compra_id_item.text())

        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT f.nome AS fornecedor, f.fornecedores_numerobalanca, c.data_compra, c.valor_abatimento
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

        altura_tabela = altura_linha * len(itens)
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

        y_linha_final = y + altura_linha / 2
        c.line(20 * mm, y_linha_final, 190 * mm, y_linha_final)

        y -= 10 * mm
        c.setFont("Helvetica-Bold", 12)
        c.drawString(20 * mm, y, f"Subtotal: R$ {total:.2f}")
        y -= 6 * mm
        c.drawString(20 * mm, y, f"Abatimento: R$ {compra['valor_abatimento']:.2f}")
        y -= 6 * mm
        total_com_abatimento = total - float(compra['valor_abatimento'])
        c.drawString(20 * mm, y, f"Total Final: R$ {total_com_abatimento:.2f}")

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

        largura, altura = 800, 600 + len(itens) * 25
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

        y_tabela_fim = y + 30
        linhas_y = [y_linha_cabecalho]
        linhas_y += [y_linha_cabecalho + 25 + i * altura_linha for i in range(len(itens) + 1)]

        for linha_y in linhas_y:
            draw.line((colunas_x[0], linha_y, colunas_x[-1], linha_y), fill="black", width=1)
        for x in colunas_x:
            draw.line((x, linhas_y[0], x, linhas_y[-1]), fill="black", width=1)

        y = y_tabela_fim
        draw.text((30, y), f"Subtotal: R$ {total:.2f}", fill="black", font=fonte_bold)
        y += 25
        draw.text((30, y), f"Abatimento: R$ {compra['valor_abatimento']:.2f}", fill="black", font=fonte_bold)
        y += 25
        draw.text((30, y), f"Total Final: R$ {total - float(compra['valor_abatimento']):.2f}", fill="black", font=fonte_bold)

        y += 40
        draw.text((30, y), f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", fill="gray", font=fonte)

        # Marca d'água na área da tabela
        imagem = self.adicionar_marca_dagua_area(
            imagem,
            texto=str(compra['fornecedores_numerobalanca']),
            x_inicio=30,
            x_fim=750,
            y_inicio=y_linha_cabecalho,
            altura=altura_linha*len(itens),
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
        self.carregar_fornecedores()
        self.carregar_produtos()
        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id is not None:
            self.carregar_categorias_para_fornecedor(fornecedor_id)

if __name__ == "__main__":
    app = QApplication([])
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    window = ComprasUI()
    window.resize(1200, 600)
    window.show()
    sys.exit(app.exec())