#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CloakChat - ứng dụng chat P2P ẩn danh 2 người qua Tor.

Đây là một file mã nguồn duy nhất, có thể chạy trực tiếp bằng Python hoặc
đóng gói bằng PyInstaller.

Phụ thuộc:
    python -m pip install stem cryptography PySocks

Cấu trúc khi chạy từ mã nguồn:
    CloakChat.py
    tor_bin/
        tor.exe  # Windows; Linux/Android dùng tor trong PATH hoặc PREFIX/bin

Ví dụ đóng gói trên Windows:
    pyinstaller --onefile --console --add-binary "tor_bin/tor.exe;tor_bin" CloakChat.py

Trên Linux, Tor được tìm trong PATH. Trên Android, có thể cài Tor bằng Termux
và mã nguồn sẽ tự tìm binary trong PREFIX/bin.

Lưu ý an toàn quan trọng:
    Safety Number phải được hai người đối chiếu qua một kênh tin cậy khác
    (trực tiếp, cuộc gọi đã xác thực, hoặc kênh có tính toàn vẹn). Nếu không
    đối chiếu, X25519 vẫn cung cấp bí mật chuyển tiếp, nhưng không tự nó ngăn
    được tấn công Man-in-the-Middle.
"""

from __future__ import annotations

import atexit
import hashlib
import os
import json
import secrets
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

try:
    import socks  # PySocks
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey,
        X25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from stem.control import Controller
except ImportError as exc:
    missing = str(exc).split("'")[-2] if "'" in str(exc) else str(exc)
    raise SystemExit(
        f"Thiếu thư viện '{missing}'. Cài đặt bằng lệnh: "
        "python -m pip install stem cryptography PySocks"
    ) from exc


APP_NAME = "CloakChat"
PROTOCOL_VERSION = b"cloakchat_v1"
SOCKS_HOST = "127.0.0.1"
SOCKS_PORT = 9050
ORBOT_SOCKS_PORT = 9050
CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = 9051
HIDDEN_SERVICE_PORT = 80
CONNECT_TIMEOUT = 30.0
ONION_CONNECT_TIMEOUT = 120.0
CONFIRM_TIMEOUT = 180.0
ONION_PUBLICATION_TIMEOUT = 180.0
MAX_FRAME_SIZE = 1_048_576
MAX_MESSAGE_BYTES = 64 * 1024
MAX_VOICE_FRAME_BYTES = 4096
MAX_NICKNAME_BYTES = 64
MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_FILE_CHUNK_BYTES = 48 * 1024

PACKET_HANDSHAKE = 0x01
PACKET_MESSAGE = 0x02
PACKET_CONFIRM = 0x03
PACKET_CLOSE = 0x04
PACKET_REACTION = 0x05
PACKET_VOICE = 0x06
PACKET_PROFILE = 0x07
PACKET_FILE = 0x08
PACKET_GROUP_KEY = 0x09
PACKET_GROUP_EVENT = 0x0A

AAD_MESSAGE = PROTOCOL_VERSION + b"|message"
AAD_REACTION = PROTOCOL_VERSION + b"|reaction"
AAD_VOICE = PROTOCOL_VERSION + b"|voice"
AAD_PROFILE = PROTOCOL_VERSION + b"|profile"
AAD_FILE = PROTOCOL_VERSION + b"|file"
AAD_GROUP_KEY = PROTOCOL_VERSION + b"|group-key"
AAD_GROUP_EVENT = PROTOCOL_VERSION + b"|group-event"
FILE_HEADER = struct.Struct("!B16sQIIH32s")

_PRINT_LOCK = threading.Lock()
_SHUTDOWN = threading.Event()
_ACTIVE_DAEMON: Optional["TorDaemon"] = None
_ACTIVE_SESSION: Optional["ChatSession"] = None
_ACTIVE_LISTENER: Optional[socket.socket] = None


BANNER = r"""
   ____ _             _    ____ _           _
  / ___| | ___   __ _| | __/ ___| |__   __ _| |_ 
 | |   | |/ _ \ / _` | |/ / |   | '_ \ / _` | __|
 | |___| | (_) | (_| |   <| |___| | | | (_| | |_
  \____|_|\___/ \__,_|_|\_\\____|_| |_|\__,_|\__|

             Anonymous. Encrypted. Direct.
"""


def safe_print(message: str = "") -> None:
    """In ra màn hình mà không để output của hai thread bị chồng lên nhau."""
    with _PRINT_LOCK:
        print(message, flush=True)


def get_application_dir() -> Path:
    """Lấy thư mục chứa tài nguyên, tương thích cả Python thường và PyInstaller."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def resolve_tor_executable() -> Path:
    """Tìm Tor daemon trên Windows, Linux hoặc Android/Termux."""
    override = os.environ.get("CLOAKCHAT_TOR_EXECUTABLE")
    candidates = []
    if override:
        candidates.append(Path(override).expanduser())

    app_dir = get_application_dir()
    binary_name = "tor.exe" if os.name == "nt" else "tor"
    candidates.extend(
        [
            app_dir / "tor_bin" / binary_name,
            Path.cwd() / "tor_bin" / binary_name,
        ]
    )

    # Termux thường cài Tor trong PREFIX/bin; shutil.which hỗ trợ các bản
    # Linux cài Tor qua apt, dnf hoặc pacman.
    termux_prefix = os.environ.get("PREFIX")
    if termux_prefix:
        candidates.append(Path(termux_prefix) / "bin" / "tor")
    system_tor = shutil.which("tor")
    if system_tor:
        candidates.append(Path(system_tor))

    for candidate in candidates:
        if candidate.is_file() and (os.name == "nt" or os.access(candidate, os.X_OK)):
            return candidate.resolve()
    searched = "\n".join(f"  - {path}" for path in candidates)
    raise FileNotFoundError(
        "Không tìm thấy Tor daemon. Trên Windows đặt tor.exe vào tor_bin/; "
        "trên Linux/Android cài gói tor hoặc dùng CLOAKCHAT_TOR_EXECUTABLE. "
        "Đã tìm:\n" + searched
    )


def find_free_tcp_port(host: str = SOCKS_HOST) -> int:
    """Chọn một cổng TCP trống trên localhost."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])
    finally:
        probe.close()


def wait_for_tcp_port(
    host: str,
    port: int,
    timeout: float,
    process: Optional[subprocess.Popen[bytes]] = None,
    diagnostic=None,
) -> None:
    """Chờ cổng TCP; báo sớm nếu Tor đã thoát và kèm log chẩn đoán."""
    deadline = time.monotonic() + timeout
    last_error: Optional[Exception] = None
    while time.monotonic() < deadline and not _SHUTDOWN.is_set():
        if process is not None and process.poll() is not None:
            details = diagnostic() if diagnostic is not None else "Không có log."
            raise RuntimeError(
                f"Tor đã thoát với mã {process.returncode}. Log Tor:\n{details}"
            )
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.5)
        try:
            probe.connect((host, port))
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25)
        finally:
            probe.close()
    raise TimeoutError(
        f"Tor không mở cổng {host}:{port} trong {timeout:.0f} giây "
        f"({last_error})."
    )


def wait_for_tor_bootstrap(
    controller: Controller,
    timeout: float,
) -> None:
    """Chờ Tor có circuit hoàn chỉnh trước khi cho phép kết nối onion."""
    deadline = time.monotonic() + timeout
    last_status = "chưa có trạng thái"
    while time.monotonic() < deadline and not _SHUTDOWN.is_set():
        try:
            last_status = controller.get_info("status/bootstrap-phase")
            if "PROGRESS=100" in last_status or "TAG=done" in last_status:
                return
        except Exception as exc:
            last_status = str(exc)
        time.sleep(1.0)
    raise TimeoutError(
        "Tor chưa hoàn tất bootstrap trong "
        f"{timeout:.0f} giây. Trạng thái cuối: {last_status}"
    )


class TorDaemon:
    """Quản lý vòng đời Tor daemon và ephemeral onion service."""

    def __init__(self) -> None:
        self.process: Optional[subprocess.Popen[bytes]] = None
        self.controller: Optional[Controller] = None
        self.data_dir: Optional[Path] = None
        self.service_id: Optional[str] = None
        self.log_path: Optional[Path] = None
        self.log_handle = None
        self.socks_port = SOCKS_PORT
        self.control_port = CONTROL_PORT
        self.using_existing_tor = False
        self._stopped = False

    def _diagnostic_log(self) -> str:
        """Đọc phần cuối log Tor để hiển thị nguyên nhân khi daemon thất bại."""
        if self.log_path is None or not self.log_path.is_file():
            return "Tor không tạo được log chẩn đoán."
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return "\n".join(lines[-12:]) or "Log Tor trống."
        except OSError as exc:
            return f"Không đọc được log Tor: {exc}"

    def start(self) -> None:
        if self.process is not None or self.controller is not None:
            return

        # Nếu Tor hệ thống đã chạy và mở ControlPort với cookie auth, dùng lại
        # nó thay vì tạo daemon thứ hai tranh chấp cổng SOCKS 9050.
        try:
            existing = Controller.from_port(address=CONTROL_HOST, port=CONTROL_PORT)
            existing.authenticate()
            wait_for_tcp_port(SOCKS_HOST, SOCKS_PORT, 2.0)
            wait_for_tor_bootstrap(existing, ONION_PUBLICATION_TIMEOUT)
            self.controller = existing
            self.socks_port = SOCKS_PORT
            self.control_port = CONTROL_PORT
            self.using_existing_tor = True
            safe_print("[+] Đang dùng Tor hệ thống hiện có (9050/9051).")
            return
        except Exception:
            try:
                existing.close()  # type: ignore[union-attr]
            except Exception:
                pass

        tor_executable = resolve_tor_executable()
        self.socks_port = int(os.environ.get("CLOAKCHAT_SOCKS_PORT", find_free_tcp_port()))
        self.control_port = int(os.environ.get("CLOAKCHAT_CONTROL_PORT", find_free_tcp_port()))
        if self.socks_port == self.control_port:
            self.control_port = find_free_tcp_port()
        self.data_dir = Path(tempfile.mkdtemp(prefix="cloakchat_tor_"))
        self.log_path = self.data_dir / "tor.log"
        self.log_handle = self.log_path.open("ab")
        command = [
            str(tor_executable),
            "--DataDirectory",
            str(self.data_dir),
            "--SocksPort",
            f"{SOCKS_HOST}:{self.socks_port}",
            "--ControlPort",
            f"{CONTROL_HOST}:{self.control_port}",
            "--CookieAuthentication",
            "1",
            "--AvoidDiskWrites",
            "1",
        ]

        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=self.log_handle,
                stderr=self.log_handle,
                startupinfo=startupinfo,
                creationflags=creationflags,
                close_fds=(os.name != "nt"),
            )
            wait_for_tcp_port(
                CONTROL_HOST,
                self.control_port,
                CONNECT_TIMEOUT,
                process=self.process,
                diagnostic=self._diagnostic_log,
            )
            wait_for_tcp_port(
                SOCKS_HOST,
                self.socks_port,
                CONNECT_TIMEOUT,
                process=self.process,
                diagnostic=self._diagnostic_log,
            )
            self.controller = Controller.from_port(
                address=CONTROL_HOST, port=self.control_port
            )
            self.controller.authenticate()
            wait_for_tor_bootstrap(self.controller, ONION_PUBLICATION_TIMEOUT)
            safe_print("[+] Tor daemon đã sẵn sàng và đã bootstrap xong.")
        except Exception as exc:
            details = self._diagnostic_log()
            self.stop()
            if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
                raise RuntimeError(
                    f"Tor không khởi động được hoặc không mở đủ cổng. Log Tor:\n{details}"
                ) from exc
            raise

    def create_ephemeral_service(self, internal_port: int) -> str:
        """Tạo onion service tạm thời, ánh xạ cổng onion 80 vào localhost."""
        if self.controller is None:
            raise RuntimeError("Tor controller chưa được khởi tạo.")

        safe_print(
            "[*] Tor đã chạy. Đang chờ mạng Tor và công bố địa chỉ .onion "
            f"(tối đa {ONION_PUBLICATION_TIMEOUT:.0f} giây)..."
        )
        try:
            service = self.controller.create_ephemeral_hidden_service(
                {HIDDEN_SERVICE_PORT: internal_port},
                key_type="NEW",
                key_content="ED25519-V3",
                await_publication=True,
                timeout=ONION_PUBLICATION_TIMEOUT,
            )
        except Exception as exc:
            try:
                bootstrap = self.controller.get_info("status/bootstrap-phase")
            except Exception:
                bootstrap = "không đọc được trạng thái bootstrap"
            raise RuntimeError(
                "Không thể công bố onion service. "
                f"Bootstrap: {bootstrap}. Chi tiết: {exc}"
            ) from exc
        self.service_id = str(service.service_id)
        return f"{self.service_id}.onion"

    def remove_ephemeral_service(self) -> None:
        if self.controller is not None and self.service_id:
            try:
                self.controller.remove_ephemeral_hidden_service(self.service_id)
            except Exception:
                pass
            finally:
                self.service_id = None

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self.remove_ephemeral_service()

        if self.controller is not None and not self.using_existing_tor:
            try:
                self.controller.signal("SHUTDOWN")
            except Exception:
                pass
            try:
                self.controller.close()
            except Exception:
                pass
            self.controller = None
        self.using_existing_tor = False

        if self.process is not None:
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=3)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
            except Exception:
                pass
            self.process = None

        if self.log_handle is not None:
            try:
                self.log_handle.close()
            except Exception:
                pass
            self.log_handle = None

        if self.data_dir is not None:
            shutil.rmtree(self.data_dir, ignore_errors=True)
            self.data_dir = None
        self.log_path = None


class ProtocolError(Exception):
    """Lỗi giao thức hoặc dữ liệu nhận được không hợp lệ."""


def recv_exact(sock: socket.socket, size: int) -> bytes:
    """Đọc chính xác size byte, xử lý việc recv trả về dữ liệu từng phần."""
    if size < 0 or size > MAX_FRAME_SIZE:
        raise ProtocolError("Kích thước dữ liệu không hợp lệ.")
    chunks = bytearray()
    while len(chunks) < size:
        part = sock.recv(size - len(chunks))
        if not part:
            raise ConnectionError("Đầu bên kia đã đóng kết nối.")
        chunks.extend(part)
    return bytes(chunks)


def send_packet(sock: socket.socket, payload: bytes) -> None:
    """Đóng gói frame bằng header 4 byte big-endian rồi gửi toàn bộ."""
    if not payload or len(payload) > MAX_FRAME_SIZE:
        raise ProtocolError("Frame rỗng hoặc vượt quá giới hạn cho phép.")
    sock.sendall(struct.pack("!I", len(payload)) + payload)


def recv_packet(sock: socket.socket) -> bytes:
    """Đọc một frame theo header độ dài 4 byte."""
    header = recv_exact(sock, 4)
    (length,) = struct.unpack("!I", header)
    if length <= 0 or length > MAX_FRAME_SIZE:
        raise ProtocolError(f"Frame có kích thước bất thường: {length}.")
    return recv_exact(sock, length)


def public_key_fingerprint(public_key: bytes) -> str:
    """Fingerprint SHA-512 của một public key, dùng cho identity/group member ID."""
    if len(public_key) != 32:
        raise ValueError("Public key phải có đúng 32 byte.")
    digest = hashlib.sha512(public_key).hexdigest()
    return "SHA512:" + ":".join(digest[index : index + 16] for index in range(0, len(digest), 16))


def sha512_fingerprint(local_public: bytes, remote_public: bytes) -> str:
    """Tạo fingerprint SHA-512 ổn định từ hai public key X25519 đã sắp xếp."""
    if len(local_public) != 32 or len(remote_public) != 32:
        raise ValueError("Public key phải có đúng 32 byte.")
    first, second = sorted((local_public, remote_public))
    digest = hashlib.sha512(first + second).hexdigest()
    return "SHA512:" + ":".join(digest[index : index + 16] for index in range(0, len(digest), 16))


def safety_number(local_public: bytes, remote_public: bytes) -> str:
    """Tương thích ngược: Safety Number nay là fingerprint SHA-512."""
    return sha512_fingerprint(local_public, remote_public)


def derive_session_key(private_key: X25519PrivateKey, remote_public: bytes) -> bytes:
    """Dùng X25519 rồi HKDF-SHA256 để dẫn xuất khóa AES-256."""
    try:
        peer_key = X25519PublicKey.from_public_bytes(remote_public)
        shared_secret = private_key.exchange(peer_key)
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=PROTOCOL_VERSION,
        ).derive(shared_secret)
    except Exception as exc:
        raise ProtocolError(f"Không thể dẫn xuất khóa phiên: {exc}") from exc


def encrypt_chat_message(
    key: bytes,
    message: str,
    nickname: str = "Anonymous",
    message_id: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> bytes:
    value = message.strip()
    if not value or len(value.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("Tin nhắn phải có từ 1 đến 64 KiB UTF-8.")
    sender = nickname.strip() or "Anonymous"
    if len(sender.encode("utf-8")) > MAX_NICKNAME_BYTES:
        raise ValueError("Nickname vượt quá 64 byte UTF-8.")
    event = {"v": 1, "id": message_id or secrets.token_hex(16), "text": value, "nickname": sender}
    if reply_to:
        event["reply_to"] = str(reply_to)
    plaintext = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    return bytes([PACKET_MESSAGE]) + nonce + AESGCM(key).encrypt(nonce, plaintext, AAD_MESSAGE)


def encrypt_message(key: bytes, message: str) -> bytes:
    plaintext = message.encode("utf-8")
    if not plaintext or len(plaintext) > MAX_MESSAGE_BYTES:
        raise ValueError("Tin nhắn phải có từ 1 đến 64 KiB UTF-8.")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, AAD_MESSAGE)
    return bytes([PACKET_MESSAGE]) + nonce + ciphertext


def decrypt_message_event(key: bytes, packet: bytes) -> dict:
    if len(packet) < 1 + 12 + 16 or packet[0] != PACKET_MESSAGE:
        raise ProtocolError("Gói tin tin nhắn không hợp lệ.")
    nonce = packet[1:13]
    ciphertext = packet[13:]
    if len(ciphertext) > MAX_MESSAGE_BYTES + 512:
        raise ProtocolError("Tin nhắn nhận được vượt quá giới hạn.")
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, AAD_MESSAGE)
    except Exception as exc:
        raise ProtocolError("Xác thực AES-GCM thất bại; dữ liệu có thể đã bị sửa đổi hoặc sai khóa.") from exc
    try:
        event = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"v": 0, "id": secrets.token_hex(16), "text": plaintext.decode("utf-8", errors="strict"), "nickname": "Peer"}
    if not isinstance(event, dict) or event.get("v") != 1 or not isinstance(event.get("id"), str) or not isinstance(event.get("text"), str):
        raise ProtocolError("Envelope tin nhắn không hợp lệ.")
    event["nickname"] = str(event.get("nickname") or "Peer")
    if "reply_to" in event and not isinstance(event["reply_to"], str):
        raise ProtocolError("Reply metadata không hợp lệ.")
    return event


def decrypt_message(key: bytes, packet: bytes) -> str:
    if len(packet) < 1 + 12 + 16 or packet[0] != PACKET_MESSAGE:
        raise ProtocolError("Gói tin tin nhắn không hợp lệ.")
    nonce = packet[1:13]
    ciphertext = packet[13:]
    if len(ciphertext) > MAX_MESSAGE_BYTES + 16:
        raise ProtocolError("Tin nhắn nhận được vượt quá giới hạn.")
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, AAD_MESSAGE)
        return plaintext.decode("utf-8")
    except Exception as exc:
        raise ProtocolError(
            "Xác thực AES-GCM thất bại; dữ liệu có thể đã bị sửa đổi hoặc sai khóa."
        ) from exc


def encrypt_reaction(key: bytes, reaction: str) -> bytes:
    """Mã hóa emoji reaction bằng nonce riêng và AAD riêng."""
    value = reaction.strip()
    encoded = value.encode("utf-8")
    if not value or len(encoded) > 32:
        raise ValueError("Reaction không hợp lệ.")
    nonce = os.urandom(12)
    return bytes([PACKET_REACTION]) + nonce + AESGCM(key).encrypt(
        nonce, encoded, AAD_REACTION
    )


def encrypt_reaction_event(key: bytes, reaction: str, message_id: Optional[str] = None) -> bytes:
    value = reaction.strip()
    if not value or len(value.encode("utf-8")) > 32:
        raise ValueError("Reaction không hợp lệ.")
    event = {"v": 1, "reaction": value, "message_id": str(message_id or "")}
    plaintext = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    return bytes([PACKET_REACTION]) + nonce + AESGCM(key).encrypt(nonce, plaintext, AAD_REACTION)


def decrypt_reaction_event(key: bytes, packet: bytes) -> dict:
    if len(packet) < 1 + 12 + 16 or packet[0] != PACKET_REACTION:
        raise ProtocolError("Gói reaction không hợp lệ.")
    try:
        plaintext = AESGCM(key).decrypt(packet[1:13], packet[13:], AAD_REACTION)
    except Exception as exc:
        raise ProtocolError("Xác thực reaction thất bại.") from exc
    try:
        event = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"v": 0, "reaction": plaintext.decode("utf-8"), "message_id": ""}
    if not isinstance(event, dict) or event.get("v") != 1 or not isinstance(event.get("reaction"), str) or not isinstance(event.get("message_id"), str):
        raise ProtocolError("Reaction event không hợp lệ.")
    return event


def decrypt_reaction(key: bytes, packet: bytes) -> str:
    if len(packet) < 1 + 12 + 16 or packet[0] != PACKET_REACTION:
        raise ProtocolError("Gói reaction không hợp lệ.")
    try:
        return AESGCM(key).decrypt(packet[1:13], packet[13:], AAD_REACTION).decode("utf-8")
    except Exception as exc:
        raise ProtocolError("Xác thực reaction thất bại.") from exc


def encrypt_group_key(pairwise_key: bytes, group_key: bytes) -> bytes:
    if len(group_key) != 32:
        raise ValueError("Group key phải có 32 byte.")
    nonce = os.urandom(12)
    return bytes([PACKET_GROUP_KEY]) + nonce + AESGCM(pairwise_key).encrypt(nonce, group_key, AAD_GROUP_KEY)


def decrypt_group_key(pairwise_key: bytes, packet: bytes) -> bytes:
    if len(packet) != 1 + 12 + 32 + 16 or packet[0] != PACKET_GROUP_KEY:
        raise ProtocolError("Gói group key không hợp lệ.")
    try:
        return AESGCM(pairwise_key).decrypt(packet[1:13], packet[13:], AAD_GROUP_KEY)
    except Exception as exc:
        raise ProtocolError("Xác thực group key thất bại.") from exc


def encrypt_group_event(group_key: bytes, event: dict) -> bytes:
    if len(group_key) != 32 or not isinstance(event, dict):
        raise ValueError("Group event không hợp lệ.")
    plaintext = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(plaintext) > MAX_MESSAGE_BYTES:
        raise ValueError("Group event vượt quá giới hạn.")
    nonce = os.urandom(12)
    return bytes([PACKET_GROUP_EVENT]) + nonce + AESGCM(group_key).encrypt(nonce, plaintext, AAD_GROUP_EVENT)


def decrypt_group_event(group_key: bytes, packet: bytes) -> dict:
    if len(packet) < 1 + 12 + 16 or packet[0] != PACKET_GROUP_EVENT:
        raise ProtocolError("Gói group event không hợp lệ.")
    try:
        event = json.loads(AESGCM(group_key).decrypt(packet[1:13], packet[13:], AAD_GROUP_EVENT).decode("utf-8"))
    except Exception as exc:
        raise ProtocolError("Xác thực group event thất bại.") from exc
    if not isinstance(event, dict) or event.get("v") != 1 or not isinstance(event.get("type"), str):
        raise ProtocolError("Group event không hợp lệ.")
    return event


def encrypt_profile(key: bytes, nickname: str) -> bytes:
    value = nickname.strip()
    encoded = value.encode("utf-8")
    if not value or len(encoded) > MAX_NICKNAME_BYTES:
        raise ValueError("Nickname phải có từ 1 đến 64 byte UTF-8.")
    nonce = os.urandom(12)
    return bytes([PACKET_PROFILE]) + nonce + AESGCM(key).encrypt(nonce, encoded, AAD_PROFILE)


def decrypt_profile(key: bytes, packet: bytes) -> str:
    if len(packet) < 1 + 12 + 16 or packet[0] != PACKET_PROFILE:
        raise ProtocolError("Gói nickname không hợp lệ.")
    ciphertext = packet[13:]
    if len(ciphertext) > MAX_NICKNAME_BYTES + 16:
        raise ProtocolError("Nickname vượt quá giới hạn.")
    try:
        value = AESGCM(key).decrypt(packet[1:13], ciphertext, AAD_PROFILE).decode("utf-8").strip()
    except Exception as exc:
        raise ProtocolError("Xác thực nickname thất bại.") from exc
    if not value:
        raise ProtocolError("Nickname rỗng.")
    return value


def encrypt_file_chunk(
    key: bytes,
    transfer_id: bytes,
    filename: str,
    total_size: int,
    chunk_index: int,
    total_chunks: int,
    file_digest: bytes,
    chunk: bytes,
) -> bytes:
    """Mã hóa một chunk file; metadata được xác thực cùng ciphertext."""
    safe_name = Path(filename).name.strip() or "received_file"
    name_bytes = safe_name.encode("utf-8")
    if len(transfer_id) != 16 or len(file_digest) != 32:
        raise ValueError("Metadata file không hợp lệ.")
    if not (1 <= total_size <= MAX_FILE_SIZE):
        raise ValueError("File vượt quá giới hạn 25 MiB.")
    if not (0 <= chunk_index < total_chunks) or not (1 <= total_chunks <= (MAX_FILE_SIZE + MAX_FILE_CHUNK_BYTES - 1) // MAX_FILE_CHUNK_BYTES):
        raise ValueError("Chỉ số chunk không hợp lệ.")
    if len(name_bytes) > 255 or not chunk or len(chunk) > MAX_FILE_CHUNK_BYTES:
        raise ValueError("Chunk hoặc tên file không hợp lệ.")
    plaintext = FILE_HEADER.pack(1, transfer_id, total_size, chunk_index, total_chunks, len(name_bytes), file_digest) + name_bytes + chunk
    nonce = os.urandom(12)
    return bytes([PACKET_FILE]) + nonce + AESGCM(key).encrypt(nonce, plaintext, AAD_FILE)


def decrypt_file_chunk(key: bytes, packet: bytes) -> dict:
    if len(packet) < 1 + 12 + 16 + FILE_HEADER.size:
        raise ProtocolError("Gói file không hợp lệ.")
    if packet[0] != PACKET_FILE:
        raise ProtocolError("Sai loại gói file.")
    try:
        plaintext = AESGCM(key).decrypt(packet[1:13], packet[13:], AAD_FILE)
    except Exception as exc:
        raise ProtocolError("Xác thực chunk file thất bại.") from exc
    if len(plaintext) < FILE_HEADER.size:
        raise ProtocolError("Metadata file bị thiếu.")
    version, transfer_id, total_size, chunk_index, total_chunks, name_len, file_digest = FILE_HEADER.unpack_from(plaintext)
    if version != 1 or total_size > MAX_FILE_SIZE or not (1 <= total_chunks <= (MAX_FILE_SIZE + MAX_FILE_CHUNK_BYTES - 1) // MAX_FILE_CHUNK_BYTES):
        raise ProtocolError("Metadata file vượt giới hạn.")
    name_start = FILE_HEADER.size
    name_end = name_start + name_len
    if name_end > len(plaintext) or name_len > 255:
        raise ProtocolError("Tên file không hợp lệ.")
    try:
        filename = Path(plaintext[name_start:name_end].decode("utf-8")).name or "received_file"
    except Exception as exc:
        raise ProtocolError("Tên file không giải mã được.") from exc
    chunk = plaintext[name_end:]
    if not chunk or len(chunk) > MAX_FILE_CHUNK_BYTES or chunk_index >= total_chunks:
        raise ProtocolError("Kích thước/chỉ số chunk không hợp lệ.")
    return {"transfer_id": transfer_id, "filename": filename, "total_size": total_size, "chunk_index": chunk_index, "total_chunks": total_chunks, "file_digest": file_digest, "chunk": chunk}


def encrypt_voice_frame(key: bytes, frame: bytes) -> bytes:
    """Mã hóa một frame PCM nhỏ; không dùng nonce lặp lại."""
    if not frame or len(frame) > MAX_VOICE_FRAME_BYTES:
        raise ValueError("Voice frame rỗng hoặc vượt quá giới hạn.")
    nonce = os.urandom(12)
    return bytes([PACKET_VOICE]) + nonce + AESGCM(key).encrypt(
        nonce, frame, AAD_VOICE
    )


def decrypt_voice_frame(key: bytes, packet: bytes) -> bytes:
    if len(packet) < 1 + 12 + 16 or packet[0] != PACKET_VOICE:
        raise ProtocolError("Gói voice frame không hợp lệ.")
    ciphertext = packet[13:]
    if len(ciphertext) > MAX_VOICE_FRAME_BYTES + 16:
        raise ProtocolError("Voice frame vượt quá giới hạn.")
    try:
        return AESGCM(key).decrypt(packet[1:13], ciphertext, AAD_VOICE)
    except Exception as exc:
        raise ProtocolError("Xác thực voice frame thất bại.") from exc


def create_orbot_join_socket(
    onion_address: str,
    socks_port: int = ORBOT_SOCKS_PORT,
) -> socks.socksocket:
    """Kết nối onion qua Orbot đang chạy, không tạo Tor daemon mới."""
    return create_join_socket(onion_address, socks_port=socks_port)


def create_join_socket(
    onion_address: str,
    socks_port: int = SOCKS_PORT,
) -> socks.socksocket:
    """Kết nối tới onion service qua SOCKS5 với DNS được phân giải từ xa."""
    address = onion_address.strip().lower()
    if address.startswith("http://"):
        address = address[7:]
    elif address.startswith("https://"):
        address = address[8:]
    address = address.rstrip("/")
    if ":" in address:
        host, port_text = address.rsplit(":", 1)
        try:
            remote_port = int(port_text)
        except ValueError as exc:
            raise ValueError("Cổng onion không hợp lệ.") from exc
    else:
        host, remote_port = address, HIDDEN_SERVICE_PORT
    if not host.endswith(".onion") or len(host) < len("a.onion"):
        raise ValueError("Địa chỉ phải có dạng <ten>.onion.")
    if not (1 <= remote_port <= 65535):
        raise ValueError("Cổng onion phải nằm trong khoảng 1-65535.")

    connection = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
    connection.set_proxy(
        proxy_type=socks.SOCKS5,
        addr=SOCKS_HOST,
        port=socks_port,
        rdns=True,
    )
    connection.settimeout(ONION_CONNECT_TIMEOUT)
    try:
        connection.connect((host, remote_port))
    except socket.timeout as exc:
        connection.close()
        raise TimeoutError(
            "Tor SOCKS5 không kết nối được tới onion service trong "
            f"{ONION_CONNECT_TIMEOUT:.0f} giây. Hãy kiểm tra Host còn đang chạy "
            "và onion address còn mới không."
        ) from exc
    except Exception as exc:
        connection.close()
        raise ConnectionError(
            "Không thể kết nối onion service qua Tor SOCKS5; "
            "Host có thể đã thoát hoặc Tor chưa tạo được circuit."
        ) from exc
    connection.settimeout(None)
    return connection


class ChatSession:
    """Một phiên chat sau khi handshake và Safety Number đã được xác nhận."""

    def __init__(
        self,
        connection: socket.socket,
        is_host: bool,
        confirm_callback: Optional[Callable[[str], bool]] = None,
        message_callback: Optional[Callable[[str], None]] = None,
        message_event_callback: Optional[Callable[[dict], None]] = None,
        reaction_callback: Optional[Callable[[str], None]] = None,
        reaction_event_callback: Optional[Callable[[dict], None]] = None,
        voice_callback: Optional[Callable[[bytes], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        nickname: str = "Anonymous",
        profile_callback: Optional[Callable[[str], None]] = None,
        file_callback: Optional[Callable[[dict], None]] = None,
        group_mode: bool = False,
        relay_mode: bool = False,
        group_event_callback: Optional[Callable[[dict], None]] = None,
        raw_group_callback: Optional[Callable[[bytes], None]] = None,
        group_key_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        self.connection = connection
        self.is_host = is_host
        self.confirm_callback = confirm_callback
        self.message_callback = message_callback
        self.message_event_callback = message_event_callback
        self.reaction_callback = reaction_callback
        self.reaction_event_callback = reaction_event_callback
        self.voice_callback = voice_callback
        self.status_callback = status_callback
        self.nickname = nickname.strip() or "Anonymous"
        self.profile_callback = profile_callback
        self.file_callback = file_callback
        self.group_mode = group_mode
        self.relay_mode = relay_mode
        self.group_key: Optional[bytes] = None
        self.group_event_callback = group_event_callback
        self.raw_group_callback = raw_group_callback
        self.group_key_callback = group_key_callback
        self.peer_nickname = "Peer"
        self.remote_public: Optional[bytes] = None
        self.private_key = X25519PrivateKey.generate()
        self.local_public = self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.session_key: Optional[bytes] = None
        self.stop_event = threading.Event()
        self.send_lock = threading.Lock()
        self.receiver_thread: Optional[threading.Thread] = None

    def _status(self, message: str) -> None:
        if self.status_callback is not None:
            self.status_callback(message)
        else:
            safe_print(message)

    def _send(self, payload: bytes) -> None:
        with self.send_lock:
            send_packet(self.connection, payload)

    def handshake_and_confirm(self) -> None:
        """Trao đổi public key, hiển thị Safety Number và xác nhận hai phía."""
        self.connection.settimeout(CONFIRM_TIMEOUT)
        self._send(bytes([PACKET_HANDSHAKE]) + self.local_public)
        remote_packet = recv_packet(self.connection)
        if (
            len(remote_packet) != 1 + 32
            or remote_packet[0] != PACKET_HANDSHAKE
        ):
            raise ProtocolError("Handshake nhận được không hợp lệ.")
        remote_public = remote_packet[1:]
        self.remote_public = remote_public
        self.session_key = derive_session_key(self.private_key, remote_public)
        number = safety_number(self.local_public, remote_public)

        if self.confirm_callback is not None:
            local_confirmed = bool(self.confirm_callback(number))
        else:
            safe_print("\n" + "=" * 68)
            safe_print("SAFETY NUMBER - HÃY ĐỐI CHIẾU NGOÀI BĂNG VỚI BẠN CHAT")
            safe_print(f"        {number}")
            safe_print("=" * 68)
            answer = input(
                "Safety Number đúng và đã được đối chiếu? [y/N]: "
            ).strip().lower()
            local_confirmed = answer == "y"
        self._send(bytes([PACKET_CONFIRM, ord("y") if local_confirmed else ord("n")]))

        remote_confirm = recv_packet(self.connection)
        if (
            len(remote_confirm) != 2
            or remote_confirm[0] != PACKET_CONFIRM
            or remote_confirm[1] not in (ord("y"), ord("n"))
        ):
            raise ProtocolError("Phản hồi xác nhận Safety Number không hợp lệ.")
        remote_confirmed = remote_confirm[1] == ord("y")

        if not local_confirmed or not remote_confirmed:
            raise PermissionError(
                "Safety Number chưa được cả hai phía xác nhận; kết nối đã bị đóng."
            )
        self._send(encrypt_profile(self.session_key, self.nickname))
        self.connection.settimeout(None)
        self._status("[+] Safety Number đã được cả hai phía xác nhận.")

    def start_receiver(self) -> None:
        self.receiver_thread = threading.Thread(
            target=self._receiver_loop,
            name="cloakchat-receiver",
            daemon=True,
        )
        self.receiver_thread.start()

    def _receiver_loop(self) -> None:
        try:
            while not self.stop_event.is_set():
                packet = recv_packet(self.connection)
                if packet[0] == PACKET_MESSAGE:
                    if self.session_key is None:
                        raise ProtocolError("Chưa có khóa phiên.")
                    event = decrypt_message_event(self.session_key, packet)
                    if self.message_event_callback is not None:
                        self.message_event_callback(event)
                    elif self.message_callback is not None:
                        self.message_callback(event["text"])
                    else:
                        safe_print(f"\n[{event.get('nickname', 'Peer')}] {event.get('text', '')}")
                        safe_print("[Bạn] ",)
                elif packet[0] == PACKET_REACTION:
                    if self.session_key is None:
                        raise ProtocolError("Chưa có khóa phiên.")
                    reaction_event = decrypt_reaction_event(self.session_key, packet)
                    if self.reaction_event_callback is not None:
                        self.reaction_event_callback(reaction_event)
                    elif self.reaction_callback is not None:
                        self.reaction_callback(reaction_event["reaction"])
                    else:
                        safe_print(f"\n[Peer reaction] {reaction_event['reaction']}")
                elif packet[0] == PACKET_VOICE:
                    if self.session_key is None:
                        raise ProtocolError("Chưa có khóa phiên.")
                    frame = decrypt_voice_frame(self.session_key, packet)
                    if self.voice_callback is not None:
                        self.voice_callback(frame)
                elif packet[0] == PACKET_GROUP_KEY:
                    if self.session_key is None:
                        raise ProtocolError("Chưa có khóa phiên.")
                    self.group_key = decrypt_group_key(self.session_key, packet)
                    self.group_mode = True
                    if self.group_key_callback is not None:
                        self.group_key_callback()
                elif packet[0] == PACKET_GROUP_EVENT:
                    if self.group_mode and self.raw_group_callback is not None:
                        self.raw_group_callback(packet)
                    elif self.group_key is not None:
                        event = decrypt_group_event(self.group_key, packet)
                        if self.group_event_callback is not None:
                            self.group_event_callback(event)
                    else:
                        raise ProtocolError("Nhận group event trước group key.")
                elif packet[0] == PACKET_PROFILE:
                    if self.session_key is None:
                        raise ProtocolError("Chưa có khóa phiên.")
                    self.peer_nickname = decrypt_profile(self.session_key, packet)
                    if self.profile_callback is not None:
                        self.profile_callback(self.peer_nickname)
                elif packet[0] == PACKET_FILE:
                    if self.group_mode and self.relay_mode and self.raw_group_callback is not None:
                        self.raw_group_callback(packet)
                        continue
                    file_key = self.group_key if self.group_mode else self.session_key
                    if file_key is None:
                        raise ProtocolError("Chưa có khóa file/group.")
                    file_info = decrypt_file_chunk(file_key, packet)
                    if self.file_callback is not None:
                        self.file_callback(file_info)
                elif packet == bytes([PACKET_CLOSE]):
                    safe_print("\n[!] Peer đã đóng phiên chat.")
                    break
                else:
                    raise ProtocolError("Nhận được loại packet không được phép.")
        except socket.timeout:
            if not self.stop_event.is_set():
                self._status("[!] Hết thời gian chờ kết nối.")
        except (ConnectionError, OSError):
            if not self.stop_event.is_set():
                self._status("[!] Kết nối mạng đã đóng.")
        except ProtocolError as exc:
            if not self.stop_event.is_set():
                self._status(f"[!] Lỗi giao thức/bảo mật: {exc}")
        finally:
            self.stop_event.set()

    def send_text(self, message: str, reply_to: Optional[str] = None) -> None:
        if self.session_key is None:
            raise RuntimeError("Phiên chưa hoàn tất handshake.")
        if self.group_mode:
            if self.group_key is None:
                raise RuntimeError("Group key chưa sẵn sàng.")
            event = {"v": 1, "type": "message", "id": secrets.token_hex(16), "text": message.strip(), "nickname": self.nickname}
            if reply_to:
                event["reply_to"] = str(reply_to)
            self._send(encrypt_group_event(self.group_key, event))
        else:
            self._send(encrypt_chat_message(self.session_key, message, self.nickname, reply_to=reply_to))

    def send_reaction(self, reaction: str, message_id: Optional[str] = None) -> None:
        if self.session_key is None:
            raise RuntimeError("Phiên chưa hoàn tất handshake.")
        if self.group_mode:
            if self.group_key is None:
                raise RuntimeError("Group key chưa sẵn sàng.")
            self._send(encrypt_group_event(self.group_key, {"v": 1, "type": "reaction", "reaction": reaction, "message_id": str(message_id or "")}))
        else:
            self._send(encrypt_reaction_event(self.session_key, reaction, message_id))

    def send_group_key(self, group_key: bytes) -> None:
        if self.session_key is None:
            raise RuntimeError("Phiên chưa hoàn tất handshake.")
        self.group_key = group_key
        self._send(encrypt_group_key(self.session_key, group_key))

    def send_group_packet(self, packet: bytes) -> None:
        if self.group_key is None or not packet or packet[0] not in (PACKET_GROUP_EVENT, PACKET_FILE):
            raise RuntimeError("Group key hoặc group packet chưa sẵn sàng.")
        self._send(packet)

    def send_chat_event(self, event: dict) -> None:
        if self.session_key is None:
            raise RuntimeError("Phiên chưa hoàn tất handshake.")
        self._send(encrypt_chat_message(self.session_key, event["text"], event.get("nickname", "Peer"), event.get("id"), event.get("reply_to")))

    def send_reaction_event(self, event: dict) -> None:
        if self.session_key is None:
            raise RuntimeError("Phiên chưa hoàn tất handshake.")
        self._send(encrypt_reaction_event(self.session_key, event["reaction"], event.get("message_id")))

    def send_file_chunk(self, info: dict) -> None:
        file_key = self.group_key if self.group_mode else self.session_key
        if file_key is None:
            raise RuntimeError("Phiên chưa hoàn tất handshake/group key.")
        self._send(encrypt_file_chunk(file_key, info["transfer_id"], info["filename"], info["total_size"], info["chunk_index"], info["total_chunks"], info["file_digest"], info["chunk"]))

    def send_voice_frame(self, frame: bytes) -> None:
        if self.session_key is None:
            raise RuntimeError("Phiên chưa hoàn tất handshake.")
        self._send(encrypt_voice_frame(self.session_key, frame))

    def send_file(self, path: str) -> None:
        """Đọc file hai lần: hash trước, sau đó gửi từng chunk đã mã hóa."""
        file_key = self.group_key if self.group_mode else self.session_key
        if file_key is None:
            raise RuntimeError("Phiên chưa hoàn tất handshake/group key.")
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(str(source))
        total_size = source.stat().st_size
        if not (1 <= total_size <= MAX_FILE_SIZE):
            raise ValueError("File phải có kích thước từ 1 đến 25 MiB.")
        file_digest = hashlib.sha256()
        with source.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                file_digest.update(block)
        digest = file_digest.digest()
        total_chunks = (total_size + MAX_FILE_CHUNK_BYTES - 1) // MAX_FILE_CHUNK_BYTES
        transfer_id = os.urandom(16)
        with source.open("rb") as handle:
            for chunk_index in range(total_chunks):
                chunk = handle.read(MAX_FILE_CHUNK_BYTES)
                self._send(encrypt_file_chunk(file_key, transfer_id, source.name, total_size, chunk_index, total_chunks, digest, chunk))

    def close(self, notify_peer: bool = True) -> None:
        if self.stop_event.is_set():
            notify_peer = False
        self.stop_event.set()
        if notify_peer:
            try:
                self._send(bytes([PACKET_CLOSE]))
            except Exception:
                pass
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.connection.close()
        except OSError:
            pass
        if (
            self.receiver_thread is not None
            and self.receiver_thread.is_alive()
            and self.receiver_thread is not threading.current_thread()
        ):
            self.receiver_thread.join(timeout=2)


def close_active_resources() -> None:
    """Dọn dẹp idempotent khi gõ exit, Ctrl+C hoặc interpreter kết thúc."""
    global _ACTIVE_DAEMON, _ACTIVE_SESSION, _ACTIVE_LISTENER
    _SHUTDOWN.set()
    if _ACTIVE_SESSION is not None:
        try:
            _ACTIVE_SESSION.close()
        except Exception:
            pass
        _ACTIVE_SESSION = None
    if _ACTIVE_LISTENER is not None:
        try:
            _ACTIVE_LISTENER.close()
        except Exception:
            pass
        _ACTIVE_LISTENER = None
    if _ACTIVE_DAEMON is not None:
        try:
            _ACTIVE_DAEMON.stop()
        except Exception:
            pass
        _ACTIVE_DAEMON = None


def install_signal_handlers() -> None:
    """Chuyển SIGINT/SIGTERM thành sự kiện dừng và cleanup bình thường."""
    def handler(signum: int, _frame: object) -> None:
        safe_print(f"\n[!] Nhận tín hiệu {signum}; đang dọn dẹp...")
        close_active_resources()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handler)


def get_local_ipv4() -> str:
    """Lấy IPv4 LAN mà máy dùng để đi tới mạng nội bộ."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Không gửi dữ liệu; connect UDP chỉ giúp hệ điều hành chọn interface.
        probe.connect(("192.0.2.1", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def accept_host_connection(
    listener: socket.socket,
    transport_name: str = "Tor",
) -> socket.socket:
    """Chờ kết nối inbound và cho phép thoát sạch bằng Ctrl+C."""
    listener.settimeout(1.0)
    safe_print(f"[*] Đang chờ peer kết nối qua {transport_name}...")
    while not _SHUTDOWN.is_set():
        try:
            connection, address = listener.accept()
            safe_print(f"[+] Đã nhận kết nối {transport_name} từ {address[0]}.")
            return connection
        except socket.timeout:
            continue
    raise KeyboardInterrupt


def run_host_lan() -> None:
    """Host trực tiếp trên LAN, không khởi động Tor và không dùng SOCKS5."""
    global _ACTIVE_LISTENER
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _ACTIVE_LISTENER = listener
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("0.0.0.0", 0))
        internal_port = listener.getsockname()[1]
        listener.listen(1)
        safe_print("\n[LAN HOST] Chế độ LAN trực tiếp: Tor đã được tắt.")
        safe_print(f"[LAN HOST] IP nội bộ: {get_local_ipv4()}")
        safe_print(f"[LAN HOST] Cổng: {internal_port}")
        safe_print(
            f"[LAN HOST] Gửi IP và cổng cho peer: {get_local_ipv4()}:{internal_port}"
        )
        safe_print(
            "[LAN HOST] E2EE vẫn bật; hai phía sẽ đối chiếu Safety Number sau khi kết nối."
        )
        connection = accept_host_connection(listener, transport_name="LAN")
        try:
            run_chat(connection, is_host=True)
        finally:
            try:
                connection.close()
            except OSError:
                pass
    finally:
        listener.close()
        _ACTIVE_LISTENER = None


def run_host_public() -> None:
    """Host TCP public IP không Tor; router phải forward cổng TCP này."""
    global _ACTIVE_LISTENER
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _ACTIVE_LISTENER = listener
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("0.0.0.0", 0))
        port = listener.getsockname()[1]
        listener.listen(1)
        public_ip = input("Nhập IP công cộng của máy Host: ").strip()
        if not public_ip:
            raise ValueError("Cần nhập IP công cộng để gửi cho peer.")
        safe_print("\n[PUBLIC HOST] Tor đã được tắt; TCP public trực tiếp.")
        safe_print(f"[PUBLIC HOST] Địa chỉ gửi cho peer: {public_ip}:{port}")
        safe_print("[PUBLIC HOST] Hãy cấu hình port forwarding và firewall trước khi chờ peer.")
        connection = accept_host_connection(listener, transport_name="PUBLIC")
        try:
            run_chat(connection, is_host=True)
        finally:
            connection.close()
    finally:
        listener.close()
        _ACTIVE_LISTENER = None


def run_join_public() -> None:
    """Join TCP public IP không Tor."""
    address = input("Nhập IP công cộng:cổng của Host: ").strip()
    safe_print("[*] Đang kết nối IP công cộng trực tiếp; không dùng Tor...")
    connection = create_public_socket(address)
    try:
        run_chat(connection, is_host=False)
    finally:
        connection.close()


def create_lan_socket(address: str) -> socket.socket:
    """Kết nối TCP trực tiếp tới IPv4/hostname trong mạng nội bộ."""
    value = address.strip()
    if ":" not in value:
        raise ValueError("Địa chỉ LAN phải có dạng IP:cổng, ví dụ 192.168.1.20:45678.")
    host, port_text = value.rsplit(":", 1)
    host = host.strip()
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError("Cổng LAN không hợp lệ.") from exc
    if not host or not (1 <= port <= 65535):
        raise ValueError("IP/hostname hoặc cổng LAN không hợp lệ.")
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.settimeout(CONNECT_TIMEOUT)
    try:
        connection.connect((host, port))
        connection.settimeout(None)
        return connection
    except Exception:
        connection.close()
        raise


def create_public_socket(address: str) -> socket.socket:
    """Kết nối TCP trực tiếp tới IP public/hostname, không dùng Tor."""
    return create_lan_socket(address)


def run_join_lan() -> None:
    """Join LAN trực tiếp, không khởi động Tor và không dùng SOCKS5."""
    address = input("Nhập IP:cổng LAN của Host: ").strip()
    safe_print("[*] Đang kết nối trực tiếp trong mạng nội bộ; không dùng Tor...")
    connection = create_lan_socket(address)
    try:
        run_chat(connection, is_host=False)
    finally:
        try:
            connection.close()
        except OSError:
            pass


def run_chat(connection: socket.socket, is_host: bool) -> None:
    global _ACTIVE_SESSION
    nickname = input("Nickname của bạn (mặc định Anonymous): ").strip() or "Anonymous"
    last_message_id: Optional[str] = None
    received_dir = Path.cwd() / "received_files"

    def on_event(event: dict) -> None:
        nonlocal last_message_id
        last_message_id = event.get("id")
        reply_note = f" ↪ {event['reply_to']}" if event.get("reply_to") else ""
        safe_print(f"\n[{event.get('nickname', 'Peer')}]{reply_note}: {event.get('text', '')}")

    def on_reaction(event: dict) -> None:
        target = f" ({event['message_id'][:8]})" if event.get("message_id") else ""
        safe_print(f"\n[Peer reaction{target}] {event.get('reaction', '')}")

    def on_profile(peer_nickname: str) -> None:
        safe_print(f"\n[*] Peer nickname: {peer_nickname}")

    def on_file(info: dict) -> None:
        received_dir.mkdir(parents=True, exist_ok=True)
        target = received_dir / info["filename"]
        if target.exists():
            target = received_dir / f"{target.stem}_{secrets.token_hex(4)}{target.suffix}"
        target.write_bytes(info["chunk"])
        safe_print(f"\n[+] Đã nhận chunk file {info['chunk_index'] + 1}/{info['total_chunks']}: {target}")

    session = ChatSession(
        connection,
        is_host=is_host,
        message_event_callback=on_event,
        reaction_event_callback=on_reaction,
        profile_callback=on_profile,
        file_callback=on_file,
        nickname=nickname,
    )
    _ACTIVE_SESSION = session
    try:
        session.handshake_and_confirm()
        session.start_receiver()
        safe_print("\n[*] Chat đã bắt đầu. Lệnh: /file PATH, /reply TEXT, /react EMOJI, exit.")
        while not session.stop_event.is_set():
            try:
                text = input(f"[{nickname}] ")
            except EOFError:
                text = "exit"
            command, _, argument = text.partition(" ")
            if text.strip().lower() == "exit":
                break
            if not text.strip():
                continue
            try:
                if command == "/file" and argument.strip():
                    session.send_file(argument.strip())
                elif command == "/react" and argument.strip():
                    session.send_reaction(argument.strip(), message_id=last_message_id)
                elif command == "/reply" and argument.strip():
                    session.send_text(argument.strip(), reply_to=last_message_id)
                else:
                    session.send_text(text)
            except (ConnectionError, OSError, RuntimeError, ValueError, FileNotFoundError) as exc:
                safe_print(f"[!] Không thể gửi dữ liệu: {exc}")
                if isinstance(exc, (ConnectionError, OSError)):
                    break
    finally:
        session.close(notify_peer=True)
        _ACTIVE_SESSION = None


def run_host(daemon: TorDaemon) -> None:
    """Host qua Tor; luồng E2EE phía dưới giống hệt chế độ LAN."""
    global _ACTIVE_LISTENER
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _ACTIVE_LISTENER = listener
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((SOCKS_HOST, 0))
        internal_port = listener.getsockname()[1]
        listener.listen(1)
        onion = daemon.create_ephemeral_service(internal_port)
        safe_print("\n[HOST] Onion address của bạn:")
        safe_print(f"        {onion}")
        safe_print(
            "[HOST] Hãy gửi địa chỉ này cho peer qua kênh an toàn, rồi chờ kết nối."
        )
        connection = accept_host_connection(listener, transport_name="Tor")
        try:
            run_chat(connection, is_host=True)
        finally:
            try:
                connection.close()
            except OSError:
                pass
    finally:
        listener.close()
        _ACTIVE_LISTENER = None


def run_join(daemon: TorDaemon) -> None:
    """Join qua Tor; luồng E2EE phía dưới giống hệt chế độ LAN."""
    onion = input("Nhập địa chỉ .onion của Host: ").strip()
    safe_print("[*] Đang kết nối tới onion service qua SOCKS5 Tor...")
    connection = create_join_socket(onion, socks_port=daemon.socks_port)
    try:
        run_chat(connection, is_host=False)
    finally:
        try:
            connection.close()
        except OSError:
            pass


def print_dependencies() -> None:
    safe_print(
        "\nYêu cầu: Python 3.9+, Tor, stem, cryptography và PySocks. "
        "Trên Windows dùng tor.exe; Linux/Android dùng binary tor đáng tin cậy."
    )


def main() -> int:
    global _ACTIVE_DAEMON
    print(BANNER)
    print_dependencies()
    install_signal_handlers()
    atexit.register(close_active_resources)

    try:
        while True:
            safe_print("\n[1] Host - tạo onion service qua Tor")
            safe_print("[2] Join - kết nối .onion qua Tor")
            safe_print("[3] Host LAN - IP nội bộ, không dùng Tor, vẫn E2EE")
            safe_print("[4] Join LAN - IP nội bộ, không dùng Tor, vẫn E2EE")
            safe_print("[5] Host public IP - Internet trực tiếp, không Tor, vẫn E2EE")
            safe_print("[6] Join public IP - Internet trực tiếp, không Tor, vẫn E2EE")
            safe_print("[7] Thoát")
            choice = input("Lựa chọn: ").strip()
            if choice == "7":
                return 0
            if choice not in ("1", "2", "3", "4", "5", "6"):

                safe_print("[!] Lựa chọn không hợp lệ.")
                continue

            _SHUTDOWN.clear()
            daemon: Optional[TorDaemon] = None
            try:
                if choice == "3":
                    # Không tạo TorDaemon trong chế độ LAN.
                    run_host_lan()
                elif choice == "4":
                    # Không tạo TorDaemon trong chế độ LAN.
                    run_join_lan()
                elif choice in ("5", "6"):
                    # Public IP dùng TCP trực tiếp; Host cần port forwarding.
                    if choice == "5":
                        run_host_public()
                    else:
                        run_join_public()
                else:
                    daemon = TorDaemon()
                    _ACTIVE_DAEMON = daemon
                    daemon.start()
                    if choice == "1":
                        run_host(daemon)
                    else:
                        run_join(daemon)
            except PermissionError as exc:
                safe_print(f"[!] {exc}")
            except KeyboardInterrupt:
                safe_print("\n[*] Đã hủy phiên.")
            except (ConnectionError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
                safe_print(f"[!] Không thể hoàn tất phiên: {exc}")
            finally:
                close_active_resources()
                if choice in ("3", "4", "5", "6"):
                    safe_print("[*] Phiên TCP trực tiếp đã dọn dẹp socket; Tor không được khởi động.")
                else:
                    safe_print("[*] Tài nguyên Tor và dữ liệu tạm đã được dọn dẹp.")
    except (KeyboardInterrupt, EOFError):
        safe_print("\n[*] Đang thoát CloakChat...")
        return 0
    except Exception as exc:
        safe_print(f"[!] Lỗi không mong muốn: {exc}")
        return 1
    finally:
        close_active_resources()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ChatSession",
    "TorDaemon",
    "create_join_socket",
    "create_orbot_join_socket",
    "create_public_socket",
    "decrypt_message",
    "decrypt_message_event",
    "decrypt_reaction",
    "decrypt_reaction_event",
    "decrypt_profile",
    "decrypt_file_chunk",
    "derive_session_key",
    "public_key_fingerprint",
    "sha512_fingerprint",
    "encrypt_message",
    "encrypt_chat_message",
    "encrypt_reaction",
    "encrypt_reaction_event",
    "encrypt_profile",
    "encrypt_file_chunk",
    "encrypt_voice_frame",
    "decrypt_voice_frame",
    "main",
    "recv_packet",
    "safety_number",
    "send_packet",
]


# End of CloakChat.py
