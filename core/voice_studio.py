#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_voice_studio.py - CapCut Text-to-Speech (TTS) Studio
Synthesizes speech using CapCut Cloud Voice Engine, supports Vietnamese and multi-language voices,
generates audio files (MP3/WAV), and provides draft audio material preparation.
"""

import os
import sys
import time
import uuid
import json
import base64
import urllib.request
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

sys.stdout.reconfigure(encoding="utf-8")

from capcut_tts_api.client import CapCutClient
from capcut_tts_api.models import VoiceInfo


class CapCutVoiceStudio:
    """Manages CapCut Text-to-Speech voice synthesis, preview, and draft export."""

    def __init__(self):
        self.client = CapCutClient()
        self.voices = self.client.list_voices()

    def get_voice_list(self) -> List[Dict[str, str]]:
        """Return list of available voice dictionaries for GUI selection."""
        res = []
        for v in self.voices:
            res.append({
                "voice_type": v.voice_type,
                "display_name": v.display_name,
                "lang": v.lang,
                "resource_id": v.resource_id,
            })
        return res

    def synthesize(
        self,
        text: str,
        voice_type: str = "BV421_vivn_streaming",
        rate: float = 1.0,
        pitch: float = 0.0,
        output_path: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Synthesizes speech using CapCut Cloud TTS API.
        Returns: (success: bool, message: str, file_path: Optional[str])
        """
        text = text.strip()
        if not text:
            return False, "Nội dung văn bản không được để trống.", None

        if not output_path:
            temp_dir = Path(__file__).resolve().parent / "temp_audio"
            temp_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(temp_dir / f"tts_{uuid.uuid4().hex[:8]}.mp3")

        rate_str = f"{rate:.1f}"

        try:
            # Generate speech via CapCutClient
            res = self.client.generate_speech(
                texts=text,
                voice=voice_type,
                rate=rate_str,
                wait=True,
                poll_interval=1.5,
                timeout=45.0,
            )

            # Check tasks payload
            tasks = (res.get("data") or {}).get("tasks") or []
            if not tasks:
                return False, f"API không trả về kết quả TTS: {res}", None

            task = tasks[0]
            if task.get("status") not in ("succeed", "success"):
                return False, f"Tạo giọng nói thất bại: {task.get('status')}", None

            payload_raw = task.get("payload", "{}")
            payload = json.loads(payload_raw) if isinstance(payload_raw, str) else payload_raw
            
            # Primary: audio_subtitles -> speech_url
            audio_url = None
            audio_subtitles = payload.get("audio_subtitles") or []
            if audio_subtitles and isinstance(audio_subtitles, list):
                audio_url = audio_subtitles[0].get("speech_url")

            if not audio_url:
                audio_url = payload.get("audio_url") or payload.get("url") or payload.get("result_url")

            # If binary audio base64 is returned:
            audio_data_b64 = payload.get("audio_data") or payload.get("data")
            if audio_data_b64:
                audio_bytes = base64.b64decode(audio_data_b64)
                with open(output_path, "wb") as f:
                    f.write(audio_bytes)
                return True, f"Tạo giọng nói thành công: {output_path}", output_path

            # If download URL is returned:
            if audio_url:
                req = urllib.request.Request(
                    audio_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    with open(output_path, "wb") as f:
                        f.write(resp.read())
                return True, f"Tải âm thanh thành công: {output_path}", output_path

            return False, f"Không tìm thấy audio_url trong payload: {payload}", None

        except Exception as exc:
            return False, f"Lỗi tạo giọng đọc: {exc}", None


if __name__ == "__main__":
    studio = CapCutVoiceStudio()
    print("=== CAPCUT VOICE STUDIO ===")
    voices = studio.get_voice_list()
    print(f"Total Voices Loaded: {len(voices)}")
    for v in voices:
        print(f" - [{v['lang']}] {v['display_name']} ({v['voice_type']})")
