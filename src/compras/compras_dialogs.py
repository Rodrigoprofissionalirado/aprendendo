from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton, QDialogButtonBox, QWidget
from PySide6.QtCore import Qt
from decimal import Decimal, InvalidOperation

class DiferencaCompraDialog(QDialog):
    def __init__(self, diferenca, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diferença de valor detectada")
        self.resultado = None

        layout = QVBoxLayout(self)
        sinal = "-" if diferenca < 0 else "+"
        label = QLabel(f"Diferença detectada: {sinal}R$ {abs(diferenca):.2f}\n\n"
                       "O que deseja fazer?")
        layout.addWidget(label)

        botoes = QHBoxLayout()
        btn_somente_alterar = QPushButton("Apenas alterar valor")
        btn_converter_abate = QPushButton("Converter diferença em abate/adiantamento")
        botoes.addWidget(btn_somente_alterar)
        botoes.addWidget(btn_converter_abate)
        layout.addLayout(botoes)

        btn_somente_alterar.clicked.connect(self.somente_alterar)
        btn_converter_abate.clicked.connect(self.converter_abate)

    def somente_alterar(self):
        self.resultado = "somente_alterar"
        self.accept()

    def converter_abate(self):
        self.resultado = "converter_abate"
        self.accept()

class ConfirmTransacaoDialog(QDialog):
    def __init__(self, mensagem, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Confirmação de Transação")
        self.resultado = None

        layout = QVBoxLayout(self)
        label = QLabel(mensagem)
        layout.addWidget(label)

        botoes = QHBoxLayout()
        btn_sim = QPushButton("Sim")
        btn_nao = QPushButton("Não")
        botoes.addWidget(btn_sim)
        botoes.addWidget(btn_nao)
        layout.addLayout(botoes)

        btn_sim.clicked.connect(self.on_sim)
        btn_nao.clicked.connect(self.on_nao)

    def on_sim(self):
        self.resultado = True
        self.accept()

    def on_nao(self):
        self.resultado = False
        self.accept()


class PagamentoMovimentacaoDialog(QDialog):
    def __init__(self, valor_movimentacao, saldo_anterior, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pagamento referente à movimentação")
        self.valor_movimentacao = valor_movimentacao
        self.saldo_anterior = saldo_anterior
        layout = QVBoxLayout(self)
        self.resultado = None

        label = QLabel("Gostaria de cadastrar um pagamento referente a essa movimentação?")
        layout.addWidget(label)
        btn_layout = QHBoxLayout()
        btn_sim = QPushButton("Sim")
        btn_nao = QPushButton("Não")
        btn_layout.addWidget(btn_sim)
        btn_layout.addWidget(btn_nao)
        layout.addLayout(btn_layout)
        btn_sim.clicked.connect(self.aceitou)
        btn_nao.clicked.connect(self.rejeitou)

        # Campos só aparecem se clicar Sim
        self.campos_widget = QWidget()
        campos_layout = QVBoxLayout(self.campos_widget)
        self.campos_widget.setVisible(False)
        campos_layout.addWidget(QLabel(f"Valor da movimentação: R$ {valor_movimentacao:.2f}"))
        campos_layout.addWidget(QLabel(f"Saldo anterior: R$ {saldo_anterior:.2f}"))
        desconto_layout = QHBoxLayout()
        desconto_layout.addWidget(QLabel("Desconto: R$"))
        self.input_desconto = QLineEdit("")
        desconto_layout.addWidget(self.input_desconto)
        campos_layout.addLayout(desconto_layout)
        self.label_valor_final = QLabel(f"Valor da transação: R$ {valor_movimentacao:.2f}")
        campos_layout.addWidget(self.label_valor_final)
        self.btn_confirmar = QPushButton("Lançar pagamento")
        self.btn_confirmar.clicked.connect(self.confirmar)
        campos_layout.addWidget(self.btn_confirmar)
        layout.addWidget(self.campos_widget)
        self.input_desconto.textChanged.connect(self.atualizar_valor_final)
        self.input_desconto.returnPressed.connect(self.confirmar) # ENTER confirma
        self.valor_lancamento = valor_movimentacao

    def aceitou(self):
        self.campos_widget.setVisible(True)
        self.input_desconto.setFocus()

    def rejeitou(self):
        self.resultado = "nao"
        self.reject()

    def atualizar_valor_final(self):
        try:
            desconto = float(self.input_desconto.text().replace(",", "."))
        except Exception:
            desconto = 0.0
        valor_final = max(0.0, self.valor_movimentacao - desconto)
        self.label_valor_final.setText(f"Valor da transação: R$ {valor_final:.2f}")
        self.valor_lancamento = valor_final

    def confirmar(self):
        self.resultado = "sim"
        self.accept()

class AtualizarTransacaoDialog(QDialog):
    def __init__(self, valor_antigo_mov, valor_novo_mov, valor_antigo_trans, valor_novo_trans, saldo_anterior, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Atualizar transação correspondente")
        self.resultado = None

        layout = QVBoxLayout(self)

        label = QLabel("Deseja atualizar o valor da transação correspondente à movimentação?")
        layout.addWidget(label)
        btn_layout = QHBoxLayout()
        btn_sim = QPushButton("Sim")
        btn_nao = QPushButton("Não")
        btn_layout.addWidget(btn_sim)
        btn_layout.addWidget(btn_nao)
        layout.addLayout(btn_layout)
        btn_sim.clicked.connect(self.aceitou)
        btn_nao.clicked.connect(self.rejeitou)

        # Campos só aparecem se clicar Sim
        self.campos_widget = QWidget()
        campos_layout = QVBoxLayout(self.campos_widget)
        self.campos_widget.setVisible(False)
        campos_layout.addWidget(QLabel(f"Valor antigo da movimentação: R$ {valor_antigo_mov:.2f}"))
        campos_layout.addWidget(QLabel(f"Valor novo da movimentação: R$ {valor_novo_mov:.2f}"))
        campos_layout.addWidget(QLabel(f"Saldo anterior (sem essa movimentação e transação antiga): R$ {saldo_anterior:.2f}"))
        desconto_layout = QHBoxLayout()
        desconto_layout.addWidget(QLabel("Desconto: R$"))
        self.input_desconto = QLineEdit("")
        desconto_layout.addWidget(self.input_desconto)
        campos_layout.addLayout(desconto_layout)
        self.label_valor_antigo_trans = QLabel(f"Valor antigo da transação: R$ {valor_antigo_trans:.2f}")
        self.label_valor_novo_trans = QLabel(f"Valor novo da transação: R$ {valor_novo_trans:.2f}")
        campos_layout.addWidget(self.label_valor_antigo_trans)
        campos_layout.addWidget(self.label_valor_novo_trans)
        self.btn_confirmar = QPushButton("Atualizar transação")
        self.btn_confirmar.clicked.connect(self.confirmar)
        campos_layout.addWidget(self.btn_confirmar)
        layout.addWidget(self.campos_widget)
        self.input_desconto.textChanged.connect(self.atualizar_valor_novo_trans)
        self.input_desconto.returnPressed.connect(self.confirmar) # ENTER confirma
        self.valor_novo_transacao = valor_novo_trans

    def aceitou(self):
        self.campos_widget.setVisible(True)
        self.input_desconto.setFocus()

    def rejeitou(self):
        self.resultado = "nao"
        self.reject()

    def atualizar_valor_novo_trans(self):
        try:
            desconto = Decimal(self.input_desconto.text().replace(",", ".") or "0")
        except InvalidOperation:
            desconto = Decimal("0.00")

        valor_novo = max(Decimal("0.00"), self.valor_novo_transacao - desconto)
        self.label_valor_novo_trans.setText(f"Valor novo da transação: R$ {valor_novo:.2f}")
        self.valor_novo_transacao_final = valor_novo

    def confirmar(self):
        self.resultado = "sim"
        # Usa self.valor_novo_transacao_final como novo valor para a transação
        self.accept()

class ConfirmarExclusaoPagamentoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Excluir pagamento correspondente")
        self.resultado = None

        layout = QVBoxLayout(self)
        label = QLabel("Esta movimentação possui um pagamento correspondente cadastrado.\n"
                       "Deseja também excluir o pagamento ao remover esta movimentação?")
        layout.addWidget(label)

        botoes = QHBoxLayout()
        btn_sim = QPushButton("Sim")
        btn_nao = QPushButton("Não")
        botoes.addWidget(btn_sim)
        botoes.addWidget(btn_nao)
        layout.addLayout(botoes)

        btn_sim.clicked.connect(self.on_sim)
        btn_nao.clicked.connect(self.on_nao)

    def on_sim(self):
        self.resultado = True
        self.accept()

    def on_nao(self):
        self.resultado = False
        self.accept()