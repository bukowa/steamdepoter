"""Tab widgets for different views."""
import random
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QMessageBox, QDialog, QLineEdit, QLabel,
    QListWidget, QListWidgetItem, QSplitter,
    QTableView, QSizePolicy, QHeaderView, QAbstractItemView,
    QToolButton, QMenu, QPlainTextEdit, QGroupBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QThread, QAbstractTableModel, QModelIndex, QTimer
from PyQt6.QtGui import QAction, QFont, QShortcut, QKeySequence
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from sqlalchemy.orm import Session

from src.services import GameService, DepotService, ManifestService
from src.db.database import Database
from src.db import Game, Depot, Manifest, ManifestFile
from src.gui.dialogs import GameDialog, DepotDialog
from src.gui.workers import CommandWorker
from src.bins.depotdownloader import DepotDownloader
from src.errors.exceptions_handler import show_error
from src.steamdb_tasks import DepotsParsingTask, ManifestsParsingTask

from src import manifest_filters
from src.settings import settings
from src.steam_manifest_flags import DEPOT_FILE_FLAG_DIRECTORY, is_directory_entry


# Table row: path, size_bytes, manifest_id, sha (empty string if missing)
_FileTableRow = Tuple[str, int, str, str]


class _ManifestFileListLoader(QThread):
    """Background load of manifest file rows (own DB session; not UI-thread safe)."""

    loaded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, db_path: Path, manifest_ids: List[str], parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._manifest_ids = manifest_ids

    def run(self) -> None:
        if not self._manifest_ids:
            self.loaded.emit([])
            return
        try:
            from sqlalchemy import create_engine, func
            from sqlalchemy.orm import sessionmaker

            engine = create_engine(
                f"sqlite:///{self._db_path}",
                echo=False,
                connect_args={"check_same_thread": False},
            )
            Session = sessionmaker(bind=engine, expire_on_commit=False)
            session = Session()
            try:
                nondir = (func.coalesce(ManifestFile.flags, 0).op("&")(DEPOT_FILE_FLAG_DIRECTORY)) == 0
                q = (
                    session.query(
                        ManifestFile.name,
                        ManifestFile.size,
                        ManifestFile.manifest_id,
                        ManifestFile.sha,
                    )
                    .filter(ManifestFile.manifest_id.in_(self._manifest_ids), nondir)
                    .order_by(ManifestFile.name)
                )
                rows: List[_FileTableRow] = []
                for name, size, mid, sha in q.yield_per(4000):
                    if self.isInterruptionRequested():
                        return
                    sz = int(size) if size is not None else 0
                    rows.append((name, sz, str(mid), (sha or "").strip()))
                self.loaded.emit(rows)
            finally:
                session.close()
                engine.dispose()
        except Exception as e:
            self.failed.emit(str(e))


