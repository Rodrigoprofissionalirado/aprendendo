from db_context import get_cursor
from decimal import Decimal

def listar_fornecedores():
    with get_cursor() as cursor:
        cursor.execute("SELECT id, nome FROM fornecedores ORDER BY nome")
        return cursor.fetchall()

def listar_contas_do_fornecedor(fornecedor_id):
    if not fornecedor_id:
        return []
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, banco, agencia, conta, nome_conta, padrao
            FROM dados_bancarios_fornecedor
            WHERE fornecedor_id = %s
            ORDER BY padrao DESC, nome_conta, banco
        """, (fornecedor_id,))
        rows = cursor.fetchall()
        return [
            {
                'id': row['id'],
                'apelido': row['nome_conta'] or row['banco'],
                'banco': row['banco'],
                'agencia': row['agencia'],
                'conta': row['conta'],
                'padrao': row['padrao'],
            }
            for row in rows
        ]

def listar_produtos():
    with get_cursor() as cursor:
        cursor.execute("SELECT id, nome, preco_base FROM produtos ORDER BY nome")
        return cursor.fetchall()

def obter_produto(produto_id):
    with get_cursor() as cursor:
        cursor.execute("SELECT id, nome, preco_base FROM produtos WHERE id = %s", (produto_id,))
        return cursor.fetchone()

def listar_compras(status=None, status_not=None, data_de=None, data_ate=None, fornecedor_id=None):
    query = """
        SELECT c.id, c.data_compra AS data, c.valor_abatimento, c.total, f.nome AS fornecedor_nome, c.status
        FROM compras c
        JOIN fornecedores f ON c.fornecedor_id = f.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND c.status = %s"
        params.append(status)
    if status_not:
        query += " AND c.status != %s"
        params.append(status_not)
    if data_de:
        query += " AND c.data_compra >= %s"
        params.append(data_de)
    if data_ate:
        query += " AND c.data_compra <= %s"
        params.append(data_ate)
    if fornecedor_id:
        query += " AND f.id = %s"
        params.append(fornecedor_id)
    query += " ORDER BY c.data_compra DESC"

    with get_cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()

def adicionar_compra(fornecedor_id, data_compra, valor_abatimento, itens_compra, status):
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "INSERT INTO compras (fornecedor_id, data_compra, valor_abatimento, status) VALUES (%s, %s, %s, %s)",
            (fornecedor_id, data_compra, valor_abatimento, status)
        )
        compra_id = cursor.lastrowid

        for item in itens_compra:
            cursor.execute(
                "INSERT INTO itens_compra (compra_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)",
                (compra_id, item['produto_id'], item['quantidade'], item['preco'])
            )

        cursor.execute("""
            UPDATE compras
            SET total = (SELECT SUM(quantidade * preco_unitario)
                         FROM itens_compra
                         WHERE compra_id = %s)
            WHERE id = %s
        """, (compra_id, compra_id))

        if valor_abatimento and valor_abatimento > 0:
            cursor.execute(
                """
                INSERT INTO debitos_fornecedores (fornecedor_id, compra_id, data_lancamento, descricao, valor, tipo)
                VALUES (%s, %s, %s, %s, %s, 'abatimento')
                """,
                (fornecedor_id, compra_id, data_compra, 'Abatimento em compra', abs(valor_abatimento))
            )

    return compra_id

def atualizar_compra(compra_id, fornecedor_id, data_compra, valor_abatimento, itens_compra, status):
    with get_cursor(commit=True) as cursor:
        cursor.execute("""
            UPDATE compras
            SET fornecedor_id=%s,
                data_compra=%s,
                valor_abatimento=%s,
                status=%s
            WHERE id = %s
        """, (fornecedor_id, data_compra, valor_abatimento, status, compra_id))

        cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))

        for item in itens_compra:
            cursor.execute(
                "INSERT INTO itens_compra (compra_id, produto_id, quantidade, preco_unitario) VALUES (%s, %s, %s, %s)",
                (compra_id, item['produto_id'], item['quantidade'], item['preco'])
            )

        cursor.execute("""
            UPDATE compras
            SET total = (SELECT SUM(quantidade * preco_unitario)
                         FROM itens_compra
                         WHERE compra_id = %s)
            WHERE id = %s
        """, (compra_id, compra_id))

