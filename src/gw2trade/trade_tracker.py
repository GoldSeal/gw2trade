import hashlib
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from db import SessionLocal, run_migrations
from models import CurrentTransaction, Item, User, WantedItem
from PyQt6.QtCore import QSettings, QSize, Qt, QUrl
from PyQt6.QtGui import (QAction, QCloseEvent, QColor, QFont, QIcon,
                         QKeySequence, QPixmap, QShortcut)
from PyQt6.QtNetwork import (QNetworkAccessManager, QNetworkReply,
                             QNetworkRequest)
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog,
                             QDialogButtonBox, QFormLayout, QHBoxLayout,
                             QHeaderView, QInputDialog, QLabel, QLineEdit,
                             QMainWindow, QMenu, QMessageBox, QPushButton,
                             QSpinBox, QStyledItemDelegate, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)
from sqlalchemy import func, select

GW2_BASE_URL = "https://api.guildwars2.com/v2"
CACHE_DIR = Path("icon_cache")
CACHE_DIR.mkdir(exist_ok=True)
CRAFTING_DISCIPLINES = [
    "Armorsmith",
    "Artificer",
    "Chef",
    "Huntsman",
    "Jeweler",
    "Leatherworker",
    "Scribe",
    "Tailor",
    "Weaponsmith",
    "Unassigned",
]
RARITY_COLORS: dict[str, QColor] = {
    "Junk": QColor("#AAAAAA"),  # Grey
    "Basic": QColor("#CCCCCC"),  # Light Grey
    "Fine": QColor("#62A4DA"),  # Blue
    "Masterwork": QColor("#1a9306"),  # Green
    "Rare": QColor("#FCD000"),  # Yellow
    "Exotic": QColor("#FFA405"),  # Orange / Gold
    "Ascended": QColor("#FB3E8D"),  # Fuchsia / Magenta
    "Legendary": QColor("#A533FF"),  # Violet (bonus)
}

DEFAULT_ITEM_COLOR = QColor("#000000")
CHECKED_BG_COLOR = QColor("#222222")
CHECKED_TEXT_COLOR = QColor("#555a64")
NORMAL_BG_COLOR = QColor("#1e1e1e")
NORMAL_TEXT_COLOR = QColor("#e0e0e0")


logger = logging.getLogger(__file__)


@dataclass
class TrackerSnapshot:
    in_trade_map: dict[tuple[int, str], int]
    wanted_map: dict[tuple[int, str], int]
    grouped_items: dict[str, list[tuple[int, str]]]
    item_metadata: dict[int, Item]
    note_map: dict[tuple[int, str], str]


class CraftDelegate(QStyledItemDelegate):
    """In-table combobox editor for manually selecting or typing a craft."""

    def __init__(self, disciplines: list[str], parent=None):
        super().__init__(parent)
        self.disciplines = disciplines

    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.setEditable(True)
        combo.addItems(self.disciplines)
        return combo

    def setEditorData(self, editor, index):
        text = index.data(Qt.ItemDataRole.DisplayRole) or "Unassigned"
        idx = editor.findText(text)
        if idx >= 0:
            editor.setCurrentIndex(idx)
        else:
            editor.setEditText(text)

    def setModelData(self, editor, model, index):
        val = editor.currentText().strip() or "Unassigned"
        model.setData(index, val, Qt.ItemDataRole.EditRole)


# ============================================================================
# Dialogs
# ============================================================================


class AddUserDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Add New User")
        self.resize(380, 140)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_input = QLineEdit()
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("XXXXXXXX-XXXX-XXXX-XXXX-...")

        form.addRow("Username:", self.name_input)
        form.addRow("API Key:", self.api_key_input)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def get_data(self) -> tuple[str, str]:
        return self.name_input.text().strip(), self.api_key_input.text().strip()


