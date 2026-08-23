#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CloakChat GUI - giao diện Kivy cho Windows, Linux và Android.

Core mạng/mật mã nằm trong CloakChat.py. File này chỉ cung cấp giao diện cửa sổ
và chạy các thao tác blocking trên worker thread để UI không bị treo.
"""

from __future__ import annotations

import atexit
import socket
import sys
import threading
from pathlib import Path
from typing import Optional

# Đảm bảo các module core đi cùng thư mục luôn được tìm thấy khi chạy từ
# PyInstaller, Buildozer hoặc một test runner ở thư mục khác.
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image

import CloakChat as core
from bluetooth_share import share_invite
from contacts_store import ContactStore
from invite_utils import create_invite, parse_invite, save_qr
from voice_chat import VoiceChat


class CloakChatGUI(App):
    """Cửa sổ chính của CloakChat."""

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

    def build(self):
        self.title = "CloakChat"
        self.contacts = ContactStore(self.user_data_dir)
        try:
            from kivy.core.window import Window
            Window.clearcolor = (0.035, 0.055, 0.09, 1)
            Window.minimum_width = dp(420)
            Window.minimum_height = dp(640)
        except Exception:
            pass

        root = BoxLayout(
            orientation="vertical",
            padding=[dp(16), dp(14)],
            spacing=dp(10),
        )

        header = BoxLayout(size_hint_y=None, height=dp(62), spacing=dp(10))
        title = Label(
            text="[b]CloakChat[/b]\n[size=12][color=#93A4C3]PRIVATE • ENCRYPTED • DIRECT[/color][/size]",
            markup=True,
            halign="left",
            valign="middle",
        )
        title.bind(size=self._sync_text_size)
        header.add_widget(title)
        self.security_badge = Label(
            text="●  E2EE\n[size=11]READY[/size]",
            markup=True,
            color=(0.35, 0.92, 0.68, 1),
            halign="center",
            valign="middle",
            size_hint_x=None,
            width=dp(82),
        )
        self.security_badge.bind(size=self._sync_text_size)
        header.add_widget(self.security_badge)
        root.add_widget(header)

        connection_card = BoxLayout(
            orientation="vertical",
            padding=[dp(12), dp(10)],
            spacing=dp(7),
            size_hint_y=None,
            height=dp(228),
        )
        with connection_card.canvas.before:
            Color(0.07, 0.10, 0.16, 1)
            connection_bg = RoundedRectangle(pos=connection_card.pos, size=connection_card.size, radius=[dp(14)])
        connection_card.bind(pos=lambda w, p: setattr(connection_bg, "pos", w.pos))
        connection_card.bind(size=lambda w, s: setattr(connection_bg, "size", w.size))

        connection_card.add_widget(Label(
            text="[b]KẾT NỐI[/b]  [color=#93A4C3]Chọn cách kết nối[/color]",
            markup=True,
            halign="left",
            size_hint_y=None,
            height=dp(25),
        ))
        fields = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(82))
        fields.add_widget(Label(text="Mạng", color=(0.58, 0.65, 0.78, 1), halign="left"))
        self.transport = Spinner(
            text="LAN trực tiếp",
            values=("LAN trực tiếp", "IP công cộng", "Tor / Onion"),
            size_hint_y=None,
            height=dp(42),
            background_normal="",
            background_color=(0.12, 0.18, 0.28, 1),
            color=(0.92, 0.95, 1, 1),
        )
        fields.add_widget(self.transport)
        fields.add_widget(Label(text="Vai trò", color=(0.58, 0.65, 0.78, 1), halign="left"))
        self.role = Spinner(
            text="Host",
            values=("Host", "Join"),
            size_hint_y=None,
            height=dp(42),
            background_normal="",
            background_color=(0.12, 0.18, 0.28, 1),
            color=(0.92, 0.95, 1, 1),
        )
        self.role.bind(text=lambda *_: self._role_changed())
        self.transport.bind(text=lambda *_: self._role_changed())
        fields.add_widget(self.role)
        connection_card.add_widget(fields)

        self.address = TextInput(
            hint_text="Địa chỉ Join: IP:cổng hoặc tên .onion",
            multiline=False,
            size_hint_y=None,
            height=dp(43),
            padding=[dp(12), dp(11)],
            background_normal="",
            background_color=(0.11, 0.15, 0.23, 1),
            foreground_color=(0.92, 0.95, 1, 1),
            hint_text_color=(0.45, 0.53, 0.67, 1),
        )
        connection_card.add_widget(self.address)
        root.add_widget(connection_card)

        action_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.start_button = Button(text="BẮT ĐẦU", background_normal="", background_color=(0.15, 0.63, 0.48, 1), bold=True)
        self.start_button.bind(on_press=self.start_connection)
        self.stop_button = Button(text="DỪNG", background_normal="", background_color=(0.55, 0.18, 0.23, 1), disabled=True)
        self.stop_button.bind(on_press=lambda *_: self.stop_connection())
        action_row.add_widget(self.start_button)
        action_row.add_widget(self.stop_button)
        root.add_widget(action_row)

        tools = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        self.qr_button = Button(text="QR INVITE", background_normal="", background_color=(0.12, 0.18, 0.28, 1), disabled=True)
        self.qr_button.bind(on_press=lambda *_: self.show_qr())
        self.bluetooth_button = Button(text="BLUETOOTH", background_normal="", background_color=(0.12, 0.18, 0.28, 1), disabled=True)
        self.bluetooth_button.bind(on_press=lambda *_: self.share_bluetooth())
        self.contacts_button = Button(text="DANH BẠ", background_normal="", background_color=(0.12, 0.18, 0.28, 1))
        self.contacts_button.bind(on_press=lambda *_: self.show_contacts())
        self.voice_button = Button(text="VOICE", background_normal="", background_color=(0.12, 0.18, 0.28, 1), disabled=True)
        self.voice_button.bind(on_press=lambda *_: self.toggle_voice())
        tools.add_widget(self.qr_button)
        tools.add_widget(self.bluetooth_button)
        tools.add_widget(self.contacts_button)
        tools.add_widget(self.voice_button)
        root.add_widget(tools)

        self.connection_label = Label(
            text="●  Sẵn sàng — LAN không dùng Tor, E2EE vẫn bật",
            color=(0.58, 0.65, 0.78, 1),
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(38),
        )
        self.connection_label.bind(size=self._sync_text_size)
        root.add_widget(self.connection_label)

        chat_panel = BoxLayout(orientation="vertical", padding=[dp(10), dp(8)], spacing=dp(4))
        with chat_panel.canvas.before:
            Color(0.055, 0.08, 0.13, 1)
            chat_bg = RoundedRectangle(pos=chat_panel.pos, size=chat_panel.size, radius=[dp(14)])
        chat_panel.bind(pos=lambda w, p: setattr(chat_bg, "pos", w.pos))
        chat_panel.bind(size=lambda w, s: setattr(chat_bg, "size", w.size))
        chat_title = Label(text="[b]TIN NHẮN[/b]  [color=#93A4C3]E2EE channel[/color]", markup=True, halign="left", size_hint_y=None, height=dp(25))
        chat_panel.add_widget(chat_title)
        scroll = ScrollView()
        self.chat_log = TextInput(
            readonly=True,
            multiline=True,
            size_hint_y=None,
            padding=[dp(8), dp(8)],
            background_normal="",
            background_color=(0.04, 0.06, 0.10, 1),
            foreground_color=(0.82, 0.88, 0.96, 1),
            cursor_color=(0, 0, 0, 0),
        )
        self.chat_log.bind(minimum_height=self.chat_log.setter("height"))
        scroll.add_widget(self.chat_log)
        chat_panel.add_widget(scroll)
        root.add_widget(chat_panel)

        reaction_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
        reaction_row.add_widget(Label(text="React", color=(0.58, 0.65, 0.78, 1), size_hint_x=None, width=dp(58)))
        for emoji in ("👍", "❤️", "😂", "😮", "🎉"):
            reaction_button = Button(text=emoji, font_size=dp(20), background_normal="", background_color=(0.12, 0.18, 0.28, 1), disabled=True)
            reaction_button.bind(on_press=lambda _btn, value=emoji: self.send_reaction(value))
            reaction_row.add_widget(reaction_button)
        self.reaction_buttons = reaction_row.children[0:5]
        root.add_widget(reaction_row)

        compose = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
        self.message_input = TextInput(
            hint_text="Viết tin nhắn bảo mật...",
            multiline=False,
            disabled=True,
            padding=[dp(12), dp(13)],
            background_normal="",
            background_color=(0.11, 0.15, 0.23, 1),
            foreground_color=(0.92, 0.95, 1, 1),
            hint_text_color=(0.45, 0.53, 0.67, 1),
        )
        self.message_input.bind(on_text_validate=self.send_message)
        self.send_button = Button(text="GỬI", size_hint_x=None, width=dp(74), disabled=True, background_normal="", background_color=(0.15, 0.63, 0.48, 1), bold=True)
        self.send_button.bind(on_press=self.send_message)
        compose.add_widget(self.message_input)
        compose.add_widget(self.send_button)
        root.add_widget(compose)

        self._append_log("Sẵn sàng. Chọn LAN để kết nối nội bộ hoặc Tor để dùng .onion.")
        atexit.register(self.stop_connection)
        return root

    @staticmethod
    def _sync_text_size(widget, _size):
        widget.text_size = (widget.width - dp(8), widget.height)

    def _role_changed(self):
        """Host không cần nhập địa chỉ; Join mới dùng ô invite."""
        if hasattr(self, "address") and hasattr(self, "role"):
            is_join = self.role.text == "Join"
            is_public_host = self.role.text == "Host" and self.transport.text == "IP công cộng"
            self.address.disabled = not (is_join or is_public_host)
            self.address.opacity = 1 if (is_join or is_public_host) else 0.55
            if is_public_host:
                self.address.hint_text = "IP public của máy này, ví dụ 203.0.113.10"
            elif is_join:
                self.address.hint_text = "Dán invite QR hoặc IP:cổng / tên .onion"
            else:
                self.address.hint_text = "Host sẽ hiển thị địa chỉ sau khi bấm Bắt đầu"

    def _append_log(self, text: str):
        """Cập nhật UI trên main thread của Kivy."""
        self.chat_log.text += text.rstrip() + "\n"
        self.chat_log.cursor = (0, len(self.chat_log.text))

    def _status_from_worker(self, text: str):
        Clock.schedule_once(lambda _dt: self._append_log(text), 0)

    def _set_connection_label(self, text: str):
        self.connection_label.text = text

    def start_connection(self, *_args):
        if self.worker and self.worker.is_alive():
            return
        self.stop_event.clear()
        self.start_button.disabled = True
        self.stop_button.disabled = False
        self.transport.disabled = True
        self.role.disabled = True
        self.address.disabled = self.role.text == "Host"
        self.worker = threading.Thread(
            target=self._connection_worker,
            name="cloakchat-gui-worker",
            daemon=True,
        )
        self.worker.start()

    def _connection_worker(self):
        try:
            is_tor = self.transport.text == "Tor / Onion"
            is_public = self.transport.text == "IP công cộng"
            is_host = self.role.text == "Host"
            if is_host:
                connection = self._prepare_host(is_tor, is_public)
            else:
                connection = self._prepare_join(is_tor, is_public)
            if self.stop_event.is_set():
                connection.close()
                return

            self.session = core.ChatSession(
                connection,
                is_host=is_host,
                confirm_callback=self._confirm_safety_number,
                message_callback=self._message_from_peer,
                reaction_callback=self._reaction_from_peer,
                status_callback=self._status_from_worker,
            )
            self._status_from_worker("[*] Đang trao đổi khóa và chờ xác nhận Safety Number...")
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
        self.current_invite = create_invite(invite_transport, address, "CloakChat Host")
        Clock.schedule_once(lambda _dt: self._set_connection_label(f"Gửi địa chỉ này cho peer: {address}"), 0)
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

    def _prepare_join(self, is_tor: bool, is_public: bool = False) -> socket.socket:
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
                    "Đối chiếu Safety Number với peer qua kênh tin cậy bên ngoài:\n\n"
                    f"[b]{number}[/b]\n\nBạn xác nhận hai số trùng nhau?"
                ),
                markup=True,
            )
        )
        buttons = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(8))
        yes = Button(text="Đúng, xác nhận")
        no = Button(text="Không")
        yes.bind(on_press=lambda *_: self._finish_confirmation(True))
        no.bind(on_press=lambda *_: self._finish_confirmation(False))
        buttons.add_widget(yes)
        buttons.add_widget(no)
        content.add_widget(buttons)
        self.safety_popup = Popup(
            title="Xác nhận Safety Number",
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
        Clock.schedule_once(lambda _dt: self._append_log(f"Peer: {message}"), 0)

    def _reaction_from_peer(self, reaction: str):
        Clock.schedule_once(lambda _dt: self._append_log(f"Peer reaction: {reaction}"), 0)

    def _enable_reactions(self, enabled: bool):
        for button in getattr(self, "reaction_buttons", []):
            button.disabled = not enabled

    def _enable_share_buttons(self):
        if hasattr(self, "qr_button"):
            self.qr_button.disabled = False
        if hasattr(self, "bluetooth_button"):
            self.bluetooth_button.disabled = False

    def _enable_voice(self, enabled: bool):
        if hasattr(self, "voice_button"):
            self.voice_button.disabled = not enabled
            if not enabled:
                self.voice_button.text = "VOICE"

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
            self.voice_button.text = "TẮT VOICE"
        except Exception as exc:
            self.voice = None
            self._append_log(f"[VOICE] Không thể bật voice: {exc}")

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
            self.transport.text = "Tor / Onion" if parsed["transport"] == "tor" else "LAN trực tiếp"
            self.role.text = "Join"
            self._append_log("[+] Đã nạp invite và transport từ danh bạ vào ô địa chỉ.")
        except ValueError as exc:
            self._append_log(f"[!] Invite trong danh bạ không hợp lệ: {exc}")

    def _chat_ready(self, _dt):
        self.connection_label.text = "●  Đã kết nối — E2EE hoạt động — Safety Number đã xác nhận"
        self.security_badge.text = "●  E2EE\n[size=11]SECURE[/size]"
        self.message_input.disabled = False
        self.send_button.disabled = False
        self._enable_reactions(True)
        self._enable_voice(True)
        self._append_log("[+] Chat đã bắt đầu. Tin nhắn được mã hóa AES-256-GCM.")

    def send_reaction(self, reaction: str):
        if not self.session:
            return
        try:
            self.session.send_reaction(reaction)
            self._append_log(f"Bạn reaction: {reaction}")
        except (ConnectionError, OSError, RuntimeError, ValueError) as exc:
            self._append_log(f"[!] Không thể gửi reaction: {exc}")

    def send_message(self, *_args):
        message = self.message_input.text.strip()
        if not message or not self.session:
            return
        try:
            self.session.send_text(message)
            self._append_log(f"Bạn: {message}")
            self.message_input.text = ""
        except (ConnectionError, OSError, RuntimeError) as exc:
            self._append_log(f"[!] Không thể gửi: {exc}")

    def stop_connection(self, *_args):
        self.stop_event.set()
        self._stop_voice()
        if self.confirm_event:
            self.confirm_event.set()
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
            self.transport.disabled = False
            self.role.disabled = False
            self.message_input.disabled = True
            self.send_button.disabled = True
            self._enable_reactions(False)
            self._enable_voice(False)
            self.connection_label.text = "●  Đã ngắt kết nối — sẵn sàng cho phiên mới"
            self.security_badge.text = "●  E2EE\n[size=11]READY[/size]"
            self.qr_button.disabled = True
            self.bluetooth_button.disabled = True
            self.current_invite = None
        Clock.schedule_once(reset, 0)

    def on_stop(self):
        self.stop_connection()


if __name__ == "__main__":
    CloakChatGUI().run()
