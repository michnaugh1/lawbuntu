# PDF OCR GUI — Design Spec

**Date:** 2026-04-18
**Project:** Ubuntu_Lawyers (tool #2 in the attorney suite)
**Status:** Approved design, ready for implementation planning

## 1. Overview

A GTK desktop application that allows non-technical attorneys to make a folder of PDF files text-searchable using `ocrmypdf`. The app appears in the GNOME application menu, requires no terminal interaction, and is designed to eventually be distributed as a Snap or Flatpak package for other attorneys.

## 2. Goals & Non-Goals

**Goals**

- Allow attorneys to select a folder and OCR all PDFs in it with one click
- Modify PDFs in-place (no separate output folder to manage)
- Skip files that already have a text layer (no redundant processing)
- Show clear, plain-English progress and results
- Install per-user with no `sudo` required
- Code structured cleanly for future Snap/Flatpak packaging

**Non-goals (V1)**

- Language selection (defaults to English; designed so a dropdown can be added later without refactoring)
- Snap/Flatpak packaging (future milestone)
- Batch profiles or saved settings
- Multi-folder selection
- Cloud storage / network paths

## 3. Users & Context

Primary user: solo or small-firm attorney on Ubuntu/GNOME who receives scanned PDFs (court documents, exhibits, correspondence) and needs them to be text-searchable for Ctrl+F, copy-paste, and full-text indexing in their document management system.

The user is non-technical. The app must never expose terminal output, exit codes, or `ocrmypdf` internals directly.

## 4. Files

| File | Location | Purpose |
|------|----------|---------|
| `tools/ocr_pdfs_gui.py` | repo | GTK application |
| `tools/ocr_pdfs_gui.desktop` | repo | GNOME launcher entry |
| `tools/install.sh` | repo | Per-user installer / uninstaller |
| `tools/ocr_pdfs.py` | repo | Existing CLI script (unchanged) |

## 5. Application UI

Single-window application. No tabs or wizard steps. Window title: **"PDF OCR — Make Searchable"**.

Layout (top to bottom):

1. **Folder selector** — text field showing chosen path + "Browse…" button opening a native GTK folder chooser dialog
2. **Options row** — two checkboxes:
   - "Include subfolders" — checked by default
   - "Auto-rotate pages" — unchecked by default
3. **"Make PDFs Searchable" button** — full-width; disabled while processing is running
4. **Progress bar** — hidden until processing starts; label shows e.g. "Processing 12 of 15 files…"
5. **Summary panel** — appears only after processing completes:
   - Files successfully processed (count)
   - Files skipped — already searchable (count)
   - Files with errors — listed by filename with a plain-English reason

## 6. Processing Architecture

- OCR runs in a **background thread** (not a subprocess of the GUI thread) so the UI stays responsive
- The worker calls `ocrmypdf` via `subprocess` with `--skip-text --quiet -l eng`
- Progress updates are sent to the GTK main thread via `GLib.idle_add`
- Each file is written to a temp file first; on success the temp file replaces the original (safe — originals are never modified if `ocrmypdf` fails)
- Processing continues through all files even if individual files fail

## 7. Error Handling

| Situation | Behavior |
|-----------|----------|
| `ocrmypdf` not installed | Dialog on launch: plain-English message + install command |
| No folder selected when button clicked | Button remains disabled until a folder is chosen |
| File is password-protected or damaged | Listed in summary: "Could not process — file may be damaged or password-protected" |
| File already searchable | Listed in summary as skipped (not an error) |
| Folder becomes unavailable mid-run | Remaining files listed as errors in summary |

## 8. Installation

`install.sh` behavior:

- **Default:** copies `ocr_pdfs_gui.py` → `~/.local/share/ocr-pdfs/` and `ocr_pdfs_gui.desktop` → `~/.local/share/applications/`; runs `update-desktop-database ~/.local/share/applications`
- **`--uninstall` flag:** removes both installed files and runs `update-desktop-database`
- No `sudo` required — per-user install only
- The `.desktop` file sets `Exec` to the absolute installed path of `ocr_pdfs_gui.py`

## 9. Future Considerations

- **Language selection:** add a dropdown above the options row; pass selected language code as `-l` to `ocrmypdf`. The worker already accepts a language parameter — only the UI needs to change.
- **Snap/Flatpak packaging:** the per-user install structure and clean path handling are designed with this in mind. `ocrmypdf` and its Tesseract dependency will need to be bundled in the package manifest.
- **Open source distribution:** target GitHub release with Snap Store listing once packaging is complete.
- **Custom app icon:** V1 uses the standard `document-open` system icon. A custom icon (`.svg`) should be designed before Snap Store submission.