def listar_itens_compra(compra_id):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT p.nome AS produto_nome, i.produto_id, i.quantidade, i.preco_unitario, (i.quantidade * i.preco_unitario) AS total
            FROM itens_compra i
            JOIN produtos p ON i.produto_id = p.id
            WHERE i.compra_id = %s
        """, (compra_id,))
        return cursor.fetchall()

def obter_fornecedor_id_da_compra(compra_id):
    if not compra_id:
        return None
    with get_cursor() as cursor:
        cursor.execute("SELECT fornecedor_id FROM compras WHERE id = %s", (compra_id,))
        row = cursor.fetchone()
        if row:
            return row['fornecedor_id']
    return None

def obter_detalhes_compra(compra_id):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT f.id   AS fornecedor_id,
                   f.nome AS fornecedor,
                   f.fornecedores_numerobalanca,
                   c.data_compra,
                   c.valor_abatimento
            FROM compras c
                 JOIN fornecedores f ON c.fornecedor_id = f.id
            WHERE c.id = %s
        """, (compra_id,))
        compra = cursor.fetchone()

        cursor.execute("""
            SELECT p.nome                            AS produto_nome,
                   i.quantidade,
                   i.preco_unitario,
                   (i.quantidade * i.preco_unitario) AS total
            FROM itens_compra i
                 JOIN produtos p ON i.produto_id = p.id
            WHERE i.compra_id = %s
        """, (compra_id,))
        itens = cursor.fetchall()
    return compra, itens

def obter_total_produtos(compra_id):
    with get_cursor() as cursor:
        cursor.execute("""
                        SELECT SUM(quantidade * preco_unitario) as total_produtos
                        FROM itens_compra
                        WHERE compra_id = %s
                        """, (compra_id,))
        row = cursor.fetchone()
        return row["total_produtos"] if row and row["total_produtos"] is not None else 0

def obter_valor_com_abatimento_adiantamento(compra_id, total_produtos=None):
    if total_produtos is None:
        total_produtos = obter_total_produtos(compra_id)
    with get_cursor() as cursor:
        # Pega abatimento
        cursor.execute("SELECT valor_abatimento FROM compras WHERE id = %s", (compra_id,))
        row = cursor.fetchone()
        abatimento = Decimal(str(row["valor_abatimento"])) if row and row["valor_abatimento"] else Decimal('0.0')
        # Pega adiantamento/inclusao
        cursor.execute("""
                        SELECT COALESCE(SUM(valor), 0) as adiantamento
                        FROM debitos_fornecedores
                        WHERE compra_id = %s
                            AND tipo = 'inclusao'
                        """, (compra_id,))
        row = cursor.fetchone()
        adiantamento = Decimal(str(row["adiantamento"])) if row and row["adiantamento"] else Decimal('0.0')
    total_produtos = Decimal(str(total_produtos))
    if adiantamento > 0:
        return total_produtos + adiantamento
    else:
        return total_produtos - abatimento

def obter_saldo_devedor_fornecedor(fornecedor_id):
    with get_cursor() as cursor:
        cursor.execute("""
                        SELECT valor, tipo
                        FROM debitos_fornecedores
                        WHERE fornecedor_id = %s
                        """, (fornecedor_id,))
        saldo = Decimal('0.00')
        for row in cursor.fetchall():
            if row["tipo"] in ("inclusao", "adiantamento"):
                saldo += Decimal(str(row["valor"]))
            else:
                saldo -= Decimal(str(row["valor"]))
        return saldo

