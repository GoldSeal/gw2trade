from datetime import datetime
from typing import Any

from const import CRAFTING_DISCIPLINES, format_coins
from models import HistoricTransaction, Item, ReListing
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class AddUserDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
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
        craft_options: list[str] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add Wanted Item")
        self.resize(320, 160)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Item ID (GW2 IDs can reach up to ~150,000+)
        self.item_id_spin = QSpinBox()
        self.item_id_spin.setRange(1, 999_999)
        # self.item_id_spin.setValue(1)

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
        self.note2_input = QLineEdit()
        self.note2_input.setPlaceholderText("Optional second note...")

        form.addRow("Item ID:", self.item_id_spin)
        form.addRow("Listing Type:", self.type_combo)
        form.addRow("Craft Partition:", self.craft_combo)
        form.addRow("Wanted Quantity:", self.qty_spin)
        form.addRow("Note:", self.note_input)
        form.addRow("Note 2:", self.note2_input)
        layout.addLayout(form)

        # OK / Cancel buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def get_data(self) -> tuple[int, str, int, str, str, str]:
        return (
            self.item_id_spin.value(),
            self.type_combo.currentText().lower(),
            self.qty_spin.value(),
            self.craft_combo.currentText().strip() or "Unassigned",
            self.note_input.text().strip(),
            self.note2_input.text().strip(),
        )


class SettingsDialog(QDialog):
    def __init__(
        self,
        cutoff_date: QDate,
        theme: str,
        craft_order: list[str] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(400, 420)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.cutoff_edit = QDateEdit()
        self.cutoff_edit.setCalendarPopup(True)
        self.cutoff_edit.setDisplayFormat("yyyy-MM-dd")
        self.cutoff_edit.setDate(cutoff_date)
        self.cutoff_edit.setToolTip(
            "Only historic sales on or after this date count toward Sold."
        )

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.setCurrentText(
            "Light" if theme.lower() == "light" else "Dark"
        )

        form.addRow("Historic sales cutoff:", self.cutoff_edit)
        form.addRow("Theme:", self.theme_combo)
        layout.addLayout(form)

        layout.addWidget(QLabel("Section order (drag or use buttons):"))

        order_row = QHBoxLayout()
        self.craft_list = QListWidget()
        self.craft_list.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
        )
        self.craft_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.craft_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        for name in craft_order or list(CRAFTING_DISCIPLINES):
            self.craft_list.addItem(QListWidgetItem(name))
        order_row.addWidget(self.craft_list)

        btn_col = QVBoxLayout()
        self.btn_move_up = QPushButton("Move Up")
        self.btn_move_up.clicked.connect(self._move_selected_up)
        self.btn_move_down = QPushButton("Move Down")
        self.btn_move_down.clicked.connect(self._move_selected_down)
        self.btn_reset_order = QPushButton("Reset")
        self.btn_reset_order.setToolTip("Restore default craft section order")
        self.btn_reset_order.clicked.connect(self._reset_craft_order)
        btn_col.addWidget(self.btn_move_up)
        btn_col.addWidget(self.btn_move_down)
        btn_col.addWidget(self.btn_reset_order)
        btn_col.addStretch()
        order_row.addLayout(btn_col)
        layout.addLayout(order_row)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _selected_row(self) -> int:
        item = self.craft_list.currentItem()
        if item is None:
            return -1
        return self.craft_list.row(item)

    def _move_selected_up(self):
        row = self._selected_row()
        if row <= 0:
            return
        item = self.craft_list.takeItem(row)
        self.craft_list.insertItem(row - 1, item)
        self.craft_list.setCurrentRow(row - 1)

    def _move_selected_down(self):
        row = self._selected_row()
        if row < 0 or row >= self.craft_list.count() - 1:
            return
        item = self.craft_list.takeItem(row)
        self.craft_list.insertItem(row + 1, item)
        self.craft_list.setCurrentRow(row + 1)

    def _reset_craft_order(self):
        self.craft_list.clear()
        for name in CRAFTING_DISCIPLINES:
            self.craft_list.addItem(QListWidgetItem(name))

    def get_craft_order(self) -> list[str]:
        return [
            self.craft_list.item(i).text()
            for i in range(self.craft_list.count())
        ]

    def get_data(self) -> tuple[QDate, str, list[str]]:
        theme = self.theme_combo.currentText().lower()
        return self.cutoff_edit.date(), theme, self.get_craft_order()


