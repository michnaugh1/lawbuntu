# Snap Packaging — Design Spec

**Date:** 2026-04-19
**Project:** Ubuntu_Lawyers — PDF OCR tool
**Status:** Approved design, ready for implementation planning

## 1. Overview

Package the "PDF OCR — Make Searchable" GTK application as a Snap for local testing and eventual Snap Store publication. The snap bundles the app, Python/GTK bindings, ocrmypdf, and Tesseract (English only) into a self-contained, strictly-confined package that installs in one command on any Ubuntu system.

## 2. Goals & Non-Goals

**Goals**

- Build a locally-installable `.snap` file that works identically to the existing per-user install
- Use strict confinement so the snap is Store-ready without special review
- Use the `gnome` extension for correct GTK 3 theming and Wayland/X11 compatibility
- English-only Tesseract for V1 (language packs added in a future release)
- No changes required to `tools/ocr_pdfs_gui.py`

**Non-goals (V1)**

- Snap Store publication (local build and test only)
- Additional Tesseract language packs
- Auto-update configuration
- core24 or core26 migration (revisit when core26 matures)

## 3. Files

| File | Action | Purpose |
|------|--------|---------|
| `snap/snapcraft.yaml` | Create | All snap packaging configuration |
| `snap/gui/ocr-pdfs.desktop` | Create | Snap-specific desktop entry (Exec handled by snap runtime) |
| `tools/ocr_pdfs_gui.py` | Unchanged | No code changes required |
| `assets/ocr-pdfs.svg` | Unchanged | Reused as snap icon |

## 4. snapcraft.yaml

### Metadata

```yaml
name: ocr-pdfs
version: '1.0.0'
summary: Make a folder of PDF files text-searchable
description: |
  A simple tool for attorneys and legal professionals to make scanned
  PDF files text-searchable using OCR. Select a folder, click one
  button, and all PDFs are processed in-place.

base: core22
confinement: strict
grade: devel

icon: assets/ocr-pdfs.svg
```

`grade: devel` prevents accidental Store publication. Change to `stable` when ready to submit.

### Part

```yaml
parts:
  ocr-pdfs:
    plugin: dump
    source: .
    source-type: local
    organize:
      tools/ocr_pdfs_gui.py: ocr_pdfs_gui.py
      assets/ocr-pdfs.svg: assets/ocr-pdfs.svg
    stage-packages:
      - python3
      - python3-gi
      - python3-gi-cairo
      - gir1.2-gtk-3.0
      - ocrmypdf
      - tesseract-ocr
      - tesseract-ocr-eng
    prime:
      - ocr_pdfs_gui.py
      - assets/
      - usr/
```

### App and plugs

```yaml
apps:
  ocr-pdfs:
    command: usr/bin/python3 $SNAP/ocr_pdfs_gui.py
    extensions: [gnome]
    plugs:
      - home
    desktop: snap/gui/ocr-pdfs.desktop

plugs:
  home:
    interface: home
```

The `gnome` extension automatically supplies: `desktop`, `desktop-legacy`, `gsettings`, `opengl`, `wayland`, `x11`, and the GNOME platform content snap (`gnome-42-2204`). Only `home` requires explicit declaration.

## 5. Snap Desktop Entry

`snap/gui/ocr-pdfs.desktop` is a minimal desktop file used by the snap runtime. Snapcraft automatically discovers desktop files placed in `snap/gui/`. The `Exec=` line is intentionally omitted — the snap runtime generates it from the app definition in `snapcraft.yaml`.

```ini
[Desktop Entry]
Type=Application
Name=PDF OCR — Make Searchable
Comment=Make a folder of PDF files text-searchable using OCR
Icon=${SNAP}/assets/ocr-pdfs.svg
Terminal=false
Categories=Office;
Keywords=PDF;OCR;searchable;text;scan;
StartupNotify=true
```

## 6. Build and Test Process

```bash
# Install snapcraft (once)
sudo snap install snapcraft --classic

# Build from project root (5-15 min, uses Multipass VM)
snapcraft

# Install locally
sudo snap install ocr-pdfs_1.0.0_amd64.snap --dangerous

# Run and verify
snap run ocr-pdfs

# Uninstall
sudo snap remove ocr-pdfs
```

`--dangerous` is required for locally-built snaps not signed by the Snap Store.

## 7. Store Publication (Future)

When ready to publish:

1. Change `grade: devel` → `grade: stable` in `snapcraft.yaml`
2. Register the name: `snapcraft register ocr-pdfs`
3. Build a clean snap: `snapcraft`
4. Upload: `snapcraft upload ocr-pdfs_1.0.0_amd64.snap`
5. Release to stable channel: `snapcraft release ocr-pdfs <revision> stable`

## 8. Future Considerations

- **Additional language packs:** add `tesseract-ocr-spa`, `tesseract-ocr-fra`, etc. to `stage-packages` and add a language dropdown to the GUI
- **core24 migration:** when core26 matures (est. late 2026), update base and gnome extension version
- **Automated builds:** Snapcraft supports GitHub Actions for automatic snap builds on push
