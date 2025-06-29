from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import platform
import os

def exportar_compra_pdf(compra, itens, saldo, filename, marca_dagua_texto=""):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    y = height - 30 * mm

    try:
        pdfmetrics.registerFont(TTFont('Arial', 'arial.ttf'))
        fonte_padrao = 'Arial'
    except:
        fonte_padrao = 'Helvetica'

    c.setFont(fonte_padrao + "-Bold", 14)
    c.drawString(20 * mm, y, f"Compra ID: {compra['id']}")
    y -= 8 * mm
    c.setFont(fonte_padrao, 12)
    c.drawString(20 * mm, y, f"Fornecedor: {compra['fornecedor']}")
    y -= 6 * mm
    c.drawString(20 * mm, y, f"Data da Compra: {compra['data_compra'].strftime('%d/%m/%Y')}")
    y -= 10 * mm

    c.setFont(fonte_padrao + "-Bold", 12)
    c.drawString(20 * mm, y, "Produtos")
    y -= 6 * mm
    c.setFont(fonte_padrao + "-Bold", 11)
    c.drawString(20 * mm, y, "Produto")
    c.drawString(90 * mm, y, "Qtd")
    c.drawString(110 * mm, y, "Unitário")
    c.drawString(140 * mm, y, "Total")

    altura_cabecalho = 6 * mm
    y_linha_cabecalho = y - 2 * mm
    c.line(20 * mm, y_linha_cabecalho, 190 * mm, y_linha_cabecalho)

    y -= 8 * mm
    altura_linha = 6 * mm
    altura_tabela = altura_linha * (len(itens) + (1 if float(compra['valor_abatimento']) != 0 else 0))
    x_inicio = 20 * mm
    x_fim = 190 * mm
    y_topo = y
    if marca_dagua_texto:
        adicionar_marca_dagua_pdf_area(
            c,
            texto=marca_dagua_texto,
            x_inicio=x_inicio,
            x_fim=x_fim,
            y_topo=y_topo,
            altura=altura_tabela,
            tamanho_fonte=30,
            cor=(0.8, 0.8, 0.8),
            angulo=25,
            fonte_nome=fonte_padrao,
        )

    total = 0
    for item in itens:
        if y < 30 * mm:
            c.showPage()
            y = height - 30 * mm
        c.setFont(fonte_padrao, 11)
        c.drawString(20 * mm, y, item['produto_nome'])
        c.drawString(90 * mm, y, str(item['quantidade']))
        c.drawString(110 * mm, y, f"R$ {item['preco_unitario']:.2f}")
        c.drawString(140 * mm, y, f"R$ {item['total']:.2f}")
        total += float(item['total'])
        y -= altura_linha

    if float(compra['valor_abatimento']) != 0:
        c.setFont(fonte_padrao + "-Oblique", 11)
        c.drawString(20 * mm, y, "Abatimento/Adiantamento")
        c.drawString(140 * mm, y, f"- R$ {compra['valor_abatimento']:.2f}")
        y -= altura_linha

    y_linha_final = y + altura_linha / 2
    c.line(20 * mm, y_linha_final, 190 * mm, y_linha_final)

    y -= 10 * mm
    c.setFont(fonte_padrao + "-Bold", 12)
    c.drawString(20 * mm, y, f"Subtotal: R$ {total:.2f}")
    y -= 6 * mm
    total_com_abatimento = total - float(compra['valor_abatimento'])
    c.drawString(20 * mm, y, f"Total Final: R$ {total_com_abatimento:.2f}")

    y -= 10 * mm
    c.setFont(fonte_padrao + "-Bold", 11)
    if saldo < 0:
        c.drawString(20 * mm, y, f"Saldo positivo do fornecedor: R$ {-saldo:.2f}")
    else:
        c.drawString(20 * mm, y, f"Saldo devedor do fornecedor: R$ {abs(saldo):.2f}")

    y -= 20 * mm
    c.setFont(fonte_padrao + "-Oblique", 9)
    c.drawString(20 * mm, y, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    c.save()

    if platform.system() == "Windows":
        os.startfile(filename)
    elif platform.system() == "Darwin":
        os.system(f"open '{filename}'")
    else:
        os.system(f"xdg-open '{filename}'")

def adicionar_marca_dagua_pdf_area(c, texto, x_inicio, x_fim, y_topo, altura, tamanho_fonte=30, cor=(0.8, 0.8, 0.8), angulo=25, fonte_nome="Helvetica"):
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

def exportar_compra_jpg(compra, itens, saldo, filename, marca_dagua_texto=""):
    largura, altura = 800, 600 + (len(itens) + 1) * 25
    imagem = Image.new("RGB", (largura, altura), "white")
    draw = ImageDraw.Draw(imagem)

    try:
        fonte = ImageFont.truetype("arial.ttf", 16)
        fonte_bold = ImageFont.truetype("arialbd.ttf", 18)
        fonte_mono = ImageFont.truetype("arial.ttf", 14)
    except IOError:
        fonte = fonte_bold = fonte_mono = ImageFont.load_default()

    y = 20
    draw.text((30, y), f"Compra ID: {compra['id']}", fill="black", font=fonte_bold)
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

    if float(compra['valor_abatimento']) != 0:
        draw.text((30, y), "Abatimento/Adiantamento", fill="black", font=fonte_mono)
        draw.text((570, y), f"-{float(compra['valor_abatimento']):.2f}", fill="black", font=fonte_mono)
        y += altura_linha

    y_tabela_fim = y + 30
    linhas_y = [y_linha_cabecalho]
    linhas_y += [y_linha_cabecalho + 25 + i * altura_linha for i in range(len(itens) + (1 if float(compra['valor_abatimento']) != 0 else 0) + 1)]

    for linha_y in linhas_y:
        draw.line((colunas_x[0], linha_y, colunas_x[-1], linha_y), fill="black", width=1)
    for x in colunas_x:
        draw.line((x, linhas_y[0], x, linhas_y[-1]), fill="black", width=1)

    y = y_tabela_fim
    draw.text((30, y), f"Subtotal: R$ {total:.2f}", fill="black", font=fonte_bold)
    y += 25
    total_com_abatimento = total - float(compra['valor_abatimento'])
    draw.text((30, y), f"Total Final: R$ {total_com_abatimento:.2f}", fill="black", font=fonte_bold)
    y += 25

    if saldo < 0:
        draw.text((30, y), f"Saldo positivo do fornecedor: R$ {-saldo:.2f}", fill="black", font=fonte_bold)
    else:
        draw.text((30, y), f"Saldo devedor do fornecedor: R$ {abs(saldo):.2f}", fill="black", font=fonte_bold)
    y += 40

    draw.text((30, y), f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", fill="gray", font=fonte)

    if marca_dagua_texto:
        imagem = adicionar_marca_dagua_area(
            imagem,
            texto=marca_dagua_texto,
            x_inicio=30,
            x_fim=750,
            y_inicio=y_linha_cabecalho,
            altura=altura_linha * (len(itens) + (1 if float(compra['valor_abatimento']) != 0 else 0)),
            fonte_path="arial.ttf",
            tamanho_fonte=30,
            opacidade=80,
            angulo=25
        )

    imagem.save(filename)

    if platform.system() == "Windows":
        os.startfile(filename)
    elif platform.system() == "Darwin":
        os.system(f"open '{filename}'")
    else:
        os.system(f"xdg-open '{filename}'")

def adicionar_marca_dagua_area(imagem, texto, x_inicio, x_fim, y_inicio, altura, fonte_path="arial.ttf", tamanho_fonte=30, opacidade=80, angulo=25):
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