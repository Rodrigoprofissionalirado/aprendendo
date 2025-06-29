import bcrypt

def hash_senha(senha):
    """Gera um hash seguro para a senha."""
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()

def checar_senha(senha, hash_armazenado):
    """Verifica se a senha corresponde ao hash armazenado."""
    return bcrypt.checkpw(senha.encode(), hash_armazenado.encode())