# -*- coding: utf-8 -*-
"""
config/settings.py - Global settings, file paths, and ByteDance API constants
"""

from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
SESSION_FILE = CONFIG_DIR / "session.json"
ACCOUNTS_FILE = CONFIG_DIR / "accounts.json"
PRESETS_FILE = CONFIG_DIR / "presets.json"
VOICES_FILE = CONFIG_DIR / "voices.json"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"

# ByteDance CapCut Platform Constants
APP_ID = 348188
APP_VERSION = "15.4.0"
SDK_VERSION = "19.3.0"
APP_NAME = "CapCut Automation Studio"

# ByteDance VOD / TOS Cloud Infrastructure
VOD_HOST = "vod-ap-singapore-1.bytevcloudapi.com"
VOD_SPACE = "capcut_vcloud_upload_sg"
VOD_REGION = "sdwdmwlll"
VOD_SERVICE = "vod"

# CapCut API Endpoints
EDIT_API_BASE = "https://edit-api-sg.capcut.com"
EVERCLOUD_MEDIA_BASE = "https://sg-gcp-media.evercloud.capcut.com"

# Network & Concurrency
DEFAULT_UPLOAD_WORKERS = 8
DEFAULT_RENDER_WORKERS = 4
MAX_CHUNK_DURATION_SEC = 1200  # 20 minutes default threshold

# Dynamic Chunk Sizing for Upload (Bytes)
CHUNK_SIZE_SMALL = 3 * 1024 * 1024     # <= 50MB
CHUNK_SIZE_MEDIUM = 10 * 1024 * 1024   # 50MB - 1GB
CHUNK_SIZE_LARGE = 20 * 1024 * 1024    # > 1GB
