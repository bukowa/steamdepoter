from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QMenu, QMessageBox, QAbstractItemView
from PyQt6.QtCore import Qt, pyqtSignal

from src.db.schema import Game, Depot, Manifest, ManifestFile
from src.services import GameService, DepotService, ManifestService

class EntityTreeWidget(QTreeWidget):
    """A unified tree widget for displaying Games -> Depots -> Manifests -> Files."""
    
    # Custom signals for actions
    open_steamdb_requested = pyqtSignal(str)          # app_id
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
        
        self.customContextMenuRequested.connect(self.on_context_menu)
        self.itemExpanded.connect(self.on_item_expanded)
        
        self.setHeaderLabels(["Item", "Details", "Language", "Status"])
        
    def load_games(self):
        """Load all root game items."""
        tree_state = self.get_tree_state()
        self.clear()
        
        try:
            service = GameService(self.session)
            games = service.get_all_games()
            
            for game in games:
                self._add_game_node(game, self)
                
            self.setColumnWidth(0, 450)
            self.setColumnWidth(1, 150)
            self.setColumnWidth(2, 120)
            self.setColumnWidth(3, 100)
            
            self.restore_tree_state(tree_state)
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load games: {e}")

    def _add_game_node(self, game: Game, parent):
        item = QTreeWidgetItem(parent)
        item.setText(0, f"📁 {game.app_id} - {game.name}")
        item.setData(0, Qt.ItemDataRole.UserRole, game)
        # Add a dummy child to enable expansion
        self._add_dummy(item)
        return item

    def _add_depot_node(self, depot: Depot, parent):
        item = QTreeWidgetItem(parent)
        item.setText(0, f"📦 {depot.depot_id} - {depot.name}")
        item.setText(1, depot.os or "")
        item.setText(2, depot.language or "")
        parsed = "Yes" if getattr(depot, "steamdb_manifests_parsed", False) else "No"
        item.setText(3, parsed)
        item.setData(0, Qt.ItemDataRole.UserRole, depot)
        self._add_dummy(item)
        return item

    def _add_manifest_node(self, manifest: Manifest, parent):
        item = QTreeWidgetItem(parent)
        item.setText(0, f"📄 {manifest.manifest_id}")
        item.setText(1, str(manifest.date_str or ""))
        parsed = "Yes" if getattr(manifest, "files_parsed", False) else "No"
        item.setText(3, parsed)
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

    def _format_size(self, size_bytes: int) -> str:
        if size_bytes is None:
            return ""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    def get_tree_state(self) -> dict:
        state = {'expanded': set(), 'selected': set()}
        def traverse(item):
            data = item.data(0, Qt.ItemDataRole.UserRole)
            item_id = None
            if isinstance(data, Game):
                item_id = f"game_{data.app_id}"
            elif isinstance(data, Depot):
                item_id = f"depot_{data.depot_id}"
            elif isinstance(data, Manifest):
                item_id = f"manifest_{data.manifest_id}"
            elif isinstance(data, ManifestFile):
                item_id = f"file_{data.id}"
                
            if item_id:
                if item.isExpanded():
                    state['expanded'].add(item_id)
                if item.isSelected():
                    state['selected'].add(item_id)
                    
            # We traverse children if expanded, or if it already has loaded children
            if item.isExpanded() or item.childCount() > 0:
                for i in range(item.childCount()):
                    traverse(item.child(i))
                    
        for i in range(self.topLevelItemCount()):
            traverse(self.topLevelItem(i))
        return state

    def restore_tree_state(self, state: dict):
        def traverse(item):
            data = item.data(0, Qt.ItemDataRole.UserRole)
            item_id = None
            if isinstance(data, Game):
                item_id = f"game_{data.app_id}"
            elif isinstance(data, Depot):
                item_id = f"depot_{data.depot_id}"
            elif isinstance(data, Manifest):
                item_id = f"manifest_{data.manifest_id}"
            elif isinstance(data, ManifestFile):
                item_id = f"file_{data.id}"
                
            if item_id:
                if item_id in state['expanded']:
                    item.setExpanded(True) # This triggers itemExpanded and loads children synchronously
                if item_id in state['selected']:
                    item.setSelected(True)
                    
            for i in range(item.childCount()):
                traverse(item.child(i))
                    
        for i in range(self.topLevelItemCount()):
            traverse(self.topLevelItem(i))

    def on_item_expanded(self, item: QTreeWidgetItem):
        # Check if already populated (doesn't just have one dummy child)
        if item.childCount() != 1 or item.child(0).data(0, Qt.ItemDataRole.UserRole) != "dummy":
            return
            
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        # Remove dummy
        item.removeChild(item.child(0))

        try:
            if isinstance(data, Game):
                # We need to refresh the session or use existing relationship
                # It's safer to re-query to avoid DetachedInstanceError
                service = GameService(self.session)
                # Using relationship if not detached, else query
                depots = self.session.query(Depot).filter(Depot.app_id == data.app_id).all()
                for depot in depots:
                    self._add_depot_node(depot, item)
            
            elif isinstance(data, Depot):
                manifests = self.session.query(Manifest).filter(Manifest.depot_id == data.depot_id).all()
                for manifest in manifests:
                    self._add_manifest_node(manifest, item)
                    
            elif isinstance(data, Manifest):
                service = ManifestService(self.session)
                files = service.get_files_by_manifest_id(str(data.manifest_id))
                for file in files:
                    self._add_file_node(file, item)
                    
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load children: {e}")

    def _get_selected_items(self) -> list:
        items = self.selectedItems()
        return [item.data(0, Qt.ItemDataRole.UserRole) for item in items if item.data(0, Qt.ItemDataRole.UserRole) is not None]

    def on_context_menu(self, point):
        items = self.selectedItems()
        if not items:
            return
            
        # We handle context menu based on the *first* selected item's type,
        # but actions might apply to all selected items of that same type.
        first_item = items[0]
        data = first_item.data(0, Qt.ItemDataRole.UserRole)
        
        selected_data = self._get_selected_items()
        
        menu = QMenu(self)
        
        if isinstance(data, Game):
            # Only apply to game if it's the only type selected
            games = [d for d in selected_data if isinstance(d, Game)]
            if len(games) == 1:
                game = games[0]
                db_game = self.session.query(Game).filter(Game.id == game.id).first()

                open_db_action = menu.addAction("Open in SteamDB")
                open_db_action.triggered.connect(lambda checked, app_id=str(game.app_id): self.open_steamdb_requested.emit(app_id))

                parse_db_action = menu.addAction("Parse Depots (SteamDB)")
                parse_db_action.triggered.connect(lambda checked, app_id=str(game.app_id): self.parse_depots_requested.emit(app_id))
                
                if db_game and db_game.depots:
                    menu.addSeparator()
                    unparsed_depots = [d for d in db_game.depots if not d.steamdb_manifests_parsed]
                    if unparsed_depots:
                        scrape_all_action = menu.addAction(f"Scrape Manifests ({len(unparsed_depots)} Unparsed Depots)")
                        scrape_all_action.triggered.connect(lambda checked, d=unparsed_depots: self.scrape_manifests_requested.emit([dep.depot_id for dep in d]))
                    
                    force_scrape_all_action = menu.addAction(f"Force Scrape Manifests (All {len(db_game.depots)} Depots)")
                    force_scrape_all_action.triggered.connect(lambda checked, d=db_game.depots: self.scrape_manifests_requested.emit([dep.depot_id for dep in d]))

                    menu.addSeparator()
                    all_manifests = []
                    for d in db_game.depots:
                        all_manifests.extend(d.manifests)
                    
                    unparsed_manifests = [m for m in all_manifests if not m.files_parsed]
                    if unparsed_manifests:
                        dl_all_action = menu.addAction(f"Fetch File List ({len(unparsed_manifests)} Unparsed Manifests)")
                        dl_all_action.triggered.connect(lambda checked, m=unparsed_manifests: self.download_manifest_requested.emit(m))

                    if all_manifests:
                        force_dl_all_action = menu.addAction(f"Force Fetch File List (All {len(all_manifests)} Manifests)")
                        force_dl_all_action.triggered.connect(lambda checked, m=all_manifests: self.download_manifest_requested.emit(m))
                
        elif isinstance(data, Depot):
            depots = [d for d in selected_data if isinstance(d, Depot)]
            if depots:
                db_depots = self.session.query(Depot).filter(Depot.id.in_([d.id for d in depots])).all()
                
                unparsed_depots = [d for d in db_depots if not d.steamdb_manifests_parsed]
                if unparsed_depots:
                    scrape_action = menu.addAction(f"Scrape Manifests ({len(unparsed_depots)} Unparsed Depots)")
                    scrape_action.triggered.connect(lambda checked, d=unparsed_depots: self.scrape_manifests_requested.emit([dep.depot_id for dep in d]))
                
                force_scrape_action = menu.addAction(f"Force Scrape Manifests (All {len(db_depots)} Selected)")
                force_scrape_action.triggered.connect(lambda checked, d=db_depots: self.scrape_manifests_requested.emit([dep.depot_id for dep in d]))

                menu.addSeparator()
                all_manifests = []
                for d in db_depots:
                    all_manifests.extend(d.manifests)

                unparsed_manifests = [m for m in all_manifests if not m.files_parsed]
                if unparsed_manifests:
                    dl_action = menu.addAction(f"Fetch File List ({len(unparsed_manifests)} Unparsed Manifests)")
                    dl_action.triggered.connect(lambda checked, m=unparsed_manifests: self.download_manifest_requested.emit(m))
                
                if all_manifests:
                    force_dl_action = menu.addAction(f"Force Fetch File List (All {len(all_manifests)} Manifests)")
                    force_dl_action.triggered.connect(lambda checked, m=all_manifests: self.download_manifest_requested.emit(m))
                
        elif isinstance(data, Manifest):
            manifests = [m for m in selected_data if isinstance(m, Manifest)]
            if manifests:
                db_manifests = self.session.query(Manifest).filter(Manifest.id.in_([m.id for m in manifests])).all()
                unparsed_manifests = [m for m in db_manifests if not m.files_parsed]
                if unparsed_manifests:
                    parse_action = menu.addAction(f"Fetch File List ({len(unparsed_manifests)} Unparsed Manifests)")
                    parse_action.triggered.connect(lambda checked, m=unparsed_manifests: self.download_manifest_requested.emit(m))
                
                force_parse_action = menu.addAction(f"Force Fetch File List (All {len(db_manifests)} Selected)")
                force_parse_action.triggered.connect(lambda checked, m=db_manifests: self.download_manifest_requested.emit(m))
                
        if not menu.isEmpty():
            menu.exec(self.mapToGlobal(point))
