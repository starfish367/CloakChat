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

    def test_safety_number_is_30_digits(self):
        one = b"a" * 32
        two = b"b" * 32
        value = MODULE.safety_number(one, two)
        self.assertEqual(len(value.replace(" ", "")), 30)
        self.assertEqual(len(value.split()), 6)

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


if __name__ == "__main__":
    unittest.main()
