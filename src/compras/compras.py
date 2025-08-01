import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QComboBox, QDateEdit, QLineEdit,
    QTableWidget, QTableWidgetItem, QMessageBox, QTabWidget, QDialog, QCheckBox,
    QSizePolicy, QHeaderView, QSplitter
)
from PySide6.QtGui import QIntValidator
from PySide6.QtCore import Qt, QTimer, QDate, QLocale, QEvent
from decimal import Decimal, InvalidOperation
from status_delegate_combo import StatusComboDelegate
from utils_permissoes import requer_permissao
from threads_utils import WorkerThread
from movimentacoes_db import obter_saldo_total

# Importações dos submódulos
from .compras_db import (
    listar_fornecedores, listar_contas_do_fornecedor, listar_produtos,
    obter_produto, listar_compras, adicionar_compra, atualizar_compra,
    listar_itens_compra, obter_fornecedor_id_da_compra, obter_detalhes_compra,
    obter_total_produtos, obter_valor_com_abatimento_adiantamento, obter_saldo_devedor_fornecedor,
    buscar_nome_conta_padrao, obter_categorias_do_fornecedor, inserir_abatimento,
    obter_ajuste_fixo, obter_id_categoria_padrao, inserir_adiantamento, remover_lancamentos_antigos,
    obter_dados_para_editar_compra, obter_itens_e_lancamentos_da_compra, excluir_compra,
    obter_fornecedor_id_por_numero_balanca, obter_primeira_categoria_do_fornecedor,
    obter_dados_bancarios_para_campo_copiavel, atualizar_conta_bancaria_da_compra,
    atualizar_status_compra as atualizar_status_compra_db, obter_totais_produtos_compras,
    obter_valores_finais_compras, contar_compras, existe_transacao_saida_para_compra,
    excluir_transacao_saida_para_compra, obter_saldo_antes_compra, atualizar_origem_compra
)
from .compras_logic import (
    obter_total_produtos_lista, calcular_valor_com_abatimento_adiantamento, formatar_moeda
)
from .compras_export import (
    exportar_compra_pdf, exportar_compra_jpg
)
from .compras_dialogs import ImportarAppDialog

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

        # Paginação
        self.pagina_atual_aberto = 1
        self.pagina_atual_app = 1
        self.pagina_atual_concluida = 1
        self.qtd_por_pagina = 50
        self.total_paginas_aberto = 1
        self.total_paginas_app = 1
        self.total_paginas_concluida = 1

        self.init_ui()
        self.carregar_fornecedores()
        self.carregar_produtos()

    # ---- Métodos DB ----
    # Todos os métodos de acesso ao banco foram movidos para compras_db.py

    # ---- Métodos de lógica ----
    # Todos os métodos de cálculo/ajuda foram movidos para compras_logic.py

    # ---- Métodos de exportação ----
    # Todos os métodos de exportação foram movidos para compras_export.py

    def init_ui(self):
        layout_principal = QVBoxLayout()

        # --------------------- Filtros (único grupo centralizado) ---------------------
        layout_filtros = QHBoxLayout()

        self.filtro_numero_balanca = QLineEdit()
        self.filtro_numero_balanca.setPlaceholderText("Número da balança")
        layout_filtros.addWidget(QLabel("Número da Balança:"))
        layout_filtros.addWidget(self.filtro_numero_balanca)

        self.filtro_combo_fornecedor = QComboBox()
        self.filtro_combo_fornecedor.addItem("Todos os Fornecedores", None)
        for f in listar_fornecedores():
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
        btn_aplicar_filtro.clicked.connect(self.aplicar_filtro_compras)
        layout_filtros.addWidget(btn_aplicar_filtro)

        btn_limpar_filtro = QPushButton("Limpar Filtro")
        btn_limpar_filtro.clicked.connect(self.limpar_filtro_compras)
        layout_filtros.addWidget(btn_limpar_filtro)

        # Sincronizar número da balança com fornecedor
        self.filtro_numero_balanca.editingFinished.connect(
            lambda: self.selecionar_fornecedor_por_numero_balanca(
                self.filtro_numero_balanca, self.filtro_combo_fornecedor
            )
        )

        layout_principal.addLayout(layout_filtros)

        # ===================== Painel ESQUERDA =====================
        widget_esquerda = QWidget()
        layout_entrada = QVBoxLayout(widget_esquerda)
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

        # ========== ComboBox + QLineEdit para Abatimento/Adiantamento ==========
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

        # Checkbox para dizer se considera ou não essa compra no saldo
        self.checkbox_considerar_no_saldo = QCheckBox("Considerar esta compra no saldo geral de movimentações")
        self.checkbox_considerar_no_saldo.setChecked(True)
        layout_dados.addWidget(self.checkbox_considerar_no_saldo, 7, 0, 1, 2)

        layout_entrada.addLayout(layout_dados)

        layout_produto = QGridLayout()
        self.combo_produto = QComboBox()
        self.combo_produto.setEditable(True)
        self.combo_produto.currentIndexChanged.connect(self.zerar_quantidade)
        self.input_quantidade = QLineEdit()
        self.input_quantidade.setPlaceholderText("Quantidade")
        self.input_quantidade.setValidator(QIntValidator(1, 9999))  # Aceita apenas inteiros de 1 a 9999
        # Atalhos de ENTER entre campos
        self.combo_produto.lineEdit().returnPressed.connect(self.focus_quantidade)
        self.input_quantidade.installEventFilter(self)

        # NOVO CAMPO: Número de Fardos
        self.input_numero_fardos = QLineEdit()
        self.input_numero_fardos.setPlaceholderText("Nº de fardos")
        self.input_numero_fardos.setValidator(QIntValidator(0, 9999))
        self.input_numero_fardos.installEventFilter(self)

        layout_produto.addWidget(QLabel("Produto"), 0, 0)
        layout_produto.addWidget(self.combo_produto, 0, 1)
        layout_produto.addWidget(QLabel("Quantidade"), 1, 0)
        layout_produto.addWidget(self.input_quantidade, 1, 1)
        layout_produto.addWidget(QLabel("Nº de fardos"), 2, 0)
        layout_produto.addWidget(self.input_numero_fardos, 2, 1)

        self.btn_adicionar_item = QPushButton("Adicionar Produto")
        self.btn_adicionar_item.clicked.connect(self.adicionar_item)
        layout_produto.addWidget(self.btn_adicionar_item, 3, 0, 1, 2)

        layout_entrada.addLayout(layout_produto)

        self.tabela_itens_adicionados = QTableWidget()
        self.tabela_itens_adicionados.setColumnCount(5)
        self.tabela_itens_adicionados.setHorizontalHeaderLabels(
            ["Produto", "Qtd", "Preço Unit.", "Total", "Nº Fardos"]
        )
        self.tabela_itens_adicionados.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tabela_itens_adicionados.cellChanged.connect(self.atualizar_item_editado)
        self.tabela_itens_adicionados.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela_itens_adicionados.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabela_itens_adicionados.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

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

        # ===================== Área direita =====================
        widget_direita = QWidget()
        layout_direita = QVBoxLayout(widget_direita)
        self.tabela_itens_compra = QTableWidget()
        self.tabela_itens_compra.setColumnCount(4)
        self.tabela_itens_compra.setHorizontalHeaderLabels(["Produto", "Qtd", "Preço Unit.", "Total"])
        self.tabela_itens_compra.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_itens_compra.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabela_itens_compra.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout_direita.addWidget(self.tabela_itens_compra)

        self.label_total_com_abatimento = QLabel("Total com Abatimento: R$ 0,00")
        self.label_total_com_abatimento.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 5px;")
        layout_direita.addWidget(self.label_total_com_abatimento)

        self.campo_texto_copiavel = QLineEdit()
        self.campo_texto_copiavel.setReadOnly(True)
        self.campo_texto_copiavel.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout_direita.addWidget(self.campo_texto_copiavel)
        self.campo_texto_copiavel.mousePressEvent = self.copiar_campo_texto_copiavel

        # Botão para trocar conta do fornecedor
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

        # ===================== Painel CENTRAL (as abas) =====================
        self.tabs = QTabWidget()

        # --- Aba Em Aberto ---
        self.tab_em_aberto = QWidget()
        layout_aberto = QVBoxLayout(self.tab_em_aberto)
        self.tabela_compras_aberto = QTableWidget()
        self.tabela_compras_aberto.setColumnCount(6)
        self.tabela_compras_aberto.setHorizontalHeaderLabels([
            "ID", "Fornecedor", "Data", "Total dos produtos (R$)", "Valor com abatimento/adiantamento", "Status"
        ])
        self.tabela_compras_aberto.setEditTriggers(QTableWidget.DoubleClicked)
        self.tabela_compras_aberto.cellClicked.connect(
            lambda row, col: self.mostrar_itens_da_compra(row, col, tabela=self.tabela_compras_aberto))
        self.tabela_compras_aberto.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela_compras_aberto.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabela_compras_aberto.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout_aberto.addWidget(self.tabela_compras_aberto)
        paginacao_aberto_layout = QHBoxLayout()
        self.btn_pagina_anterior_aberto = QPushButton("Página anterior")
        self.btn_pagina_proxima_aberto = QPushButton("Próxima página")
        self.label_paginacao_aberto = QLabel()
        paginacao_aberto_layout.addWidget(self.btn_pagina_anterior_aberto)
        paginacao_aberto_layout.addWidget(self.label_paginacao_aberto)
        paginacao_aberto_layout.addWidget(self.btn_pagina_proxima_aberto)
        layout_aberto.addLayout(paginacao_aberto_layout)

        # --- Aba App (N) ---
        self.tab_app = QWidget()
        layout_app = QVBoxLayout(self.tab_app)
        self.tabela_compras_app = QTableWidget()
        self.tabela_compras_app.setColumnCount(6)
        self.tabela_compras_app.setHorizontalHeaderLabels([
            "ID", "Fornecedor", "Data", "Total dos produtos (R$)", "Valor com abatimento/adiantamento", "Status"
        ])
        self.tabela_compras_app.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_compras_app.cellClicked.connect(
            lambda row, col: self.mostrar_itens_da_compra(row, col, tabela=self.tabela_compras_app))
        self.tabela_compras_app.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela_compras_app.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabela_compras_app.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout_app.addWidget(self.tabela_compras_app)
        paginacao_app_layout = QHBoxLayout()
        self.btn_pagina_anterior_app = QPushButton("Página anterior")
        self.btn_pagina_proxima_app = QPushButton("Próxima página")
        self.label_paginacao_app = QLabel()
        paginacao_app_layout.addWidget(self.btn_pagina_anterior_app)
        paginacao_app_layout.addWidget(self.label_paginacao_app)
        paginacao_app_layout.addWidget(self.btn_pagina_proxima_app)
        layout_app.addLayout(paginacao_app_layout)

        # --- Aba Concluídas ---
        self.tab_concluidas = QWidget()
        layout_concluidas = QVBoxLayout(self.tab_concluidas)
        self.tabela_compras_concluidas = QTableWidget()
        self.tabela_compras_concluidas.setColumnCount(6)
        self.tabela_compras_concluidas.setHorizontalHeaderLabels([
            "ID", "Fornecedor", "Data", "Total dos produtos (R$)", "Valor com abatimento/adiantamento", "Status"
        ])
        self.tabela_compras_concluidas.setEditTriggers(QTableWidget.DoubleClicked)
        self.tabela_compras_concluidas.cellClicked.connect(
            lambda row, col: self.mostrar_itens_da_compra(row, col, tabela=self.tabela_compras_concluidas))
        self.tabela_compras_concluidas.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela_compras_concluidas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabela_compras_concluidas.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout_concluidas.addWidget(self.tabela_compras_concluidas)
        paginacao_concluida_layout = QHBoxLayout()
        self.btn_pagina_anterior_concluida = QPushButton("Página anterior")
        self.btn_pagina_proxima_concluida = QPushButton("Próxima página")
        self.label_paginacao_concluida = QLabel()
        paginacao_concluida_layout.addWidget(self.btn_pagina_anterior_concluida)
        paginacao_concluida_layout.addWidget(self.label_paginacao_concluida)
        paginacao_concluida_layout.addWidget(self.btn_pagina_proxima_concluida)
        layout_concluidas.addLayout(paginacao_concluida_layout)

        # Adiciona abas ao QTabWidget
        self.tabs.addTab(self.tab_em_aberto, "Em aberto")
        self.tabs.addTab(self.tab_app, "App (0)")
        self.tabs.addTab(self.tab_concluidas, "Concluídas")

        self.tab_em_aberto.setLayout(layout_aberto)
        self.tab_app.setLayout(layout_app)
        self.tab_concluidas.setLayout(layout_concluidas)

        # ============== Splitter principal: esquerda, central (abas), direita ==============
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(widget_esquerda)
        splitter.addWidget(self.tabs)
        splitter.addWidget(widget_direita)
        splitter.setSizes([320, 800, 320])

        layout_principal.addWidget(splitter)
        self.setLayout(layout_principal)

        self.setLayout(layout_principal)
        self.itens_compra = []
        self.atualizar_tabela_itens_adicionados()
        self.atualizar_tabelas()
        self.status_delegate = StatusComboDelegate(self.STATUS_COLORS, STATUS_LIST, self.tabela_compras_aberto)
        self.tabela_compras_aberto.setItemDelegateForColumn(5, self.status_delegate)
        self.tabela_compras_concluidas.setItemDelegateForColumn(5, self.status_delegate)
        self.tabela_compras_aberto.itemChanged.connect(self.on_status_item_changed)
        self.tabela_compras_concluidas.itemChanged.connect(self.on_status_item_changed)

        # Conexões dos botões de paginação
        self.btn_pagina_anterior_aberto.clicked.connect(self.ir_para_pagina_anterior_aberto)
        self.btn_pagina_proxima_aberto.clicked.connect(self.ir_para_pagina_proxima_aberto)
        self.btn_pagina_anterior_app.clicked.connect(self.ir_para_pagina_anterior_app)
        self.btn_pagina_proxima_app.clicked.connect(self.ir_para_pagina_proxima_app)
        self.btn_pagina_anterior_concluida.clicked.connect(self.ir_para_pagina_anterior_concluida)
        self.btn_pagina_proxima_concluida.clicked.connect(self.ir_para_pagina_proxima_concluida)

        # Troca de aba recarrega dados
        self.tabs.currentChanged.connect(self.atualizar_tabelas)

    def carregar_dados(self):
        self.atualizar_tabelas()
        self.combo_produto.blockSignals(True)
        self.combo_produto.clear()
        for p in listar_produtos():
            self.combo_produto.addItem(p['nome'], p['id'])
        self.combo_produto.setCurrentIndex(-1)
        self.combo_produto.blockSignals(False)
        self.atualizar_tabelas()

    def selecionar_categoria_do_fornecedor(self, fornecedor_id):
        categoria_id = obter_primeira_categoria_do_fornecedor(fornecedor_id)
        if categoria_id is not None:
            index = self.combo_categoria_temporaria.findData(categoria_id)
            if index != -1:
                self.combo_categoria_temporaria.setCurrentIndex(index)
        else:
            # Tenta pegar categoria padrão
            cat_padrao_id = obter_id_categoria_padrao()
            if cat_padrao_id:
                index = self.combo_categoria_temporaria.findData(cat_padrao_id)
                if index != -1:
                    self.combo_categoria_temporaria.setCurrentIndex(index)

    def carregar_categorias_para_fornecedor(self, fornecedor_id):
        self.combo_categoria_temporaria.blockSignals(True)
        self.combo_categoria_temporaria.clear()
        self.combo_categoria_temporaria.addItem("Selecione uma categoria", 0)
        categorias = obter_categorias_do_fornecedor(fornecedor_id)
        for c in categorias:
            self.combo_categoria_temporaria.addItem(c['nome'], c['id'])
        self.combo_categoria_temporaria.setCurrentIndex(1 if self.combo_categoria_temporaria.count() > 1 else 0)
        self.combo_categoria_temporaria.blockSignals(False)

    def atualizar_campo_texto_copiavel(self):
        compra_id = self.obter_compra_id_selecionado()
        if not compra_id:
            self.campo_texto_copiavel.setText("")
            return
        texto = obter_dados_bancarios_para_campo_copiavel(compra_id)
        self.campo_texto_copiavel.setText(texto or "")

    def focus_quantidade(self):
        self.input_quantidade.setFocus()

    def atalho_enter_quantidade(self):
        self.adicionar_item()
        self.combo_produto.setFocus()
        self.combo_produto.lineEdit().selectAll()

    def obter_compra_id_selecionado(self, tabela=None):
        if tabela is None:
            tabela = self.tabela_ativa()
        row = tabela.currentRow()
        if row < 0:
            return None
        item = tabela.item(row, 0)
        return int(item.text()) if item else None

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if obj is self.input_quantidade and event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.input_numero_fardos.setFocus()
                self.input_numero_fardos.selectAll()
                return True
            elif obj is self.input_numero_fardos and event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.atalho_enter_quantidade()
                return True
        return super().eventFilter(obj, event)

    @requer_permissao(['admin', 'gerente', 'operador'])
    def abrir_dialog_troca_conta_fornecedor(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox, QComboBox, QLabel, QMessageBox

        compra_id = self.obter_compra_id_selecionado()
        if not compra_id:
            QMessageBox.warning(self, "Atenção", "Selecione uma compra primeiro.")
            return

        fornecedor_id = obter_fornecedor_id_da_compra(compra_id)
        if not fornecedor_id:
            QMessageBox.warning(self, "Erro", "Não foi possível identificar o fornecedor da compra selecionada.")
            return

        contas_do_fornecedor = listar_contas_do_fornecedor(fornecedor_id)
        if not contas_do_fornecedor:
            QMessageBox.information(self, "Sem contas", "Este fornecedor não possui contas bancárias cadastradas.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Escolher conta do fornecedor para esta compra")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Selecione a conta bancária ou chave PIX:"))

        combo_contas = QComboBox(dialog)
        for conta in contas_do_fornecedor:
            texto = f"{conta['apelido']}"
            detalhes = []
            if conta.get('banco'):
                detalhes.append(f"{conta['banco']} Ag:{conta['agencia']} Conta:{conta['conta']}")
            if conta.get('chave_pix'):
                detalhes.append(f"PIX: {conta['chave_pix']}")
            if conta.get('padrao'):
                detalhes.append("(padrão)")
            if detalhes:
                texto += " - " + " | ".join(detalhes)
            combo_contas.addItem(texto, conta['id'])

        layout.addWidget(combo_contas)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        def on_ok():
            conta_id = combo_contas.currentData()
            compra_id_local = self.obter_compra_id_selecionado()
            if conta_id and compra_id_local:
                atualizar_conta_bancaria_da_compra(compra_id_local, conta_id)
                # Chama o méodo para atualizar o campo copiável
                self.atualizar_campo_texto_copiavel()
            dialog.accept()

        def on_cancel():
            dialog.reject()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(on_cancel)

        dialog.exec()

    def atualizar_tabelas(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        status_filtro = self.filtro_combo_status.currentData()
        fornecedor_id = self.filtro_combo_fornecedor.currentData()
        data_de = self.filtro_data_de.date().toPython()
        data_ate = self.filtro_data_ate.date().toPython()
        qtd_por_pagina = self.qtd_por_pagina

        pagina_atual_aberto = getattr(self, "pagina_atual_aberto", 1)
        pagina_atual_app = getattr(self, "pagina_atual_app", 1)
        pagina_atual_concluida = getattr(self, "pagina_atual_concluida", 1)

        def tarefa_db():
            # Em aberto
            offset_aberto = (pagina_atual_aberto - 1) * qtd_por_pagina
            compras_aberto = listar_compras(
                status=None if status_filtro == "Concluída" else status_filtro,
                status_not="Concluída",
                data_de=data_de,
                data_ate=data_ate,
                fornecedor_id=fornecedor_id,
                origem='compras',
                limit=qtd_por_pagina,
                offset=offset_aberto
            )
            total_aberto = contar_compras(
                status=None if status_filtro == "Concluída" else status_filtro,
                status_not="Concluída",
                data_de=data_de,
                data_ate=data_ate,
                fornecedor_id=fornecedor_id,
                origem='compras'
            )
            # App
            offset_app = (pagina_atual_app - 1) * qtd_por_pagina
            compras_app = listar_compras(
                status=None,
                status_not=None,
                data_de=data_de,
                data_ate=data_ate,
                fornecedor_id=fornecedor_id,
                origem='app',
                limit=qtd_por_pagina,
                offset=offset_app
            )
            total_app = contar_compras(
                status=None,
                status_not=None,
                data_de=data_de,
                data_ate=data_ate,
                fornecedor_id=fornecedor_id,
                origem='app'
            )
            # Concluídas
            offset_concluida = (pagina_atual_concluida - 1) * qtd_por_pagina
            compras_concluidas = listar_compras(
                status="Concluída",
                data_de=data_de,
                data_ate=data_ate,
                fornecedor_id=fornecedor_id,
                origem='compras',
                limit=qtd_por_pagina,
                offset=offset_concluida
            )
            total_concluida = contar_compras(
                status="Concluída",
                data_de=data_de,
                data_ate=data_ate,
                fornecedor_id=fornecedor_id,
                origem='compras'
            )
            todos_ids = [c['id'] for c in compras_aberto] + [c['id'] for c in compras_app] + [c['id'] for c in
                                                                                              compras_concluidas]
            itens_por_compra = listar_itens_compra(todos_ids)
            return (compras_aberto, total_aberto, compras_app, total_app, compras_concluidas, total_concluida,
                    itens_por_compra)

        self.worker = WorkerThread(tarefa_db)
        self.worker.finished.connect(self._atualizar_tabelas_ui)
        self.worker.erro.connect(self._mostrar_erro_thread)
        self.worker.start()

    def _atualizar_tabelas_ui(self, resultado):
        compras_aberto, total_aberto, compras_app, total_app, compras_concluidas, total_concluida, itens_por_compra = resultado
        self.itens_por_compra = itens_por_compra
        self.total_paginas_aberto = max(1, (total_aberto + self.qtd_por_pagina - 1) // self.qtd_por_pagina)
        self.total_paginas_app = max(1, (total_app + self.qtd_por_pagina - 1) // self.qtd_por_pagina)
        self.total_paginas_concluida = max(1, (total_concluida + self.qtd_por_pagina - 1) // self.qtd_por_pagina)

        self.preencher_tabela_compras(self.tabela_compras_aberto, compras_aberto)
        self.label_paginacao_aberto.setText(f"Página {self.pagina_atual_aberto} de {self.total_paginas_aberto}")

        self.preencher_tabela_compras(self.tabela_compras_app, compras_app)
        self.label_paginacao_app.setText(f"Página {self.pagina_atual_app} de {self.total_paginas_app}")

        self.preencher_tabela_compras(self.tabela_compras_concluidas, compras_concluidas)
        self.label_paginacao_concluida.setText(
            f"Página {self.pagina_atual_concluida} de {self.total_paginas_concluida}")

        # Atualiza o contador da aba App
        self.tabs.setTabText(1, f"App ({total_app})")

    def _mostrar_erro_thread(self, mensagem):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Erro", mensagem)

    # Métodos de paginação para cada aba:
    def ir_para_pagina_anterior_aberto(self):
        if self.pagina_atual_aberto > 1:
            self.pagina_atual_aberto -= 1
            self.atualizar_tabelas()

    def ir_para_pagina_proxima_aberto(self):
        if self.pagina_atual_aberto < self.total_paginas_aberto:
            self.pagina_atual_aberto += 1
            self.atualizar_tabelas()

    def ir_para_pagina_anterior_app(self):
        if self.pagina_atual_app > 1:
            self.pagina_atual_app -= 1
            self.atualizar_tabelas()

    def ir_para_pagina_proxima_app(self):
        if self.pagina_atual_app < self.total_paginas_app:
            self.pagina_atual_app += 1
            self.atualizar_tabelas()

    def ir_para_pagina_anterior_concluida(self):
        if self.pagina_atual_concluida > 1:
            self.pagina_atual_concluida -= 1
            self.atualizar_tabelas()

    def ir_para_pagina_proxima_concluida(self):
        if self.pagina_atual_concluida < self.total_paginas_concluida:
            self.pagina_atual_concluida += 1
            self.atualizar_tabelas()

    def preencher_tabela_compras(self, tabela, compras):
        # NÃO carregue self.itens_por_compra aqui!
        # Ele deve ser carregado uma única vez em atualizar_tabelas, com TODOS os IDs das compras visíveis.

        compra_ids = [c['id'] for c in compras]
        totais_produtos = obter_totais_produtos_compras(compra_ids)
        valores_finais = obter_valores_finais_compras(compra_ids)
        tabela.blockSignals(True)
        try:
            tabela.setRowCount(len(compras))
            for i, c in enumerate(compras):
                tabela.setItem(i, 0, QTableWidgetItem(str(c['id'])))
                tabela.setItem(i, 1, QTableWidgetItem(c['fornecedor_nome']))
                tabela.setItem(i, 2, QTableWidgetItem(str(c['data'])))
                total_produtos = totais_produtos.get(c['id'], 0)
                tabela.setItem(i, 3, QTableWidgetItem(self.locale.toString(float(total_produtos), 'f', 2)))

                vf = valores_finais.get(c['id'], {'abatimento': 0, 'adiantamento': 0})
                valor_final = total_produtos + vf['adiantamento'] - vf['abatimento']
                tabela.setItem(i, 4, QTableWidgetItem(self.locale.toString(float(valor_final), 'f', 2)))
                tabela.setItem(i, 5, QTableWidgetItem(c['status']))
        finally:
            tabela.blockSignals(False)

    def on_status_item_changed(self, item):
        from .compras_dialogs import (
            ConfirmarExclusaoPagamentoDialog,
            PagamentoMovimentacaoDialog,
        )
        if item.column() == 5:
            row = item.row()
            tabela = item.tableWidget()
            compra_id = int(tabela.item(row, 0).text())
            novo_status = item.text()
            considerar_no_saldo = self.checkbox_considerar_no_saldo.isChecked() if hasattr(self, 'checkbox_considerar_no_saldo') else False

            # Busca status anterior do banco ANTES de atualizar!
            compra, _ = obter_detalhes_compra(compra_id)
            status_anterior = compra.get('status') if compra else None

            # Atualiza status no banco
            self.atualizar_status_compra(compra_id, novo_status)

            if considerar_no_saldo:
                if novo_status == "Concluída" and status_anterior != "Concluída":
                    # Pergunta sobre lançar pagamento (usando PagamentoMovimentacaoDialog)
                    if not existe_transacao_saida_para_compra(compra_id):
                        try:
                            fornecedor_id = compra['fornecedor_id']
                            valor_movimentacao = float(obter_valor_com_abatimento_adiantamento(compra_id))
                            saldo_atual = float(obter_saldo_total(fornecedor_id, lambda x: x.lower()))
                        except Exception:
                            saldo_atual = 0.0
                            valor_movimentacao = 0.0
                        from .compras_dialogs import PagamentoMovimentacaoDialog
                        dialog = PagamentoMovimentacaoDialog(valor_movimentacao, saldo_atual, self)
                        if dialog.exec() and getattr(dialog, "resultado", None) == "sim":
                            valor_pagamento = getattr(dialog, "valor_lancamento", valor_movimentacao)
                            valor_desconto = getattr(dialog, "valor_desconto", 0.0)
                            descricao = ""
                            if valor_desconto > 0:
                                descricao += f"Desconto: R$ {valor_desconto:.2f} - "
                            descricao += f"Pagamento referente à CompraID:{compra_id}"
                            self.lancar_transacao_saida_para_compra(compra_id, valor_pagamento, descricao)
                    else:
                        QMessageBox.information(self, "Atenção",
                                                "Já existe uma transação de pagamento para esta compra!")
                elif status_anterior == "Concluída" and novo_status != "Concluída":
                    # Pergunta sobre exclusão do pagamento (usando ConfirmarExclusaoPagamentoDialog)
                    if existe_transacao_saida_para_compra(compra_id):
                        dialog = ConfirmarExclusaoPagamentoDialog(self)
                        if dialog.exec() and getattr(dialog, "resultado", None):
                            excluir_transacao_saida_para_compra(compra_id)

            self.atualizar_tabelas()

    def lancar_transacao_saida_para_compra(self, compra_id, valor_pagamento=None, descricao_custom=None):
        from movimentacoes_db import inserir_movimentacao, inserir_item_compra, get_conta_padrao_id
        compra, itens = obter_detalhes_compra(compra_id)
        fornecedor_id = compra['fornecedor_id']
        data_compra = compra['data_compra']
        if descricao_custom is not None:
            descricao = descricao_custom
        else:
            descricao = f"Pagamento referente à CompraID:{compra_id}"

        valor_final = float(obter_valor_com_abatimento_adiantamento(compra_id))
        valor_para_lancar = valor_pagamento if valor_pagamento is not None else valor_final

        conta_padrao_id = get_conta_padrao_id(fornecedor_id)
        mov_id = inserir_movimentacao(
            fornecedor_id=fornecedor_id,
            data=data_compra,
            tipo="Transação",
            direcao="Saída",
            descricao=descricao,
            valor_abatimento=Decimal("0.00"),
            valor_operacao=Decimal(str(valor_para_lancar)),
            status="Concluída",
            origem="movimentacao",
            considerar_no_saldo=True,
            dados_bancarios_id=conta_padrao_id
        )
        return mov_id

    def atualizar_status_compra(self, compra_id, novo_status):
        atualizar_status_compra_db(compra_id, novo_status)

    def aplicar_filtro_compras(self):
        self.atualizar_tabelas()

    def limpar_filtro_compras(self):
        self.filtro_combo_fornecedor.setCurrentIndex(0)
        self.filtro_combo_status.setCurrentIndex(0)
        self.filtro_data_de.setDate(QDate.currentDate().addMonths(-1))
        self.filtro_data_ate.setDate(QDate.currentDate())
        self.atualizar_tabelas()

    def zerar_quantidade(self):
        self.input_quantidade.clear()

    def atualizar_saldo_fornecedor(self):
        fornecedor_id = self.combo_fornecedor.currentData()
        if not fornecedor_id:
            self.label_saldo_fornecedor.setText("Saldo total: R$ 0,00")
            self.label_saldo_fornecedor.setStyleSheet(
                "font-weight: bold; color: #808080; font-size: 13px; text-decoration: underline; cursor: pointer;")
            return

        # Use saldo de movimentações
        saldo = float(
            obter_saldo_total(fornecedor_id, lambda x: x.lower().replace('ç', 'c').replace('ã', 'a').replace('á', 'a')))
        # Ajuste o lambda conforme o remove_acento utilizado

        # Define texto e cor de acordo com o saldo
        if saldo < 0:
            texto = f"Saldo devedor: R$ {self.locale.toString(abs(saldo), 'f', 2)}"
            cor = "#b22222"  # vermelho
        elif saldo > 0:
            texto = f"Saldo credor: R$ {self.locale.toString(abs(-saldo), 'f', 2)}"
            cor = "#228B22"  # verde
        else:
            texto = "Saldo zerado: R$ 0,00"
            cor = "#808080"  # cinza

        self.label_saldo_fornecedor.setText(texto)
        self.label_saldo_fornecedor.setStyleSheet(
            f"font-weight: bold; color: {cor}; font-size: 13px; text-decoration: underline; cursor: pointer;"
        )

    @requer_permissao(['admin', 'gerente', 'operador'])
    def on_saldo_label_clicked(self, event):
        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id and hasattr(self, 'main_window'):
            # Abra o módulo movimentações e selecione a aba do fornecedor
            movimentacoes_ui = getattr(self.main_window, "movimentacoes_ui", None)
            if movimentacoes_ui:
                # Descobre o índice da MovimentaçõesUI no stack
                index = self.main_window.stack.indexOf(movimentacoes_ui)
                self.main_window.stack.setCurrentIndex(index)
                # Seleciona o fornecedor na MovimentaçõesUI
                combo_fornecedor = movimentacoes_ui.combo_fornecedor
                idx = combo_fornecedor.findData(fornecedor_id)
                if idx >= 0:
                    combo_fornecedor.setCurrentIndex(idx)
                    movimentacoes_ui.abrir_nova_aba()  # já abre a aba do fornecedor

    def set_main_window(self, main_window):
        self.main_window = main_window

    @requer_permissao(['admin', 'gerente', 'operador', 'consulta'])
    def copiar_campo_texto_copiavel(self, event):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.campo_texto_copiavel.text())
        self.campo_texto_copiavel.setStyleSheet("background-color: #b2f2b4; font-weight: bold; font-size: 13px;")
        QTimer.singleShot(350, lambda: self.campo_texto_copiavel.setStyleSheet("font-weight: bold; font-size: 13px;"))
        QLineEdit.mousePressEvent(self.campo_texto_copiavel, event)

    def ao_mudar_fornecedor(self):
        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id is not None:
            self.carregar_categorias_para_fornecedor(fornecedor_id)
            self.selecionar_categoria_do_fornecedor(fornecedor_id)
            self.atualizar_saldo_fornecedor()

    @requer_permissao(['admin', 'gerente', 'operador'])
    def adicionar_item(self):
        produto_id = self.combo_produto.currentData()
        texto = self.input_quantidade.text()
        if not texto or int(texto) <= 0:
            QMessageBox.warning(self, "Erro", "Informe uma quantidade válida.")
            return
        quantidade = int(texto)
        if produto_id is None or quantidade <= 0:
            QMessageBox.warning(self, "Erro", "Selecione um produto e uma quantidade válida.")
            return

        produto = obter_produto(produto_id)
        if produto is None:
            QMessageBox.critical(self, "Erro", "Produto não encontrado.")
            return

        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id is None:
            QMessageBox.warning(self, "Erro", "Selecione um fornecedor.")
            return

        categoria_id = self.combo_categoria_temporaria.currentData()
        if categoria_id is None or categoria_id == 0:
            categoria_id = obter_id_categoria_padrao()
            if categoria_id is None:
                QMessageBox.warning(self, "Erro", "Selecione uma categoria válida para esta compra.")
                return

        ajuste_fixo = obter_ajuste_fixo(produto_id, categoria_id)
        preco = Decimal(str(produto["preco_base"])) + ajuste_fixo
        total = Decimal(str(quantidade)) * preco

        # NOVO: pega número de fardos
        numero_fardos = self.input_numero_fardos.text()
        numero_fardos = int(numero_fardos) if numero_fardos else None

        self.itens_compra.append({
            "produto_id": produto_id,
            "nome": produto["nome"],
            "quantidade": quantidade,
            "preco": preco,
            "total": total,
            "numero_fardos": numero_fardos
        })

        self.atualizar_tabela_itens_adicionados()
        self.combo_produto.setCurrentIndex(-1)
        self.input_quantidade.clear()
        self.input_numero_fardos.clear()

    def atualizar_tabela_itens_adicionados(self):
        self.tabela_itens_adicionados.blockSignals(True)
        self.tabela_itens_adicionados.setRowCount(len(self.itens_compra))
        for i, item in enumerate(self.itens_compra):
            self.tabela_itens_adicionados.setItem(i, 0, QTableWidgetItem(item["nome"]))
            self.tabela_itens_adicionados.setItem(i, 1, QTableWidgetItem(str(item["quantidade"])))
            preco = Decimal(item['preco'])
            total = Decimal(item['total'])
            preco_formatado = formatar_moeda(preco, self.locale)
            total_formatado = formatar_moeda(total, self.locale)
            self.tabela_itens_adicionados.setItem(i, 2, QTableWidgetItem(preco_formatado))
            self.tabela_itens_adicionados.setItem(i, 3, QTableWidgetItem(total_formatado))
            # NOVO: coluna número de fardos
            nfardos = item.get("numero_fardos")
            self.tabela_itens_adicionados.setItem(i, 4, QTableWidgetItem(str(nfardos) if nfardos is not None else ""))
        self.tabela_itens_adicionados.blockSignals(False)
        total = obter_total_produtos_lista(self.itens_compra)
        total_formatado = formatar_moeda(total, self.locale)
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
        total = obter_total_produtos_lista(self.itens_compra)
        valor_abatimento = valor if tipo == "abatimento" else Decimal('0.00')
        valor_adiantamento = valor if tipo == "adiantamento" else Decimal('0.00')
        total_final = calcular_valor_com_abatimento_adiantamento(total, valor_abatimento, valor_adiantamento)
        total_formatado = self.locale.toString(float(total_final), 'f', 2)
        self.label_total_compra.setText(f"Total: R$ {total_formatado}")

    @requer_permissao(['admin', 'gerente', 'operador'])
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
        except (ValueError, InvalidOperation):
            QMessageBox.warning(self, "Erro", "Valor de abatimento/adiantamento inválido.")
            return
        tipo_lancamento = self.combo_tipo_lancamento.currentData()
        status = self.combo_status.currentText()
        valor_abatimento = valor_lancamento if tipo_lancamento == "abatimento" else Decimal('0.00')
        valor_inclusao = valor_lancamento if tipo_lancamento == "adiantamento" else Decimal('0.00')
        considerar_no_saldo = self.checkbox_considerar_no_saldo.isChecked()

        if self.compra_edit_id is None:
            compra_id = adicionar_compra(
                fornecedor_id, data_compra, valor_abatimento, self.itens_compra, status,
                origem='compras', considerar_no_saldo_movimentacao=considerar_no_saldo
            )
            if tipo_lancamento == "adiantamento" and valor_inclusao > 0:
                inserir_adiantamento(fornecedor_id, compra_id, data_compra, valor_inclusao)
            # Não chama inserir_abatimento manualmente!
            QMessageBox.information(self, "Sucesso", "Compra cadastrada com sucesso.")
        else:
            remover_lancamentos_antigos(self.compra_edit_id)
            if tipo_lancamento == "adiantamento" and valor_inclusao > 0:
                inserir_adiantamento(fornecedor_id, self.compra_edit_id, data_compra, valor_inclusao)
            elif tipo_lancamento == "abatimento" and valor_abatimento > 0:
                inserir_abatimento(fornecedor_id, self.compra_edit_id, data_compra, valor_abatimento)
            atualizar_compra(
                self.compra_edit_id,
                fornecedor_id,
                data_compra,
                valor_abatimento,
                self.itens_compra,
                status,
                considerar_no_saldo_movimentacao=considerar_no_saldo
            )
            # PATCH: se veio da importação do app, troca origem para "compras"
            atualizar_origem_compra(self.compra_edit_id, "compras", origem_esperada="app")
            QMessageBox.information(self, "Sucesso", "Compra editada com sucesso.")

        # Limpa e atualiza UI
        self.limpar_campos()
        self.atualizar_tabelas()
        self.limpar_itens()
        self.carregar_fornecedores()
        self.carregar_produtos()
        self.checkbox_considerar_no_saldo.setChecked(True)
        if hasattr(self, 'janela_debitos'):
            self.janela_debitos.atualizar()

    @requer_permissao(['admin', 'gerente', 'operador'])
    def editar_compra_finalizada(self):
        aba_idx = self.tabs.currentIndex()
        if aba_idx == 1:  # App
            row = self.tabela_compras_app.currentRow()
            if row < 0:
                QMessageBox.warning(self, "Importar", "Selecione uma compra do App para importar.")
                return
            compra_id = int(self.tabela_compras_app.item(row, 0).text())
            compra, itens, _ = obter_dados_para_editar_compra(compra_id)
            cliente = compra.get('fornecedor')  # ou campo correto
            descricao = compra.get('descricao', '')

            categorias = obter_categorias_do_fornecedor(compra['fornecedor_id'])

            def get_precos_func(cat_id):
                # Busca preços ajustados para cada produto nesta categoria
                precos = {}
                for item in itens:
                    ajuste = obter_ajuste_fixo(item['produto_id'], cat_id)
                    produto = obter_produto(item['produto_id'])
                    precos[item['produto_id']] = float(produto['preco_base']) + float(ajuste)
                return precos

            dialog = ImportarAppDialog(cliente, descricao, itens, categorias, get_precos_func, self)
            if dialog.exec() and dialog.resultado:
                # Prosseguir: abrir edição normal, preenchendo campos com dialog.novos_itens e categoria
                self.itens_compra = dialog.novos_itens
                # Setar categoria temporária, fornecedor, etc, conforme necessário
                # Seta self.compra_edit_id = compra_id
                # Troca origem para "compras" ao finalizar
                self.compra_edit_id = compra_id
                idx_cat = self.combo_categoria_temporaria.findData(dialog.categoria_id)
                if idx_cat != -1:
                    self.combo_categoria_temporaria.setCurrentIndex(idx_cat)
                # Preenche fornecedor
                idx_forn = self.combo_fornecedor.findData(compra['fornecedor_id'])
                if idx_forn != -1:
                    self.combo_fornecedor.setCurrentIndex(idx_forn)
                # Preenche data
                if 'data_compra' in compra:
                    try:
                        from PySide6.QtCore import QDate
                        if isinstance(compra['data_compra'], QDate):
                            self.input_data.setDate(compra['data_compra'])
                        else:
                            self.input_data.setDate(QDate.fromString(str(compra['data_compra']), "yyyy-MM-dd"))
                    except Exception:
                        self.input_data.setDate(QDate.currentDate())
                # Preenche valor de lançamento
                valor_adiantamento = 0
                if hasattr(dialog, "categoria_id"):
                    # Se já buscou adiantamento, use
                    valor_adiantamento = dialog.novos_itens[0].get('adiantamento', 0) if dialog.novos_itens else 0
                if valor_adiantamento > 0:
                    self.combo_tipo_lancamento.setCurrentIndex(1)
                    self.input_valor_lancamento.setText(str(valor_adiantamento))
                else:
                    self.combo_tipo_lancamento.setCurrentIndex(0)
                    self.input_valor_lancamento.setText(str(compra.get('valor_abatimento', 0)))
                # Preenche status
                idx_status = self.combo_status.findText(compra['status'])
                self.combo_status.setCurrentIndex(idx_status if idx_status >= 0 else 0)
                # Considerar no saldo
                self.checkbox_considerar_no_saldo.setChecked(compra.get('considerar_no_saldo_movimentacao', True))
                # Atualiza tabela de itens
                self.atualizar_tabela_itens_adicionados()
                # Ao salvar, chame função que atualiza origem para "compras"
            return  # Interrompe o fluxo normal aqui
        linha = self.tabela_ativa().currentRow()
        if linha < 0:
            QMessageBox.information(self, "Editar Compra", "Selecione uma compra para editar.")
            return
        compra_id_item = self.tabela_ativa().item(linha, 0)
        if compra_id_item is None:
            return
        compra_id = int(compra_id_item.text())

        def tarefa_db():
            from .compras_db import obter_dados_para_editar_compra
            return obter_dados_para_editar_compra(compra_id)

        self.worker_edit = WorkerThread(tarefa_db)
        self.worker_edit.finished.connect(lambda dados: self._preencher_edicao_compra(compra_id, dados))
        self.worker_edit.erro.connect(self._mostrar_erro_thread)
        self.worker_edit.start()

    def _preencher_edicao_compra(self, compra_id, resultado):
        compra, itens, valor_adiantamento = resultado

        if compra is None:
            QMessageBox.warning(self, "Erro", "Compra não encontrada.")
            return

        idx_fornecedor = self.combo_fornecedor.findData(compra['fornecedor_id'])
        self.combo_fornecedor.setCurrentIndex(idx_fornecedor if idx_fornecedor >= 0 else 0)

        # Data pode precisar ser convertida para QDate corretamente
        if isinstance(compra['data_compra'], QDate):
            self.input_data.setDate(compra['data_compra'])
        else:
            # Tenta converter de str para QDate
            try:
                self.input_data.setDate(QDate.fromString(str(compra['data_compra']), "yyyy-MM-dd"))
            except Exception:
                self.input_data.setDate(QDate.currentDate())

        # Atualiza combo e campo de valor conforme o tipo de lançamento
        if valor_adiantamento > 0:
            self.combo_tipo_lancamento.setCurrentIndex(1)  # Adiantamento
            self.input_valor_lancamento.setText(str(valor_adiantamento))
        else:
            self.combo_tipo_lancamento.setCurrentIndex(0)  # Abatimento
            self.input_valor_lancamento.setText(str(compra.get('valor_abatimento', 0)))

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

    def tabela_ativa(self):
        aba_idx = self.tabs.currentIndex()
        if aba_idx == 0:
            return self.tabela_compras_aberto
        elif aba_idx == 1:
            return self.tabela_compras_app
        else:
            return self.tabela_compras_concluidas

    @requer_permissao(['admin', 'gerente', 'operador'])
    def alterar_status_compra(self):
        aba_idx = self.tabs.currentIndex()
        if aba_idx == 0:
            tabela = self.tabela_compras_aberto
        elif aba_idx == 1:
            tabela = self.tabela_compras_app
        else:
            tabela = self.tabela_compras_concluidas

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

    @requer_permissao(['admin', 'gerente'])
    def excluir_compra_finalizada(self):
        aba_idx = self.tabs.currentIndex()
        if aba_idx == 0:
            tabela = self.tabela_compras_aberto
        elif aba_idx == 1:
            tabela = self.tabela_compras_app
        else:
            tabela = self.tabela_compras_concluidas

        linha = tabela.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Excluir Compra", "Selecione uma compra para excluir.")
            return

        compra_id_item = tabela.item(linha, 0)
        if compra_id_item is None:
            return

        compra_id = int(compra_id_item.text())

        _, valor_abatimento, _ = obter_itens_e_lancamentos_da_compra(compra_id)
        if valor_abatimento and valor_abatimento > 0:
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
            excluir_compra(compra_id)
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

        fornecedor_id = obter_fornecedor_id_por_numero_balanca(numero)
        if fornecedor_id:
            idx = combo_fornecedor.findData(fornecedor_id)
            if idx >= 0:
                combo_fornecedor.setCurrentIndex(idx)
                if hasattr(self, 'selecionar_categoria_do_fornecedor'):
                    self.selecionar_categoria_do_fornecedor(fornecedor_id)
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
        self.input_quantidade.clear()
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
            tabela = self.tabela_ativa()
        compra_id_item = tabela.item(row, 0)
        if compra_id_item is None:
            return

        compra_id = int(compra_id_item.text())
        itens = self.itens_por_compra.get(compra_id, [])
        _, valor_abatimento, valor_adiantamento = obter_itens_e_lancamentos_da_compra(compra_id)

        subtotal = float(sum(item["total"] for item in itens))

        # PATCH: Só mostra "Nº Fardos" se algum item tiver valor não nulo e sempre na última coluna
        mostrar_coluna_fardos = any(
            item.get("numero_fardos") not in (None, "", 0) for item in itens
        )
        colunas = ["Produto", "Qtd", "Preço Unit.", "Total"]
        if mostrar_coluna_fardos:
            colunas.append("Nº Fardos")
        self.tabela_itens_compra.setColumnCount(len(colunas))
        self.tabela_itens_compra.setHorizontalHeaderLabels(colunas)

        linhas_extra = 1
        self.tabela_itens_compra.setRowCount(len(itens) + linhas_extra)
        for i, item in enumerate(itens):
            self.tabela_itens_compra.setItem(i, 0, QTableWidgetItem(item['produto_nome']))
            self.tabela_itens_compra.setItem(i, 1, QTableWidgetItem(str(item['quantidade'])))
            preco_formatado = self.locale.toString(float(item['preco_unitario']), 'f', 2)
            total_formatado = self.locale.toString(float(item['total']), 'f', 2)
            self.tabela_itens_compra.setItem(i, 2, QTableWidgetItem(preco_formatado))
            self.tabela_itens_compra.setItem(i, 3, QTableWidgetItem(total_formatado))
            if mostrar_coluna_fardos:
                nfardos = item.get("numero_fardos")
                self.tabela_itens_compra.setItem(i, 4,
                                                 QTableWidgetItem(str(nfardos) if nfardos not in (None, "", 0) else ""))

        # Linha para abatimento ou adiantamento
        idx_extra = len(itens)
        if valor_adiantamento > 0:
            self.tabela_itens_compra.setItem(idx_extra, 0, QTableWidgetItem("Adiantamento"))
            self.tabela_itens_compra.setItem(idx_extra, 1, QTableWidgetItem(""))
            self.tabela_itens_compra.setItem(idx_extra, 2, QTableWidgetItem(""))
            self.tabela_itens_compra.setItem(idx_extra, 3,
                                             QTableWidgetItem(f"+{self.locale.toString(valor_adiantamento, 'f', 2)}"))
            if mostrar_coluna_fardos:
                self.tabela_itens_compra.setItem(idx_extra, 4, QTableWidgetItem(""))
            total_final = subtotal + valor_adiantamento
            self.label_total_com_abatimento.setText(
                f"Total com Adiantamento: R$ {self.locale.toString(total_final, 'f', 2)}"
            )
        else:
            self.tabela_itens_compra.setItem(idx_extra, 0, QTableWidgetItem("Abatimento"))
            self.tabela_itens_compra.setItem(idx_extra, 1, QTableWidgetItem(""))
            self.tabela_itens_compra.setItem(idx_extra, 2, QTableWidgetItem(""))
            self.tabela_itens_compra.setItem(idx_extra, 3,
                                             QTableWidgetItem(f"-{self.locale.toString(valor_abatimento, 'f', 2)}"))
            if mostrar_coluna_fardos:
                self.tabela_itens_compra.setItem(idx_extra, 4, QTableWidgetItem(""))
            total_final = subtotal - valor_abatimento
            self.label_total_com_abatimento.setText(
                f"Total com Abatimento: R$ {self.locale.toString(total_final, 'f', 2)}"
            )
        self.atualizar_campo_texto_copiavel()

    def carregar_fornecedores(self):
        self.combo_fornecedor.clear()
        self.filtro_combo_fornecedor.clear()
        self.filtro_combo_fornecedor.addItem("Todos os Fornecedores", None)
        self.combo_fornecedor.addItem("", None)
        for f in listar_fornecedores():
            self.combo_fornecedor.addItem(f["nome"], f["id"])
            self.filtro_combo_fornecedor.addItem(f["nome"], f["id"])

    def carregar_produtos(self):
        self.combo_produto.blockSignals(True)
        self.combo_produto.clear()
        self.combo_produto.setEditable(True)
        produtos = listar_produtos()
        produtos.sort(key=lambda p: p["nome"])
        for p in produtos:
            self.combo_produto.addItem(p['nome'], p['id'])
        self.combo_produto.setCurrentIndex(-1)
        self.combo_produto.blockSignals(False)

    @requer_permissao(['admin', 'gerente', 'operador'])
    def atualizar_item_editado(self, row, column):
        if row < 0 or row >= len(self.itens_compra):
            return

        try:
            if column == 1:  # Quantidade
                nova_qtd = int(self.tabela_itens_adicionados.item(row, 1).text())
                self.itens_compra[row]['quantidade'] = nova_qtd
            elif column == 2:  # Preço unitário
                novo_preco_str = self.tabela_itens_adicionados.item(row, 2).text().replace(',', '.')
                novo_preco = Decimal(novo_preco_str)
                self.itens_compra[row]['preco'] = novo_preco
            elif column == 4:  # Número de fardos
                novo_nfardos_str = self.tabela_itens_adicionados.item(row, 4).text()
                self.itens_compra[row]['numero_fardos'] = int(novo_nfardos_str) if novo_nfardos_str else None

            qtd = self.itens_compra[row]['quantidade']
            preco = self.itens_compra[row]['preco']
            self.itens_compra[row]['total'] = Decimal(qtd) * Decimal(preco)

            self.atualizar_tabela_itens_adicionados()

        except Exception:
            QMessageBox.warning(self, "Erro", "Valor inválido. Digite um número válido.")

    def set_janela_debitos(self, janela_debitos):
        self.janela_debitos = janela_debitos

    @requer_permissao(['admin', 'gerente', 'operador', 'consulta'])
    def exportar_compra_pdf(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        compra_id = self.obter_compra_id_selecionado()
        if compra_id is None:
            QMessageBox.warning(self, "Exportar PDF", "Selecione uma compra para exportar.")
            return

        def tarefa_pdf():
            from .compras_db import obter_detalhes_compra, obter_saldo_devedor_fornecedor
            from .compras_export import exportar_compra_pdf
            compra, itens = obter_detalhes_compra(compra_id)
            saldo = obter_saldo_devedor_fornecedor(compra['fornecedor_id'])
            filename = f"compra_{compra_id}.pdf"
            exportar_compra_pdf(compra, itens, saldo, filename,
                                marca_dagua_texto=str(compra.get('fornecedores_numerobalanca', '')))
            return filename

        self.worker_pdf = WorkerThread(tarefa_pdf)
        self.worker_pdf.finished.connect(
            lambda filename: QMessageBox.information(self, "PDF gerado", f"Arquivo: {filename}"))
        self.worker_pdf.erro.connect(self._mostrar_erro_thread)
        self.worker_pdf.start()

    @requer_permissao(['admin', 'gerente', 'operador', 'consulta'])
    def exportar_compra_jpg(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        compra_id = self.obter_compra_id_selecionado()
        if compra_id is None:
            QMessageBox.warning(self, "Exportar JPG", "Selecione uma compra para exportar.")
            return

        def tarefa_jpg():
            from .compras_db import obter_detalhes_compra, obter_saldo_devedor_fornecedor
            from .compras_export import exportar_compra_jpg
            compra, itens = obter_detalhes_compra(compra_id)
            saldo = obter_saldo_devedor_fornecedor(compra['fornecedor_id'])
            filename = f"compra_{compra_id}.jpg"
            exportar_compra_jpg(compra, itens, saldo, filename,
                                marca_dagua_texto=str(compra.get('fornecedores_numerobalanca', '')))
            return filename

        self.worker_jpg = WorkerThread(tarefa_jpg)
        self.worker_jpg.finished.connect(
            lambda filename: QMessageBox.information(self, "JPG gerado", f"Arquivo: {filename}"))
        self.worker_jpg.erro.connect(self._mostrar_erro_thread)
        self.worker_jpg.start()

    def closeEvent(self, event):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        if hasattr(self, "worker_pdf") and self.worker_pdf.isRunning():
            self.worker_pdf.quit()
            self.worker_pdf.wait()
        if hasattr(self, "worker_jpg") and self.worker_jpg.isRunning():
            self.worker_jpg.quit()
            self.worker_jpg.wait()
        event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        self.atualizar_tabelas()
        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id is not None:
            self.carregar_categorias_para_fornecedor(fornecedor_id)
            self.atualizar_saldo_fornecedor()
            self.carregar_produtos()

if __name__ == "__main__":
    app = QApplication([])
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    window = ComprasUI()
    window.resize(1200, 600)
    window.show()
    sys.exit(app.exec())