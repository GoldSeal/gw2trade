from const import CRAFTING_DISCIPLINES
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
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
