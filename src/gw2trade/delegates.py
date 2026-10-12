import typing
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QSpinBox, QStyledItemDelegate


class SpinBoxDelegate(QStyledItemDelegate):

    def __init__(
        self,
        min_val: int = 0,
        max_val: int = 1_000_000,
        step: int = 1,
        parent=None,
    ):
        super().__init__(parent)
        self.min_val = min_val
        self.max_val = max_val
        self.step = step

    def createEditor(self, parent, option, index):
        editor = QSpinBox(parent)
        editor.setRange(self.min_val, self.max_val)
        editor.setSingleStep(self.step)
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return editor

    def setEditorData(self, editor, index):
        # Read the current integer value from the cell
        value = index.data(Qt.ItemDataRole.EditRole)
        try:
            editor.setValue(int(value))
        except (ValueError, TypeError):
            editor.setValue(0)

    def setModelData(self, editor, model, index):
        # Commit the new spinbox value back to the table model
        model.setData(index, str(editor.value()), Qt.ItemDataRole.EditRole)


class CraftDelegate(QStyledItemDelegate):
    """In-table combobox editor for manually selecting or typing a craft."""

    def __init__(self, disciplines: list[str], parent=None):
        super().__init__(parent)
        self.disciplines = disciplines

    @typing.override
    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.setEditable(True)
        combo.addItems(self.disciplines)
        return combo

    @typing.override
    def setEditorData(self, editor, index):
        text = index.data(Qt.ItemDataRole.DisplayRole) or "Unassigned"
        idx = editor.findText(text)
        if idx >= 0:
            editor.setCurrentIndex(idx)
        else:
            editor.setEditText(text)

    @typing.override
    def setModelData(self, editor, model, index):
        val = editor.currentText().strip() or "Unassigned"
        model.setData(index, val, Qt.ItemDataRole.EditRole)
