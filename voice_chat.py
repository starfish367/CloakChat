#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voice chat tùy chọn, truyền audio frame qua ChatSession E2EE.

Desktop dùng sounddevice/PortAudio. Android dùng API native AudioRecord và
AudioTrack thông qua pyjnius, không cần biên dịch sounddevice trong APK.
"""

from __future__ import annotations

import os
import queue
import threading
from typing import Optional


class VoiceChat:
    """Thu/phát PCM mono 16 kHz qua ChatSession đã handshake."""

    SAMPLE_RATE = 16_000
    BLOCK_SIZE = 320  # 20 ms PCM16 mono = 640 bytes

    def __init__(self, session, status_callback=None):
        self.session = session
        self.status_callback = status_callback
        self.input_stream = None
        self.output_stream = None
        self.android_record = None
        self.android_track = None
        self.android_mode = bool(os.environ.get("ANDROID_ARGUMENT"))
        self.capture_queue: queue.Queue[bytes] = queue.Queue(maxsize=50)
        self.playback_queue: queue.Queue[bytes] = queue.Queue(maxsize=50)
        self.stop_event = threading.Event()
        self.capture_thread: Optional[threading.Thread] = None

    def _status(self, value: str):
        if self.status_callback:
            self.status_callback(value)

    def start(self):
        if self.capture_thread and self.capture_thread.is_alive():
            return
        if self.android_mode:
            self._start_android()
        else:
            self._start_desktop()

    def _start_desktop(self):
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError(
                "Voice desktop cần sounddevice và PortAudio."
            ) from exc

        def input_callback(indata, _frames, _time, status):
            if status:
                self._status(f"[VOICE] {status}")
            try:
                self.capture_queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

        def output_callback(outdata, _frames, _time, status):
            if status:
                self._status(f"[VOICE] {status}")
            try:
                data = self.playback_queue.get_nowait()
            except queue.Empty:
                data = b""
            outdata[:] = b"\x00" * len(outdata)
            outdata[: min(len(data), len(outdata))] = data[: len(outdata)]

        self.input_stream = sd.RawInputStream(
            samplerate=self.SAMPLE_RATE,
            blocksize=self.BLOCK_SIZE,
            channels=1,
            dtype="int16",
            callback=input_callback,
        )
        self.output_stream = sd.RawOutputStream(
            samplerate=self.SAMPLE_RATE,
            blocksize=self.BLOCK_SIZE,
            channels=1,
            dtype="int16",
            callback=output_callback,
        )
        self.session.voice_callback = self._receive_audio
        self.stop_event.clear()
        self.input_stream.start()
        self.output_stream.start()
        self.capture_thread = threading.Thread(target=self._send_loop, name="cloakchat-voice-send", daemon=True)
        self.capture_thread.start()
        self._status("[VOICE] Đã bật; audio frame được mã hóa AES-256-GCM.")

    def _start_android(self):
        try:
            from jnius import autoclass
            AudioRecord = autoclass("android.media.AudioRecord")
            AudioTrack = autoclass("android.media.AudioTrack")
            AudioFormat = autoclass("android.media.AudioFormat")
            AudioSource = autoclass("android.media.MediaRecorder$AudioSource")
            AudioManager = autoclass("android.media.AudioManager")
        except Exception as exc:
            raise RuntimeError("APK thiếu pyjnius hoặc Android audio API.") from exc

        encoding = AudioFormat.ENCODING_PCM_16BIT
        in_channel = AudioFormat.CHANNEL_IN_MONO
        out_channel = AudioFormat.CHANNEL_OUT_MONO
        min_buffer = AudioRecord.getMinBufferSize(self.SAMPLE_RATE, in_channel, encoding)
        if min_buffer <= 0:
            raise RuntimeError("Android không cung cấp microphone PCM16 16 kHz.")
        buffer_size = max(int(min_buffer), self.BLOCK_SIZE * 2)
        self.android_record = AudioRecord(
            AudioSource.DEFAULT,
            self.SAMPLE_RATE,
            in_channel,
            encoding,
            buffer_size,
        )
        self.android_track = AudioTrack(
            AudioManager.STREAM_MUSIC,
            self.SAMPLE_RATE,
            out_channel,
            encoding,
            buffer_size,
            AudioTrack.MODE_STREAM,
        )
        self.session.voice_callback = self._receive_audio
        self.stop_event.clear()
        self.android_record.startRecording()
        self.android_track.play()
        self.capture_thread = threading.Thread(target=self._android_capture_loop, name="cloakchat-android-voice", daemon=True)
        self.capture_thread.start()
        self._status("[VOICE] Android microphone đã bật; audio frame được mã hóa AES-256-GCM.")

    def _send_loop(self):
        while not self.stop_event.is_set():
            try:
                frame = self.capture_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.session.send_voice_frame(frame)
            except Exception as exc:
                self._status(f"[VOICE] Không thể gửi audio: {exc}")
                self.stop_event.set()

    def _android_capture_loop(self):
        buffer = bytearray(self.BLOCK_SIZE * 2)
        while not self.stop_event.is_set():
            try:
                count = self.android_record.read(buffer, 0, len(buffer))
                if count and count > 0:
                    self.session.send_voice_frame(bytes(buffer[:count]))
            except Exception as exc:
                self._status(f"[VOICE] Lỗi microphone Android: {exc}")
                self.stop_event.set()

    def _receive_audio(self, frame: bytes):
        if self.android_mode and self.android_track is not None:
            try:
                self.android_track.write(bytearray(frame), 0, len(frame))
            except Exception as exc:
                self._status(f"[VOICE] Lỗi loa Android: {exc}")
            return
        try:
            self.playback_queue.put_nowait(frame)
        except queue.Full:
            pass

    def stop(self):
        self.stop_event.set()
        if self.android_record is not None:
            try:
                self.android_record.stop()
                self.android_record.release()
            except Exception:
                pass
        if self.android_track is not None:
            try:
                self.android_track.stop()
                self.android_track.release()
            except Exception:
                pass
        self.android_record = None
        self.android_track = None
        for stream in (self.input_stream, self.output_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self.input_stream = None
        self.output_stream = None
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1)
        self.capture_thread = None
        self.session.voice_callback = None
