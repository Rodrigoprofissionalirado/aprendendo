import sys
import unicodedata
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QComboBox, QDateEdit, QLineEdit, QSpinBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QSizePolicy, QTabWidget
)
from PySide6.QtCore import Qt, QDate, QLocale
from decimal import Decimal
from db_context import get_cursor

def remove_acento(txt):
    if not txt:
        return ""
    return ''.join(
        c for c in unicodedata.normalize('NFKD', txt)
        if not unicodedata.combining(c)
    ).lower().strip()

class MovimentacaoTabUI(QWidget):
    STATUS_LIST = [
        "Compra", "Venda", "Transação"
    ]
    DIRECAO_LIST = [
        "Entrada", "Saída"
    ]

    def __init__(self, fornecedor, parent=None):
        super().__init__(parent)
        self.locale = QLocale(QLocale.Portuguese, QLocale.Brazil)
        self.fornecedor = fornecedor
        self.itens_movimentacao = []
        self.movimentacao_edit_id = None
        self.init_ui()
        self.carregar_produtos()
        self.atualizar_tabela()

    def obter_categoria_principal(self):
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT id, nome FROM categorias_fornecedor_por_fornecedor WHERE fornecedor_id = %s ORDER BY id ASC LIMIT 1",
                (self.fornecedor['id'],)
            )
            cat = cursor.fetchone()
            if not cat:
                cursor.execute("SELECT id, nome FROM categorias_fornecedor_por_fornecedor WHERE nome = %s LIMIT 1", ('Padrão',))
                cat = cursor.fetchone()
            return cat

    def listar_produtos(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome, preco_base FROM produtos ORDER BY nome")
            return cursor.fetchall()

    def listar_movimentacoes(self, data_de=None, data_ate=None):
        query = """
                SELECT m.id, m.data, m.tipo, m.direcao, m.descricao, m.valor_operacao
                FROM movimentacoes m
                WHERE m.fornecedor_id = %s 
                """
        params = [self.fornecedor['id']]
        if data_de:
            query += " AND m.data >= %s"
            params.append(data_de)
        if data_ate:
            query += " AND m.data <= %s"
            params.append(data_ate)
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

    def obter_saldo_total(self):
        saldo = Decimal("0.00")
        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT tipo, direcao, valor_operacao
                           FROM movimentacoes
                           WHERE fornecedor_id = %s
                           """, (self.fornecedor['id'],))
            movimentacoes = cursor.fetchall()
            for mov in movimentacoes:
                tipo = remove_acento(mov['tipo'] or '')
                direcao = remove_acento(mov['direcao'] or '')
                valor_op = Decimal(mov['valor_operacao']) if mov['valor_operacao'] is not None else Decimal('0.00')
                if tipo == "compra":
                    saldo += valor_op
                elif tipo == "venda":
                    saldo -= valor_op
                elif tipo == "transacao":
                    if direcao == "entrada":
                        saldo += valor_op
                    elif direcao == "saida":
                        saldo -= valor_op
        return saldo

    def editar_movimentacao_finalizada(self):
        linha = self.tabela_movimentacoes.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Editar Movimentação", "Selecione uma movimentação para editar.")
            return
        movimentacao_id_item = self.tabela_movimentacoes.item(linha, 0)
        if movimentacao_id_item is None:
            return
        movimentacao_id = int(movimentacao_id_item.text())

        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT fornecedor_id, data, tipo, direcao, descricao, valor_operacao
                           FROM movimentacoes
                           WHERE id = %s
                           """, (movimentacao_id,))
            movimentacao = cursor.fetchone()

            cursor.execute("""
                           SELECT p.nome                            AS produto_nome,
                                  i.produto_id,
                                  i.quantidade,
                                  i.preco_unitario,
                                  (i.quantidade * i.preco_unitario) AS total
                           FROM itens_movimentacao i
                                    JOIN produtos p ON i.produto_id = p.id
                           WHERE i.movimentacao_id = %s
                           """, (movimentacao_id,))
            itens = cursor.fetchall()

        if movimentacao is None:
            QMessageBox.warning(self, "Erro", "Movimentação não encontrada.")
            return

        idx_fornecedor = self.combo_fornecedor.findData(movimentacao['fornecedor_id'])
        self.combo_fornecedor.setCurrentIndex(idx_fornecedor if idx_fornecedor >= 0 else 0)
        self.input_data.setDate(QDate(movimentacao['data']))
        idx_tipo = self.combo_tipo.findText(movimentacao['tipo'])
        self.combo_tipo.setCurrentIndex(idx_tipo if idx_tipo >= 0 else 0)
        idx_direcao = self.combo_direcao.findText(movimentacao['direcao'])
        self.combo_direcao.setCurrentIndex(idx_direcao if idx_direcao >= 0 else 0)
        self.input_descricao.setText(str(movimentacao['descricao']))
        self.input_valor_operacao.setText(str(movimentacao['valor_operacao']))

        self.itens_movimentacao = []
        for item in itens:
            self.itens_movimentacao.append({
                "produto_id": item['produto_id'],
                "nome": item['produto_nome'],
                "quantidade": item['quantidade'],
                "preco": item['preco_unitario'],
                "total": item['total']
            })

        self.movimentacao_edit_id = movimentacao_id
        self.atualizar_tabela_itens_adicionados()

    def excluir_movimentacao_finalizada(self):
        linha = self.tabela_movimentacoes.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Excluir Movimentação", "Selecione uma movimentação para excluir.")
            return

        movimentacao_id_item = self.tabela_movimentacoes.item(linha, 0)
        if movimentacao_id_item is None:
            return

        movimentacao_id = int(movimentacao_id_item.text())

        confirm = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            f"Tem certeza que deseja excluir a movimentação ID {movimentacao_id}?",
            QMessageBox.Yes | QMessageBox.No
        )

        if confirm != QMessageBox.Yes:
            return

        try:
            with get_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM itens_movimentacao WHERE movimentacao_id = %s", (movimentacao_id,))
                cursor.execute("DELETE FROM movimentacoes WHERE id = %s", (movimentacao_id,))
            QMessageBox.information(self, "Sucesso", "Movimentação excluída com sucesso.")
            self.atualizar_tabela()
            self.tabela_itens_movimentacao.setRowCount(0)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao excluir movimentação: {e}")

    def acao_cancelar(self):
        self.limpar_campos()
        self.limpar_itens()
        self.carregar_produtos()

    def init_ui(self):
        layout_root = QHBoxLayout(self)
        layout_esq = QVBoxLayout()
        form_grid = QGridLayout()

        # Fornecedor (fixo na aba)
        form_grid.addWidget(QLabel(
            f"Fornecedor: {self.fornecedor['nome']} - Balança {self.fornecedor['fornecedores_numerobalanca']}"),
            0, 0, 1, 2)

        # Data
        self.input_data = QDateEdit()
        self.input_data.setDate(QDate.currentDate())
        self.input_data.setCalendarPopup(True)
        form_grid.addWidget(QLabel("Data"), 1, 0)
        form_grid.addWidget(self.input_data, 1, 1)

        # Categoria
        self.combo_categoria = QComboBox()
        self.combo_categoria.addItem("Categoria principal", 0)
        categoria_principal = self.obter_categoria_principal()
        if categoria_principal:
            self.combo_categoria.addItem(categoria_principal['nome'], categoria_principal['id'])
            self.combo_categoria.setCurrentIndex(1)
        form_grid.addWidget(QLabel("Categoria"), 2, 0)
        form_grid.addWidget(self.combo_categoria, 2, 1)

        # Abatimento
        self.input_valor_abatimento = QLineEdit()
        self.input_valor_abatimento.setPlaceholderText("Valor do abatimento")
        self.input_valor_abatimento.textChanged.connect(self.atualizar_total_movimentacao)
        form_grid.addWidget(QLabel("Abatimento"), 3, 0)
        form_grid.addWidget(self.input_valor_abatimento, 3, 1)

        # Tipo da movimentação
        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(self.STATUS_LIST)
        self.combo_tipo.currentTextChanged.connect(self.tipo_changed)
        form_grid.addWidget(QLabel("Tipo"), 4, 0)
        form_grid.addWidget(self.combo_tipo, 4, 1)

        # Direção (só para transação)
        self.combo_direcao = QComboBox()
        self.combo_direcao.addItems(self.DIRECAO_LIST)
        self.combo_direcao.setVisible(False)
        self.label_direcao = QLabel("Direção:")
        self.label_direcao.setVisible(False)
        form_grid.addWidget(self.label_direcao, 5, 0)
        form_grid.addWidget(self.combo_direcao, 5, 1)

        # Descrição
        self.input_descricao = QLineEdit()
        form_grid.addWidget(QLabel("Descrição"), 6, 0)
        form_grid.addWidget(self.input_descricao, 6, 1)

        # Valor operação (só para transação)
        self.input_valor_operacao = QLineEdit()
        self.input_valor_operacao.setPlaceholderText("Ex: 1000,00")
        self.label_valor_operacao = QLabel("Valor Operação:")
        form_grid.addWidget(self.label_valor_operacao, 7, 0)
        form_grid.addWidget(self.input_valor_operacao, 7, 1)
        self.input_valor_operacao.setVisible(False)
        self.label_valor_operacao.setVisible(False)

        # Produtos (só para compra/venda) - sem campo de preço unitário editável!
        self.layout_produto = QGridLayout()
        self.combo_produto = QComboBox()
        self.combo_produto.setEditable(True)  # Permitir escrever o nome
        self.input_quantidade = QSpinBox()
        self.input_quantidade.setMinimum(1)
        self.input_quantidade.setMaximum(99999)
        self.layout_produto.addWidget(QLabel("Produto"), 0, 0)
        self.layout_produto.addWidget(self.combo_produto, 0, 1)
        self.layout_produto.addWidget(QLabel("Quantidade"), 1, 0)
        self.layout_produto.addWidget(self.input_quantidade, 1, 1)
        btn_add_item = QPushButton("Adicionar Produto")
        btn_add_item.clicked.connect(self.adicionar_item)
        self.layout_produto.addWidget(btn_add_item, 2, 0, 1, 2)
        form_grid.addLayout(self.layout_produto, 8, 0, 1, 2)

        # Tabela de itens adicionados (apenas visualização do preço e total)
        self.tabela_itens_adicionados = QTableWidget()
        self.tabela_itens_adicionados.setColumnCount(4)
        self.tabela_itens_adicionados.setHorizontalHeaderLabels(["Produto", "Qtd", "Valor unitário", "Total"])
        self.tabela_itens_adicionados.setEditTriggers(QTableWidget.NoEditTriggers)
        form_grid.addWidget(QLabel("Itens (antes de salvar):"), 9, 0, 1, 2)
        form_grid.addWidget(self.tabela_itens_adicionados, 10, 0, 1, 2)

        btn_remover_item = QPushButton("Remover Item Selecionado")
        btn_remover_item.clicked.connect(self.remover_item)
        form_grid.addWidget(btn_remover_item, 11, 0, 1, 2)

        btn_limpar_itens = QPushButton("Limpar Itens")
        btn_limpar_itens.clicked.connect(self.limpar_itens)
        form_grid.addWidget(btn_limpar_itens, 12, 0, 1, 2)

        btn_finalizar = QPushButton("Salvar Movimentação")
        btn_finalizar.clicked.connect(self.finalizar_movimentacao)
        form_grid.addWidget(btn_finalizar, 14, 0, 1, 2)

        self.label_total_movimentacao = QLabel("Total: R$ 0,00")
        form_grid.addWidget(self.label_total_movimentacao, 15, 0, 1, 2)

        # Após outros widgets/layouts já existentes
        self.btn_editar_movimentacao = QPushButton("Editar Movimentação Finalizada Selecionada")
        self.btn_editar_movimentacao.clicked.connect(self.editar_movimentacao_finalizada)
        form_grid.addWidget(self.btn_editar_movimentacao, 16, 0, 1, 2)

        self.btn_excluir_movimentacao = QPushButton("Excluir Movimentação Finalizada Selecionada")
        self.btn_excluir_movimentacao.clicked.connect(self.excluir_movimentacao_finalizada)
        form_grid.addWidget(self.btn_excluir_movimentacao, 17, 0, 1, 2)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.clicked.connect(self.acao_cancelar)
        form_grid.addWidget(self.btn_cancelar, 13, 0, 1, 2)

        self.label_saldo_total = QLabel("Saldo total: R$ 0,00")
        font = self.label_saldo_total.font()
        font.setPointSize(12)
        font.setBold(True)
        self.label_saldo_total.setFont(font)
        form_grid.addWidget(self.label_saldo_total, 18, 0, 1, 2)

        layout_esq.addLayout(form_grid)
        layout_esq.addStretch()
        layout_root.addLayout(layout_esq, 1)

        # ----------- MEIO: Tabela movimentações (sem coluna de fornecedor) -----------
        layout_meio = QVBoxLayout()
        layout_filtros = QHBoxLayout()
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
        btn_filtrar = QPushButton("Filtrar")
        btn_filtrar.clicked.connect(self.atualizar_tabela)
        layout_filtros.addWidget(btn_filtrar)
        layout_meio.addLayout(layout_filtros)

        self.tabela_movimentacoes = QTableWidget()
        self.tabela_movimentacoes.setColumnCount(6)
        self.tabela_movimentacoes.setHorizontalHeaderLabels([
            "ID", "Data", "Tipo", "Direção", "Descrição", "Valor Operação"
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
        self.tabela_itens.setColumnCount(3)
        self.tabela_itens.setHorizontalHeaderLabels(["Produto", "Qtd", "Total"])
        self.tabela_itens.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_itens.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout_dir.addWidget(self.tabela_itens)
        layout_root.addLayout(layout_dir, 2)

        self.tipo_changed()
        self.atualiza_saldo_total()

    def tipo_changed(self):
        tipo = self.combo_tipo.currentText()
        is_transacao = tipo == "Transação"
        self.combo_direcao.setVisible(is_transacao)
        self.label_direcao.setVisible(is_transacao)
        self.input_valor_operacao.setVisible(is_transacao)
        self.label_valor_operacao.setVisible(is_transacao)
        for i in range(self.layout_produto.count()):
            widget = self.layout_produto.itemAt(i).widget()
            if widget:
                widget.setVisible(not is_transacao)
        self.tabela_itens_adicionados.setVisible(not is_transacao)
        self.combo_categoria.setVisible(not is_transacao)
        self.input_valor_abatimento.setVisible(not is_transacao)
        self.label_total_movimentacao.setVisible(not is_transacao)
        self.atualizar_total_movimentacao()

    def carregar_produtos(self):
        self.combo_produto.clear()
        self.combo_produto.setEditable(True)
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT p.id, p.nome, p.preco_base
                FROM produtos p
                ORDER BY p.nome
            """)
            produtos = cursor.fetchall()
        self.produtos = produtos
        self.combo_produto.addItem("Selecione um produto", None)
        for p in produtos:
            self.combo_produto.addItem(p["nome"], p["id"])

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

        categoria_id = self.combo_categoria.currentData()
        with get_cursor() as cursor:
            cursor.execute(
                """
                SELECT ajuste_fixo
                FROM ajustes_fixos_produto_fornecedor_categoria
                WHERE produto_id = %s AND categoria_id = %s
                """,
                (produto_id, categoria_id)
            )
            ajuste_row = cursor.fetchone()
        ajuste_fixo = Decimal(str(ajuste_row["ajuste_fixo"])) if ajuste_row and "ajuste_fixo" in ajuste_row else Decimal("0.00")

        preco_base = produto["preco_base"]
        preco_unitario = Decimal(str(preco_base)) + ajuste_fixo
        total = quantidade * preco_unitario

        self.itens_movimentacao.append({
            "produto_id": produto_id,
            "nome": produto["nome"],
            "quantidade": quantidade,
            "preco": preco_unitario,
            "total": total
        })
        self.atualizar_tabela_itens_adicionados()
        self.combo_produto.setCurrentIndex(0)
        self.input_quantidade.setValue(1)

    def atualizar_tabela_itens_adicionados(self):
        self.tabela_itens_adicionados.blockSignals(True)
        self.tabela_itens_adicionados.setRowCount(len(self.itens_movimentacao))
        for i, item in enumerate(self.itens_movimentacao):
            self.tabela_itens_adicionados.setItem(i, 0, QTableWidgetItem(item["nome"]))
            self.tabela_itens_adicionados.setItem(i, 1, QTableWidgetItem(str(item["quantidade"])))
            preco_formatado = self.locale.toString(float(item['preco']), 'f', 2)
            total_formatado = self.locale.toString(float(item['total']), 'f', 2)
            self.tabela_itens_adicionados.setItem(i, 2, QTableWidgetItem(preco_formatado))
            self.tabela_itens_adicionados.setItem(i, 3, QTableWidgetItem(total_formatado))
        self.tabela_itens_adicionados.blockSignals(False)
        self.atualizar_total_movimentacao()

    def remover_item(self):
        selected = self.tabela_itens_adicionados.currentRow()
        if selected >= 0:
            del self.itens_movimentacao[selected]
            self.atualizar_tabela_itens_adicionados()

    def limpar_itens(self):
        self.itens_movimentacao = []
        self.atualizar_tabela_itens_adicionados()

    def atualizar_total_movimentacao(self):
        if self.combo_tipo.currentText() == "Transação":
            self.label_total_movimentacao.setText("Total: R$ 0,00")
            return
        valor_texto = self.input_valor_abatimento.text().replace(',', '.')
        try:
            valor_abatimento = Decimal(valor_texto) if valor_texto else Decimal('0.00')
        except Exception:
            valor_abatimento = Decimal('0.00')
        total = sum(Decimal(str(item['total'])) for item in self.itens_movimentacao)
        total_final = total - valor_abatimento
        total_formatado = self.locale.toString(float(total_final), 'f', 2)
        self.label_total_movimentacao.setText(f"Total: R$ {total_formatado}")

    def finalizar_movimentacao(self):
        tipo = self.combo_tipo.currentText().lower()
        data = self.input_data.date().toPython()
        direcao = self.combo_direcao.currentText().lower() if tipo == "transação" else None
        descricao = self.input_descricao.text().strip()

        # Abatimento: salva como uma transação de entrada separada
        valor_abatimento = None
        if tipo != "transação":
            valor_texto = self.input_valor_abatimento.text().replace(',', '.')
            try:
                valor_abatimento = Decimal(valor_texto) if valor_texto else Decimal('0.00')
            except Exception:
                valor_abatimento = Decimal('0.00')

        if tipo == "transação":
            try:
                valor_operacao = Decimal(self.input_valor_operacao.text().replace(",", "."))
            except Exception:
                QMessageBox.warning(self, "Erro", "Digite um valor válido para a operação.")
                return
        else:
            if not self.itens_movimentacao:
                QMessageBox.warning(self, "Erro", "Adicione pelo menos um item antes de salvar.")
                return
            total = sum(Decimal(str(item['total'])) for item in self.itens_movimentacao)
            valor_abatimento = Decimal(self.input_valor_abatimento.text().replace(',',
                                                                                  '.')) if self.input_valor_abatimento.text() else Decimal(
                '0.00')
            valor_operacao = total - valor_abatimento  # este valor vai para a coluna valor_operacao

        with get_cursor(commit=True) as cursor:
            # Compra/Venda: salva normalmente
            cursor.execute(
                "INSERT INTO movimentacoes (fornecedor_id, data, tipo, direcao, descricao, valor_operacao) VALUES (%s, %s, %s, %s, %s, %s)",
                (self.fornecedor['id'], data, tipo, direcao, descricao, valor_operacao)
            )
            movimentacao_id = cursor.lastrowid
            if tipo != "transação":
                for item in self.itens_movimentacao:
                    cursor.execute(
                        "INSERT INTO itens_movimentacao (movimentacao_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)",
                        (movimentacao_id, item["produto_id"], item["quantidade"], item["preco"])
                    )
                # Se houver abatimento, cria uma transação de entrada separada
                if valor_abatimento and valor_abatimento > 0:
                    cursor.execute(
                        "INSERT INTO movimentacoes (fornecedor_id, data, tipo, direcao, descricao, valor_operacao) VALUES (%s, %s, %s, %s, %s, %s)",
                        (
                            self.fornecedor['id'],
                            data,
                            "transação",
                            "entrada",
                            f"Abatimento automático referente à movimentação {movimentacao_id}",
                            valor_abatimento
                        )
                    )
        QMessageBox.information(self, "Sucesso", "Movimentação cadastrada com sucesso.")
        self.limpar_itens()
        self.input_valor_abatimento.clear()
        self.atualizar_tabela()
        self.atualiza_saldo_total()

    def atualizar_tabela(self):
        data_de = self.filtro_data_de.date().toPython()
        data_ate = self.filtro_data_ate.date().toPython()
        movimentacoes = self.listar_movimentacoes(data_de, data_ate)
        self.tabela_movimentacoes.setRowCount(len(movimentacoes))
        for i, m in enumerate(movimentacoes):
            self.tabela_movimentacoes.setItem(i, 0, QTableWidgetItem(str(m["id"])))
            self.tabela_movimentacoes.setItem(i, 1, QTableWidgetItem(str(m["data"])))
            self.tabela_movimentacoes.setItem(i, 2, QTableWidgetItem(m["tipo"].capitalize()))
            self.tabela_movimentacoes.setItem(i, 3, QTableWidgetItem(m["direcao"].capitalize() if m["direcao"] else ""))
            self.tabela_movimentacoes.setItem(i, 4, QTableWidgetItem(m["descricao"] or ""))
            valor_op = m.get("valor_operacao")
            if valor_op is not None:
                valor_op_str = self.locale.toString(float(valor_op), 'f', 2)
            else:
                valor_op_str = ""
            self.tabela_movimentacoes.setItem(i, 5, QTableWidgetItem(valor_op_str))
        self.atualiza_saldo_total()

    def atualiza_saldo_total(self):
        saldo = self.obter_saldo_total()
        self.label_saldo_total.setText(f"Saldo total: R$ {self.locale.toString(float(saldo), 'f', 2)}")

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
            total_formatado = self.locale.toString(float(item['preco_unitario'] * item['quantidade']), 'f', 2)
            self.tabela_itens.setItem(i, 2, QTableWidgetItem(total_formatado))


class MovimentacoesUI(QWidget):
    def __init__(self):
        super().__init__()
        self.locale = QLocale(QLocale.Portuguese, QLocale.Brazil)
        self.fornecedores = self.listar_fornecedores()
        self.init_ui()

    def listar_fornecedores(self):
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome, fornecedores_numerobalanca FROM fornecedores ORDER BY nome")
            return cursor.fetchall()

    def selecionar_fornecedor_por_numero_balanca(self, campo_input: QLineEdit, combo_fornecedor: QComboBox):
        numero = campo_input.text().strip()
        if not numero:
            return
        with get_cursor() as cursor:
            cursor.execute("SELECT id FROM fornecedores WHERE fornecedores_numerobalanca = %s", (numero,))
            resultado = cursor.fetchone()
        if resultado:
            idx = -1
            for i in range(combo_fornecedor.count()):
                if combo_fornecedor.itemData(i) == resultado['id']:
                    idx = i
                    break
            if idx >= 0:
                combo_fornecedor.setCurrentIndex(idx)
            else:
                QMessageBox.warning(self, "Fornecedor não encontrado", f"Nenhum fornecedor com número de balança {numero}.")
                campo_input.clear()
        else:
            QMessageBox.warning(self, "Fornecedor não encontrado", f"Nenhum fornecedor com número de balança {numero}.")
            campo_input.clear()

    def init_ui(self):
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.input_numero_balanca = QLineEdit()
        self.input_numero_balanca.setPlaceholderText("Número da balança")
        self.combo_fornecedor = QComboBox()
        self.combo_fornecedor.addItem("Selecione um fornecedor", None)
        for f in self.fornecedores:
            self.combo_fornecedor.addItem(f"{f['nome']} - Balança {f['fornecedores_numerobalanca']}", f['id'])
        row.addWidget(QLabel("Fornecedor:"))
        row.addWidget(self.combo_fornecedor)
        row.addWidget(QLabel("ou"))
        row.addWidget(QLabel("Nº Balança:"))
        row.addWidget(self.input_numero_balanca)
        self.btn_nova_op = QPushButton("Nova operação")
        self.btn_nova_op.clicked.connect(self.abrir_nova_aba)
        row.addWidget(self.btn_nova_op)
        layout.addLayout(row)

        self.input_numero_balanca.editingFinished.connect(
            lambda: self.selecionar_fornecedor_por_numero_balanca(self.input_numero_balanca, self.combo_fornecedor)
        )

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.fechar_aba)
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def abrir_nova_aba(self):
        idx = self.combo_fornecedor.currentIndex()
        if idx <= 0:
            return
        fornecedor_id = self.combo_fornecedor.itemData(idx)
        fornecedor = next((f for f in self.fornecedores if f['id'] == fornecedor_id), None)
        if not fornecedor:
            return
        for i in range(self.tabs.count()):
            tab_widget = self.tabs.widget(i)
            if hasattr(tab_widget, "fornecedor") and tab_widget.fornecedor['id'] == fornecedor['id']:
                self.tabs.setCurrentIndex(i)
                return
        tab = MovimentacaoTabUI(fornecedor)
        title = f"{fornecedor['nome']} - {fornecedor['fornecedores_numerobalanca']}"
        self.tabs.addTab(tab, title)
        self.tabs.setCurrentWidget(tab)

    def fechar_aba(self, idx):
        self.tabs.removeTab(idx)

if __name__ == "__main__":
    app = QApplication([])
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    window = MovimentacoesUI()
    window.resize(1200, 700)
    window.show()
    sys.exit(app.exec())