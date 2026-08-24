"""Kiểm tra nhất quán cấu hình đóng gói chéo nền tảng của CloakChat.

Script chỉ đọc file cấu hình, không chạy build và không thay đổi giao thức hay khóa.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
gui_spec = (ROOT / "CloakChatGUI.spec").read_text(encoding="utf-8")
buildozer = (ROOT / "buildozer.spec").read_text(encoding="utf-8")

required_workflow_fragments = (
    "name: Linux GUI executable",
    "name: Android APK",
    "name: CloakChat-linux-x86_64",
    "name: CloakChat-android-debug",
)
for fragment in required_workflow_fragments:
    assert fragment in workflow, f"missing workflow fragment: {fragment}"
assert "  windows:" not in workflow
assert "CloakChat-windows-x64" not in workflow

assert "cloakchat_gui.py" in gui_spec
assert "requirements = python3,kivy,cryptography" in buildozer
assert "p4a.branch = v2024.01.21" in buildozer
for permission in ("INTERNET", "RECORD_AUDIO", "BLUETOOTH_CONNECT"):
    assert permission in buildozer, f"missing Android permission: {permission}"

print("Packaging configuration check: OK")
