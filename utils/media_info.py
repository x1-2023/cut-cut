# -*- coding: utf-8 -*-
"""
utils/media_info.py - FFprobe metadata extraction, MD5 and CRC32 hashing
"""

import json
import hashlib
import binascii
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


def calc_md5(file_path: Path | str) -> str:
    """Calculate MD5 hex of local file with 4MB read blocks."""
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def calc_crc32(data: bytes) -> str:
    """Calculate 8-character zero-padded CRC32 hex."""
    return f"{binascii.crc32(data) & 0xFFFFFFFF:08x}"


def get_media_info(file_path: str | Path) -> Dict[str, Any]:
    """
    Extracts duration, dimensions, fps, bitrate and codec using ffprobe.
    """
    p = Path(file_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size,bit_rate",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name,codec_type",
        "-of", "json",
        str(p),
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
    except Exception as e:
        return {
            "duration": 0.0,
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "size": p.stat().st_size,
            "error": str(e),
        }

    duration = float(data.get("format", {}).get("duration", 0.0))
    size = int(data.get("format", {}).get("size", p.stat().st_size))

    width = 1920
    height = 1080
    fps = 30.0
    codec = "h264"

    for st in data.get("streams", []):
        if st.get("codec_type") == "video":
            width = int(st.get("width", 1920))
            height = int(st.get("height", 1080))
            codec = st.get("codec_name", "h264")
            r_fps = st.get("r_frame_rate", "30/1")
            try:
                if "/" in r_fps:
                    num, den = r_fps.split("/")
                    fps = round(float(num) / float(den), 2)
                else:
                    fps = float(r_fps)
            except Exception:
                fps = 30.0
            break

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "size": size,
        "codec": codec,
    }


def get_media_duration(file_path: str | Path) -> float:
    """Returns media duration in seconds."""
    info = get_media_info(file_path)
    return float(info.get("duration", 0.0))
