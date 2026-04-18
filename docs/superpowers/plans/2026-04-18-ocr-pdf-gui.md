# PDF OCR GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GTK 3 desktop application that lets attorneys select a folder and OCR all PDFs in it in-place, with progress feedback and a plain-English summary, installed via a per-user script into the GNOME application menu.

**Architecture:** Single Python file (`ocr_pdfs_gui.py`) containing OCR worker functions at module level (importable without a display server) followed by the `OcrApp` GTK class. A background `threading.Thread` runs the OCR batch; `GLib.idle_add` delivers all UI updates back to the GTK main thread safely. A `.desktop` file and `install.sh` handle per-user GNOME integration.

**Tech Stack:** Python 3, PyGObject (GTK 3), ocrmypdf (system binary via subprocess), threading, unittest / unittest.mock

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `conftest.py` | Create | Add project root to sys.path for pytest imports |
| `tools/__init__.py` | Create | Make tools/ a Python package so tests can import from it |
| `tools/ocr_pdfs_gui.py` | Create | GTK app + all OCR worker functions |
| `tools/ocr_pdfs_gui.desktop` | Create | GNOME launcher entry |
| `tools/install.sh` | Create | Per-user install / uninstall script |
| `tests/__init__.py` | Create | Make tests/ a Python package |
| `tests/test_ocr_worker.py` | Create | Unit tests for the three worker functions |

---

### Task 1: Create test scaffolding and test find_pdfs()

**Files:**
- Create: `conftest.py`
- Create: `tools/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_ocr_worker.py`

- [ ] **Step 1: Create conftest.py at project root**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
```

- [ ] **Step 2: Create empty package markers**

Create `tools/__init__.py` — empty file.
Create `tests/__init__.py` — empty file.

- [ ] **Step 3: Write failing tests for find_pdfs()**

Create `tests/test_ocr_worker.py`:

```python
import shutil
import tempfile
import unittest
from pathlib import Path


class TestFindPdfs(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _touch(self, rel):
        p = self.tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
        return p

    def test_finds_pdfs_in_flat_directory(self):
        self._touch('a.pdf')
        self._touch('b.pdf')
        self._touch('notes.txt')
        from tools.ocr_pdfs_gui import find_pdfs
        result = find_pdfs(self.tmp, recursive=False)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(p.suffix == '.pdf' for p in result))

    def test_recursive_finds_nested_pdfs(self):
        self._touch('top.pdf')
        self._touch('sub/nested.pdf')
        from tools.ocr_pdfs_gui import find_pdfs
        result = find_pdfs(self.tmp, recursive=True)
        self.assertEqual(len(result), 2)

    def test_non_recursive_skips_nested_pdfs(self):
        self._touch('top.pdf')
        self._touch('sub/nested.pdf')
        from tools.ocr_pdfs_gui import find_pdfs
        result = find_pdfs(self.tmp, recursive=False)
        self.assertEqual(len(result), 1)

    def test_returns_sorted_list(self):
        self._touch('z.pdf')
        self._touch('a.pdf')
        from tools.ocr_pdfs_gui import find_pdfs
        result = find_pdfs(self.tmp, recursive=False)
        names = [p.name for p in result]
        self.assertEqual(names, sorted(names))

    def test_empty_directory_returns_empty_list(self):
        from tools.ocr_pdfs_gui import find_pdfs
        self.assertEqual(find_pdfs(self.tmp, recursive=False), [])


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 4: Run tests to confirm they fail**

```bash
cd /home/michnaugh1/Dev/Ubuntu_Lawyers
python -m pytest tests/test_ocr_worker.py::TestFindPdfs -v
```

Expected: `ModuleNotFoundError` — `tools.ocr_pdfs_gui` doesn't exist yet.

- [ ] **Step 5: Create tools/ocr_pdfs_gui.py with just find_pdfs()**

```python
#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


# ---------------------------------------------------------------------------
# OCR Worker Functions — importable without a display server
# ---------------------------------------------------------------------------

def find_pdfs(directory, recursive=True):
    """Return a sorted list of Path objects for all PDFs in directory."""
    path = Path(directory)
    pattern = '**/*.pdf' if recursive else '*.pdf'
    return sorted(path.glob(pattern))
```

(Stop here — more functions and the GTK class are added in later tasks.)

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_ocr_worker.py::TestFindPdfs -v
```

Expected: 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add conftest.py tools/__init__.py tools/ocr_pdfs_gui.py tests/__init__.py tests/test_ocr_worker.py
git commit -m "feat: add find_pdfs() with tests and test scaffolding"
```

