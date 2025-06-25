import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QComboBox, QDateEdit, QLineEdit, QSpinBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt, QDate, QLocale
from decimal import Decimal
from db_context import get_cursor

class MovimentacoesUI(QWidget):
    STATUS_LIST = [
        "Compra", "Venda", "Transação"
    ]
    DIRECAO_LIST = [
        "Entrada", "Saída"
    ]

    def __init__(self):
        super().__init__()
        self.locale = QLocale(QLocale.Portuguese, QLocale.Brazil)
        self.itens_movimentacao = []
        self.movimentacao_edit_id = None
        self.init_ui()
        self.carregar_fornecedores()
        self.carregar_produtos()
        self.atualizar_tabela()

    # ------- DB helpers -------
    def listar_fornecedores(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome, fornecedores_numerobalanca FROM fornecedores ORDER BY nome")
            return cursor.fetchall()

    def listar_produtos(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome, preco_base FROM produtos ORDER BY nome")
            return cursor.fetchall()

    def listar_movimentacoes(self, data_de=None, data_ate=None, fornecedor_id=None):
        query = """
            SELECT m.id, m.data, m.tipo, m.direcao, m.descricao, m.valor_operacao,
                   f.nome AS fornecedor_nome, f.fornecedores_numerobalanca
            FROM movimentacoes m
            JOIN fornecedores f ON m.fornecedor_id = f.id
            WHERE 1=1
        """
        params = []
        if data_de:
            query += " AND m.data >= %s"
            params.append(data_de)
        if data_ate:
            query += " AND m.data <= %s"
            params.append(data_ate)
        if fornecedor_id:
            query += " AND m.fornecedor_id = %s"
            params.append(fornecedor_id)
        query += " ORDER BY m.data DESC, m.id DESC"

        with get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def listar_itens_movimentacao(self, movimentacao_id):
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT i.id, p.nome AS produto_nome, i.produto_id, i.quantidade, i.preco_unitario
                FROM itens_movimentacao i
                JOIN produtos p ON i.produto_id = p.id
                WHERE i.movimentacao_id = %s
            """, (movimentacao_id,))
            return cursor.fetchall()

    # ------- UI & lógica -------
    def init_ui(self):
        layout_root = QHBoxLayout(self)

        # ----------- ESQUERDA: Cadastro/edição -----------
        layout_esq = QVBoxLayout()

        form_grid = QGridLayout()
        self.combo_fornecedor = QComboBox()
        self.combo_fornecedor.setEditable(True)
        self.input_num_balanca = QLineEdit()
        self.input_num_balanca.setPlaceholderText("Número balança")
        self.input_num_balanca.editingFinished.connect(
            lambda: self.selecionar_fornecedor_por_numero_balanca(self.input_num_balanca, self.combo_fornecedor)
        )
        form_grid.addWidget(QLabel("Número na Balança"), 0, 0)
        form_grid.addWidget(self.input_num_balanca, 0, 1)
        form_grid.addWidget(QLabel("Fornecedor"), 1, 0)
        form_grid.addWidget(self.combo_fornecedor, 1, 1)
        self.input_data = QDateEdit()
        self.input_data.setDate(QDate.currentDate())
        self.input_data.setCalendarPopup(True)
        form_grid.addWidget(QLabel("Data"), 2, 0)
        form_grid.addWidget(self.input_data, 2, 1)
        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(self.STATUS_LIST)
        form_grid.addWidget(QLabel("Tipo"), 3, 0)
        form_grid.addWidget(self.combo_tipo, 3, 1)
        self.combo_direcao = QComboBox()
        self.combo_direcao.addItems(self.DIRECAO_LIST)
        self.combo_direcao.setVisible(False)
        self.label_direcao = QLabel("Direção:")
        self.label_direcao.setVisible(False)
        form_grid.addWidget(self.label_direcao, 4, 0)
        form_grid.addWidget(self.combo_direcao, 4, 1)
        self.input_descricao = QLineEdit()
        form_grid.addWidget(QLabel("Descrição"), 5, 0)
        form_grid.addWidget(self.input_descricao, 5, 1)

        self.input_valor_operacao = QLineEdit()
        self.input_valor_operacao.setPlaceholderText("Ex: 1000,00")
        self.label_valor_operacao = QLabel("Valor Operação:")
        form_grid.addWidget(self.label_valor_operacao, 6, 0)
        form_grid.addWidget(self.input_valor_operacao, 6, 1)
        self.input_valor_operacao.setVisible(False)
        self.label_valor_operacao.setVisible(False)

        # Adição de itens (só para compra/venda)
        self.layout_produto = QGridLayout()
        self.combo_produto = QComboBox()
        self.input_quantidade = QSpinBox()
        self.input_quantidade.setMinimum(1)
        self.input_quantidade.setMaximum(99999)
        self.input_preco = QLineEdit()
        self.input_preco.setPlaceholderText("Ex: 10,00")
        self.layout_produto.addWidget(QLabel("Produto"), 0, 0)
        self.layout_produto.addWidget(self.combo_produto, 0, 1)
        self.layout_produto.addWidget(QLabel("Quantidade"), 1, 0)
        self.layout_produto.addWidget(self.input_quantidade, 1, 1)
        self.layout_produto.addWidget(QLabel("Valor unitário"), 2, 0)
        self.layout_produto.addWidget(self.input_preco, 2, 1)
        btn_add_item = QPushButton("Adicionar Produto")
        btn_add_item.clicked.connect(self.adicionar_item)
        self.layout_produto.addWidget(btn_add_item, 3, 0, 1, 2)
        form_grid.addLayout(self.layout_produto, 7, 0, 1, 2)

        self.tabela_itens_adicionados = QTableWidget()
        self.tabela_itens_adicionados.setColumnCount(4)
        self.tabela_itens_adicionados.setHorizontalHeaderLabels(["Produto", "Qtd", "Valor Unit.", "Total"])
        self.tabela_itens_adicionados.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        form_grid.addWidget(QLabel("Itens da movimentação (antes de salvar):"), 8, 0, 1, 2)
        form_grid.addWidget(self.tabela_itens_adicionados, 9, 0, 1, 2)

        btn_remover_item = QPushButton("Remover Item Selecionado")
        btn_remover_item.clicked.connect(self.remover_item)
        form_grid.addWidget(btn_remover_item, 10, 0, 1, 2)

        btn_limpar_itens = QPushButton("Limpar Itens")
        btn_limpar_itens.clicked.connect(self.limpar_itens)
        form_grid.addWidget(btn_limpar_itens, 11, 0, 1, 2)

        btn_finalizar = QPushButton("Salvar Movimentação")
        btn_finalizar.clicked.connect(self.finalizar_movimentacao)
        form_grid.addWidget(btn_finalizar, 12, 0, 1, 2)

        btn_excluir_mov = QPushButton("Excluir Movimentação Selecionada")
        btn_excluir_mov.clicked.connect(self.excluir_movimentacao)
        form_grid.addWidget(btn_excluir_mov, 13, 0, 1, 2)

        layout_esq.addLayout(form_grid)
        layout_esq.addStretch()
        layout_root.addLayout(layout_esq, 1)

        # ----------- MEIO: Filtros + tabela movimentações -----------
        layout_meio = QVBoxLayout()

        # Filtros (modificado para empilhar "de", "até" e "filtrar" embaixo)
        layout_filtros = QVBoxLayout()
        # Primeira linha: número da balança e fornecedor
        row1 = QHBoxLayout()
        self.filtro_numero_balanca = QLineEdit()
        self.filtro_numero_balanca.setPlaceholderText("Número da balança")
        row1.addWidget(QLabel("Nº Balança:"))
        row1.addWidget(self.filtro_numero_balanca)
        self.filtro_combo_fornecedor = QComboBox()
        self.filtro_combo_fornecedor.setEditable(True)
        row1.addWidget(QLabel("Fornecedor:"))
        row1.addWidget(self.filtro_combo_fornecedor)
        layout_filtros.addLayout(row1)

        # Segunda linha: de, até, filtrar
        row2 = QHBoxLayout()
        self.filtro_data_de = QDateEdit()
        self.filtro_data_de.setCalendarPopup(True)
        self.filtro_data_de.setDate(QDate.currentDate().addMonths(-1))
        row2.addWidget(QLabel("De:"))
        row2.addWidget(self.filtro_data_de)
        self.filtro_data_ate = QDateEdit()
        self.filtro_data_ate.setCalendarPopup(True)
        self.filtro_data_ate.setDate(QDate.currentDate())
        row2.addWidget(QLabel("Até:"))
        row2.addWidget(self.filtro_data_ate)
        btn_filtrar = QPushButton("Filtrar")
        btn_filtrar.clicked.connect(self.atualizar_tabela)
        row2.addWidget(btn_filtrar)
        layout_filtros.addLayout(row2)

        layout_meio.addLayout(layout_filtros)

        self.filtro_numero_balanca.editingFinished.connect(
            lambda: self.selecionar_fornecedor_por_numero_balanca(self.filtro_numero_balanca,
                                                                  self.filtro_combo_fornecedor)
        )

        self.tabela_movimentacoes = QTableWidget()
        self.tabela_movimentacoes.setColumnCount(7)
        self.tabela_movimentacoes.setHorizontalHeaderLabels([
            "ID", "Data", "Tipo", "Direção", "Fornecedor", "Descrição", "Valor Operação"
        ])
        self.tabela_movimentacoes.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_movimentacoes.cellClicked.connect(self.mostrar_itens_movimentacao)
        self.tabela_movimentacoes.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout_meio.addWidget(self.tabela_movimentacoes)

        layout_root.addLayout(layout_meio, 1)

        # ----------- DIREITA: Tabela itens da movimentação selecionada -----------
        layout_dir = QVBoxLayout()
        layout_dir.addWidget(QLabel("Itens da movimentação selecionada:"))
        self.tabela_itens = QTableWidget()
        self.tabela_itens.setColumnCount(4)
        self.tabela_itens.setHorizontalHeaderLabels(["Produto", "Qtd", "Valor Unit.", "Total"])
        self.tabela_itens.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_itens.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout_dir.addWidget(self.tabela_itens)
        layout_root.addLayout(layout_dir, 4)

        # Agora que todos widgets estão criados, conecte o sinal e chame tipo_changed
        self.combo_tipo.currentTextChanged.connect(self.tipo_changed)
        self.tipo_changed()

    def tipo_changed(self):
        is_transacao = self.combo_tipo.currentText() == "Transação"
        # Esconde/adiciona campos e layouts
        self.combo_direcao.setVisible(is_transacao)
        self.label_direcao.setVisible(is_transacao)
        self.input_valor_operacao.setVisible(is_transacao)
        self.label_valor_operacao.setVisible(is_transacao)

        # Itens de produto/quantidade/etc só aparecem para compra/venda
        for i in range(self.layout_produto.count()):
            widget = self.layout_produto.itemAt(i).widget()
            if widget:
                widget.setVisible(not is_transacao)
        self.tabela_itens_adicionados.setVisible(not is_transacao)
        # Também rótulo e botões dos itens
        for idx in [8, 9, 10, 11]:  # linhas do grid que são para os itens
            item = self.layout_produto.parent().itemAtPosition(idx, 0)
            if item:
                widget = item.widget()
                if widget:
                    widget.setVisible(not is_transacao)

    def carregar_fornecedores(self):
        self.combo_fornecedor.clear()
        self.filtro_combo_fornecedor.clear()
        fornecedores = self.listar_fornecedores()
        self.fornecedores = fornecedores
        self.combo_fornecedor.addItem("Selecione um fornecedor", None)
        self.filtro_combo_fornecedor.addItem("Todos", None)
        for f in fornecedores:
            label = f"{f['nome']} - Balança {f['fornecedores_numerobalanca']}"
            self.combo_fornecedor.addItem(label, f['id'])
            self.filtro_combo_fornecedor.addItem(label, f['id'])

    def carregar_produtos(self):
        self.combo_produto.clear()
        produtos = self.listar_produtos()
        self.produtos = produtos
        self.combo_produto.addItem("Selecione um produto", None)
        for p in produtos:
            self.combo_produto.addItem(p["nome"], p["id"])

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
        else:
            QMessageBox.warning(self, "Fornecedor não encontrado", f"Nenhum fornecedor com número de balança {numero}.")
            campo_input.clear()

    def adicionar_item(self):
        produto_id = self.combo_produto.currentData()
        quantidade = self.input_quantidade.value()
        if produto_id is None or quantidade <= 0:
            QMessageBox.warning(self, "Erro", "Selecione um produto e uma quantidade válida.")
            return
        produto = next((p for p in self.produtos if p["id"] == produto_id), None)
        if produto is None:
            QMessageBox.critical(self, "Erro", "Produto não encontrado.")
            return
        try:
            preco = Decimal(self.input_preco.text().replace(",", "."))
        except Exception:
            QMessageBox.warning(self, "Erro", "Digite um valor unitário válido.")
            return
        total = preco * quantidade
        self.itens_movimentacao.append({
            "produto_id": produto_id,
            "nome": produto["nome"],
            "quantidade": quantidade,
            "preco": preco,
            "total": total
        })
        self.atualizar_tabela_itens_adicionados()
        self.combo_produto.setCurrentIndex(0)
        self.input_quantidade.setValue(1)
        self.input_preco.clear()

    def atualizar_tabela_itens_adicionados(self):
        self.tabela_itens_adicionados.setRowCount(len(self.itens_movimentacao))
        for i, item in enumerate(self.itens_movimentacao):
            self.tabela_itens_adicionados.setItem(i, 0, QTableWidgetItem(item["nome"]))
            self.tabela_itens_adicionados.setItem(i, 1, QTableWidgetItem(str(item["quantidade"])))
            preco_formatado = self.locale.toString(float(item['preco']), 'f', 2)
            total_formatado = self.locale.toString(float(item['total']), 'f', 2)
            self.tabela_itens_adicionados.setItem(i, 2, QTableWidgetItem(preco_formatado))
            self.tabela_itens_adicionados.setItem(i, 3, QTableWidgetItem(total_formatado))

    def remover_item(self):
        selected = self.tabela_itens_adicionados.currentRow()
        if selected >= 0:
            del self.itens_movimentacao[selected]
            self.atualizar_tabela_itens_adicionados()

    def limpar_itens(self):
        self.itens_movimentacao = []
        self.atualizar_tabela_itens_adicionados()

    def finalizar_movimentacao(self):
        tipo = self.combo_tipo.currentText().lower()
        fornecedor_id = self.combo_fornecedor.currentData()
        data = self.input_data.date().toPython()
        direcao = self.combo_direcao.currentText().lower() if tipo == "transação" else None
        descricao = self.input_descricao.text().strip()
        if fornecedor_id is None or fornecedor_id == 0:
            QMessageBox.warning(self, "Erro", "Selecione um fornecedor.")
            return
        if tipo == "transação":
            try:
                valor_operacao = Decimal(self.input_valor_operacao.text().replace(",", "."))
            except Exception:
                QMessageBox.warning(self, "Erro", "Digite um valor válido para a operação.")
                return
        else:
            valor_operacao = None
            if not self.itens_movimentacao:
                QMessageBox.warning(self, "Erro", "Adicione pelo menos um item antes de salvar.")
                return
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO movimentacoes (fornecedor_id, data, tipo, direcao, descricao, valor_operacao) VALUES (%s, %s, %s, %s, %s, %s)",
                (fornecedor_id, data, tipo, direcao, descricao, valor_operacao)
            )
            movimentacao_id = cursor.lastrowid
            if tipo != "transação":
                for item in self.itens_movimentacao:
                    cursor.execute(
                        "INSERT INTO itens_movimentacao (movimentacao_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)",
                        (movimentacao_id, item["produto_id"], item["quantidade"], item["preco"])
                    )
        QMessageBox.information(self, "Sucesso", "Movimentação cadastrada com sucesso.")
        self.limpar_campos()
        self.limpar_itens()
        self.atualizar_tabela()

    def limpar_campos(self):
        self.combo_fornecedor.setCurrentIndex(0)
        self.input_num_balanca.clear()
        self.input_data.setDate(QDate.currentDate())
        self.combo_tipo.setCurrentIndex(0)
        self.combo_direcao.setCurrentIndex(0)
        self.input_descricao.clear()
        self.input_valor_operacao.clear()
        self.tipo_changed()

    def atualizar_tabela(self):
        fornecedor_id = self.filtro_combo_fornecedor.currentData()
        data_de = self.filtro_data_de.date().toPython()
        data_ate = self.filtro_data_ate.date().toPython()
        movimentacoes = self.listar_movimentacoes(data_de, data_ate, fornecedor_id)
        self.tabela_movimentacoes.setRowCount(len(movimentacoes))
        for i, m in enumerate(movimentacoes):
            self.tabela_movimentacoes.setItem(i, 0, QTableWidgetItem(str(m["id"])))
            self.tabela_movimentacoes.setItem(i, 1, QTableWidgetItem(str(m["data"])))
            self.tabela_movimentacoes.setItem(i, 2, QTableWidgetItem(m["tipo"].capitalize()))
            self.tabela_movimentacoes.setItem(i, 3, QTableWidgetItem(m["direcao"].capitalize() if m["direcao"] else ""))
            self.tabela_movimentacoes.setItem(i, 4, QTableWidgetItem(m["fornecedor_nome"]))
            self.tabela_movimentacoes.setItem(i, 5, QTableWidgetItem(m["descricao"] or ""))
            valor_op = m.get("valor_operacao")
            if valor_op is not None:
                valor_op = self.locale.toString(float(valor_op), 'f', 2)
            else:
                valor_op = ""
            self.tabela_movimentacoes.setItem(i, 6, QTableWidgetItem(valor_op))

    def mostrar_itens_movimentacao(self, row, col):
        item = self.tabela_movimentacoes.item(row, 0)
        if not item:
            return
        movimentacao_id = int(item.text())
        tipo = self.tabela_movimentacoes.item(row, 2).text().lower()
        if tipo == "transação":
            self.tabela_itens.setRowCount(0)
            return
        itens = self.listar_itens_movimentacao(movimentacao_id)
        self.tabela_itens.setRowCount(len(itens))
        for i, item in enumerate(itens):
            self.tabela_itens.setItem(i, 0, QTableWidgetItem(item["produto_nome"]))
            self.tabela_itens.setItem(i, 1, QTableWidgetItem(str(item["quantidade"])))
            preco_formatado = self.locale.toString(float(item['preco_unitario']), 'f', 2)
            total_formatado = self.locale.toString(float(item['preco_unitario'] * item['quantidade']), 'f', 2)
            self.tabela_itens.setItem(i, 2, QTableWidgetItem(preco_formatado))
            self.tabela_itens.setItem(i, 3, QTableWidgetItem(total_formatado))

    def excluir_movimentacao(self):
        row = self.tabela_movimentacoes.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Atenção", "Selecione uma movimentação na tabela para excluir.")
            return

        movimentacao_id_item = self.tabela_movimentacoes.item(row, 0)
        if not movimentacao_id_item:
            return
        movimentacao_id = int(movimentacao_id_item.text())

        resposta = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            f"Tem certeza que deseja excluir a movimentação ID {movimentacao_id}?\n"
            f"Todos os itens dessa movimentação também serão apagados.",
            QMessageBox.Yes | QMessageBox.No
        )
        if resposta != QMessageBox.Yes:
            return

        try:
            with get_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM itens_movimentacao WHERE movimentacao_id = %s", (movimentacao_id,))
                cursor.execute("DELETE FROM movimentacoes WHERE id = %s", (movimentacao_id,))
            QMessageBox.information(self, "Sucesso", "Movimentação excluída com sucesso.")
            self.atualizar_tabela()
            self.tabela_itens.setRowCount(0)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao excluir movimentação: {e}")

if __name__ == "__main__":
    app = QApplication([])
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    window = MovimentacoesUI()
    window.resize(1200, 700)
    window.show()
    sys.exit(app.exec())