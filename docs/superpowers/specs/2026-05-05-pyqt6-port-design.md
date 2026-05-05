# PyQt6 Port Design — ocr-pdfs-kde

**Date:** 2026-05-05
**Status:** Approved

## Overview

Port the existing GTK3 `ocr-pdfs` snap to PyQt6 as a separate snap named `ocr-pdfs-kde`, targeting KDE Plasma users. Both snaps coexist in the same repository. The OCR backend is shared between both GUIs via a new common module.

## Goals

- Native-looking Qt app on KDE Plasma
- Identical functionality to the GTK version
- Plasma desktop notification on OCR completion
- Self-contained snap (`ocr-pdfs-kde`) published to the Snap Store separately

## Non-Goals

- Replacing the GTK snap
- Adding features beyond what the GTK version has (except the notification)
- KDE Frameworks (PyKF6) integration — PyQt6 only

## File Changes

### New files

| File | Purpose |
|---|---|
| `tools/ocr_backend.py` | Shared OCR backend: `process_pdf`, `find_pdfs`, `check_ocrmypdf_installed` |
| `tools/ocr_pdfs_qt.py` | PyQt6 GUI application |
| `snap/snapcraft-kde.yaml` | Snap configuration for `ocr-pdfs-kde` |
| `snap/local/launcher-kde` | Launcher script with env var setup for Qt snap |

### Modified files

| File | Change |
|---|---|
| `tools/ocr_pdfs_gui.py` | Replace inline backend definitions with `from ocr_backend import ...` |
| `tools/ocr_pdfs.py` | Replace inline backend definitions with `from ocr_backend import ...` |

## Architecture

### Shared Backend (`tools/ocr_backend.py`)

Extracted from `ocr_pdfs_gui.py` with no behaviour changes:

- `find_pdfs(directory, recursive=True) -> list[Path]`
- `check_ocrmypdf_installed() -> bool`
- `process_pdf(pdf_path, language='eng', rotate=False) -> dict`

Both `ocr_pdfs_gui.py` and `ocr_pdfs_qt.py` import from this module. `ocr_pdfs.py` (CLI tool) does the same.

### PyQt6 GUI (`tools/ocr_pdfs_qt.py`)

**Window:** `QMainWindow`, fixed width 500px, non-resizable. Single central `QWidget` with `QVBoxLayout` (margins 20px, spacing 14px).

**Widgets:**
- `QLabel` "Folder to Process" — dim secondary style
- `QHBoxLayout`: `QLineEdit` (read-only, placeholder "Select a folder…") + `QPushButton` "Browse…"
- `QHBoxLayout`: `QCheckBox` "Include subfolders" (checked by default) + `QCheckBox` "Auto-rotate pages" (unchecked)
- `QPushButton` "Make PDFs Searchable" — full width, KDE Breeze accent (`#0057ae`), disabled until folder selected
- `QProgressBar` — hidden until processing starts, shows "Processing N of M: filename.pdf"
- `QLabel` summary — hidden until processing completes, shows counts and any errors

**Threading:** `OcrWorker(QObject)` runs in a `QThread`. Signals:
- `progress = pyqtSignal(int, int, str)` — current, total, filename
- `finished = pyqtSignal(list, list, list)` — ok, skipped, errors

Main window connects these signals to UI update slots via Qt's queued connection (thread-safe, replaces `GLib.idle_add`).

**Notifications:** On `finished`, calls `QSystemTrayIcon.showMessage(title, body, icon, duration)` with a summary line (e.g., "5 PDFs made searchable, 2 skipped"). The tray icon uses `QIcon` loaded from `assets/ocr-pdfs.svg` (same asset as the GNOME snap). Degrades silently if system tray is unavailable.

**Missing dependency dialog:** `QMessageBox.critical()` shown on startup if `ocrmypdf` is not found on PATH.

## Snap Configuration (`snap/snapcraft-kde.yaml`)

```
name: ocr-pdfs-kde
version: '1.0.0'
base: core24
confinement: strict
grade: stable
```

- Extension: `kde-neon` (provides Qt/KDE platform runtime). If `kde-neon` is unavailable for core24 at build time, fall back to no extension and bundle Qt platform plugins via stage-packages (`qt6-qpa-plugins`).
- Plugs: `home`
- Stage-packages: `python3-pyqt6`, `ocrmypdf`, `tesseract-ocr`, `tesseract-ocr-eng`, `poppler-utils`
- Organizes `tools/ocr_backend.py`, `tools/ocr_pdfs_qt.py`, `snap/local/launcher-kde`

## Launcher (`snap/local/launcher-kde`)

Same environment variable setup as `launcher`:
- `PYTHONPATH=$SNAP/usr/lib/python3/dist-packages`
- `TESSDATA_PREFIX` — dynamically resolved from `$SNAP/usr/share/tesseract-ocr/`
- `GS_LIB` — dynamically resolved from `$SNAP/usr/share/ghostscript/` (numeric dirs only)

Executes: `python3 $SNAP/ocr_pdfs_qt.py`

## UI States

| State | Progress bar | Summary panel | Start button | Browse button |
|---|---|---|---|---|
| No folder selected | Hidden | Hidden | Disabled | Enabled |
| Folder selected, idle | Hidden | Hidden | Enabled | Enabled |
| Processing | Visible | Hidden | Disabled | Disabled |
| Complete | Visible (Done) | Visible | Enabled | Enabled |

## Testing

Existing tests in `tests/test_ocr_worker.py` test the backend functions directly and continue to work unchanged once the backend is extracted to `ocr_backend.py`. No new GUI tests are required — the backend is the testable logic, and the Qt GUI is a thin wrapper over it.
