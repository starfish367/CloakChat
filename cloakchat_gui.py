#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CloakChat GUI - giao diện Kivy cho Windows, Linux và Android.

Core mạng/mật mã nằm trong CloakChat.py. File này chỉ cung cấp giao diện cửa sổ
và chạy các thao tác blocking trên worker thread để UI không bị treo.
"""

from __future__ import annotations

import atexit
import hashlib
import os
import secrets
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# Đảm bảo các module core đi cùng thư mục luôn được tìm thấy khi chạy từ
# PyInstaller, Buildozer hoặc một test runner ở thư mục khác.
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from kivy.app import App
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.utils import platform

import CloakChat as core
from bluetooth_share import share_invite
from contacts_store import ContactStore
from invite_utils import create_invite, parse_invite, save_qr
from voice_chat import VoiceChat
from group_chat import GroupHost, GroupProtocolError, MODE_HOST_RELAY, MODE_TRUE_E2EE


class CloakChatGUI(App):
    """Cửa sổ chính của CloakChat."""

    TRANSPORT_LABELS = {
        "LAN": {"vi": "LAN trực tiếp", "en": "Direct LAN"},
        "PUBLIC": {"vi": "IP công cộng", "en": "Public IP"},
        "TOR": {"vi": "Tor / Onion", "en": "Tor / Onion"},
        "ORBOT": {"vi": "Orbot SOCKS5", "en": "Orbot SOCKS5"},
    }
    GROUP_MODE_LABELS = {
        "DIRECT": {"vi": "2 người", "en": "1–1"},
        "A": {"vi": "Nhóm A — Host relay", "en": "Group A — Host relay"},
        "B": {"vi": "Nhóm B — E2EE thật", "en": "Group B — true E2EE"},
    }
    SECURITY_LABELS = {
        "BALANCED": {"vi": "Cân bằng", "en": "Balanced"},
        "STRICT": {"vi": "Nghiêm ngặt", "en": "Strict"},
    }
    ROLE_LABELS = {
        "HOST": {"vi": "Host", "en": "Host"},
        "JOIN": {"vi": "Join", "en": "Join"},
    }
    TEXTS = {
        "vi": {
            "language": "Ngôn ngữ",
            "subtitle": "RIÊNG TƯ • MÃ HÓA • TRỰC TIẾP",
            "ready": "SẴN SÀNG",
            "secure": "AN TOÀN",
            "connection": "KẾT NỐI",
            "choose_connection": "Chọn cách kết nối",
            "network": "Mạng",
            "role": "Vai trò",
            "start": "BẮT ĐẦU",
            "stop": "DỪNG",
            "qr": "QR INVITE",
            "bluetooth": "BLUETOOTH",
            "contacts": "DANH BẠ",
            "voice": "VOICE",
            "voice_off": "TẮT VOICE",
            "chat": "TIN NHẮN",
            "channel": "Kênh E2EE",
            "reaction": "Phản hồi",
            "send": "GỬI",
            "address_join": "Địa chỉ Join: IP:cổng hoặc tên .onion",
            "address_public": "IP public của máy này, ví dụ 203.0.113.10",
            "address_invite": "Dán invite QR hoặc IP:cổng / tên .onion",
            "address_host": "Host sẽ hiển thị địa chỉ sau khi bấm Bắt đầu",
            "message_hint": "Viết tin nhắn bảo mật...",
            "status_ready": "●  Sẵn sàng — LAN không dùng Tor, E2EE vẫn bật",
            "status_disconnected": "●  Đã ngắt kết nối — sẵn sàng cho phiên mới",
            "status_connected": "●  Đã kết nối — E2EE hoạt động — SHA-512 fingerprint đã xác nhận",
            "log_ready": "Sẵn sàng. Chọn LAN để kết nối nội bộ hoặc Tor để dùng .onion.",
            "safety_prompt": "Đối chiếu SHA-512 fingerprint với peer qua kênh tin cậy bên ngoài",
            "safety_question": "Bạn xác nhận hai fingerprint trùng khớp hoàn toàn?",
            "yes": "Đúng, xác nhận",
            "no": "Không",
            "safety_title": "Xác nhận SHA-512 fingerprint",
            "qr_hint": "Quét QR này để lấy invite CloakChat.",
            "qr_title": "CloakChat QR invite",
            "orbot_join_only": "Orbot SOCKS5 chỉ hỗ trợ Join onion trên Android.",
            "orbot_not_android": "Orbot SOCKS5 chỉ khả dụng trên Android.",
            "orbot_not_installed": "Chưa tìm thấy Orbot. Hãy cài và mở Orbot trước khi kết nối.",
            "orbot_wait": "Đang chờ Orbot SOCKS5 sẵn sàng...",
            "copy": "SAO CHÉP",
            "share": "CHIA SẺ",
            "copy_invite": "COPY INVITE",
            "retry": "KẾT NỐI LẠI",
            "check_orbot": "KIỂM TRA ORBOT",
            "orbot_port": "Cổng Orbot (tự động)",
            "orbot_checking": "Đang kiểm tra Orbot SOCKS5...",
            "orbot_ready": "Orbot SOCKS5 hoạt động tại",
            "font_size": "CỠ CHỮ",
            "font_small": "NHỎ",
            "font_default": "MẶC ĐỊNH",
            "font_large": "LỚN",
            "diagnostics": "CHẨN ĐOÁN",
            "diagnostics_title": "Chẩn đoán kết nối",
            "diagnostics_empty": "Chưa có thông tin chẩn đoán.",
            "paste": "DÁN INVITE",
            "fingerprint": "FINGERPRINT",
            "clear_chat": "XÓA CHAT",
            "clear_chat_title": "Xóa lịch sử cục bộ",
            "clear_chat_confirm": "Xóa bản sao chat trên thiết bị này? Peer vẫn giữ bản sao của họ.",
            "cancel": "HỦY",
            "copied": "Đã sao chép địa chỉ vào clipboard.",
            "fingerprint_copied": "Đã sao chép SHA-512 fingerprint để đối chiếu ngoài băng.",
            "no_fingerprint": "Fingerprint chỉ xuất hiện sau khi handshake hoàn tất.",
            "chat_cleared": "Đã xóa lịch sử chat cục bộ trên thiết bị này.",
            "search_hint": "Tìm trong chat...",
            "search": "TÌM",
            "clear_search": "XÓA TÌM",
            "details": "CHI TIẾT",
            "session_details_title": "Chi tiết phiên bảo mật",
            "transport_detail": "Transport",
            "role_detail": "Vai trò",
            "group_detail": "Chế độ nhóm",
            "security_detail": "Mức bảo mật",
            "fingerprint_detail": "SHA-512 fingerprint",
            "no_session_details": "Chưa có phiên đang hoạt động.",
            "show_settings": "MỞ CẤU HÌNH",
            "hide_settings": "ẨN CẤU HÌNH",
            "export": "XUẤT CHAT",
            "export_saved": "Đã lưu transcript tại",
            "shared": "Đã mở bảng chia sẻ.",
            "share_desktop": "Desktop chưa có Sharesheet; địa chỉ đã được sao chép để bạn dán vào ứng dụng khác.",
            "invite_label": "Gửi địa chỉ này cho peer:",
            "nickname": "Biệt danh của bạn",
            "file": "TỆP",
            "choose_file": "Chọn tệp để gửi",
            "file_sent": "Đã gửi tệp",
            "file_received": "Đã nhận tệp",
            "peer_joined": "Peer dùng biệt danh",
            "reply": "TRẢ LỜI",
            "replying": "Đang trả lời tin nhắn",
            "group_mode": "Chế độ chat",
            "security_level": "Mức bảo mật",
            "group_b_started": "Group B dùng group key; relay không giải mã trong luồng bình thường.",
            "group_ready": "Group A đang chờ thành viên; Host relay giải mã được nội dung.",
            "group_b_ready": "Group B đang chờ thành viên; relay chuyển ciphertext và xoay group key khi kick/ban.",
            "security_warning": "Mức Strict chỉ cho phép Group B; hãy xác minh fingerprint trước khi dùng.",
            "members": "THÀNH VIÊN",
            "kick": "ĐUỔI",
            "ban": "BAN",
            "no_group": "Chưa có Group Host đang chạy.",
            "auto_delete": "Tự hủy cục bộ",
            "auto_off": "Tắt",
            "auto_30s": "30 giây",
            "auto_5m": "5 phút",


        },
        "en": {
            "language": "Language",
            "subtitle": "PRIVATE • ENCRYPTED • DIRECT",
            "ready": "READY",
            "secure": "SECURE",
            "connection": "CONNECTION",
            "choose_connection": "Choose a transport",
            "network": "Network",
            "role": "Role",
            "start": "START",
            "stop": "STOP",
            "qr": "QR INVITE",
            "bluetooth": "BLUETOOTH",
            "contacts": "CONTACTS",
            "voice": "VOICE",
            "voice_off": "STOP VOICE",
            "chat": "MESSAGES",
            "channel": "E2EE channel",
            "reaction": "React",
            "send": "SEND",
            "address_join": "Join address: IP:port or .onion host",
            "address_public": "This machine's public IP, e.g. 203.0.113.10",
            "address_invite": "Paste QR invite or IP:port / .onion host",
            "address_host": "Host address appears after pressing Start",
            "message_hint": "Write a secure message...",
            "status_ready": "●  Ready — LAN uses no Tor; E2EE remains on",
            "status_disconnected": "●  Disconnected — ready for a new session",
            "status_connected": "●  Connected — E2EE active — SHA-512 fingerprint verified",
            "log_ready": "Ready. Choose Direct LAN for local chat or Tor for a .onion session.",
            "safety_prompt": "Compare the SHA-512 fingerprint with your peer through a trusted channel",
            "safety_question": "Do both fingerprints match exactly?",
            "yes": "Yes, confirm",
            "no": "No",
            "safety_title": "Confirm SHA-512 fingerprint",
            "qr_hint": "Scan this QR code to receive the CloakChat invite.",
            "qr_title": "CloakChat QR invite",
            "orbot_join_only": "Orbot SOCKS5 supports onion Join on Android only.",
            "orbot_not_android": "Orbot SOCKS5 is available on Android only.",
            "orbot_not_installed": "Orbot was not found. Install and open Orbot before connecting.",
            "orbot_wait": "Waiting for the Orbot SOCKS5 proxy...",
            "copy": "COPY",
            "share": "SHARE",
            "copy_invite": "COPY INVITE",
            "retry": "RECONNECT",
            "check_orbot": "TEST ORBOT",
            "orbot_port": "Orbot port (auto)",
            "orbot_checking": "Checking Orbot SOCKS5...",
            "orbot_ready": "Orbot SOCKS5 is ready at",
            "font_size": "TEXT SIZE",
            "font_small": "SMALL",
            "font_default": "DEFAULT",
            "font_large": "LARGE",
            "diagnostics": "DIAGNOSTICS",
            "diagnostics_title": "Connection diagnostics",
            "diagnostics_empty": "No diagnostic information yet.",
            "paste": "PASTE INVITE",
            "fingerprint": "FINGERPRINT",
            "clear_chat": "CLEAR CHAT",
            "clear_chat_title": "Clear local history",
            "clear_chat_confirm": "Clear the chat copy on this device? Your peer keeps their own copy.",
            "cancel": "CANCEL",
            "copied": "Address copied to the clipboard.",
            "fingerprint_copied": "SHA-512 fingerprint copied for out-of-band verification.",
            "no_fingerprint": "The fingerprint appears after the handshake completes.",
            "chat_cleared": "Local chat history was cleared on this device.",
            "search_hint": "Search chat...",
            "search": "SEARCH",
            "clear_search": "CLEAR SEARCH",
            "details": "DETAILS",
            "session_details_title": "Secure session details",
            "transport_detail": "Transport",
            "role_detail": "Role",
            "group_detail": "Group mode",
            "security_detail": "Security level",
            "fingerprint_detail": "SHA-512 fingerprint",
            "no_session_details": "No active session.",
            "show_settings": "SHOW SETTINGS",
            "hide_settings": "HIDE SETTINGS",
            "export": "EXPORT CHAT",
            "export_saved": "Transcript saved to",
            "shared": "Share sheet opened.",
            "share_desktop": "Desktop has no system share sheet; the address was copied so you can paste it into another app.",
            "invite_label": "Send this address to your peer:",
            "nickname": "Your nickname",
            "file": "FILE",
            "choose_file": "Choose a file to send",
            "file_sent": "File sent",
            "file_received": "File received",
            "peer_joined": "Peer nickname",
            "reply": "REPLY",
            "replying": "Replying to message",
            "group_mode": "Chat mode",
            "security_level": "Security level",
            "group_b_started": "Group B uses a group key; the relay does not decrypt events during normal forwarding.",
            "group_ready": "Group A is waiting for members; the Host relay can read group content.",
            "group_b_ready": "Group B is waiting for members; the relay forwards ciphertext and rotates the group key after kick/ban.",
            "security_warning": "Strict mode permits Group B only; verify the fingerprint before use.",
            "members": "MEMBERS",
            "kick": "KICK",
            "ban": "BAN",
            "no_group": "No Group Host is running.",
            "auto_delete": "Local auto-delete",
            "auto_off": "Off",
            "auto_30s": "30 seconds",
            "auto_5m": "5 minutes",


        },
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.daemon: Optional[core.TorDaemon] = None
        self.listener: Optional[socket.socket] = None
        self.session: Optional[core.ChatSession] = None
        self.worker: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.confirm_event: Optional[threading.Event] = None
        self.confirm_result = False
        self.safety_popup: Optional[Popup] = None
        self.current_invite: Optional[str] = None
        self.contacts: Optional[ContactStore] = None
        self.voice: Optional[VoiceChat] = None
        self.language = "vi"
        self._transport_labels = {}
        self._role_labels = {}
        self.current_address: Optional[str] = None
        self.incoming_files = {}
        self.log_entries = []
        self.search_query = ""
        self.settings_expanded = True
        self.has_attempted_connection = False
        self.font_scale = 1.0
        self.last_diagnostics = ""
        self.auto_delete_seconds = 0
        self.group_host: Optional[GroupHost] = None
        self.group_mode = "DIRECT"
        self.security_level = "BALANCED"
        self.last_peer_message_id: Optional[str] = None
        self.reply_to_id: Optional[str] = None

    def build(self):
        self.title = "CloakChat"
        self.contacts = ContactStore(self.user_data_dir)
        try:
            from kivy.core.window import Window
            Window.clearcolor = (0.035, 0.055, 0.09, 1)
            Window.minimum_width = dp(420)
            Window.minimum_height = dp(640)
            desktop_layout = Window.width >= dp(760)
        except Exception:
            desktop_layout = True

        root = BoxLayout(
            orientation="horizontal" if desktop_layout else "vertical",
            padding=0,
            spacing=0,
        )

        sidebar = BoxLayout(
            orientation="vertical",
            padding=[dp(14), dp(14)],
            spacing=dp(8),
            size_hint_x=None if desktop_layout else 1,
            size_hint_y=1 if desktop_layout else None,
            width=dp(310) if desktop_layout else 1,
            height=1 if desktop_layout else dp(660),
        )
        with sidebar.canvas.before:
            Color(0.045, 0.065, 0.105, 1)
            sidebar_bg = Rectangle(pos=sidebar.pos, size=sidebar.size)
        sidebar.bind(pos=lambda w, p: setattr(sidebar_bg, "pos", w.pos))
        sidebar.bind(size=lambda w, s: setattr(sidebar_bg, "size", w.size))

        header = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.title_label = Label(
            text="[b]CloakChat[/b]\n[size=11][color=#93A4C3]RIÊNG TƯ • MÃ HÓA • TRỰC TIẾP[/color][/size]",
            markup=True,
            halign="left",
            valign="middle",
        )
        self.title_label.bind(size=self._sync_text_size)
        header.add_widget(self.title_label)
        self.language_spinner = Spinner(
            text="Tiếng Việt",
            values=("Tiếng Việt", "English"),
            size_hint_x=None,
            width=dp(98),
            background_normal="",
            background_color=(0.12, 0.18, 0.28, 1),
            color=(0.92, 0.95, 1, 1),
        )
        self.language_spinner.bind(text=lambda _spinner, value: self.set_language("en" if value == "English" else "vi"))
        header.add_widget(self.language_spinner)
        self.details_button = Button(text=self._t("details"), size_hint_x=None, width=dp(78), background_normal="", background_color=(0.12, 0.18, 0.28, 1), font_size=dp(10), disabled=True)
        self.details_button.bind(on_press=lambda *_: self.show_session_details())
        header.add_widget(self.details_button)
        sidebar.add_widget(header)

        self.security_badge = Label(
            text="●  E2EE\n[size=11]READY[/size]",
            markup=True,
            color=(0.35, 0.92, 0.68, 1),
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(40),
        )
        self.security_badge.bind(size=self._sync_text_size)
        sidebar.add_widget(self.security_badge)
        self.settings_toggle_button = Button(
            text=self._t("hide_settings"),
            size_hint_y=None,
            height=dp(32),
            background_normal="",
            background_color=(0.10, 0.15, 0.23, 1),
            font_size=dp(10),
        )
        self.settings_toggle_button.bind(on_press=lambda *_: self.toggle_settings())
        sidebar.add_widget(self.settings_toggle_button)

        connection_card = BoxLayout(
            orientation="vertical",
            padding=[dp(10), dp(9)],
            spacing=dp(5),
            size_hint_y=None,
            height=dp(258),
        )
        with connection_card.canvas.before:
            Color(0.07, 0.10, 0.16, 1)
            connection_bg = RoundedRectangle(pos=connection_card.pos, size=connection_card.size, radius=[dp(14)])
        connection_card.bind(pos=lambda w, p: setattr(connection_bg, "pos", w.pos))
        connection_card.bind(size=lambda w, s: setattr(connection_bg, "size", w.size))
        self.connection_header = Label(
            text="[b]KẾT NỐI[/b]  [color=#93A4C3]Chọn cách kết nối[/color]",
            markup=True,
            halign="left",
            size_hint_y=None,
            height=dp(21),
        )
        connection_card.add_widget(self.connection_header)
        fields = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(112))
        self.network_label = Label(text="Mạng", color=(0.58, 0.65, 0.78, 1), halign="left")
        fields.add_widget(self.network_label)
        self.transport = Spinner(
            text=self._transport_value("LAN"),
            values=tuple(self._transport_value(key) for key in ("LAN", "PUBLIC", "TOR", "ORBOT")),
            background_normal="",
            background_color=(0.12, 0.18, 0.28, 1),
            color=(0.92, 0.95, 1, 1),
        )
        fields.add_widget(self.transport)
        self.role_label = Label(text="Vai trò", color=(0.58, 0.65, 0.78, 1), halign="left")
        fields.add_widget(self.role_label)
        self.role = Spinner(
            text=self._role_value("HOST"),
            values=(self._role_value("HOST"), self._role_value("JOIN")),
            background_normal="",
            background_color=(0.12, 0.18, 0.28, 1),
            color=(0.92, 0.95, 1, 1),
        )
        self.role.bind(text=lambda *_: self._role_changed())
        self.transport.bind(text=lambda *_: self._role_changed())
        fields.add_widget(self.role)
        self.group_mode_label = Label(text=self._t("group_mode"), color=(0.58, 0.65, 0.78, 1), halign="left")
        fields.add_widget(self.group_mode_label)
        self.group_mode_spinner = Spinner(
            text=self._group_mode_value("DIRECT"),
            values=tuple(self._group_mode_value(key) for key in ("DIRECT", "A", "B")),
            background_normal="",
            background_color=(0.12, 0.18, 0.28, 1),
            color=(0.92, 0.95, 1, 1),
        )
        self.group_mode_spinner.bind(text=lambda *_: self._role_changed())
        fields.add_widget(self.group_mode_spinner)
        self.security_level_label = Label(text=self._t("security_level"), color=(0.58, 0.65, 0.78, 1), halign="left")
        fields.add_widget(self.security_level_label)
        self.security_level_spinner = Spinner(
            text=self._security_value("BALANCED"),
            values=tuple(self._security_value(key) for key in ("BALANCED", "STRICT")),
            background_normal="",
            background_color=(0.12, 0.18, 0.28, 1),
            color=(0.92, 0.95, 1, 1),
        )
        fields.add_widget(self.security_level_spinner)
        connection_card.add_widget(fields)
        self.nickname_input = TextInput(
            hint_text=self._t("nickname"),
            text="Anonymous",
            multiline=False,
            size_hint_y=None,
            height=dp(36),
            padding=[dp(10), dp(8)],
            background_normal="",
            background_color=(0.11, 0.15, 0.23, 1),
            foreground_color=(0.92, 0.95, 1, 1),
            hint_text_color=(0.45, 0.53, 0.67, 1),
        )
        connection_card.add_widget(self.nickname_input)
        self.address = TextInput(
            hint_text=self._t("address_join"),
            multiline=False,
            size_hint_y=None,
            height=dp(36),
            padding=[dp(10), dp(8)],
            background_normal="",
            background_color=(0.11, 0.15, 0.23, 1),
            foreground_color=(0.92, 0.95, 1, 1),
            hint_text_color=(0.45, 0.53, 0.67, 1),
        )
        connection_card.add_widget(self.address)
        self.orbot_port_input = TextInput(
            hint_text=self._t("orbot_port"),
            multiline=False,
            input_filter="int",
            size_hint_y=None,
            height=dp(36),
            padding=[dp(10), dp(8)],
            background_normal="",
            background_color=(0.11, 0.15, 0.23, 1),
            foreground_color=(0.92, 0.95, 1, 1),
            hint_text_color=(0.45, 0.53, 0.67, 1),
        )
        connection_card.add_widget(self.orbot_port_input)
        self.connection_card = connection_card
        sidebar.add_widget(connection_card)

        action_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self.start_button = Button(text=self._t("start"), background_normal="", background_color=(0.15, 0.63, 0.48, 1), bold=True)
        self.start_button.bind(on_press=self.start_connection)
        self.stop_button = Button(text=self._t("stop"), background_normal="", background_color=(0.55, 0.18, 0.23, 1), disabled=True)
        self.retry_button = Button(text=self._t("retry"), background_normal="", background_color=(0.12, 0.18, 0.28, 1), disabled=True, font_size=dp(10))
        self.retry_button.bind(on_press=lambda *_: self.retry_connection())
        self.stop_button.bind(on_press=lambda *_: self.stop_connection())
        action_row.add_widget(self.start_button)
        action_row.add_widget(self.stop_button)
        action_row.add_widget(self.retry_button)
        sidebar.add_widget(action_row)

        tools = GridLayout(cols=3, spacing=dp(5), size_hint_y=None, height=dp(104))
        button_style = dict(background_normal="", background_color=(0.12, 0.18, 0.28, 1), font_size=dp(11))
        self.qr_button = Button(text=self._t("qr"), disabled=True, **button_style)
        self.qr_button.bind(on_press=lambda *_: self.show_qr())
        self.bluetooth_button = Button(text=self._t("bluetooth"), disabled=True, **button_style)
        self.bluetooth_button.bind(on_press=lambda *_: self.share_bluetooth())
        self.contacts_button = Button(text=self._t("contacts"), **button_style)
        self.contacts_button.bind(on_press=lambda *_: self.show_contacts())
        self.voice_button = Button(text=self._t("voice"), disabled=True, **button_style)
        self.voice_button.bind(on_press=lambda *_: self.toggle_voice())
        self.file_button = Button(text=self._t("file"), disabled=True, **button_style)
        self.file_button.bind(on_press=lambda *_: self.choose_file())
        self.members_button = Button(text=self._t("members"), disabled=True, **button_style)
        self.members_button.bind(on_press=lambda *_: self.show_group_members())
        self.orbot_check_button = Button(text=self._t("check_orbot"), **button_style)
        self.orbot_check_button.bind(on_press=lambda *_: self.check_orbot())
        self.diagnostics_button = Button(text=self._t("diagnostics"), **button_style)
        self.diagnostics_button.bind(on_press=lambda *_: self.show_diagnostics())
        for widget in (self.qr_button, self.bluetooth_button, self.contacts_button, self.voice_button, self.file_button, self.members_button, self.orbot_check_button, self.diagnostics_button):
            tools.add_widget(widget)
        sidebar.add_widget(tools)

        settings_row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
        self.auto_delete_label = Label(text=self._t("auto_delete"), color=(0.58, 0.65, 0.78, 1), size_hint_x=None, width=dp(110), font_size=dp(11))
        settings_row.add_widget(self.auto_delete_label)
        self.auto_delete_spinner = Spinner(
            text=self._t("auto_off"),
            values=(self._t("auto_off"), self._t("auto_30s"), self._t("auto_5m")),
            size_hint_x=None,
            width=dp(105),
            background_normal="",
            background_color=(0.12, 0.18, 0.28, 1),
            color=(0.92, 0.95, 1, 1),
            font_size=dp(11),
        )
        self.auto_delete_spinner.bind(text=lambda *_: self._auto_delete_changed())
        settings_row.add_widget(self.auto_delete_spinner)
        self.font_size_label = Label(text=self._t("font_size"), color=(0.58, 0.65, 0.78, 1), size_hint_x=None, width=dp(66), font_size=dp(10))
        self.font_minus_button = Button(text="A−", size_hint_x=None, width=dp(38), background_normal="", background_color=(0.12, 0.18, 0.28, 1), font_size=dp(10))
        self.font_reset_button = Button(text="A", size_hint_x=None, width=dp(38), background_normal="", background_color=(0.12, 0.18, 0.28, 1), font_size=dp(10))
        self.font_plus_button = Button(text="A+", size_hint_x=None, width=dp(38), background_normal="", background_color=(0.12, 0.18, 0.28, 1), font_size=dp(10))
        self.font_minus_button.bind(on_press=lambda *_: self.set_font_scale(self.font_scale - 0.1))
        self.font_reset_button.bind(on_press=lambda *_: self.set_font_scale(1.0))
        self.font_plus_button.bind(on_press=lambda *_: self.set_font_scale(self.font_scale + 0.1))
        font_row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(4))
        font_row.add_widget(self.font_size_label)
        font_row.add_widget(self.font_minus_button)
        font_row.add_widget(self.font_reset_button)
        font_row.add_widget(self.font_plus_button)
        sidebar.add_widget(font_row)
        if desktop_layout:
            root.add_widget(sidebar)
        else:
            # Android/màn hình hẹp: giữ chat luôn nhìn thấy và cho phần cấu hình
            # cuộn độc lập thay vì đẩy composer ra khỏi màn hình.
            sidebar_scroll = ScrollView(
                size_hint_y=None,
                height=dp(255),
                do_scroll_x=False,
                bar_width=dp(4),
            )
            sidebar_scroll.add_widget(sidebar)
            root.add_widget(sidebar_scroll)

        content = BoxLayout(orientation="vertical", padding=[dp(14), dp(12)], spacing=dp(8), size_hint_x=1, size_hint_y=1)
        self.connection_label = Label(text=self._t("status_ready"), color=(0.58, 0.65, 0.78, 1), halign="left", valign="middle", size_hint_y=None, height=dp(28))
        self.connection_label.bind(size=self._sync_text_size)
        content.add_widget(self.connection_label)

        invite_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        self.invite_address_label = Label(text="", color=(0.72, 0.80, 0.92, 1), halign="left", valign="middle", shorten=True, shorten_from="right")
        self.invite_address_label.bind(size=self._sync_text_size)
        self.copy_address_button = Button(text=self._t("copy"), size_hint_x=None, width=dp(86), background_normal="", background_color=(0.12, 0.18, 0.28, 1), disabled=True, font_size=dp(11))
        self.copy_address_button.bind(on_press=lambda *_: self.copy_address())
        self.share_address_button = Button(text=self._t("share"), size_hint_x=None, width=dp(86), background_normal="", background_color=(0.12, 0.18, 0.28, 1), disabled=True, font_size=dp(11))
        self.share_address_button.bind(on_press=lambda *_: self.share_address())
        invite_row.add_widget(self.invite_address_label)
        invite_row.add_widget(self.copy_address_button)
        invite_row.add_widget(self.share_address_button)
        content.add_widget(invite_row)

        quick_actions = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
        quick_style = dict(background_normal="", background_color=(0.12, 0.18, 0.28, 1), font_size=dp(10))
        self.paste_button = Button(text=self._t("paste"), **quick_style)
        self.paste_button.bind(on_press=lambda *_: self.paste_invite())
        self.fingerprint_button = Button(text=self._t("fingerprint"), disabled=True, **quick_style)
        self.fingerprint_button.bind(on_press=lambda *_: self.copy_fingerprint())
        self.clear_chat_button = Button(text=self._t("clear_chat"), **quick_style)
        self.clear_chat_button.bind(on_press=lambda *_: self.confirm_clear_chat())
        self.copy_invite_button = Button(text=self._t("copy_invite"), **quick_style)
        self.copy_invite_button.bind(on_press=lambda *_: self.copy_invite())
        quick_actions.add_widget(self.copy_invite_button)
        quick_actions.add_widget(self.paste_button)
        quick_actions.add_widget(self.fingerprint_button)
        quick_actions.add_widget(self.clear_chat_button)
        self.export_button = Button(text=self._t("export"), **quick_style)
        self.export_button.bind(on_press=lambda *_: self.export_chat())
        quick_actions.add_widget(self.export_button)
        content.add_widget(quick_actions)

        search_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
        self.search_input = TextInput(
            hint_text=self._t("search_hint"),
            multiline=False,
            padding=[dp(12), dp(9)],
            background_normal="",
            background_color=(0.11, 0.15, 0.23, 1),
            foreground_color=(0.92, 0.95, 1, 1),
            hint_text_color=(0.45, 0.53, 0.67, 1),
        )
        self.search_input.bind(on_text_validate=lambda *_: self.apply_search())
        self.search_button = Button(text=self._t("search"), size_hint_x=None, width=dp(70), **quick_style)
        self.search_button.bind(on_press=lambda *_: self.apply_search())
        self.clear_search_button = Button(text=self._t("clear_search"), size_hint_x=None, width=dp(90), **quick_style)
        self.clear_search_button.bind(on_press=lambda *_: self.clear_search())
        search_row.add_widget(self.search_input)
        search_row.add_widget(self.search_button)
        search_row.add_widget(self.clear_search_button)
        content.add_widget(search_row)

        chat_panel = BoxLayout(orientation="vertical", padding=[dp(12), dp(10)], spacing=dp(6), size_hint_y=1)
        with chat_panel.canvas.before:
            Color(0.055, 0.08, 0.13, 1)
            chat_bg = RoundedRectangle(pos=chat_panel.pos, size=chat_panel.size, radius=[dp(16)])
        chat_panel.bind(pos=lambda w, p: setattr(chat_bg, "pos", w.pos))
        chat_panel.bind(size=lambda w, s: setattr(chat_bg, "size", w.size))
        self.chat_title = Label(text="[b]TIN NHẮN[/b]  [color=#93A4C3]Kênh E2EE[/color]", markup=True, halign="left", size_hint_y=None, height=dp(25))
        chat_panel.add_widget(self.chat_title)
        scroll = ScrollView(do_scroll_x=False)
        self.chat_log = TextInput(readonly=True, multiline=True, size_hint_y=None, padding=[dp(14), dp(12)], background_normal="", background_color=(0.04, 0.06, 0.10, 1), foreground_color=(0.86, 0.90, 0.97, 1), cursor_color=(0, 0, 0, 0), font_size=dp(16), line_height=1.35)
        self.chat_log.bind(minimum_height=self.chat_log.setter("height"))
        scroll.add_widget(self.chat_log)
        chat_panel.add_widget(scroll)
        content.add_widget(chat_panel)

        reaction_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
        self.reaction_label = Label(text=self._t("reaction"), color=(0.58, 0.65, 0.78, 1), size_hint_x=None, width=dp(72), font_size=dp(11))
        reaction_row.add_widget(self.reaction_label)
        for emoji in ("👍", "❤️", "😂", "😮", "🎉"):
            reaction_button = Button(text=emoji, font_size=dp(20), background_normal="", background_color=(0.12, 0.18, 0.28, 1), disabled=True)
            reaction_button.bind(on_press=lambda _btn, value=emoji: self.send_reaction(value))
            reaction_row.add_widget(reaction_button)
        self.reaction_buttons = reaction_row.children[0:5]
        content.add_widget(reaction_row)

        compose = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(7))
        self.message_input = TextInput(hint_text=self._t("message_hint"), multiline=False, disabled=True, padding=[dp(14), dp(13)], background_normal="", background_color=(0.11, 0.15, 0.23, 1), foreground_color=(0.92, 0.95, 1, 1), hint_text_color=(0.45, 0.53, 0.67, 1))
        self.message_input.bind(on_text_validate=self.send_message)
        self.reply_button = Button(text=self._t("reply"), size_hint_x=None, width=dp(78), disabled=True, background_normal="", background_color=(0.12, 0.18, 0.28, 1), font_size=dp(11))
        self.reply_button.bind(on_press=lambda *_: self._prepare_reply())
        self.send_button = Button(text=self._t("send"), size_hint_x=None, width=dp(76), disabled=True, background_normal="", background_color=(0.15, 0.63, 0.48, 1), bold=True)
        self.send_button.bind(on_press=self.send_message)
        compose.add_widget(self.reply_button)
        compose.add_widget(self.message_input)
        compose.add_widget(self.send_button)
        content.add_widget(compose)
        root.add_widget(content)

        self._append_log(self._t("log_ready"))
        atexit.register(self.stop_connection)
        return root

    def _t(self, key: str) -> str:
        return self.TEXTS[self.language][key]

    def _transport_value(self, key: str) -> str:
        return self.TRANSPORT_LABELS[key][self.language]

    def _group_mode_value(self, key: str) -> str:
        return self.GROUP_MODE_LABELS[key][self.language]

    def _group_mode_key(self) -> str:
        for key in ("DIRECT", "A", "B"):
            if self.group_mode_spinner.text == self._group_mode_value(key):
                return key
        return "DIRECT"

    def _security_value(self, key: str) -> str:
        return self.SECURITY_LABELS[key][self.language]

    def _security_key(self) -> str:
        for key in ("BALANCED", "STRICT"):
            if self.security_level_spinner.text == self._security_value(key):
                return key
        return "BALANCED"

    def _role_value(self, key: str) -> str:
        return self.ROLE_LABELS[key][self.language]

    def _transport_key(self) -> str:
        for key in ("LAN", "PUBLIC", "TOR", "ORBOT"):
            if self.transport.text == self._transport_value(key):
                return key
        return "LAN"

    def _role_key(self) -> str:
        return "HOST" if self.role.text == self._role_value("HOST") else "JOIN"

    def set_language(self, language: str):
        """Đổi ngôn ngữ giao diện mà không thay đổi trạng thái phiên mạng."""
        if language not in self.TEXTS or not hasattr(self, "transport"):
            self.language = language if language in self.TEXTS else "vi"
            return
        transport_key = self._transport_key()
        role_key = self._role_key()
        group_key = self._group_mode_key()
        security_key = self._security_key()
        self.language = language
        self.transport.values = tuple(self._transport_value(key) for key in ("LAN", "PUBLIC", "TOR", "ORBOT"))
        self.transport.text = self._transport_value(transport_key)
        self.role.values = (self._role_value("HOST"), self._role_value("JOIN"))
        self.role.text = self._role_value(role_key)
        self.group_mode_spinner.values = tuple(self._group_mode_value(key) for key in ("DIRECT", "A", "B"))
        self.group_mode_spinner.text = self._group_mode_value(group_key)
        self.security_level_spinner.values = tuple(self._security_value(key) for key in ("BALANCED", "STRICT"))
        self.security_level_spinner.text = self._security_value(security_key)
        self.group_mode = group_key
        self.security_level = security_key
        self.title_label.text = f"[b]CloakChat[/b]\n[size=12][color=#93A4C3]{self._t('subtitle')}[/color][/size]"
        self.connection_header.text = f"[b]{self._t('connection')}[/b]  [color=#93A4C3]{self._t('choose_connection')}[/color]"
        self.network_label.text = self._t("network")
        self.role_label.text = self._t("role")
        self.group_mode_label.text = self._t("group_mode")
        self.security_level_label.text = self._t("security_level")
        self.start_button.text = self._t("start")
        self.stop_button.text = self._t("stop")
        self.qr_button.text = self._t("qr")
        self.bluetooth_button.text = self._t("bluetooth")
        self.contacts_button.text = self._t("contacts")
        self.file_button.text = self._t("file")
        self.members_button.text = self._t("members")
        self.reply_button.text = self._t("reply")
        self.paste_button.text = self._t("paste")
        self.fingerprint_button.text = self._t("fingerprint")
        self.copy_invite_button.text = self._t("copy_invite")
        self.clear_chat_button.text = self._t("clear_chat")
        self.export_button.text = self._t("export")
        self.search_input.hint_text = self._t("search_hint")
        self.search_button.text = self._t("search")
        self.clear_search_button.text = self._t("clear_search")
        self.details_button.text = self._t("details")
        self.settings_toggle_button.text = self._t("hide_settings" if self.settings_expanded else "show_settings")
        self.orbot_port_input.hint_text = self._t("orbot_port")
        self.orbot_check_button.text = self._t("check_orbot")
        self.diagnostics_button.text = self._t("diagnostics")
        self.font_size_label.text = self._t("font_size")
        self.auto_delete_label.text = self._t("auto_delete")
        self.auto_delete_spinner.values = (self._t("auto_off"), self._t("auto_30s"), self._t("auto_5m"))
        self.auto_delete_spinner.text = self._auto_delete_label()

        self.nickname_input.hint_text = self._t("nickname")
        self.copy_address_button.text = self._t("copy")
        self.share_address_button.text = self._t("share")
        if self.voice is None:
            self.voice_button.text = self._t("voice")
        self.chat_title.text = f"[b]{self._t('chat')}[/b]  [color=#93A4C3]{self._t('channel')}[/color]"
        self.reaction_label.text = self._t("reaction")
        self.message_input.hint_text = self._t("message_hint")
        self.security_badge.text = f"●  E2EE\n[size=11]{self._t('secure' if self.session else 'ready')}[/size]"
        self.connection_label.text = self._t("status_connected" if self.session else "status_ready")
        if self.current_address:
            self._set_invite_address(self.current_address)
        self._role_changed()

    @staticmethod
    def _sync_text_size(widget, _size):
        widget.text_size = (widget.width - dp(8), widget.height)

    def toggle_settings(self):
        """Thu gọn card cấu hình trên Android để ưu tiên vùng chat."""
        self.settings_expanded = not self.settings_expanded
        self.connection_card.opacity = 1 if self.settings_expanded else 0
        self.connection_card.disabled = not self.settings_expanded
        self.connection_card.height = dp(218) if self.settings_expanded else 0
        self.settings_toggle_button.text = self._t("hide_settings" if self.settings_expanded else "show_settings")

    def show_session_details(self):
        if not self.session and not self.group_host:
            self._append_log(f"[!] {self._t('no_session_details')}")
            return
        transport = self._transport_key()
        role = self._role_key()
        group = self._group_mode_key()
        fingerprint = "—"
        if self.session and self.session.remote_public:
            fingerprint = core.sha512_fingerprint(self.session.local_public, self.session.remote_public)
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(9))
        content.add_widget(Label(text=(
            f"{self._t('transport_detail')}: {self._transport_value(transport)}\n"
            f"{self._t('role_detail')}: {self._role_value(role)}\n"
            f"{self._t('group_detail')}: {self._group_mode_value(group)}\n"
            f"{self._t('security_detail')}: {self._security_value(self._security_key())}\n\n"
            f"{self._t('fingerprint_detail')}:\n{fingerprint}"
        ), halign="left", valign="middle"))
        close_button = Button(text=self._t("cancel"), size_hint_y=None, height=dp(42))
        content.add_widget(close_button)
        popup = Popup(title=self._t("session_details_title"), content=content, size_hint=(0.94, 0.56), auto_dismiss=False)
        close_button.bind(on_press=lambda *_: popup.dismiss())
        popup.open()

    def _role_changed(self):
        """Host không cần nhập địa chỉ; Join mới dùng ô invite."""
        if hasattr(self, "address") and hasattr(self, "role"):
            is_join = self._role_key() == "JOIN"
            is_public_host = self._role_key() == "HOST" and self._transport_key() == "PUBLIC"
            self.address.disabled = not (is_join or is_public_host)
            self.address.opacity = 1 if (is_join or is_public_host) else 0.55
            if is_public_host:
                self.address.hint_text = self._t("address_public")
            elif is_join:
                self.address.hint_text = self._t("address_invite")
            else:
                self.address.hint_text = self._t("address_host")

    def _auto_delete_label(self) -> str:
        if self.auto_delete_seconds == 30:
            return self._t("auto_30s")
        if self.auto_delete_seconds == 300:
            return self._t("auto_5m")
        return self._t("auto_off")

    def _auto_delete_changed(self):
        value = self.auto_delete_spinner.text
        if value == self._t("auto_30s"):
            self.auto_delete_seconds = 30
        elif value == self._t("auto_5m"):
            self.auto_delete_seconds = 300
        else:
            self.auto_delete_seconds = 0

    def _render_log(self):
        query = self.search_query.casefold().strip()
        entries = (
            [entry for entry in self.log_entries if query in entry["text"].casefold()]
            if query
            else self.log_entries
        )
        self.chat_log.text = "\n".join(entry["text"] for entry in entries) + ("\n" if entries else "")
        self.chat_log.cursor = (0, len(self.chat_log.text))

    def apply_search(self):
        """Lọc log cục bộ; không gửi query hoặc nội dung chat qua mạng."""
        self.search_query = self.search_input.text.strip()
        self._render_log()

    def clear_search(self):
        self.search_query = ""
        self.search_input.text = ""
        self._render_log()

    def export_chat(self):
        """Xuất transcript local, không bao gồm private key, session key hay invite."""
        export_dir = Path(self.user_data_dir) / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        filename = time.strftime("cloakchat_%Y%m%d_%H%M%S.txt")
        target = export_dir / filename
        target.write_text("\n".join(entry["text"] for entry in self.log_entries) + "\n", encoding="utf-8")
        self._append_log(f"[+] {self._t('export_saved')}: {target}", delete_after=8)

    def _expire_log_entry(self, entry_id: str):
        self.log_entries[:] = [entry for entry in self.log_entries if entry["id"] != entry_id]
        self._render_log()

    def _append_log(self, text: str, message_id: Optional[str] = None, delete_after: Optional[int] = None):
        """Cập nhật UI trên main thread; auto-delete chỉ xóa bản sao cục bộ."""
        entry_id = message_id or secrets.token_hex(8)
        self.log_entries.append({"id": entry_id, "text": text.rstrip()})
        self._render_log()
        lifetime = delete_after if delete_after is not None else self.auto_delete_seconds
        if lifetime > 0 and message_id:
            Clock.schedule_once(lambda _dt, eid=entry_id: self._expire_log_entry(eid), lifetime)

    def _status_from_worker(self, text: str):
        Clock.schedule_once(lambda _dt: self._append_log(text), 0)

    def _set_connection_label(self, text: str):
        self.connection_label.text = text

    def retry_connection(self):
        """Thử lại cấu hình kết nối gần nhất mà không cần nhập lại trên Android."""
        if self.worker and self.worker.is_alive():
            return
        self.start_connection()

    def start_connection(self, *_args):
        if self.worker and self.worker.is_alive():
            return
        self.has_attempted_connection = True
        self.stop_event.clear()
        self.start_button.disabled = True
        self.stop_button.disabled = False
        self.retry_button.disabled = True
        self.transport.disabled = True
        self.role.disabled = True
        # Public Host cần giữ ô địa chỉ mở để worker đọc IP do người dùng nhập;
        # Host LAN/Tor vẫn khóa vì địa chỉ được tạo tự động.
        is_public_host = self._role_key() == "HOST" and self._transport_key() == "PUBLIC"
        self.address.disabled = not (self._role_key() == "JOIN" or is_public_host)
        self.worker = threading.Thread(
            target=self._connection_worker,
            name="cloakchat-gui-worker",
            daemon=True,
        )
        self.worker.start()

    def _connection_worker(self):
        try:
            transport_key = self._transport_key()
            is_tor = transport_key == "TOR"
            is_public = transport_key == "PUBLIC"
            is_orbot = transport_key == "ORBOT"
            is_host = self._role_key() == "HOST"
            group_mode = self._group_mode_key()
            security_level = self._security_key()
            self.group_mode = group_mode
            self.security_level = security_level
            if group_mode == "A" and security_level == "STRICT":
                raise GroupProtocolError(self._t("security_warning"))
            if is_orbot and is_host:
                raise ValueError(self._t("orbot_join_only"))
            if is_host and group_mode in ("A", "B"):
                self._prepare_group_host(is_tor, is_public, group_mode)
                return
            if is_host:
                connection = self._prepare_host(is_tor, is_public)
            else:
                connection = self._prepare_join(is_tor, is_public, is_orbot)
            if self.stop_event.is_set():
                connection.close()
                return

            self.session = core.ChatSession(
                connection,
                is_host=is_host,
                confirm_callback=self._confirm_safety_number,
                message_callback=self._message_from_peer,
                message_event_callback=self._message_event_from_peer,
                reaction_callback=self._reaction_from_peer,
                reaction_event_callback=self._reaction_event_from_peer,
                group_mode=group_mode == "B",
                group_event_callback=self._group_event_from_peer,
                group_key_callback=self._group_key_ready,
                status_callback=self._status_from_worker,
                nickname=self.nickname_input.text.strip() or "Anonymous",
                profile_callback=self._profile_from_peer,
                file_callback=self._file_from_peer,
            )
            self._status_from_worker("[*] Đang trao đổi khóa và chờ xác nhận SHA-512 fingerprint...")
            self.session.handshake_and_confirm()
            if self.stop_event.is_set():
                return
            self.session.start_receiver()
            Clock.schedule_once(self._chat_ready, 0)
        except PermissionError as exc:
            self._status_from_worker(f"[!] {exc}")
            self._reset_ui()
        except (ConnectionError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            self._status_from_worker(f"[!] Không thể kết nối: {exc}")
            self._reset_ui()
        except Exception as exc:
            self._status_from_worker(f"[!] Lỗi UI không mong muốn: {exc}")
            self._reset_ui()

    def _prepare_group_host(self, is_tor: bool, is_public: bool = False, mode: str = "A") -> None:
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_host = core.SOCKS_HOST if is_tor else "0.0.0.0"
        self.listener.bind((bind_host, 0))
        port = self.listener.getsockname()[1]
        self.listener.listen(8)
        self.listener.settimeout(1.0)
        if is_tor:
            self.daemon = core.TorDaemon()
            self.daemon.start()
            address = self.daemon.create_ephemeral_service(port)
            invite_transport = "tor"
        elif is_public:
            public_ip = self.address.text.strip()
            if not public_ip:
                raise ValueError("Host IP công cộng cần nhập IP public trước khi bắt đầu.")
            address = f"{public_ip}:{port}"
            invite_transport = "public"
        else:
            address = f"{core.get_local_ipv4()}:{port}"
            invite_transport = "lan"
        self.current_address = address
        self.current_invite = create_invite(invite_transport, address, "CloakChat Group Host")
        self.group_host = GroupHost(self.listener, nickname=self.nickname_input.text.strip() or "Host", mode=MODE_TRUE_E2EE if mode == "B" else MODE_HOST_RELAY, confirm_callback=self._confirm_safety_number, status_callback=self._status_from_worker, event_callback=self._group_event_from_host)
        self.group_host.start()
        Clock.schedule_once(lambda _dt: self._set_invite_address(address), 0)
        Clock.schedule_once(lambda _dt: self._enable_share_buttons(), 0)
        Clock.schedule_once(self._group_ready, 0)
        self._status_from_worker(self._t("group_b_ready" if mode == "B" else "group_ready"))

    def _group_ready(self, _dt):
        self.details_button.disabled = False
        self.connection_label.text = self._t("group_b_ready" if self.group_mode == "B" else "group_ready")
        self.message_input.disabled = False
        self.send_button.disabled = False
        self._enable_reactions(True)
        self.file_button.disabled = False
        self.members_button.disabled = False
        self.voice_button.disabled = True

    def _group_event_from_host(self, event: dict):
        if event.get("type") == "profile":
            self._status_from_worker(f"[GROUP] {event.get('nickname', 'Peer')} joined.")
        elif event.get("type") == "file_sent":
            self._status_from_worker(f"[+] {self._t('file_sent')}: {event.get('filename', '')}")
        elif "text" in event:
            nickname = event.get("nickname", "Peer")
            reply_note = f" ↪ {event['reply_to']}" if event.get("reply_to") else ""
            self._status_from_worker(f"{nickname}{reply_note}: {event['text']}")
        elif event.get("type") == "reaction":
            self._status_from_worker(f"Peer reaction: {event.get('reaction', '')}")

    def _group_event_from_peer(self, event: dict):
        event_type = event.get("type")
        if event_type == "message":
            self.last_peer_message_id = event.get("id")
            nickname = event.get("nickname", "Peer")
            reply_note = f" ↪ {event['reply_to']}" if event.get("reply_to") else ""
            Clock.schedule_once(lambda _dt: self._append_log(f"{nickname}{reply_note}: {event.get('text', '')}", message_id=event.get('id')), 0)
            if hasattr(self, "reply_button"):
                Clock.schedule_once(lambda _dt: setattr(self.reply_button, "disabled", False), 0)
        elif event_type == "reaction":
            target = f" ({event['message_id'][:8]})" if event.get("message_id") else ""
            Clock.schedule_once(lambda _dt: self._append_log(f"Peer reaction{target}: {event.get('reaction', '')}"), 0)

    def _prepare_host(self, is_tor: bool, is_public: bool = False) -> socket.socket:
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_host = core.SOCKS_HOST if is_tor else "0.0.0.0"
        self.listener.bind((bind_host, 0))
        port = self.listener.getsockname()[1]
        self.listener.listen(1)

        if is_tor:
            self.daemon = core.TorDaemon()
            self.daemon.start()
            onion = self.daemon.create_ephemeral_service(port)
            address = onion
            self._status_from_worker("[TOR HOST] Onion service đã được công bố.")
            invite_transport = "tor"
        elif is_public:
            public_ip = self.address.text.strip()
            if not public_ip:
                raise ValueError("Host IP công cộng cần nhập IP public trước khi bắt đầu.")
            address = f"{public_ip}:{port}"
            self._status_from_worker("[PUBLIC HOST] Kết nối TCP công cộng trực tiếp; Tor không được dùng.")
            invite_transport = "public"
        else:
            address = f"{core.get_local_ipv4()}:{port}"
            self._status_from_worker("[LAN HOST] Tor không được khởi động.")
            invite_transport = "lan"
        self.current_address = address
        self.current_invite = create_invite(invite_transport, address, "CloakChat Host")
        Clock.schedule_once(lambda _dt: self._set_invite_address(address), 0)
        Clock.schedule_once(lambda _dt: self._enable_share_buttons(), 0)

        connection = self._accept_connection(is_tor)
        self.listener.close()
        self.listener = None
        return connection

    def _accept_connection(self, is_tor: bool) -> socket.socket:
        assert self.listener is not None
        self.listener.settimeout(1.0)
        transport = "Tor" if is_tor else "LAN"
        self._status_from_worker(f"[*] Đang chờ kết nối {transport}...")
        while not self.stop_event.is_set():
            try:
                connection, peer = self.listener.accept()
                self._status_from_worker(f"[+] Peer đã kết nối từ {peer[0]}.")
                return connection
            except socket.timeout:
                continue
        raise KeyboardInterrupt

    def _prepare_join(
        self,
        is_tor: bool,
        is_public: bool = False,
        is_orbot: bool = False,
    ) -> socket.socket:
        value = self.address.text.strip()
        if value.startswith("CLOAKCHAT:"):
            invite = parse_invite(value)
            value = invite["address"]
            is_tor = invite["transport"] == "tor"
            is_public = invite["transport"] == "public"
            self._status_from_worker(
                f"[*] Đã đọc invite {invite['transport']} từ QR/danh bạ."
            )
        if not value:
            raise ValueError("Hãy nhập địa chỉ của Host trước khi Join.")
        if is_orbot:
            socks_port = self._prepare_orbot()
            self._status_from_worker(
                f"[*] Orbot SOCKS5 sẵn sàng tại 127.0.0.1:{socks_port}."
                if self.language == "vi"
                else f"[*] Orbot SOCKS5 ready at 127.0.0.1:{socks_port}."
            )
            return core.create_orbot_join_socket(value, socks_port=socks_port)
        if is_tor:
            self.daemon = core.TorDaemon()
            self.daemon.start()
            self._status_from_worker("[*] Đang kết nối .onion qua SOCKS5 Tor...")
            return core.create_join_socket(value, socks_port=self.daemon.socks_port)
        if is_public:
            self._status_from_worker("[*] Đang kết nối IP công cộng trực tiếp; Tor không được dùng...")
            return core.create_public_socket(value)
        self._status_from_worker("[*] Đang kết nối IP nội bộ trực tiếp; Tor không được dùng...")
        return core.create_lan_socket(value)

    def set_font_scale(self, scale: float):
        """Điều chỉnh cỡ chữ cục bộ, hữu ích trên màn hình Android nhỏ."""
        self.font_scale = max(0.85, min(1.25, round(scale, 2)))
        base = dp(16) * self.font_scale
        self.chat_log.font_size = base
        self.message_input.font_size = base
        self.search_input.font_size = dp(14) * self.font_scale
        self.nickname_input.font_size = dp(14) * self.font_scale
        self.address.font_size = dp(14) * self.font_scale

    def show_diagnostics(self):
        details = self.last_diagnostics or self._t("diagnostics_empty")
        content = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(9))
        content.add_widget(Label(text=details, halign="left", valign="top"))
        close_button = Button(text=self._t("cancel"), size_hint_y=None, height=dp(42))
        content.add_widget(close_button)
        popup = Popup(title=self._t("diagnostics_title"), content=content, size_hint=(0.94, 0.62), auto_dismiss=False)
        close_button.bind(on_press=lambda *_: popup.dismiss())
        popup.open()

    def _orbot_candidate_ports(self):
        """Trả về các cổng SOCKS5 cần thử; biến môi trường luôn được ưu tiên."""
        configured = self.orbot_port_input.text.strip() or os.environ.get("CLOAKCHAT_ORBOT_SOCKS_PORT", "").strip()
        if configured:
            try:
                port = int(configured)
            except ValueError as exc:
                raise ValueError("CLOAKCHAT_ORBOT_SOCKS_PORT must be a valid port." if self.language == "en" else "CLOAKCHAT_ORBOT_SOCKS_PORT phải là cổng hợp lệ.") from exc
            if not 1 <= port <= 65535:
                raise ValueError("Orbot SOCKS5 port must be between 1 and 65535." if self.language == "en" else "Cổng Orbot SOCKS5 phải nằm trong khoảng 1-65535.")
            return [port]
        return list(dict.fromkeys((core.ORBOT_SOCKS_PORT, 9150)))

    def check_orbot(self):
        """Kiểm tra Orbot trên worker thread để giao diện Android không bị treo."""
        if self.worker and self.worker.is_alive():
            return
        threading.Thread(target=self._check_orbot_worker, name="cloakchat-orbot-check", daemon=True).start()

    def _check_orbot_worker(self):
        try:
            self._status_from_worker(self._t("orbot_checking"))
            port = self._prepare_orbot()
            self._status_from_worker(f"[+] {self._t('orbot_ready')}: 127.0.0.1:{port}")
        except Exception as exc:
            self._status_from_worker(f"[!] {exc}")

    def _prepare_orbot(self) -> int:
        """Mở Orbot trên Android và chờ SOCKS5 listener sẵn sàng."""
        if platform != "android":
            raise RuntimeError(self._t("orbot_not_android"))
        candidate_ports = self._orbot_candidate_ports()
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            package_manager = activity.getPackageManager()
            package_name = "org.torproject.android"
            intent = package_manager.getLaunchIntentForPackage(package_name)
            if intent is None:
                Intent = autoclass("android.content.Intent")
                intent = Intent(Intent.ACTION_MAIN)
                intent.addCategory(Intent.CATEGORY_LAUNCHER)
                intent.setPackage(package_name)
            activity.startActivity(intent)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(self._t("orbot_not_installed")) from exc

        self._status_from_worker(self._t("orbot_wait"))
        deadline = time.monotonic() + 45.0
        last_errors = []
        while time.monotonic() < deadline and not self.stop_event.is_set():
            for socks_port in candidate_ports:
                try:
                    probe = socket.create_connection((core.SOCKS_HOST, socks_port), timeout=1.0)
                    probe.close()
                    self.last_diagnostics = f"Orbot SOCKS5: 127.0.0.1:{socks_port}\nPorts tried: {', '.join(str(port) for port in candidate_ports)}"
                    return socks_port
                except OSError as exc:
                    last_errors.append(f"{socks_port}: {exc}")
            time.sleep(1.0)
        ports = ", ".join(str(port) for port in candidate_ports)
        self.last_diagnostics = (
            f"Ports tried: {ports}\n"
            f"Errors: {'; '.join(last_errors[-6:])}\n"
            "Next steps: open Orbot, wait for Connected, verify the port, and use a fresh onion address."
        )
        raise TimeoutError(
            f"Orbot SOCKS5 was not ready on ports {ports} within 45 seconds. "
            "Open Orbot, wait until it is connected, or set CLOAKCHAT_ORBOT_SOCKS_PORT."
            if self.language == "en"
            else f"Orbot SOCKS5 chưa sẵn sàng ở cổng {ports} sau 45 giây. Hãy mở Orbot, chờ trạng thái đã kết nối hoặc đặt CLOAKCHAT_ORBOT_SOCKS_PORT."
        )

    def _set_invite_address(self, address: str):
        if hasattr(self, "invite_address_label"):
            self.invite_address_label.text = f"{self._t('invite_label')} {address}"

    def copy_address(self):
        if not self.current_address:
            self._append_log("[!] Chưa có địa chỉ Host để sao chép." if self.language == "vi" else "[!] No host address to copy.")
            return
        Clipboard.copy(self.current_address)
        self._append_log(f"[+] {self._t('copied')}")

    def share_address(self):
        payload = self.current_invite or self.current_address
        if not payload:
            self._append_log("[!] Chưa có địa chỉ/invite để chia sẻ." if self.language == "vi" else "[!] No address/invite to share.")
            return
        if share_invite(payload):
            self._append_log(f"[+] {self._t('shared')}")
        else:
            Clipboard.copy(payload)
            self._append_log(f"[+] {self._t('share_desktop')}")

    def copy_invite(self):
        """Sao chép payload invite đầy đủ, gồm checksum nhưng không gồm khóa bí mật."""
        payload = self.current_invite or self.current_address or self.address.text.strip()
        if not payload:
            self._append_log("[!] Chưa có invite để sao chép." if self.language == "vi" else "[!] No invite to copy.")
            return
        try:
            Clipboard.copy(payload)
            self._append_log(f"[+] {self._t('copied')}")
        except Exception as exc:
            self._append_log(f"[!] Clipboard unavailable: {exc}")

    def paste_invite(self):
        """Nạp invite hoặc địa chỉ từ clipboard, không đọc private/session key."""
        try:
            value = (Clipboard.paste() or "").strip()
        except Exception as exc:
            self._append_log(f"[!] Clipboard unavailable: {exc}")
            return
        if not value:
            self._append_log("[!] Clipboard đang trống." if self.language == "vi" else "[!] Clipboard is empty.")
            return
        self.address.text = value
        if value.startswith("CLOAKCHAT:"):
            try:
                parsed = parse_invite(value)
                transport_key = {"tor": "TOR", "public": "PUBLIC", "lan": "LAN"}[parsed["transport"]]
                self.transport.text = self._transport_value(transport_key)
                self.role.text = self._role_value("JOIN")
                self._append_log("[+] Đã nạp invite từ clipboard." if self.language == "vi" else "[+] Invite loaded from clipboard.")
            except (KeyError, ValueError) as exc:
                self._append_log(f"[!] Invite không hợp lệ: {exc}" if self.language == "vi" else f"[!] Invalid invite: {exc}")
        else:
            self._append_log("[+] Đã dán địa chỉ vào ô Join." if self.language == "vi" else "[+] Address pasted into the Join field.")

    def copy_fingerprint(self):
        """Sao chép fingerprint đã tính từ hai public key X25519 của phiên."""
        if not self.session or not self.session.remote_public:
            self._append_log(f"[!] {self._t('no_fingerprint')}")
            return
        fingerprint = core.sha512_fingerprint(self.session.local_public, self.session.remote_public)
        try:
            Clipboard.copy(fingerprint)
            self._append_log(f"[+] {self._t('fingerprint_copied')}")
        except Exception as exc:
            self._append_log(f"[!] Clipboard unavailable: {exc}")

    def confirm_clear_chat(self):
        """Xóa log hiển thị cục bộ; không gửi lệnh xóa cho peer."""
        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        content.add_widget(Label(text=self._t("clear_chat_confirm"), halign="left", valign="middle"))
        buttons = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        clear_button = Button(text=self._t("clear_chat"), background_normal="", background_color=(0.55, 0.18, 0.23, 1))
        cancel_button = Button(text=self._t("cancel"))
        buttons.add_widget(clear_button)
        buttons.add_widget(cancel_button)
        content.add_widget(buttons)
        popup = Popup(title=self._t("clear_chat_title"), content=content, size_hint=(0.9, 0.36), auto_dismiss=False)
        clear_button.bind(on_press=lambda *_: self._clear_local_chat(popup))
        cancel_button.bind(on_press=lambda *_: popup.dismiss())
        popup.open()

    def _clear_local_chat(self, popup):
        popup.dismiss()
        self.log_entries.clear()
        self._render_log()
        self._append_log(f"[+] {self._t('chat_cleared')}", delete_after=8)

    def _confirm_safety_number(self, number: str) -> bool:
        """Hiển thị popup trên UI và chặn worker đến khi người dùng chọn."""
        self.confirm_event = threading.Event()
        self.confirm_result = False
        Clock.schedule_once(lambda _dt: self._show_safety_popup(number), 0)
        self.confirm_event.wait(timeout=core.CONFIRM_TIMEOUT)
        return self.confirm_result

    def _show_safety_popup(self, number: str):
        content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        content.add_widget(
            Label(
                text=(
                    f"{self._t('safety_prompt')}:\n\n"
                    f"[b]{number}[/b]\n\n{self._t('safety_question')}"
                ),
                markup=True,
            )
        )
        buttons = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(8))
        yes = Button(text=self._t("yes"))
        no = Button(text=self._t("no"))
        yes.bind(on_press=lambda *_: self._finish_confirmation(True))
        no.bind(on_press=lambda *_: self._finish_confirmation(False))
        buttons.add_widget(yes)
        buttons.add_widget(no)
        content.add_widget(buttons)
        self.safety_popup = Popup(
            title=self._t("safety_title"),
            content=content,
            size_hint=(0.92, 0.52),
            auto_dismiss=False,
        )
        self.safety_popup.open()

    def _finish_confirmation(self, result: bool):
        self.confirm_result = result
        if self.safety_popup:
            self.safety_popup.dismiss()
            self.safety_popup = None
        if self.confirm_event:
            self.confirm_event.set()

    def _message_from_peer(self, message: str):
        Clock.schedule_once(lambda _dt: self._append_log(f"{getattr(self.session, 'peer_nickname', 'Peer')}: {message}"), 0)

    def _message_event_from_peer(self, event: dict):
        self.last_peer_message_id = event["id"]
        nickname = event.get("nickname") or getattr(self.session, "peer_nickname", "Peer")
        reply_note = f" ↪ {event['reply_to']}" if event.get("reply_to") else ""
        Clock.schedule_once(lambda _dt: self._append_log(f"{nickname}{reply_note}: {event['text']}", message_id=event['id']), 0)
        if hasattr(self, "reply_button"):
            Clock.schedule_once(lambda _dt: setattr(self.reply_button, "disabled", False), 0)

    def _prepare_reply(self):
        if not self.last_peer_message_id:
            return
        self.reply_to_id = self.last_peer_message_id
        self.message_input.hint_text = f"{self._t('replying')} ({self.reply_to_id[:8]})"
        self.message_input.focus = True

    def _profile_from_peer(self, nickname: str):
        Clock.schedule_once(lambda _dt: self._append_log(f"[+] {self._t('peer_joined')}: {nickname}"), 0)

    def _reaction_from_peer(self, reaction: str):
        Clock.schedule_once(lambda _dt: self._append_log(f"Peer reaction: {reaction}"), 0)

    def _reaction_event_from_peer(self, event: dict):
        target = f" ({event['message_id'][:8]})" if event.get("message_id") else ""
        Clock.schedule_once(lambda _dt: self._append_log(f"Peer reaction{target}: {event['reaction']}"), 0)

    def _file_from_peer(self, file_info: dict):
        transfer_id = file_info["transfer_id"]
        state = self.incoming_files.setdefault(
            transfer_id,
            {"filename": file_info["filename"], "total_size": file_info["total_size"], "total_chunks": file_info["total_chunks"], "file_digest": file_info["file_digest"], "next_index": 0, "data": bytearray()},
        )
        if file_info["chunk_index"] != state["next_index"]:
            self.incoming_files.pop(transfer_id, None)
            self._status_from_worker("[!] File chunk out of order; transfer discarded.")
            return
        state["data"].extend(file_info["chunk"])
        state["next_index"] += 1
        if state["next_index"] != state["total_chunks"]:
            return
        payload = bytes(state["data"])
        valid = len(payload) == state["total_size"] and hashlib.sha256(payload).digest() == state["file_digest"]
        self.incoming_files.pop(transfer_id, None)
        if not valid:
            self._status_from_worker("[!] File hash verification failed; file was discarded.")
            return
        received_dir = Path(self.user_data_dir) / "received_files"
        received_dir.mkdir(parents=True, exist_ok=True)
        target = received_dir / state["filename"]
        if target.exists():
            target = received_dir / f"{target.stem}_{int(time.time())}{target.suffix}"
        target.write_bytes(payload)
        self._status_from_worker(f"[+] {self._t('file_received')}: {target}")

    def _enable_reactions(self, enabled: bool):
        for button in getattr(self, "reaction_buttons", []):
            button.disabled = not enabled

    def _enable_share_buttons(self):
        if hasattr(self, "qr_button"):
            self.qr_button.disabled = False
        if hasattr(self, "bluetooth_button"):
            self.bluetooth_button.disabled = False
        if hasattr(self, "copy_address_button"):
            self.copy_address_button.disabled = False
        if hasattr(self, "share_address_button"):
            self.share_address_button.disabled = False

    def _enable_voice(self, enabled: bool):
        if hasattr(self, "voice_button"):
            self.voice_button.disabled = not enabled
            if not enabled:
                self.voice_button.text = self._t("voice")

    def toggle_voice(self):
        """Bật/tắt voice trên desktop; Android báo rõ nếu chưa có audio backend."""
        if not self.session:
            return
        if self.voice is not None:
            self.voice.stop()
            self.voice = None
            self.voice_button.text = "VOICE"
            self._append_log("[VOICE] Đã tắt voice chat.")
            return
        try:
            self.voice = VoiceChat(self.session, status_callback=self._status_from_worker)
            self.voice.start()
            self.voice_button.text = self._t("voice_off")
        except Exception as exc:
            self.voice = None
            self._append_log(f"[VOICE] Không thể bật voice: {exc}")

    def choose_file(self):
        if not self.session and not self.group_host:
            return
        chooser = FileChooserListView(path=str(Path.home()), multiselect=False)
        buttons = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        send_button = Button(text=self._t("send"))
        cancel_button = Button(text=self._t("no"))
        buttons.add_widget(send_button)
        buttons.add_widget(cancel_button)
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        content.add_widget(chooser)
        content.add_widget(buttons)
        popup = Popup(title=self._t("choose_file"), content=content, size_hint=(0.94, 0.84), auto_dismiss=False)
        send_button.bind(on_press=lambda *_: self._send_selected_file(chooser, popup))
        cancel_button.bind(on_press=lambda *_: popup.dismiss())
        popup.open()

    def _send_selected_file(self, chooser, popup):
        if not chooser.selection:
            return
        path = chooser.selection[0]
        popup.dismiss()
        self._append_log(f"[*] {self._t('choose_file')}: {path}")
        threading.Thread(target=self._send_file_worker, args=(path,), name="cloakchat-file-sender", daemon=True).start()

    def _send_file_worker(self, path: str):
        try:
            if self.group_host:
                self.group_host.send_file(path)
            else:
                self.session.send_file(path)
            self._status_from_worker(f"[+] {self._t('file_sent')}: {Path(path).name}")
        except Exception as exc:
            self._status_from_worker(f"[!] File send failed: {exc}")

    def show_group_members(self):
        if not self.group_host:
            self._append_log(f"[!] {self._t('no_group')}")
            return
        content = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        for member_id, nickname in list(self.group_host.nicknames.items()):
            row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(5))
            row.add_widget(Label(text=f"{nickname} ({member_id[:8]})", halign="left"))
            kick_button = Button(text=self._t("kick"), size_hint_x=None, width=dp(70))
            ban_button = Button(text=self._t("ban"), size_hint_x=None, width=dp(70))
            kick_button.bind(on_press=lambda *_btn, mid=member_id: self._moderate_member(mid, False))
            ban_button.bind(on_press=lambda *_btn, mid=member_id: self._moderate_member(mid, True))
            row.add_widget(kick_button)
            row.add_widget(ban_button)
            content.add_widget(row)
        popup = Popup(title=self._t("members"), content=content, size_hint=(0.94, 0.72))
        popup.open()

    def _moderate_member(self, member_id: str, ban: bool):
        if self.group_host and self.group_host.kick(member_id, ban=ban):
            self._append_log(f"[GROUP] {'Banned' if ban else 'Kicked'} {member_id[:8]}")

    def _stop_voice(self):
        if self.voice is not None:
            self.voice.stop()
            self.voice = None
        if hasattr(self, "voice_button"):
            self.voice_button.text = "VOICE"
            self.voice_button.disabled = True

    def show_qr(self):
        if not self.current_invite:
            self._append_log("[!] Chưa có invite để tạo QR.")
            return
        try:
            output = str(Path(self.user_data_dir) / "cloakchat_invite.png")
            save_qr(self.current_invite, output)
            content = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
            content.add_widget(Image(source=output))
            content.add_widget(Label(text="Quét QR này để lấy invite CloakChat."))
            Popup(title="CloakChat QR invite", content=content, size_hint=(0.9, 0.85)).open()
            self._append_log(f"[+] Đã tạo QR: {output}")
        except Exception as exc:
            self._append_log(f"[!] Không thể tạo QR: {exc}")

    def share_bluetooth(self):
        if not self.current_invite:
            self._append_log("[!] Chưa có invite để chia sẻ.")
            return
        if share_invite(self.current_invite):
            self._append_log("[+] Đã mở bảng chia sẻ Android; chọn Bluetooth nếu muốn.")
        else:
            self._append_log(
                "[!] Bluetooth Sharesheet chỉ được hỗ trợ trực tiếp trên Android. "
                "Desktop có thể dùng QR hoặc sao chép invite."
            )

    def show_contacts(self):
        if not self.contacts:
            return
        content = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(6))
        name_input = TextInput(hint_text="Tên liên hệ để lưu", multiline=False, size_hint_y=None, height=dp(40))
        content.add_widget(name_input)
        save_button = Button(text="Lưu invite hiện tại", size_hint_y=None, height=dp(42))
        content.add_widget(save_button)
        list_layout = BoxLayout(orientation="vertical", spacing=dp(4))
        for item in self.contacts.list_contacts():
            button = Button(text=item.get("name", "(không tên)"), size_hint_y=None, height=dp(40))
            button.bind(on_press=lambda _btn, invite=item.get("invite", ""): self._load_contact(invite))
            list_layout.add_widget(button)
        content.add_widget(list_layout)
        popup = Popup(title="Danh bạ cục bộ", content=content, size_hint=(0.9, 0.8))
        save_button.bind(on_press=lambda *_: self._save_contact_from_popup(name_input, popup))
        popup.open()

    def _save_contact_from_popup(self, name_input, popup):
        if not self.current_invite or not self.contacts:
            self._append_log("[!] Hãy tạo hoặc nhận invite trước.")
            return
        try:
            self.contacts.save(name_input.text, self.current_invite)
            self._append_log(f"[+] Đã lưu liên hệ cục bộ: {name_input.text.strip()}")
            popup.dismiss()
        except ValueError as exc:
            self._append_log(f"[!] {exc}")

    def _load_contact(self, invite: str):
        try:
            parsed = parse_invite(invite)
            self.address.text = invite
            transport_key = "TOR" if parsed["transport"] == "tor" else "PUBLIC" if parsed["transport"] == "public" else "LAN"
            self.transport.text = self._transport_value(transport_key)
            self.role.text = self._role_value("JOIN")
            self._append_log("[+] Invite and transport loaded from contacts." if self.language == "en" else "[+] Đã nạp invite và transport từ danh bạ vào ô địa chỉ.")
        except ValueError as exc:
            self._append_log(f"[!] Invite trong danh bạ không hợp lệ: {exc}")

    def _group_key_ready(self):
        Clock.schedule_once(lambda _dt: self._enable_group_b_client(), 0)

    def _enable_group_b_client(self):
        if self.group_mode != "B":
            return
        self.message_input.disabled = False
        self.send_button.disabled = False
        self._enable_reactions(True)
        self.file_button.disabled = False
        self.connection_label.text = self._t("status_connected")

    def _chat_ready(self, _dt):
        self.details_button.disabled = False
        self.connection_label.text = self._t("status_connected")
        self.security_badge.text = f"●  E2EE\n[size=11]{self._t('secure')}[/size]"
        self.message_input.disabled = self.group_mode == "B"
        self.send_button.disabled = self.group_mode == "B"
        self.fingerprint_button.disabled = False
        self._enable_reactions(self.group_mode != "B")
        self._enable_voice(self.group_mode != "B")
        if hasattr(self, "file_button"):
            self.file_button.disabled = self.group_mode == "B"
        self._append_log("[+] Chat ready. AES-256-GCM encryption is active." if self.language == "en" else "[+] Chat đã bắt đầu. Tin nhắn được mã hóa AES-256-GCM.")

    def send_reaction(self, reaction: str):
        if not self.session and not self.group_host:
            return
        try:
            if self.group_host:
                self.group_host.send_reaction(reaction, message_id=self.last_peer_message_id)
            else:
                self.session.send_reaction(reaction, message_id=self.last_peer_message_id)
            self._append_log(f"{self.nickname_input.text.strip() or 'Anonymous'} reaction: {reaction}")
        except (ConnectionError, OSError, RuntimeError, ValueError) as exc:
            self._append_log(f"[!] Không thể gửi reaction: {exc}")

    def send_message(self, *_args):
        message = self.message_input.text.strip()
        if not message or (not self.session and not self.group_host):
            return
        try:
            if self.group_host:
                message_id = self.group_host.send_message(message, reply_to=self.reply_to_id)
            else:
                message_id = self.session.send_text(message, reply_to=self.reply_to_id)
            self._append_log(f"{self.nickname_input.text.strip() or 'Anonymous'}: {message}", message_id=message_id)
            self.message_input.text = ""
            self.reply_to_id = None
            self.message_input.hint_text = self._t("message_hint")
        except (ConnectionError, OSError, RuntimeError) as exc:
            self._append_log(f"[!] Không thể gửi: {exc}")

    def stop_connection(self, *_args):
        self.stop_event.set()
        self._stop_voice()
        if self.confirm_event:
            self.confirm_event.set()
        if self.group_host:
            try:
                self.group_host.stop()
            except Exception:
                pass
            self.group_host = None
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass
            self.session = None
        if self.listener:
            try:
                self.listener.close()
            except OSError:
                pass
            self.listener = None
        if self.daemon:
            try:
                self.daemon.stop()
            except Exception:
                pass
            self.daemon = None
        if hasattr(self, "start_button"):
            self._reset_ui()

    def _reset_ui(self):
        def reset(_dt):
            self.start_button.disabled = False
            self.stop_button.disabled = True
            self.retry_button.disabled = not self.has_attempted_connection
            self.transport.disabled = False
            self.role.disabled = False
            self.message_input.disabled = True
            self.send_button.disabled = True
            self._enable_reactions(False)
            self._enable_voice(False)
            self.file_button.disabled = True
            self.members_button.disabled = True
            self.reply_button.disabled = True
            self.fingerprint_button.disabled = True
            self.details_button.disabled = True
            self.settings_expanded = True
            self.connection_card.opacity = 1
            self.connection_card.disabled = False
            self.connection_card.height = dp(258)
            self.settings_toggle_button.text = self._t("hide_settings")
            self.reply_to_id = None
            self.search_query = ""
            self.search_input.text = ""
            self.last_peer_message_id = None
            self.connection_label.text = self._t("status_disconnected")
            self.security_badge.text = f"●  E2EE\n[size=11]{self._t('ready')}[/size]"
            self.qr_button.disabled = True
            self.bluetooth_button.disabled = True
            self.current_invite = None
            self.current_address = None
            self.invite_address_label.text = ""
            self.copy_address_button.disabled = True
            self.share_address_button.disabled = True
        Clock.schedule_once(reset, 0)

    def on_stop(self):
        self.stop_connection()


if __name__ == "__main__":
    CloakChatGUI().run()