---

### Task 2: Test and implement check_ocrmypdf_installed()

**Files:**
- Modify: `tests/test_ocr_worker.py`
- Modify: `tools/ocr_pdfs_gui.py`

- [ ] **Step 1: Append tests to tests/test_ocr_worker.py**

Add this class before `if __name__ == '__main__':` (or at the end of the file if that line isn't there yet):

```python
class TestCheckOcrmypdfInstalled(unittest.TestCase):

    def test_returns_true_when_installed(self):
        from tools.ocr_pdfs_gui import check_ocrmypdf_installed
        self.assertTrue(check_ocrmypdf_installed())

    def test_returns_false_when_not_on_path(self):
        from unittest.mock import patch
        from tools.ocr_pdfs_gui import check_ocrmypdf_installed
        with patch('shutil.which', return_value=None):
            self.assertFalse(check_ocrmypdf_installed())
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_ocr_worker.py::TestCheckOcrmypdfInstalled -v
```

Expected: `AttributeError` — `check_ocrmypdf_installed` not defined.

- [ ] **Step 3: Add check_ocrmypdf_installed() to tools/ocr_pdfs_gui.py**

After the `find_pdfs` function, add:

```python
def check_ocrmypdf_installed():
    """Return True if ocrmypdf is available on PATH."""
    return shutil.which('ocrmypdf') is not None
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_ocr_worker.py::TestCheckOcrmypdfInstalled -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/ocr_pdfs_gui.py tests/test_ocr_worker.py
git commit -m "feat: add check_ocrmypdf_installed() with tests"
```

---

### Task 3: Test and implement process_pdf()

**Files:**
- Modify: `tests/test_ocr_worker.py`
- Modify: `tools/ocr_pdfs_gui.py`

- [ ] **Step 1: Append tests to tests/test_ocr_worker.py**

```python
class TestProcessPdf(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _make_pdf(self, name='test.pdf'):
        p = self.tmp / name
        p.write_bytes(b'%PDF-1.4 fake content')
        return p

    def test_returns_skipped_on_exit_code_6(self):
        from unittest.mock import patch, Mock
        from tools.ocr_pdfs_gui import process_pdf
        pdf = self._make_pdf()
        with patch('subprocess.run', return_value=Mock(returncode=6, stderr='')):
            result = process_pdf(pdf)
        self.assertEqual(result['status'], 'skipped')
        self.assertTrue(pdf.exists())

    def test_returns_ok_and_moves_temp_file_on_success(self):
        from unittest.mock import patch, Mock
        from tools.ocr_pdfs_gui import process_pdf
        pdf = self._make_pdf()

        def fake_run(cmd, **kwargs):
            Path(cmd[-1]).write_bytes(b'%PDF-1.4 ocr processed')
            return Mock(returncode=0, stderr='')

        with patch('subprocess.run', side_effect=fake_run):
            result = process_pdf(pdf)
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(pdf.exists())

    def test_returns_error_on_nonzero_exit(self):
        from unittest.mock import patch, Mock
        from tools.ocr_pdfs_gui import process_pdf
        pdf = self._make_pdf()
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr='unknown error')):
            result = process_pdf(pdf)
        self.assertEqual(result['status'], 'error')
        self.assertIn('message', result)
        self.assertTrue(pdf.exists())

    def test_error_message_mentions_password_when_encrypted(self):
        from unittest.mock import patch, Mock
        from tools.ocr_pdfs_gui import process_pdf
        pdf = self._make_pdf()
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr='encrypted password required')):
            result = process_pdf(pdf)
        self.assertIn('password', result['message'].lower())

    def test_error_message_mentions_damaged_when_invalid(self):
        from unittest.mock import patch, Mock
        from tools.ocr_pdfs_gui import process_pdf
        pdf = self._make_pdf()
        with patch('subprocess.run', return_value=Mock(returncode=1, stderr='not a pdf invalid format')):
            result = process_pdf(pdf)
        self.assertIn('damaged', result['message'].lower())
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_ocr_worker.py::TestProcessPdf -v
```

Expected: `AttributeError` — `process_pdf` not defined.

- [ ] **Step 3: Implement process_pdf() in tools/ocr_pdfs_gui.py**

After `check_ocrmypdf_installed()`, add:

```python
def process_pdf(pdf_path, language='eng', rotate=False):
    """
    Run ocrmypdf on a single PDF, replacing it in-place on success.

    Returns a dict: {'status': 'ok'|'skipped'|'error', 'message': str}
    Exit code 6 from ocrmypdf means all pages already had text (skip-text).
    """
    pdf_path = Path(pdf_path)
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp_path = Path(tmp.name)

    cmd = ['ocrmypdf', '--skip-text', '--quiet', '-l', language,
           str(pdf_path), str(tmp_path)]
    if rotate:
        cmd.insert(-2, '--rotate-pages')

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 6:
        tmp_path.unlink(missing_ok=True)
        return {'status': 'skipped', 'message': 'Already searchable'}
    elif result.returncode == 0:
        shutil.move(str(tmp_path), str(pdf_path))
        return {'status': 'ok', 'message': ''}
    else:
        tmp_path.unlink(missing_ok=True)
        stderr = result.stderr.strip().lower()
        if 'encrypt' in stderr or 'password' in stderr:
            msg = 'Could not process — file may be password-protected'
        elif 'invalid' in stderr or 'not a pdf' in stderr or 'damaged' in stderr:
            msg = 'Could not process — file may be damaged'
        else:
            msg = 'Could not process — unknown error'
        return {'status': 'error', 'message': msg}
```

- [ ] **Step 4: Run all worker tests**

```bash
python -m pytest tests/test_ocr_worker.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/ocr_pdfs_gui.py tests/test_ocr_worker.py
git commit -m "feat: add process_pdf() with tests"
```

---

### Task 4: Build the GTK application window

**Files:**
- Modify: `tools/ocr_pdfs_gui.py`

No unit tests for GTK widget construction — verified visually by running the app.

- [ ] **Step 1: Append the OcrApp class and entry point to tools/ocr_pdfs_gui.py**

Add everything below after the last worker function:

```python
# ---------------------------------------------------------------------------
# GTK Application
# ---------------------------------------------------------------------------

class OcrApp(Gtk.Application):

    def __init__(self):
        super().__init__(application_id='org.ubuntu-lawyers.ocr-pdfs')
        self.window = None

    def do_activate(self):
        if self.window:
            self.window.present()
            return

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title('PDF OCR \u2014 Make Searchable')
        self.window.set_default_size(500, -1)
        self.window.set_resizable(False)
        self.window.set_border_width(20)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.window.add(root)

        # --- Folder selector ---
        folder_label = Gtk.Label(label='Folder to Process', xalign=0)
        folder_label.get_style_context().add_class('dim-label')
        root.pack_start(folder_label, False, False, 0)

        folder_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.folder_entry = Gtk.Entry()
        self.folder_entry.set_placeholder_text('Select a folder\u2026')
        self.folder_entry.set_editable(False)
        self.folder_entry.set_hexpand(True)
        self.browse_btn = Gtk.Button(label='Browse\u2026')
        self.browse_btn.connect('clicked', self._on_browse)
        folder_row.pack_start(self.folder_entry, True, True, 0)
        folder_row.pack_start(self.browse_btn, False, False, 0)
        root.pack_start(folder_row, False, False, 0)

        # --- Options ---
        options_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        self.recursive_check = Gtk.CheckButton(label='Include subfolders')
        self.recursive_check.set_active(True)
        self.rotate_check = Gtk.CheckButton(label='Auto-rotate pages')
        self.rotate_check.set_active(False)
        options_row.pack_start(self.recursive_check, False, False, 0)
        options_row.pack_start(self.rotate_check, False, False, 0)
        root.pack_start(options_row, False, False, 0)

        # --- Start button ---
        self.start_btn = Gtk.Button(label='Make PDFs Searchable')
        self.start_btn.set_sensitive(False)
        self.start_btn.get_style_context().add_class('suggested-action')
        self.start_btn.connect('clicked', self._on_start)
        root.pack_start(self.start_btn, False, False, 0)

        # --- Progress bar (hidden until processing) ---
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.progress_bar.set_no_show_all(True)
        root.pack_start(self.progress_bar, False, False, 0)

        # --- Summary panel (hidden until done) ---
        self.summary_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.summary_box.set_no_show_all(True)

        self.summary_label = Gtk.Label(xalign=0)
        self.summary_label.set_line_wrap(True)
        self.summary_box.pack_start(self.summary_label, False, False, 0)

        self.error_label = Gtk.Label(xalign=0)
        self.error_label.set_line_wrap(True)
        self.error_label.set_selectable(True)
        self.error_label.set_no_show_all(True)
        self.summary_box.pack_start(self.error_label, False, False, 0)

        root.pack_start(self.summary_box, False, False, 0)

        self.window.show_all()

        if not check_ocrmypdf_installed():
            self._show_missing_dependency_dialog()

    def _on_browse(self, _btn):
        dialog = Gtk.FileChooserDialog(
            title='Select Folder',
            parent=self.window,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            'Select', Gtk.ResponseType.OK,
        )
        if dialog.run() == Gtk.ResponseType.OK:
            self.folder_entry.set_text(dialog.get_filename())
            self.start_btn.set_sensitive(True)
            self.summary_box.hide()
        dialog.destroy()

    def _on_start(self, _btn):
        folder = self.folder_entry.get_text()
        if not folder:
            return
        recursive = self.recursive_check.get_active()
        rotate = self.rotate_check.get_active()

        self.start_btn.set_sensitive(False)
        self.browse_btn.set_sensitive(False)
        self.summary_box.hide()
        self.progress_bar.set_fraction(0)
        self.progress_bar.set_text('Finding PDFs\u2026')
        self.progress_bar.show()

        threading.Thread(
            target=self._run_ocr_thread,
            args=(folder, recursive, rotate),
            daemon=True,
        ).start()

    def _run_ocr_thread(self, folder, recursive, rotate):
        pdfs = find_pdfs(folder, recursive=recursive)
        total = len(pdfs)

        if total == 0:
            GLib.idle_add(self._finish, [], [], [])
            return

        ok, skipped, errors = [], [], []
        for i, pdf in enumerate(pdfs):
            GLib.idle_add(self._update_progress, i, total, pdf.name)
            result = process_pdf(pdf, rotate=rotate)
            if result['status'] == 'ok':
                ok.append(pdf.name)
            elif result['status'] == 'skipped':
                skipped.append(pdf.name)
            else:
                errors.append((pdf.name, result['message']))

        GLib.idle_add(self._finish, ok, skipped, errors)

    def _update_progress(self, current, total, filename):
        self.progress_bar.set_fraction(current / total)
        self.progress_bar.set_text(f'Processing {current + 1} of {total}: {filename}')

    def _finish(self, ok, skipped, errors):
        self.progress_bar.set_fraction(1.0)
        self.progress_bar.set_text('Done')

        lines = []
        if ok:
            lines.append(f'\u2705  {len(ok)} PDF{"s" if len(ok) != 1 else ""} made searchable')
        if skipped:
            lines.append(f'\u23ed  {len(skipped)} already searchable, skipped')
        if not ok and not skipped and not errors:
            lines.append('No PDF files were found in the selected folder.')
        self.summary_label.set_text('\n'.join(lines))

        if errors:
            error_lines = ['\u26a0  Could not process:']
            for name, msg in errors:
                error_lines.append(f'   \u2022 {name} \u2014 {msg}')
            self.error_label.set_text('\n'.join(error_lines))
            self.error_label.show()
        else:
            self.error_label.hide()

        self.summary_box.show()
        self.start_btn.set_sensitive(True)
        self.browse_btn.set_sensitive(True)

    def _show_missing_dependency_dialog(self):
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text='ocrmypdf is not installed',
        )
        dialog.format_secondary_text(
            'This tool requires ocrmypdf. Install it by running:\n\n'
            '    sudo apt install ocrmypdf\n\n'
            'Then restart the application.'
        )
        dialog.run()
        dialog.destroy()
        self.start_btn.set_sensitive(False)


if __name__ == '__main__':
    app = OcrApp()
    sys.exit(app.run(sys.argv))
```

- [ ] **Step 2: Run the app and verify the window**

```bash
python3 tools/ocr_pdfs_gui.py
```

Verify:
- Window opens titled "PDF OCR — Make Searchable"
- Folder entry is empty with placeholder text
- Two checkboxes visible; "Include subfolders" is pre-checked
- "Make PDFs Searchable" button is greyed out
- "Browse…" opens a native folder picker
- Selecting a folder enables the start button
- Progress bar and summary panel are not visible at launch

- [ ] **Step 3: Confirm all unit tests still pass**

```bash
python -m pytest tests/ -v
```

Expected: all 12 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tools/ocr_pdfs_gui.py
git commit -m "feat: add GTK application window, layout, and worker thread wiring"
```

---

### Task 5: Create .desktop launcher file

**Files:**
- Create: `tools/ocr_pdfs_gui.desktop`

- [ ] **Step 1: Create the file**

```ini
[Desktop Entry]
Version=1.0
Type=Application
Name=PDF OCR — Make Searchable
Comment=Make a folder of PDF files text-searchable using OCR
Exec=python3 /usr/local/share/ocr-pdfs/ocr_pdfs_gui.py
Icon=document-open
Terminal=false
Categories=Office;Utility;
Keywords=PDF;OCR;searchable;text;scan;
StartupNotify=true
```

Save as `tools/ocr_pdfs_gui.desktop`.

Note: the `install.sh` (next task) rewrites the `Exec=` line to use the installing user's actual home path before copying.

- [ ] **Step 2: Validate the file**

```bash
desktop-file-validate tools/ocr_pdfs_gui.desktop
```

Expected: no output (no errors).

- [ ] **Step 3: Commit**

```bash
git add tools/ocr_pdfs_gui.desktop
git commit -m "feat: add GNOME .desktop launcher entry"
```

---

### Task 6: Create install.sh

**Files:**
- Create: `tools/install.sh`

- [ ] **Step 1: Create the script**

```bash
#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/ocr-pdfs"
DESKTOP_DIR="$HOME/.local/share/applications"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

uninstall() {
    echo "Uninstalling PDF OCR — Make Searchable..."
    rm -f "$INSTALL_DIR/ocr_pdfs_gui.py"
    rmdir --ignore-fail-on-non-empty "$INSTALL_DIR"
    rm -f "$DESKTOP_DIR/ocr_pdfs_gui.desktop"
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    echo "Done. The app has been removed from your application menu."
}

install() {
    echo "Installing PDF OCR — Make Searchable..."

    mkdir -p "$INSTALL_DIR"
    cp "$SCRIPT_DIR/ocr_pdfs_gui.py" "$INSTALL_DIR/ocr_pdfs_gui.py"
    chmod +x "$INSTALL_DIR/ocr_pdfs_gui.py"

    mkdir -p "$DESKTOP_DIR"
    sed "s|Exec=.*|Exec=python3 $INSTALL_DIR/ocr_pdfs_gui.py|" \
        "$SCRIPT_DIR/ocr_pdfs_gui.desktop" \
        > "$DESKTOP_DIR/ocr_pdfs_gui.desktop"

    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

    echo "Done. Search for 'PDF OCR' in your application menu."
}

case "${1:-install}" in
    --uninstall) uninstall ;;
    install|*)   install ;;
