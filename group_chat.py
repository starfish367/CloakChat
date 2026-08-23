#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Group chat primitives for CloakChat.

Mode A is an authenticated Host relay: the Host decrypts incoming events and
re-encrypts them separately for each member. Mode B is deliberately not
silently downgraded; it requires a real group-key protocol and is rejected
until that protocol is enabled explicitly.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import socket
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

import CloakChat as core


MAX_GROUP_MEMBERS = 8
MODE_HOST_RELAY = "A"
MODE_TRUE_E2EE = "B"


class GroupProtocolError(RuntimeError):
    pass


class GroupHost:
    """Multi-member Host for mode A with explicit moderation operations."""

    def __init__(
        self,
        listener: socket.socket,
        nickname: str = "Host",
        mode: str = MODE_HOST_RELAY,
        max_members: int = MAX_GROUP_MEMBERS,
        confirm_callback: Optional[Callable[[str], bool]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        event_callback: Optional[Callable[[dict], None]] = None,
    ) -> None:
        if mode not in (MODE_HOST_RELAY, MODE_TRUE_E2EE):
            raise ValueError("Group mode must be A or B.")
        if not 1 <= max_members <= MAX_GROUP_MEMBERS:
            raise ValueError("Group size must be between 1 and 8.")
        self.listener = listener
        self.nickname = nickname.strip() or "Host"
        self.mode = mode
        self.group_key = os.urandom(32) if mode == MODE_TRUE_E2EE else None
        self.max_members = max_members
        self.confirm_callback = confirm_callback
        self.status_callback = status_callback
        self.event_callback = event_callback
        self.sessions: Dict[str, core.ChatSession] = {}
        self.nicknames: Dict[str, str] = {}
        self.banned = set()
        self.stop_event = threading.Event()
        self.accept_thread: Optional[threading.Thread] = None
        self.lock = threading.RLock()
        self.handshake_lock = threading.Lock()

    def _status(self, message: str) -> None:
        if self.status_callback:
            self.status_callback(message)

    def start(self) -> None:
        self.listener.listen(self.max_members)
        self.accept_thread = threading.Thread(target=self._accept_loop, name="cloakchat-group-accept", daemon=True)
        self.accept_thread.start()

    def _accept_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                connection, _peer = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            thread = threading.Thread(target=self._admit_client, args=(connection,), name="cloakchat-group-admit", daemon=True)
            thread.start()

    def _admit_client(self, connection: socket.socket) -> None:
        session: Optional[core.ChatSession] = None
        member_id = ""
        try:
            with self.lock:
                if len(self.sessions) >= self.max_members:
                    connection.close()
                    return
            session = core.ChatSession(
                connection,
                is_host=True,
                confirm_callback=self.confirm_callback,
                message_event_callback=lambda event: self._on_event(member_id, event),
                reaction_event_callback=lambda event: self._on_reaction(member_id, event),
                file_callback=lambda info: self._on_file(member_id, info),
                profile_callback=lambda nickname: self._on_profile(member_id, nickname),
                nickname=self.nickname,
                status_callback=self.status_callback,
                group_mode=self.mode == MODE_TRUE_E2EE,
                relay_mode=self.mode == MODE_TRUE_E2EE,
                group_event_callback=lambda event: self._on_group_event(member_id, event),
                raw_group_callback=lambda packet: self._on_group_packet(member_id, packet),
            )
            with self.handshake_lock:
                session.handshake_and_confirm()
            if session.remote_public is None:
                raise GroupProtocolError("Peer public key missing after handshake.")
            member_id = core.public_key_fingerprint(session.remote_public)
            with self.lock:
                if member_id in self.banned:
                    session.close(notify_peer=False)
                    return
                if len(self.sessions) >= self.max_members:
                    session.close(notify_peer=False)
                    return
                self.sessions[member_id] = session
                self.nicknames[member_id] = session.peer_nickname
            if self.group_key is not None:
                session.send_group_key(self.group_key)
            session.start_receiver()
            self._status(f"[GROUP] Member joined: {member_id[:12]}")
        except Exception as exc:
            self._status(f"[GROUP] Member rejected: {exc}")
            if session is not None:
                session.close(notify_peer=False)
            else:
                try:
                    connection.close()
                except OSError:
                    pass

    def _on_profile(self, member_id: str, nickname: str) -> None:
        with self.lock:
            if member_id:
                self.nicknames[member_id] = nickname
        if self.event_callback:
            self.event_callback({"type": "profile", "member_id": member_id, "nickname": nickname})

    def _on_group_packet(self, member_id: str, packet: bytes) -> None:
        if self.mode != MODE_TRUE_E2EE:
            return
        with self.lock:
            peers = [(mid, session) for mid, session in self.sessions.items() if mid != member_id]
        for _peer_id, session in peers:
            try:
                session.send_group_packet(packet)
            except (ConnectionError, OSError, RuntimeError):
                pass

    def _on_group_event(self, member_id: str, event: dict) -> None:
        if self.event_callback:
            self.event_callback({**event, "member_id": member_id})

    def _on_event(self, member_id: str, event: dict) -> None:
        if self.mode == MODE_TRUE_E2EE:
            return
        event = dict(event)
        event["member_id"] = member_id
        if self.event_callback:
            self.event_callback(event)
        with self.lock:
            peers = [(mid, session) for mid, session in self.sessions.items() if mid != member_id]
        for _peer_id, session in peers:
            try:
                session.send_chat_event(event)
            except (ConnectionError, OSError, RuntimeError):
                pass

    def _on_reaction(self, member_id: str, event: dict) -> None:
        if self.mode == MODE_TRUE_E2EE:
            return
        event = dict(event)
        event["member_id"] = member_id
        if self.event_callback:
            self.event_callback(event)
        with self.lock:
            peers = [(mid, session) for mid, session in self.sessions.items() if mid != member_id]
        for _peer_id, session in peers:
            try:
                session.send_reaction_event(event)
            except (ConnectionError, OSError, RuntimeError):
                pass

    def _on_file(self, member_id: str, info: dict) -> None:
        if self.mode == MODE_TRUE_E2EE:
            self._status("[GROUP] File transfer in Group B requires encrypted group-file chunks and is disabled in this release.")
            return
        if self.event_callback:
            self.event_callback({"type": "file", "member_id": member_id, **info})
        with self.lock:
            peers = [(mid, session) for mid, session in self.sessions.items() if mid != member_id]
        for _peer_id, session in peers:
            try:
                session.send_file_chunk(info)
            except (ConnectionError, OSError, RuntimeError, ValueError):
                pass

    def _members(self):
        with self.lock:
            return list(self.sessions.values())

    def send_message(self, text: str, reply_to: Optional[str] = None) -> str:
        event = {"v": 1, "id": secrets.token_hex(16), "text": text, "nickname": self.nickname}
        if reply_to:
            event["reply_to"] = str(reply_to)
        if self.event_callback:
            self.event_callback(event)
        for session in self._members():
            try:
                if self.mode == MODE_TRUE_E2EE:
                    session.send_group_packet(core.encrypt_group_event(self.group_key, {**event, "type": "message"}))
                else:
                    session.send_chat_event(event)
            except (ConnectionError, OSError, RuntimeError):
                pass
        return event["id"]

    def send_reaction(self, reaction: str, message_id: Optional[str] = None) -> None:
        event = {"v": 1, "reaction": reaction, "message_id": str(message_id or "")}
        if self.event_callback:
            self.event_callback({"type": "reaction", **event})
        for session in self._members():
            try:
                if self.mode == MODE_TRUE_E2EE:
                    session.send_group_packet(core.encrypt_group_event(self.group_key, {**event, "type": "reaction"}))
                else:
                    session.send_reaction_event(event)
            except (ConnectionError, OSError, RuntimeError):
                pass

    def send_file(self, path: str) -> None:
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(str(source))
        total_size = source.stat().st_size
        if not (1 <= total_size <= core.MAX_FILE_SIZE):
            raise ValueError("File phải có kích thước từ 1 đến 25 MiB.")
        digest = hashlib.sha256(source.read_bytes()).digest()
        total_chunks = (total_size + core.MAX_FILE_CHUNK_BYTES - 1) // core.MAX_FILE_CHUNK_BYTES
        transfer_id = os.urandom(16)
        with source.open("rb") as handle:
            for chunk_index in range(total_chunks):
                chunk = handle.read(core.MAX_FILE_CHUNK_BYTES)
                info = {"transfer_id": transfer_id, "filename": source.name, "total_size": total_size, "chunk_index": chunk_index, "total_chunks": total_chunks, "file_digest": digest, "chunk": chunk}
                for session in self._members():
                    try:
                        if self.mode == MODE_TRUE_E2EE:
                            session.send_group_packet(core.encrypt_file_chunk(self.group_key, transfer_id, source.name, total_size, chunk_index, total_chunks, digest, chunk))
                        else:
                            session.send_file_chunk(info)
                    except (ConnectionError, OSError, RuntimeError, ValueError):
                        pass
        if self.event_callback:
            self.event_callback({"type": "file_sent", "filename": source.name, "total_size": total_size})

    def kick(self, member_id: str, ban: bool = False) -> bool:
        with self.lock:
            session = self.sessions.pop(member_id, None)
            self.nicknames.pop(member_id, None)
            if ban:
                self.banned.add(member_id)
        if session is None:
            return False
        session.close(notify_peer=True)
        if self.mode == MODE_TRUE_E2EE:
            self.group_key = os.urandom(32)
            for remaining in self._members():
                try:
                    remaining.send_group_key(self.group_key)
                except (ConnectionError, OSError, RuntimeError):
                    pass
        self._status(f"[GROUP] {'Banned' if ban else 'Kicked'} member {member_id[:12]}")
        return True

    def stop(self) -> None:
        self.stop_event.set()
        try:
            self.listener.close()
        except OSError:
            pass
        with self.lock:
            sessions = list(self.sessions.values())
            self.sessions.clear()
        for session in sessions:
            session.close(notify_peer=False)


__all__ = ["GroupHost", "GroupProtocolError", "MAX_GROUP_MEMBERS", "MODE_HOST_RELAY", "MODE_TRUE_E2EE"]
