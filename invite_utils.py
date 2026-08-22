#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tạo và kiểm tra invite CloakChat dùng cho QR/Bluetooth."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Dict

INVITE_VERSION = 1


def create_invite(transport: str, address: str, display_name: str = "") -> str:
    """Tạo payload ngắn, có checksum; tuyệt đối không chứa khóa bí mật."""
    if transport not in ("lan", "tor"):
        raise ValueError("transport phải là lan hoặc tor")
    address = address.strip()
    if not address or len(address) > 255:
        raise ValueError("Địa chỉ invite không hợp lệ")
    body: Dict[str, Any] = {
        "v": INVITE_VERSION,
        "transport": transport,
        "address": address,
        "name": display_name.strip()[:64],
    }
    canonical = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    body["checksum"] = checksum
    return "CLOAKCHAT:" + base64.urlsafe_b64encode(
        json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")


def parse_invite(payload: str) -> Dict[str, str]:
    """Giải mã invite và kiểm tra checksum trước khi trả về dữ liệu."""
    if not payload.startswith("CLOAKCHAT:"):
        raise ValueError("Không phải invite CloakChat")
    encoded = payload.split(":", 1)[1]
    encoded += "=" * (-len(encoded) % 4)
    try:
        body = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invite bị hỏng hoặc không hợp lệ") from exc
    if body.get("v") != INVITE_VERSION or body.get("transport") not in ("lan", "tor"):
        raise ValueError("Phiên bản hoặc transport invite không được hỗ trợ")
    checksum = body.pop("checksum", None)
    canonical = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    if checksum != expected:
        raise ValueError("Checksum invite không khớp")
    return {
        "transport": str(body["transport"]),
        "address": str(body["address"]),
        "name": str(body.get("name", "")),
    }


def save_qr(payload: str, output_path: str) -> str:
    """Tạo file PNG QR; thư viện qrcode là dependency GUI tùy chọn."""
    try:
        import qrcode
    except ImportError as exc:
        raise RuntimeError("Cần cài qrcode và Pillow để tạo QR") from exc
    image = qrcode.make(payload)
    image.save(output_path)
    return output_path
