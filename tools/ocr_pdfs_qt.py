#!/usr/bin/env python3
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QLineEdit,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

from ocr_backend import check_ocrmypdf_installed, find_pdfs, process_pdf


class OcrWorker(QObject):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(list, list, list)

    def __init__(self, folder, recursive, rotate):
        super().__init__()
        self.folder = folder
        self.recursive = recursive
        self.rotate = rotate

    def run(self):
        pdfs = find_pdfs(self.folder, recursive=self.recursive)
        total = len(pdfs)
        ok, skipped, errors = [], [], []

        if total == 0:
            self.finished.emit([], [], [])
            return

        for i, pdf in enumerate(pdfs):
            self.progress.emit(i, total, pdf.name)
            result = process_pdf(pdf, rotate=self.rotate)
            if result["status"] == "ok":
                ok.append(pdf.name)
            elif result["status"] == "skipped":
                skipped.append(pdf.name)
            else:
                errors.append((pdf.name, result["message"]))

        self.finished.emit(ok, skipped, errors)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF OCR — Make Searchable")
        self.setFixedWidth(500)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        folder_label = QLabel("Folder to Process")
        folder_label.setStyleSheet("color: #888;")
        layout.addWidget(folder_label)

        folder_row = QHBoxLayout()
        self.folder_entry = QLineEdit()
        self.folder_entry.setPlaceholderText("Select a folder…")
        self.folder_entry.setReadOnly(True)
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(self._on_browse)
        folder_row.addWidget(self.folder_entry)
        folder_row.addWidget(self.browse_btn)
        layout.addLayout(folder_row)

        options_row = QHBoxLayout()
        self.recursive_check = QCheckBox("Include subfolders")
        self.recursive_check.setChecked(True)
        self.rotate_check = QCheckBox("Auto-rotate pages")
        options_row.addWidget(self.recursive_check)
        options_row.addWidget(self.rotate_check)
        options_row.addStretch()
        layout.addLayout(options_row)

        self.start_btn = QPushButton("Make PDFs Searchable")
        self.start_btn.setEnabled(False)
        self.start_btn.setStyleSheet(
            "QPushButton { background: #0057ae; color: white; padding: 8px;"
            " border-radius: 4px; border: none; }"
            "QPushButton:disabled { background: #ccc; color: #888; border: none; }"
        )
        self.start_btn.clicked.connect(self._on_start)
        layout.addWidget(self.start_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.summary_label.hide()
        layout.addWidget(self.summary_label)

        icon_path = Path(__file__).parent.parent / "assets" / "ocr-pdfs.svg"
        self._tray = QSystemTrayIcon(QIcon(str(icon_path)), self)

        self._thread = None
        self._worker = None

        if not check_ocrmypdf_installed():
            self._show_missing_dependency_dialog()

    def _on_browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder", str(Path.home())
        )
        if folder:
            self.folder_entry.setText(folder)
            self.start_btn.setEnabled(True)
            self.summary_label.hide()

    def _on_start(self):
        folder = self.folder_entry.text()
        if not folder:
            return

        self.start_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.summary_label.hide()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Finding PDFs…")
        self.progress_bar.show()

        self._worker = OcrWorker(
            folder,
            self.recursive_check.isChecked(),
            self.rotate_check.isChecked(),
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_progress(self, current, total, filename):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(
            f"Processing {current + 1} of {total}: {filename}"
        )

    def _on_finished(self, ok, skipped, errors):
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(100)
        self.progress_bar.setFormat("Done")

        lines = []
        if ok:
            lines.append(f"✅  {len(ok)} PDF{'s' if len(ok) != 1 else ''} made searchable")
        if skipped:
            lines.append(f"⏭  {len(skipped)} already searchable, skipped")
        if not ok and not skipped and not errors:
            lines.append("No PDF files were found in the selected folder.")
        if errors:
            lines.append("⚠  Could not process:")
            for name, msg in errors:
                lines.append(f"   • {name} — {msg}")

        self.summary_label.setText("\n".join(lines))
        self.summary_label.show()
        self.start_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)

        if QSystemTrayIcon.isSystemTrayAvailable():
            parts = []
            if ok:
                parts.append(f"{len(ok)} PDF{'s' if len(ok) != 1 else ''} made searchable")
            if skipped:
                parts.append(f"{len(skipped)} skipped")
            if errors:
                parts.append(f"{len(errors)} error{'s' if len(errors) != 1 else ''}")
            body = ", ".join(parts) if parts else "No PDFs found"
            self._tray.show()
            self._tray.showMessage(
                "PDF OCR Complete",
                body,
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )

    def _show_missing_dependency_dialog(self):
        QMessageBox.critical(
            self,
            "ocrmypdf is not installed",
            "This tool requires ocrmypdf. Install it by running:\n\n"
            "    sudo apt install ocrmypdf\n\n"
            "Then restart the application.",
        )
        self.start_btn.setEnabled(False)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PDF OCR — Make Searchable")
    window = MainWindow()
    window.show()
    result = app.exec()
    sys.exit(result)


if __name__ == "__main__":
    main()
