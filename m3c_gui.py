#!/usr/bin/env python3
"""Never make me write frontend again.

Put this next to m3c.py and run it:

    pip install PySide6
    python3 m3c_gui.py
"""

import os
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox,
    QPushButton, QSpinBox, QSplitter, QStyle, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m3c  # noqa: E402
from m3c_preview import PreviewPanel  # noqa: E402


class NoFocusDelegate(QStyledItemDelegate):

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.state &= ~QStyle.State_HasFocus


def human(n):
    return "%s bytes" % f"{n:,}"


class SlotDialog(QDialog):
    # Asks which slot an incoming camera should land in

    def __init__(self, parent, cam, used, capacity):
        super().__init__(parent)
        self.setWindowTitle("Inject camera")
        self.setMinimumWidth(380)

        self.spin = QSpinBox()
        self.spin.setRange(0, max(0, capacity - 1))
        self.spin.setValue(cam.slot)
        self.spin.valueChanged.connect(self._describe)

        self.note = QLabel()
        self.note.setWordWrap(True)
        self._used = dict(used)

        form = QFormLayout()
        form.addRow("Camera", QLabel("%d frames, from %s"
                                     % (cam.frames, cam.source or "unknown")))
        form.addRow("Slot", self.spin)
        form.addRow("", self.note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self._describe()

    def _describe(self):
        s = self.spin.value()
        label = m3c.slot_label(s)
        if s in self._used:
            self.note.setText("Slot %d holds %s, %d frames. It will be replaced."
                              % (s, label, self._used[s]))
        else:
            self.note.setText("Slot %d (%s) is empty." % (s, label))

    def slot(self):
        return self.spin.value()


class Window(QMainWindow):
    COLUMNS = ["Slot", "Guess", "Frames", "Size"]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Marvel 3 Camera Tool")
        self.resize(860, 660)
        self.setAcceptDrops(True)

        self.path = None
        self.version = 1
        self.capacity = 256
        self.cameras = []
        self.dirty = False

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setItemDelegate(NoFocusDelegate(self.table))
        self.table.itemSelectionChanged.connect(self._on_selection)

        self.btn_extract = QPushButton("Extract selected")
        self.btn_extract_all = QPushButton("Extract all")
        self.btn_inject = QPushButton("Inject camera")
        self.btn_remove = QPushButton("Remove selected")
        self.btn_extract.clicked.connect(self.extract_selected)
        self.btn_extract_all.clicked.connect(self.extract_all)
        self.btn_inject.clicked.connect(self.inject)
        self.btn_remove.clicked.connect(self.remove_selected)

        row = QHBoxLayout()
        for b in (self.btn_extract, self.btn_extract_all,
                  self.btn_inject, self.btn_remove):
            row.addWidget(b)

        self.hint = QLabel("Open a .lmcm, or drag one onto this window.")
        self.hint.setAlignment(Qt.AlignCenter)

        self.preview = PreviewPanel()

        top = QWidget()
        top_box = QVBoxLayout(top)
        top_box.setContentsMargins(0, 0, 0, 0)
        top_box.addWidget(self.hint)
        top_box.addWidget(self.table)
        top_box.addLayout(row)

        split = QSplitter(Qt.Vertical)
        split.addWidget(top)
        split.addWidget(self.preview)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([220, 320])
        self.setCentralWidget(split)

        self._build_menu()
        self._sync_buttons()
        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------- plumbing

    def _build_menu(self):
        f = self.menuBar().addMenu("&File")
        for text, slot, key in (
            ("&Open...", self.open_file, QKeySequence.Open),
            ("&Save", self.save, QKeySequence.Save),
            ("Save &As...", self.save_as, QKeySequence.SaveAs),
        ):
            act = QAction(text, self)
            act.setShortcut(key)
            act.triggered.connect(slot)
            f.addAction(act)
        f.addSeparator()
        act = QAction("&Quit", self)
        act.setShortcut(QKeySequence.Quit)
        act.triggered.connect(self.close)
        f.addAction(act)

    def _on_selection(self):
        self._sync_buttons()
        rows = self.selected_rows()
        self.preview.set_camera(self.cameras[rows[0]] if rows else None)

    def _sync_buttons(self):
        loaded = self.path is not None
        picked = bool(self.table.selectionModel()
                      and self.table.selectionModel().selectedRows())
        self.btn_extract.setEnabled(loaded and picked)
        self.btn_remove.setEnabled(loaded and picked)
        self.btn_extract_all.setEnabled(loaded and bool(self.cameras))
        self.btn_inject.setEnabled(loaded)

    def _mark_dirty(self, on=True):
        self.dirty = on
        name = os.path.basename(self.path) if self.path else "no file"
        self.setWindowTitle("Marvel 3 Camera Tool  -  %s%s"
                            % (name, " *" if on else ""))

    def _fail(self, what, err):
        traceback.print_exc()
        QMessageBox.critical(self, what, str(err))

    def selected_rows(self):
        return sorted(i.row() for i in
                      self.table.selectionModel().selectedRows())

    # -------------------------------------------------------------- actions

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].toLocalFile().lower().endswith((".lmcm", ".m3c")):
            event.acceptProposedAction()

    def dropEvent(self, event):
        p = event.mimeData().urls()[0].toLocalFile()
        if p.lower().endswith(".lmcm"):
            self.load(p)
        elif self.path:
            self.inject(p)
        else:
            QMessageBox.information(self, "Open a .lmcm first",
                                    "Load an .lmcm before dropping a camera in.")

    def open_file(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Open camera file", "", "Marvel 3 cameras (*.lmcm)")
        if p:
            self.load(p)

    def load(self, path):
        try:
            version, capacity, cams = m3c.read_lmcm(path)
        except Exception as e:
            return self._fail("Could not read that file", e)
        self.path, self.version, self.capacity = path, version, capacity
        self.cameras = cams
        self.refresh()
        if self.cameras:
            self.table.selectRow(0)
        self._mark_dirty(False)
        self.statusBar().showMessage(
            "%d cameras, %d frames total"
            % (len(cams), sum(c.frames for c in cams)))

    def refresh(self):
        self.cameras.sort(key=lambda c: c.slot)
        self.table.setRowCount(len(self.cameras))
        for r, c in enumerate(self.cameras):
            for col, text in enumerate((str(c.slot), m3c.slot_label(c.slot),
                                        str(c.frames), human(c.block_size))):
                item = QTableWidgetItem(text)
                if col != 1:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, col, item)
        self.hint.setText(os.path.basename(self.path) if self.path
                          else "Open a .lmcm, or drag one onto this window.")
        rows = self.selected_rows() if self.table.selectionModel() else []
        if not rows:
            self.preview.set_camera(None)
        self._sync_buttons()

    def extract_selected(self):
        rows = self.selected_rows()
        if not rows:
            return
        stem = os.path.splitext(os.path.basename(self.path))[0]
        if len(rows) == 1:
            c = self.cameras[rows[0]]
            suggested = "%s_slot%02d.m3c" % (stem, c.slot)
            p, _ = QFileDialog.getSaveFileName(
                self, "Save camera", suggested, "Single cameras (*.m3c)")
            if not p:
                return
            try:
                m3c.write_m3c(p, c)
            except Exception as e:
                return self._fail("Could not write that camera", e)
            self.statusBar().showMessage("Wrote %s" % os.path.basename(p))
            return

        folder = QFileDialog.getExistingDirectory(self, "Choose a folder")
        if not folder:
            return
        self._dump([self.cameras[r] for r in rows], folder, stem)

    def extract_all(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder")
        if not folder:
            return
        stem = os.path.splitext(os.path.basename(self.path))[0]
        self._dump(self.cameras, folder, stem)

    def _dump(self, cams, folder, stem):
        try:
            for c in cams:
                m3c.write_m3c(os.path.join(folder, "%s_slot%02d.m3c"
                                           % (stem, c.slot)), c)
        except Exception as e:
            return self._fail("Could not write those cameras", e)
        self.statusBar().showMessage("Wrote %d cameras to %s"
                                     % (len(cams), folder))

    def inject(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose a camera", "", "Single cameras (*.m3c)")
        if not path:
            return
        try:
            cam = m3c.read_m3c(path)
        except Exception as e:
            return self._fail("Could not read that camera", e)

        used = {c.slot: c.frames for c in self.cameras}
        dialog = SlotDialog(self, cam, used, self.capacity)
        if dialog.exec() != QDialog.Accepted:
            return

        cam.slot = dialog.slot()
        self.cameras = [c for c in self.cameras if c.slot != cam.slot] + [cam]
        self.refresh()
        for r, c in enumerate(self.cameras):
            if c.slot == cam.slot:
                self.table.selectRow(r)
                break
        self._mark_dirty()
        self.statusBar().showMessage("Slot %d now holds %d frames from %s"
                                     % (cam.slot, cam.frames,
                                        os.path.basename(path)))

    def remove_selected(self):
        rows = self.selected_rows()
        if not rows:
            return
        slots = [self.cameras[r].slot for r in rows]
        answer = QMessageBox.question(
            self, "Remove cameras",
            "Remove slot%s %s?\n\nCameras will not update until you save."
            % ("" if len(slots) == 1 else "s",
               ", ".join(str(s) for s in slots)))
        if answer != QMessageBox.Yes:
            return
        self.cameras = [c for c in self.cameras if c.slot not in slots]
        self.refresh()
        self._mark_dirty()
        self.statusBar().showMessage("Removed %d camera(s)" % len(slots))

    def save(self):
        if not self.path:
            return
        self._write(self.path)

    def save_as(self):
        if not self.path:
            return
        suggested = self.path.replace(".lmcm", "_patched.lmcm")
        p, _ = QFileDialog.getSaveFileName(
            self, "Save as", suggested, "Marvel 3 cameras (*.lmcm)")
        if p:
            self._write(p)

    def _write(self, path):
        if not self.cameras:
            QMessageBox.warning(self, "Nothing to save",
                                "This file has no cameras left in it.")
            return
        try:
            size = m3c.write_lmcm(path, self.version, self.capacity,
                                  self.cameras)
        except Exception as e:
            return self._fail("Could not save", e)
        self.path = path
        self._mark_dirty(False)
        self.statusBar().showMessage("Saved %s, %s"
                                     % (os.path.basename(path), human(size)))

    def closeEvent(self, event):
        if not self.dirty:
            return event.accept()
        answer = QMessageBox.question(
            self, "Unsaved changes", "Save before closing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if answer == QMessageBox.Save:
            self.save()
            event.accept()
        elif answer == QMessageBox.Discard:
            event.accept()
        else:
            event.ignore()


def selftest():
    # Window builder.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication([])
    w = Window()
    w.show()
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".lmcm"):
            w.load(arg)
            if not w.cameras:
                print("selftest: loaded %s but found no cameras" % arg)
                return 1
            w.table.selectRow(0)
            if w.preview.cam is None:
                print("selftest: preview did not pick up the camera")
                return 1
            print("selftest: %s, %d cameras, preview on slot %d"
                  % (os.path.basename(arg), len(w.cameras), w.preview.cam.slot))
    app.processEvents()
    print("selftest: ok")
    return 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    app = QApplication(sys.argv)
    w = Window()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".lmcm"):
        w.load(sys.argv[1])
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
