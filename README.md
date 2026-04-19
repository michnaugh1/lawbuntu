# Ubuntu Lawyers

A suite of Ubuntu/GNOME-native tools for solo and small-firm attorneys. Built to fill the gap left by legal software that assumes macOS or Windows.

---

## Tools

### PDF OCR — Make Searchable

Make a folder of scanned PDFs text-searchable in one click. Uses [ocrmypdf](https://ocrmypdf.readthedocs.io/) and Tesseract under the hood.

**Features:**
- Select any folder (with optional subdirectory recursion)
- Processes PDFs in-place — no duplicate files to manage
- Skips files that are already searchable
- Auto-rotate pages option for mis-scanned documents
- Plain-English progress and summary — no terminal output exposed
- Graceful handling of password-protected or damaged files

**Screenshot:**

![PDF OCR app icon](assets/ocr-pdfs.svg)

---

## Requirements

- Ubuntu 22.04+ with GNOME
- Python 3.10+
- `ocrmypdf` and `tesseract-ocr`

```bash
sudo apt install ocrmypdf tesseract-ocr
```

For additional OCR languages (e.g. Spanish):

```bash
sudo apt install tesseract-ocr-spa
```

---

## Installation

### Option 1: Snap (recommended)

Build and install locally:

```bash
git clone https://github.com/YOUR_USERNAME/ubuntu-lawyers.git
cd ubuntu-lawyers
snapcraft
sudo snap install ocr-pdfs_1.0.0_amd64.snap --dangerous --classic
```

> Once published to the Snap Store, this will simply be:
> `sudo snap install ocr-pdfs`

### Option 2: Install from source

Clone the repository and run the installer:

```bash
git clone https://github.com/YOUR_USERNAME/ubuntu-lawyers.git
cd ubuntu-lawyers
bash tools/install.sh
```

The app installs per-user (no `sudo` required) and appears in your GNOME application menu as **"PDF OCR — Make Searchable"**.

### Uninstall

**Snap:**
```bash
sudo snap remove ocr-pdfs
```

**Source install:**
```bash
bash tools/install.sh --uninstall
```

---

## CLI Usage

A command-line version is also available for scripting or server use:

```bash
# OCR all PDFs in a folder (in-place)
python3 tools/ocr_pdfs.py /path/to/folder

# Include subfolders
python3 tools/ocr_pdfs.py /path/to/folder --recursive

# Auto-rotate pages
python3 tools/ocr_pdfs.py /path/to/folder --rotate

# Different language
python3 tools/ocr_pdfs.py /path/to/folder -l spa
```

---

## Development

```bash
# Run tests
python3 -m pytest tests/ -v

# Run the GUI directly (requires a display)
python3 tools/ocr_pdfs_gui.py
```

### Project Structure

```
tools/
  ocr_pdfs.py          # CLI batch OCR tool
  ocr_pdfs_gui.py      # GTK 3 GUI application
  ocr_pdfs_gui.desktop # GNOME launcher entry (template)
  install.sh           # Per-user install / uninstall
assets/
  ocr-pdfs.svg         # Application icon
tests/
  test_ocr_worker.py   # Unit tests for OCR worker functions
docs/
  superpowers/
    specs/             # Design specifications
    plans/             # Implementation plans
```

---

## Roadmap

- [x] Snap packaging for easy installation by other attorneys
- [ ] Language selection in the GUI
- [ ] Additional tools (time tracking, invoice generation)

---

## License

MIT — free to use, modify, and distribute. Contributions welcome.

---

*Built for attorneys running Ubuntu. If you find it useful, please share it with colleagues.*
