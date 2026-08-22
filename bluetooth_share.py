#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Chia sẻ invite qua Bluetooth/system share.

Android dùng ACTION_SEND qua Pyjnius để người dùng chọn Bluetooth hoặc ứng dụng
chia sẻ phù hợp. Desktop trả về False để GUI không giả vờ Bluetooth đã hoạt động.
"""

from __future__ import annotations


def share_invite_android(payload: str) -> bool:
    """Mở Android Sharesheet; người dùng có thể chọn Bluetooth."""
    try:
        from jnius import autoclass
        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
        except Exception:
            PythonActivity = autoclass("org.renpy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        activity = PythonActivity.mActivity
        intent = Intent(Intent.ACTION_SEND)
        intent.setType("text/plain")
        intent.putExtra(Intent.EXTRA_TEXT, payload)
        chooser = Intent.createChooser(intent, "Chia sẻ CloakChat invite")
        activity.startActivity(chooser)
        return True
    except Exception:
        return False


def share_invite(payload: str) -> bool:
    """Chia sẻ invite. Trên Android dùng system Sharesheet; desktop chưa hỗ trợ."""
    return share_invite_android(payload)
