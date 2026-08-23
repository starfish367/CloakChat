import importlib.util
import socket
import threading
import unittest


SPEC = importlib.util.spec_from_file_location("cloakchat", "CloakChat.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


class ProtocolTests(unittest.TestCase):
    def test_x25519_hkdf_and_aes_gcm(self):
        private_a = X25519PrivateKey.generate()
        private_b = X25519PrivateKey.generate()
        public_a = private_a.public_key().public_bytes(
            MODULE.serialization.Encoding.Raw,
            MODULE.serialization.PublicFormat.Raw,
        )
        public_b = private_b.public_key().public_bytes(
            MODULE.serialization.Encoding.Raw,
            MODULE.serialization.PublicFormat.Raw,
        )
        key_a = MODULE.derive_session_key(private_a, public_b)
        key_b = MODULE.derive_session_key(private_b, public_a)
        self.assertEqual(key_a, key_b)
        self.assertEqual(len(key_a), 32)
        packet = MODULE.encrypt_message(key_a, "xin chào")
        self.assertEqual(MODULE.decrypt_message(key_b, packet), "xin chào")
        event_packet = MODULE.encrypt_chat_message(key_a, "trả lời", "Alice", message_id="m1", reply_to="m0")
        event = MODULE.decrypt_message_event(key_b, event_packet)
        self.assertEqual(event["nickname"], "Alice")
        self.assertEqual(event["reply_to"], "m0")

        reaction_packet = MODULE.encrypt_reaction(key_a, "👍")
        self.assertEqual(MODULE.decrypt_reaction(key_b, reaction_packet), "👍")

        voice_frame = b"\x01\x02" * 320
        voice_packet = MODULE.encrypt_voice_frame(key_a, voice_frame)
        self.assertEqual(MODULE.decrypt_voice_frame(key_b, voice_packet), voice_frame)

        profile_packet = MODULE.encrypt_profile(key_a, "Alice")
        self.assertEqual(MODULE.decrypt_profile(key_b, profile_packet), "Alice")

        transfer_id = b"t" * 16
        payload = b"hello encrypted file"
        digest = MODULE.hashlib.sha256(payload).digest()
        file_packet = MODULE.encrypt_file_chunk(key_a, transfer_id, "hello.txt", len(payload), 0, 1, digest, payload)
        file_info = MODULE.decrypt_file_chunk(key_b, file_packet)
        self.assertEqual(file_info["filename"], "hello.txt")
        self.assertEqual(file_info["chunk"], payload)

        group_key = b"g" * 32
        group_key_packet = MODULE.encrypt_group_key(key_a, group_key)
        self.assertEqual(MODULE.decrypt_group_key(key_b, group_key_packet), group_key)
        group_event_packet = MODULE.encrypt_group_event(group_key, {"v": 1, "type": "message", "id": "g1", "nickname": "Alice", "text": "hello group"})
        group_event = MODULE.decrypt_group_event(group_key, group_event_packet)
        self.assertEqual(group_event["type"], "message")
        self.assertEqual(group_event["text"], "hello group")

    def test_safety_number_is_sha512_fingerprint(self):
        one = b"a" * 32
        two = b"b" * 32
        value = MODULE.safety_number(one, two)
        self.assertTrue(value.startswith("SHA512:"))
        digest_text = value.removeprefix("SHA512:").replace(":", "")
        self.assertEqual(len(digest_text), 128)
        self.assertEqual(len(value.split(":")), 9)

    def test_length_prefixed_frame(self):
        left, right = socket.socketpair()
        received = []

        def reader():
            received.append(MODULE.recv_packet(right))

        thread = threading.Thread(target=reader)
        thread.start()
        MODULE.send_packet(left, b"frame")
        thread.join(timeout=2)
        left.close()
        right.close()
        self.assertEqual(received, [b"frame"])

    def test_direct_lan_socket(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        received = []

        def accept_once():
            connection, _ = server.accept()
            received.append(connection.recv(4))
            connection.close()

        thread = threading.Thread(target=accept_once)
        thread.start()
        client = MODULE.create_lan_socket(f"127.0.0.1:{port}")
        client.sendall(b"LAN!")
        client.close()
        thread.join(timeout=2)
        server.close()
        self.assertEqual(received, [b"LAN!"])


if __name__ == "__main__":
    unittest.main()