esac
```

Save as `tools/install.sh`.

- [ ] **Step 2: Make it executable**

```bash
chmod +x tools/install.sh
```

- [ ] **Step 3: Run install and verify**

```bash
bash tools/install.sh
```

Expected output:
```
Installing PDF OCR — Make Searchable...
Done. Search for 'PDF OCR' in your application menu.
```

Open the GNOME Activities overview, search "PDF OCR" — the app should appear. Launch it and verify it works correctly.

- [ ] **Step 4: Test uninstall**

```bash
bash tools/install.sh --uninstall
```

Expected:
```
Uninstalling PDF OCR — Make Searchable...
Done. The app has been removed from your application menu.
```

Verify `~/.local/share/applications/ocr_pdfs_gui.desktop` is gone and the app no longer appears in GNOME search.

- [ ] **Step 5: Reinstall for actual use**

```bash
bash tools/install.sh
```

- [ ] **Step 6: Commit**

```bash
git add tools/install.sh
git commit -m "feat: add per-user install/uninstall script"
```

---

### Task 7: End-to-end integration test

**Files:** none (manual verification)

- [ ] **Step 1: Run the full test suite**

```bash
cd /home/michnaugh1/Dev/Ubuntu_Lawyers
python -m pytest tests/ -v
```

Expected: all 12 tests PASS.

- [ ] **Step 2: Test with a real mixed folder of PDFs**

Prepare a test folder containing:
- At least 2 scanned PDFs with no text layer
- At least 1 PDF that is already searchable
- A subfolder containing 1 additional PDF

Launch from GNOME menu. Select the folder. Leave "Include subfolders" checked. Click "Make PDFs Searchable".

Verify:
- Progress bar updates per file (not frozen)
- Summary shows correct counts: processed / skipped
- Open a processed PDF in Evince and confirm Ctrl+F finds text

- [ ] **Step 3: Test the ocrmypdf-not-installed guard**

```bash
sudo mv /usr/bin/ocrmypdf /usr/bin/ocrmypdf.bak
python3 ~/.local/share/ocr-pdfs/ocr_pdfs_gui.py
```

Expected: error dialog appears with install instructions. Close dialog — start button is disabled.

Restore:
```bash
sudo mv /usr/bin/ocrmypdf.bak /usr/bin/ocrmypdf
```

- [ ] **Step 4: Commit**

```bash
git add -A
git status
git commit -m "chore: PDF OCR GUI complete — all tests passing"
```
