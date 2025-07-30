import sys
import os, platform
import unicodedata
import re
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QComboBox, QDateEdit, QLineEdit, QTableWidget,
    QTableWidgetItem, QMessageBox, QSizePolicy, QTabWidget, QDialog,
    QSizePolicy, QHeaderView, QSplitter
)
from PySide6.QtGui import QIntValidator
from PySide6.QtCore import Qt, QDate, QLocale, QEvent, QTimer
from decimal import Decimal, InvalidOperation
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

from threads_utils import WorkerThread
from compras.compras_db import (
    listar_produtos,
    listar_fornecedores,
    obter_ajuste_fixo,
    obter_itens_e_lancamentos_da_compra,
    obter_valor_com_abatimento_adiantamento,
    existe_transacao_saida_para_compra,
    obter_detalhes_compra,
    obter_transacao_saida_para_compra,
    excluir_transacao_saida_para_compra,
    obter_dados_bancarios_para_campo_copiavel,
    listar_contas_do_fornecedor,
    atualizar_conta_bancaria_da_compra,
    obter_fornecedor_id_da_compra,
    obter_saldo_antes_compra
)
from compras.compras_dialogs import (
    PagamentoMovimentacaoDialog,
    AtualizarTransacaoDialog,
    ConfirmarExclusaoPagamentoDialog
)
from movimentacoes_db import (
    listar_movimentacoes,
    obter_categoria_principal,
    obter_saldo_total,
    obter_saldos_acumulados,
    listar_itens_movimentacao,
    obter_compra_por_id,
    excluir_movimentacao,
    atualizar_movimentacao,
    inserir_movimentacao,
    inserir_item_compra,
    buscar_fornecedor_id_por_numero_balanca,
    contar_movimentacoes,
    obter_saldo_anterior,
    get_conta_padrao_id
)

def decimal_para_str_brasil(valor, locale=None):
    if locale is None:
        locale = QLocale(QLocale.Portuguese, QLocale.Brazil)
    return locale.toString(float(valor), 'f', 2)

def str_brasil_para_decimal(texto):
    texto = texto.replace('.', '').replace(',', '.')
    try:
        return Decimal(texto)
    except (InvalidOperation, TypeError):
        return Decimal('0.00')

class FocusLineEdit(QLineEdit):
    def focusInEvent(self, event):
        if self.text() == "" or self.text() == "Selecione um produto":
            self.clear()
        super().focusInEvent(event)

