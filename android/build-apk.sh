#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

python3 -m venv .venv-buildozer
source .venv-buildozer/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install buildozer cython
buildozer -v android debug
printf '\nAPK build hoàn tất trong thư mục bin/.\n'
printf 'Android hiện ưu tiên LAN E2EE; Tor cần tích hợp binary/service Android riêng.\n'
