#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/ocr-pdfs"
DESKTOP_DIR="$HOME/.local/share/applications"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

uninstall() {
    echo "Uninstalling PDF OCR — Make Searchable..."
    rm -f "$INSTALL_DIR/ocr_pdfs_gui.py"
    rmdir --ignore-fail-on-non-empty "$INSTALL_DIR"
    rm -f "$DESKTOP_DIR/ocr_pdfs_gui.desktop"
    rm -f "$ICON_DIR/ocr-pdfs.svg"
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    echo "Done. The app has been removed from your application menu."
}

install() {
    echo "Installing PDF OCR — Make Searchable..."

    mkdir -p "$INSTALL_DIR"
    cp "$SCRIPT_DIR/ocr_pdfs_gui.py" "$INSTALL_DIR/ocr_pdfs_gui.py"
    chmod +x "$INSTALL_DIR/ocr_pdfs_gui.py"

    mkdir -p "$ICON_DIR"
    cp "$SCRIPT_DIR/../assets/ocr-pdfs.svg" "$ICON_DIR/ocr-pdfs.svg"
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

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
