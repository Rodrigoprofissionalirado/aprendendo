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
            resultado = self.target_func(*self.args, **self.kwargs)
            self.finished.emit(resultado)
        except Exception as e:
            self.erro.emit(str(e))