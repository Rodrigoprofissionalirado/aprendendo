from PySide6.QtCore import QThread, Signal

class WorkerThread(QThread):
    finished = Signal(object)  # resultado do trabalho (pode ser tuple, list, dict, etc)
    erro = Signal(str)

    def __init__(self, target_func, *args, **kwargs):
        super().__init__()
        self.target_func = target_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            print("[WorkerThread] Iniciando função alvo...")
            resultado = self.target_func(*self.args, **self.kwargs)
            print("[WorkerThread] Função concluída, emitindo resultado.")
            self.finished.emit(resultado)
        except Exception as e:
            import traceback
            print("[WorkerThread] Erro na thread:")
            traceback.print_exc()
            self.erro.emit(str(e))