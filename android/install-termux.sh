#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# Cài runtime cho CloakChat trên Android/Termux.
pkg update -y
pkg install -y python tor git
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

printf '\nCài đặt hoàn tất. Chạy bằng:\n  python CloakChat.py\n'