class _ManifestFileTableModel(QAbstractTableModel):
    """Lightweight read-only table: Path, Size (MB), Manifest, SHA."""

    _HEADERS = ("Path", "Size (MB)", "Manifest", "SHA")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: List[_FileTableRow] = []

    def set_rows(self, rows: List[_FileTableRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        name, size_b, mid, sha = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return name
            if col == 1:
                return self._format_mb(size_b)
            if col == 2:
                return mid
            if col == 3:
                return sha
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 1:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._HEADERS):
                return self._HEADERS[section]
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if not self._rows:
            return
        reverse = order == Qt.SortOrder.DescendingOrder

        def key(row: _FileTableRow):
            name, size_b, mid, sha = row
            if column == 0:
                return name.lower()
            if column == 1:
                return size_b
            if column == 2:
                return mid
            return sha.lower()

        self.layoutAboutToBeChanged.emit()
        self._rows.sort(key=key, reverse=reverse)
        self.layoutChanged.emit()

    @staticmethod
    def _format_mb(size_bytes: int) -> str:
        if size_bytes <= 0:
            return "0.00"
        mb = size_bytes / (1024 * 1024)
        return f"{mb:.2f}"


class LibraryTab(QWidget):
    """Unified Library Tab displaying Games, Depots, Manifests, and Files."""
    
    data_changed = pyqtSignal()
    open_steamdb = pyqtSignal(str)
    open_steamdb_depot = pyqtSignal(str)
    parse_depots_steamdb = pyqtSignal(str)
    scrape_manifests_steamdb = pyqtSignal(list)

    def __init__(self, session: Session, console=None, db: Database = None):
        super().__init__()
        self.session = session
        self.console = console
        self.db = db
        self._file_list_generation = 0
        self._file_loader: Optional[_ManifestFileListLoader] = None
        self._cached_file_rows: List[_FileTableRow] = []
        self.init_ui()

    def init_ui(self) -> None:
        layout = QVBoxLayout()

        # Toolbar
        toolbar = QHBoxLayout()
        add_game_btn = self._make_button("Add Game", self.on_add_game)
        add_depot_btn = self._make_button("Add Depot", self.on_add_depot)
        del_btn = self._make_button("Delete Selected", self.on_delete)
        ref_btn = self._make_button("Refresh", self._manual_refresh)

        toolbar.addWidget(add_game_btn)
        toolbar.addWidget(add_depot_btn)
        toolbar.addWidget(del_btn)
        toolbar.addWidget(ref_btn)
        toolbar.addStretch()

        from src.gui.components import EntityTreeWidget

        self.tree_view = EntityTreeWidget(self.session)

        # Connect signals
        self.tree_view.open_steamdb_requested.connect(self.open_steamdb.emit)
        self.tree_view.open_steamdb_depot_requested.connect(self.open_steamdb_depot.emit)
        self.tree_view.parse_depots_requested.connect(self.parse_depots_steamdb.emit)
        self.tree_view.scrape_manifests_requested.connect(self.scrape_manifests_steamdb.emit)
        self.tree_view.download_manifest_requested.connect(self.on_download_manifests)

        self.tree_view.itemSelectionChanged.connect(self._on_tree_selection_changed)

        # Left: toolbar + tree; right: manifest file table (virtualized via QTableView)
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.addLayout(toolbar)
        left_l.addWidget(self.tree_view)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)
        self._file_pane_title = QLabel("Files")
        self._file_pane_status = QLabel("Select a game, depot, or manifest in the tree.")
        self._file_pane_status.setWordWrap(True)

        self._file_pane_options_btn = QToolButton()
        self._file_pane_options_btn.setText("Options")
        self._file_pane_options_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._file_pane_options_menu = QMenu(self._file_pane_options_btn)
        self._act_filter_non_binary = QAction("Hide paths matching patterns below", self)
        self._act_filter_non_binary.setCheckable(True)
        self._act_filter_non_binary.setChecked(True)
        self._act_filter_non_binary.toggled.connect(self._on_hide_patterns_filter_toggled)
        self._file_pane_options_menu.addAction(self._act_filter_non_binary)
        self._act_restore_suffix_defaults = QAction("Restore bundled default patterns", self)
        self._act_restore_suffix_defaults.triggered.connect(self._on_restore_default_hide_patterns)
        self._file_pane_options_menu.addAction(self._act_restore_suffix_defaults)
        self._file_pane_options_btn.setMenu(self._file_pane_options_menu)

        file_pane_header = QHBoxLayout()
        file_pane_header.setContentsMargins(0, 0, 0, 0)
        file_pane_header.addWidget(self._file_pane_title)
        file_pane_header.addStretch()
        file_pane_header.addWidget(self._file_pane_options_btn)

        self._file_table_model = _ManifestFileTableModel(self)
        self._file_table_view = QTableView()
        self._file_table_view.setModel(self._file_table_model)
        self._file_table_view.setAlternatingRowColors(True)
        self._file_table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._file_table_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._file_table_view.setSortingEnabled(True)
        self._file_table_view.setShowGrid(False)
        self._file_table_view.verticalHeader().setVisible(False)
        self._file_table_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._file_table_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        hh = self._file_table_view.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setMinimumSectionSize(64)

        ext_group = QGroupBox(
            "Hide patterns — Unix globs (pathlib), one per line; "
            "prefix re: for regex. Preview refreshes shortly after you stop typing; Ctrl+S saves to data/settings.json. # comments"
        )
        ext_gl = QVBoxLayout(ext_group)
        self._ext_plain = QPlainTextEdit()
        self._ext_plain.setPlaceholderText(
            "e.g. **/*.lua\n**/Content/Localization/**\nre:.*\\.txt$"
        )
        mono = QFont("Consolas")
        if not mono.exactMatch():
            mono = QFont("monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._ext_plain.setFont(mono)
        self._ext_plain.setMinimumHeight(120)
        self._ext_plain.setTabStopDistance(self._ext_plain.fontMetrics().horizontalAdvance(" ") * 4)
        self._hide_patterns_debounce = QTimer(self)
        self._hide_patterns_debounce.setSingleShot(True)
        self._hide_patterns_debounce.setInterval(300)
        self._hide_patterns_debounce.timeout.connect(self._flush_hide_patterns_editor_to_filter)
        self._ext_plain.textChanged.connect(self._on_hide_patterns_text_changed)
        ext_gl.addWidget(self._ext_plain)
        self._pattern_save_notice = QLabel("")
        self._pattern_save_notice.setStyleSheet("color: palette(mid);")
        ext_gl.addWidget(self._pattern_save_notice)

        self._sc_save_patterns = QShortcut(QKeySequence.StandardKey.Save, self._ext_plain)
        self._sc_save_patterns.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sc_save_patterns.activated.connect(self._save_library_hide_patterns)

        file_body_split = QSplitter(Qt.Orientation.Vertical)
        file_body_split.addWidget(self._file_table_view)
        file_body_split.addWidget(ext_group)
        file_body_split.setStretchFactor(0, 5)
        file_body_split.setStretchFactor(1, 1)
        file_body_split.setSizes([480, 160])
        right_l.addLayout(file_pane_header)
        right_l.addWidget(self._file_pane_status)
        right_l.addWidget(file_body_split, stretch=1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)
        self.setLayout(layout)

        self._sync_hide_pattern_ui()
        self.refresh_data()

    @staticmethod
    def _make_button(label: str, callback) -> QPushButton:
        btn = QPushButton(label)
        btn.clicked.connect(callback)
        return btn

    def refresh_data(self) -> None:
        self.tree_view.load_games()
        self._cancel_file_loader()
        self._set_file_pane_cache([], update_counts_in_status=False)
        self._file_pane_status.setText("Select a game, depot, or manifest in the tree.")

    def _sync_hide_pattern_ui(self) -> None:
        self._hide_patterns_debounce.stop()
        if not manifest_filters.get_patterns_text().strip():
            manifest_filters.init_from_app_settings(settings)
        self._ext_plain.blockSignals(True)
        self._ext_plain.setPlainText(manifest_filters.get_patterns_text())
        self._ext_plain.blockSignals(False)
        self._act_filter_non_binary.setChecked(manifest_filters.is_hide_filter_enabled())

    def _sync_manifest_filters_from_editor(self) -> None:
        """Keep ``manifest_filters`` in sync with the pattern editor (cheap parse)."""
        manifest_filters.set_patterns_from_text(self._ext_plain.toPlainText())

    def _flush_hide_patterns_editor_to_filter(self) -> None:
        """Apply editor patterns to the file table (after debounce)."""
        self._sync_manifest_filters_from_editor()
        self._apply_file_pane_filter(update_counts_in_status=True)

    def _on_hide_patterns_filter_toggled(self, checked: bool) -> None:
        self._hide_patterns_debounce.stop()
        self._sync_manifest_filters_from_editor()
        settings.set_global("library_hide_patterns_enabled", checked)
        manifest_filters.set_hide_filter_enabled(checked)
        self._apply_file_pane_filter(update_counts_in_status=True)

    def _on_hide_patterns_text_changed(self) -> None:
        text = self._ext_plain.toPlainText()
        dirty = manifest_filters.patterns_text_is_dirty(text)
        if dirty:
            self._pattern_save_notice.setText("Unsaved changes — press Ctrl+S to write data/settings.json")
        else:
            self._pattern_save_notice.setText("")
        self._hide_patterns_debounce.start()

    def _save_library_hide_patterns(self) -> None:
        self._hide_patterns_debounce.stop()
        text = self._ext_plain.toPlainText()
        manifest_filters.persist_patterns_to_disk(settings, text)
        manifest_filters.set_patterns_from_text(text)
        self._apply_file_pane_filter(update_counts_in_status=True)
        self._pattern_save_notice.setText("Saved to data/settings.json")
        QTimer.singleShot(3500, lambda: self._pattern_save_notice.setText(""))

    def _on_restore_default_hide_patterns(self) -> None:
        self._hide_patterns_debounce.stop()
        doc = manifest_filters.default_patterns_document()
        self._ext_plain.blockSignals(True)
        self._ext_plain.setPlainText(doc)
        self._ext_plain.blockSignals(False)
        manifest_filters.set_patterns_from_text(doc)
        manifest_filters.persist_patterns_to_disk(settings, doc)
        self._apply_file_pane_filter(update_counts_in_status=True)
        self._pattern_save_notice.setText("Restored defaults and saved.")
        QTimer.singleShot(3500, lambda: self._pattern_save_notice.setText(""))

    def _set_file_pane_cache(
        self, rows: List[_FileTableRow], *, update_counts_in_status: bool = True
    ) -> None:
        self._hide_patterns_debounce.stop()
        self._sync_manifest_filters_from_editor()
        self._cached_file_rows = list(rows)
        self._apply_file_pane_filter(update_counts_in_status=update_counts_in_status)

    def _apply_file_pane_filter(self, *, update_counts_in_status: bool = True) -> None:
        full = self._cached_file_rows
        if manifest_filters.is_hide_filter_enabled():
            visible = [r for r in full if not manifest_filters.should_hide_non_binary_path(r[0])]
        else:
            visible = list(full)
        self._file_table_model.set_rows(visible)
        if not update_counts_in_status or not full:
            return
        n_full = len(full)
        n_vis = len(visible)
        if manifest_filters.is_hide_filter_enabled() and n_vis != n_full:
            self._file_pane_status.setText(f"{n_vis:,} file(s) shown · {n_full:,} total")
        else:
            self._file_pane_status.setText(f"{n_vis:,} file(s).")

    def _cancel_file_loader(self) -> None:
        if self._file_loader is not None:
            self._file_loader.requestInterruption()
            self._file_loader = None

    def _manifest_ids_for_app_ids(self, app_ids: List[str]) -> List[str]:
        """All manifest IDs for depots belonging to the given game app_id strings."""
        if not app_ids:
            return []
        rows = (
            self.session.query(Manifest.manifest_id)
            .join(Depot, Manifest.depot_id == Depot.depot_id)
            .filter(Depot.app_id.in_(app_ids))
            .all()
        )
        return sorted({str(r[0]) for r in rows})

    def _manifest_ids_for_depot_ids(self, depot_ids: List[str]) -> List[str]:
        """All manifest IDs belonging to the given depot_id strings (main-thread session)."""
        if not depot_ids:
            return []
        rows = (
            self.session.query(Manifest.manifest_id)
            .filter(Manifest.depot_id.in_(depot_ids))
            .all()
        )
        return sorted({str(r[0]) for r in rows})

    def _on_tree_selection_changed(self) -> None:
        selected = self.tree_view.get_selected_items()
        manifests = [x for x in selected if isinstance(x, Manifest)]
        depots = [x for x in selected if isinstance(x, Depot)]
        games = [x for x in selected if isinstance(x, Game)]
        files_only = [x for x in selected if isinstance(x, ManifestFile)]

        if manifests:
            ids = sorted({str(m.manifest_id) for m in manifests})
            self._file_pane_title.setText(
                "Files" if len(ids) == 1 else f"Files ({len(ids)} manifests)"
            )
            self._file_pane_status.setText("Loading…")
            self._set_file_pane_cache([], update_counts_in_status=False)
            self._start_file_loader(ids)
            return

        if depots:
            depot_ids = sorted({str(d.depot_id) for d in depots})
            manifest_ids = self._manifest_ids_for_depot_ids(depot_ids)
            self._cancel_file_loader()
            if not manifest_ids:
                self._file_pane_title.setText(
                    "Files" if len(depot_ids) == 1 else f"Files ({len(depot_ids)} depots)"
                )
                self._file_pane_status.setText("No manifests for this depot yet.")
                self._set_file_pane_cache([], update_counts_in_status=False)
                return
            self._file_pane_title.setText(
                "Files (depot)" if len(depot_ids) == 1 else f"Files ({len(depot_ids)} depots)"
            )
            self._file_pane_status.setText("Loading…")
            self._set_file_pane_cache([], update_counts_in_status=False)
            self._start_file_loader(manifest_ids)
            return

        if games:
            app_ids = sorted({str(g.app_id) for g in games})
            manifest_ids = self._manifest_ids_for_app_ids(app_ids)
            self._cancel_file_loader()
            if not manifest_ids:
                self._file_pane_title.setText(
                    "Files" if len(app_ids) == 1 else f"Files ({len(app_ids)} games)"
                )
                self._file_pane_status.setText("No manifests under this game yet.")
                self._set_file_pane_cache([], update_counts_in_status=False)
                return
            self._file_pane_title.setText(
                "Files (game)" if len(app_ids) == 1 else f"Files ({len(app_ids)} games)"
            )
            self._file_pane_status.setText("Loading…")
            self._set_file_pane_cache([], update_counts_in_status=False)
            self._start_file_loader(manifest_ids)
            return

        self._cancel_file_loader()

        if files_only and not manifests:
            rows: List[_FileTableRow] = []
            for f in sorted(files_only, key=lambda x: x.name):
                if is_directory_entry(f.flags):
                    continue
                sz = int(f.size) if f.size is not None else 0
                rows.append((f.name, sz, str(f.manifest_id), (f.sha or "").strip()))
            self._file_pane_title.setText("Files (selection)")
            self._set_file_pane_cache(rows, update_counts_in_status=True)
            return

        self._file_pane_title.setText("Files")
        self._file_pane_status.setText("Select a game, depot, or manifest in the tree.")
        self._set_file_pane_cache([], update_counts_in_status=False)

    def _start_file_loader(self, manifest_ids: List[str]) -> None:
        self._cancel_file_loader()
        if not self.db:
            self._file_pane_status.setText("Database handle missing; cannot load file list.")
            return

        self._file_list_generation += 1
        gen = self._file_list_generation

        loader = _ManifestFileListLoader(Path(self.db.db_path), manifest_ids, self)
        self._file_loader = loader

        def on_loaded(rows: list) -> None:
            if gen != self._file_list_generation:
                return
            self._file_loader = None
            self._set_file_pane_cache(rows, update_counts_in_status=True)

        def on_failed(msg: str) -> None:
            if gen != self._file_list_generation:
                return
            self._file_loader = None
            self._set_file_pane_cache([], update_counts_in_status=False)
            self._file_pane_status.setText(f"Load failed: {msg}")

        loader.loaded.connect(on_loaded)
        loader.failed.connect(on_failed)
        loader.start()

    def _manual_refresh(self) -> None:
        self.session.expire_all()
        self.refresh_data()

    def on_add_game(self) -> None:
        dialog = GameDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                service = GameService(self.session)
                service.create_game(props=data)
                self.data_changed.emit()
                self._manual_refresh()
                QMessageBox.information(self, "Success", f"Game '{data['name']}' added successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Add Game")

    def on_add_depot(self) -> None:
        try:
            game_service = GameService(self.session)
            games = game_service.get_all_games()
        except Exception as e:
            show_error(self, e, "Failed to Load Games")
            return

        app_ids = [game.app_id for game in games]

        if not app_ids:
            show_error(self, Exception("No games exist. Please add a game first!"))
            return

        dialog = DepotDialog(self, app_ids=app_ids)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            try:
                service = DepotService(self.session)
                service.create_depot(props=data)
                self.data_changed.emit()
                self._manual_refresh()
                QMessageBox.information(self, "Success", f"Depot '{data['name']}' added successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Add Depot")

    def on_delete(self) -> None:
        selected_data = self.tree_view.get_selected_items()
        if not selected_data:
            show_error(self, Exception("Please select items to delete."))
            return

        games = [item for item in selected_data if isinstance(item, Game)]
        depots = [item for item in selected_data if isinstance(item, Depot)]
        manifests = [item for item in selected_data if isinstance(item, Manifest)]

        # Capture IDs and relationships BEFORE any deletion (which commits and expires objects)
        game_ids = [g.id for g in games]
        game_app_ids = {g.app_id for g in games}
        depot_ids = [d.id for d in depots if d.app_id not in game_app_ids]
        manifest_ids = [m.id for m in manifests]
        
        msg_parts = []
        if games: msg_parts.append(f"{len(games)} game(s)")
        if depots: msg_parts.append(f"{len(depots)} depot(s)")
        if manifests: msg_parts.append(f"{len(manifests)} manifest(s)")
        
        if not msg_parts:
            return

        msg = "Delete " + " and ".join(msg_parts) + "?"
        if games:
            msg += "\nWarning: Deleting a game will delete all its depots and manifests!"

        response = QMessageBox.question(
            self,
            "Confirm Delete",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if response == QMessageBox.StandardButton.Yes:
            try:
                if game_ids:
                    GameService(self.session).delete_games(game_ids)
                if depot_ids:
                    DepotService(self.session).delete_depots(depot_ids)
                if manifest_ids:
                    ManifestService(self.session).delete_manifests(manifest_ids)
                
                self.data_changed.emit()
                self._manual_refresh()
                QMessageBox.information(self, "Success", "Items deleted successfully!")
            except Exception as e:
                show_error(self, e, "Failed to Delete Items")

    def on_download_manifests(self, manifests: list) -> None:
        if not self.console:
            return

        downloader = DepotDownloader()
        
        targets_by_app = {}
        for m in manifests:
            depot = self.session.query(Depot).filter(Depot.depot_id == m.depot_id).first()
            if not depot:
                show_error(self, Exception(f"Could not find depot for manifest {m.manifest_id}"))
                continue
            
            app_id = int(depot.app_id)
            if app_id not in targets_by_app:
                targets_by_app[app_id] = []
            
            targets_by_app[app_id].append(m)

        for app_id, app_manifests in targets_by_app.items():
            targets = [(int(m.depot_id), int(m.manifest_id)) for m in app_manifests]
            
            def handle_incremental_update(manifest_id, status, parsed_manifest):
                if self.db:
                    new_session = self.db.get_session()
                    try:
                        service = ManifestService(new_session)
                        manifest_id_str = str(manifest_id)
                        
                        if parsed_manifest:
                            # This now handles status, metadata, and files
                            service.save_downloaded_manifest_files(manifest_id_str, parsed_manifest)
                        else:
                            service.update_manifest_status(manifest_id_str, status)
                        
                        self.data_changed.emit()
                    except Exception as e:
                        print(f"Failed to process incremental manifest {manifest_id}: {e}")
                    finally:
                        new_session.close()

            worker = CommandWorker(
                downloader.get_manifest_data, 
                app_id=app_id, 
                targets=targets,
                on_manifest_complete=handle_incremental_update
            )
            worker.on_cancel = downloader.runner.stop
            # Final on_finished can be simpler now, or just emit one last refresh
            worker.finished.connect(lambda _: self.data_changed.emit())
            
            self.console.add_command(worker, f"Fetch File List for {len(targets)} Manifest(s) (App {app_id})")


class BrowserTab(QWidget):
    """Browser tab for Steam and SteamDB with a sidebar for parsing tasks."""

    data_changed = pyqtSignal()
    task_queue_finished = pyqtSignal()

    def __init__(self, session: Session, console=None, db: Database = None):
        super().__init__()
        self.session = session
        self.console = console
        self.db = db
        self.current_app_id = None
        self.cancel_requested = False
        self.tasks = [
            DepotsParsingTask,
            ManifestsParsingTask,
        ]
        self.init_ui()

    def init_ui(self):
        import os
        layout = QVBoxLayout()

        # URL bar
        url_layout = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Enter URL or App ID...")
        self.url_edit.returnPressed.connect(self.load_url)
        url_layout.addWidget(QLabel("URL:"))
        url_layout.addWidget(self.url_edit)

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self.load_url)
        url_layout.addWidget(load_btn)

        steam_btn = QPushButton("Steam Login")
        steam_btn.clicked.connect(self.load_steam)
        url_layout.addWidget(steam_btn)

        layout.addLayout(url_layout)

        # Main splitter for Sidebar and Browser
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sidebar for Tasks
        self.sidebar = QWidget()
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.addWidget(QLabel("<b>SteamDB Tasks</b>"))
        
        self.task_list = QListWidget()
        for task_cls in self.tasks:
            item = QListWidgetItem(task_cls.name)
            item.setToolTip(task_cls.description)
            item.setData(Qt.ItemDataRole.UserRole, task_cls)
            self.task_list.addItem(item)
        
        self.task_list.itemDoubleClicked.connect(self.run_selected_task)
        sidebar_layout.addWidget(self.task_list)

        run_task_btn = QPushButton("Run Task")
        run_task_btn.clicked.connect(self.run_selected_task)
        sidebar_layout.addWidget(run_task_btn)

        cancel_task_btn = QPushButton("Cancel Running Tasks")
        cancel_task_btn.clicked.connect(self.cancel_tasks)
        sidebar_layout.addWidget(cancel_task_btn)
        
        sidebar_layout.addStretch()

        # Web view
        storage_path = os.path.abspath(os.path.join("data", "browser_storage"))
        os.makedirs(storage_path, exist_ok=True)

        self.profile = QWebEngineProfile("SteamDepoter", self)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.setPersistentStoragePath(storage_path)
        self.profile.setCachePath(os.path.join(storage_path, "cache"))
        self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        
        self.web_view = QWebEngineView()
        self.web_page = QWebEnginePage(self.profile, self.web_view)
        self.web_view.setPage(self.web_page)
        self.web_view.urlChanged.connect(self._on_url_changed)
        
        # Add components to splitter
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.web_view)
        self.splitter.setStretchFactor(1, 4)  # Browser takes more space

        layout.addWidget(self.splitter)
        self.setLayout(layout)

    # ── Navigation ────────────────────────────────────────────────

    def _on_url_changed(self, url: QUrl):
        """Update the URL bar when the browser navigates."""
        self.url_edit.setText(url.toString())

    def set_app_id(self, app_id: str):
        """Programmatically navigate to a specific App ID's depots page."""
        self.current_app_id = app_id
        url = f"https://steamdb.info/app/{app_id}/depots/"
        self.url_edit.setText(url)
        self.web_view.load(QUrl(url))

    def set_depot_id(self, depot_id: str):
        """Programmatically navigate to a specific Depot ID's page."""
        url = f"https://steamdb.info/depot/{depot_id}/"
        self.url_edit.setText(url)
        self.web_view.load(QUrl(url))

    def load_url(self):
        url = self.url_edit.text().strip()
        if not url:
            return
            
        if url.isdigit():
            self.set_app_id(url)
            return

        if not url.startswith("http"):
            url = "https://" + url
        self.web_view.load(QUrl(url))

    def load_steam(self):
        self.web_view.load(QUrl("https://store.steampowered.com/login/"))

    # ── Task execution ────────────────────────────────────────────

    def _log(self, title: str, text: str, finished: bool = False):
        if self.console:
            self.console.log_message(title, text, cancel_callback=self.cancel_tasks, finished=finished)

    def cancel_tasks(self):
        self.cancel_requested = True
        if self.console:
            self.console.log_message("System", "Cancellation requested. Tasks will stop before processing the next item.")

    def _resolve_target_id(self, task_cls, target_id=None):
        """Determine target_id from the current URL if not provided."""
        import re
        if target_id:
            return target_id

        url = self.web_view.url().toString()
        pattern = rf"/{task_cls.target_type}/(\d+)"
        match = re.search(pattern, url)
        return match.group(1) if match else None

    def _show_retry_dialog(self, result, cancel_label="Cancel"):
        """Show a retry dialog for Cloudflare/rate-limit errors. Returns True if user wants to continue."""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)

        if result == "RATE_LIMITED":
            msg_box.setWindowTitle("Rate Limited")
            msg_box.setText("You have been temporarily rate limited by SteamDB.")
            msg_box.setInformativeText("It is highly recommended to stop for at least an hour to avoid a permanent ban. Continue at your own risk.")
        else:
            msg_box.setWindowTitle("Action Required")
            msg_box.setText("The page failed to load or parse correctly (likely Cloudflare or a block).")
            msg_box.setInformativeText("Please check the browser tab, solve any challenges, and click 'Continue' to retry.")

        continue_btn = msg_box.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)
        msg_box.addButton(cancel_label, QMessageBox.ButtonRole.RejectRole)

        msg_box.exec()
        return msg_box.clickedButton() == continue_btn

    def run_selected_task(self):
        item = self.task_list.currentItem()
        if not item:
            show_error(self, Exception("Please select a task from the sidebar."))
            return

        task_cls = item.data(Qt.ItemDataRole.UserRole)
        self.run_task(task_cls)

    def run_task(self, task_cls, target_id=None):
        """Run a single task, determining target_id from the URL if not provided."""
        target_id = self._resolve_target_id(task_cls, target_id)
        if not target_id:
            show_error(self, Exception(f"Could not determine {task_cls.target_type.upper()} ID from URL or arguments."))
            return

        task = task_cls(self.web_page, str(target_id))
        log_title = f"{task_cls.name} Task"

        def on_finished(result):
            if result in ("RETRY_REQUIRED", "RATE_LIMITED", None):
                if self._show_retry_dialog(result):
                    self._log(log_title, f"Retrying {target_id}...")
                    self.run_task(task_cls, target_id)
                else:
                    self._log(log_title, "Task cancelled by user.", finished=True)
                return

            try:
                msg = task.save_result(self.session, result)
                self.data_changed.emit()
                self.task_queue_finished.emit()
                QMessageBox.information(self, "Success", msg)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to process task result: {str(e)}")

        task.run(on_finished)

    def run_task_queue(self, task_cls, target_ids: list):
        """Run a task on a list of targets sequentially with delays to avoid rate limiting."""
        from PyQt6.QtCore import QTimer

        if not target_ids:
            return

        log_title = f"{task_cls.name} Queue"

        def process_next():
            if self.cancel_requested:
                self._log(log_title, "Queue cancelled by user.", finished=True)
                self.cancel_requested = False
                self.task_queue_finished.emit()
                return

            if not target_ids:
                self._log(log_title, "Queue finished processing all targets.", finished=True)
                self.task_queue_finished.emit()
                QMessageBox.information(self, "Queue Finished", f"Finished processing all targets for {task_cls.name}")
                return

            target_id = target_ids.pop(0)
            self._log(log_title, f"Started processing target ID: {target_id}...")

            task = task_cls(self.web_page, str(target_id))

            def on_finished(result):
                if result in ("RETRY_REQUIRED", "RATE_LIMITED", None):
                    if self._show_retry_dialog(result, cancel_label="Stop Queue"):
                        self._log(log_title, f"Retrying {target_id}...")
                        target_ids.insert(0, target_id)
                        QTimer.singleShot(1000, process_next)
                    else:
                        self._log(log_title, "Queue cancelled by user.", finished=True)
                    return

                try:
                    msg = task.save_result(self.session, result)

                    # Mark depot as parsed if this is a manifests-parsing task
                    if task_cls == ManifestsParsingTask:
                        DepotService(self.session).mark_manifests_parsed(str(target_id))

                    self.data_changed.emit()
                    self._log(log_title, f"Success for {target_id}: {msg}")
                except Exception as e:
                    self._log(log_title, f"Error for {target_id}: {e}")

                if target_ids:
                    delay = random.randint(7000, 15000)
                    self._log(log_title, f"Waiting {delay/1000:.1f} seconds before next target...")
                    QTimer.singleShot(delay, process_next)
                else:
                    process_next()

            task.run(on_finished)

        # Start the queue immediately
        self._log(log_title, f"Initializing queue with {len(target_ids)} targets. First task will start immediately.")
        process_next()

    def refresh_data(self):
        pass


