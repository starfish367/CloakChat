from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cloakchat_gui import CloakChatGUI

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
app.current_address = "example.onion"
app._set_invite_address(app.current_address)
assert "example.onion" in app.invite_address_label.text
app.set_language("vi")
assert app.transport.text == "Orbot SOCKS5"
assert app._transport_key() == "ORBOT"
app.stop_connection()
print("GUI i18n/Orbot/Copy-Share smoke test: OK")
