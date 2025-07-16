# Requisitos: pip install PySide6 mysql-connector-python

import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QHBoxLayout,
    QComboBox, QGridLayout, QInputDialog, QDialog, QDialogButtonBox, QFormLayout,
    QDoubleSpinBox, QSizePolicy, QHeaderView, QSplitter
)
from PySide6.QtCore import Qt, QLocale
from PySide6.QtGui import QIntValidator
from db_context import get_cursor
from threads_utils import WorkerThread
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Table, TableStyle, Paragraph
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import os
import tempfile
import subprocess
import platform
from compras.compras_db import listar_fornecedores_cached, listar_categorias_do_fornecedor_cached
from compras.compras import get_fornecedores_cache, get_categorias_fornecedor_cache
from movimentacoes_db import obter_categoria_principal_cached

def abrir_arquivo(caminho):
    """Abre arquivo PDF ou imagem com programa padrão do SO."""
    if platform.system() == "Windows":
        os.startfile(caminho)
    elif platform.system() == "Darwin":
        subprocess.call(("open", caminho))
    else:
        subprocess.call(("xdg-open", caminho))

class DB:
    def listar_fornecedores(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT * FROM fornecedores ORDER BY nome")
            return cursor.fetchall()

    def listar_categorias_do_fornecedor(self, fornecedor_id):
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT id, nome FROM categorias_fornecedor_por_fornecedor 
                WHERE fornecedor_id = %s ORDER BY nome
            """, (fornecedor_id,))
            return cursor.fetchall()

    def adicionar_fornecedor(self, nome, endereco, numero_balanca):
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO fornecedores (nome, fornecedores_endereco, fornecedores_numerobalanca) VALUES (%s, %s, %s)",
                (nome, endereco, numero_balanca)
            )
        listar_fornecedores_cached.cache_clear()
        get_fornecedores_cache.cache_clear()

    def excluir_fornecedor(self, fornecedor_id):
        with get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM fornecedores WHERE id = %s", (fornecedor_id,))

    def atualizar_fornecedor(self, fornecedor_id, nome, endereco, numero_balanca):
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE fornecedores SET nome=%s, fornecedores_endereco=%s, fornecedores_numerobalanca=%s WHERE id=%s",
                (nome, endereco, numero_balanca, fornecedor_id)
            )
        listar_fornecedores_cached.cache_clear()
        get_fornecedores_cache.cache_clear()

    def listar_precos_por_categoria(self, categoria_id):
        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT p.id,
                                  p.nome,
                                  p.preco_base,
                                  COALESCE(aj.ajuste_fixo, 0)                  AS ajuste_fixo,
                                  (p.preco_base + COALESCE(aj.ajuste_fixo, 0)) AS preco_final
                           FROM produtos p
                                    LEFT JOIN ajustes_fixos_produto_fornecedor_categoria aj
                                              ON p.id = aj.produto_id AND aj.categoria_id = %s
                           ORDER BY p.nome
                           """, (categoria_id,))
            return cursor.fetchall()

    def adicionar_categoria_para_fornecedor(self, fornecedor_id, nome_categoria):
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO categorias_fornecedor_por_fornecedor (fornecedor_id, nome) VALUES (%s, %s)",
                (fornecedor_id, nome_categoria)
            )
            cursor.execute("SELECT LAST_INSERT_ID() as cid")
            return cursor.fetchone()['cid']

    def listar_produtos(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome FROM produtos ORDER BY nome")
            return cursor.fetchall()

    def inserir_ajustes_categoria(self, categoria_id, ajustes: dict):
        # ajustes: {produto_id: ajuste_fixo}
        if not ajustes:
            return
        with get_cursor(commit=True) as cursor:
            for produto_id, ajuste in ajustes.items():
                cursor.execute(
                    "INSERT INTO ajustes_fixos_produto_fornecedor_categoria (produto_id, categoria_id, ajuste_fixo) VALUES (%s, %s, %s)",
                    (produto_id, categoria_id, ajuste)
                )

    def atualizar_ajuste_fixo(self, produto_id, categoria_id, ajuste_fixo):
        with get_cursor(commit=True) as cursor:
            cursor.execute("""
                INSERT INTO ajustes_fixos_produto_fornecedor_categoria (produto_id, categoria_id, ajuste_fixo)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE ajuste_fixo = VALUES(ajuste_fixo)
            """, (produto_id, categoria_id, ajuste_fixo))

class DialogNovaCategoria(QDialog):
    def __init__(self, produtos, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nova Categoria")
        self.produtos = produtos  # lista de dicts
        self.ajustes = {}
        self.nome_categoria = ""

        self.layout = QVBoxLayout(self)

        # Campo nome categoria
        self.input_nome = QLineEdit()
        self.layout.addWidget(QLabel("Nome da nova categoria:"))
        self.layout.addWidget(self.input_nome)

        # Lista de produtos e campos de ajuste
        self.form_produtos = QFormLayout()
        self.inputs_ajustes = {}
        for prod in produtos:
            spin = QDoubleSpinBox()
            spin.setDecimals(2)
            spin.setMinimum(-9999.99)
            spin.setMaximum(99999.99)
            spin.setValue(0.00)
            spin.setSingleStep(0.05)  # <-- Esta linha faz o passo ser de 0,05
            self.inputs_ajustes[prod['id']] = spin
            self.form_produtos.addRow(prod['nome'], spin)
        self.layout.addLayout(self.form_produtos)

        # Botões
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def get_dados(self):
        self.nome_categoria = self.input_nome.text().strip()
        self.ajustes = {
            pid: spin.value()
            for pid, spin in self.inputs_ajustes.items()
            if spin.value() != 0.00
        }
        return self.nome_categoria, self.ajustes

class FornecedoresUI(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DB()
        self.fornecedores = []
        self.fornecedores_exibidos = []
        self.categorias_do_fornecedor = []
        self.editando_ajuste = False  # Para bloquear recursão no slot de edição
        self._em_linha_selecionada = False  # Flag para proteção
        self._carregando_categorias = False  # Flag de carregamento
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Gestão de Fornecedores')

        self.criar_widgets()
        self.configurar_validacoes()
        self.conectar_sinais()
        self.organizar_layouts()

        self.atualizar_tabela()
        #self.carregar_combo_fornecedores()
        self.cancelar_edicao()

    def criar_widgets(self):
        # Filtros
        self.label_filtro_nome = QLabel('Filtro Nome:')
        self.input_filtro_nome = QLineEdit()

        self.label_filtro_balanca = QLabel('Filtro Nº Balança:')
        self.input_filtro_balanca = QLineEdit()

        # Dados do fornecedor
        self.label_dropdown = QLabel('Selecionar Fornecedor')
        self.combo_fornecedores = QComboBox()

        self.label_nome = QLabel('Nome do Fornecedor')
        self.input_nome = QLineEdit()

        self.label_endereco = QLabel('Endereço')
        self.input_endereco = QLineEdit()

        self.label_numero_balanca = QLabel('Número da Balança')
        self.input_numero_balanca = QLineEdit()

        self.label_categoria = QLabel('Categoria')
        self.combo_categoria = QComboBox()

        self.btn_add_categoria = QPushButton('Adicionar Categoria')
        self.btn_editar_categoria = QPushButton('Editar Categoria')
        self.btn_excluir_categoria = QPushButton('Excluir Categoria')

        # Botões CRUD
        self.btn_adicionar = QPushButton('Adicionar')
        self.btn_atualizar = QPushButton('Atualizar')
        self.btn_excluir = QPushButton('Excluir')
        self.btn_cancelar = QPushButton('Cancelar')

        # Tabela principal
        self.tabela = QTableWidget()
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.setColumnCount(3)
        self.tabela.setHorizontalHeaderLabels(['Nº Balança', 'Nome', 'Endereço'])

        # Tabela de preços
        self.tabela_precos = QTableWidget()
        self.tabela_precos.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tabela_precos.setColumnCount(4)
        self.tabela_precos.setHorizontalHeaderLabels(['Produto', 'Preço Base', 'Ajuste Fixo', 'Preço Final'])

        # Botões de exportação
        self.btn_export_pdf = QPushButton("Exportar Tabela em PDF")
        self.btn_export_jpg = QPushButton("Exportar Tabela em JPG")

    def configurar_validacoes(self):
        self.input_filtro_balanca.setValidator(QIntValidator())
        self.input_numero_balanca.setValidator(QIntValidator())

    def conectar_sinais(self):
        self.input_filtro_nome.textChanged.connect(self.aplicar_filtro)
        self.input_filtro_balanca.textChanged.connect(self.aplicar_filtro)
        self.combo_fornecedores.currentIndexChanged.connect(self.fornecedor_selecionado)

        self.btn_adicionar.clicked.connect(self.adicionar_fornecedor)
        self.btn_atualizar.clicked.connect(self.atualizar_fornecedor_combo)
        self.btn_excluir.clicked.connect(self.excluir_fornecedor_combo)
        self.btn_cancelar.clicked.connect(self.cancelar_edicao)

        self.tabela.cellClicked.connect(self.linha_selecionada)
        self.combo_categoria.currentIndexChanged.connect(self.categoria_selecionada)
        self.btn_export_pdf.clicked.connect(self.exportar_pdf)
        self.btn_export_jpg.clicked.connect(self.exportar_jpg)
        self.btn_add_categoria.clicked.connect(self.adicionar_categoria)
        self.btn_editar_categoria.clicked.connect(self.editar_categoria)
        self.btn_excluir_categoria.clicked.connect(self.excluir_categoria)
        self.tabela_precos.itemChanged.connect(self.on_ajuste_fixo_editado)

    def organizar_layouts(self):
        # Filtros
        linha_nome = QHBoxLayout()
        linha_nome.addWidget(self.label_filtro_nome)
        linha_nome.addWidget(self.input_filtro_nome)

        linha_balanca = QHBoxLayout()
        linha_balanca.addWidget(self.label_filtro_balanca)
        linha_balanca.addWidget(self.input_filtro_balanca)

        filtro_layout = QHBoxLayout()
        filtro_layout.addLayout(linha_nome)
        filtro_layout.addLayout(linha_balanca)
        filtro_layout.addStretch()  # Empurra os filtros para a esquerda

        # PAINEL ESQUERDA (cadastro/edição)
        layout_dados = QGridLayout()
        layout_dados.addWidget(self.label_dropdown, 0, 0, 1, 2)
        layout_dados.addWidget(self.combo_fornecedores, 1, 0, 1, 2)
        layout_dados.addWidget(self.label_nome, 2, 0)
        layout_dados.addWidget(self.input_nome, 2, 1)
        layout_dados.addWidget(self.label_endereco, 3, 0)
        layout_dados.addWidget(self.input_endereco, 3, 1)
        layout_dados.addWidget(self.label_numero_balanca, 4, 0)
        layout_dados.addWidget(self.input_numero_balanca, 4, 1)
        layout_dados.addWidget(self.label_categoria, 5, 0)
        layout_dados.addWidget(self.combo_categoria, 5, 1)
        layout_dados.addWidget(self.btn_editar_categoria, 6, 0)
        layout_dados.addWidget(self.btn_add_categoria, 6, 1)
        layout_dados.addWidget(self.btn_excluir_categoria, 7, 0, 1, 2)

        layout_botoes = QHBoxLayout()
        layout_botoes.addWidget(self.btn_adicionar)
        layout_botoes.addWidget(self.btn_atualizar)
        layout_botoes.addWidget(self.btn_excluir)
        layout_botoes.addWidget(self.btn_cancelar)
        layout_botoes.addStretch()

        layout_esquerda = QVBoxLayout()
        layout_esquerda.addLayout(layout_dados)
        layout_esquerda.addLayout(layout_botoes)
        layout_esquerda.addStretch()
        widget_esquerda = QWidget()
        widget_esquerda.setLayout(layout_esquerda)

        # PAINEL CENTRAL (tabela de fornecedores + filtros)
        self.tabela.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout_central = QVBoxLayout()
        layout_central.addLayout(filtro_layout)
        layout_central.addWidget(self.tabela)
        layout_central.addStretch()
        widget_central = QWidget()
        widget_central.setLayout(layout_central)

        # PAINEL DIREITA (tabela de preços + exportação)
        self.tabela_precos.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabela_precos.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout_export = QHBoxLayout()
        layout_export.addWidget(self.btn_export_pdf)
        layout_export.addWidget(self.btn_export_jpg)
        layout_export.addStretch()
        layout_direita = QVBoxLayout()
        layout_direita.addWidget(QLabel("Tabela de Preços da Categoria"))
        layout_direita.addWidget(self.tabela_precos)
        layout_direita.addLayout(layout_export)
        layout_direita.addStretch()
        widget_direita = QWidget()
        widget_direita.setLayout(layout_direita)

        # SPLITTER COM TRÊS PAINÉIS
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(widget_esquerda)
        splitter.addWidget(widget_central)
        splitter.addWidget(widget_direita)
        splitter.setSizes([320, 600, 400])

        layout_principal = QHBoxLayout()
        layout_principal.addWidget(splitter)
        self.setLayout(layout_principal)

    def aplicar_filtro(self):
        nome_filtro = self.input_filtro_nome.text().lower()
        balanca_filtro = self.input_filtro_balanca.text()

        # Sempre filtra sobre self.fornecedores!
        if not nome_filtro and not balanca_filtro:
            filtrados = self.fornecedores
        else:
            filtrados = []
            for f in self.fornecedores:
                nome_ok = nome_filtro in f['nome'].lower()
                balanca_ok = balanca_filtro == '' or str(
                    f.get('fornecedores_numerobalanca', '') or f.get('numerobalanca', '')).startswith(balanca_filtro)
                if nome_ok and balanca_ok:
                    filtrados.append(f)

        self.fornecedores_exibidos = filtrados
        self.tabela.setRowCount(len(filtrados))
        for i, row in enumerate(filtrados):
            self.tabela.setItem(i, 0, QTableWidgetItem(
                str(row.get('fornecedores_numerobalanca', '') or row.get('numerobalanca', ''))))
            self.tabela.setItem(i, 1, QTableWidgetItem(row['nome']))
            self.tabela.setItem(i, 2, QTableWidgetItem(row.get('fornecedores_endereco', '') or row.get('endereco', '')))
        self.carregar_combo_fornecedores(filtrados)

    def atualizar_tabela(self, dados=None):
        if dados is not None:
            # Se os dados já foram fornecidos (ex: filtrados), atualiza direto na UI
            self._atualizar_tabela_ui(dados)
            return

        def tarefa_db():
            # Chama o méodo da camada DB que faz a consulta
            return self.db.listar_fornecedores()

        self.worker_tabela = WorkerThread(tarefa_db)
        self.worker_tabela.finished.connect(self._atualizar_tabela_ui)
        self.worker_tabela.erro.connect(self._mostrar_erro_thread)
        self.worker_tabela.start()

    def _atualizar_tabela_ui(self, dados):
        self.fornecedores = list(dados)
        self.fornecedores_exibidos = list(dados)
        self.tabela.setRowCount(len(dados))
        for i, row in enumerate(dados):
            self.tabela.setItem(i, 0, QTableWidgetItem(
                str(row.get('fornecedores_numerobalanca', '') or row.get('numerobalanca', ''))))
            self.tabela.setItem(i, 1, QTableWidgetItem(row['nome']))
            self.tabela.setItem(i, 2, QTableWidgetItem(row.get('fornecedores_endereco', '') or row.get('endereco', '')))

        # Chama aplicar_filtro para garantir sincronismo após atualização da tabela
        self.aplicar_filtro()

    def _mostrar_erro_thread(self, mensagem):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Erro", mensagem)

    def carregar_combo_fornecedores(self, lista=None):
        self.combo_fornecedores.clear()
        fornecedores = lista if lista is not None else self.fornecedores
        for f in fornecedores:
            self.combo_fornecedores.addItem(f['nome'], f['id'])
        if self.combo_fornecedores.count() > 0:
            self.combo_fornecedores.setCurrentIndex(0)

    def fornecedor_selecionado(self, index):
        if index < 0 or index >= len(self.fornecedores):
            self.input_nome.clear()
            self.input_endereco.clear()
            self.input_numero_balanca.clear()
            self.combo_categoria.clear()
            self.tabela_precos.setRowCount(0)
            return

        f = self.fornecedores[index]
        self.input_nome.setText(f['nome'])
        self.input_endereco.setText(f.get('fornecedores_endereco', '') or f.get('endereco', ''))
        self.input_numero_balanca.setText(str(f.get('fornecedores_numerobalanca', '') or f.get('numerobalanca', '')))
        self.carregar_categorias_do_fornecedor(f['id'])

    def carregar_categorias_do_fornecedor(self, fornecedor_id):
        # Trava para evitar múltiplos carregamentos simultâneos
        if self._carregando_categorias:
            return
        self._carregando_categorias = True
        self.tabela.setEnabled(False)  # Desabilita tabela central

        # Finaliza worker anterior se estiver rodando
        if hasattr(self, "worker_categorias") and self.worker_categorias.isRunning():
            self.worker_categorias.quit()
            self.worker_categorias.wait()

        def tarefa_db():
            categorias = self.db.listar_categorias_do_fornecedor(fornecedor_id)
            if not categorias:
                from db_context import get_cursor
                with get_cursor() as cursor:
                    cursor.execute("SELECT id, nome FROM categorias_fornecedor_por_fornecedor WHERE nome = %s LIMIT 1",
                                   ('Padrão',))
                    cat_padrao = cursor.fetchone()
                    if cat_padrao:
                        categorias = [cat_padrao]
            return categorias

        self.worker_categorias = WorkerThread(tarefa_db)
        self.worker_categorias.finished.connect(self._preencher_combo_categorias)
        self.worker_categorias.erro.connect(self._mostrar_erro_thread)
        self.worker_categorias.start()

    def _preencher_combo_categorias(self, categorias):
        self.combo_categoria.clear()
        self.categorias_do_fornecedor = categorias
        for c in categorias:
            self.combo_categoria.addItem(c['nome'], c['id'])
        self.tabela_precos.setRowCount(0)
        self.tabela.setEnabled(True)  # Habilita tabela novamente
        self._carregando_categorias = False  # Libera trava
        if self.combo_categoria.count() > 0:
            self.combo_categoria.setCurrentIndex(0)
            self.categoria_selecionada(0)
        else:
            self.tabela_precos.setRowCount(0)

    def categoria_selecionada(self, index):
        if index < 0 or index >= len(self.categorias_do_fornecedor):
            self.tabela_precos.setRowCount(0)
            return
        categoria_id = self.combo_categoria.currentData()
        self.preencher_tabela_precos(categoria_id)

    def excluir_categoria(self):
        fornecedor_idx = self.combo_fornecedores.currentIndex()
        categoria_idx = self.combo_categoria.currentIndex()
        if fornecedor_idx < 0 or categoria_idx < 0:
            QMessageBox.warning(self, "Excluir Categoria", "Selecione um fornecedor e categoria.")
            return

        categoria_nome = self.combo_categoria.currentText()
        categoria_id = self.combo_categoria.currentData()
        if categoria_nome.lower() == "padrão":
            QMessageBox.warning(self, "Excluir Categoria", "Não é permitido excluir a categoria Padrão.")
            return

        resposta = QMessageBox.question(
            self, 'Confirmar exclusão',
            f'Deseja realmente excluir a categoria "{categoria_nome}"?',
            QMessageBox.Yes | QMessageBox.No
        )
        if resposta == QMessageBox.Yes:
            try:
                with get_cursor(commit=True) as cursor:
                    cursor.execute("DELETE FROM categorias_fornecedor_por_fornecedor WHERE id = %s", (categoria_id,))
                    cursor.execute("DELETE FROM ajustes_fixos_produto_fornecedor_categoria WHERE categoria_id = %s",
                                   (categoria_id,))
                fornecedor_id = self.combo_fornecedores.currentData()
                self.carregar_categorias_do_fornecedor(fornecedor_id)
                QMessageBox.information(self, "Categoria", "Categoria excluída com sucesso.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", str(e))
        listar_categorias_do_fornecedor_cached.cache_clear()
        get_categorias_fornecedor_cache.cache_clear()
        obter_categoria_principal_cached.cache_clear()

    def editar_categoria(self):
        fornecedor_idx = self.combo_fornecedores.currentIndex()
        categoria_idx = self.combo_categoria.currentIndex()
        if fornecedor_idx < 0 or categoria_idx < 0:
            QMessageBox.warning(self, "Editar Categoria", "Selecione um fornecedor e categoria.")
            return

        categoria_nome = self.combo_categoria.currentText()
        categoria_id = self.combo_categoria.currentData()
        if categoria_nome.lower() == "padrão":
            QMessageBox.warning(self, "Editar Categoria", "Não é permitido editar a categoria Padrão.")
            return

        # Dialog para editar o nome da categoria
        novo_nome, ok = QInputDialog.getText(self, "Editar Categoria", "Novo nome para a categoria:",
                                             text=categoria_nome)
        if ok and novo_nome.strip():
            try:
                with get_cursor(commit=True) as cursor:
                    cursor.execute("UPDATE categorias_fornecedor_por_fornecedor SET nome = %s WHERE id = %s",
                                   (novo_nome.strip(), categoria_id))
                fornecedor_id = self.combo_fornecedores.currentData()
                self.carregar_categorias_do_fornecedor(fornecedor_id)
                QMessageBox.information(self, "Categoria", "Categoria atualizada com sucesso.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", str(e))
        listar_categorias_do_fornecedor_cached.cache_clear()
        get_categorias_fornecedor_cache.cache_clear()
        obter_categoria_principal_cached.cache_clear()

    def linha_selecionada(self, row, column):
        if self._em_linha_selecionada:
            return
        self._em_linha_selecionada = True
        try:
            if 0 <= row < len(self.fornecedores_exibidos):
                f = self.fornecedores_exibidos[row]
                index_combo = self.combo_fornecedores.findData(f['id'])
                if index_combo != -1:
                    self.combo_fornecedores.setCurrentIndex(index_combo)
                self.input_nome.setText(f['nome'])
                self.input_endereco.setText(f.get('fornecedores_endereco', '') or f.get('endereco', ''))
                self.input_numero_balanca.setText(
                    str(f.get('fornecedores_numerobalanca', '') or f.get('numerobalanca', '')))
                self.carregar_categorias_do_fornecedor(f['id'])
                if self.combo_categoria.count() > 0:
                    self.combo_categoria.setCurrentIndex(0)
                    self.categoria_selecionada(0)
        finally:
            self._em_linha_selecionada = False

    def preencher_tabela_precos(self, categoria_id):
        self.editando_ajuste = True
        self.tabela_precos.setRowCount(0)
        if not categoria_id:
            self.editando_ajuste = False
            return
        precos = self.db.listar_precos_por_categoria(categoria_id)
        self.tabela_precos.setRowCount(len(precos))
        for i, p in enumerate(precos):
            self.tabela_precos.setItem(i, 0, QTableWidgetItem(p['nome']))
            self.tabela_precos.setItem(i, 1, QTableWidgetItem(f"{p['preco_base']:.2f}"))
            item_ajuste = QTableWidgetItem(f"{p['ajuste_fixo']:.2f}")
            item_ajuste.setFlags(item_ajuste.flags() | Qt.ItemIsEditable)
            self.tabela_precos.setItem(i, 2, item_ajuste)
            self.tabela_precos.setItem(i, 3, QTableWidgetItem(f"{p['preco_final']:.2f}"))
        self.editando_ajuste = False

    def on_ajuste_fixo_editado(self, item):
        # Só reage se for a coluna do ajuste fixo (índice 2)
        if self.editando_ajuste or item.column() != 2:
            return
        row = item.row()
        try:
            novo_ajuste = float(item.text().replace(',', '.'))
        except ValueError:
            QMessageBox.warning(self, "Valor inválido", "Digite um número válido para o ajuste.")
            # Restaura o valor antigo
            categoria_id = self.combo_categoria.currentData()
            precos = self.db.listar_precos_por_categoria(categoria_id)
            self.tabela_precos.blockSignals(True)
            item.setText(f"{precos[row]['ajuste_fixo']:.2f}")
            self.tabela_precos.blockSignals(False)
            return

        categoria_id = self.combo_categoria.currentData()
        precos = self.db.listar_precos_por_categoria(categoria_id)
        produto_id = precos[row]['id']

        # Atualiza ou insere o ajuste fixo no banco
        self.db.atualizar_ajuste_fixo(produto_id, categoria_id, novo_ajuste)

        # Atualiza o preço final na tabela
        preco_base = float(self.tabela_precos.item(row, 1).text().replace(',', '.'))
        self.tabela_precos.blockSignals(True)
        self.tabela_precos.setItem(row, 3, QTableWidgetItem(f"{preco_base + novo_ajuste:.2f}"))
        self.tabela_precos.blockSignals(False)

    def adicionar_fornecedor(self):
        nome = self.input_nome.text().strip()
        endereco = self.input_endereco.text().strip()
        numero_balanca = self.input_numero_balanca.text().strip()

        if nome and numero_balanca:
            try:
                self.db.adicionar_fornecedor(nome, endereco, numero_balanca)
                self.cancelar_edicao()
                self.atualizar_tabela()
                self.carregar_combo_fornecedores()
                self.aplicar_filtro()
            except Exception as e:
                QMessageBox.critical(self, 'Erro', str(e))
        else:
            QMessageBox.warning(self, 'Campos obrigatórios', 'Preencha o nome e o número da balança.')

    def atualizar_fornecedor_combo(self):
        index = self.combo_fornecedores.currentIndex()
        if index >= 0:
            fornecedor_id = self.combo_fornecedores.currentData()
            nome = self.input_nome.text().strip()
            endereco = self.input_endereco.text().strip()
            numero_balanca = self.input_numero_balanca.text().strip()

            if nome and numero_balanca:
                try:
                    self.db.atualizar_fornecedor(fornecedor_id, nome, endereco, numero_balanca)
                    self.cancelar_edicao()
                    self.atualizar_tabela()
                    self.carregar_combo_fornecedores()
                    self.aplicar_filtro()
                except Exception as e:
                    QMessageBox.critical(self, 'Erro', str(e))
            else:
                QMessageBox.warning(self, 'Campos obrigatórios',
                                    'Preencha o nome e o número da balança para atualizar.')
        listar_fornecedores_cached.cache_clear()
        get_fornecedores_cache.cache_clear()

    def excluir_fornecedor_combo(self):
        index = self.combo_fornecedores.currentIndex()
        if index < 0:
            QMessageBox.warning(self, 'Seleção', 'Selecione um fornecedor para excluir.')
            return

        fornecedor_id = self.combo_fornecedores.currentData()
        resposta = QMessageBox.question(
            self, 'Confirmar exclusão',
            f'Deseja realmente excluir o fornecedor {self.combo_fornecedores.currentText()}?',
            QMessageBox.Yes | QMessageBox.No
        )
        if resposta == QMessageBox.Yes:
            try:
                self.db.excluir_fornecedor(fornecedor_id)
                self.cancelar_edicao()
                self.atualizar_tabela()
                self.carregar_combo_fornecedores()
                self.aplicar_filtro()
            except Exception as e:
                QMessageBox.critical(self, 'Erro', str(e))
        listar_fornecedores_cached.cache_clear()
        get_fornecedores_cache.cache_clear()

    def cancelar_edicao(self):
        self.combo_fornecedores.setCurrentIndex(-1)
        self.input_nome.clear()
        self.input_endereco.clear()
        self.input_numero_balanca.clear()
        self.combo_categoria.clear()
        self.input_filtro_nome.clear()
        self.input_filtro_balanca.clear()
        self.tabela_precos.setRowCount(0)

    def adicionar_categoria(self):
        fornecedor_idx = self.combo_fornecedores.currentIndex()
        if fornecedor_idx < 0:
            QMessageBox.warning(self, "Adicionar Categoria", "Selecione um fornecedor antes de criar uma categoria.")
            return
        fornecedor_id = self.combo_fornecedores.currentData()

        produtos = self.db.listar_produtos()
        dialog = DialogNovaCategoria(produtos, self)
        if dialog.exec() == QDialog.Accepted:
            nome_categoria, ajustes = dialog.get_dados()
            if not nome_categoria:
                QMessageBox.warning(self, "Categoria", "Nome da categoria não pode ser vazio.")
                return
            try:
                categoria_id = self.db.adicionar_categoria_para_fornecedor(fornecedor_id, nome_categoria)
                if ajustes:
                    self.db.inserir_ajustes_categoria(categoria_id, ajustes)
                self.carregar_categorias_do_fornecedor(fornecedor_id)
                QMessageBox.information(self, "Categoria", "Categoria e ajustes adicionados com sucesso.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", str(e))
        listar_categorias_do_fornecedor_cached.cache_clear()
        get_categorias_fornecedor_cache.cache_clear()
        obter_categoria_principal_cached.cache_clear()

    # ... [Os métodos exportar_pdf e exportar_jpg permanecem inalterados] ...

    def exportar_pdf(self):
        if hasattr(self, "worker_tabela") and self.worker_tabela.isRunning():
            self.worker_tabela.quit()
            self.worker_tabela.wait()
        fornecedor_idx = self.combo_fornecedores.currentIndex()
        categoria_idx = self.combo_categoria.currentIndex()
        if fornecedor_idx < 0 or categoria_idx < 0:
            QMessageBox.warning(self, "Exportar PDF", "Selecione um fornecedor e uma categoria para exportar a tabela.")
            return

        fornecedor = self.fornecedores[fornecedor_idx]
        nome = fornecedor['nome']
        num_balanca = str(fornecedor.get('fornecedores_numerobalanca', '') or fornecedor.get('numerobalanca', ''))
        categoria_id = self.combo_categoria.currentData()
        categoria_nome = self.combo_categoria.currentText()

        def tarefa_pdf():
            precos = self.db.listar_precos_por_categoria(categoria_id)
            precos_filtrados = [p for p in precos if (p['preco_base'] + p['ajuste_fixo']) > 0]
            if not precos_filtrados:
                return None  # Sinaliza para não abrir PDF

            arquivo_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
            c = canvas.Canvas(arquivo_pdf, pagesize=A4)
            largura, altura = A4

            margem = 2 * cm
            largura_disponivel = largura - 2 * margem
            altura_disponivel = altura - 2 * margem - 60
            linhas_por_pagina = 25
            altura_linha = 18
            dados_tabela = [["Produto", "Preço"]]
            for p in precos_filtrados:
                preco_ajustado = p['preco_base'] + p['ajuste_fixo']
                dados_tabela.append([p['nome'], f"R$ {preco_ajustado:.2f}"])
            total_linhas = len(dados_tabela) - 1
            paginas = (total_linhas + linhas_por_pagina - 1) // linhas_por_pagina
            for pagina in range(paginas):
                c.setFont("Helvetica-Bold", 16)
                c.drawString(margem, altura - margem,
                             f"Tabela de Preços - {nome} (Nº Balança: {num_balanca}) - {categoria_nome}")
                c.setFont("Helvetica", 10)
                data_emissao = datetime.now().strftime("%d/%m/%Y")
                c.drawString(margem, altura - margem - 20, f"Data de emissão: {data_emissao}")
                inicio = pagina * linhas_por_pagina + 1
                fim = inicio + linhas_por_pagina
                fatia = [dados_tabela[0]] + dados_tabela[inicio:fim]
                largura_colunas = [largura_disponivel * 0.7, largura_disponivel * 0.3]
                tabela = Table(fatia, colWidths=largura_colunas, rowHeights=altura_linha)
                estilo = TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ])
                tabela.setStyle(estilo)
                largura_tabela, altura_tabela = tabela.wrapOn(c, largura_disponivel, altura_disponivel)
                y_tabela = altura - margem - 50 - altura_tabela
                # Marca d'água
                if hasattr(self, 'adicionar_marca_dagua_pdf_area'):
                    self.adicionar_marca_dagua_pdf_area(
                        c,
                        texto=num_balanca,
                        x_inicio=margem,
                        x_fim=margem + largura_disponivel,
                        y_topo=y_tabela + altura_tabela - 60,
                        altura=altura_tabela,
                        tamanho_fonte=30,
                        cor=(0.8, 0.8, 0.8),
                        angulo=25
                    )
                tabela.drawOn(c, margem, y_tabela)
                texto_rodape = "Tabela com validade de 7(sete) dias corridos, podendo ter mudanças a qualquer momento"
                c.setFont("Helvetica-Oblique", 9)
                c.drawCentredString(largura / 2, margem / 2, texto_rodape)
                c.showPage()
            c.save()
            return arquivo_pdf

        def on_pdf_ready(path):
            if not path:
                QMessageBox.information(self, "Exportar PDF", "Não há produtos com preço positivo para essa categoria.")
                return
            QMessageBox.information(self, "Exportar PDF", f"Arquivo PDF gerado:\n{path}")
            abrir_arquivo(path)

        self.worker_exportar_pdf = WorkerThread(tarefa_pdf)
        self.worker_exportar_pdf.finished.connect(on_pdf_ready)
        self.worker_exportar_pdf.erro.connect(self._mostrar_erro_thread)
        self.worker_exportar_pdf.start()

    def adicionar_marca_dagua_pdf_area(self, c, texto, x_inicio, x_fim, y_topo, altura, tamanho_fonte=30, cor=(0.8, 0.8, 0.8), angulo=25):
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        try:
            pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'))
            fonte_nome = 'Arial'
        except:
            fonte_nome = 'Helvetica'
        c.saveState()
        c.setFont(fonte_nome, tamanho_fonte)
        c.setFillColorRGB(*cor, alpha=0.3)
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

    def exportar_jpg(self):
        if hasattr(self, "worker_tabela") and self.worker_tabela.isRunning():
            self.worker_tabela.quit()
            self.worker_tabela.wait()
        fornecedor_idx = self.combo_fornecedores.currentIndex()
        categoria_idx = self.combo_categoria.currentIndex()
        if fornecedor_idx < 0 or categoria_idx < 0:
            QMessageBox.warning(self, "Exportar JPG", "Selecione um fornecedor e uma categoria para exportar a tabela.")
            return

        fornecedor = self.fornecedores[fornecedor_idx]
        nome = fornecedor['nome']
        num_balanca = str(fornecedor.get('fornecedores_numerobalanca', '') or fornecedor.get('numerobalanca', ''))
        categoria_id = self.combo_categoria.currentData()
        categoria_nome = self.combo_categoria.currentText()

        def tarefa_jpg():
            import tempfile
            from PIL import Image, ImageDraw, ImageFont
            from datetime import datetime

            precos = self.db.listar_precos_por_categoria(categoria_id)
            precos_filtrados = [p for p in precos if (p['preco_base'] + p['ajuste_fixo']) > 0]
            if not precos_filtrados:
                return None

            try:
                fonte_titulo = ImageFont.truetype("arialbd.ttf", 24)
                fonte_texto = ImageFont.truetype("arial.ttf", 16)
                fonte_rodape = ImageFont.truetype("ariali.ttf", 12)
                fonte_marca = ImageFont.truetype("arialbd.ttf", 30)
            except IOError:
                fonte_titulo = fonte_texto = fonte_rodape = fonte_marca = ImageFont.load_default()

            largura_img = 800
            altura_linha = 30
            num_linhas = len(precos_filtrados) + 1
            altura_tabela = num_linhas * altura_linha
            altura_total = altura_tabela + 200

            img_base = Image.new("RGB", (largura_img, altura_total), (255, 255, 255))
            draw = ImageDraw.Draw(img_base)

            margem_topo = 40
            margem_lateral = 40

            draw.text((margem_lateral, 10), f"Tabela de Preços - {nome} (Nº Balança: {num_balanca}) - {categoria_nome}",
                      font=fonte_titulo, fill=(0, 0, 0))
            draw.text((margem_lateral, 10 + 30), f"Data de emissão: {datetime.now().strftime('%d/%m/%Y')}",
                      font=fonte_texto, fill=(0, 0, 0))

            col1_x = margem_lateral
            col2_x = int(largura_img * 0.65)
            col_end = largura_img - margem_lateral

            y = margem_topo + 50
            draw.rectangle([col1_x, y, col_end, y + altura_linha], fill=(100, 100, 100))
            draw.text((col1_x + 10, y + 5), "Produto", font=fonte_texto, fill=(255, 255, 255))
            draw.text((col2_x + 10, y + 5), "Preço", font=fonte_texto, fill=(255, 255, 255))
            y += altura_linha

            for p in precos_filtrados:
                preco_ajustado = p['preco_base'] + p['ajuste_fixo']
                draw.rectangle([col1_x, y, col_end, y + altura_linha], outline=(0, 0, 0))
                draw.line((col2_x, y, col2_x, y + altura_linha), fill=(0, 0, 0))
                draw.text((col1_x + 10, y + 5), p['nome'], font=fonte_texto, fill=(0, 0, 0))
                draw.text((col2_x + 10, y + 5), f"R$ {preco_ajustado:.2f}", font=fonte_texto, fill=(0, 0, 0))
                y += altura_linha

            y_fim_tabela = y
            y_inicio_tabela = margem_topo + 50 + altura_linha

            # Marca d'água opcional: use sua função já existente se desejar.
            if hasattr(self, 'adicionar_marca_dagua_area'):
                img_base = self.adicionar_marca_dagua_area(
                    img_base,
                    texto=num_balanca,
                    x_inicio=col1_x,
                    x_fim=col_end,
                    y_inicio=y_inicio_tabela,
                    altura=altura_linha * len(precos_filtrados),
                    fonte_path="arialbd.ttf",
                    tamanho_fonte=30,
                    opacidade=80,
                    angulo=25
                )

            texto_rodape = "Tabela com validade de 7(sete) dias corridos, podendo ter mudanças a qualquer momento"
            bbox = draw.textbbox((0, 0), texto_rodape, font=fonte_rodape)
            draw.text(((largura_img - bbox[2]) // 2, altura_total - 30), texto_rodape, font=fonte_rodape,
                      fill=(0, 0, 0, 255))

            arquivo_jpg = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
            img_base.convert("RGB").save(arquivo_jpg, "JPEG")
            return arquivo_jpg

        def on_jpg_ready(path):
            if not path:
                QMessageBox.information(self, "Exportar JPG", "Não há produtos com preço positivo para essa categoria.")
                return
            QMessageBox.information(self, "Exportar JPG", f"Arquivo JPG gerado:\n{path}")
            abrir_arquivo(path)

        self.worker_exportar_jpg = WorkerThread(tarefa_jpg)
        self.worker_exportar_jpg.finished.connect(on_jpg_ready)
        self.worker_exportar_jpg.erro.connect(self._mostrar_erro_thread)
        self.worker_exportar_jpg.start()

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

    def closeEvent(self, event):
        for attr in ["worker_tabela", "worker_categorias", "worker_exportar_pdf", "worker_exportar_jpg"]:
            if hasattr(self, attr):
                worker = getattr(self, attr)
                if worker.isRunning():
                    worker.quit()
                    worker.wait()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    janela = FornecedoresUI()
    janela.resize(1100, 600)
    janela.show()
    sys.exit(app.exec())