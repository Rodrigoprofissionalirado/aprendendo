from db_context import get_cursor
from decimal import Decimal
from compras.compras_db import obter_valor_com_abatimento_adiantamento

def obter_categoria_principal(fornecedor_id):
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT id, nome FROM categorias_fornecedor_por_fornecedor WHERE fornecedor_id = %s ORDER BY id ASC LIMIT 1",
            (fornecedor_id,)
        )
        cat = cursor.fetchone()
        if not cat:
            cursor.execute("SELECT id, nome FROM categorias_fornecedor_por_fornecedor WHERE nome = %s LIMIT 1", ('Padrão',))
            cat = cursor.fetchone()
        return cat

def listar_movimentacoes(fornecedor_id, data_de=None, data_ate=None, limit=50, offset=0):
    query = """
        SELECT c.id, c.data_compra AS data, c.tipo, c.direcao, c.descricao, c.total AS valor_operacao,
               f.nome as fornecedor, f.fornecedores_numerobalanca
        FROM compras c
        JOIN fornecedores f ON c.fornecedor_id = f.id
        WHERE c.fornecedor_id = %s
          AND c.considerar_no_saldo_movimentacao=True
    """
    params = [fornecedor_id]
    if data_de:
        query += " AND c.data_compra >= %s"
        params.append(data_de)
    if data_ate:
        query += " AND c.data_compra <= %s"
        params.append(data_ate)
    query += " ORDER BY c.data_compra DESC, c.id DESC"
    query += " LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    with get_cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()

def obter_saldo_total(fornecedor_id, remove_acento):
    saldo = Decimal("0.00")
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, tipo, direcao, total, valor_abatimento, origem
            FROM compras
            WHERE fornecedor_id = %s
              AND considerar_no_saldo_movimentacao = TRUE
        """, (fornecedor_id,))
        compras = cursor.fetchall()
        for mov in compras:
            tipo = remove_acento(mov['tipo'] or '')
            direcao = remove_acento(mov['direcao'] or '')
            origem = remove_acento(mov.get('origem', '') or '')
            valor_op = Decimal(mov['total']) if mov['total'] is not None else Decimal('0.00')
            valor_abatimento = Decimal(mov['valor_abatimento']) if mov['valor_abatimento'] else Decimal('0.00')

            # Busca adiantamento vinculado à compra
            cursor.execute(
                "SELECT COALESCE(SUM(valor),0) as adiantamento FROM debitos_fornecedores WHERE compra_id = %s AND tipo = 'inclusao'",
                (mov['id'],)
            )
            row = cursor.fetchone()
            valor_adiantamento = Decimal(row['adiantamento']) if row and row['adiantamento'] else Decimal('0.00')

            valor_real = valor_op - valor_abatimento + valor_adiantamento

            if tipo == "compra":
                saldo += valor_real
            elif tipo == "venda":
                saldo -= valor_real
            elif tipo == "transacao":
                if direcao == "entrada":
                    saldo += valor_real
                elif direcao == "saida":
                    saldo -= valor_real

    return saldo

def obter_saldos_acumulados(fornecedor_id, data_de, data_ate, remove_acento):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT c.id, c.data_compra, c.tipo, c.direcao, c.total, c.valor_abatimento
            FROM compras c
            WHERE c.fornecedor_id = %s
              AND c.considerar_no_saldo_movimentacao = TRUE
            ORDER BY c.data_compra, c.id
        """, (fornecedor_id,))
        todas_movs = cursor.fetchall()

    saldo = Decimal("0.00")
    saldo_por_id = {}
    for mov in todas_movs:
        tipo = remove_acento(mov['tipo'] or '')
        direcao = remove_acento(mov['direcao'] or '')
        valor_op = Decimal(mov['total']) if mov['total'] is not None else Decimal('0.00')
        valor_abatimento = Decimal(mov.get('valor_abatimento', 0)) if mov.get('valor_abatimento', None) else Decimal('0.00')

        # Busca adiantamento vinculado à compra
        with get_cursor() as cursor2:
            cursor2.execute(
                "SELECT COALESCE(SUM(valor),0) as adiantamento FROM debitos_fornecedores WHERE compra_id = %s AND tipo = 'inclusao'",
                (mov['id'],)
            )
            row = cursor2.fetchone()
            valor_adiantamento = Decimal(row['adiantamento']) if row and row['adiantamento'] else Decimal('0.00')

        valor_real = valor_op - valor_abatimento + valor_adiantamento

        if tipo == "compra":
            saldo += valor_real
        elif tipo == "venda":
            saldo -= valor_real
        elif tipo == "transacao":
            if direcao == "entrada":
                saldo += valor_real
            elif direcao == "saida":
                saldo -= valor_real
        saldo_por_id[mov['id']] = saldo

    # Filtra apenas ids dentro do intervalo exportado
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT c.id
            FROM compras c
            WHERE c.fornecedor_id = %s
              AND c.considerar_no_saldo_movimentacao = TRUE
              AND c.data_compra >= %s
              AND c.data_compra <= %s
            ORDER BY c.data_compra, c.id
        """, (fornecedor_id, data_de, data_ate))
        exportadas = [row['id'] for row in cursor.fetchall()]
    return {mid: saldo_por_id[mid] for mid in exportadas}

    # Filtra apenas ids dentro do intervalo exportado
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

def listar_itens_movimentacao(compra_id):
    from compras.compras_db import listar_itens_compra
    if not compra_id:
        return {}
    return listar_itens_compra([compra_id])

def obter_compra_por_id(compra_id):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, fornecedor_id, data_compra, tipo, direcao, descricao, total, valor_abatimento
            FROM compras
            WHERE id = %s
        """, (compra_id,))
        return cursor.fetchone()

