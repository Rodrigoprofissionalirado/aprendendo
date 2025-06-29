import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QComboBox, QDateEdit, QLineEdit,
    QSpinBox, QTableWidget, QTableWidgetItem, QMessageBox, QTabWidget
)
from PySide6.QtCore import Qt, QTimer, QDate, QLocale, QEvent
from decimal import Decimal
from status_delegate_combo import StatusComboDelegate
from utils_permissoes import requer_permissao

# Importações dos submódulos
from compras_db import (
    listar_fornecedores, listar_contas_do_fornecedor, listar_produtos,
    obter_produto, listar_compras, adicionar_compra, atualizar_compra,
    listar_itens_compra, obter_fornecedor_id_da_compra, obter_detalhes_compra,
    obter_total_produtos, obter_valor_com_abatimento_adiantamento, obter_saldo_devedor_fornecedor,
    buscar_nome_conta_padrao, obter_categorias_do_fornecedor, inserir_abatimento,
    obter_ajuste_fixo, obter_id_categoria_padrao, inserir_adiantamento, remover_lancamentos_antigos,
    obter_dados_para_editar_compra, obter_itens_e_lancamentos_da_compra, excluir_compra,
    obter_fornecedor_id_por_numero_balanca, obter_primeira_categoria_do_fornecedor,
    obter_dados_bancarios_para_campo_copiavel
)
from compras_logic import (
    obter_total_produtos_lista, calcular_valor_com_abatimento_adiantamento, formatar_moeda
)
from compras_export import (
    exportar_compra_pdf, exportar_compra_jpg
)
from compras_dialogs import DiferencaCompraDialog

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
    # Todos os métodos de acesso ao banco foram movidos para compras_db.py

    # ---- Métodos de lógica ----
    # Todos os métodos de cálculo/ajuda foram movidos para compras_logic.py

    # ---- Métodos de exportação ----
    # Todos os métodos de exportação foram movidos para compras_export.py

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
        self.combo_produto.setEditable(True)
        self.combo_produto.currentIndexChanged.connect(self.zerar_quantidade)
        self.input_quantidade = QSpinBox()
        self.input_quantidade.setMinimum(1)
        self.input_quantidade.setMaximum(9999)
        # Atalhos de ENTER entre campos
        self.combo_produto.lineEdit().returnPressed.connect(self.focus_quantidade)
        self.input_quantidade.installEventFilter(self)
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
        for f in listar_fornecedores():
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
        for p in listar_produtos():
            self.combo_produto.addItem(p['nome'], p['id'])
        self.combo_produto.setCurrentIndex(-1)
        self.combo_produto.blockSignals(False)
        self.atualizar_tabelas()

    def mostrar_dialog_diferenca(self, diferenca):
        dialog = DiferencaCompraDialog(diferenca, self)
        if dialog.exec() == QDialog.Accepted:
            return dialog.resultado
        return None

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
        self.btn_adicionar_item.click()
        self.combo_produto.setFocus()
        self.combo_produto.lineEdit().selectAll()

    def eventFilter(self, obj, event):
        if obj is self.input_quantidade and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.atalho_enter_quantidade()
                return True
        return super().eventFilter(obj, event)

    @requer_permissao(['admin', 'gerente', 'operador'])
    def abrir_dialog_troca_conta_fornecedor(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox, QComboBox, QLabel, QMessageBox

        compra_id = obter_compra_id_selecionado()
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
            compra_id_local = obter_compra_id_selecionado()
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
        compras_aberto = listar_compras(
            status=None if status_filtro == "Concluída" else status_filtro,
            status_not="Concluída",
            data_de=data_de,
            data_ate=data_ate,
            fornecedor_id=fornecedor_id
        )
        # Concluídas: só concluída
        compras_concluidas = listar_compras(
            status="Concluída",
            data_de=data_de,
            data_ate=data_ate,
            fornecedor_id=fornecedor_id
        )
        self.preencher_tabela_compras(self.tabela_compras_aberto, compras_aberto)
        self.preencher_tabela_compras(self.tabela_compras_concluidas, compras_concluidas)

    def preencher_tabela_compras(self, tabela, compras):
        tabela.blockSignals(True)
        try:
            tabela.setRowCount(len(compras))
            for i, c in enumerate(compras):
                tabela.setItem(i, 0, QTableWidgetItem(str(c['id'])))
                tabela.setItem(i, 1, QTableWidgetItem(c['fornecedor_nome']))
                tabela.setItem(i, 2, QTableWidgetItem(str(c['data'])))
                total_produtos = obter_total_produtos(c['id'])
                tabela.setItem(i, 3, QTableWidgetItem(self.locale.toString(float(total_produtos), 'f', 2)))
                valor_final = obter_valor_com_abatimento_adiantamento(c['id'], total_produtos)
                tabela.setItem(i, 4, QTableWidgetItem(self.locale.toString(float(valor_final), 'f', 2)))
                tabela.setItem(i, 5, QTableWidgetItem(c['status']))
                pass
        finally:
            tabela.blockSignals(False)

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

    def atualizar_saldo_fornecedor(self):
        fornecedor_id = self.combo_fornecedor.currentData()
        if not fornecedor_id:
            self.label_saldo_fornecedor.setText("Saldo devedor: R$ 0,00")
            self.label_saldo_fornecedor.setStyleSheet(
                "font-weight: bold; color: #808080; font-size: 13px; text-decoration: underline; cursor: pointer;")
            return

        saldo = float(obter_saldo_devedor_fornecedor(fornecedor_id))

        # Define texto e cor de acordo com o saldo
        if saldo > 0:
            texto = f"Saldo devedor: R$ {self.locale.toString(abs(saldo), 'f', 2)}"
            cor = "#b22222"  # vermelho
        elif saldo < 0:
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
        if fornecedor_id and hasattr(self, 'janela_debitos'):
            if hasattr(self.janela_debitos, "filtrar_por_fornecedor"):
                self.janela_debitos.filtrar_por_fornecedor(fornecedor_id)
            if hasattr(self, "main_window"):
                index = self.main_window.stack.indexOf(self.janela_debitos)
                self.main_window.stack.setCurrentIndex(index)

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
            carregar_categorias_para_fornecedor(fornecedor_id)
            selecionar_categoria_do_fornecedor(fornecedor_id)
            self.atualizar_saldo_fornecedor()

    @requer_permissao(['admin', 'gerente', 'operador'])
    def adicionar_item(self):
        produto_id = self.combo_produto.currentData()
        quantidade = self.input_quantidade.value()
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

        self.itens_compra.append({
            "produto_id": produto_id,
            "nome": produto["nome"],
            "quantidade": quantidade,
            "preco": preco,
            "total": total
        })

        self.atualizar_tabela_itens_adicionados()
        self.combo_produto.setCurrentIndex(-1)
        self.input_quantidade.setValue(1)

    def carregar_categorias_para_fornecedor(self, fornecedor_id):
        self.combo_categoria_temporaria.blockSignals(True)
        self.combo_categoria_temporaria.clear()
        self.combo_categoria_temporaria.addItem("Selecione uma categoria", 0)
        categorias = obter_categorias_do_fornecedor(fornecedor_id)
        for c in categorias:
            self.combo_categoria_temporaria.addItem(c['nome'], c['id'])
        self.combo_categoria_temporaria.setCurrentIndex(1 if self.combo_categoria_temporaria.count() > 1 else 0)

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
        except ValueError:
            QMessageBox.warning(self, "Erro", "Valor de abatimento/adiantamento inválido.")
            return

        tipo_lancamento = self.combo_tipo_lancamento.currentData()
        status = self.combo_status.currentText()

        valor_abatimento = valor_lancamento if tipo_lancamento == "abatimento" else Decimal('0.00')
        valor_inclusao = valor_lancamento if tipo_lancamento == "adiantamento" else Decimal('0.00')

        if self.compra_edit_id is None:
            compra_id = adicionar_compra(
                fornecedor_id, data_compra, valor_abatimento, self.itens_compra, status
            )
            if tipo_lancamento == "adiantamento" and valor_inclusao > 0:
                inserir_adiantamento(fornecedor_id, compra_id, data_compra, valor_inclusao)
            QMessageBox.information(self, "Sucesso", "Compra cadastrada com sucesso.")
        else:
            remover_lancamentos_antigos(self.compra_edit_id)
            # ... atualização de valor_abatimento pode ser função de DB...
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

    @requer_permissao(['admin', 'gerente', 'operador'])
    def editar_compra_finalizada(self):
        linha = self.tabela_compras_aberto.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Editar Compra", "Selecione uma compra para editar.")
            return
        compra_id_item = self.tabela_compras_aberto.item(linha, 0)
        if compra_id_item is None:
            return
        compra_id = int(compra_id_item.text())

        compra, itens, valor_adiantamento = obter_dados_para_editar_compra(compra_id)

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

    @requer_permissao(['admin', 'gerente', 'operador'])
    def alterar_status_compra(self):
        tabela = self.tabela_compras_aberto if self.tabs.currentIndex() == 0 else self.tabela_compras_concluidas
        compra_id = obter_compra_id_selecionado(tabela=tabela)
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
        linha = self.tabela_compras_aberto.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Excluir Compra", "Selecione uma compra para excluir.")
            return

        compra_id_item = self.tabela_compras_aberto.item(linha, 0)
        if compra_id_item is None:
            return

        compra_id = int(compra_id_item.text())

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
        itens, valor_abatimento, valor_adiantamento = obter_itens_e_lancamentos_da_compra(compra_id)

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
        compra_id = obter_compra_id_selecionado()
        if compra_id is None:
            QMessageBox.warning(self, "Exportar PDF", "Selecione uma compra para exportar.")
            return
        compra, itens = obter_detalhes_compra(compra_id)
        saldo = obter_saldo_devedor_fornecedor(compra['fornecedor_id'])
        filename = f"compra_{compra_id}.pdf"
        exportar_compra_pdf(compra, itens, saldo, filename,
                            marca_dagua_texto=str(compra.get('fornecedores_numerobalanca', '')))

    @requer_permissao(['admin', 'gerente', 'operador', 'consulta'])
    def exportar_compra_jpg(self):
        compra_id = obter_compra_id_selecionado()
        if compra_id is None:
            QMessageBox.warning(self, "Exportar JPG", "Selecione uma compra para exportar.")
            return
        compra, itens = obter_detalhes_compra(compra_id)
        saldo = obter_saldo_devedor_fornecedor(compra['fornecedor_id'])
        filename = f"compra_{compra_id}.jpg"
        exportar_compra_jpg(compra, itens, saldo, filename, marca_dagua_texto=str(compra.get('fornecedores_numerobalanca', '')))

    def showEvent(self, event):
        super().showEvent(event)
        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id is not None:
            carregar_categorias_para_fornecedor(fornecedor_id)
            self.atualizar_saldo_fornecedor()
            self.carregar_produtos()

if __name__ == "__main__":
    app = QApplication([])
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    window = ComprasUI()
    window.resize(1200, 600)
    window.show()
    sys.exit(app.exec())