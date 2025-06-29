from PySide6.QtWidgets import QMessageBox

def requer_permissao(niveis):
    """
    Decorador para exigir que o usuário logado tenha um dos níveis permitidos.
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            if not hasattr(self, 'usuario_logado') or self.usuario_logado is None:
                QMessageBox.warning(self, "Acesso negado", "Usuário não autenticado.")
                return
            if self.usuario_logado['nivel'] not in niveis:
                QMessageBox.warning(self, "Acesso negado", "Você não tem permissão para esta ação.")
                return
            return func(self, *args, **kwargs)
        return wrapper
    return decorator