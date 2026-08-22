#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# Cài runtime cho CloakChat trên Android/Termux.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_DIR}"

# Termux quản lý pip bằng pkg. Không chạy `pip install --upgrade pip`:
# Termux sẽ chặn thao tác đó để tránh làm hỏng python-pip.
pkg update -y
pkg upgrade -y
pkg install -y git python tor python-cryptography

# Chỉ cài các gói thuần Python từ PyPI. cryptography đã đến từ Termux.
python -m pip install -r requirements-termux.txt

python - <<'PY'
import cryptography
import socks
import stem
print("CloakChat dependencies: OK")
print("cryptography:", cryptography.__version__)
PY

printf '\nCài đặt hoàn tất trong %s. Chạy bằng:\n  python CloakChat.py\n' "${REPO_DIR}"
