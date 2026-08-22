#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Danh bạ CloakChat cục bộ, tối giản và không đồng bộ lên máy chủ."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List


class ContactStore:
    def __init__(self, directory: str):
        self.path = Path(directory) / "contacts.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list_contacts(self) -> List[Dict[str, str]]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return []
            return [item for item in raw if isinstance(item, dict)]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def save(self, name: str, invite: str) -> None:
        name = name.strip()[:64]
        if not name or not invite.strip():
            raise ValueError("Tên và invite không được để trống")
        contacts = [item for item in self.list_contacts() if item.get("name") != name]
        contacts.append({"name": name, "invite": invite.strip()})
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(contacts, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def delete(self, name: str) -> None:
        contacts = [item for item in self.list_contacts() if item.get("name") != name]
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(contacts, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, self.path)
