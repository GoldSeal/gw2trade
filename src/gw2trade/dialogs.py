from const import CRAFTING_DISCIPLINES
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
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
            self.note_input.text().strip(),
        )
