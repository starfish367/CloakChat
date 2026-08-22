#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# Cài runtime cho CloakChat trên Android/Termux.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_DIR}"

pkg update -y
pkg install -y python tor git
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

printf '\nCài đặt hoàn tất trong %s. Chạy bằng:\n  python CloakChat.py\n' "${REPO_DIR}"
