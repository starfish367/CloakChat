#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

python3 -m venv .venv-gui
source .venv-gui/bin/activate
python -m pip install -r requirements-gui.txt
python -m PyInstaller --clean --noconfirm CloakChatGUI.spec
printf '\nBuild hoàn tất: %s/dist/CloakChatGUI\n' "$(pwd)"
printf 'Tor cần được cài trên hệ thống, ví dụ: sudo apt install tor\n'
