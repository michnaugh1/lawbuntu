# Snap Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the PDF OCR GTK app as a strictly-confined Snap that can be installed locally with one command and eventually submitted to the Snap Store.

**Architecture:** A `snap/snapcraft.yaml` file drives the build. The `gnome` extension handles GTK 3 / Wayland / theming. A small bash launcher script (`snap/local/launcher`) provides a reliable entry point — more predictable than relying on `$SNAP` variable expansion in the `command` field. `ocrmypdf` and `tesseract-ocr-eng` are pulled in as `stage-packages` from Ubuntu's apt repos. The build runs inside a Multipass VM that snapcraft manages automatically.

**Tech Stack:** snapcraft (core22), gnome extension (gnome-42-2204 content snap), PyGObject, ocrmypdf, tesseract-ocr

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `snap/snapcraft.yaml` | Create | All snap build configuration |
| `snap/gui/ocr-pdfs.desktop` | Create | Snap desktop entry (auto-discovered by snapcraft) |
| `snap/local/launcher` | Create | Bash wrapper that invokes python3 with correct $SNAP paths |
| `.gitignore` | Modify | Exclude snapcraft build artifacts (*.snap, parts/, stage/, prime/) |
| `README.md` | Modify | Add snap installation instructions |

---

### Task 1: Install prerequisites and update .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Install snapcraft and Multipass**

```bash
sudo snap install snapcraft --classic
sudo snap install multipass
```

Verify:

```bash
snapcraft --version
```

Expected output (version may differ): `snapcraft 8.x.x`

- [ ] **Step 2: Add snapcraft build artifacts to .gitignore**

Open `.gitignore` and append:

```
# Snapcraft build artifacts
*.snap
parts/
stage/
prime/
.snapcraft/
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: exclude snapcraft build artifacts from git"
```

---

### Task 2: Create the snap directory structure and launcher

**Files:**
- Create: `snap/local/launcher`
- Create: `snap/gui/` (directory)

- [ ] **Step 1: Create directories**

```bash
mkdir -p snap/gui snap/local
```

- [ ] **Step 2: Create snap/local/launcher**

```bash
#!/bin/bash
exec "$SNAP/usr/bin/python3" "$SNAP/ocr_pdfs_gui.py"
```

Save as `snap/local/launcher` and make it executable:

```bash
chmod +x snap/local/launcher
```

- [ ] **Step 3: Verify the file is executable**

```bash
ls -la snap/local/launcher
```

Expected: `-rwxr-xr-x` permissions.

- [ ] **Step 4: Commit**

```bash
git add snap/local/launcher
git commit -m "feat: add snap launcher script"
```

---

### Task 3: Create snap/gui/ocr-pdfs.desktop

**Files:**
- Create: `snap/gui/ocr-pdfs.desktop`

Snapcraft auto-discovers desktop files in `snap/gui/`. The `Exec=` line is omitted — the snap runtime generates it from `snapcraft.yaml`.

- [ ] **Step 1: Create snap/gui/ocr-pdfs.desktop**

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

- [ ] **Step 2: Commit**

```bash
git add snap/gui/ocr-pdfs.desktop
git commit -m "feat: add snap desktop entry"
```

---

### Task 4: Create snap/snapcraft.yaml

**Files:**
- Create: `snap/snapcraft.yaml`

- [ ] **Step 1: Create snap/snapcraft.yaml**

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

apps:
  ocr-pdfs:
    command: bin/launch-ocr-pdfs
    extensions: [gnome]
    plugs:
      - home

plugs:
  home:
    interface: home

parts:
  ocr-pdfs:
    plugin: dump
    source: .
    source-type: local
    organize:
      tools/ocr_pdfs_gui.py: ocr_pdfs_gui.py
      assets/ocr-pdfs.svg: assets/ocr-pdfs.svg
      snap/local/launcher: bin/launch-ocr-pdfs
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
      - bin/
      - usr/
      - -usr/share/doc
      - -usr/share/man
```

- [ ] **Step 2: Commit**

```bash
git add snap/snapcraft.yaml
git commit -m "feat: add snapcraft.yaml packaging configuration"
```

---

### Task 5: Build the snap

**Files:** none (build output only, excluded by .gitignore)

This task builds the snap inside a Multipass VM. First build takes 10–20 minutes as it downloads the core22 base and gnome content snap. Subsequent builds are faster.

- [ ] **Step 1: Run the build from the project root**

```bash
cd /home/michnaugh1/Dev/Ubuntu_Lawyers
snapcraft
```

Snapcraft automatically finds `snap/snapcraft.yaml`. Watch for errors — common ones and their fixes are in Step 2.

- [ ] **Step 2: Handle common build errors**

**If `multipass` not found:**
```bash
sudo snap install multipass
snapcraft
```

**If a stage-package is not found (e.g., `gir1.2-gtk-3.0`):**
Check the exact package name: `apt-cache search gir1.2-gtk` inside the build VM, or adjust the package name in `snap/snapcraft.yaml` and rebuild.

**If the gnome extension version conflicts:**
The extension requires `gnome-42-2204` content snap. If snapcraft reports a version mismatch, add this to `snapcraft.yaml` under `apps.ocr-pdfs`:
```yaml
    plugs:
      - home
      - gnome-42-2204
```
Then rebuild.

- [ ] **Step 3: Verify the snap file was produced**

```bash
ls -lh *.snap
```

Expected: `ocr-pdfs_1.0.0_amd64.snap` (size roughly 50–150 MB).

---

### Task 6: Install and test the snap locally

**Files:** none

- [ ] **Step 1: Install the snap**

```bash
sudo snap install ocr-pdfs_1.0.0_amd64.snap --dangerous
```

`--dangerous` bypasses Store signature verification for locally-built snaps.

Expected output:
```
ocr-pdfs 1.0.0 installed
```

- [ ] **Step 2: Launch and verify the app**

```bash
snap run ocr-pdfs
```

Verify:
- Window opens titled "PDF OCR — Make Searchable"
- Browse button opens a native folder picker
- Selecting a folder enables the "Make PDFs Searchable" button
- Run it against a folder of PDFs and confirm processing works end-to-end
- Summary panel appears after processing with correct counts

- [ ] **Step 3: Verify home directory access**

Select a folder inside `$HOME` (e.g. `~/Documents`) and process a PDF. Confirm the file is modified in-place without permission errors.

If you get a permission error, check which interfaces are connected:

```bash
snap connections ocr-pdfs
```

The `home` interface should show as connected. If not:

```bash
sudo snap connect ocr-pdfs:home :home
```

- [ ] **Step 4: Check the app appears in GNOME Activities**

Open GNOME Activities and search "PDF OCR". The snap version of the app should appear alongside (or instead of) the manually-installed version.

- [ ] **Step 5: Uninstall when done testing**

```bash
sudo snap remove ocr-pdfs
```

---

### Task 7: Update README and final commit

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add snap installation section to README.md**

Find the `## Installation` section in `README.md` and replace it with:

```markdown
## Installation

### Option 1: Snap (recommended)

```bash
sudo snap install ocr-pdfs_1.0.0_amd64.snap --dangerous
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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add snap installation instructions to README"
```
