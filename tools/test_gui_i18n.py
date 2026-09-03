from pathlib import Path
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cloakchat_gui import CloakChatGUI
from invite_utils import create_invite


class FakeClipboard:
    value = ""

    @classmethod
    def paste(cls):
        return cls.value

    @classmethod
    def copy(cls, value):
        cls.value = value


app = CloakChatGUI()
root = app.build()
app.set_language("vi")
assert app.language == "vi"
assert app._transport_key() == "LAN"
_original_orbot_port = os.environ.pop("CLOAKCHAT_ORBOT_SOCKS_PORT", None)
try:
    assert app._orbot_candidate_ports() == [9050, 9150]
    os.environ["CLOAKCHAT_ORBOT_SOCKS_PORT"] = "9152"
    assert app._orbot_candidate_ports() == [9152]
finally:
    if _original_orbot_port is None:
        os.environ.pop("CLOAKCHAT_ORBOT_SOCKS_PORT", None)
    else:
        os.environ["CLOAKCHAT_ORBOT_SOCKS_PORT"] = _original_orbot_port
app.set_language("en")
assert app.transport.text == "Direct LAN"
assert app.chat_title.text.startswith("[b]MESSAGES[/b]")
app.transport.text = "Orbot SOCKS5"
app.role.text = "Join"
assert app._transport_key() == "ORBOT"
assert app._role_key() == "JOIN"
app.group_mode_spinner.text = app._group_mode_value("A")
app.security_level_spinner.text = app._security_value("BALANCED")
assert app._group_mode_key() == "A"
assert app._security_key() == "BALANCED"
assert app.paste_button.text == "PASTE INVITE"
assert app.fingerprint_button.disabled is True
assert app.clear_search_button.text == "CLEAR SEARCH"
assert app.latest_button.text == "LATEST"
assert app.message_counter.text == "0/65536 B"
assert app.details_button.text == "DETAILS"
assert app.orbot_check_button.text == "TEST ORBOT"
assert app.orbot_port_input.hint_text == "Orbot port (auto)"
assert app.copy_diagnostics_button.text == "COPY DIAGNOSTICS"
assert app.help_button.text == "HELP"
import cloakchat_gui
cloakchat_gui.Clipboard = FakeClipboard
app.last_diagnostics = "Ports tried: 9050, 9150"
app.copy_diagnostics()
assert FakeClipboard.value == app.last_diagnostics
app.message_input.text = "Xin chào 🌊"
assert app.message_counter.text.startswith("14/")
app.log_entries[:] = [{"id": "one", "text": "one"}, {"id": "two", "text": "two"}]
app._render_log()
app.chat_scroll.scroll_y = 0.5
app.jump_to_latest()
assert app.chat_scroll.scroll_y == 0
app.set_font_scale(1.25)
assert app.font_scale == 1.25
assert app.chat_log.font_size > 16
app.set_font_scale(1.0)
assert app.preferences_path.is_file()
assert json.loads(app.preferences_path.read_text(encoding="utf-8"))["font_scale"] == 1.0

# Tìm kiếm tra nạp invite từ clipboard: chỉ nạp transport/address, không đụng key.
FakeClipboard.value = create_invite("lan", "192.0.2.10:4567", "Test Host")
app.paste_invite()
assert app.address.text == FakeClipboard.value
app.copy_invite()
assert FakeClipboard.value == app.address.text
assert app._transport_key() == "LAN"
assert app._role_key() == "JOIN"

app.current_address = "example.onion"
app._set_invite_address(app.current_address)
assert "example.onion" in app.invite_address_label.text
app.set_language("vi")
assert app.transport.text == "LAN trực tiếp"
assert app.message_counter.text.startswith("14/")
assert app._transport_key() == "LAN"
assert app.paste_button.text == "DÁN INVITE"
assert app.clear_search_button.text == "XÓA TÌM"
assert app.latest_button.text == "TIN MỚI"
assert app.details_button.text == "CHI TIẾT"
assert app.orbot_check_button.text == "KIỂM TRA ORBOT"
assert app.orbot_port_input.hint_text == "Cổng Orbot (tự động)"
assert app.copy_diagnostics_button.text == "COPY CHẨN ĐOÁN"
assert app.help_button.text == "HƯỚNG DẪN"
app.toggle_settings()
assert app.connection_card.height == 0
assert app.settings_toggle_button.text == "MỞ CẤU HÌNH"
app.toggle_settings()
assert app.connection_card.height > 0
assert app.settings_toggle_button.text == "ẨN CẤU HÌNH"

# Tìm kiếm chỉ lọc log tại chỗ và không thay đổi danh sách transcript gốc.
app.log_entries.clear()
app._append_log("Alice: hello secure world")
app._append_log("Bob: unrelated message")
app.search_input.text = "SECURE"
app.apply_search()
assert app.chat_log.text == "Alice: hello secure world\n"
app.clear_search()
assert "unrelated message" in app.chat_log.text

# Xuất transcript local không bao gồm khóa hoặc dữ liệu session.
app.export_chat()
exports = sorted((Path(app.user_data_dir) / "exports").glob("cloakchat_*.txt"), key=lambda item: item.stat().st_mtime)
assert exports
assert "Alice: hello secure world" in exports[-1].read_text(encoding="utf-8")
exports[-1].unlink()

# Fingerprint chỉ được phép copy sau khi phiên có đủ hai public key.
class FakeSession:
    local_public = b"a" * 32
    remote_public = b"b" * 32

app.session = FakeSession()
app.copy_fingerprint()
assert FakeClipboard.value.startswith("SHA512:")
app.session = None

# Regression: Public Host vẫn phải đọc được IP do người dùng nhập khi bấm Start.
class FakeThread:
    def __init__(self, target, name, daemon):
        self.target = target
        self.name = name
        self.daemon = daemon

    def is_alive(self):
        return False

    def start(self):
        return None

cloakchat_gui.threading.Thread = FakeThread
app.transport.text = app._transport_value("PUBLIC")
app.role.text = app._role_value("HOST")
app.address.text = "203.0.113.10"
app._role_changed()
app.start_connection()
assert app.address.disabled is False
assert app.retry_button.disabled is True
app.retry_button.disabled = False
app.retry_connection()
assert app.start_button.disabled is True

class FakePopup:
    def dismiss(self):
        return None

app.log_entries.clear()
app._append_log("local message")
app._clear_local_chat(FakePopup())
assert "chat_cleared" not in app.chat_log.text
assert "Đã xóa lịch sử chat cục bộ" in app.chat_log.text

app.stop_connection()
print("GUI i18n/Orbot/Copy-Share smoke test: OK")
