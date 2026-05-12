"""Console panel for displaying command outputs."""
from datetime import datetime
from typing import Dict, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, 
    QPlainTextEdit, QLabel, QSplitter
)
from PyQt6.QtCore import Qt

from src.gui.workers import CommandWorker


class ConsoleItem(QListWidgetItem):
    """Represents a command in the console list."""
    def __init__(self, title: str, worker: CommandWorker = None):
        timestamp = datetime.now().strftime("%H:%M:%S")
        super().__init__(f"[{timestamp}] {title}")
        self.title = title
        self.worker = worker
        self.output = ""
        self.status = "running" # running, success, error
        self._update_icon()

    def append_output(self, text: str):
        self.output += text

    def set_status(self, status: str):
        self.status = status
        self._update_icon()

    def _update_icon(self):
        if self.status == "running":
            self.setText(f"🟡 {self.text().split(' ', 1)[-1]}")
        elif self.status == "success":
            self.setText(f"✅ {self.text().split(' ', 1)[-1]}")
        elif self.status == "error":
            self.setText(f"❌ {self.text().split(' ', 1)[-1]}")


class ConsolePanel(QWidget):
    """
    A panel that displays a list of running/finished commands and their logs.
    """
    def __init__(self):
        super().__init__()
        self.items: List[ConsoleItem] = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: List of commands
        self.list_widget = QListWidget()
        self.list_widget.setFixedWidth(250)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_changed)
        
        # Right: Log viewer
        self.log_viewer = QPlainTextEdit()
        self.log_viewer.setReadOnly(True)
        self.log_viewer.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace;")

        splitter.addWidget(self.list_widget)
        splitter.addWidget(self.log_viewer)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

    def add_command(self, worker: CommandWorker, title: str):
        """Adds a new command to track."""
        item = ConsoleItem(title, worker)
        self.items.append(item)
        self.list_widget.addItem(item)
        self.list_widget.setCurrentItem(item)

        worker.output_received.connect(lambda text: self._on_output(item, text))
        worker.finished.connect(lambda result: self._on_finished(item, result))
        worker.error.connect(lambda err: self._on_error(item, err))
        
        worker.start()

    def _on_output(self, item: ConsoleItem, text: str):
        item.append_output(text)
        if self.list_widget.currentItem() == item:
            self.log_viewer.moveCursor(self.log_viewer.textCursor().MoveOperation.End)
            self.log_viewer.insertPlainText(text)

    def _on_finished(self, item: ConsoleItem, result):
        item.set_status("success")
        if self.list_widget.currentItem() == item:
            self.log_viewer.appendPlainText(f"\n--- Process finished with exit code {result.exit_code} ---")

    def _on_error(self, item: ConsoleItem, error_msg: str):
        item.set_status("error")
        item.append_output(f"\nERROR: {error_msg}")
        if self.list_widget.currentItem() == item:
            self.log_viewer.appendPlainText(f"\nERROR: {error_msg}")

    def _on_selection_changed(self):
        selected = self.list_widget.currentItem()
        if isinstance(selected, ConsoleItem):
            self.log_viewer.setPlainText(selected.output)
            self.log_viewer.moveCursor(self.log_viewer.textCursor().MoveOperation.End)

    def log_message(self, title: str, text: str):
        """Log a generic message to a specific titled console item."""
        target_item = None
        for item in self.items:
            if getattr(item, 'is_generic_log', False) and item.title == title:
                target_item = item
                break
        
        if not target_item:
            target_item = ConsoleItem(title, None)
            target_item.is_generic_log = True
            target_item.set_status("success") # default state for log
            self.items.append(target_item)
            self.list_widget.addItem(target_item)
        
        # Don't steal focus unless it's the current item or first message
        if len(target_item.output) == 0:
            self.list_widget.setCurrentItem(target_item)

        timestamp = datetime.now().strftime("%H:%M:%S")
        self._on_output(target_item, f"[{timestamp}] {text}\n")
