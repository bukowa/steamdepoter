"""PyQt6 models for SQLAlchemy ORM."""
from typing import List, Optional, Any
from PyQt6.QtCore import Qt, QAbstractItemModel, QModelIndex


class TreeItem:
    """Wrapper for tree items."""

    def __init__(self, data: Any, parent: Optional["TreeItem"] = None):
        self.data = data  # SQLAlchemy model instance
        self.parent_item = parent
        self.child_items: List[TreeItem] = []

    def append_child(self, child: "TreeItem") -> None:
        self.child_items.append(child)

    def child(self, row: int) -> Optional["TreeItem"]:
        if 0 <= row < len(self.child_items):
            return self.child_items[row]
        return None

    def child_count(self) -> int:
        return len(self.child_items)

    def parent(self) -> Optional["TreeItem"]:
        return self.parent_item

    def row(self) -> int:
        if self.parent_item:
            return self.parent_item.child_items.index(self)
        return 0


class SQLAlchemyTreeModel(QAbstractItemModel):
    """Generic tree model for SQLAlchemy ORM with relationships."""

    def __init__(self, root_items: List[Any], columns: List[str], relationship_attr: Optional[str] = None):
        """
        Initialize tree model.

        Args:
            root_items: SQLAlchemy model instances (e.g., Game objects)
            columns: Column names to display (e.g., ["app_id", "name"])
            relationship_attr: Relationship attribute name (e.g., "depots")
        """
        super().__init__()
        self.columns = columns
        self.relationship_attr = relationship_attr

        # Create root tree item
        self.root_item = TreeItem(None)

        # Populate root items
        for item in root_items:
            tree_item = TreeItem(item, self.root_item)
            self.root_item.append_child(tree_item)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        return parent_item.child_count()

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        item = index.internalPointer()
        if item.data is None:
            return None

        column_name = self.columns[index.column()]
        return str(getattr(item.data, column_name, ""))

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)

        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item.parent()

        if parent_item == self.root_item or parent_item is None:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def hasChildren(self, parent: QModelIndex = QModelIndex()) -> bool:
        if not parent.isValid():
            return self.root_item.child_count() > 0

        item = parent.internalPointer()

        # Load children on demand if relationship exists
        if self.relationship_attr and item.child_count() == 0:
            related_items = getattr(item.data, self.relationship_attr, [])
            for related_item in related_items:
                child = TreeItem(related_item, item)
                item.append_child(child)

        return item.child_count() > 0

    def canFetchMore(self, parent: QModelIndex) -> bool:
        if not parent.isValid():
            return False

        item = parent.internalPointer()
        return self.relationship_attr and item.child_count() == 0

    def fetchMore(self, parent: QModelIndex) -> None:
        if not self.canFetchMore(parent):
            return

        item = parent.internalPointer()
        related_items = getattr(item.data, self.relationship_attr, [])

        self.beginInsertRows(parent, 0, len(related_items) - 1)
        for related_item in related_items:
            child = TreeItem(related_item, item)
            item.append_child(child)
        self.endInsertRows()

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.columns):
            return self.columns[section]

        return None

