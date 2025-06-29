from decimal import Decimal

def obter_total_produtos_lista(itens_compra):
    return sum(Decimal(str(item['total'])) for item in itens_compra)

def calcular_valor_com_abatimento_adiantamento(total_produtos, valor_abatimento, valor_adiantamento):
    total_produtos = Decimal(str(total_produtos))
    abatimento = Decimal(str(valor_abatimento)) if valor_abatimento else Decimal('0.0')
    adiantamento = Decimal(str(valor_adiantamento)) if valor_adiantamento else Decimal('0.0')
    return total_produtos - abatimento + adiantamento


def formatar_moeda(valor, locale):
    return locale.toString(float(valor), 'f', 2)

def atualizar_total_compra(self):
    valor_texto = self.input_valor_lancamento.text().replace(',', '.')
    try:
        valor = Decimal(valor_texto) if valor_texto else Decimal('0.00')
    except Exception:
        valor = Decimal('0.00')
    tipo = self.combo_tipo_lancamento.currentData()
    total = sum(Decimal(str(item['total'])) for item in self.itens_compra)
    if tipo == "abatimento":
        total_final = total - valor
    else:  # adiantamento
        total_final = total + valor
    total_formatado = self.locale.toString(float(total_final), 'f', 2)
    self.label_total_compra.setText(f"Total: R$ {total_formatado}")