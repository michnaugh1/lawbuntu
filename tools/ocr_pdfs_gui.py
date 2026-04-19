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


def check_ocrmypdf_installed():
    """Return True if ocrmypdf is available on PATH."""
    return shutil.which('ocrmypdf') is not None


def process_pdf(pdf_path, language='eng', rotate=False):
    """
    Run ocrmypdf on a single PDF, replacing it in-place on success.

    Returns a dict: {'status': 'ok'|'skipped'|'error', 'message': str}
    Exit code 6 from ocrmypdf means all pages already had text (--skip-text).
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
            msg = 'Could not process \u2014 file may be password-protected'
        elif 'invalid' in stderr or 'not a pdf' in stderr or 'damaged' in stderr:
            msg = 'Could not process \u2014 file may be damaged'
        else:
            msg = 'Could not process \u2014 unknown error'
        return {'status': 'error', 'message': msg}


# ---------------------------------------------------------------------------
# GTK Application
# ---------------------------------------------------------------------------

class OcrApp(Gtk.Application):

    def __init__(self):
        super().__init__(application_id=None)
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
        dialog.set_current_folder(str(Path.home()))
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
