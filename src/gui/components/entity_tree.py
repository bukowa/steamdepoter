"""Unified entity tree widget for Games -> Depots -> Manifests -> Files."""
from typing import Optional

from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QMenu, QMessageBox, QAbstractItemView
from PyQt6.QtCore import Qt, pyqtSignal

from src.db.schema import Game, Depot, Manifest, ManifestFile
from src.services import ManifestService


class EntityTreeWidget(QTreeWidget):
    """A unified tree widget for displaying Games -> Depots -> Manifests -> Files."""

    # Custom signals for actions
    open_steamdb_requested = pyqtSignal(str)          # app_id
    open_steamdb_depot_requested = pyqtSignal(str)    # depot_id
    parse_depots_requested = pyqtSignal(str)          # app_id
    scrape_manifests_requested = pyqtSignal(list)     # [depot_ids]
    download_manifest_requested = pyqtSignal(list)    # [manifests]
    data_changed = pyqtSignal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.customContextMenuRequested.connect(self._on_context_menu)
        self.itemExpanded.connect(self._on_item_expanded)

        self.setHeaderLabels(["Item", "Details", "Language", "Status"])

    # ── Data loading ──────────────────────────────────────────────

    def load_games(self):
        """Load all root game items."""
        tree_state = self._get_tree_state()
        self.clear()

        try:
            games = self.session.query(Game).all()
            for game in games:
                self._add_game_node(game, self)

            self.setColumnWidth(0, 450)
            self.setColumnWidth(1, 150)
            self.setColumnWidth(2, 120)
            self.setColumnWidth(3, 100)

            self._restore_tree_state(tree_state)

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load games: {e}")

    # ── Node builders ─────────────────────────────────────────────

    def _add_game_node(self, game: Game, parent):
        item = QTreeWidgetItem(parent)
        item.setText(0, f"📁 {game.app_id} - {game.name}")
        item.setData(0, Qt.ItemDataRole.UserRole, game)
        self._add_dummy(item)
        return item

    def _add_depot_node(self, depot: Depot, parent):
        item = QTreeWidgetItem(parent)
        item.setText(0, f"📦 {depot.depot_id} - {depot.name}")
        item.setText(1, depot.os or "")
        item.setText(2, depot.language or "")
        
        status = "Scraped" if depot.steamdb_manifests_parsed else "New"
        item.setText(3, status)
        
        item.setData(0, Qt.ItemDataRole.UserRole, depot)
        self._add_dummy(item)
        return item

    def _add_manifest_node(self, manifest: Manifest, parent):
        item = QTreeWidgetItem(parent)
        item.setText(0, f"📄 {manifest.manifest_id}")
        item.setText(1, str(manifest.date_str or ""))
        
        # Determine status text
        status_map = {
            0: "Pending",
            1: "Success",
            2: "401 Unauthorized",
            3: "Error"
        }
        
        status_val = manifest.parsed_status if manifest.parsed_status is not None else 0
        status_text = status_map.get(status_val, f"Unknown ({status_val})")
        item.setText(3, status_text)
        
        # Color code the status
        if status_val == 1:
            item.setForeground(3, Qt.GlobalColor.green)
        elif status_val == 2:
            item.setForeground(3, Qt.GlobalColor.red)
        elif status_val == 3:
            item.setForeground(3, Qt.GlobalColor.darkRed)
        
        item.setData(0, Qt.ItemDataRole.UserRole, manifest)
        self._add_dummy(item)
        return item

    def _add_file_node(self, file: ManifestFile, parent):
        item = QTreeWidgetItem(parent)
        item.setText(0, f"📄 {file.name}")
        item.setText(1, self._format_size(file.size))
        item.setData(0, Qt.ItemDataRole.UserRole, file)
        return item

    def _add_dummy(self, parent_item):
        dummy = QTreeWidgetItem(parent_item)
        dummy.setText(0, "Loading...")
        dummy.setData(0, Qt.ItemDataRole.UserRole, "dummy")

    # ── Lazy loading on expand ────────────────────────────────────

    def _on_item_expanded(self, item: QTreeWidgetItem):
        """Load children when a node is expanded for the first time."""
        if not self._has_dummy(item):
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        # Remove the dummy placeholder
        item.removeChild(item.child(0))

        try:
            self._load_children(data, item)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load children: {e}")

    def _has_dummy(self, item: QTreeWidgetItem) -> bool:
        """Check if item only has the dummy placeholder child."""
        return item.childCount() == 1 and item.child(0).data(0, Qt.ItemDataRole.UserRole) == "dummy"

    def _load_children(self, parent_data, parent_item: QTreeWidgetItem):
        """Query and add child nodes based on parent type."""
        if isinstance(parent_data, Game):
            for depot in self.session.query(Depot).filter(Depot.app_id == parent_data.app_id).all():
                self._add_depot_node(depot, parent_item)

        elif isinstance(parent_data, Depot):
            for manifest in self.session.query(Manifest).filter(Manifest.depot_id == parent_data.depot_id).all():
                self._add_manifest_node(manifest, parent_item)

        elif isinstance(parent_data, Manifest):
            service = ManifestService(self.session)
            for file in service.get_files_by_manifest_id(str(parent_data.manifest_id)):
                self._add_file_node(file, parent_item)

    # ── Tree state save/restore ───────────────────────────────────

    @staticmethod
    def _get_item_id(data) -> Optional[str]:
        """Return a stable string ID for a tree node's data, or None."""
        try:
            if isinstance(data, Game):
                return f"game_{data.app_id}"
            if isinstance(data, Depot):
                return f"depot_{data.depot_id}"
            if isinstance(data, Manifest):
                return f"manifest_{data.manifest_id}"
            if isinstance(data, ManifestFile):
                return f"file_{data.id}"
        except Exception:
            # Handle expired/deleted SQLAlchemy objects
            return None
        return None

    def _get_tree_state(self) -> dict:
        """Capture which nodes are expanded/selected."""
        state = {'expanded': set(), 'selected': set()}

        def traverse(item):
            item_id = self._get_item_id(item.data(0, Qt.ItemDataRole.UserRole))
            if item_id:
                if item.isExpanded():
                    state['expanded'].add(item_id)
                if item.isSelected():
                    state['selected'].add(item_id)

            if item.isExpanded() or item.childCount() > 0:
                for i in range(item.childCount()):
                    traverse(item.child(i))

        for i in range(self.topLevelItemCount()):
            traverse(self.topLevelItem(i))
        return state

    def _restore_tree_state(self, state: dict):
        """Re-apply expansion and selection from a saved state."""
        def traverse(item):
            item_id = self._get_item_id(item.data(0, Qt.ItemDataRole.UserRole))
            if item_id:
                if item_id in state['expanded']:
                    item.setExpanded(True)  # triggers _on_item_expanded, loads children
                if item_id in state['selected']:
                    item.setSelected(True)

            for i in range(item.childCount()):
                traverse(item.child(i))

        for i in range(self.topLevelItemCount()):
            traverse(self.topLevelItem(i))

    # ── Selection helpers ─────────────────────────────────────────

    def get_selected_items(self) -> list:
        """Return the UserRole data for all selected tree items."""
        return [
            item.data(0, Qt.ItemDataRole.UserRole)
            for item in self.selectedItems()
            if item.data(0, Qt.ItemDataRole.UserRole) is not None
        ]

    def select_manifest(self, manifest_id_str: str) -> bool:
        """Expand necessary parents and select the manifest node."""
        manifest = self.session.query(Manifest).filter(Manifest.manifest_id == manifest_id_str).first()
        if not manifest or not manifest.depot:
            return False

        app_id = manifest.depot.app_id
        depot_id = manifest.depot.depot_id

        for i in range(self.topLevelItemCount()):
            game_item = self.topLevelItem(i)
            game_data = game_item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(game_data, Game) and game_data.app_id == app_id:
                game_item.setExpanded(True)
                
                for j in range(game_item.childCount()):
                    depot_item = game_item.child(j)
                    depot_data = depot_item.data(0, Qt.ItemDataRole.UserRole)
                    if isinstance(depot_data, Depot) and depot_data.depot_id == depot_id:
                        depot_item.setExpanded(True)
                        
                        for k in range(depot_item.childCount()):
                            man_item = depot_item.child(k)
                            man_data = man_item.data(0, Qt.ItemDataRole.UserRole)
                            if isinstance(man_data, Manifest) and str(man_data.manifest_id) == manifest_id_str:
                                self.clearSelection()
                                man_item.setSelected(True)
                                self.scrollToItem(man_item)
                                return True
                break
        return False

    # ── Context menu ──────────────────────────────────────────────

    def _on_context_menu(self, point):
        items = self.selectedItems()
        if not items:
            return

        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)

        if isinstance(data, Game):
            self._build_game_menu(menu)
        elif isinstance(data, Depot):
            self._build_depot_menu(menu)
        elif isinstance(data, Manifest):
            self._build_manifest_menu(menu)

        if not menu.isEmpty():
            menu.exec(self.mapToGlobal(point))

    def _build_game_menu(self, menu: QMenu):
        """Build context menu actions for a selected game."""
        games = [d for d in self.get_selected_items() if isinstance(d, Game)]
        if len(games) != 1:
            return

        game = games[0]
        db_game = self.session.query(Game).filter(Game.id == game.id).first()

        menu.addAction("Open in SteamDB").triggered.connect(
            lambda: self.open_steamdb_requested.emit(str(game.app_id)))

        menu.addAction("Parse Depots (SteamDB)").triggered.connect(
            lambda: self.parse_depots_requested.emit(str(game.app_id)))

        if not db_game or not db_game.depots:
            return

        menu.addSeparator()
        self._add_scrape_actions(menu, db_game.depots)

        menu.addSeparator()
        all_manifests = [m for d in db_game.depots for m in d.manifests]
        self._add_fetch_actions(menu, all_manifests)

    def _build_depot_menu(self, menu: QMenu):
        """Build context menu actions for selected depots."""
        selected_depots = [d for d in self.get_selected_items() if isinstance(d, Depot)]
        if not selected_depots:
            return

        if len(selected_depots) == 1:
            depot = selected_depots[0]
            menu.addAction("Open in SteamDB").triggered.connect(
                lambda: self.open_steamdb_depot_requested.emit(str(depot.depot_id)))
            menu.addSeparator()

        depot_ids = [d.id for d in selected_depots]
        db_depots = self.session.query(Depot).filter(Depot.id.in_(depot_ids)).all()
        self._add_scrape_actions(menu, db_depots)

        menu.addSeparator()
        all_manifests = [m for d in db_depots for m in d.manifests]
        self._add_fetch_actions(menu, all_manifests)

    def _build_manifest_menu(self, menu: QMenu):
        """Build context menu actions for selected manifests."""
        manifest_ids = [m.id for m in self.get_selected_items() if isinstance(m, Manifest)]
        if not manifest_ids:
            return

        db_manifests = self.session.query(Manifest).filter(Manifest.id.in_(manifest_ids)).all()
        self._add_fetch_actions(menu, db_manifests)

    # ── Reusable menu action builders ─────────────────────────────

    def _add_scrape_actions(self, menu: QMenu, depots: list):
        """Add 'Scrape Manifests' actions (unparsed + force) for a list of depots."""
        unparsed = [d for d in depots if not d.steamdb_manifests_parsed]
        if unparsed:
            menu.addAction(f"Scrape Manifests ({len(unparsed)} Unparsed Depots)").triggered.connect(
                lambda _=None, d=unparsed: self.scrape_manifests_requested.emit([x.depot_id for x in d]))

        menu.addAction(f"Force Scrape Manifests (All {len(depots)} Depots)").triggered.connect(
            lambda _=None, d=depots: self.scrape_manifests_requested.emit([x.depot_id for x in d]))

    def _add_fetch_actions(self, menu: QMenu, manifests: list):
        """Add 'Fetch File List' actions (unparsed + force) for a list of manifests."""
        unparsed = [m for m in manifests if not m.files_parsed]
        if unparsed:
            menu.addAction(f"Fetch File List ({len(unparsed)} Unparsed Manifests)").triggered.connect(
                lambda _=None, m=unparsed: self.download_manifest_requested.emit(m))

        if manifests:
            menu.addAction(f"Force Fetch File List (All {len(manifests)} Manifests)").triggered.connect(
                lambda _=None, m=manifests: self.download_manifest_requested.emit(m))

    # ── Utilities ─────────────────────────────────────────────────

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes is None:
            return ""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
