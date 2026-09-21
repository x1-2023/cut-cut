#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/auto_caption.py - CapCut Cloud Auto-Caption (ASR) Engine
Recognizes speech from video using CapCut Cloud AI, extracts accurate timestamps,
and injects stylized subtitle tracks directly into draft_content.json.
"""

import os
import sys
import time
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable

from capcut_tts_api.client import CapCutClient
from capcut_tts_api.models import SubtitleResult, Utterance

LANGUAGE_MAP = {
    "Tiếng Việt": "vi-VN",
    "Tiếng Anh": "en-US",
    "Tự động nhận diện": "auto",
    "Tiếng Trung": "zh-CN",
    "Tiếng Nhật": "ja-JP",
    "Tiếng Hàn": "ko-KR",
    "Tiếng Pháp": "fr-FR",
    "Tiếng Tây Ban Nha": "es-ES",
    "Tiếng Đức": "de-DE",
    "Tiếng Nga": "ru-RU",
    "Tiếng Thái": "th-TH",
    "Tiếng Indonesia": "id-ID",
}

LANGUAGE_CODES = {v: k for k, v in LANGUAGE_MAP.items()}


class CapCutAutoCaption:
    """Manages CapCut Cloud speech recognition and subtitle draft injection."""

    def __init__(self):
        self.client = CapCutClient()

    def transcribe(
        self,
        video_path: str,
        language: str = "vi-VN",
        log_cb: Optional[Callable[[str], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Transcribes speech in video via CapCut Cloud ASR.
        Returns a list of utterance dicts: [{'text': str, 'start_ms': int, 'end_ms': int}]
        """
        def log(msg: str):
            if log_cb:
                log_cb(msg)
            else:
                print(msg)

        lang_code = LANGUAGE_MAP.get(language, language)
        log(f"[*] Gửi video lên CapCut Cloud AI nhận dạng phụ đề ({lang_code})...")

        res = self.client.transcribe_file(
            file_path=video_path,
            language=lang_code,
            wait=True,
            timeout=120.0,
        )

        sub_res = self.client.extract_subtitles(res)
        utterances_data = []

        for u in sub_res.utterances:
            t = u.text.strip()
            if t:
                utterances_data.append({
                    "text": t,
                    "start_ms": int(u.start_time),
                    "end_ms": int(u.end_time),
                })

        log(f"[+] Nhận diện thành công: {len(utterances_data)} đoạn phụ đề thoại.")
        return utterances_data

    @staticmethod
    def inject_subtitles_to_draft(
        draft_content: Dict[str, Any],
        utterances: List[Dict[str, Any]],
        font_size: float = 6.0,
        text_color: str = "#ffffff",
        stroke_color: str = "#000000",
        stroke_width: int = 15,
        y_position: float = -0.7,
    ) -> Dict[str, Any]:
        """
        Injects recognized subtitles into draft_content.json matching CapCut Web spec.
        """
        if not utterances:
            return draft_content

        materials = draft_content.setdefault("materials", {})
        texts_list = materials.setdefault("texts", [])
        tracks = draft_content.setdefault("tracks", [])

        # Color conversion for fill style [r, g, b] in [0, 1]
        try:
            r = int(text_color[1:3], 16) / 255.0
            g = int(text_color[3:5], 16) / 255.0
            b = int(text_color[5:7], 16) / 255.0
        except Exception:
            r, g, b = 1.0, 1.0, 1.0

        segments = []

        for idx, item in enumerate(utterances):
            text_str = item["text"]
            start_ms = item["start_ms"]
            end_ms = item["end_ms"]
            dur_ms = max(100, end_ms - start_ms)

            text_id = str(uuid.uuid4()).upper()

            content_obj = {
                "text": text_str,
                "styles": [
                    {
                        "size": font_size,
                        "fill": {
                            "alpha": 1.0,
                            "content": {
                                "render_type": "solid",
                                "solid": {
                                    "alpha": 1.0,
                                    "color": [r, g, b],
                                },
                            },
                        },
                        "font": {"id": "", "path": ""},
                        "range": [0, len(text_str)],
                    }
                ],
            }

            text_mat = {
                "id": text_id,
                "type": "subtitle",
                "name": "",
                "content": json.dumps(content_obj, ensure_ascii=False),
                "base_content": "",
                "global_alpha": 1.0,
                "background_color": "",
                "background_alpha": 1.0,
                "background_style": 0,
                "layer_weight": 0,
                "letter_spacing": 0,
                "line_spacing": 0.02,
                "has_shadow": False,
                "shadow_color": "",
                "shadow_alpha": 0.8,
                "shadow_smoothing": 1.0,
                "shadow_distance": 8.0,
                "shadow_angle": -45.0,
                "border_alpha": 1.0,
                "border_color": stroke_color,
                "border_width": stroke_width,
                "style_name": "",
                "text_color": text_color,
                "text_preset_resource_id": "",
                "check_flag": 7,
                "font_id": "",
                "font_path": "",
                "font_name": "",
                "font_size": font_size,
                "alignment": 1,
                "sub_type": 0,
            }
            texts_list.append(text_mat)

            segment = {
                "id": str(uuid.uuid4()),
                "material_id": text_id,
                "render_index": 14000 + idx,
                "enable_lut": True,
                "enable_adjust": True,
                "enable_hsl": True,
                "visible": True,
                "group_id": "",
                "enable_color_curves": True,
                "track_render_index": 1,
                "enable_color_wheels": True,
                "track_attribute": 0,
                "is_placeholder": False,
                "template_id": "",
                "enable_smart_color_adjust": False,
                "template_scene": "default",
                "enable_color_match_adjust": False,
                "enable_color_correct_adjust": False,
                "enable_adjust_mask": True,
                "raw_segment_id": "",
                "target_timerange": {
                    "start": int(start_ms * 1000),
                    "duration": int(dur_ms * 1000),
                },
                "clip": {
                    "rotation": 0.0,
                    "alpha": 1.0,
                    "scale": {"x": 1.0, "y": 1.0},
                    "transform": {"x": 0.0, "y": y_position},
                    "flip": {"vertical": False, "horizontal": False},
                },
            }
            segments.append(segment)

        # Create or append to subtitle track
        existing_text_track = next((t for t in tracks if t.get("type") == "text"), None)
        if existing_text_track:
            existing_text_track.setdefault("segments", []).extend(segments)
        else:
            tracks.append({
                "id": str(uuid.uuid4()),
                "type": "text",
                "flag": 0,
                "segments": segments,
            })

        return draft_content
