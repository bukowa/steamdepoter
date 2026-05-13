"""Background workers for long-running tasks."""
from typing import List, Optional, Callable, Any
from PyQt6.QtCore import QThread, pyqtSignal

from src.bins.runner import BinOutput


class CommandWorker(QThread):
    """
    A worker thread that executes a command using a runner.
    """
    output_received = pyqtSignal(str)
    finished = pyqtSignal(object)  # BinOutput
    error = pyqtSignal(str)

    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._is_cancelled = False
        self.on_cancel: Optional[Callable] = None
        # Inject our signal as the on_output callback
        self.kwargs['on_output'] = self._handle_output
        # Also inject a cancellation check if the function supports it
        self.kwargs['is_cancelled'] = self.is_cancelled

    def is_cancelled(self) -> bool:
        return self._is_cancelled

    def stop(self):
        self._is_cancelled = True
        if self.on_cancel:
            self.on_cancel()

    def _handle_output(self, char: str):
        self.output_received.emit(char)

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            if self._is_cancelled:
                return
            self.error.emit(str(e))
