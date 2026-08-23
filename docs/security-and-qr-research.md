# Security and QR research

## OpenSSH fingerprints

The OpenBSD `ssh-keygen` manual documents `ssh-keygen -l` for displaying a public-key fingerprint and lists `md5` and `sha256` as its supported display hashes. OpenSSH-style verification is based on comparing a fingerprint of the public key through a trusted channel or known-hosts database; a short numeric code is not a replacement for the public-key fingerprint or the key exchange.

Source: https://man.openbsd.org/ssh-keygen

## Kivy camera

The Kivy 2.3.1 Camera example uses the `Camera` widget, toggles `play`, and captures frames with `export_to_png`. A QR scanner still needs a decoder and platform camera permissions; the Android build must request `CAMERA` runtime permission, while Linux camera availability depends on the installed camera provider/backend.

Source: https://kivy.org/doc/stable/examples/gen__camera__main__py.html

## Design decision

CloakChat should display a SHA-512 fingerprint derived from the X25519 public keys, but it must retain the existing key exchange and authenticated AES-GCM protocol. The fingerprint is for human verification and should not itself become an encryption key. The current Group B prototype encrypts group events and avoids plaintext handling in the relay loop, but the Host process creates/holds the group key; therefore it is not yet a server-untrusted E2EE guarantee. A fully server-untrusted design needs authenticated pairwise distribution of a client-owned group key and a formal membership/key-rotation protocol. File transfer uses encrypted, authenticated chunks with size limits and a final hash. A short 8-digit code can be implemented only as a pairing/session lookup code, never as the sole MitM defense.

## Group and moderation research

Signal's private group messaging design discusses pairwise authenticated exchanges, group key agreement, forward secrecy, deniability, and transcript consistency. Matrix moderation documentation distinguishes kick from permanent ban and shows that moderation removes access but does not guarantee deletion of copies already retained by a participant.

Sources:
- https://signal.org/blog/private-groups/
- https://matrix.org/docs/communities/moderation/

Implementation implication: group mode A lets the Host relay plaintext and therefore the Host can inspect content; group mode B uses group-key ciphertext and key rotation, but must be labeled prototype until the Host no longer owns the group key. A kick/ban event should rotate keys for future messages, invalidate the removed member's access, and clearly state that previously received files/screenshots cannot be remotely erased. Reply binds the referenced message identifier inside authenticated ciphertext to prevent ambiguous context.