class AddWantedItemDialog(QDialog):
    def __init__(
        self,
        craft_options: Optional[list[str]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add Wanted Item")
        self.resize(320, 160)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Item ID (GW2 IDs can reach up to ~150,000+)
        self.item_id_spin = QSpinBox()
        self.item_id_spin.setRange(1, 999_999)
        self.item_id_spin.setValue(1)

        # Listing Type dropdown
        self.type_combo = QComboBox()
        self.type_combo.addItems(["SELL", "BUY"])

        # Target Quantity
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(0, 1_000_000)
        self.qty_spin.setValue(1)

        self.craft_combo = QComboBox()
        self.craft_combo.setEditable(True)
        crafts = list(CRAFTING_DISCIPLINES)
        if craft_options:
            for c in craft_options:
                if c not in crafts:
                    crafts.append(c)
        self.craft_combo.addItems(crafts)
        self.craft_combo.setCurrentText("Unassigned")

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Optional note / character name...")

        form.addRow("Item ID:", self.item_id_spin)
        form.addRow("Listing Type:", self.type_combo)
        form.addRow("Craft Partition:", self.craft_combo)
        form.addRow("Wanted Quantity:", self.qty_spin)
        form.addRow("Note:", self.note_input)
        layout.addLayout(form)

        # OK / Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def get_data(self) -> tuple[int, str, int, str, str]:
        return (
            self.item_id_spin.value(),
            self.type_combo.currentText().lower(),
            self.qty_spin.value(),
            self.craft_combo.currentText().strip() or "Unassigned",
            self.note_input.currentText().strip(),
        )


# ============================================================================
# Main Window
# ============================================================================


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GW2 Commerce & Inventory Tracker")
        self.resize(1050, 650)

        self.active_user_id: Optional[int] = None
        self.active_user_name: str = ""

        self.search_matches: list[int] = []
        self.current_match_idx: int = -1

        # Image caching and non-blocking downloader
        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self._on_image_downloaded)
        self.image_cache: dict[str, QPixmap] = {}
        self.pending_replies: dict[QNetworkReply, tuple[int, int, Path]] = {}

        self._init_menu()
        self._init_ui()
        self._restore_settings()
        self._bootstrap_user()

    def _init_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)  # Ctrl+Q / Cmd+Q
        exit_action.setStatusTip("Close the application")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        user_menu = menubar.addMenu("&Users")

        switch_user_action = QAction("&Switch User...", self)
        switch_user_action.triggered.connect(self.switch_user)
        user_menu.addAction(switch_user_action)

        add_user_action = QAction("&Add New User...", self)
        add_user_action.triggered.connect(self.prompt_add_user)
        user_menu.addAction(add_user_action)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Top Control Bar
        top_bar = QHBoxLayout()
        self.user_label = QLabel("No user active")
        self.user_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        top_bar.addWidget(self.user_label)
        top_bar.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Find item (press Enter)...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(170)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._jump_next)
        top_bar.addWidget(self.search_input)

        self.btn_prev_match = QPushButton("▲")
        self.btn_prev_match.setFixedWidth(26)
        self.btn_prev_match.setToolTip("Previous match")
        self.btn_prev_match.clicked.connect(self._jump_prev)
        top_bar.addWidget(self.btn_prev_match)

        self.btn_next_match = QPushButton("▼")
        self.btn_next_match.setFixedWidth(26)
        self.btn_next_match.setToolTip("Next match")
        self.btn_next_match.clicked.connect(self._jump_next)
        top_bar.addWidget(self.btn_next_match)

        self.match_count_label = QLabel("")
        self.match_count_label.setStyleSheet("color: #888888; font-size: 11px;")
        top_bar.addWidget(self.match_count_label)

        self.clear_search_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.clear_search_shortcut.activated.connect(self._clear_search)

        # Craft Partition Filter
        top_bar.addWidget(QLabel("Partition:"))
        self.craft_filter_combo = QComboBox()
        self.craft_filter_combo.addItem("All Crafts")
        self.craft_filter_combo.currentTextChanged.connect(
            self.refresh_tracker_table
        )
        top_bar.addWidget(self.craft_filter_combo)

        self.btn_fetch = QPushButton("Refresh from API")
        self.btn_fetch.clicked.connect(self.fetch_user_transactions)
        top_bar.addWidget(self.btn_fetch)

        self.btn_add_target = QPushButton("Add Target Item")
        self.btn_add_target.clicked.connect(self.add_target_item)
        top_bar.addWidget(self.btn_add_target)

        layout.addLayout(top_bar)

        # Comparison Table
        self.tracker_table = QTableWidget()
        self.tracker_table.setColumnCount(8)
        self.tracker_table.setHorizontalHeaderLabels(
            [
                "Item",
                "Craft",
                "Type",
                "Needed",
                "Wanted",
                "In Trade",
                "",
                "Note",
            ]
        )
        self.tracker_table.setIconSize(QSize(32, 32))
        self.tracker_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.tracker_table.horizontalHeader().setSectionResizeMode(
            7, QHeaderView.ResizeMode.Interactive
        )
        self.tracker_table.setColumnWidth(6, 40)

        self.tracker_table.setItemDelegateForColumn(
            1, CraftDelegate(CRAFTING_DISCIPLINES, self.tracker_table)
        )
        self.tracker_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.tracker_table.customContextMenuRequested.connect(
            self._on_context_menu
        )

        self.tracker_table.setStyleSheet("""
            QTableWidget {
                background-color: #1e1e1e;
                color: #e0e0e0;
                gridline-color: #333333;
                selection-background-color: #3d4450;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #3a3a3a;
                padding: 4px;
                font-weight: bold;
            }
            QTableCornerButton::section {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
            }
            """)
        self.tracker_table.cellChanged.connect(self.on_cell_changed)
        layout.addWidget(self.tracker_table)

    def _restore_settings(self):
        settings = QSettings("GW2Trade", "TradeTracker")

        # Restore column widths / header state
        header_state = settings.value("tracker_table_header")
        if header_state:
            self.tracker_table.horizontalHeader().restoreState(header_state)

        # Restore window geometry
        geometry = settings.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event: QCloseEvent):
        settings = QSettings("GW2Trade", "TradeTracker")

        # Save header sizes and window geometry
        settings.setValue(
            "tracker_table_header",
            self.tracker_table.horizontalHeader().saveState(),
        )
        settings.setValue("window_geometry", self.saveGeometry())

        super().closeEvent(event)

    # ========================================================================
    # Search & Jump Navigation
    # ========================================================================

    def _on_search_text_changed(self, text: str):
        query = text.strip().lower()
        self.search_matches.clear()
        self.current_match_idx = -1

        if not query:
            self.match_count_label.setText("")
            self.search_input.setStyleSheet("")
            return

        clean_query = query.lstrip("#").removeprefix("id:").strip()
        exact_matches = []
        partial_matches = []

        for row in range(self.tracker_table.rowCount()):
            # Skip banner header rows (spanned over all columns)
            if self.tracker_table.columnSpan(row, 0) > 1:
                continue

            item = self.tracker_table.item(row, 0)
            if not item:
                continue

            item_id = item.data(Qt.ItemDataRole.UserRole)
            item_text = item.text().lower()
            str_item_id = str(item_id) if item_id is not None else ""
            if clean_query and clean_query == str_item_id:
                exact_matches.append(row)
            elif (
                (clean_query and clean_query in str_item_id)
                or query in item_text
            ):
                partial_matches.append(row)
            self.search_matches = exact_matches + partial_matches

        if self.search_matches:
            self.search_input.setStyleSheet("")
            self._jump_to_match(0)
        else:
            self.search_input.setStyleSheet("border: 1px solid #a33;")
            self.match_count_label.setText("No matches")

    def _jump_next(self):
        if not self.search_matches:
            return
        next_idx = (self.current_match_idx + 1) % len(self.search_matches)
        self._jump_to_match(next_idx)

    def _jump_prev(self):
        if not self.search_matches:
            return
        prev_idx = (self.current_match_idx - 1) % len(self.search_matches)
        self._jump_to_match(prev_idx)

    def _jump_to_match(self, match_idx: int):
        self.current_match_idx = match_idx
        target_row = self.search_matches[match_idx]

        self.tracker_table.selectRow(target_row)
        target_item = self.tracker_table.item(target_row, 0)
        if target_item:
            self.tracker_table.scrollToItem(
                target_item,
                QTableWidget.ScrollHint.PositionAtCenter,
            )

        self.match_count_label.setText(
            f"{match_idx + 1}/{len(self.search_matches)}"
        )

    def _clear_search(self):
        """Clears search text, match markers, and table selection on Esc."""
        if self.search_input.text():
            self.search_input.clear()
        self.tracker_table.clearSelection()
        self.search_input.clearFocus()
        self.tracker_table.setFocus()

    # ========================================================================
    # User Management
    # ========================================================================

    def _bootstrap_user(self):
        with SessionLocal() as session:
            first_user = session.scalars(select(User).order_by(User.id)).first()

        if first_user:
            self.set_active_user(first_user.id, first_user.name)
        else:
            QMessageBox.information(
                self,
                "Welcome",
                "No users found. Please add a user to continue.",
            )
            created = self.prompt_add_user()
            if not created:
                self.user_label.setText(
                    "No active user. Use 'Users -> Add New User...'."
                )
                self.btn_fetch.setEnabled(False)
                self.btn_add_target.setEnabled(False)

    def set_active_user(self, user_id: int, user_name: str):
        self.active_user_id = user_id
        self.active_user_name = user_name
        self.user_label.setText(f"Active User: {user_name} (ID: {user_id})")
        self.btn_fetch.setEnabled(True)
        self.btn_add_target.setEnabled(True)
        self.refresh_tracker_table()

    def prompt_add_user(self) -> bool:
        dialog = AddUserDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, api_key = dialog.get_data()
            if not name or not api_key:
                QMessageBox.warning(
                    self, "Validation Error", "Name and API Key are required."
                )
                return False

            with SessionLocal() as session:
                new_user = User(name=name, api_key=api_key)
                session.add(new_user)
                try:
                    session.commit()
                    self.set_active_user(new_user.id, new_user.name)
                    return True
                except Exception as exc:
                    session.rollback()
                    QMessageBox.critical(
                        self, "Database Error", f"Could not create user:\n{exc}"
                    )
        return False

    def switch_user(self):
        with SessionLocal() as session:
            users = session.scalars(select(User).order_by(User.id)).all()

        if not users:
            QMessageBox.information(self, "No Users", "No users found.")
            return

        user_map = {f"{u.name} (ID: {u.id})": u for u in users}
        current_display = f"{self.active_user_name} (ID: {self.active_user_id})"
        default_index = (
            list(user_map.keys()).index(current_display)
            if current_display in user_map
            else 0
        )

        selected_label, ok = QInputDialog.getItem(
            self,
            "Switch User",
            "Select User:",
            list(user_map.keys()),
            current=default_index,
            editable=False,
        )

        if ok and selected_label:
            selected_user = user_map[selected_label]
            self.set_active_user(selected_user.id, selected_user.name)

    # ========================================================================
    # Item Metadata & Icon Loading
    # ========================================================================

    def ensure_items_cached(self, item_ids: set[int]):
        """Fetches missing items in bulk from GW2 API and stores them."""
        if not item_ids:
            return

        with SessionLocal() as session:
            existing = set(
                session.scalars(
                    select(Item.id).where(Item.id.in_(item_ids))
                ).all()
            )
            missing = list(item_ids - existing)

            # Bulk request in batches of up to 200 items
            batch_size = 200
            for i in range(0, len(missing), batch_size):
                batch = missing[i : i + batch_size]
                ids_str = ",".join(str(x) for x in batch)
                try:
                    resp = requests.get(
                        f"{GW2_BASE_URL}/items?ids={ids_str}", timeout=10
                    )
                    if resp.status_code == 200:
                        for raw in resp.json():
                            item = Item(
                                id=raw["id"],
                                name=raw.get("name", "Unknown Item"),
                                icon=raw.get("icon"),
                                chat_link=raw.get("chat_link"),
                                description=raw.get("description"),
                                type=raw.get("type"),
                                rarity=raw.get("rarity"),
                                level=raw.get("level", 0),
                                vendor_value=raw.get("vendor_value", 0),
                            )
                            session.add(item)
                        session.commit()
                except requests.RequestException:
                    pass

    def _get_disk_cache_path(self, url: str) -> Path:
        """Generates a stable local filename using MD5 hash of the URL."""
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        return CACHE_DIR / f"{url_hash}.png"

    def _load_icon_for_item(self, row: int, col: int, icon_url: str):
        """Asynchronously loads the item icon, using a local memory cache."""
        if not icon_url:
            return

        if icon_url in self.image_cache:
            item_widget = self.tracker_table.item(row, col)
            if item_widget:
                item_widget.setIcon(QIcon(self.image_cache[icon_url]))
            return

        disk_path = self._get_disk_cache_path(icon_url)
        if disk_path.exists():
            pixmap = QPixmap(str(disk_path))
            if not pixmap.isNull():
                self.image_cache[icon_url] = pixmap
                item_widget = self.tracker_table.item(row, col)
                if item_widget:
                    item_widget.setIcon(QIcon(pixmap))
                return

        reply = self.network_manager.get(QNetworkRequest(QUrl(icon_url)))
        self.pending_replies[reply] = (row, col, disk_path)

    def _on_image_downloaded(self, reply: QNetworkReply):
        loc = self.pending_replies.pop(reply, None)
        if not loc:
            reply.deleteLater()
            return

        row, col, disk_path = loc

        if reply.error() == QNetworkReply.NetworkError.NoError:
            raw_bytes = reply.readAll().data()

            # Save binary data directly to disk cache
            try:
                disk_path.write_bytes(raw_bytes)
            except OSError as exc:
                print(f"Warning: could not write disk cache {disk_path}: {exc}")

            # Construct QPixmap and store in memory cache
            pixmap = QPixmap()
            pixmap.loadFromData(raw_bytes)
            url_str = reply.url().toString()
            self.image_cache[url_str] = pixmap

            # Set icon on the table cell
            item_widget = self.tracker_table.item(row, col)
            if item_widget:
                item_widget.setIcon(QIcon(pixmap))

        reply.deleteLater()

    # ========================================================================
    # Transactions Sync
    # ========================================================================

    def fetch_user_transactions(self):
        if not self.active_user_id:
            return

        with SessionLocal() as session:
            user = session.get(User, self.active_user_id)
            if not user:
                return
            api_key = user.api_key

        headers = {"Authorization": f"Bearer {api_key}"}
        endpoints = {
            "buy": f"{GW2_BASE_URL}/commerce/transactions/current/buys",
            "sell": f"{GW2_BASE_URL}/commerce/transactions/current/sells",
        }

        fetched_transactions = []
        try:
            for l_type, base_url in endpoints.items():
                page = 0
                total_pages = 1
                while page < total_pages:
                    resp = requests.get(
                        base_url,
                        headers=headers,
                        params={"page": page, "page_size": 200},
                        timeout=10,
                    )
                    resp.raise_for_status()
                    total_pages = int(resp.headers.get("X-Page-Total", 1))

                    for tx in resp.json():
                        tx["listing_type"] = l_type
                        fetched_transactions.append(tx)
                    page += 1

        except requests.RequestException as exc:
            QMessageBox.critical(
                self,
                "API Error",
                f"Failed fetching current transactions:\n{exc}",
            )
            return

        with SessionLocal() as session:
            session.query(CurrentTransaction).filter(
                CurrentTransaction.user_id == self.active_user_id
            ).delete()

            for tx in fetched_transactions:
                record = CurrentTransaction(
                    id=tx["id"],
                    user_id=self.active_user_id,
                    item_id=tx["item_id"],
                    price=tx["price"],
                    quantity=tx["quantity"],
                    created=tx["created"],
                    listing_type=tx["listing_type"],
                )
                session.add(record)
            session.commit()

        # Pre-fetch any newly discovered items
        referenced_ids = {tx["item_id"] for tx in fetched_transactions}
        self.ensure_items_cached(referenced_ids)

        QMessageBox.information(
            self,
            "Success",
            f"Successfully updated {len(fetched_transactions)} active listing(s).",
        )
        self.refresh_tracker_table()

    # ========================================================================
    def _get_item_craft(self, session, item_id: int) -> str:
        craft = session.scalar(
            select(WantedItem.craft).where(
                WantedItem.user_id == self.active_user_id,
                WantedItem.item_id == item_id,
            )
        )
        return craft or "Unassigned"

    def _set_item_craft(self, item_id: int, listing_type: str, craft: str):
        if not self.active_user_id:
            return

        with SessionLocal() as session:
            targets = session.scalars(
                select(WantedItem).where(
                    WantedItem.user_id == self.active_user_id,
                    WantedItem.item_id == item_id,
                )
            ).all()

            if targets:
                for t in targets:
                    t.craft = craft
            else:
                session.add(
                    WantedItem(
                        user_id=self.active_user_id,
                        item_id=item_id,
                        target_quantity=0,
                        listing_type=listing_type,
                        craft=craft,
                    )
                )
            session.commit()

        self.refresh_tracker_table()

    def _prompt_custom_craft(self, item_id: int, listing_type: str):
        text, ok = QInputDialog.getText(
            self,
            "Custom Craft Partition",
            "Enter craft or character partition name:",
        )
        if ok and text.strip():
            self._set_item_craft(item_id, listing_type, text.strip())

    def _delete_target_item(self, item_id: int, listing_type: str):
        if not self.active_user_id:
            return

        with SessionLocal() as session:
            target = session.scalar(
                select(WantedItem).where(
                    WantedItem.user_id == self.active_user_id,
                    WantedItem.item_id == item_id,
                    WantedItem.listing_type == listing_type,
                )
            )
            if target:
                session.delete(target)
                session.commit()

        self.refresh_tracker_table()

    def _on_context_menu(self, pos):
        row = self.tracker_table.rowAt(pos.y())
        if row < 0:
            return

        meta_item = self.tracker_table.item(row, 4)
        if not meta_item:
            return
        meta = meta_item.data(Qt.ItemDataRole.UserRole)
        if not meta:
            return

        item_id, listing_type = meta

        menu = QMenu(self)
        craft_menu = menu.addMenu("Set Craft Partition")

        for craft in CRAFTING_DISCIPLINES:
            action = craft_menu.addAction(craft)
            action.triggered.connect(
                lambda _, d=craft: self._set_item_craft(
                    item_id, listing_type, d
                )
            )

        custom_action = craft_menu.addAction("Custom...")
        custom_action.triggered.connect(
            lambda _: self._prompt_custom_craft(item_id, listing_type)
        )

        menu.addSeparator()
        delete_action = menu.addAction("Remove Target Item")
        delete_action.triggered.connect(
            lambda _: self._delete_target_item(item_id, listing_type)
        )

        menu.exec(self.tracker_table.viewport().mapToGlobal(pos))

    # ========================================================================
    # Table Rendering with Icons & Target Quantities
    # ========================================================================

    def add_target_item(self):
        if not self.active_user_id:
            return

        dialog = AddWantedItemDialog(CRAFTING_DISCIPLINES, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        item_id, tx_type, target_qty, craft, note = dialog.get_data()

        with SessionLocal() as session:
            existing = session.scalar(
                select(WantedItem).where(
                    WantedItem.user_id == self.active_user_id,
                    WantedItem.item_id == item_id,
                    WantedItem.listing_type == tx_type,
                )
            )
            if existing:
                existing.target_quantity = target_qty
                existing.craft = craft
                existing.note = note
            else:
                session.add(
                    WantedItem(
                        user_id=self.active_user_id,
                        item_id=item_id,
                        target_quantity=target_qty,
                        listing_type=tx_type,
                        craft=craft,
                        note=note,
                    )
                )
            # Keep other listing types for this item aligned to the same craft
            other_targets = session.scalars(
                select(WantedItem).where(
                    WantedItem.user_id == self.active_user_id,
                    WantedItem.item_id == item_id,
                )
            ).all()
            for target in other_targets:
                target.craft = craft
            session.commit()

        self.ensure_items_cached({item_id})
        self.refresh_tracker_table()

    def refresh_tracker_table(self):
        """Refreshes, filters, and renders the trade tracker comparison table."""
        if not self.active_user_id:
            return

        snapshot = self._load_tracker_data()
        active_filter = self._sync_craft_filter(snapshot.grouped_items)
        filtered_groups = self._filter_and_sort_groups(snapshot, active_filter)

        self.tracker_table.blockSignals(True)
        self.tracker_table.clearSpans()

        total_rows = sum(1 + len(keys) for keys in filtered_groups.values())
        self.tracker_table.setRowCount(total_rows)

        current_row = 0
        for craft_name, keys in filtered_groups.items():
            self._render_banner_row(current_row, craft_name, len(keys))
            current_row += 1

            for item_id, listing_type in keys:
                self._render_item_row(
                    row=current_row,
                    item_id=item_id,
                    listing_type=listing_type,
                    craft_name=craft_name,
                    wanted_qty=snapshot.wanted_map.get(
                        (item_id, listing_type), 0
                    ),
                    in_trade_qty=snapshot.in_trade_map.get(
                        (item_id, listing_type), 0
                    ),
                    item_data=snapshot.item_metadata.get(item_id),
                    note=snapshot.note_map.get((item_id, listing_type), ""),
                )
                current_row += 1

        self.tracker_table.blockSignals(False)

    def _load_tracker_data(self) -> TrackerSnapshot:
        """Queries database for active trades, targets, and item metadata."""
        with SessionLocal() as session:
            trade_rows = session.execute(
                select(
                    CurrentTransaction.item_id,
                    CurrentTransaction.listing_type,
                    func.sum(CurrentTransaction.quantity).label(
                        "total_in_trade"
                    ),
                )
                .where(CurrentTransaction.user_id == self.active_user_id)
                .group_by(
                    CurrentTransaction.item_id,
                    CurrentTransaction.listing_type,
                )
            ).all()

            in_trade_map = {
                (row.item_id, row.listing_type): row.total_in_trade
                for row in trade_rows
            }

            targets = session.scalars(
                select(WantedItem).where(
                    WantedItem.user_id == self.active_user_id
                )
            ).all()

            all_keys = set(in_trade_map.keys()) | {
                (t.item_id, t.listing_type) for t in targets
            }
            wanted_map = {
                (t.item_id, t.listing_type): t.target_quantity for t in targets
            }

            craft_map: dict[tuple[int, str], str] = {}
            craft_by_item: dict[int, str] = {}
            for t in targets:
                c_val = t.craft or "Unassigned"
                craft_map[(t.item_id, t.listing_type)] = c_val
                if t.item_id not in craft_by_item or c_val != "Unassigned":
                    craft_by_item[t.item_id] = c_val

            all_item_ids = {k[0] for k in all_keys}
            self.ensure_items_cached(all_item_ids)

            db_items = session.scalars(
                select(Item).where(Item.id.in_(all_item_ids))
            ).all()
            item_metadata = {item.id: item for item in db_items}

            grouped_items: dict[str, list[tuple[int, str]]] = defaultdict(list)
            for key in all_keys:
                c = craft_map.get(key, craft_by_item.get(key[0], "Unassigned"))
                grouped_items[c].append(key)

            note_map = {
                (t.item_id, t.listing_type): t.note or "" for t in targets
            }

        return TrackerSnapshot(
            in_trade_map=in_trade_map,
            wanted_map=wanted_map,
            grouped_items=grouped_items,
            item_metadata=item_metadata,
            note_map=note_map,
        )

    def _sync_craft_filter(
        self, grouped_items: dict[str, list[tuple[int, str]]]
    ) -> str:
        """Updates the partition combo filter and returns the active selection."""
        present_crafts = sorted(
            grouped_items.keys(),
            key=lambda x: (
                (
                    CRAFTING_DISCIPLINES.index(x)
                    if x in CRAFTING_DISCIPLINES
                    else 99
                ),
                x,
            ),
        )

        current_filter = self.craft_filter_combo.currentText()
        self.craft_filter_combo.blockSignals(True)
        self.craft_filter_combo.clear()
        self.craft_filter_combo.addItem("All Crafts")

        for c in present_crafts:
            self.craft_filter_combo.addItem(f"{c} ({len(grouped_items[c])})")

        found_idx = 0
        for idx in range(self.craft_filter_combo.count()):
            text = self.craft_filter_combo.itemText(idx)
            if text.split(" (")[0] == current_filter.split(" (")[0]:
                found_idx = idx
                break

        self.craft_filter_combo.setCurrentIndex(found_idx)
        self.craft_filter_combo.blockSignals(False)

        return self.craft_filter_combo.currentText().split(" (")[0]

    def _filter_and_sort_groups(
        self, snapshot: TrackerSnapshot, active_filter: str
    ) -> dict[str, list[tuple[int, str]]]:
        """Applies partition filter and sorts items by needed quantity descending."""

        def sort_key(key_tuple):
            item_id, listing_type = key_tuple
            w_qty = snapshot.wanted_map.get(key_tuple, 0)
            t_qty = snapshot.in_trade_map.get(key_tuple, 0)
            diff = w_qty - t_qty
            return (-diff, item_id, listing_type)

        sorted_groups: dict[str, list[tuple[int, str]]] = {}
        for craft_name, keys in snapshot.grouped_items.items():
            if (
                active_filter in ("All Crafts", "")
                or craft_name == active_filter
            ):
                sorted_groups[craft_name] = sorted(keys, key=sort_key)

        return sorted_groups

    def _render_banner_row(self, row: int, craft_name: str, count: int):
        """Renders the section header banner spanning all columns."""
        banner_font = QFont()
        banner_font.setBold(True)

        banner_item = QTableWidgetItem(f" Craft: {craft_name} ({count} items)")
        banner_item.setBackground(QColor("#474f4d"))
        banner_item.setForeground(QColor("#a3b3ed"))
        banner_item.setFont(banner_font)
        banner_item.setFlags(Qt.ItemFlag.NoItemFlags)

        self.tracker_table.setItem(row, 0, banner_item)
        self.tracker_table.setSpan(row, 0, 1, 8)

    def _render_item_row(
        self,
        row: int,
        item_id: int,
        listing_type: str,
        craft_name: str,
        wanted_qty: int,
        in_trade_qty: int,
        note: str,
        item_data: Optional[Item],
    ):
        """Renders all cells for a single item row."""
        item_name = item_data.name if item_data else f"Item #{item_id}"
        rarity = item_data.rarity if item_data else "Basic"
        icon_url = item_data.icon if item_data else None
        diff = wanted_qty - in_trade_qty

        # Col 0: Item Name & Icon
        item_widget = QTableWidgetItem(f"{item_name}  (ID: {item_id})")
        item_widget.setFlags(item_widget.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item_widget.setData(Qt.ItemDataRole.UserRole, item_id)
        item_widget.setForeground(RARITY_COLORS.get(rarity, DEFAULT_ITEM_COLOR))
        self.tracker_table.setItem(row, 0, item_widget)

        if icon_url:
            self._load_icon_for_item(item_id, row, icon_url)

        # Col 1: Craft Partition
        craft_item = QTableWidgetItem(craft_name)
        craft_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        craft_item.setData(Qt.ItemDataRole.UserRole, (item_id, listing_type))
        self.tracker_table.setItem(row, 1, craft_item)

        # Col 2: Type
        type_item = QTableWidgetItem(listing_type.upper())
        type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.tracker_table.setItem(row, 2, type_item)

        # Col 3: Needed (diff)
        diff_label = f"{diff}" if diff > 0 else ""
        diff_item = QTableWidgetItem(diff_label)
        diff_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        diff_item.setFlags(diff_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if diff > 0:
            diff_item.setForeground(Qt.GlobalColor.yellow)
        self.tracker_table.setItem(row, 3, diff_item)

        # Col 4: Wanted Qty (Editable)
        wanted_widget = QTableWidgetItem(str(wanted_qty))
        wanted_widget.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        wanted_widget.setData(Qt.ItemDataRole.UserRole, (item_id, listing_type))
        self.tracker_table.setItem(row, 4, wanted_widget)

        # Col 5: In Trade Qty
        trade_item = QTableWidgetItem(str(in_trade_qty))
        trade_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        trade_item.setFlags(trade_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.tracker_table.setItem(row, 5, trade_item)

        # Col 6: Checkbox
        check_item = QTableWidgetItem()
        check_item.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        check_item.setCheckState(Qt.CheckState.Unchecked)
        check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        check_item.setData(Qt.ItemDataRole.UserRole, (item_id, listing_type))
        check_item.setData(Qt.ItemDataRole.UserRole + 1, (rarity, diff))
        self.tracker_table.setItem(row, 6, check_item)

        note_widget = QTableWidgetItem(note)
        note_widget.setData(Qt.ItemDataRole.UserRole, (item_id, listing_type))
        self.tracker_table.setItem(row, 7, note_widget)

    def on_cell_changed(self, row: int, column: int):
        if not self.active_user_id:
            logger.warning("no active user")
            return

        item = self.tracker_table.item(row, column)
        meta = item.data(Qt.ItemDataRole.UserRole)
        if not meta:
            logger.warning(f"item ({row}, {column}) has no metadata")
            return

        item_id, listing_type = meta

        if column == 1:
            new_craft = item.text().strip() or "Unassigned"
            self._set_item_craft(item_id, listing_type, new_craft)
            return

        if column == 6:
            self.on_check_toggle(item, row)
            return

        if column == 4:
            self.on_new_wanted_quantity(item, item_id, listing_type)

        if column == 7:
            self.on_note_edited(item, item_id, listing_type)

        self.refresh_tracker_table()

    def on_new_wanted_quantity(self, item, item_id: int, listing_type: str):
        try:
            new_qty = int(item.text().strip())
            if new_qty < 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(
                self, "Invalid Value", "Quantity must be a positive integer."
            )
            self.refresh_tracker_table()
            return

        with SessionLocal() as session:
            target = session.scalar(
                select(WantedItem).where(
                    WantedItem.user_id == self.active_user_id,
                    WantedItem.item_id == item_id,
                    WantedItem.listing_type == listing_type,
                )
            )
            if target:
                target.target_quantity = new_qty
            else:
                session.add(
                    WantedItem(
                        user_id=self.active_user_id,
                        item_id=item_id,
                        target_quantity=new_qty,
                        listing_type=listing_type,
                        note="",
                    )
                )
            session.commit()

    def on_note_edited(self, item, item_id: int, listing_type: str):
        new_note = item.text().strip()
        with SessionLocal() as session:
            target = session.scalar(
                select(WantedItem).where(
                    WantedItem.user_id == self.active_user_id,
                    WantedItem.item_id == item_id,
                    WantedItem.listing_type == listing_type,
                )
            )
            if target:
                target.note = new_note
            else:
                existing_craft = self._get_item_craft(session, item_id)
                session.add(
                    WantedItem(
                        user_id=self.active_user_id,
                        item_id=item_id,
                        target_quantity=0,
                        listing_type=listing_type,
                        craft=existing_craft,
                        note=new_note,
                    )
                )
            session.commit()

    def on_check_toggle(self, item, row: int):
        is_checked = item.checkState() == Qt.CheckState.Checked
        rarity, diff = item.data(Qt.ItemDataRole.UserRole + 1)
        bg_color = CHECKED_BG_COLOR if is_checked else NORMAL_BG_COLOR
        fg_color = CHECKED_TEXT_COLOR if is_checked else NORMAL_TEXT_COLOR
        logger.info(f"row {row} toggled {is_checked}")

        self.tracker_table.blockSignals(True)
        for col in range(self.tracker_table.columnCount()):
            item_ = self.tracker_table.item(row, col)
            if item_:
                item_.setBackground(bg_color)
                item_.setForeground(fg_color)

        # Restore specialized foregrounds if row is active (unchecked)
        if not is_checked:
            item_0 = self.tracker_table.item(row, 0)
            if item_0:
                item_0.setForeground(
                    RARITY_COLORS.get(rarity, DEFAULT_ITEM_COLOR)
                )

            diff_item = self.tracker_table.item(row, 3)
            if diff_item and diff > 0:
                diff_item.setForeground(Qt.GlobalColor.yellow)
        self.tracker_table.blockSignals(False)


# ============================================================================
# Entry Point
# ============================================================================


def main():
    logging.basicConfig()
    run_migrations()
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