class DialogFiltroData(QDialog):
    def __init__(self, data_de, data_ate, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escolher Período para Exportação")
        layout = QVBoxLayout(self)

        hlayout1 = QHBoxLayout()
        hlayout1.addWidget(QLabel("Data inicial:"))
        self.input_data_de = QDateEdit()
        self.input_data_de.setCalendarPopup(True)
        self.input_data_de.setDate(data_de)
        hlayout1.addWidget(self.input_data_de)
        layout.addLayout(hlayout1)

        hlayout2 = QHBoxLayout()
        hlayout2.addWidget(QLabel("Data final:"))
        self.input_data_ate = QDateEdit()
        self.input_data_ate.setCalendarPopup(True)
        self.input_data_ate.setDate(data_ate)
        hlayout2.addWidget(self.input_data_ate)
        layout.addLayout(hlayout2)

        hlayout3 = QHBoxLayout()
        self.btn_ok = QPushButton("Exportar")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        hlayout3.addWidget(self.btn_ok)
        hlayout3.addWidget(self.btn_cancel)
        layout.addLayout(hlayout3)

    def get_datas(self):
        return self.input_data_de.date(), self.input_data_ate.date()

def remove_acento(txt):
    if not txt:
        return ""
    return ''.join(
        c for c in unicodedata.normalize('NFKD', txt)
        if not unicodedata.combining(c)
    ).lower().strip()

def limpar_numero_nome_produto(nome):
    # Remove todos os números do nome do produto
    return re.sub(r'\d+', '', nome).strip()

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
        self.produtos = listar_produtos()
        self.itens_movimentacao = []
        self.movimentacao_edit_id = None
        self.pagina_atual = 1
        self.qtd_por_pagina = 50
        self.total_paginas = 1
        self.dados_bancarios_id_selecionada = None
        self.init_ui()
        self.carregar_produtos()
        self.atualizar_tabela()

        # ==== PATCH INICIO: CÓPIA DE COMPRASUI para campo copiável e trocar conta ====
    def atualizar_campo_texto_copiavel(self):
        compra_id = self.obter_compra_id_selecionado()
        if not compra_id:
            self.campo_texto_copiavel.setText("")
            return
        texto = obter_dados_bancarios_para_campo_copiavel(compra_id)
        self.campo_texto_copiavel.setText(texto or "")

    def copiar_campo_texto_copiavel(self, event):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.campo_texto_copiavel.text())
        self.campo_texto_copiavel.setStyleSheet("background-color: #b2f2b4; font-weight: bold; font-size: 13px;")
        QTimer.singleShot(350, lambda: self.campo_texto_copiavel.setStyleSheet("font-weight: bold; font-size: 13px;"))
        QLineEdit.mousePressEvent(self.campo_texto_copiavel, event)

    def abrir_dialog_troca_conta_fornecedor(self):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QDialogButtonBox, QComboBox, QLabel, QMessageBox
        compra_id = self.obter_compra_id_selecionado()
        # Permite trocar mesmo sem movimentação salva, guardando no atributo (será gravado no insert/update)
        fornecedor_id = self.fornecedor["id"]
        contas_do_fornecedor = listar_contas_do_fornecedor(fornecedor_id)
        if not contas_do_fornecedor:
            QMessageBox.information(self, "Sem contas", "Este fornecedor não possui contas bancárias cadastradas.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Escolher conta do fornecedor para esta movimentação")
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
        # Seleciona a conta atual, se houver
        if self.dados_bancarios_id_selecionada:
            idx = combo_contas.findData(self.dados_bancarios_id_selecionada)
            if idx >= 0:
                combo_contas.setCurrentIndex(idx)
        layout.addWidget(combo_contas)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        def on_ok():
            conta_id = combo_contas.currentData()
            self.dados_bancarios_id_selecionada = conta_id
            compra_id_local = self.obter_compra_id_selecionado()
            if conta_id and compra_id_local:
                atualizar_conta_bancaria_da_compra(compra_id_local, conta_id)
                self.atualizar_campo_texto_copiavel()
            dialog.accept()

        def on_cancel():
            dialog.reject()

        buttons.accepted.connect(on_ok)
        buttons.rejected.connect(on_cancel)
        dialog.exec()

    def obter_compra_id_selecionado(self):
        row = self.tabela_movimentacoes.currentRow()
        if row < 0:
            return None
        item = self.tabela_movimentacoes.item(row, 0)
        return int(item.text()) if item else None
        # ==== PATCH FIM ====

    def editar_movimentacao_finalizada(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        linha = self.tabela_movimentacoes.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Editar Movimentação", "Selecione uma movimentação para editar.")
            return
        compra_id_item = self.tabela_movimentacoes.item(linha, 0)
        if compra_id_item is None:
            return
        compra_id = int(compra_id_item.text())

        def tarefa_db():
            compra = obter_compra_por_id(compra_id)
            itens = listar_itens_movimentacao(compra_id)
            return compra, itens

        self.worker_edit = WorkerThread(tarefa_db)
        self.worker_edit.finished.connect(lambda dados: self._preencher_edicao_movimentacao(compra_id, dados))
        self.worker_edit.erro.connect(self._mostrar_erro_thread)
        self.worker_edit.start()

    def _preencher_edicao_movimentacao(self, compra_id, resultado):
        compra, itens = resultado
        # Se itens vier como dicionário agrupado por compra_id
        if isinstance(itens, dict):
            itens = itens.get(compra_id, [])
        self.itens_movimentacao = []
        for item in itens:
            self.itens_movimentacao.append({
                "produto_id": item['produto_id'],
                "nome": item['produto_nome'],
                "quantidade": item['quantidade'],
                "preco": item['preco_unitario'],
                "total": item['total']
            })
        self.atualizar_tabela_itens_adicionados()

        if compra is None:
            QMessageBox.warning(self, "Erro", "Movimentação não encontrada.")
            return

        self.limpar_campos()
        self.itens_movimentacao = []
        # Data
        if isinstance(compra['data_compra'], QDate):
            self.input_data.setDate(compra['data_compra'])
        else:
            try:
                self.input_data.setDate(QDate.fromString(str(compra['data_compra']), "yyyy-MM-dd"))
            except Exception:
                self.input_data.setDate(QDate.currentDate())

        # Tipo
        tipo_mov = remove_acento(compra['tipo'])
        idx_tipo = -1
        for i in range(self.combo_tipo.count()):
            if remove_acento(self.combo_tipo.itemText(i)) == tipo_mov:
                idx_tipo = i
                break
        self.combo_tipo.blockSignals(True)
        self.combo_tipo.setCurrentIndex(idx_tipo if idx_tipo >= 0 else 0)
        self.combo_tipo.blockSignals(False)
        self.tipo_changed()

        # Direção (se for transação)
        if remove_acento(compra['tipo']).lower() == "transacao":
            direcao_db = remove_acento(compra['direcao'] or "").capitalize()
            idx_direcao = -1
            for i in range(self.combo_direcao.count()):
                item = self.combo_direcao.itemText(i)
                if remove_acento(item).capitalize() == direcao_db:
                    idx_direcao = i
                    break
            self.combo_direcao.setCurrentIndex(idx_direcao if idx_direcao >= 0 else 0)
            valor_str = decimal_para_str_brasil(compra['total'], self.locale)
            self.input_valor_operacao.setText(valor_str)
        else:
            self.input_valor_operacao.setText("")
            self.itens_movimentacao = []
            for item in itens:
                self.itens_movimentacao.append({
                    "produto_id": item['produto_id'],
                    "nome": item['produto_nome'],
                    "quantidade": item['quantidade'],
                    "preco": item['preco_unitario'],
                    "total": item['total']
                })
            self.atualizar_tabela_itens_adicionados()

        # Pega valor de adiantamento (debitos_fornecedores, tipo='inclusao')
        from db_context import get_cursor
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT COALESCE(SUM(valor),0) AS valor_adiantamento
                FROM debitos_fornecedores
                WHERE compra_id = %s AND tipo = 'inclusao'
            """, (compra_id,))
            row = cursor.fetchone()
            valor_adiantamento = float(row['valor_adiantamento']) if row else 0.0

        # Define tipo e valor do lançamento conforme o que existe
        if valor_adiantamento > 0:
            self.combo_tipo_lancamento.setCurrentIndex(1)  # Adiantamento
            self.input_valor_lancamento.setText(str(valor_adiantamento))
        else:
            self.combo_tipo_lancamento.setCurrentIndex(0)  # Abatimento
            valor_abatimento = compra.get('valor_abatimento')
            self.input_valor_lancamento.setText(str(valor_abatimento) if valor_abatimento else "")

        # Descrição
        self.input_descricao.setText(str(compra['descricao']) if compra['descricao'] else "")
        self.movimentacao_edit_id = compra_id

    def _mostrar_erro_thread(self, mensagem):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(self, "Erro", mensagem)

    def excluir_movimentacao_finalizada(self):
        selected_ranges = self.tabela_movimentacoes.selectedRanges()
        if not selected_ranges:
            QMessageBox.information(self, "Excluir Movimentação", "Selecione uma movimentação para excluir.")
            return
        linha = selected_ranges[0].topRow()

        compra_id_item = self.tabela_movimentacoes.item(linha, 0)
        if compra_id_item is None:
            return

        compra_id = int(compra_id_item.text())

        # Verifica se há transação de saída vinculada à movimentação (pagamento correspondente)
        if existe_transacao_saida_para_compra(compra_id):
            dialog = ConfirmarExclusaoPagamentoDialog(self)
            if dialog.exec() and dialog.resultado:
                # Excluir também a transação de saída vinculada
                excluir_transacao_saida_para_compra(compra_id)
        # Confirma exclusão da movimentação principal
        confirm = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            f"Tem certeza que deseja excluir a movimentação ID {compra_id}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            excluir_movimentacao(compra_id)
            QMessageBox.information(self, "Sucesso", "Movimentação excluída com sucesso.")
            self.atualizar_tabela()
            self.tabela_itens.setRowCount(0)
            self.atualiza_saldo_total()
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao excluir movimentação: {e}")

    def acao_cancelar(self):
        # Sempre sai do modo edição e limpa tudo, pronto para incluir nova movimentação
        self.movimentacao_edit_id = None
        self.limpar_campos()
        self.limpar_itens()
        self.carregar_produtos()

    def limpar_campos(self):
        self.input_data.setDate(QDate.currentDate())
        self.input_valor_lancamento.clear()
        self.combo_tipo_lancamento.setCurrentIndex(0)
        self.combo_tipo.setCurrentIndex(0)
        self.combo_direcao.setCurrentIndex(0)
        self.input_descricao.clear()
        self.input_valor_operacao.clear()
        self.combo_produto.setCurrentIndex(0)
        self.input_quantidade.setText("")
        # Se houver outros campos a limpar, adicione aqui.

    def combo_produto_focus_in_event(self, event):
        line_edit = self.combo_produto.lineEdit()
        if line_edit.text() == "" or line_edit.text() == "Selecione um produto":
            line_edit.clear()
        # Chame o evento padrão para manter o comportamento normal
        super(type(line_edit), line_edit).focusInEvent(event)

    def atualizar_item_editado(self, row, column):
        if row < 0 or row >= len(self.itens_movimentacao):
            return
        try:
            if column == 1:  # Quantidade
                nova_qtd = int(self.tabela_itens_adicionados.item(row, 1).text())
                if nova_qtd <= 0:
                    raise ValueError("Quantidade deve ser maior que zero.")
                self.itens_movimentacao[row]['quantidade'] = nova_qtd
            elif column == 2:  # Preço unitário
                novo_preco_str = self.tabela_itens_adicionados.item(row, 2).text()
                novo_preco = str_brasil_para_decimal(novo_preco_str)
                if novo_preco < 0:
                    raise ValueError("Preço não pode ser negativo.")
                self.itens_movimentacao[row]['preco'] = novo_preco
            elif column == 4:  # Número de fardos
                novo_nfardos_str = self.tabela_itens_adicionados.item(row, 4).text()
                self.itens_movimentacao[row]['numero_fardos'] = int(novo_nfardos_str) if novo_nfardos_str else None
            else:
                return
            qtd = self.itens_movimentacao[row]['quantidade']
            preco = self.itens_movimentacao[row]['preco']
            self.itens_movimentacao[row]['total'] = Decimal(str(qtd)) * preco

            # Atualiza o campo "Total" na tabela
            total_formatado = decimal_para_str_brasil(self.itens_movimentacao[row]['total'], self.locale)
            self.tabela_itens_adicionados.blockSignals(True)
            self.tabela_itens_adicionados.setItem(row, 3, QTableWidgetItem(total_formatado))
            self.tabela_itens_adicionados.blockSignals(False)

            self.atualizar_total_movimentacao()
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Valor inválido: {e}")
            # Restaurar valor anterior
            self.tabela_itens_adicionados.blockSignals(True)
            self.tabela_itens_adicionados.setItem(row, 1, QTableWidgetItem(str(self.itens_movimentacao[row]['quantidade'])))
            preco_formatado = decimal_para_str_brasil(self.itens_movimentacao[row]['preco'], self.locale)
            self.tabela_itens_adicionados.setItem(row, 2, QTableWidgetItem(preco_formatado))
            nfardos = self.itens_movimentacao[row].get("numero_fardos")
            self.tabela_itens_adicionados.setItem(row, 4, QTableWidgetItem(str(nfardos) if nfardos is not None else ""))
            self.tabela_itens_adicionados.blockSignals(False)

    def exportar_movimentacoes_pdf(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        dialog = DialogFiltroData(self.filtro_data_de.date(), self.filtro_data_ate.date(), self)
        if not dialog.exec():
            return
        data_de, data_ate = dialog.get_datas()
        data_de = data_de.toPython()
        data_ate = data_ate.toPython()
        fornecedor_id = self.fornecedor['id']

        def tarefa_pdf():
            movimentacoes = listar_movimentacoes(fornecedor_id, data_de, data_ate)
            if not movimentacoes:
                return None

            movimentacoes = movimentacoes[::-1]

            saldo_por_id = obter_saldos_acumulados(fornecedor_id, data_de, data_ate, remove_acento)
            mov_ids = [mov['id'] for mov in movimentacoes]
            itens_por_mov = listar_itens_movimentacao(mov_ids)
            saldo_anterior = obter_saldo_anterior(fornecedor_id, data_de, remove_acento)

            largura, altura_pagina = A4
            margem = 20 * mm
            espacamento_compra = 10
            espacamento_transacao = 10
            altura_util_pagina = altura_pagina - 2 * margem

            # Preparar blocos e altura de cada um
            blocos = []
            for mov in movimentacoes:
                bloco = {}
                bloco['mov'] = mov
                bloco['itens'] = itens_por_mov.get(mov['id'], []) if mov['tipo'].lower() in ("compra", "venda") else []
                if remove_acento(mov['tipo']) == "transacao":
                    bloco['altura'] = 210
                    bloco['espacamento'] = espacamento_transacao
                else:
                    bloco['altura'] = 250 + 28 * (len(bloco['itens']) if bloco['itens'] else 1)
                    bloco['espacamento'] = espacamento_compra
                blocos.append(bloco)

            filename = f"movimentacoes_{data_de.strftime('%Y%m%d')}_{data_ate.strftime('%Y%m%d')}_extrato.pdf"
            c = canvas.Canvas(filename, pagesize=A4)

            def desenhar_cabecalho(y, primeira_pagina):
                # Fornecedor e balança
                if movimentacoes:
                    nome_fornecedor = movimentacoes[0]['fornecedor']
                    num_balanca = movimentacoes[0]['fornecedores_numerobalanca']
                    c.setFont("Helvetica-Bold", 16)
                    c.setFillColorRGB(0, 0, 0)
                    c.drawString(margem, y,
                                 f"Extrato de movimentações - Fornecedor: {nome_fornecedor}  |  Balança: {num_balanca}")
                    y -= 30
                # Cabeçalho de datas
                if data_de != data_ate:
                    c.setFont("Helvetica", 12)
                    c.drawString(margem, y,
                                 f"Do dia {data_de.strftime('%d/%m/%Y')} até {data_ate.strftime('%d/%m/%Y')}")
                    y -= 25
                # Saldo anterior só na primeira página
                if primeira_pagina:
                    c.setFont("Helvetica-Bold", 14)
                    if saldo_anterior >= 0:
                        c.setFillColorRGB(0, 0.39, 0)
                    else:
                        c.setFillColorRGB(1, 0, 0)
                    c.drawString(margem, y, f"SALDO ANTERIOR AO PERÍODO: R$ {float(saldo_anterior):,.2f}")
                    c.setFillColorRGB(0, 0, 0)
                    y -= 30
                return y

            y = altura_pagina - margem
            pagina = 1
            y = desenhar_cabecalho(y, primeira_pagina=True)

            for bloco in blocos:
                if (y - (bloco['altura'] + bloco['espacamento'])) < margem:
                    c.showPage()
                    pagina += 1
                    y = altura_pagina - margem
                    y = desenhar_cabecalho(y, primeira_pagina=False)

                mov = bloco['mov']
                itens = bloco['itens']
                tipo_raw = mov['tipo']
                tipo = tipo_raw.capitalize()
                if remove_acento(tipo_raw).lower() == "transacao":
                    tipo = "Transação"
                direcao = (mov.get('direcao') or "").lower()
                descricao = mov['descricao'] or ""
                valor_operacao = float(mov['valor_operacao'] or 0)
                saldo_atual = saldo_por_id.get(mov['id'], 0)

                c.setFont("Helvetica-Bold", 13)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(margem, y, f"{tipo}")
                y -= 20

                c.setFont("Helvetica", 11)
                if direcao == "saida":
                    c.drawString(margem, y, "Pagamento efetuado")
                    y -= 18
                elif direcao == "entrada":
                    c.drawString(margem, y, "Pagamento recebido")
                    y -= 18

                if 'data' in mov and mov['data']:
                    if isinstance(mov['data'], datetime):
                        data_str = mov['data'].strftime('%d/%m/%Y')
                    else:
                        data_str = str(mov['data'])
                    c.drawString(margem, y, f"Data: {data_str}")
                    y -= 18

                if descricao:
                    c.drawString(margem, y, f"Descrição: {descricao}")
                    y -= 18

                if itens:
                    # --- PATCH: Detecta se algum item tem número de fardos ---
                    mostrar_coluna_fardos = any(
                        item.get("numero_fardos") not in (None, "", 0) for item in itens
                    )
                    y -= 5
                    c.setFont("Helvetica-Bold", 11)
                    c.drawString(margem, y, "Produtos")
                    y -= 15
                    c.setFont("Helvetica-Bold", 10)
                    c.drawString(margem, y, "Produto")
                    c.drawString(margem + 180, y, "Qtd")
                    c.drawString(margem + 240, y, "Unitário")
                    c.drawString(margem + 330, y, "Total")
                    if mostrar_coluna_fardos:
                        c.drawString(margem + 420, y, "Nº Fardos")
                    y -= 8
                    c.line(margem, y, largura - margem, y)
                    y -= 8
                    c.setFont("Helvetica", 10)
                    total = 0
                    for item in itens:
                        c.drawString(margem, y, limpar_numero_nome_produto(item['produto_nome']))
                        c.drawString(margem + 180, y, str(item['quantidade']))
                        c.drawString(margem + 240, y, f"R$ {item['preco_unitario']:.2f}")
                        c.drawString(margem + 330, y, f"R$ {item['total']:.2f}")
                        if mostrar_coluna_fardos:
                            nfardos = item.get("numero_fardos")
                            c.drawString(margem + 420, y, str(nfardos) if nfardos not in (None, "", 0) else "")
                        total += float(item['total'])
                        y -= 13
                    y -= 8
                    c.line(margem, y, largura - margem, y)
                    y -= 10
                    c.setFont("Helvetica-Bold", 11)
                    c.setFillColorRGB(0, 0, 0)
                    c.drawString(margem, y, f"Subtotal: R$ {total:.2f}")
                    y -= 12
                    c.drawString(margem, y, f"Total Final (com abatimento): R$ {valor_operacao:.2f}")
                    y -= 13
                else:
                    y -= 8
                    c.setFont("Helvetica-Bold", 14)
                    c.drawString(margem, y, f"Valor da Operação: R$ {valor_operacao:.2f}")
                    y -= 25

                c.setFont("Helvetica-Bold", 12)
                if saldo_atual < 0:
                    c.setFillColorRGB(1, 0, 0)
                else:
                    c.setFillColorRGB(0, 0.39, 0)
                c.drawString(margem, y, f"SALDO TOTAL APÓS ESTA MOVIMENTAÇÃO: R$ {float(saldo_atual):,.2f}")
                c.setFillColorRGB(0, 0, 0)
                y -= 21

                self.adicionar_marca_dagua_pdf_area(
                    c,
                    texto=str(mov['fornecedores_numerobalanca']),
                    x_inicio=margem,
                    x_fim=largura - margem,
                    y_topo=y + 73,
                    altura=bloco['altura'] - 70,
                    tamanho_fonte=24,
                    cor=(0.8, 0.8, 0.8),
                    angulo=25
                )

                y -= bloco['espacamento']

            c.save()
            return filename

        def on_pdf_ready(filename):
            if not filename:
                QMessageBox.warning(self, "Exportar PDF", "Nenhuma movimentação encontrada no período selecionado.")
                return
            QMessageBox.information(self, "Exportar PDF", f"PDF gerado com sucesso:\n{filename}")
            if platform.system() == "Windows":
                os.startfile(filename)
            elif platform.system() == "Darwin":
                os.system(f"open '{filename}'")
            else:
                os.system(f"xdg-open '{filename}'")

        self.worker_export_pdf = WorkerThread(tarefa_pdf)
        self.worker_export_pdf.finished.connect(on_pdf_ready)
        self.worker_export_pdf.erro.connect(self._mostrar_erro_thread)
        self.worker_export_pdf.start()

    def adicionar_marca_dagua_pdf_area(self, c, texto, x_inicio, x_fim, y_topo, altura, tamanho_fonte=30,
                                       cor=(0.8, 0.8, 0.8), angulo=25):
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

    def exportar_movimentacoes_jpg(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        dialog = DialogFiltroData(self.filtro_data_de.date(), self.filtro_data_ate.date(), self)
        if not dialog.exec():
            return

        data_de, data_ate = dialog.get_datas()
        data_de = data_de.toPython()
        data_ate = data_ate.toPython()
        fornecedor_id = self.fornecedor['id']

        def tarefa_jpg():
            compras = listar_movimentacoes(fornecedor_id, data_de, data_ate)
            if not compras:
                return None

            compras = compras[::-1]

            saldo_por_id = obter_saldos_acumulados(fornecedor_id, data_de, data_ate, remove_acento)
            mov_ids = [mov['id'] for mov in compras]
            itens_por_mov = listar_itens_movimentacao(mov_ids)
            saldo_anterior = obter_saldo_anterior(fornecedor_id, data_de, remove_acento)

            largura_img = 1200
            margem = 20 * mm
            espacamento_compra = 10
            espacamento_transacao = 10

            altura_total = margem + 40
            blocos = []
            for mov in compras:
                bloco = {}
                bloco['mov'] = mov
                bloco['itens'] = itens_por_mov.get(mov['id'], []) if mov['tipo'].lower() in ("compra", "venda") else []
                if remove_acento(mov['tipo']) == "transacao":
                    bloco['altura'] = 210
                else:
                    bloco['altura'] = 250 + 28 * (len(bloco['itens']) if bloco['itens'] else 1)
                altura_total += bloco['altura'] + (
                    espacamento_transacao if remove_acento(mov['tipo']) == "transacao" else espacamento_compra)
                blocos.append(bloco)

            altura_total += 40

            try:
                fonte = ImageFont.truetype("arial.ttf", 18)
                fonte_bold = ImageFont.truetype("arialbd.ttf", 24)
                fonte_mono = ImageFont.truetype("arial.ttf", 16)
                fonte_menor = ImageFont.truetype("arial.ttf", 15)
                fonte_saldo = ImageFont.truetype("arialbd.ttf", 17)
                fonte_valor_op = ImageFont.truetype("arialbd.ttf", 26)
            except IOError:
                fonte = fonte_bold = fonte_mono = fonte_menor = fonte_saldo = fonte_valor_op = ImageFont.load_default()

            imagem = Image.new("RGB", (int(largura_img), int(altura_total)), "white")
            draw = ImageDraw.Draw(imagem)
            y_base = margem
            marca_dagua_blocos = []

            # Cabeçalho fornecedor e balança
            if compras:
                nome_fornecedor = compras[0]['fornecedor']
                num_balanca = compras[0]['fornecedores_numerobalanca']
                draw.text((margem, y_base),
                          f"Extrato de movimentações - Fornecedor: {nome_fornecedor}  |  Balança: {num_balanca}",
                          font=fonte_bold, fill="black")
                y_base += 30

            # Cabeçalho de datas
            if data_de != data_ate:
                draw.text((margem, y_base),
                          f"Do dia {data_de.strftime('%d/%m/%Y')} até {data_ate.strftime('%d/%m/%Y')}", font=fonte,
                          fill="black")
                y_base += 25

            cor_saldo = (0, 70, 0) if saldo_anterior >= 0 else (220, 0, 0)
            draw.text((margem, y_base), f"SALDO ANTERIOR AO PERÍODO: R$ {float(saldo_anterior):,.2f}", fill=cor_saldo,
                      font=fonte_bold)
            y_base += 30

            for bloco in blocos:
                mov = bloco['mov']
                itens = bloco['itens']
                tipo_raw = mov['tipo']
                tipo = tipo_raw.capitalize()
                if remove_acento(tipo_raw).lower() == "transacao":
                    tipo = "Transação"
                direcao = (mov.get('direcao') or "").lower()
                descricao = mov['descricao'] or ""
                valor_operacao = float(mov['valor_operacao'] or 0)
                saldo_atual = saldo_por_id.get(mov['id'], 0)
                y = y_base

                # Exibe só o tipo
                draw.text((margem, y), f"{tipo}", fill="black", font=fonte_bold)
                y += 36

                if direcao == "saida":
                    draw.text((margem, y), "Pagamento efetuado", fill="black", font=fonte)
                    y += 24
                elif direcao == "entrada":
                    draw.text((margem, y), "Pagamento recebido", fill="black", font=fonte)
                    y += 24

                if 'data' in mov and mov['data']:
                    if isinstance(mov['data'], datetime):
                        data_str = mov['data'].strftime('%d/%m/%Y')
                    else:
                        data_str = str(mov['data'])
                    draw.text((margem, y), f"Data: {data_str}", fill="black", font=fonte)
                    y += 24

                if descricao:
                    draw.text((margem, y), f"Descrição: {descricao}", fill="black", font=fonte)
                    y += 24

                if itens:
                    # PATCH: Detecta se algum item tem número de fardos
                    mostrar_coluna_fardos = any(
                        item.get("numero_fardos") not in (None, "", 0) for item in itens
                    )
                    y += 6
                    draw.text((margem, y), "Produtos", fill="black", font=fonte_bold)
                    y += 26
                    draw.text((margem, y), "Produto", fill="black", font=fonte_menor)
                    draw.text((margem + 500, y), "Qtd", fill="black", font=fonte_menor)
                    draw.text((margem + 650, y), "Unitário", fill="black", font=fonte_menor)
                    draw.text((margem + 800, y), "Total", fill="black", font=fonte_menor)
                    if mostrar_coluna_fardos:
                        draw.text((margem + 950, y), "Nº Fardos", fill="black", font=fonte_menor)
                    y += 5
                    draw.line((margem, y + 20, largura_img - margem, y + 20), fill="black", width=1)
                    y += 22

                    total = 0
                    for item in itens:
                        draw.text((margem, y), limpar_numero_nome_produto(item['produto_nome']), fill="black",
                                  font=fonte_mono)
                        draw.text((margem + 500, y), str(item['quantidade']), fill="black", font=fonte_mono)
                        draw.text((margem + 650, y), f"R$ {item['preco_unitario']:.2f}", fill="black", font=fonte_mono)
                        draw.text((margem + 800, y), f"R$ {item['total']:.2f}", fill="black", font=fonte_mono)
                        if mostrar_coluna_fardos:
                            nfardos = item.get("numero_fardos")
                            draw.text((margem + 950, y), str(nfardos) if nfardos not in (None, "", 0) else "",
                                      fill="black", font=fonte_mono)
                        total += float(item['total'])
                        y += 28
                    y += 5
                    draw.line((margem, y, largura_img - margem, y), fill="black", width=1)
                    y += 7
                    draw.text((margem, y), f"Subtotal: R$ {total:.2f}", fill="black", font=fonte_menor)
                    y += 19
                    draw.text((margem, y), f"Total Final (com abatimento): R$ {valor_operacao:.2f}", fill="black",
                              font=fonte_menor)
                    y += 19
                else:
                    # Valor da operação em destaque e bold para transação
                    y += 8
                    draw.text((margem, y), f"Valor da Operação: R$ {valor_operacao:.2f}", fill="black",
                              font=fonte_valor_op)
                    y += 32

                saldo_str = f"SALDO TOTAL APÓS ESTA MOVIMENTAÇÃO: R$ {float(saldo_atual):,.2f}"
                cor_saldo_mov = (220, 0, 0) if saldo_atual < 0 else (0, 70, 0)
                draw.text((margem, y), saldo_str, fill=cor_saldo_mov, font=fonte_saldo)
                y += 21

                marca_dagua_blocos.append({
                    "texto": str(mov['fornecedores_numerobalanca']),
                    "x_inicio": margem,
                    "x_fim": largura_img - margem,
                    "y_inicio": y_base + 70,
                    "altura": bloco['altura'] - 70
                })

                # Espaçamento pós movimentação: menor após transação, padrão após compra/venda
                if remove_acento(tipo_raw).lower() == "transacao":
                    y_base += bloco['altura'] + espacamento_transacao
                else:
                    y_base += bloco['altura'] + espacamento_compra

            for md in marca_dagua_blocos:
                imagem = self.adicionar_marca_dagua_area(
                    imagem,
                    texto=md["texto"],
                    x_inicio=md["x_inicio"],
                    x_fim=md["x_fim"],
                    y_inicio=md["y_inicio"],
                    altura=md["altura"],
                    fonte_path="arial.ttf",
                    tamanho_fonte=36,
                    opacidade=80,
                    angulo=25
                )

            nome_arquivo = f"movimentacoes_{data_de.strftime('%Y%m%d')}_{data_ate.strftime('%d%m%Y')}_extrato.jpg"
            imagem.save(nome_arquivo)
            return nome_arquivo

        def on_jpg_ready(nome_arquivo):
            if not nome_arquivo:
                QMessageBox.warning(self, "Exportar JPG", "Nenhuma movimentação encontrada no período selecionado.")
                return
            QMessageBox.information(self, "Exportar JPG", f"Arquivo gerado com sucesso: {nome_arquivo}")
            if platform.system() == "Windows":
                os.startfile(nome_arquivo)
            elif platform.system() == "Darwin":
                os.system(f"open '{nome_arquivo}'")
            else:
                os.system(f"xdg-open '{nome_arquivo}'")

        self.worker_export_jpg = WorkerThread(tarefa_jpg)
        self.worker_export_jpg.finished.connect(on_jpg_ready)
        self.worker_export_jpg.erro.connect(self._mostrar_erro_thread)
        self.worker_export_jpg.start()

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

    def init_ui(self):
        layout_root = QHBoxLayout(self)

        # ESQUERDA
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
        categoria_principal = obter_categoria_principal(self.fornecedor['id'])
        if categoria_principal:
            self.combo_categoria.addItem(categoria_principal['nome'], categoria_principal['id'])
            self.combo_categoria.setCurrentIndex(1)
        form_grid.addWidget(QLabel("Categoria"), 2, 0)
        form_grid.addWidget(self.combo_categoria, 2, 1)

        # ========== ComboBox + QLineEdit para Abatimento/Adiantamento ==========
        self.combo_tipo_lancamento = QComboBox()
        self.combo_tipo_lancamento.addItem("Abatimento", "abatimento")
        self.combo_tipo_lancamento.addItem("Adiantamento", "adiantamento")
        self.combo_tipo_lancamento.setCurrentIndex(0)
        self.combo_tipo_lancamento.currentIndexChanged.connect(self.atualizar_total_movimentacao)

        self.input_valor_lancamento = QLineEdit()
        self.input_valor_lancamento.setPlaceholderText("Valor")
        self.input_valor_lancamento.textChanged.connect(self.atualizar_total_movimentacao)

        layout_lancamento = QHBoxLayout()
        layout_lancamento.addWidget(self.combo_tipo_lancamento)
        layout_lancamento.addWidget(self.input_valor_lancamento)

        form_grid.addWidget(QLabel("Abatimento/Adiantamento"), 3, 0)
        form_grid.addLayout(layout_lancamento, 3, 1)

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

        # Campos de produtos
        self.layout_produto = QGridLayout()
        self.combo_produto = QComboBox()
        self.combo_produto.setEditable(True)
        self.combo_produto.lineEdit().setPlaceholderText("Selecione um produto")
        self.combo_produto.lineEdit().returnPressed.connect(self.focus_quantidade)
        self.input_quantidade = QLineEdit()
        self.input_quantidade.setPlaceholderText("Quantidade")
        self.input_quantidade.setValidator(QIntValidator(1, 99999))
        self.input_quantidade.installEventFilter(self)

        # NOVO campo: Número de Fardos
        self.input_numero_fardos = QLineEdit()
        self.input_numero_fardos.setPlaceholderText("Nº de fardos")
        self.input_numero_fardos.setValidator(QIntValidator(0, 99999))
        self.input_numero_fardos.installEventFilter(self)

        self.layout_produto.addWidget(QLabel("Produto"), 0, 0)
        self.layout_produto.addWidget(self.combo_produto, 0, 1)
        self.layout_produto.addWidget(QLabel("Quantidade"), 1, 0)
        self.layout_produto.addWidget(self.input_quantidade, 1, 1)
        self.layout_produto.addWidget(QLabel("Nº de fardos"), 2, 0)
        self.layout_produto.addWidget(self.input_numero_fardos, 2, 1)

        btn_add_item = QPushButton("Adicionar Produto")
        btn_add_item.clicked.connect(self.adicionar_item)
        self.layout_produto.addWidget(btn_add_item, 3, 0, 1, 2)
        form_grid.addLayout(self.layout_produto, 8, 0, 1, 2)

        # Tabela de itens adicionados
        self.tabela_itens_adicionados = QTableWidget()
        self.tabela_itens_adicionados.setColumnCount(5)
        self.tabela_itens_adicionados.setHorizontalHeaderLabels(
            ["Produto", "Qtd", "Valor unitário", "Total", "Nº Fardos"])
        self.tabela_itens_adicionados.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.SelectedClicked)
        self.tabela_itens_adicionados.cellChanged.connect(self.atualizar_item_editado)
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

        # MEIO
        layout_meio = QVBoxLayout()
        layout_filtros = QHBoxLayout()
        self.filtro_data_de = QDateEdit()
        self.filtro_data_de.setCalendarPopup(True)
        self.filtro_data_de.setDate(QDate.currentDate().addDays(-7))
        layout_filtros.addWidget(QLabel("De:"))
        layout_filtros.addWidget(self.filtro_data_de)
        self.filtro_data_ate = QDateEdit()
        self.filtro_data_ate.setCalendarPopup(True)
        self.filtro_data_ate.setDate(QDate.currentDate())
        layout_filtros.addWidget(QLabel("Até:"))
        layout_filtros.addWidget(self.filtro_data_ate)
        btn_filtrar = QPushButton("Filtrar")
        btn_filtrar.clicked.connect(self.resetar_e_filtrar)
        layout_filtros.addWidget(btn_filtrar)
        layout_filtros.addStretch()
        layout_meio.addLayout(layout_filtros)

        self.tabela_movimentacoes = QTableWidget()
        self.tabela_movimentacoes.setColumnCount(6)
        self.tabela_movimentacoes.setHorizontalHeaderLabels([
            "ID", "Data", "Tipo", "Direção", "Descrição", "Valor Operação"
        ])
        self.tabela_movimentacoes.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_movimentacoes.cellClicked.connect(self.mostrar_itens_movimentacao)
        self.tabela_movimentacoes.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabela_movimentacoes.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout_meio.addWidget(self.tabela_movimentacoes)

        # Paginação
        paginacao_layout = QHBoxLayout()
        self.btn_pagina_anterior = QPushButton("Página anterior")
        self.label_paginacao = QLabel()
        self.btn_pagina_proxima = QPushButton("Próxima página")
        paginacao_layout.addWidget(self.btn_pagina_anterior)
        paginacao_layout.addWidget(self.label_paginacao)
        paginacao_layout.addWidget(self.btn_pagina_proxima)
        paginacao_layout.addStretch()
        layout_meio.addLayout(paginacao_layout)
        layout_meio.addStretch()

        self.btn_pagina_anterior.clicked.connect(self.ir_para_pagina_anterior)
        self.btn_pagina_proxima.clicked.connect(self.ir_para_pagina_proxima)

        # DIREITA
        layout_dir = QVBoxLayout()
        layout_dir.addWidget(QLabel("Itens da movimentação selecionada:"))
        self.tabela_itens = QTableWidget()
        self.tabela_itens.setColumnCount(4)
        self.tabela_itens.setHorizontalHeaderLabels(["Produto", "Qtd", "Preço", "Total"])
        self.tabela_itens.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_itens.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabela_itens.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout_dir.addWidget(self.tabela_itens)

        # --- Campo copiável e botão trocar conta do fornecedor ---
        self.campo_texto_copiavel = QLineEdit()
        self.campo_texto_copiavel.setReadOnly(True)
        self.campo_texto_copiavel.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.campo_texto_copiavel.mousePressEvent = self.copiar_campo_texto_copiavel
        layout_dir.addWidget(self.campo_texto_copiavel)
        self.btn_trocar_conta_fornecedor = QPushButton("Trocar conta do fornecedor (só para esta movimentação)")
        self.btn_trocar_conta_fornecedor.clicked.connect(self.abrir_dialog_troca_conta_fornecedor)
        self.campo_texto_copiavel.setVisible(False)
        self.btn_trocar_conta_fornecedor.setVisible(False)
        layout_dir.addWidget(self.btn_trocar_conta_fornecedor)
        # --- Fim bloco campo copiável ---

        layout_dir.addStretch()
        btn_exportar_pdf = QPushButton("Exportar Movimentações em PDF")
        btn_exportar_pdf.clicked.connect(self.exportar_movimentacoes_pdf)
        btn_exportar_jpg = QPushButton("Exportar Movimentações em JPG")
        btn_exportar_jpg.clicked.connect(self.exportar_movimentacoes_jpg)

        layout_dir.addWidget(btn_exportar_pdf)
        layout_dir.addWidget(btn_exportar_jpg)

        # CRIAR WIDGETS PARA O SPLITTER
        widget_esq = QWidget()
        widget_esq.setLayout(layout_esq)
        widget_meio = QWidget()
        widget_meio.setLayout(layout_meio)
        widget_dir = QWidget()
        widget_dir.setLayout(layout_dir)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(widget_esq)
        splitter.addWidget(widget_meio)
        splitter.addWidget(widget_dir)
        splitter.setSizes([320, 720, 320])

        layout_root.addWidget(splitter)

        self.atualizar_tabela()
        self.tipo_changed()
        self.atualiza_saldo_total()

    def tipo_changed(self):
        tipo = self.combo_tipo.currentText()
        is_transacao = remove_acento(tipo) == "transacao"
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
        self.input_valor_lancamento.setVisible(not is_transacao)
        self.label_total_movimentacao.setVisible(not is_transacao)
        self.atualizar_total_movimentacao()

    def resetar_e_filtrar(self):
        self.pagina_atual = 1
        self.atualizar_tabela()

    def ir_para_pagina_anterior(self):
        if self.pagina_atual > 1:
            self.pagina_atual -= 1
            self.atualizar_tabela()

    def ir_para_pagina_proxima(self):
        if self.pagina_atual < self.total_paginas:
            self.pagina_atual += 1
            self.atualizar_tabela()

    def focus_quantidade(self):
        self.input_quantidade.setFocus()

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

    def atalho_enter_quantidade(self):
        self.adicionar_item()
        self.combo_produto.setFocus()
        self.combo_produto.lineEdit().selectAll()

    def carregar_produtos(self):
        self.combo_produto.clear()
        self.combo_produto.setEditable(True)
        self.combo_produto.addItem("", None)
        for p in listar_produtos():
            self.combo_produto.addItem(p["nome"], p["id"])

    def adicionar_item(self):
        produto_id = self.combo_produto.currentData()
        quantidade_texto = self.input_quantidade.text()
        try:
            quantidade = int(quantidade_texto)
            if quantidade <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Quantidade inválida", "Digite uma quantidade inteira positiva.")
            self.input_quantidade.setFocus()
            return
        if produto_id is None:
            QMessageBox.warning(self, "Produto obrigatório", "Selecione um produto antes de adicionar.")
            self.combo_produto.setFocus()
            return
        produto = next((p for p in self.produtos if p["id"] == produto_id), None)
        if produto is None:
            QMessageBox.critical(self, "Produto não encontrado",
                                 "O produto selecionado não existe na lista. Atualize ou selecione outro.")
            return
        categoria_id = self.combo_categoria.currentData()
        if not categoria_id:
            QMessageBox.warning(self, "Categoria obrigatória", "Selecione uma categoria para o produto.")
            self.combo_categoria.setFocus()
            return
        ajuste_fixo = obter_ajuste_fixo(produto_id, categoria_id)
        preco_base = produto["preco_base"]
        preco_unitario = Decimal(str(preco_base)) + ajuste_fixo
        total = quantidade * preco_unitario

        # NOVO: número de fardos
        numero_fardos = self.input_numero_fardos.text()
        numero_fardos = int(numero_fardos) if numero_fardos else None

        self.itens_movimentacao.append({
            "produto_id": produto_id,
            "nome": produto["nome"],
            "quantidade": quantidade,
            "preco": preco_unitario,
            "total": total,
            "numero_fardos": numero_fardos
        })
        self.atualizar_tabela_itens_adicionados()
        self.combo_produto.setCurrentIndex(-1)
        self.input_quantidade.setText("")
        self.input_numero_fardos.setText("")

    def atualizar_tabela_itens_adicionados(self):
        self.tabela_itens_adicionados.blockSignals(True)
        try:
            self.tabela_itens_adicionados.setRowCount(len(self.itens_movimentacao))
            for i, item in enumerate(self.itens_movimentacao):
                # Produto (não editável)
                nome_item = QTableWidgetItem(item["nome"])
                nome_item.setFlags(nome_item.flags() & ~Qt.ItemIsEditable)
                self.tabela_itens_adicionados.setItem(i, 0, nome_item)

                # Quantidade (editável)
                qtd_item = QTableWidgetItem(str(item["quantidade"]))
                qtd_item.setFlags(qtd_item.flags() | Qt.ItemIsEditable)
                self.tabela_itens_adicionados.setItem(i, 1, qtd_item)

                # Preço unitário (editável)
                preco_item = QTableWidgetItem(decimal_para_str_brasil(item['preco'], self.locale))
                preco_item.setFlags(preco_item.flags() | Qt.ItemIsEditable)
                self.tabela_itens_adicionados.setItem(i, 2, preco_item)

                # Total (não editável)
                total_item = QTableWidgetItem(decimal_para_str_brasil(item['total'], self.locale))
                total_item.setFlags(total_item.flags() & ~Qt.ItemIsEditable)
                self.tabela_itens_adicionados.setItem(i, 3, total_item)
                # NOVO: número de fardos
                nfardos = item.get("numero_fardos")
                nf_item = QTableWidgetItem(str(nfardos) if nfardos is not None else "")
                nf_item.setFlags(nf_item.flags() | Qt.ItemIsEditable)
                self.tabela_itens_adicionados.setItem(i, 4, nf_item)
        finally:
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
        valor_texto = self.input_valor_lancamento.text().replace(',', '.')
        try:
            valor = Decimal(valor_texto) if valor_texto else Decimal('0.00')
        except Exception:
            valor = Decimal('0.00')
        tipo = self.combo_tipo_lancamento.currentData()
        total = sum(Decimal(str(item['total'])) for item in self.itens_movimentacao)
        valor_abatimento = valor if tipo == "abatimento" else Decimal('0.00')
        valor_adiantamento = valor if tipo == "adiantamento" else Decimal('0.00')
        total_final = total + valor_adiantamento - valor_abatimento
        self.label_total_movimentacao.setText(f"Total: R$ {decimal_para_str_brasil(total_final, self.locale)}")

    def finalizar_movimentacao(self):
        tipo = self.combo_tipo.currentText()
        tipo_normalizado = remove_acento(tipo)
        if not self.input_data.date().isValid():
            QMessageBox.warning(self, "Data inválida", "A data selecionada não é válida.")
            self.input_data.setFocus()
            return
        data = self.input_data.date().toPython()
        direcao = self.combo_direcao.currentText().lower() if tipo_normalizado == "transacao" else None
        descricao = self.input_descricao.text().strip()
        compra_id = self.movimentacao_edit_id

        valor_texto = self.input_valor_lancamento.text().replace(',', '.')
        try:
            valor_lancamento = Decimal(valor_texto) if valor_texto else Decimal('0.00')
        except (ValueError, InvalidOperation):
            QMessageBox.warning(self, "Erro", "Valor de abatimento/adiantamento inválido.")
            return
        tipo_lancamento = self.combo_tipo_lancamento.currentData()
        valor_abatimento = valor_lancamento if tipo_lancamento == "abatimento" else Decimal('0.00')
        valor_adiantamento = valor_lancamento if tipo_lancamento == "adiantamento" else Decimal('0.00')

        if tipo_normalizado == "transacao":
            try:
                valor_operacao = Decimal(self.input_valor_operacao.text().replace(",", "."))
                conta_padrao_id = get_conta_padrao_id(self.fornecedor['id'])
                compra_id = inserir_movimentacao(
                    self.fornecedor['id'], data, tipo, direcao, descricao,
                    valor_abatimento, valor_operacao,
                    tipo_lancamento=None, valor_lancamento=None,
                    status='Criada', origem='movimentacao', considerar_no_saldo=True,
                    dados_bancarios_id=conta_padrao_id
                )
                QMessageBox.information(self, "Sucesso", "Transação cadastrada com sucesso.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao cadastrar transação: {e}")
            self.limpar_itens()
            self.limpar_campos()
            self.atualizar_tabela()
            return
        else:
            if not self.itens_movimentacao:
                QMessageBox.warning(self, "Erro", "Adicione pelo menos um item antes de salvar.")
                return

            if compra_id is not None:
                valor_operacao = obter_valor_com_abatimento_adiantamento(compra_id)
            else:
                total = sum(Decimal(str(item['total'])) for item in self.itens_movimentacao)
                valor_operacao = total + valor_adiantamento - valor_abatimento

        itens = [
            {
                "produto_id": item["produto_id"],
                "quantidade": item["quantidade"],
                "preco_unitario": item["preco"]
            }
            for item in self.itens_movimentacao
        ]

        if compra_id is not None:
            try:
                valor_antigo_mov = obter_valor_com_abatimento_adiantamento(compra_id)

                # PATCH: grava conta bancária ao atualizar movimentação
                atualizar_movimentacao(
                    compra_id, data, tipo, direcao, descricao, valor_abatimento, valor_operacao, tipo_lancamento,
                    valor_lancamento, origem='movimentacao', considerar_no_saldo=True,
                    fornecedor_id=self.fornecedor['id'],
                    dados_bancarios_id=self.dados_bancarios_id_selecionada
                )
                if tipo_normalizado != "transacao" and itens:
                    inserir_item_compra(compra_id, itens)
                from db_context import get_cursor
                with get_cursor(commit=True) as cursor:
                    cursor.execute("DELETE FROM debitos_fornecedores WHERE compra_id = %s", (compra_id,))
                    if valor_adiantamento > 0:
                        cursor.execute("""
                                    INSERT INTO debitos_fornecedores (fornecedor_id, compra_id, valor, tipo)
                                    VALUES (%s, %s, %s, 'inclusao')
                                """, (self.fornecedor['id'], compra_id, valor_adiantamento))
                QMessageBox.information(self, "Sucesso", "Movimentação editada com sucesso.")

                if existe_transacao_saida_para_compra(compra_id):
                    compra_antiga, itens_antigos = obter_detalhes_compra(compra_id)
                    transacao = obter_transacao_saida_para_compra(compra_id)
                    valor_antigo_trans = transacao['total'] if transacao else 0.0
                    valor_novo_mov = obter_valor_com_abatimento_adiantamento(compra_id)
                    valor_novo_trans = obter_valor_com_abatimento_adiantamento(compra_id)
                    saldo_atual = float(obter_saldo_total(self.fornecedor['id'], remove_acento))
                    dialog = AtualizarTransacaoDialog(
                        valor_antigo_mov, valor_novo_mov, valor_antigo_trans, valor_novo_trans, saldo_atual, self
                    )
                    if dialog.exec() == QDialog.Accepted and dialog.resultado == "sim":
                        novo_valor = getattr(dialog, 'valor_novo_transacao_final', valor_novo_trans)
                        atualizar_movimentacao(
                            transacao['id'], data, "Transação", "Saída",
                            transacao['descricao'],
                            Decimal('0.00'), Decimal(str(novo_valor)),
                            None, None,
                            origem="movimentacao", considerar_no_saldo=True,
                            fornecedor_id=self.fornecedor['id'],
                            dados_bancarios_id=self.dados_bancarios_id_selecionada
                        )
                        QMessageBox.information(self, "Transação atualizada",
                                                "Transação vinculada à movimentação foi atualizada com sucesso.")

                # PATCH: só mostra dialog de pagamento se NÃO for transação
                if tipo_normalizado in ("compra", "venda") and not existe_transacao_saida_para_compra(compra_id):
                    saldo_atual = float(obter_saldo_total(self.fornecedor['id'], remove_acento))
                    dialog = PagamentoMovimentacaoDialog(float(valor_operacao), saldo_atual, self)
                    if dialog.exec() == QDialog.Accepted and dialog.resultado == "sim":
                        valor_pagamento = dialog.valor_lancamento
                        direcao_pagamento = "Saída" if tipo_normalizado == "compra" else "Entrada"
                        inserir_movimentacao(
                            fornecedor_id=self.fornecedor['id'],
                            data=datetime.now(),
                            tipo="Transação",
                            direcao=direcao_pagamento,
                            descricao=f"Pagamento referente à CompraID:{compra_id}",
                            valor_abatimento=Decimal('0.00'),
                            valor_operacao=Decimal(str(valor_pagamento)),
                            status="Concluída",
                            origem="movimentacao",
                            considerar_no_saldo=True,
                            dados_bancarios_id=self.dados_bancarios_id_selecionada
                        )
                        QMessageBox.information(self, "Pagamento cadastrado",
                                                "Pagamento referente à movimentação foi cadastrado com sucesso!")

            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao editar movimentação: {e}")
            self.movimentacao_edit_id = None
        else:
            try:
                # Primeiro, insere a movimentação e itens normalmente
                compra_id = inserir_movimentacao(
                    self.fornecedor['id'], data, tipo, direcao, descricao, valor_abatimento, valor_operacao,
                    tipo_lancamento=tipo_lancamento, valor_lancamento=valor_lancamento,
                    status='Criada', origem='movimentacao', considerar_no_saldo=True,
                    dados_bancarios_id=self.dados_bancarios_id_selecionada
                )
                if tipo_normalizado != "transacao" and itens:
                    inserir_item_compra(compra_id, itens)
                if valor_adiantamento > 0:
                    from db_context import get_cursor
                    with get_cursor(commit=True) as cursor:
                        cursor.execute("""
                            INSERT INTO debitos_fornecedores (fornecedor_id, compra_id, valor, tipo)
                            VALUES (%s, %s, %s, 'inclusao')
                        """, (self.fornecedor['id'], compra_id, valor_adiantamento))
                QMessageBox.information(self, "Sucesso", "Movimentação cadastrada com sucesso.")

                if tipo_normalizado in ("compra", "venda"):
                    saldo_atual = float(obter_saldo_total(self.fornecedor['id'], remove_acento))
                    dialog = PagamentoMovimentacaoDialog(float(valor_operacao), saldo_atual, self)
                    if dialog.exec() == QDialog.Accepted and dialog.resultado == "sim":
                        valor_pagamento = dialog.valor_lancamento
                        direcao_pagamento = "Saída" if tipo_normalizado == "compra" else "Entrada"
                        inserir_movimentacao(
                            fornecedor_id=self.fornecedor['id'],
                            data=datetime.now(),
                            tipo="Transação",
                            direcao=direcao_pagamento,
                            descricao=f"Pagamento referente à CompraID:{compra_id}",
                            valor_abatimento=Decimal('0.00'),
                            valor_operacao=Decimal(str(valor_pagamento)),
                            status="Concluída",
                            origem="movimentacao",
                            considerar_no_saldo=True,
                            dados_bancarios_id=self.dados_bancarios_id_selecionada
                        )
                        QMessageBox.information(self, "Pagamento cadastrado",
                                                "Pagamento referente à movimentação foi cadastrado com sucesso!")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao cadastrar movimentação: {e}")
        self.limpar_itens()
        self.limpar_campos()
        self.atualizar_tabela()
        # self.atualiza_saldo_total()

    def atualizar_tabela(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        data_de = self.filtro_data_de.date().toPython()
        data_ate = self.filtro_data_ate.date().toPython()
        offset = (self.pagina_atual - 1) * self.qtd_por_pagina
        fornecedor_id = self.fornecedor['id']
        qtd_por_pagina = self.qtd_por_pagina

        def tarefa_db():
            import json
            movimentacoes = listar_movimentacoes(fornecedor_id, data_de, data_ate, limit=qtd_por_pagina, offset=offset)
            total_movs = contar_movimentacoes(fornecedor_id, data_de, data_ate)
            mov_ids = [m["id"] for m in movimentacoes]
            itens_por_mov = listar_itens_movimentacao(mov_ids)

            import datetime

            def sanitize(obj):
                if isinstance(obj, dict):
                    return {k: sanitize(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [sanitize(x) for x in obj]
                elif isinstance(obj, Decimal):
                    return float(obj)
                elif isinstance(obj, (datetime.datetime, datetime.date, QDate)):
                    try:
                        return obj.strftime('%d/%m/%Y')
                    except Exception:
                        return str(obj)
                elif obj is None:
                    return ""
                else:
                    return obj

            movimentacoes = [sanitize(m) for m in movimentacoes]
            for k, v in itens_por_mov.items():
                itens_por_mov[k] = [sanitize(item) for item in v]

            result = [movimentacoes, int(total_movs), itens_por_mov]
            result_json = json.dumps(result)
            result_pure = json.loads(result_json)
            return result_pure

        self.worker = WorkerThread(tarefa_db)
        self.worker.finished.connect(self._atualizar_tabela_ui)
        self.worker.erro.connect(self._mostrar_erro_thread)
        self.worker.start()

    def _atualizar_tabela_ui(self, resultado):
        movimentacoes, total_movs, itens_por_mov = resultado
        self.tabela_movimentacoes.setRowCount(len(movimentacoes))
        for i, mov in enumerate(movimentacoes):
            try:
                compra_id = mov.get('id', "")
                self.tabela_movimentacoes.setItem(i, 0, QTableWidgetItem(str(compra_id)))
                self.tabela_movimentacoes.setItem(i, 1, QTableWidgetItem(mov.get('data', "")))
                tipo = mov.get('tipo', "")
                self.tabela_movimentacoes.setItem(i, 2, QTableWidgetItem(tipo))
                self.tabela_movimentacoes.setItem(i, 3, QTableWidgetItem(str(mov.get('direcao', ""))))
                self.tabela_movimentacoes.setItem(i, 4, QTableWidgetItem(mov.get('descricao', "")))

                # PATCH: para transação, sempre use mov['valor_operacao'] do banco
                if tipo.lower() == "transacao":
                    valor_operacao = mov.get('valor_operacao')
                    # Se vier None, tenta buscar 'total' (caso campo no dict seja diferente)
                    if valor_operacao is None:
                        valor_operacao = mov.get('total', 0.0)
                    self.tabela_movimentacoes.setItem(i, 5, QTableWidgetItem(f"{float(valor_operacao):.2f}"))
                else:
                    valor_operacao = obter_valor_com_abatimento_adiantamento(compra_id)
                    self.tabela_movimentacoes.setItem(i, 5, QTableWidgetItem(f"{float(valor_operacao):.2f}"))
            except Exception as e:
                print(f"Erro ao setar linha {i}: {e}, mov={mov}")

        self.total_paginas = max(1, (total_movs + self.qtd_por_pagina - 1) // self.qtd_por_pagina)
        self.label_paginacao.setText(f"Página {self.pagina_atual} de {self.total_paginas}")
        self.atualiza_saldo_total()

    def atualiza_saldo_total(self):
        saldo = obter_saldo_total(self.fornecedor['id'], remove_acento)
        self.label_saldo_total.setText(f"Saldo total: R$ {self.locale.toString(float(saldo), 'f', 2)}")

    def mostrar_itens_movimentacao(self, row, col):
        item = self.tabela_movimentacoes.item(row, 0)
        if not item:
            return
        compra_id = int(item.text())
        tipo = self.tabela_movimentacoes.item(row, 2).text().lower()
        if remove_acento(tipo) == "transacao":
            self.tabela_itens.setRowCount(0)
            self.campo_texto_copiavel.setVisible(True)
            self.btn_trocar_conta_fornecedor.setVisible(True)
            self.atualizar_campo_texto_copiavel()
            return
        else:
            self.campo_texto_copiavel.setVisible(False)
            self.btn_trocar_conta_fornecedor.setVisible(False)

        # --- PATCH: Só mostra "Nº Fardos" se algum item tiver valor não nulo e sempre na última coluna
        itens, valor_abatimento, valor_adiantamento = obter_itens_e_lancamentos_da_compra(compra_id)
        linha_extra = int(valor_adiantamento > 0) + int(valor_abatimento > 0)

        mostrar_coluna_fardos = any(
            item.get("numero_fardos") not in (None, "", 0) for item in itens
        )
        colunas = ["Produto", "Qtd", "Preço", "Total"]
        if mostrar_coluna_fardos:
            colunas.append("Nº Fardos")
        self.tabela_itens.setColumnCount(len(colunas))
        self.tabela_itens.setHorizontalHeaderLabels(colunas)
        self.tabela_itens.setRowCount(len(itens) + linha_extra)

        for i, item in enumerate(itens):
            self.tabela_itens.setItem(i, 0, QTableWidgetItem(item["produto_nome"]))
            self.tabela_itens.setItem(i, 1, QTableWidgetItem(str(item["quantidade"])))
            preco_unitario = float(item['preco_unitario'])
            preco_formatado = self.locale.toString(preco_unitario, 'f', 2)
            self.tabela_itens.setItem(i, 2, QTableWidgetItem(preco_formatado))
            total_formatado = self.locale.toString(preco_unitario * float(item['quantidade']), 'f', 2)
            self.tabela_itens.setItem(i, 3, QTableWidgetItem(total_formatado))
            if mostrar_coluna_fardos:
                nfardos = item.get("numero_fardos")
                self.tabela_itens.setItem(i, 4, QTableWidgetItem(str(nfardos) if nfardos not in (None, "", 0) else ""))

        row = len(itens)
        # Adiantamento
        if valor_adiantamento > 0:
            self.tabela_itens.setItem(row, 0, QTableWidgetItem("Adiantamento"))
            self.tabela_itens.setItem(row, 1, QTableWidgetItem(""))
            self.tabela_itens.setItem(row, 2, QTableWidgetItem(""))
            self.tabela_itens.setItem(row, 3, QTableWidgetItem(f"+{self.locale.toString(valor_adiantamento, 'f', 2)}"))
            if mostrar_coluna_fardos:
                self.tabela_itens.setItem(row, 4, QTableWidgetItem(""))
            row += 1
        # Abatimento
        if valor_abatimento > 0:
            self.tabela_itens.setItem(row, 0, QTableWidgetItem("Abatimento"))
            self.tabela_itens.setItem(row, 1, QTableWidgetItem(""))
            self.tabela_itens.setItem(row, 2, QTableWidgetItem(""))
            self.tabela_itens.setItem(row, 3, QTableWidgetItem(f"-{self.locale.toString(valor_abatimento, 'f', 2)}"))
            if mostrar_coluna_fardos:
                self.tabela_itens.setItem(row, 4, QTableWidgetItem(""))

class MovimentacoesUI(QWidget):
    def __init__(self):
        super().__init__()
        self.locale = QLocale(QLocale.Portuguese, QLocale.Brazil)
        self.fornecedores = self.listar_fornecedores()
        self.init_ui()

    def listar_fornecedores(self):
        return listar_fornecedores()

    def selecionar_fornecedor_por_numero_balanca(self, campo_input: QLineEdit, combo_fornecedor: QComboBox):
        numero = campo_input.text().strip()
        if not numero:
            return
        resultado = buscar_fornecedor_id_por_numero_balanca(numero)
        if resultado:
            idx = -1
            for i in range(combo_fornecedor.count()):
                if combo_fornecedor.itemData(i) == resultado['id']:
                    idx = i
                    break
            if idx >= 0:
                combo_fornecedor.setCurrentIndex(idx)
            else:
                QMessageBox.warning(self, "Fornecedor não encontrado",
                                    f"Nenhum fornecedor com número de balança {numero}.")
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

        # --- NOVO: Atalho ENTER no campo número da balança ---
        self.input_numero_balanca.editingFinished.connect(
            lambda: self.selecionar_fornecedor_por_numero_balanca(self.input_numero_balanca, self.combo_fornecedor)
        )
        self.input_numero_balanca.returnPressed.connect(self._enter_nova_operacao)

        # Adiciona o eventFilter para ENTER no combo
        self.combo_fornecedor.installEventFilter(self)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.fechar_aba)
        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def eventFilter(self, obj, event):
        if obj is self.combo_fornecedor and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._enter_nova_operacao()
                return True
        return super().eventFilter(obj, event)

    def _enter_nova_operacao(self):
        # Executa ação do botão nova operação ao pressionar ENTER
        self.btn_nova_op.click()

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
        try:
            tab = MovimentacaoTabUI(fornecedor)
        except Exception as e:
            print(f"Erro ao criar aba MovimentacaoTabUI: {e}")
            import traceback;
            traceback.print_exc()
            return
        title = f"{fornecedor['nome']} - {fornecedor['fornecedores_numerobalanca']}"
        self.tabs.addTab(tab, title)
        self.tabs.setCurrentWidget(tab)

    def fechar_aba(self, idx):
        self.tabs.removeTab(idx)

    def atualizar_lista_produtos(self):
        """Atualiza a lista de produtos do banco e recarrega o combo de produtos."""
        self.produtos = listar_produtos()
        # Atualize a lista de produtos em cada aba aberta
        for i in range(self.tabs.count()):
            tab_widget = self.tabs.widget(i)
            if hasattr(tab_widget, "produtos"):
                tab_widget.produtos = self.produtos
                if hasattr(tab_widget, "carregar_produtos"):
                    tab_widget.carregar_produtos()

    def showEvent(self, event):
        super().showEvent(event)
        # Se não houver nenhuma guia aberta, foca no campo de número da balança
        if self.tabs.count() == 0:
            self.input_numero_balanca.setFocus()
        else:
            # Se houver uma aba aberta, foca no combo de produtos da aba ativa
            tab = self.tabs.currentWidget()
            if tab and hasattr(tab, "combo_produto"):
                tab.combo_produto.setFocus()
        # Chama atualizar_tabela() em cada aba aberta
        for i in range(self.tabs.count()):
            tab_widget = self.tabs.widget(i)
            if tab_widget and hasattr(tab_widget, "atualizar_tabela"):
                tab_widget.atualizar_tabela()

        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id is not None:
            self.atualizar_lista_produtos()
            # Atualiza saldo da aba ativa, se houver
            tab = self.tabs.currentWidget()
            if tab and hasattr(tab, "atualiza_saldo_total"):
                tab.atualiza_saldo_total()

    def closeEvent(self, event):
        for attr in ["worker", "worker_edit", "worker_export_pdf", "worker_export_jpg"]:
            if hasattr(self, attr):
                worker = getattr(self, attr)
                if worker.isRunning():
                    worker.quit()
                    worker.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication([])
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    window = MovimentacoesUI()
    window.resize(1200, 700)
    window.show()
    sys.exit(app.exec())