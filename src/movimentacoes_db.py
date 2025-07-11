from db_context import get_cursor
from decimal import Decimal
from functools import lru_cache

@lru_cache(maxsize=128)
def obter_categoria_principal_cached(fornecedor_id):
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

def obter_categoria_principal(fornecedor_id):
    return obter_categoria_principal_cached(fornecedor_id)

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
            SELECT tipo, direcao, total
            FROM compras
            WHERE fornecedor_id = %s
              AND considerar_no_saldo_movimentacao = TRUE
        """, (fornecedor_id,))
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

def obter_saldos_acumulados(fornecedor_id, data_de, data_ate, remove_acento):
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

def listar_itens_movimentacao(compra_id):
    from compras.compras_db import listar_itens_compra
    return listar_itens_compra(compra_id)

def obter_abatimento_automatico(compra_id):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT total
            FROM compras
            WHERE tipo = 'transação'
              AND direcao = 'entrada'
              AND descricao LIKE %s
        """, (f"Abatimento automático referente à movimentação {compra_id}",))
        return cursor.fetchone()

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
        cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))
        cursor.execute("DELETE FROM compras WHERE id = %s", (compra_id,))

def buscar_fornecedor_id_por_numero_balanca(numero_balanca):
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM fornecedores WHERE fornecedores_numerobalanca = %s", (numero_balanca,))
        return cursor.fetchone()

def atualizar_movimentacao(compra_id, data, tipo, direcao, descricao, valor_abatimento, valor_operacao, origem='movimentacao', considerar_no_saldo=True):
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "UPDATE compras SET data_compra=%s, tipo=%s, direcao=%s, descricao=%s, valor_abatimento=%s, total=%s, origem=%s, considerar_no_saldo_movimentacao=%s WHERE id=%s",
            (data, tipo, direcao, descricao, valor_abatimento, valor_operacao, origem, considerar_no_saldo, compra_id)
        )
        cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))

def inserir_movimentacao(fornecedor_id, data, tipo, direcao, descricao, valor_abatimento, valor_operacao, status='Criada', origem='movimentacao', considerar_no_saldo=True):
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "INSERT INTO compras (fornecedor_id, data_compra, tipo, direcao, descricao, valor_abatimento, total, status, origem, considerar_no_saldo_movimentacao) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (fornecedor_id, data, tipo, direcao, descricao, valor_abatimento, valor_operacao, status, origem, considerar_no_saldo)
        )
        compra_id = cursor.lastrowid
    return compra_id

def inserir_item_compra(compra_id, produto_id, quantidade, preco_unitario):
    """
        Insere vários itens de compra de uma só vez usando executemany.
        :param compra_id: id da compra
        :param itens: lista de dicionários ou tuplas (produto_id, quantidade, preco_unitario)
        """
    with get_cursor(commit=True) as cursor:
        cursor.executemany(
            "INSERT INTO itens_compra (compra_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)",
            [(compra_id, item['produto_id'], item['quantidade'], item['preco_unitario']) for item in itens]
        )

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
