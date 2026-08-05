#!/bin/sh
# ts cross compiles :exploding_head:
set -e
python3 -m pip install --upgrade PySide6 pyinstaller
python3 -m PyInstaller --noconfirm --clean m3c_gui.spec
echo
echo "Done:"
ls -la dist/
