from pathlib import Path
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
assert app.language == "vi"
assert app._transport_key() == "LAN"
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
assert app.clear_chat_button.text == "CLEAR CHAT"

# Kiểm tra nạp invite từ clipboard: chỉ nạp transport/address, không đụng key.
import cloakchat_gui
cloakchat_gui.Clipboard = FakeClipboard
FakeClipboard.value = create_invite("lan", "192.0.2.10:4567", "Test Host")
app.paste_invite()
assert app.address.text == FakeClipboard.value
assert app._transport_key() == "LAN"
assert app._role_key() == "JOIN"

app.current_address = "example.onion"
app._set_invite_address(app.current_address)
assert "example.onion" in app.invite_address_label.text
app.set_language("vi")
assert app.transport.text == "LAN trực tiếp"
assert app._transport_key() == "LAN"
assert app.paste_button.text == "DÁN INVITE"
assert app.clear_chat_button.text == "XÓA CHAT"

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
