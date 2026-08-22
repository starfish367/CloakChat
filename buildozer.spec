[app]
# Tên ứng dụng hiển thị trên Android.
title = CloakChat
package.name = cloakchat
package.domain = org.cloakchat
source.dir = .
source.include_exts = py,txt,md
source.exclude_dirs = .git,.venv,tests,build,dist,__pycache__
version = 1.1.0

# Kivy GUI; cryptography được build qua recipe của python-for-android.
requirements = python3,kivy,cryptography,pyjnius,pysocks,stem,qrcode,pillow
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_CONNECT,BLUETOOTH_SCAN

[buildozer]
log_level = 2
warn_on_root = 1

# Bản Android ưu tiên LAN. Tor mode cần binary Tor/Orbot tích hợp riêng.