def buscar_nome_conta_padrao(fornecedor_id):
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                            SELECT nome_conta
                            FROM dados_bancarios_fornecedor
                            WHERE fornecedor_id = %s
                            AND padrao = 1 LIMIT 1
                            """, (fornecedor_id,))
            row = cursor.fetchone()
            return row["nome_conta"] if row else "Conta não cadastrada"
    except mysql.connector.Error as e:
        print(f"Erro ao buscar conta padrão: {e}")
        return "Erro ao buscar conta"

def obter_valor_com_abatimento_adiantamento(compra_id, total_produtos=None):
    if total_produtos is None:
        total_produtos = obter_total_produtos(compra_id)
    with get_cursor() as cursor:
        # Pega abatimento
        cursor.execute("SELECT valor_abatimento FROM compras WHERE id = %s", (compra_id,))
        row = cursor.fetchone()
        abatimento = Decimal(str(row["valor_abatimento"])) if row and row["valor_abatimento"] else Decimal('0.0')
        # Pega adiantamento/inclusao
        cursor.execute("""
                        SELECT COALESCE(SUM(valor), 0) as adiantamento
                        FROM debitos_fornecedores
                        WHERE compra_id = %s
                        AND tipo = 'inclusao'
                        """, (compra_id,))
        row = cursor.fetchone()
        adiantamento = Decimal(str(row["adiantamento"])) if row and row["adiantamento"] else Decimal('0.0')
    total_produtos = Decimal(str(total_produtos))
    if adiantamento > 0:
        return total_produtos + adiantamento
    else:
        return total_produtos - abatimento

def obter_saldo_devedor_fornecedor(fornecedor_id):
    with get_cursor() as cursor:
        cursor.execute("""
                        SELECT valor, tipo
                        FROM debitos_fornecedores
                        WHERE fornecedor_id = %s
                        """, (fornecedor_id,))
        saldo = Decimal('0.00')
        for row in cursor.fetchall():
            if row["tipo"] in ("inclusao", "adiantamento"):
                saldo += Decimal(str(row["valor"]))
            else:
                saldo -= Decimal(str(row["valor"]))
        return saldo

def buscar_nome_conta_padrao(fornecedor_id):
    try:
        with get_cursor() as cursor:
            cursor.execute("""
                            SELECT nome_conta
                            FROM dados_bancarios_fornecedor
                            WHERE fornecedor_id = %s
                            AND padrao = 1 LIMIT 1
                            """, (fornecedor_id,))
            row = cursor.fetchone()
            return row["nome_conta"] if row else "Conta não cadastrada"
    except mysql.connector.Error as e:
        print(f"Erro ao buscar conta padrão: {e}")
        return "Erro ao buscar conta"

def obter_categorias_do_fornecedor(fornecedor_id):
    with get_cursor() as cursor:
        cursor.execute("SELECT id, nome FROM categorias_fornecedor_por_fornecedor WHERE fornecedor_id = %s ORDER BY nome", (fornecedor_id,))
        return cursor.fetchall()

def obter_id_categoria_padrao():
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM categorias_fornecedor_por_fornecedor WHERE nome = %s LIMIT 1", ('Padrão',))
        cat = cursor.fetchone()
        return cat['id'] if cat else None

def obter_ajuste_fixo(produto_id, categoria_id):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT ajuste_fixo
            FROM ajustes_fixos_produto_fornecedor_categoria
            WHERE produto_id = %s AND categoria_id = %s
        """, (produto_id, categoria_id))
        ajuste = cursor.fetchone()
    return Decimal(str(ajuste["ajuste_fixo"])) if ajuste else Decimal('0.00')

def inserir_adiantamento(fornecedor_id, compra_id, data_compra, valor_inclusao):
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            """
            INSERT INTO debitos_fornecedores
                (fornecedor_id, compra_id, data_lancamento, descricao, valor, tipo)
            VALUES (%s, %s, %s, %s, %s, 'inclusao')
            """,
            (fornecedor_id, compra_id, data_compra, 'Inclusão em compra', abs(valor_inclusao))
        )

def inserir_abatimento(fornecedor_id, compra_id, data_compra, valor_abatimento):
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            """
            INSERT INTO debitos_fornecedores
                (fornecedor_id, compra_id, data_lancamento, descricao, valor, tipo)
            VALUES (%s, %s, %s, %s, %s, 'abatimento')
            """,
            (fornecedor_id, compra_id, data_compra, 'Abatimento em compra', abs(valor_abatimento))
        )

def remover_lancamentos_antigos(compra_id):
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "DELETE FROM debitos_fornecedores WHERE compra_id = %s AND (tipo = 'abatimento' OR tipo = 'inclusao')",
            (compra_id,)
        )

