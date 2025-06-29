from auth_utils import hash_senha
from db_context import get_cursor

user = "admin"
senha = "Ro220199@"
nome = "Administrador"
nivel = "admin"

senha_hash = hash_senha(senha)
with get_cursor(commit=True) as cursor:
    cursor.execute("INSERT INTO usuarios (username, senha_hash, nome, nivel, ativo) VALUES (%s, %s, %s, %s, 1)",
                   (user, senha_hash, nome, nivel))
print("Usuário admin criado!")