def excluir_movimentacao(compra_id):
    with get_cursor(commit=True) as cursor:
        # Primeiro exclui adiantamentos/abatimentos vinculados
        cursor.execute("DELETE FROM debitos_fornecedores WHERE compra_id = %s", (compra_id,))
        # Depois exclui itens_compra (se usar)
        cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))
        # Por fim, exclui a movimentação em si
        cursor.execute("DELETE FROM compras WHERE id = %s", (compra_id,))

def buscar_fornecedor_id_por_numero_balanca(numero_balanca):
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM fornecedores WHERE fornecedores_numerobalanca = %s", (numero_balanca,))
        return cursor.fetchone()


def atualizar_movimentacao(compra_id, data, tipo, direcao, descricao, valor_abatimento,
    valor_operacao, tipo_lancamento,# "abatimento" ou "adiantamento"
    valor_lancamento,  # valor do campo input (decimal, sempre positivo)
    origem='movimentacao', considerar_no_saldo=True, fornecedor_id=None,
    dados_bancarios_id=None
):
    """
    Atualiza a movimentação e faz a lógica correta de abatimento/adiantamento:
    - Sempre remove lançamentos antigos de debitos_fornecedores para esta movimentação.
    - Se for abatimento, salva em compras.valor_abatimento e não insere em debitos_fornecedores.
    - Se for adiantamento, zera compras.valor_abatimento e insere em debitos_fornecedores.
    """

    with get_cursor(commit=True) as cursor:
        # Atualiza movimentação principal
        cursor.execute(
            """
            UPDATE compras
            SET data_compra=%s,
                tipo=%s,
                direcao=%s,
                descricao=%s,
                valor_abatimento=%s,
                total=%s,
                origem=%s,
                considerar_no_saldo_movimentacao=%s,
                dados_bancarios_id=%s
            WHERE id=%s
            """,
            (data, tipo, direcao, descricao,
             valor_abatimento, valor_operacao, origem, considerar_no_saldo,
             dados_bancarios_id, compra_id)
        )

        # Sempre limpa os itens antigos antes de adicionar os novos
        cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))
        # Sempre limpa lançamentos antigos de abate/adiantamento
        cursor.execute("DELETE FROM debitos_fornecedores WHERE compra_id = %s", (compra_id,))

        # Descobre o fornecedor_id se não foi passado
        if fornecedor_id is None:
            cursor.execute("SELECT fornecedor_id FROM compras WHERE id = %s", (compra_id,))
            row = cursor.fetchone()
            fornecedor_id = row["fornecedor_id"] if row else None

        # Se for adiantamento, insere o registro
        if tipo_lancamento == "adiantamento" and valor_lancamento > 0:
            cursor.execute(
                """
                INSERT INTO debitos_fornecedores (fornecedor_id, compra_id, valor, tipo)
                VALUES (%s, %s, %s, 'inclusao')
                """,
                (fornecedor_id, compra_id, valor_lancamento)
            )

        # NOVO PATCH: Atualiza o campo total com a soma dos itens (se não for transação)
        if tipo.lower() != "transação":
            cursor.execute("""
                UPDATE compras
                SET total = (SELECT COALESCE(SUM(quantidade * preco_unitario), 0)
                             FROM itens_compra
                             WHERE compra_id = %s)
                WHERE id = %s
            """, (compra_id, compra_id))

