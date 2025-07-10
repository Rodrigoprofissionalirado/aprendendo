import sys
import os, platform
import unicodedata
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QComboBox, QDateEdit, QLineEdit, QTableWidget,
    QTableWidgetItem, QMessageBox, QSizePolicy, QTabWidget, QDialog
)
from PySide6.QtGui import QIntValidator
from PySide6.QtCore import Qt, QDate, QLocale, QEvent
from decimal import Decimal, InvalidOperation
from db_context import get_cursor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from compras.compras_db import (
    listar_produtos,
    listar_itens_compra,
    obter_primeira_categoria_do_fornecedor,
    listar_fornecedores,
    listar_compras,
    obter_ajuste_fixo
)

def decimal_para_str_brasil(valor, locale=None):
    # Converte Decimal para string formatada no padrão brasileiro
    if locale is None:
        locale = QLocale(QLocale.Portuguese, QLocale.Brazil)
    return locale.toString(float(valor), 'f', 2)

def str_brasil_para_decimal(texto):
    # Converte string monetária brasileira para Decimal
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

    def listar_movimentacoes(self, data_de=None, data_ate=None):
        query = """
            SELECT c.id, c.data_compra AS data, c.tipo, c.direcao, c.descricao, c.total AS valor_operacao
            FROM compras c
            WHERE c.fornecedor_id = %s
              AND c.considerar_no_saldo_movimentacao=True
        """
        params = [self.fornecedor['id']]
        if data_de:
            query += " AND c.data_compra >= %s"
            params.append(data_de)
        if data_ate:
            query += " AND c.data_compra <= %s"
            params.append(data_ate)
        query += " ORDER BY c.data_compra DESC, c.id DESC"
        with get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    def listar_itens_movimentacao(self, compra_id):
        return listar_itens_compra(compra_id)

    def obter_saldo_total(self):
        saldo = Decimal("0.00")
        with get_cursor() as cursor:
            cursor.execute("""
                SELECT tipo, direcao, total
                FROM compras
                WHERE fornecedor_id = %s
                  AND considerar_no_saldo_movimentacao = TRUE
            """, (self.fornecedor['id'],))
            compras = cursor.fetchall()
            for mov in compras:
                tipo = remove_acento(mov['tipo'] or '')
                direcao = remove_acento(mov['direcao'] or '')
                valor_op = Decimal(mov['total']) if mov['total'] is not None else Decimal('0.00')
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
        compra_id_item = self.tabela_movimentacoes.item(linha, 0)
        if compra_id_item is None:
            return
        compra_id = int(compra_id_item.text())

        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT fornecedor_id, data_compra, tipo, direcao, descricao, total, valor_abatimento
                           FROM compras
                           WHERE id = %s
                           """, (compra_id,))
            compra = cursor.fetchone()

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

        if compra is None:
            QMessageBox.warning(self, "Erro", "Movimentação não encontrada.")
            return

        # Corrigido: limpar apenas os campos de edição, não a compra selecionada!
        self.limpar_campos()
        # Corrigido: zera apenas a lista de itens de movimentação
        self.itens_movimentacao = []

        # Preenche campos
        self.input_data.setDate(QDate(compra['data_compra']))

        tipo_mov = remove_acento(compra['tipo'])
        idx_tipo = -1
        for i in range(self.combo_tipo.count()):
            if remove_acento(self.combo_tipo.itemText(i)) == tipo_mov:
                idx_tipo = i
                break
        self.combo_tipo.setCurrentIndex(idx_tipo if idx_tipo >= 0 else 0)
        self.tipo_changed()

        if compra['tipo'].lower() == "transação":
            idx_direcao = self.combo_direcao.findText((compra['direcao'] or "").capitalize())
            self.combo_direcao.setCurrentIndex(idx_direcao if idx_direcao >= 0 else 0)
            self.input_valor_operacao.setText(str(compra['total']))
            # Corrigido: não popula itens para transação
            self.itens_movimentacao = []
            self.atualizar_tabela_itens_adicionados()
            self.input_valor_abatimento.clear()
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
            # Primeiro tenta puxar o valor do campo valor_abatimento da compra
            valor_abatimento = compra.get('valor_abatimento')
            if valor_abatimento is not None and float(valor_abatimento) > 0:
                self.input_valor_abatimento.setText(str(valor_abatimento))
            else:
                # Se não houver, tenta procurar por transação automática associada
                with get_cursor() as cursor:
                    cursor.execute("""
                                   SELECT total
                                   FROM compras
                                   WHERE tipo = 'transação'
                                     AND direcao = 'entrada'
                                     AND descricao LIKE %s
                                   """, (f"Abatimento automático referente à movimentação {compra_id}",))
                    abat = cursor.fetchone()
                if abat:
                    self.input_valor_abatimento.setText(str(abat['total']))
                else:
                    self.input_valor_abatimento.setText("")

        self.input_descricao.setText(str(compra['descricao']) if compra['descricao'] else "")
        self.movimentacao_edit_id = compra_id

    def excluir_movimentacao_finalizada(self):
        linha = self.tabela_movimentacoes.currentRow()
        if linha < 0:
            QMessageBox.information(self, "Excluir Movimentação", "Selecione uma movimentação para excluir.")
            return

        compra_id_item = self.tabela_movimentacoes.item(linha, 0)
        if compra_id_item is None:
            return

        compra_id = int(compra_id_item.text())

        confirm = QMessageBox.question(
            self,
            "Confirmar Exclusão",
            f"Tem certeza que deseja excluir a movimentação ID {compra_id}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            with get_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))
                cursor.execute("DELETE FROM compras WHERE id = %s", (compra_id,))
            QMessageBox.information(self, "Sucesso", "Movimentação excluída com sucesso.")
            self.atualizar_tabela()
            self.tabela_itens.setRowCount(0)
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
        self.input_valor_abatimento.clear()
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
            else:
                return  # Não faz nada para outras colunas

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
            self.tabela_itens_adicionados.setItem(row, 1,
                                                  QTableWidgetItem(str(self.itens_movimentacao[row]['quantidade'])))
            preco_formatado = decimal_para_str_brasil(self.itens_movimentacao[row]['preco'], self.locale)
            self.tabela_itens_adicionados.setItem(row, 2, QTableWidgetItem(preco_formatado))
            self.tabela_itens_adicionados.blockSignals(False)

    def obter_saldos_acumulados(self, fornecedor_id, data_de, data_ate):
        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT c.id, c.data_compra, c.tipo, c.direcao, c.total
                           FROM compras c
                           WHERE c.fornecedor_id = %s
                           ORDER BY c.data_compra, c.id
                           """, (fornecedor_id,))
            todas_movs = cursor.fetchall()

        saldo = Decimal("0.00")
        saldo_por_id = {}
        for mov in todas_movs:
            tipo = remove_acento(mov['tipo'] or '')
            direcao = remove_acento(mov['direcao'] or '')
            valor_op = Decimal(mov['total']) if mov['total'] is not None else Decimal('0.00')
            if tipo == "compra":
                saldo += valor_op
            elif tipo == "venda":
                saldo -= valor_op
            elif tipo == "transacao":
                if direcao == "entrada":
                    saldo += valor_op
                elif direcao == "saida":
                    saldo -= valor_op
            saldo_por_id[mov['id']] = saldo

        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT c.id
                           FROM compras c
                           WHERE c.fornecedor_id = %s
                             AND c.data_compra >= %s
                             AND c.data_compra <= %s
                           ORDER BY c.data_compra, c.id
                           """, (fornecedor_id, data_de, data_ate))
            exportadas = [row['id'] for row in cursor.fetchall()]
        return {mid: saldo_por_id[mid] for mid in exportadas}

    def exportar_movimentacoes_pdf(self):
        dialog = DialogFiltroData(self.filtro_data_de.date(), self.filtro_data_ate.date(), self)
        if not dialog.exec():
            return
        data_de, data_ate = dialog.get_datas()
        data_de = data_de.toPython()
        data_ate = data_ate.toPython()

        fornecedor_id = self.fornecedor['id']

        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT c.id,
                                  c.data_compra AS data,
                                  f.nome as fornecedor,
                                  f.fornecedores_numerobalanca,
                                  c.tipo,
                                  c.direcao,
                                  c.descricao,
                                  c.total AS valor_operacao
                           FROM compras c
                                    JOIN fornecedores f ON c.fornecedor_id = f.id
                           WHERE c.fornecedor_id = %s
                             AND c.data_compra >= %s
                             AND c.data_compra <= %s
                           ORDER BY c.data_compra, c.id
                           """, (fornecedor_id, data_de, data_ate))
            movimentacoes = cursor.fetchall()

        if not movimentacoes:
            QMessageBox.warning(self, "Exportar PDF", "Nenhuma movimentação encontrada no período selecionado.")
            return

        saldo_por_id = self.obter_saldos_acumulados(fornecedor_id, data_de, data_ate)

        # --- OTIMIZAÇÃO: Busque todos os itens de uma vez só ---
        mov_ids = [mov['id'] for mov in movimentacoes]
        itens_por_mov = {mid: [] for mid in mov_ids}
        if mov_ids:
            with get_cursor() as cursor:
                format_strings = ','.join(['%s'] * len(mov_ids))
                cursor.execute(f"""
                            SELECT i.compra_id, p.nome AS produto_nome, i.quantidade, i.preco_unitario, (i.quantidade * i.preco_unitario) AS total
                            FROM itens_compra i
                            JOIN produtos p ON i.produto_id = p.id
                            WHERE i.compra_id IN ({format_strings})
                        """, tuple(mov_ids))
                for item in cursor.fetchall():
                    itens_por_mov[item['compra_id']].append(item)
        # --------------------------------------------------------

        largura, _ = A4
        margem = 20 * mm
        espacamento_blocos = 10 * mm

        altura_total = margem
        blocos = []
        for mov in movimentacoes:
            bloco = {}
            bloco['mov'] = mov
            bloco['itens'] = itens_por_mov.get(mov['id'], []) if mov['tipo'].lower() in ("compra", "venda") else []
            bloco['altura'] = 250 + 28 * (len(bloco['itens']) if bloco['itens'] else 1)
            altura_total += bloco['altura'] + espacamento_blocos
            blocos.append(bloco)

        filename = f"movimentacoes_{data_de.strftime('%Y%m%d')}_{data_ate.strftime('%Y%m%d')}_extrato.pdf"
        c = canvas.Canvas(filename, pagesize=(largura, altura_total))
        y = altura_total - margem

        for bloco in blocos:
            mov = bloco['mov']
            itens = bloco['itens']
            tipo = mov['tipo'].capitalize()
            direcao = (mov.get('direcao') or "").capitalize()
            descricao = mov['descricao'] or ""
            valor_operacao = float(mov['valor_operacao'] or 0)
            saldo_atual = saldo_por_id.get(mov['id'], 0)

            c.setFont("Helvetica-Bold", 13)
            c.setFillColorRGB(0, 0, 0)
            c.drawString(margem, y, f"Movimentação ID: {mov['id']} | Tipo: {tipo}")
            y -= 16
            c.setFont("Helvetica", 11)
            c.drawString(margem, y, f"Fornecedor: {mov['fornecedor']}")
            y -= 13
            c.drawString(margem, y, f"Nº Balança: {mov['fornecedores_numerobalanca']}")
            y -= 13
            c.drawString(margem, y, f"Data: {mov['data'].strftime('%d/%m/%Y')}")
            y -= 13
            if direcao:
                c.drawString(margem, y, f"Direção: {direcao}")
                y -= 13
            if descricao:
                c.drawString(margem, y, f"Descrição: {descricao}")
                y -= 13

            # Marca d'água para o bloco
            self.adicionar_marca_dagua_pdf_area(
                c,
                texto=str(mov['fornecedores_numerobalanca']),
                x_inicio=margem,
                x_fim=largura - margem,
                y_topo=y + 73,  # topo do bloco (ajustar se desejar)
                altura=bloco['altura'] - 18,
                tamanho_fonte=24,  # menor
                cor=(0.8, 0.8, 0.8),
                angulo=25
            )

            if itens:
                y -= 8
                c.setFont("Helvetica-Bold", 11)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(margem, y, "Produtos")
                y -= 12
                c.setFont("Helvetica-Bold", 10)
                c.drawString(margem, y, "Produto")
                c.drawString(margem + 180, y, "Qtd")
                c.drawString(margem + 240, y, "Unitário")
                c.drawString(margem + 330, y, "Total")
                y -= 8
                c.line(margem, y, largura - margem, y)
                y -= 8
                c.setFont("Helvetica", 10)
                total = 0
                for item in itens:
                    c.drawString(margem, y, item['produto_nome'])
                    c.drawString(margem + 180, y, str(item['quantidade']))
                    c.drawString(margem + 240, y, f"R$ {item['preco_unitario']:.2f}")
                    c.drawString(margem + 330, y, f"R$ {item['total']:.2f}")
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
                y -= 13
                c.setFont("Helvetica-Bold", 11)
                c.setFillColorRGB(0, 0, 0)
                c.drawString(margem, y, f"Valor da Operação: R$ {valor_operacao:.2f}")
                y -= 13

            # SALDO TOTAL APÓS ESTA MOVIMENTAÇÃO (cor e fonte menor)
            c.setFont("Helvetica-Bold", 10)
            if saldo_atual < 0:
                c.setFillColorRGB(1, 0, 0)  # vermelho
            else:
                c.setFillColorRGB(0, 0.39, 0)  # verde escuro (aprox. #006400)
            c.drawString(margem, y, f"SALDO TOTAL APÓS ESTA MOVIMENTAÇÃO: R$ {float(saldo_atual):,.2f}")
            c.setFillColorRGB(0, 0, 0)
            y -= 14

            c.setFont("Helvetica-Oblique", 8)
            c.drawString(margem, y, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
            y -= espacamento_blocos

        c.save()
        QMessageBox.information(self, "Exportar PDF", f"PDF gerado com sucesso:\n{filename}")

        if platform.system() == "Windows":
            os.startfile(filename)
        elif platform.system() == "Darwin":
            os.system(f"open '{filename}'")
        else:
            os.system(f"xdg-open '{filename}'")

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
        dialog = DialogFiltroData(self.filtro_data_de.date(), self.filtro_data_ate.date(), self)
        if not dialog.exec():
            return

        data_de, data_ate = dialog.get_datas()
        data_de = data_de.toPython()
        data_ate = data_ate.toPython()

        fornecedor_id = self.fornecedor['id']

        with get_cursor() as cursor:
            cursor.execute("""
                           SELECT c.id,
                                  c.data_compra AS data,
                                  f.nome as fornecedor,
                                  f.fornecedores_numerobalanca,
                                  c.tipo,
                                  c.direcao,
                                  c.descricao,
                                  c.total
                           FROM compras c
                                    JOIN fornecedores f ON c.fornecedor_id = f.id
                           WHERE c.fornecedor_id = %s
                             AND c.data_compra >= %s
                             AND c.data_compra <= %s
                           ORDER BY c.data_compra, c.id
                           """, (fornecedor_id, data_de, data_ate))
            compras = cursor.fetchall()

        if not compras:
            QMessageBox.warning(self, "Exportar JPG", "Nenhuma movimentação encontrada no período selecionado.")
            return

        saldo_por_id = self.obter_saldos_acumulados(fornecedor_id, data_de, data_ate)

        # --- OTIMIZAÇÃO: Busque todos os itens de uma vez só ---
        mov_ids = [mov['id'] for mov in compras]
        itens_por_mov = {mid: [] for mid in mov_ids}
        if mov_ids:
            with get_cursor() as cursor:
                format_strings = ','.join(['%s'] * len(mov_ids))
                cursor.execute(f"""
                            SELECT i.compra_id, p.nome AS produto_nome, i.quantidade, i.preco_unitario, (i.quantidade * i.preco_unitario) AS total
                            FROM itens_compra i
                            JOIN produtos p ON i.produto_id = p.id
                            WHERE i.compra_id IN ({format_strings})
                        """, tuple(mov_ids))
                for item in cursor.fetchall():
                    itens_por_mov[item['compra_id']].append(item)
        # --------------------------------------------------------

        largura_img = 1200
        margem = 20 * mm
        espacamento_blocos = 10 * mm

        altura_total = margem
        blocos = []
        for mov in compras:
            bloco = {}
            bloco['mov'] = mov
            bloco['itens'] = itens_por_mov.get(mov['id'], []) if mov['tipo'].lower() in ("compra", "venda") else []
            bloco['altura'] = 250 + 28 * (len(bloco['itens']) if bloco['itens'] else 1)
            altura_total += bloco['altura'] + espacamento_blocos
            blocos.append(bloco)

        imagem = Image.new("RGB", (int(largura_img), int(altura_total)), "white")
        draw = ImageDraw.Draw(imagem)
        y_base = margem
        marca_dagua_blocos = []

        try:
            fonte = ImageFont.truetype("arial.ttf", 18)
            fonte_bold = ImageFont.truetype("arialbd.ttf", 24)
            fonte_mono = ImageFont.truetype("arial.ttf", 16)
            fonte_menor = ImageFont.truetype("arial.ttf", 15)
            fonte_saldo = ImageFont.truetype("arialbd.ttf", 17)
        except IOError:
            fonte = fonte_bold = fonte_mono = fonte_menor = fonte_saldo = ImageFont.load_default()

        for bloco in blocos:
            mov = bloco['mov']
            itens = bloco['itens']
            tipo = mov['tipo'].capitalize()
            direcao = (mov.get('direcao') or "").capitalize()
            descricao = mov['descricao'] or ""
            valor_operacao = float(mov['total'] or 0)
            saldo_atual = saldo_por_id.get(mov['id'], 0)
            y = y_base

            draw.text((margem, y), f"Movimentação ID: {mov['id']} | Tipo: {tipo}", fill="black", font=fonte_bold)
            y += 36
            draw.text((margem, y), f"Fornecedor: {mov['fornecedor']}", fill="black", font=fonte)
            y += 24
            draw.text((margem, y), f"Nº Balança: {mov['fornecedores_numerobalanca']}", fill="black", font=fonte)
            y += 24
            draw.text((margem, y), f"Data: {mov['data'].strftime('%d/%m/%Y')}", fill="black", font=fonte)
            y += 24
            if direcao:
                draw.text((margem, y), f"Direção: {direcao}", fill="black", font=fonte)
                y += 24
            if descricao:
                draw.text((margem, y), f"Descrição: {descricao}", fill="black", font=fonte)
                y += 24

            if itens:
                y += 6
                draw.text((margem, y), "Produtos", fill="black", font=fonte_bold)
                y += 26
                draw.text((margem, y), "Produto", fill="black", font=fonte_menor)
                draw.text((margem + 500, y), "Qtd", fill="black", font=fonte_menor)
                draw.text((margem + 650, y), "Unitário", fill="black", font=fonte_menor)
                draw.text((margem + 800, y), "Total", fill="black", font=fonte_menor)
                y += 5
                draw.line((margem, y + 20, largura_img - margem, y + 20), fill="black", width=1)
                y += 22

                total = 0
                for item in itens:
                    draw.text((margem, y), item['produto_nome'], fill="black", font=fonte_mono)
                    draw.text((margem + 500, y), str(item['quantidade']), fill="black", font=fonte_mono)
                    draw.text((margem + 650, y), f"R$ {item['preco_unitario']:.2f}", fill="black", font=fonte_mono)
                    draw.text((margem + 800, y), f"R$ {item['total']:.2f}", fill="black", font=fonte_mono)
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
                y += 8
                draw.text((margem, y), f"Valor da Operação: R$ {valor_operacao:.2f}", fill="black", font=fonte_menor)
                y += 19

            # S A L D O   (com cor)
            saldo_str = f"SALDO TOTAL APÓS ESTA MOVIMENTAÇÃO: R$ {float(saldo_atual):,.2f}"
            if saldo_atual < 0:
                cor_saldo = (220, 0, 0)  # vermelho
            else:
                cor_saldo = (0, 70, 0)  # verde escuro (aprox. #006400)
            draw.text((margem, y), saldo_str, fill=cor_saldo, font=fonte_saldo)
            y += 21

            draw.text((margem, y), f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", fill="gray",
                      font=fonte_menor)

            marca_dagua_blocos.append({
                "texto": str(mov['fornecedores_numerobalanca']),
                "x_inicio": margem,
                "x_fim": largura_img - margem,
                "y_inicio": y_base + 70,
                "altura": bloco['altura'] - 70
            })

            y_base += bloco['altura'] + 25

        # Aplica as marcas d'água reatribuindo imagem
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

        nome_arquivo = f"movimentacoes_{data_de.strftime('%Y%m%d')}_{data_ate.strftime('%Y%m%d')}_extrato.jpg"
        imagem.save(nome_arquivo)
        QMessageBox.information(self, "Exportar JPG", f"Arquivo gerado com sucesso: {nome_arquivo}")

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

        self.layout_produto = QGridLayout()
        self.combo_produto = QComboBox()
        self.combo_produto.setEditable(True)  # Permitir escrever o nome
        self.combo_produto.lineEdit().setPlaceholderText("Selecione um produto")
        self.combo_produto.lineEdit().returnPressed.connect(self.focus_quantidade)
        self.input_quantidade = QLineEdit()
        self.input_quantidade.setPlaceholderText("Quantidade")
        self.input_quantidade.setValidator(QIntValidator(1, 99999))
        self.input_quantidade.installEventFilter(self)
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
        layout_root.addLayout(layout_esq, 3)

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
        layout_root.addLayout(layout_meio, 5)

        # ----------- DIREITA: Tabela itens da movimentação selecionada -----------
        layout_dir = QVBoxLayout()
        layout_dir.addWidget(QLabel("Itens da movimentação selecionada:"))
        self.tabela_itens = QTableWidget()
        self.tabela_itens.setColumnCount(4)
        self.tabela_itens.setHorizontalHeaderLabels(["Produto", "Qtd", "Preço", "Total"])
        self.tabela_itens.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_itens.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout_dir.addWidget(self.tabela_itens)
        layout_root.addLayout(layout_dir, 3)
        # Botões de exportação abaixo do layout da direita
        btn_exportar_pdf = QPushButton("Exportar Movimentações em PDF")
        btn_exportar_pdf.clicked.connect(self.exportar_movimentacoes_pdf)
        btn_exportar_jpg = QPushButton("Exportar Movimentações em JPG")
        btn_exportar_jpg.clicked.connect(self.exportar_movimentacoes_jpg)

        layout_dir.addWidget(btn_exportar_pdf)
        layout_dir.addWidget(btn_exportar_jpg)

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

    def focus_quantidade(self):
        self.input_quantidade.setFocus()

    def eventFilter(self, obj, event):
        if obj is self.input_quantidade and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
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
        for p in self.produtos:
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
        self.itens_movimentacao.append({
            "produto_id": produto_id,
            "nome": produto["nome"],
            "quantidade": quantidade,
            "preco": preco_unitario,
            "total": total
        })
        self.atualizar_tabela_itens_adicionados()
        self.combo_produto.setCurrentIndex(-1)
        self.input_quantidade.setText("")

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
        valor_abatimento = str_brasil_para_decimal(self.input_valor_abatimento.text())
        total = sum(Decimal(str(item['total'])) for item in self.itens_movimentacao)
        total_final = total - valor_abatimento
        self.label_total_movimentacao.setText(f"Total: R$ {decimal_para_str_brasil(total_final, self.locale)}")

    def finalizar_movimentacao(self):
        tipo = self.combo_tipo.currentText().lower()
        if not self.input_data.date().isValid():
            QMessageBox.warning(self, "Data inválida", "A data selecionada não é válida.")
            self.input_data.setFocus()
            return
        data = self.input_data.date().toPython()
        direcao = self.combo_direcao.currentText().lower() if tipo == "transação" else None
        descricao = self.input_descricao.text().strip()
        valor_abatimento = None
        if tipo != "transação":
            valor_abatimento = str_brasil_para_decimal(self.input_valor_abatimento.text())
        if tipo == "transação":
            try:
                valor_operacao = Decimal(self.input_valor_operacao.text().replace(",", "."))
            except Exception as e:
                QMessageBox.warning(self, "Erro", f"Valor inválido: {e}")
                return
        else:
            if not self.itens_movimentacao:
                QMessageBox.warning(self, "Erro", "Adicione pelo menos um item antes de salvar.")
                return
            total = sum(Decimal(str(item['total'])) for item in self.itens_movimentacao)
            valor_abatimento = Decimal(self.input_valor_abatimento.text().replace(',', '.')) if self.input_valor_abatimento.text() else Decimal('0.00')
            valor_operacao = total - valor_abatimento

        if self.movimentacao_edit_id is not None:
            compra_id = self.movimentacao_edit_id
            try:
                with get_cursor(commit=True) as cursor:
                    cursor.execute(
                        "UPDATE compras SET data_compra=%s, tipo=%s, direcao=%s, descricao=%s, valor_abatimento=%s, total=%s, origem=%s, considerar_no_saldo_movimentacao=%s WHERE id=%s",
                        (data, tipo, direcao, descricao, valor_abatimento, valor_operacao, 'movimentacao', True, compra_id)
                    )
                    cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))
                    if tipo != "transação":
                        for item in self.itens_movimentacao:
                            cursor.execute(
                                "INSERT INTO itens_compra (compra_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)",
                                (compra_id, item["produto_id"], item["quantidade"], item["preco"])
                            )
                QMessageBox.information(self, "Sucesso", "Movimentação editada com sucesso.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao editar movimentação: {e}")
            self.movimentacao_edit_id = None
        else:
            with get_cursor(commit=True) as cursor:
                cursor.execute(
                    "INSERT INTO compras (fornecedor_id, data_compra, tipo, direcao, descricao, valor_abatimento, total, status, origem, considerar_no_saldo_movimentacao) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (self.fornecedor['id'], data, tipo, direcao, descricao, valor_abatimento, valor_operacao, 'Criada', 'movimentacao', True)
                )
                compra_id = cursor.lastrowid
                if tipo != "transação":
                    for item in self.itens_movimentacao:
                        cursor.execute(
                            "INSERT INTO itens_compra (compra_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)",
                            (compra_id, item["produto_id"], item["quantidade"], item["preco"])
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
                valor_op_str = decimal_para_str_brasil(valor_op, self.locale)
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
        compra_id = int(item.text())
        tipo = self.tabela_movimentacoes.item(row, 2).text().lower()
        if tipo == "transação":
            self.tabela_itens.setRowCount(0)
            return
        itens = self.listar_itens_movimentacao(compra_id)
        self.tabela_itens.setRowCount(len(itens))
        for i, item in enumerate(itens):
            self.tabela_itens.setItem(i, 0, QTableWidgetItem(item["produto_nome"]))
            self.tabela_itens.setItem(i, 1, QTableWidgetItem(str(item["quantidade"])))
            preco_unitario = float(item['preco_unitario'])
            preco_formatado = self.locale.toString(preco_unitario, 'f', 2)
            self.tabela_itens.setItem(i, 2, QTableWidgetItem(preco_formatado))
            total_formatado = self.locale.toString(preco_unitario * float(item['quantidade']), 'f', 2)
            self.tabela_itens.setItem(i, 3, QTableWidgetItem(total_formatado))

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
        fornecedor_id = self.combo_fornecedor.currentData()
        if fornecedor_id is not None:
            self.atualizar_lista_produtos()
            # Atualiza saldo da aba ativa, se houver
            tab = self.tabs.currentWidget()
            if tab and hasattr(tab, "atualiza_saldo_total"):
                tab.atualiza_saldo_total()

if __name__ == "__main__":
    app = QApplication([])
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    window = MovimentacoesUI()
    window.resize(1200, 700)
    window.show()
    sys.exit(app.exec())