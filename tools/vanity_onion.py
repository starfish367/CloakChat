#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wrapper tạo vanity onion v3 bằng mkp224o.

Công cụ không rút ngắn onion address; nó chỉ tạo prefix dễ nhớ. Private key
được mkp224o ghi trong output directory, vì vậy thư mục đó phải được bảo vệ.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Tor v3 vanity prefix")
    parser.add_argument("prefix", help="Prefix lowercase base32, ví dụ cloakchat")
    parser.add_argument("-o", "--output", default="vanity-onions", help="Thư mục output")
    parser.add_argument("--threads", type=int, default=0, help="Số worker của mkp224o")
    args = parser.parse_args()

    prefix = args.prefix.strip().lower()
    alphabet = set("abcdefghijklmnopqrstuvwxyz234567")
    if not prefix or len(prefix) > 16 or any(char not in alphabet for char in prefix):
        print(
            "Prefix phải là 1-16 ký tự lowercase base32: a-z hoặc 2-7.",
            file=sys.stderr,
        )
        return 2
    if shutil.which("mkp224o") is None:
        print(
            "Chưa tìm thấy mkp224o. Cài/build mkp224o từ nguồn đáng tin cậy "
            "rồi đặt executable vào PATH.",
            file=sys.stderr,
        )
        return 1

    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    command = ["mkp224o", "-d", str(output)]
    if args.threads > 0:
        command.extend(["-t", str(args.threads)])
    command.append(prefix)
    print("Đang tạo vanity onion; prefix dài sẽ tốn nhiều thời gian/tài nguyên hơn.")
    print("Dừng bằng Ctrl+C. Bảo vệ toàn bộ private key trong thư mục output.")
    try:
        return subprocess.call(command)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