def inserir_movimentacao(
    fornecedor_id, data, tipo, direcao, descricao,
    valor_abatimento, valor_operacao,
    tipo_lancamento=None, valor_lancamento=None,
    status='Criada', origem='movimentacao', considerar_no_saldo=True,
    dados_bancarios_id=None
):
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "INSERT INTO compras (fornecedor_id, data_compra, tipo, direcao, descricao, valor_abatimento, total, status, origem, considerar_no_saldo_movimentacao, dados_bancarios_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (fornecedor_id, data, tipo, direcao, descricao, valor_abatimento, valor_operacao, status, origem, considerar_no_saldo, dados_bancarios_id)
        )
        compra_id = cursor.lastrowid
        if tipo_lancamento == "adiantamento" and valor_lancamento and valor_lancamento > 0:
            cursor.execute(
                "INSERT INTO debitos_fornecedores (fornecedor_id, compra_id, valor, tipo) VALUES (%s, %s, %s, 'inclusao')",
                (fornecedor_id, compra_id, valor_lancamento)
            )
    return compra_id

def inserir_item_compra(compra_id, itens):
    """
        Insere vários itens de compra de uma só vez usando executemany.
        :param compra_id: id da compra
        :param itens: lista de dicionários ou tuplas (produto_id, quantidade, preco_unitario)
        """
    with get_cursor(commit=True) as cursor:
        cursor.executemany(
            "INSERT INTO itens_compra (compra_id, produto_id, quantidade, preco_unitario, numero_fardos) VALUES (%s, %s, %s, %s, %s)",
            [(compra_id, item['produto_id'], item['quantidade'], item['preco_unitario'], item.get('numero_fardos')) for item in itens]
        )
    # PATCH: Atualiza o campo total após inserir itens
    with get_cursor(commit=True) as cursor:
        cursor.execute("""
            UPDATE compras
            SET total = (SELECT COALESCE(SUM(quantidade * preco_unitario), 0)
                         FROM itens_compra
                         WHERE compra_id = %s)
            WHERE id = %s
        """, (compra_id, compra_id))

def contar_movimentacoes(fornecedor_id, data_de=None, data_ate=None):
    query = """
        SELECT COUNT(*) AS total
        FROM compras c
        WHERE c.fornecedor_id = %s
    """
    params = [fornecedor_id]
    if data_de:
        query += " AND c.data_compra >= %s"
        params.append(data_de)
    if data_ate:
        query += " AND c.data_compra <= %s"
        params.append(data_ate)
    with get_cursor() as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
        return row["total"] if row else 0

def obter_saldo_anterior(fornecedor_id, data_de, remove_acento):
    saldo = Decimal("0.00")
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT tipo, direcao, total
            FROM compras
            WHERE fornecedor_id = %s
              AND considerar_no_saldo_movimentacao = TRUE
              AND data_compra < %s
            ORDER BY data_compra, id
        """, (fornecedor_id, data_de))
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

def get_conta_padrao_id(fornecedor_id):
    from compras.compras_db import listar_contas_do_fornecedor
    contas = listar_contas_do_fornecedor(fornecedor_id)
    for conta in contas:
        if conta.get('padrao', 0) == 1:
            return conta['id']
    # Se não achar nenhuma padrão, retorna None
    return None