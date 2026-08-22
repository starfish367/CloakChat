import json
import tempfile
import unittest
from pathlib import Path

from contacts_store import ContactStore
from invite_utils import create_invite, parse_invite


class FeatureTests(unittest.TestCase):
    def test_invite_round_trip_and_tamper_detection(self):
        invite = create_invite("lan", "192.168.1.20:45678", "Host")
        parsed = parse_invite(invite)
        self.assertEqual(parsed["transport"], "lan")
        self.assertEqual(parsed["address"], "192.168.1.20:45678")
        self.assertEqual(parsed["name"], "Host")
        encoded = invite[:-1] + ("A" if invite[-1] != "A" else "B")
        with self.assertRaises(ValueError):
            parse_invite(encoded)

    def test_local_contact_store(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ContactStore(directory)
            store.save("Host", create_invite("tor", "example.onion", "Host"))
            contacts = store.list_contacts()
            self.assertEqual(len(contacts), 1)
            self.assertEqual(contacts[0]["name"], "Host")
            store.delete("Host")
            self.assertEqual(store.list_contacts(), [])


if __name__ == "__main__":
    unittest.main()