def obter_dados_para_editar_compra(compra_id):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT fornecedor_id, data_compra, valor_abatimento, status
            FROM compras WHERE id = %s
        """, (compra_id,))
        compra = cursor.fetchone()

        cursor.execute("""
            SELECT p.nome AS produto_nome, i.produto_id, i.quantidade, i.preco_unitario, (i.quantidade * i.preco_unitario) AS total
            FROM itens_compra i
            JOIN produtos p ON i.produto_id = p.id
            WHERE i.compra_id = %s
        """, (compra_id,))
        itens = cursor.fetchall()

        cursor.execute("""
            SELECT COALESCE(SUM(valor),0) as valor_adiantamento
            FROM debitos_fornecedores
            WHERE compra_id = %s AND tipo = 'inclusao'
        """, (compra_id,))
        adiantamento_row = cursor.fetchone()
        valor_adiantamento = float(adiantamento_row["valor_adiantamento"]) if adiantamento_row else 0.0

    return compra, itens, valor_adiantamento

def obter_itens_e_lancamentos_da_compra(compra_id):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT p.nome AS produto_nome,
                   i.produto_id,
                   i.quantidade,
                   i.preco_unitario,
                   (i.quantidade * i.preco_unitario) AS total
            FROM itens_compra i
            JOIN produtos p ON i.produto_id = p.id
            WHERE i.compra_id = %s
        """, (compra_id,))
        itens = cursor.fetchall()

        cursor.execute("SELECT valor_abatimento FROM compras WHERE id = %s", (compra_id,))
        compra = cursor.fetchone()

        cursor.execute("""
            SELECT COALESCE(SUM(valor),0) AS valor_adiantamento
            FROM debitos_fornecedores
            WHERE compra_id = %s AND tipo = 'inclusao'
        """, (compra_id,))
        adiantamento_row = cursor.fetchone()

    valor_abatimento = float(compra["valor_abatimento"]) if compra else 0.0
    valor_adiantamento = float(adiantamento_row["valor_adiantamento"]) if adiantamento_row else 0.0
    return itens, valor_abatimento, valor_adiantamento

def excluir_compra(compra_id):
    with get_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM debitos_fornecedores WHERE compra_id = %s", (compra_id,))
        cursor.execute("DELETE FROM itens_compra WHERE compra_id = %s", (compra_id,))
        cursor.execute("DELETE FROM compras WHERE id = %s", (compra_id,))

def obter_primeira_categoria_do_fornecedor(fornecedor_id):
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM categorias_fornecedor_por_fornecedor WHERE fornecedor_id = %s ORDER BY nome LIMIT 1", (fornecedor_id,))
        result = cursor.fetchone()
        return result['id'] if result else None

def obter_fornecedor_id_por_numero_balanca(numero):
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM fornecedores WHERE fornecedores_numerobalanca = %s", (numero,))
        resultado = cursor.fetchone()
    return resultado['id'] if resultado else None

def obter_dados_bancarios_para_campo_copiavel(compra_id):
    with get_cursor() as cursor:
        # Primeiro tenta pegar a conta personalizada (da compra)
        cursor.execute("""
            SELECT c.total, dbf.banco, dbf.agencia, dbf.conta, dbf.nome_conta, dbf.CPFouCNPJ
            FROM compras c
                LEFT JOIN dados_bancarios_fornecedor dbf ON c.dados_bancarios_id = dbf.id
            WHERE c.id = %s
        """, (compra_id,))
        row = cursor.fetchone()
        if row and row['banco']:
            valor = f"{row['total']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            tipo_doc = "CNPJ" if row['CPFouCNPJ'] and len(row['CPFouCNPJ']) > 14 else "CPF"
            texto = (
                f"{row['nome_conta'] or row['banco']} - R$ {valor}\n"
                f"{row['banco']} (Ag: {row['agencia']}, Conta: {row['conta']})\n"
                f"{tipo_doc}: {row['CPFouCNPJ']}"
            )
            return texto
        else:
            # Se não houver conta personalizada, busca a padrão do fornecedor com o mesmo formato
            cursor.execute("""
                SELECT dbf.banco, dbf.agencia, dbf.conta, dbf.nome_conta, dbf.CPFouCNPJ, c.total
                FROM compras c
                JOIN dados_bancarios_fornecedor dbf
                    ON dbf.fornecedor_id = c.fornecedor_id AND dbf.padrao = 1
                WHERE c.id = %s LIMIT 1
            """, (compra_id,))
            row = cursor.fetchone()
            if row:
                valor = f"{row['total']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                tipo_doc = "CNPJ" if row['CPFouCNPJ'] and len(row['CPFouCNPJ']) > 14 else "CPF"
                texto = (
                    f"{row['nome_conta'] or row['banco']} - R$ {valor}\n"
                    f"{row['banco']} (Ag: {row['agencia']}, Conta: {row['conta']})\n"
                    f"{tipo_doc}: {row['CPFouCNPJ']}"
                )
                return texto
    return ""

def atualizar_conta_bancaria_da_compra(compra_id, conta_id):
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "UPDATE compras SET dados_bancarios_id = %s WHERE id = %s",
            (conta_id, compra_id)
        )

def atualizar_status_compra(compra_id, novo_status):
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "UPDATE compras SET status = %s WHERE id = %s",
            (novo_status, compra_id)
        )