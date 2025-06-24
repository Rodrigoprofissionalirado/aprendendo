import sys
import os
import tempfile
import platform
import subprocess
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QMessageBox, QDialog, QFormLayout, QDialogButtonBox
)
from PySide6.QtCore import Qt, QDate, QMarginsF, QLocale
from db_context import get_cursor  # Certifique-se que seu get_cursor usa 'with'
from PySide6.QtGui import QPainter, QFont, QImage, QPageLayout
from PySide6.QtPrintSupport import QPrinter


class DebitosUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Controle de Débitos")
        self.init_ui()
        self.atualizar()

    def init_ui(self):
        layout_principal = QVBoxLayout()

        # Filtros
        layout_filtros = QGridLayout()

        self.input_num_balanca = QLineEdit()
        self.input_num_balanca.setPlaceholderText("Número da Balança")
        self.input_num_balanca.editingFinished.connect(self.selecionar_fornecedor_por_balanca)
        layout_filtros.addWidget(QLabel("Nº Balança"), 0, 0)
        layout_filtros.addWidget(self.input_num_balanca, 0, 1)

        self.combo_fornecedor = QComboBox()
        self.combo_fornecedor.currentIndexChanged.connect(self.atualizar)
        layout_filtros.addWidget(QLabel("Fornecedor"), 1, 0)
        layout_filtros.addWidget(self.combo_fornecedor, 1, 1)

        self.data_de = QDateEdit()
        self.data_ate = QDateEdit()
        self.data_de.setCalendarPopup(True)
        self.data_ate.setCalendarPopup(True)
        self.data_de.setDate(QDate.currentDate().addMonths(-1))
        self.data_ate.setDate(QDate.currentDate())
        layout_filtros.addWidget(QLabel("Data De"), 2, 0)
        layout_filtros.addWidget(self.data_de, 2, 1)
        layout_filtros.addWidget(QLabel("Data Até"), 3, 0)
        layout_filtros.addWidget(self.data_ate, 3, 1)

        btn_atualizar = QPushButton("Atualizar")
        btn_atualizar.clicked.connect(self.atualizar)
        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.clicked.connect(self.limpar_filtros)
        layout_filtros.addWidget(btn_atualizar, 4, 0, 1, 2)
        layout_filtros.addWidget(btn_cancelar, 5, 0, 1, 2)

        layout_principal.addLayout(layout_filtros)

        # Tabela
        self.tabela = QTableWidget()
        self.tabela.setColumnCount(5)
        self.tabela.setHorizontalHeaderLabels(["Data", "Descrição", "Valor", "Tipo", "Origem"])
        layout_principal.addWidget(self.tabela)

        self.label_saldo = QLabel("Saldo devedor: R$ 0,00")
        layout_principal.addWidget(self.label_saldo)

        layout_botoes = QHBoxLayout()
        self.btn_incluir = QPushButton("Incluir Débito Manual")
        self.btn_incluir.clicked.connect(self.incluir_debito_manual)
        layout_botoes.addWidget(self.btn_incluir)

        self.btn_excluir = QPushButton("Excluir Selecionado")
        self.btn_excluir.clicked.connect(self.excluir)
        layout_botoes.addWidget(self.btn_excluir)

        self.btn_exportar_pdf = QPushButton("Exportar PDF")
        self.btn_exportar_pdf.clicked.connect(self.exportar_pdf)
        layout_botoes.addWidget(self.btn_exportar_pdf)

        self.btn_exportar_jpg = QPushButton("Exportar JPG")
        self.btn_exportar_jpg.clicked.connect(self.exportar_jpg)
        layout_botoes.addWidget(self.btn_exportar_jpg)


        layout_principal.addLayout(layout_botoes)

        self.setLayout(layout_principal)
        self.carregar_fornecedores()

    def carregar_fornecedores(self):
        self.combo_fornecedor.clear()
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome FROM fornecedores")
            for f in cursor.fetchall():
                self.combo_fornecedor.addItem(f["nome"], f["id"])
        self.combo_fornecedor.setCurrentIndex(-1)

    def selecionar_fornecedor_por_balanca(self):
        numero = self.input_num_balanca.text().strip()
        if not numero:
            return
        with get_cursor() as cursor:
            cursor.execute("SELECT id FROM fornecedores WHERE fornecedores_numerobalanca = %s", (numero,))
            f = cursor.fetchone()
            if f:
                idx = self.combo_fornecedor.findData(f["id"])
                if idx >= 0:
                    self.combo_fornecedor.setCurrentIndex(idx)
            else:
                QMessageBox.warning(self, "Não encontrado", "Fornecedor não encontrado.")

    def atualizar(self):
        fornecedor_id = self.combo_fornecedor.currentData()
        data_de = self.data_de.date().toPython()
        data_ate = self.data_ate.date().toPython()

        query = """
            SELECT d.data_lancamento, d.descricao, d.valor, d.tipo,
                   IFNULL(c.id, 'Manual') as origem
            FROM debitos_fornecedores d
            LEFT JOIN compras c ON d.compra_id = c.id
            WHERE d.data_lancamento BETWEEN %s AND %s
        """
        params = [data_de, data_ate]
        if fornecedor_id:
            query += " AND d.fornecedor_id = %s"
            params.append(fornecedor_id)
        query += " ORDER BY d.data_lancamento DESC"

        with get_cursor() as cursor:
            cursor.execute(query, params)
            resultados = cursor.fetchall()

        self.tabela.setRowCount(len(resultados))
        saldo = 0.0
        for i, row in enumerate(resultados):
            self.tabela.setItem(i, 0, QTableWidgetItem(str(row["data_lancamento"])))
            self.tabela.setItem(i, 1, QTableWidgetItem(row["descricao"]))
            self.tabela.setItem(i, 2, QTableWidgetItem(f"R$ {row['valor']:.2f}"))
            self.tabela.setItem(i, 3, QTableWidgetItem("Inclusão" if row["tipo"] == "inclusao" else "Abatimento"))
            self.tabela.setItem(i, 4, QTableWidgetItem(str(row["origem"])))
            saldo += float(row["valor"]) if row["tipo"] == "inclusao" else -float(row["valor"])
        self.label_saldo.setText(f"Saldo devedor: R$ {saldo:.2f}")

    def filtrar_por_fornecedor(self, fornecedor_id):
        idx = self.combo_fornecedor.findData(fornecedor_id)
        if idx >= 0:
            self.combo_fornecedor.setCurrentIndex(idx)
        else:
            # Se não encontrou, limpa o filtro
            self.combo_fornecedor.setCurrentIndex(-1)
        self.atualizar()

    def limpar_filtros(self):
        self.combo_fornecedor.setCurrentIndex(0)  # seleciona "todos" ou primeiro item
        self.input_num_balanca.clear()
        self.data_de.setDate(QDate.currentDate().addMonths(-1))  # data início 1 mês atrás
        self.data_ate.setDate(QDate.currentDate())  # data fim hoje
        self.atualizar()  # atualiza a tabela com filtros limpos

    def incluir_debito_manual(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Novo Débito Manual")
        form = QFormLayout(dialog)

        # Campo para número da balança
        input_num_balanca = QLineEdit()
        input_num_balanca.setPlaceholderText("Digite o número da balança")

        # Campo para selecionar o cliente
        input_cliente = QComboBox()
        fornecedores = []
        with get_cursor() as cursor:
            cursor.execute("SELECT id, nome, fornecedores_numerobalanca FROM fornecedores ORDER BY nome")
            fornecedores = cursor.fetchall()
        for f in fornecedores:
            nome_display = f"{f['nome']} (Bal: {f['fornecedores_numerobalanca']})" if f[
                'fornecedores_numerobalanca'] else f['nome']
            input_cliente.addItem(nome_display, f["id"])

        # Pré-seleciona o fornecedor do filtro, se houver (ou nenhum)
        filtro_fornecedor_id = self.combo_fornecedor.currentData()
        if filtro_fornecedor_id:
            idx = input_cliente.findData(filtro_fornecedor_id)
            input_cliente.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            input_cliente.setCurrentIndex(0)

        def selecionar_fornecedor_por_balanca_dialog():
            numero = input_num_balanca.text().strip()
            if not numero:
                return
            idx = -1
            for i in range(input_cliente.count()):
                data = input_cliente.itemData(i)
                nome = input_cliente.itemText(i)
                # Busca pelo número da balança no display do combo
                if f"(Bal: {numero})" in nome:
                    idx = i
                    break
            if idx >= 0:
                input_cliente.setCurrentIndex(idx)
            else:
                QMessageBox.warning(dialog, "Não encontrado", "Fornecedor não encontrado para este número de balança.")

        input_num_balanca.editingFinished.connect(selecionar_fornecedor_por_balanca_dialog)

        form.addRow("Número da Balança:", input_num_balanca)
        form.addRow("Cliente:", input_cliente)

        input_valor = QLineEdit()
        input_valor.setPlaceholderText("Ex: 150,00")
        input_descricao = QLineEdit()
        input_descricao.setPlaceholderText("Descrição do débito (opcional)")
        input_data = QDateEdit()
        input_data.setDate(QDate.currentDate())
        input_data.setCalendarPopup(True)

        form.addRow("Valor (R$):", input_valor)
        form.addRow("Descrição:", input_descricao)
        form.addRow("Data:", input_data)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(dialog.accept)
        botoes.rejected.connect(dialog.reject)
        form.addWidget(botoes)

        if dialog.exec() == QDialog.Accepted:
            fornecedor_id = input_cliente.currentData()
            valor_texto = input_valor.text().strip().replace(",", ".")
            descricao = input_descricao.text().strip()
            data_lancamento = input_data.date().toPython()

            try:
                valor = float(valor_texto)
            except ValueError:
                QMessageBox.warning(self, "Erro", "Valor inválido.")
                return

            with get_cursor(commit=True) as cursor:
                cursor.execute("""
                               INSERT INTO debitos_fornecedores (fornecedor_id, data_lancamento, descricao, valor, tipo)
                               VALUES (%s, %s, %s, %s, 'inclusao')
                               """, (fornecedor_id, data_lancamento, descricao, valor))
            self.atualizar()

    def excluir(self):
        linha = self.tabela.currentRow()
        if linha < 0:
            return
        data = self.tabela.item(linha, 0).text()
        descricao = self.tabela.item(linha, 1).text()
        confirm = QMessageBox.question(
            self, "Confirmação",
            f"Deseja excluir o débito de {data}\nDescrição: {descricao}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            return

        with get_cursor() as cursor:
            cursor.execute("""
                SELECT id FROM debitos_fornecedores
                WHERE data_lancamento = %s AND descricao = %s LIMIT 1
            """, (data, descricao))
            debito = cursor.fetchone()
            if not debito:
                QMessageBox.warning(self, "Erro", "Débito não encontrado.")
                return

        with get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM debitos_fornecedores WHERE id = %s", (debito["id"],))
        self.atualizar()

    def exportar_pdf(self):
        path_temp = tempfile.mktemp(suffix=".pdf")
        printer = QPrinter()
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path_temp)
        printer.setPageOrientation(QPageLayout.Landscape)
        # Define as margens (esquerda, topo, direita, inferior) em milímetros
        margins = QMarginsF(20, 20, 20, 20)
        printer.setPageMargins(margins, QPageLayout.Millimeter)

        painter = QPainter(printer)
        y_final = self._desenhar_relatorio(painter, printer)
        painter.end()

        self.abrir_arquivo(path_temp)

    def exportar_jpg(self):
        # Calcula altura com base no número de linhas + cabeçalho + totais
        linhas = self.tabela.rowCount()
        altura = 100 + (linhas + 5) * 30  # margem + cada linha + espaço para totais

        largura = 1200
        imagem = QImage(largura, altura, QImage.Format_RGB32)
        imagem.fill(Qt.white)

        painter = QPainter(imagem)
        self._desenhar_relatorio(painter)
        painter.end()

        path_temp = tempfile.mktemp(suffix=".jpg")
        imagem.save(path_temp, "JPG")
        self.abrir_arquivo(path_temp)

    def abrir_arquivo(self, path):
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(["open", path])
        else:  # Linux
            subprocess.run(["xdg-open", path])

    def _desenhar_relatorio(self, painter, printer=None):
        font = QFont("Arial", 10)
        painter.setFont(font)

        y = 30

        # Cabeçalho do relatório
        painter.setFont(QFont("Arial", 14, QFont.Bold))
        painter.drawText(20, y, "Relatório de Débitos")
        y += 25

        # Informações de filtro
        fornecedor = self.combo_fornecedor.currentText()
        data_inicio = self.data_de.date().toString("dd/MM/yyyy")
        data_fim = self.data_ate.date().toString("dd/MM/yyyy")

        painter.setFont(QFont("Arial", 10))
        if fornecedor:
            painter.drawText(20, y, f"Fornecedor: {fornecedor}")
            y += 20

        painter.drawText(20, y, f"Período: {data_inicio} até {data_fim}")
        y += 30

        # Cabeçalhos da tabela
        x_offsets = [20, 180, 480, 650, 800]
        col_widths = [160, 300, 170, 150, 150]
        headers = ["Data", "Descrição", "Valor", "Tipo", "Origem"]

        painter.setFont(QFont("Arial", 11, QFont.Bold))
        row_height = 25

        # Desenhar cabeçalhos com borda
        for i, header in enumerate(headers):
            painter.drawRect(x_offsets[i], y, col_widths[i], row_height)
            painter.drawText(x_offsets[i] + 5, y + 17, header)
        y += row_height

        # Dados da tabela + cálculo de totais
        painter.setFont(QFont("Arial", 10))
        total_inclusoes = 0.0
        total_abatimentos = 0.0

        for row in range(self.tabela.rowCount()):
            tipo = self.tabela.item(row, 3).text().strip().lower()
            valor_str = self.tabela.item(row, 2).text().replace("R$", "").replace(",", ".").strip()

            try:
                valor = float(valor_str)
            except ValueError:
                valor = 0.0

            if "inclus" in tipo:
                total_inclusoes += valor
            elif "abat" in tipo:
                total_abatimentos += valor

            for col in range(self.tabela.columnCount()):
                texto = self.tabela.item(row, col).text()
                painter.drawRect(x_offsets[col], y, col_widths[col], row_height)
                painter.drawText(x_offsets[col] + 5, y + 17, texto)
            y += row_height

            # ➕ SE FOR PDF: quebra de página se estiver perto do fim da folha
            if printer and y > printer.height() - 100:
                printer.newPage()
                y = 30  # reinicia no topo da nova página

                # Redesenha cabeçalhos na nova página
                painter.setFont(QFont("Arial", 11, QFont.Bold))
                for i, header in enumerate(headers):
                    painter.drawRect(x_offsets[i], y, col_widths[i], row_height)
                    painter.drawText(x_offsets[i] + 5, y + 17, header)
                y += row_height

        # ➖ Linha horizontal separadora
        y += 10
        painter.drawLine(20, y, 1150, y)
        y += 20

        saldo_final = total_inclusoes - total_abatimentos

        # Totais
        painter.setFont(QFont("Arial", 11, QFont.Bold))
        painter.drawText(20, y, f"Total de Inclusões: R$ {total_inclusoes:.2f}")
        y += 20
        painter.drawText(20, y, f"Total de Abatimentos: R$ {total_abatimentos:.2f}")
        y += 20
        painter.drawText(20, y, f"Saldo Devedor Final: R$ {saldo_final:.2f}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))
    janela = DebitosUI()
    janela.resize(800, 600)
    janela.show()
    sys.exit(app.exec())