class ItemHistoryDialog(QDialog):
    def __init__(
        self,
        item_id: int,
        listing_type: str,
        item_data: Item | None,
        historic_txs: list[HistoricTransaction],
        relistings: list[ReListing],
        icon_cache=None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        item_name = item_data.name if item_data else f"Item #{item_id}"
        self.setWindowTitle(f"History: {item_name} (ID: {item_id})")
        self.resize(750, 480)

        layout = QVBoxLayout(self)

        # Header info
        header_layout = QHBoxLayout()
        if item_data and item_data.icon and icon_cache:
            pixmap = icon_cache.load_icon(item_id, item_data.icon)
            if pixmap:
                icon_lbl = QLabel()
                icon_lbl.setPixmap(
                    pixmap.scaled(
                        36,
                        36,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                header_layout.addWidget(icon_lbl)

        info_lbl = QLabel(
            f"<b>{item_name}</b> (ID: {item_id}) &mdash; Type: <b>{listing_type.upper()}</b>"
        )
        header_layout.addWidget(info_lbl)
        header_layout.addStretch()

        sold_total = sum(tx.quantity for tx in historic_txs)
        relist_total = sum(r.quantity for r in relistings)
        summary_lbl = QLabel(
            f"Total Sold: <b>{sold_total}</b> | Total Re-Listed: <b>{relist_total}</b>"
        )
        header_layout.addWidget(summary_lbl)
        layout.addLayout(header_layout)

        # Merge and sort events chronologically descending
        events = []
        for h in historic_txs:
            dt = self._parse_dt(h.purchased)
            events.append(
                {
                    "type": "Sold",
                    "datetime": dt,
                    "quantity": h.quantity,
                    "price": h.price,
                    "listing_type": h.listing_type,
                }
            )
        for r in relistings:
            dt = self._parse_dt(r.created)
            events.append(
                {
                    "type": "Re-Listing",
                    "datetime": dt,
                    "quantity": r.quantity,
                    "price": r.price,
                    "listing_type": r.listing_type,
                }
            )

        events.sort(key=lambda e: e["datetime"], reverse=True)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            [
                "Action",
                "Date / Time",
                "Quantity",
                "Unit Price",
                "Total Amount",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setRowCount(len(events))

        for row, ev in enumerate(events):
            # Action
            act_item = QTableWidgetItem(ev["type"])
            act_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            act_item.setFlags(act_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if ev["type"] == "Sold":
                act_item.setForeground(QColor("#4caf50"))
            else:
                act_item.setForeground(QColor("#2196f3"))
            self.table.setItem(row, 0, act_item)

            # Date / Time
            dt_str = (
                ev["datetime"].strftime("%Y-%m-%d %H:%M:%S")
                if ev["datetime"] != datetime.min
                else "—"
            )
            dt_item = QTableWidgetItem(dt_str)
            dt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            dt_item.setFlags(dt_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, dt_item)

            # Quantity
            qty_item = QTableWidgetItem(str(ev["quantity"]))
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            qty_item.setFlags(qty_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, qty_item)

            # Unit Price
            price_item = QTableWidgetItem(format_coins(ev["price"]))
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            price_item.setFlags(
                price_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            self.table.setItem(row, 3, price_item)

            # Total Amount
            total_item = QTableWidgetItem(
                format_coins(ev["price"] * ev["quantity"])
            )
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            total_item.setFlags(
                total_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            self.table.setItem(row, 4, total_item)

        layout.addWidget(self.table)

        # Close button
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    @staticmethod
    def _parse_dt(val: Any) -> datetime:
        if isinstance(val, datetime):
            return val
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val)
            except ValueError:
                pass
            for fmt in (
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ):
                try:
                    return datetime.strptime(val, fmt)
                except ValueError:
                    pass
        return datetime.min
