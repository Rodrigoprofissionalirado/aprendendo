# Requisitos: pip install PySide6 mysql-connector-python

import sys
import mysql.connector
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QHBoxLayout,
    QComboBox, QGridLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtGui import QPixmap
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Table, TableStyle, Paragraph
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import os
import tempfile
import subprocess
import platform


def abrir_arquivo(caminho):
    """Abre arquivo PDF ou imagem com programa padrão do SO."""
    if platform.system() == "Windows":
        os.startfile(caminho)
    elif platform.system() == "Darwin":
        subprocess.call(("open", caminho))
    else:
        subprocess.call(("xdg-open", caminho))

class DB:
    def __init__(self):
        self.config = {
            'host': 'rodrigopirata.duckdns.org',
            'port': 3306,
            'user': 'rodrigo',
            'password': 'Ro220199@mariadb',
            'database': 'Trabalho'
        }

    def listar_fornecedores(self):
        with mysql.connector.connect(**self.config) as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT f.*, c.nome as categoria_nome 
                    FROM fornecedores f 
                    LEFT JOIN categorias_fornecedor c ON f.categoria_id = c.id
                    ORDER BY f.nome
                """)
                return cursor.fetchall()

    def listar_categorias(self):
        with mysql.connector.connect(**self.config) as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT id, nome FROM categorias_fornecedor ORDER BY nome")
                return cursor.fetchall()

    def adicionar_fornecedor(self, nome, categoria_id, endereco, numero_balanca):
        with mysql.connector.connect(**self.config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO fornecedores (nome, categoria_id, fornecedores_endereco, fornecedores_numerobalanca) VALUES (%s, %s, %s, %s)",
                    (nome, categoria_id, endereco, numero_balanca)
                )
                conn.commit()

    def excluir_fornecedor(self, fornecedor_id):
        with mysql.connector.connect(**self.config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM fornecedores WHERE id = %s", (fornecedor_id,))
                conn.commit()

    def atualizar_fornecedor(self, fornecedor_id, nome, categoria_id, endereco, numero_balanca):
        with mysql.connector.connect(**self.config) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE fornecedores SET nome=%s, categoria_id=%s, fornecedores_endereco=%s, fornecedores_numerobalanca=%s WHERE id=%s",
                    (nome, categoria_id, endereco, numero_balanca, fornecedor_id)
                )
                conn.commit()

    def listar_precos_por_categoria(self, categoria_id):
        with mysql.connector.connect(**self.config) as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("""
                               SELECT p.id,
                                      p.nome,
                                      p.preco_base,
                                      COALESCE(aj.ajuste_fixo, 0)                  AS ajuste_fixo,
                                      (p.preco_base + COALESCE(aj.ajuste_fixo, 0)) AS preco_final
                               FROM produtos p
                                        LEFT JOIN ajustes_fixos_produto_categoria aj
                                                  ON p.id = aj.produto_id AND aj.categoria_id = %s
                               ORDER BY p.nome
                               """, (categoria_id,))
                return cursor.fetchall()


class FornecedoresUI(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DB()
        self.fornecedores = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle('Gestão de Fornecedores')

        layout_principal = QHBoxLayout()
        layout_esquerda = QVBoxLayout()
        layout_topo = QVBoxLayout()
        layout_dados = QGridLayout()

        # Filtros
        filtro_layout = QHBoxLayout()
        self.label_filtro_nome = QLabel('Filtro Nome:')
        self.input_filtro_nome = QLineEdit()
        self.input_filtro_nome.textChanged.connect(self.aplicar_filtro)

        self.label_filtro_balanca = QLabel('Filtro Nº Balança:')
        self.input_filtro_balanca = QLineEdit()
        self.input_filtro_balanca.setValidator(QIntValidator())
        self.input_filtro_balanca.textChanged.connect(self.aplicar_filtro)

        linha_nome = QHBoxLayout()
        linha_nome.addWidget(self.label_filtro_nome)
        linha_nome.addWidget(self.input_filtro_nome)

        linha_balanca = QHBoxLayout()
        linha_balanca.addWidget(self.label_filtro_balanca)
        linha_balanca.addWidget(self.input_filtro_balanca)

        filtro_layout.addLayout(linha_nome)
        filtro_layout.addLayout(linha_balanca)

        self.label_dropdown = QLabel('Selecionar Fornecedor')
        self.combo_fornecedores = QComboBox()
        self.combo_fornecedores.currentIndexChanged.connect(self.preencher_campos_combo)

        self.label_nome = QLabel('Nome do Fornecedor')
        self.input_nome = QLineEdit()

        self.label_categoria = QLabel('Categoria')
        self.combo_categoria = QComboBox()

        self.label_endereco = QLabel('Endereço')
        self.input_endereco = QLineEdit()

        self.label_numero_balanca = QLabel('Número da Balança')
        self.input_numero_balanca = QLineEdit()
        self.input_numero_balanca.setValidator(QIntValidator())

        layout_dados.addWidget(self.label_dropdown, 0, 0, 1, 2)
        layout_dados.addWidget(self.combo_fornecedores, 1, 0, 1, 2)
        layout_dados.addWidget(self.label_nome, 2, 0)
        layout_dados.addWidget(self.input_nome, 2, 1)
        layout_dados.addWidget(self.label_categoria, 3, 0)
        layout_dados.addWidget(self.combo_categoria, 3, 1)
        layout_dados.addWidget(self.label_endereco, 4, 0)
        layout_dados.addWidget(self.input_endereco, 4, 1)
        layout_dados.addWidget(self.label_numero_balanca, 5, 0)
        layout_dados.addWidget(self.input_numero_balanca, 5, 1)

        self.btn_adicionar = QPushButton('Adicionar')
        self.btn_adicionar.clicked.connect(self.adicionar_fornecedor)
        self.btn_atualizar = QPushButton('Atualizar')
        self.btn_atualizar.clicked.connect(self.atualizar_fornecedor_combo)
        self.btn_excluir = QPushButton('Excluir')
        self.btn_excluir.clicked.connect(self.excluir_fornecedor_combo)
        self.btn_cancelar = QPushButton('Cancelar')
        self.btn_cancelar.clicked.connect(self.cancelar_edicao)

        layout_botoes = QHBoxLayout()
        layout_botoes.addWidget(self.btn_adicionar)
        layout_botoes.addWidget(self.btn_atualizar)
        layout_botoes.addWidget(self.btn_excluir)
        layout_botoes.addWidget(self.btn_cancelar)

        layout_topo.addLayout(layout_dados)
        layout_topo.addLayout(layout_botoes)

        layout_esquerda.addLayout(layout_topo)

        self.tabela = QTableWidget()
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela.setColumnCount(5)
        self.tabela.setHorizontalHeaderLabels(['ID', 'Nome', 'Categoria', 'Endereço', 'Nº Balança'])
        self.tabela.cellClicked.connect(self.linha_selecionada)

        # Tabela de preços da categoria
        self.tabela_precos = QTableWidget()
        self.tabela_precos.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabela_precos.setColumnCount(4)
        self.tabela_precos.setHorizontalHeaderLabels(['Produto', 'Preço Base', 'Ajuste Fixo', 'Preço Final'])

        layout_tabelas = QHBoxLayout()
        layout_tabelas.addWidget(self.tabela)
        layout_tabelas.addWidget(self.tabela_precos)

        # BOTÕES DE EXPORTAÇÃO
        self.btn_export_pdf = QPushButton("Exportar Tabela em PDF")
        self.btn_export_pdf.clicked.connect(self.exportar_pdf)
        self.btn_export_jpg = QPushButton("Exportar Tabela em JPG")
        self.btn_export_jpg.clicked.connect(self.exportar_jpg)

        # Adiciona botões abaixo da tabela de preços
        layout_export = QHBoxLayout()
        layout_export.addWidget(self.btn_export_pdf)
        layout_export.addWidget(self.btn_export_jpg)

        layout_principal.addLayout(layout_esquerda, 1)

        main_layout = QVBoxLayout()
        main_layout.addLayout(filtro_layout)
        main_layout.addLayout(layout_tabelas)
        # Adiciona layout_export ao layout principal logo após a tabela de preços
        main_layout.addLayout(layout_export)
        layout_principal.addLayout(main_layout, 2)

        self.setLayout(layout_principal)

        self.atualizar_tabela()
        self.carregar_combo()
        self.carregar_categorias()
        self.cancelar_edicao()

    def aplicar_filtro(self):
        nome_filtro = self.input_filtro_nome.text().lower()
        balanca_filtro = self.input_filtro_balanca.text()
        filtrados = []

        for f in self.fornecedores:
            nome_ok = nome_filtro in f['nome'].lower()
            balanca_ok = balanca_filtro == '' or str(f.get('fornecedores_numerobalanca', '') or f.get('numerobalanca', '')).startswith(balanca_filtro)
            if nome_ok and balanca_ok:
                filtrados.append(f)

        self.atualizar_tabela(filtrados)

    def atualizar_tabela(self, dados=None):
        if dados is None:
            self.fornecedores = self.db.listar_fornecedores()
            dados = self.fornecedores

        self.tabela.setRowCount(len(dados))
        for i, row in enumerate(dados):
            self.tabela.setItem(i, 0, QTableWidgetItem(str(row['id'])))
            self.tabela.setItem(i, 1, QTableWidgetItem(row['nome']))
            self.tabela.setItem(i, 2, QTableWidgetItem(row.get('categoria_nome', str(row['categoria_id']))))
            self.tabela.setItem(i, 3, QTableWidgetItem(row.get('fornecedores_endereco', '') or row.get('endereco', '')))
            self.tabela.setItem(i, 4, QTableWidgetItem(str(row.get('fornecedores_numerobalanca', '') or row.get('numerobalanca', ''))))

    def carregar_combo(self):
        self.combo_fornecedores.clear()
        for f in self.fornecedores:
            self.combo_fornecedores.addItem(f['nome'], f['id'])

    def carregar_categorias(self):
        self.combo_categoria.clear()
        categorias = self.db.listar_categorias()
        for c in categorias:
            self.combo_categoria.addItem(c['nome'], c['id'])

    def preencher_campos_combo(self, index):
        if 0 <= index < len(self.fornecedores):
            f = self.fornecedores[index]
            self.input_nome.setText(f['nome'])
            self.input_endereco.setText(f.get('fornecedores_endereco', '') or f.get('endereco', ''))
            self.input_numero_balanca.setText(str(f.get('fornecedores_numerobalanca', '') or f.get('numerobalanca', '')))
            categoria_nome = f.get('categoria_nome')
            for i in range(self.combo_categoria.count()):
                if self.combo_categoria.itemText(i) == categoria_nome:
                    self.combo_categoria.setCurrentIndex(i)
                    break
            self.preencher_tabela_precos(f.get('categoria_id'))

    def linha_selecionada(self, row, column):
        if 0 <= row < len(self.fornecedores):
            f = self.fornecedores[row]
            index_combo = self.combo_fornecedores.findData(f['id'])
            if index_combo != -1:
                self.combo_fornecedores.setCurrentIndex(index_combo)
            self.input_nome.setText(f['nome'])
            self.input_endereco.setText(f.get('fornecedores_endereco', '') or f.get('endereco', ''))
            self.input_numero_balanca.setText(str(f.get('fornecedores_numerobalanca', '') or f.get('numerobalanca', '')))
            categoria_nome = f.get('categoria_nome')
            for i in range(self.combo_categoria.count()):
                if self.combo_categoria.itemText(i) == categoria_nome:
                    self.combo_categoria.setCurrentIndex(i)
                    break
            self.preencher_tabela_precos(f.get('categoria_id'))

    def preencher_tabela_precos(self, categoria_id):
        self.tabela_precos.setRowCount(0)
        if not categoria_id:
            return
        precos = self.db.listar_precos_por_categoria(categoria_id)
        self.tabela_precos.setRowCount(len(precos))
        for i, p in enumerate(precos):
            self.tabela_precos.setItem(i, 0, QTableWidgetItem(p['nome']))
            self.tabela_precos.setItem(i, 1, QTableWidgetItem(f"{p['preco_base']:.2f}"))
            self.tabela_precos.setItem(i, 2, QTableWidgetItem(f"{p['ajuste_fixo']:.2f}"))
            self.tabela_precos.setItem(i, 3, QTableWidgetItem(f"{p['preco_final']:.2f}"))

    def adicionar_fornecedor(self):
        nome = self.input_nome.text().strip()
        categoria_id = self.combo_categoria.currentData()
        endereco = self.input_endereco.text().strip()
        numero_balanca = self.input_numero_balanca.text().strip()

        if nome and categoria_id and endereco and numero_balanca:
            try:
                self.db.adicionar_fornecedor(nome, int(categoria_id), endereco, numero_balanca)
                self.cancelar_edicao()
                self.atualizar_tabela()
                self.carregar_combo()
                self.aplicar_filtro()
            except Exception as e:
                QMessageBox.critical(self, 'Erro', str(e))
        else:
            QMessageBox.warning(self, 'Campos obrigatórios', 'Preencha todos os campos.')

    def atualizar_fornecedor_combo(self):
        index = self.combo_fornecedores.currentIndex()
        if index >= 0:
            fornecedor_id = self.combo_fornecedores.currentData()
            nome = self.input_nome.text().strip()
            categoria_id = self.combo_categoria.currentData()
            endereco = self.input_endereco.text().strip()
            numero_balanca = self.input_numero_balanca.text().strip()

            if nome and categoria_id and endereco and numero_balanca:
                try:
                    self.db.atualizar_fornecedor(fornecedor_id, nome, int(categoria_id), endereco, numero_balanca)
                    self.cancelar_edicao()
                    self.atualizar_tabela()
                    self.carregar_combo()
                    self.aplicar_filtro()
                except Exception as e:
                    QMessageBox.critical(self, 'Erro', str(e))
            else:
                QMessageBox.warning(self, 'Campos obrigatórios', 'Preencha todos os campos para atualizar.')

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
                self.carregar_combo()
                self.aplicar_filtro()
            except Exception as e:
                QMessageBox.critical(self, 'Erro', str(e))

    def cancelar_edicao(self):
        self.combo_fornecedores.setCurrentIndex(-1)
        self.input_nome.clear()
        self.input_endereco.clear()
        self.input_numero_balanca.clear()
        self.combo_categoria.setCurrentIndex(-1)
        self.input_filtro_nome.clear()
        self.input_filtro_balanca.clear()
        self.tabela_precos.setRowCount(0)

    def exportar_pdf(self):
        index = self.combo_fornecedores.currentIndex()
        if index < 0:
            QMessageBox.warning(self, "Exportar PDF", "Selecione um fornecedor para exportar a tabela.")
            return

        fornecedor = self.fornecedores[index]
        nome = fornecedor['nome']
        num_balanca = str(fornecedor.get('fornecedores_numerobalanca', '') or fornecedor.get('numerobalanca', ''))
        categoria_id = fornecedor.get('categoria_id')

        precos = self.db.listar_precos_por_categoria(categoria_id)
        if not precos:
            QMessageBox.information(self, "Exportar PDF", "Não há preços para essa categoria.")
            return

        # Filtra os produtos com preço ajustado >= 0
        precos_filtrados = [p for p in precos if (p['preco_base'] + p['ajuste_fixo']) >= 0]

        if not precos_filtrados:
            QMessageBox.information(self, "Exportar PDF", "Não há produtos com preço positivo para essa categoria.")
            return

        arquivo_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name

        c = canvas.Canvas(arquivo_pdf, pagesize=A4)
        largura, altura = A4

        margem = 2 * cm
        largura_disponivel = largura - 2 * margem
        altura_disponivel = altura - 2 * margem - 60  # reservando espaço para cabeçalho e rodapé

        linhas_por_pagina = 25  # número de linhas da tabela por página (sem contar cabeçalho)
        altura_linha = 18

        # Prepara os dados da tabela (com cabeçalho)
        dados_tabela = [["Produto", "Preço"]]
        for p in precos_filtrados:
            preco_ajustado = p['preco_base'] + p['ajuste_fixo']
            dados_tabela.append([p['nome'], f"R$ {preco_ajustado:.2f}"])

        total_linhas = len(dados_tabela) - 1  # exceto cabeçalho
        paginas = (total_linhas + linhas_por_pagina - 1) // linhas_por_pagina

        for pagina in range(paginas):
            c.setFont("Helvetica-Bold", 16)
            c.drawString(margem, altura - margem, f"Tabela de Preços - {nome} (Nº Balança: {num_balanca})")
            c.setFont("Helvetica", 10)
            data_emissao = datetime.now().strftime("%d/%m/%Y")
            c.drawString(margem, altura - margem - 20, f"Data de emissão: {data_emissao}")

            # Define fatias da tabela para a página atual
            inicio = pagina * linhas_por_pagina + 1
            fim = inicio + linhas_por_pagina
            fatia = [dados_tabela[0]] + dados_tabela[inicio:fim]

            # Define largura das colunas proporcional
            largura_colunas = [largura_disponivel * 0.7, largura_disponivel * 0.3]
            tabela = Table(fatia, colWidths=largura_colunas, rowHeights=altura_linha)

            # Estilo tabela com grid e cabeçalho cinza
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
            tabela.drawOn(c, margem, y_tabela)

            # Marca d'água no centro da tabela na página atual
            c.saveState()
            c.setFont("Helvetica-Bold", 100)
            c.setFillColorRGB(0.8, 0.8, 0.8, alpha=0.3)
            centro_x = largura / 2
            centro_y = y_tabela + altura_tabela / 2
            c.translate(centro_x, centro_y)
            c.rotate(45)
            c.drawCentredString(0, 0, num_balanca)
            c.restoreState()

            # Rodapé
            texto_rodape = "Tabela com validade de 7(sete) dias corridos, podendo ter mudanças a qualquer momento"
            c.setFont("Helvetica-Oblique", 9)
            c.drawCentredString(largura / 2, margem / 2, texto_rodape)

            c.showPage()

        c.save()
        QMessageBox.information(self, "Exportar PDF", f"Arquivo PDF gerado:\n{arquivo_pdf}")
        abrir_arquivo(arquivo_pdf)

    def exportar_jpg(self):
        index = self.combo_fornecedores.currentIndex()
        if index < 0:
            QMessageBox.warning(self, "Exportar JPG", "Selecione um fornecedor para exportar a tabela.")
            return

        fornecedor = self.fornecedores[index]
        nome = fornecedor['nome']
        num_balanca = str(fornecedor.get('fornecedores_numerobalanca', '') or fornecedor.get('numerobalanca', ''))
        categoria_id = fornecedor.get('categoria_id')

        precos = self.db.listar_precos_por_categoria(categoria_id)
        if not precos:
            QMessageBox.information(self, "Exportar JPG", "Não há preços para essa categoria.")
            return

        # Filtra os produtos com preço ajustado >= 0
        precos_filtrados = [p for p in precos if (p['preco_base'] + p['ajuste_fixo']) >= 0]

        if not precos_filtrados:
            QMessageBox.information(self, "Exportar JPG", "Não há produtos com preço positivo para essa categoria.")
            return

        try:
            fonte_titulo = ImageFont.truetype("arialbd.ttf", 24)
            fonte_texto = ImageFont.truetype("arial.ttf", 16)
            fonte_rodape = ImageFont.truetype("ariali.ttf", 12)
            fonte_marca = ImageFont.truetype("arialbd.ttf", 100)
        except IOError:
            fonte_titulo = fonte_texto = fonte_rodape = fonte_marca = ImageFont.load_default()

        largura_img = 800
        altura_linha = 30
        num_linhas = len(precos_filtrados) + 1  # +1 cabeçalho
        altura_tabela = num_linhas * altura_linha
        altura_total = altura_tabela + 200  # margem superior e rodapé

        img_base = Image.new("RGB", (largura_img, altura_total), (255, 255, 255))
        draw = ImageDraw.Draw(img_base)

        margem_topo = 40
        margem_lateral = 40

        # Título e data
        draw.text((margem_lateral, 10), f"Tabela de Preços - {nome} (Nº Balança: {num_balanca})", font=fonte_titulo,
                  fill=(0, 0, 0))
        draw.text((margem_lateral, 10 + 30), f"Data de emissão: {datetime.now().strftime('%d/%m/%Y')}",
                  font=fonte_texto, fill=(0, 0, 0))

        # Colunas
        col1_x = margem_lateral
        col2_x = int(largura_img * 0.65)
        col_end = largura_img - margem_lateral

        # Cabeçalho da tabela
        y = margem_topo + 50
        draw.rectangle([col1_x, y, col_end, y + altura_linha], fill=(100, 100, 100))
        draw.text((col1_x + 10, y + 5), "Produto", font=fonte_texto, fill=(255, 255, 255))
        draw.text((col2_x + 10, y + 5), "Preço", font=fonte_texto, fill=(255, 255, 255))
        y += altura_linha

        # Linhas da tabela
        for p in precos_filtrados:
            preco_ajustado = p['preco_base'] + p['ajuste_fixo']
            draw.rectangle([col1_x, y, col_end, y + altura_linha], outline=(0, 0, 0))
            draw.line((col2_x, y, col2_x, y + altura_linha), fill=(0, 0, 0))
            draw.text((col1_x + 10, y + 5), p['nome'], font=fonte_texto, fill=(0, 0, 0))
            draw.text((col2_x + 10, y + 5), f"R$ {preco_ajustado:.2f}", font=fonte_texto, fill=(0, 0, 0))
            y += altura_linha

        y_fim_tabela = y
        y_inicio_tabela = margem_topo + 50 + altura_linha  # após cabeçalho

        # Marca d’água no meio da tabela
        marca = Image.new("RGBA", img_base.size, (255, 255, 255, 0))
        draw_marca = ImageDraw.Draw(marca)

        bbox = draw_marca.textbbox((0, 0), num_balanca, font=fonte_marca)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]

        texto_img = Image.new("RGBA", (w * 2, h * 2), (255, 255, 255, 0))
        draw_texto = ImageDraw.Draw(texto_img)
        draw_texto.text((w // 2, h // 2), num_balanca, font=fonte_marca, fill=(80, 80, 80, 100))
        rotacionada = texto_img.rotate(45, expand=1)

        centro_y = (y_inicio_tabela + y_fim_tabela) // 2
        centro_x = largura_img // 2
        pos_x = centro_x - rotacionada.width // 2
        pos_y = centro_y - rotacionada.height // 2

        marca.paste(rotacionada, (pos_x, pos_y), rotacionada)
        imagem_final = Image.alpha_composite(img_base.convert("RGBA"), marca)

        # Rodapé
        texto_rodape = "Tabela com validade de 7(sete) dias corridos, podendo ter mudanças a qualquer momento"
        bbox = draw.textbbox((0, 0), texto_rodape, font=fonte_rodape)
        draw = ImageDraw.Draw(imagem_final)
        draw.text(((largura_img - bbox[2]) // 2, altura_total - 30), texto_rodape, font=fonte_rodape,
                  fill=(0, 0, 0, 255))

        arquivo_jpg = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
        imagem_final.convert("RGB").save(arquivo_jpg, "JPEG")
        QMessageBox.information(self, "Exportar JPG", f"Arquivo JPG gerado:\n{arquivo_jpg}")
        abrir_arquivo(arquivo_jpg)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    janela = FornecedoresUI()
    janela.resize(1100, 600)
    janela.show()
    sys.exit(app.exec())
