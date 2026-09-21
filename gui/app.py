#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_studio_gui.py - CapCut Studio Pro Desktop Application
Redesigned according to CAPCUT_STUDIO_PRO_GUI_REDESIGN.md specification:
- Automation Workbench / Job Builder architecture
- Fixed Left Sidebar navigation (Create, Effects, Voice, Exports, Accounts)
- Clean compact header (Brand, Status, Account pill)
- 65/35 Create Job workbench: Input & Collapsible Recipe Accordion on left,
  Live Reactive Job Summary & Output Mode & Primary Action Button on right
- Collapsible Technical Log & Progress Queue at bottom
- Preset System (Save / Load / Delete recipe presets)
- Catalog-style Effects Library with 'Use in Current Recipe'
- 60/40 Voice Studio (TTS) with 2-second audio preview & 'Add as BGM'
- Searchable Exports table with instant play & open folder
- Clean Accounts Manager with modal '+ Add Account' dialog
"""

import os
import sys
import time
import json
import uuid
import threading
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")

import customtkinter as ctk
from tkinter import filedialog, messagebox

# Theme and Color System
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CLR_BG_APP = "#111315"
CLR_BG_PANEL = "#181a1d"
CLR_BG_CARD = "#202328"
CLR_BG_INPUT = "#292d32"
CLR_BORDER = "#34383e"
CLR_PRIMARY = "#38bdf8"
CLR_SUCCESS = "#22c55e"
CLR_WARNING = "#f59e0b"
CLR_DANGER = "#ef4444"
CLR_TXT_MAIN = "#f1f5f9"
CLR_TXT_MUTED = "#94a3b8"

# Import Core Modules
from config.settings import PRESETS_FILE, SESSION_FILE, ACCOUNTS_FILE, DEFAULT_OUTPUT_DIR
from core.auth import CapCutAuth
from core.auto_login import CapCutAutoLogin
from core.account_manager import CapCutAccountManager
from core.effects_catalog import CapCutEffectsCatalog
from core.voice_studio import CapCutVoiceStudio
from core.draft_builder import make_draft, save_local_capcut_draft, render_draft_cloud, render_video_auto_chunked_cloud, get_duration

DEFAULT_PRESETS = {
    "TikTok Fire v3": {
        "video": {"speed": 1.1, "scale": 110, "volume_db": 20.0},
        "effect": {"name": "Ngọn lửa", "speed": 13, "air": 35},
        "audio": {"voice_sharpen": True, "vocal_sep": False, "bgm_path": "", "bgm_db": 0.0},
        "overlay": {"path": "", "chroma_enabled": True, "chroma_intensity": 70},
        "color": {"temperature": 0, "tone": 0, "saturation": 0, "contrast": 0, "shadow": 0},
        "output": {"mode": "cloud", "resolution": "1080p", "fps": 30},
    },
    "Movie Recap Soft": {
        "video": {"speed": 1.0, "scale": 105, "volume_db": 10.0},
        "effect": {"name": "Sương mù", "speed": 8, "air": 25},
        "audio": {"voice_sharpen": True, "vocal_sep": True, "bgm_path": "", "bgm_db": -6.0},
        "overlay": {"path": "", "chroma_enabled": True, "chroma_intensity": 70},
        "color": {"temperature": 10, "tone": -5, "saturation": 5, "contrast": 10, "shadow": -5},
        "output": {"mode": "cloud", "resolution": "1080p", "fps": 30},
    },
    "Glitter Shorts": {
        "video": {"speed": 1.15, "scale": 115, "volume_db": 15.0},
        "effect": {"name": "Mưa kim tuyến", "speed": 20, "air": 40},
        "audio": {"voice_sharpen": False, "vocal_sep": False, "bgm_path": "", "bgm_db": 0.0},
        "overlay": {"path": "", "chroma_enabled": False, "chroma_intensity": 70},
        "color": {"temperature": 5, "tone": 5, "saturation": 10, "contrast": 5, "shadow": 0},
        "output": {"mode": "cloud", "resolution": "1080p", "fps": 60},
    },
}


class CapCutStudioApp(ctk.CTk):
    """Modern Desktop Automation Workbench for CapCut."""

    def __init__(self):
        super().__init__()

        self.title("CapCut Studio Pro")
        self.geometry("1320x880")
        self.minsize(1100, 720)
        self.configure(fg_color=CLR_BG_APP)

        # Core Engines
        self.auth = CapCutAuth()
        self.acc_mgr = CapCutAccountManager()
        self.effects_catalog = CapCutEffectsCatalog()
        self.voice_studio = CapCutVoiceStudio()

        # State
        self.is_processing = False
        self.active_nav = "create"
        self.log_visible = False
        self.presets = dict(DEFAULT_PRESETS)
        self._load_presets()

        # Batch Automation State
        self.batch_running = False
        self.batch_stop_requested = False
        self.batch_videos = []
        self.batch_items_ui = {}
        self.batch_stats = {"total": 0, "running": 0, "done": 0, "failed": 0}

        # Build UI Architecture
        self._build_header()
        self._build_body_layout()

        # Initial background sync
        self.after(200, self._initial_sync)

    # --------------------------------------------------------------------------
    # Header
    # --------------------------------------------------------------------------
    def _build_header(self):
        header = ctk.CTkFrame(self, height=54, corner_radius=0, fg_color=CLR_BG_PANEL)
        header.pack(fill="x", side="top")

        # Brand
        brand_f = ctk.CTkFrame(header, fg_color="transparent")
        brand_f.pack(side="left", padx=20, pady=10)

        ctk.CTkLabel(
            brand_f,
            text="CAPCUT STUDIO PRO",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=CLR_PRIMARY,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            brand_f,
            text="AUTOMATION WORKBENCH",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=CLR_TXT_MUTED,
        ).pack(side="left", pady=(3, 0))

        # Status Badges
        right_f = ctk.CTkFrame(header, fg_color="transparent")
        right_f.pack(side="right", padx=20, pady=10)

        self.hdr_cloud_badge = ctk.CTkLabel(
            right_f,
            text="● Cloud Ready",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=CLR_SUCCESS,
            fg_color="#14532d",
            corner_radius=6,
            padx=10,
            pady=4,
        )
        self.hdr_cloud_badge.pack(side="left", padx=(0, 10))

        self.hdr_account_badge = ctk.CTkLabel(
            right_f,
            text="PRO · 5d 21h",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24",
            fg_color="#332405",
            corner_radius=6,
            padx=10,
            pady=4,
        )
        self.hdr_account_badge.pack(side="left", padx=(0, 10))

        self.hdr_user_btn = ctk.CTkButton(
            right_f,
            text="Account: ...",
            font=ctk.CTkFont(size=12),
            fg_color=CLR_BG_CARD,
            hover_color=CLR_BORDER,
            height=30,
            command=lambda: self._switch_nav("accounts"),
        )
        self.hdr_user_btn.pack(side="left")

    # --------------------------------------------------------------------------
    # Body Layout: Fixed Left Sidebar + Main Content Container
    # --------------------------------------------------------------------------
    def _build_body_layout(self):
        body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        body.pack(fill="both", expand=True)

        # 1. Left Fixed Sidebar (200px)
        self.sidebar = ctk.CTkFrame(body, width=200, corner_radius=0, fg_color=CLR_BG_PANEL)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Nav Buttons
        self.nav_btns: Dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("create", "🎬  Create Job"),
            ("batch", "⚡  Batch Automation"),
            ("effects", "✨  Effect Library"),
            ("voice", "🎙  Voice Studio"),
            ("exports", "📦  Exports History"),
            ("accounts", "👥  Account Manager"),
        ]

        ctk.CTkFrame(self.sidebar, height=12, fg_color="transparent").pack()
        for key, label in nav_items:
            btn = ctk.CTkButton(
                self.sidebar,
                text=label,
                anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
                height=42,
                corner_radius=8,
                fg_color="transparent",
                text_color=CLR_TXT_MAIN,
                hover_color=CLR_BG_CARD,
                command=lambda k=key: self._switch_nav(k),
            )
            btn.pack(fill="x", padx=10, pady=4)
            self.nav_btns[key] = btn

        # 2. Main Content Container
        self.content_container = ctk.CTkFrame(body, fg_color="transparent", corner_radius=0)
        self.content_container.pack(side="left", fill="both", expand=True)

        # Build Pages
        self.page_create = self._build_page_create()
        self.page_batch = self._build_page_batch()
        self.page_effects = self._build_page_effects()
        self.page_voice = self._build_page_voice()
        self.page_exports = self._build_page_exports()
        self.page_accounts = self._build_page_accounts()

        # Show default page
        self._switch_nav("create")

    def _switch_nav(self, key: str):
        self.active_nav = key
        for k, btn in self.nav_btns.items():
            if k == key:
                btn.configure(fg_color="#0284c7", text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent", text_color=CLR_TXT_MAIN)

        for p in [self.page_create, self.page_batch, self.page_effects, self.page_voice, self.page_exports, self.page_accounts]:
            p.pack_forget()

        if key == "create":
            self.page_create.pack(fill="both", expand=True)
            self._update_live_summary()
        elif key == "batch":
            self.page_batch.pack(fill="both", expand=True)
            self._update_batch_stat_cards()
        elif key == "effects":
            self.page_effects.pack(fill="both", expand=True)
        elif key == "voice":
            self.page_voice.pack(fill="both", expand=True)
        elif key == "exports":
            self.page_exports.pack(fill="both", expand=True)
            self._refresh_exports_table()
        elif key == "accounts":
            self.page_accounts.pack(fill="both", expand=True)

    # --------------------------------------------------------------------------
    # PAGE 1: CREATE JOB (Automation Workbench 65% / 35%)
    # --------------------------------------------------------------------------
    def _build_page_create(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.content_container, fg_color="transparent")

        # Top 2-Column Area
        top_area = ctk.CTkFrame(page, fg_color="transparent")
        top_area.pack(fill="both", expand=True, padx=16, pady=(12, 6))

        # ======================================================================
        # LEFT ~65%: Input Card & Recipe Accordion
        # ======================================================================
        left_col = ctk.CTkScrollableFrame(top_area, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # --- Card 1: INPUT ---
        in_card = ctk.CTkFrame(left_col, fg_color=CLR_BG_CARD, corner_radius=10)
        in_card.pack(fill="x", pady=(0, 10))

        in_hdr = ctk.CTkFrame(in_card, fg_color="transparent")
        in_hdr.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(in_hdr, text="SINGLE VIDEO SOURCE", font=ctk.CTkFont(size=14, weight="bold"), text_color=CLR_PRIMARY).pack(side="left")

        ctk.CTkLabel(
            in_hdr,
            text="Tạo công thức & xem trước (Hàng loạt: dùng tab Batch)",
            font=ctk.CTkFont(size=11),
            text_color=CLR_TXT_MUTED,
        ).pack(side="right")

        in_input_f = ctk.CTkFrame(in_card, fg_color="transparent")
        in_input_f.pack(fill="x", padx=16, pady=4)

        self.input_path_entry = ctk.CTkEntry(in_input_f, placeholder_text="Chọn file video để dựng công thức & xem trước...", height=32, fg_color=CLR_BG_INPUT, border_color=CLR_BORDER)
        self.input_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.in_browse_btn = ctk.CTkButton(in_input_f, text="Browse Video", width=110, height=32, command=self._browse_input_source)
        self.in_browse_btn.pack(side="left")

        self.input_detected_lbl = ctk.CTkLabel(in_card, text="Chưa chọn file video nguồn", font=ctk.CTkFont(size=12), text_color=CLR_TXT_MUTED)
        self.input_detected_lbl.pack(anchor="w", padx=16, pady=(2, 8))

        # Parameters Row
        param_f = ctk.CTkFrame(in_card, fg_color="transparent")
        param_f.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(param_f, text="Split every:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        self.seg_entry = ctk.CTkEntry(param_f, width=70, height=28, fg_color=CLR_BG_INPUT, border_color=CLR_BORDER)
        self.seg_entry.pack(side="left", padx=(0, 4))
        self.seg_entry.insert(0, "0")
        self.seg_entry.bind("<KeyRelease>", lambda e: self._update_live_summary())
        ctk.CTkLabel(param_f, text="sec (0 = giữ 1 clip, tối ưu video dài)", font=ctk.CTkFont(size=11), text_color=CLR_TXT_MUTED).pack(side="left", padx=(0, 20))

        ctk.CTkLabel(param_f, text="Workers:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 6))
        self.workers_combo = ctk.CTkComboBox(param_f, values=["1", "2", "4", "8", "16"], width=75, height=28, command=lambda v: self._update_live_summary())
        self.workers_combo.pack(side="left")
        self.workers_combo.set("4")

        # --- Preset Selector Row ---
        preset_card = ctk.CTkFrame(left_col, fg_color=CLR_BG_CARD, corner_radius=10)
        preset_card.pack(fill="x", pady=(0, 10))

        p_row = ctk.CTkFrame(preset_card, fg_color="transparent")
        p_row.pack(fill="x", padx=16, pady=10)

        ctk.CTkLabel(p_row, text="Recipe Preset:", font=ctk.CTkFont(size=13, weight="bold"), text_color=CLR_PRIMARY).pack(side="left", padx=(0, 10))

        self.preset_combo = ctk.CTkComboBox(p_row, values=list(self.presets.keys()), width=240, height=30, command=self._apply_preset_by_name)
        self.preset_combo.pack(side="left", padx=(0, 10))
        self.preset_combo.set(list(self.presets.keys())[0])

        save_p_btn = ctk.CTkButton(p_row, text="Save Preset", width=90, height=30, fg_color="#0284c7", hover_color="#0369a1", command=self._save_current_preset)
        save_p_btn.pack(side="left", padx=(0, 6))

        del_p_btn = ctk.CTkButton(p_row, text="Delete", width=70, height=30, fg_color=CLR_DANGER, hover_color="#b91c1c", command=self._delete_current_preset)
        del_p_btn.pack(side="left")

        # --- Card 2: CAPCUT RECIPE (Accordion) ---
        recipe_card = ctk.CTkFrame(left_col, fg_color=CLR_BG_CARD, corner_radius=10)
        recipe_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(recipe_card, text="CAPCUT RECIPE", font=ctk.CTkFont(size=14, weight="bold"), text_color=CLR_PRIMARY).pack(anchor="w", padx=16, pady=(12, 8))

        # 6.1 Section: Video
        self.f_video_content = self._create_accordion_section(recipe_card, "Video Settings", default_open=True)
        self.vspeed_slider = self._add_slider_ctrl(self.f_video_content, "Speed", 0.1, 10.0, 1.1, "x")
        self.scale_slider = self._add_slider_ctrl(self.f_video_content, "Scale", 50.0, 500.0, 110.0, "%")

        # 6.2 Section: Effect
        self.f_effect_content = self._create_accordion_section(recipe_card, "CapCut Effect", default_open=True)
        eff_p = ctk.CTkFrame(self.f_effect_content, fg_color="transparent")
        eff_p.pack(fill="x", pady=4)

        ctk.CTkLabel(eff_p, text="Effect:", width=120, anchor="w").pack(side="left")
        effect_names = ["Không có"] + [e["name"] for e in self.effects_catalog.list_all()]
        self.effect_combo = ctk.CTkComboBox(eff_p, values=effect_names, width=240, height=28, command=lambda v: self._update_live_summary())
        self.effect_combo.pack(side="left", padx=(0, 10))
        self.effect_combo.set("Ngọn lửa" if len(effect_names) > 1 else "Không có")

        lib_btn = ctk.CTkButton(eff_p, text="Browse Library", width=110, height=28, fg_color="#334155", hover_color="#475569", command=lambda: self._switch_nav("effects"))
        lib_btn.pack(side="left")

        self.eff_speed_slider = self._add_slider_ctrl(self.f_effect_content, "Effect Speed", 0, 100, 13)
        self.eff_air_slider = self._add_slider_ctrl(self.f_effect_content, "Air / Animation", 0, 100, 35)

        # 6.3 Section: Audio
        self.f_audio_content = self._create_accordion_section(recipe_card, "Audio & Voice", default_open=False)
        self.vol_slider = self._add_slider_ctrl(self.f_audio_content, "Original Volume", -60.0, 20.0, 20.0, "dB")

        chk_a_f = ctk.CTkFrame(self.f_audio_content, fg_color="transparent")
        chk_a_f.pack(fill="x", pady=4)
        self.chk_voice_sharpen = ctk.CTkCheckBox(chk_a_f, text="Voice Sharpen (Giọng nói sắc nét)", command=self._update_live_summary)
        self.chk_voice_sharpen.pack(side="left", padx=(0, 15))
        self.chk_vocal_sep = ctk.CTkCheckBox(chk_a_f, text="Vocal Separation (Tách giọng giữ lời)", command=self._update_live_summary)
        self.chk_vocal_sep.pack(side="left")

        bgm_f = ctk.CTkFrame(self.f_audio_content, fg_color="transparent")
        bgm_f.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(bgm_f, text="Background Music:", width=120, anchor="w").pack(side="left")
        self.bgm_entry = ctk.CTkEntry(bgm_f, placeholder_text="File nhạc nền...", height=28, fg_color=CLR_BG_INPUT, border_color=CLR_BORDER)
        self.bgm_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(bgm_f, text="Browse", width=60, height=28, command=self._browse_bgm).pack(side="left", padx=(0, 4))
        ctk.CTkButton(bgm_f, text="×", width=30, height=28, fg_color=CLR_DANGER, hover_color="#b91c1c", command=lambda: [self.bgm_entry.delete(0, "end"), self._update_live_summary()]).pack(side="left")

        self.bgm_vol_slider = self._add_slider_ctrl(self.f_audio_content, "BGM Volume", -60.0, 20.0, 0.0, "dB")

        # 6.4 Section: Overlay
        self.f_overlay_content = self._create_accordion_section(recipe_card, "Overlay & Green Screen", default_open=False)
        ov_f = ctk.CTkFrame(self.f_overlay_content, fg_color="transparent")
        ov_f.pack(fill="x", pady=4)
        ctk.CTkLabel(ov_f, text="Overlay Video:", width=120, anchor="w").pack(side="left")
        self.ov_entry = ctk.CTkEntry(ov_f, placeholder_text="File overlay (green screen / effect)...", height=28, fg_color=CLR_BG_INPUT, border_color=CLR_BORDER)
        self.ov_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(ov_f, text="Browse", width=60, height=28, command=self._browse_overlay_video).pack(side="left", padx=(0, 4))
        ctk.CTkButton(ov_f, text="×", width=30, height=28, fg_color=CLR_DANGER, hover_color="#b91c1c", command=lambda: [self.ov_entry.delete(0, "end"), self._update_live_summary()]).pack(side="left")

        ov_sub_f = ctk.CTkFrame(self.f_overlay_content, fg_color="transparent")
        ov_sub_f.pack(fill="x", pady=4)
        self.chk_chroma = ctk.CTkCheckBox(ov_sub_f, text="Remove Green Screen (Chroma Key)", command=self._toggle_chroma)
        self.chk_chroma.pack(side="left")
        self.chk_chroma.select()

        self.chroma_slider = self._add_slider_ctrl(self.f_overlay_content, "Chroma Intensity", 0, 100, 70)

        # 6.5 Section: Color
        self.f_color_content = self._create_accordion_section(recipe_card, "Color Grading", default_open=False)
        self.color_temp_slider = self._add_slider_ctrl(self.f_color_content, "Temperature", -50, 50, 0)
        self.color_tone_slider = self._add_slider_ctrl(self.f_color_content, "Tone / Tint", -50, 50, 0)
        self.color_sat_slider = self._add_slider_ctrl(self.f_color_content, "Saturation", -50, 50, 0)
        self.color_contrast_slider = self._add_slider_ctrl(self.f_color_content, "Contrast", -50, 50, 0)
        self.color_shadow_slider = self._add_slider_ctrl(self.f_color_content, "Shadow", -50, 50, 0)

        reset_c_btn = ctk.CTkButton(self.f_color_content, text="Reset Color to Default", width=150, height=28, fg_color="#334155", hover_color="#475569", command=self._reset_color)
        reset_c_btn.pack(anchor="w", padx=120, pady=(4, 8))

        # ======================================================================
        # RIGHT ~35%: Live Job Summary, Output Mode, Action Button
        # ======================================================================
        right_col = ctk.CTkFrame(top_area, width=370, fg_color=CLR_BG_CARD, corner_radius=10)
        right_col.pack(side="right", fill="both")
        right_col.pack_propagate(False)

        ctk.CTkLabel(right_col, text="JOB SUMMARY", font=ctk.CTkFont(size=14, weight="bold"), text_color=CLR_PRIMARY).pack(anchor="w", padx=16, pady=(14, 8))

        # Live Summary Card Display
        self.summary_box = ctk.CTkTextbox(right_col, height=270, font=ctk.CTkFont(family="Consolas", size=12), text_color=CLR_TXT_MAIN, fg_color=CLR_BG_PANEL, corner_radius=8)
        self.summary_box.pack(fill="x", padx=16, pady=(0, 10))

        # Output Mode Card
        ctk.CTkLabel(right_col, text="OUTPUT DESTINATION", font=ctk.CTkFont(size=13, weight="bold"), text_color=CLR_PRIMARY).pack(anchor="w", padx=16, pady=(6, 4))

        self.export_mode = ctk.StringVar(value="cloud")
        r_cloud = ctk.CTkRadioButton(
            right_col,
            text="Create Draft + Cloud Render",
            variable=self.export_mode,
            value="cloud",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=CLR_SUCCESS,
            command=self._on_output_mode_changed,
        )
        r_cloud.pack(anchor="w", padx=20, pady=3)

        r_local = ctk.CTkRadioButton(
            right_col,
            text="Create CapCut Draft Only (PC)",
            variable=self.export_mode,
            value="local",
            font=ctk.CTkFont(size=12),
            command=self._on_output_mode_changed,
        )
        r_local.pack(anchor="w", padx=20, pady=3)

        # Resolution & FPS
        self.f_cloud_opts = ctk.CTkFrame(right_col, fg_color="transparent")
        self.f_cloud_opts.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(self.f_cloud_opts, text="Res:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self.res_combo = ctk.CTkComboBox(self.f_cloud_opts, values=["1080p", "2k", "4k"], width=80, height=26, command=lambda v: self._update_live_summary())
        self.res_combo.pack(side="left", padx=(0, 10))
        self.res_combo.set("1080p")

        ctk.CTkLabel(self.f_cloud_opts, text="FPS:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self.fps_combo = ctk.CTkComboBox(self.f_cloud_opts, values=["30", "60"], width=65, height=26, command=lambda v: self._update_live_summary())
        self.fps_combo.pack(side="left")
        self.fps_combo.set("30")

        self.auto_chunk_var = ctk.BooleanVar(value=True)
        self.auto_chunk_chk = ctk.CTkCheckBox(self.f_cloud_opts, text="Auto-chunk (>60s)", variable=self.auto_chunk_var, font=ctk.CTkFont(size=11), command=lambda: self._update_live_summary())
        self.auto_chunk_chk.pack(side="left", padx=(10, 0))

        # PRIMARY ACTION BUTTON
        self.primary_action_btn = ctk.CTkButton(
            right_col,
            text="▶ CREATE & RENDER",
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=46,
            corner_radius=8,
            command=self._start_pipeline_thread,
        )
        self.primary_action_btn.pack(fill="x", padx=16, pady=(12, 10))

        # Bottom Queue / Progress Bar & Collapsible Log
        bottom_box = ctk.CTkFrame(page, fg_color=CLR_BG_CARD, corner_radius=10)
        bottom_box.pack(fill="x", padx=16, pady=(0, 12))

        prog_hdr = ctk.CTkFrame(bottom_box, fg_color="transparent")
        prog_hdr.pack(fill="x", padx=16, pady=(8, 2))

        self.queue_status_lbl = ctk.CTkLabel(prog_hdr, text="● Ready · CapCut account authenticated", font=ctk.CTkFont(size=12, weight="bold"), text_color=CLR_SUCCESS)
        self.queue_status_lbl.pack(side="left")

        self.queue_pct_lbl = ctk.CTkLabel(prog_hdr, text="0%", font=ctk.CTkFont(size=12, weight="bold"), text_color=CLR_TXT_MUTED)
        self.queue_pct_lbl.pack(side="right")

        self.queue_bar = ctk.CTkProgressBar(bottom_box, height=8, corner_radius=4)
        self.queue_bar.pack(fill="x", padx=16, pady=(2, 6))
        self.queue_bar.set(0.0)

        # Collapsible Technical Log Bar
        log_bar = ctk.CTkFrame(bottom_box, fg_color="transparent")
        log_bar.pack(fill="x", padx=16, pady=(0, 6))

        self.toggle_log_btn = ctk.CTkButton(
            log_bar,
            text="▶ Show Technical Log",
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            hover_color=CLR_BG_INPUT,
            text_color=CLR_PRIMARY,
            height=24,
            command=self._toggle_technical_log,
        )
        self.toggle_log_btn.pack(side="left")

        self.f_log_actions = ctk.CTkFrame(log_bar, fg_color="transparent")
        copy_btn = ctk.CTkButton(self.f_log_actions, text="Copy", width=50, height=22, font=ctk.CTkFont(size=11), fg_color="#334155", command=self._copy_log)
        copy_btn.pack(side="left", padx=4)
        clear_btn = ctk.CTkButton(self.f_log_actions, text="Clear", width=50, height=22, font=ctk.CTkFont(size=11), fg_color="#334155", command=self._clear_log)
        clear_btn.pack(side="left")

        self.log_textbox = ctk.CTkTextbox(bottom_box, height=130, font=ctk.CTkFont(family="Consolas", size=11), text_color="#e2e8f0", fg_color="#0a0b0d")
        # Hidden by default

        return page

    # --------------------------------------------------------------------------
    # Accordion Helper
    # --------------------------------------------------------------------------
    def _create_accordion_section(self, parent, title: str, default_open: bool = True) -> ctk.CTkFrame:
        sec_f = ctk.CTkFrame(parent, fg_color="#1a1c22", corner_radius=8)
        sec_f.pack(fill="x", padx=16, pady=4)

        content_f = ctk.CTkFrame(sec_f, fg_color="transparent")

        def toggle():
            if content_f.winfo_ismapped():
                content_f.pack_forget()
                hdr_btn.configure(text=f"▶  {title}")
            else:
                content_f.pack(fill="x", padx=12, pady=(0, 8))
                hdr_btn.configure(text=f"▼  {title}")

        hdr_btn = ctk.CTkButton(
            sec_f,
            text=f"▼  {title}" if default_open else f"▶  {title}",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            fg_color="transparent",
            hover_color="#242830",
            text_color=CLR_TXT_MAIN,
            height=34,
            command=toggle,
        )
        hdr_btn.pack(fill="x", padx=6, pady=2)

        if default_open:
            content_f.pack(fill="x", padx=12, pady=(0, 8))

        return content_f

    def _add_slider_ctrl(self, parent, label: str, from_: float, to: float, default: float, suffix: str = ""):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=2)

        lbl = ctk.CTkLabel(frame, text=label, width=120, anchor="w", font=ctk.CTkFont(size=12))
        lbl.pack(side="left")

        val_lbl = ctk.CTkLabel(frame, text=f"{default:.1f}{suffix}" if isinstance(default, float) else f"{int(default)}{suffix}", width=55, font=ctk.CTkFont(size=12, weight="bold"), text_color=CLR_PRIMARY)
        val_lbl.pack(side="right")

        def on_slide(val):
            if isinstance(default, int) and from_ == int(from_):
                val_lbl.configure(text=f"{int(round(val))}{suffix}")
            else:
                val_lbl.configure(text=f"{val:.1f}{suffix}")
            self._update_live_summary()

        slider = ctk.CTkSlider(frame, from_=from_, to=to, command=on_slide, height=16)
        slider.set(default)
        slider.pack(side="left", fill="x", expand=True, padx=(4, 8))
        return slider

    # --------------------------------------------------------------------------
    # Live Summary Reactive Updater
    # --------------------------------------------------------------------------
    def _update_live_summary(self):
        try:
            in_path = self.input_path_entry.get().strip()
            input_summary = Path(in_path).name if (in_path and os.path.isfile(in_path)) else "None selected"

            seg_val = self.seg_entry.get().strip() or "0"
            seg_txt = f"{seg_val}s" if seg_val != "0" else "Không cắt (1 clip)"
            workers = self.workers_combo.get()

            v_spd = f"{self.vspeed_slider.get():.2f}x"
            scale = f"{int(self.scale_slider.get())}%"

            eff_name = self.effect_combo.get()
            eff_txt = f"{eff_name} (Spd {int(self.eff_speed_slider.get())} · Air {int(self.eff_air_slider.get())})" if eff_name != "Không có" else "None"

            ov_path = self.ov_entry.get().strip()
            if ov_path:
                chroma_on = self.chk_chroma.get()
                ov_txt = f"{Path(ov_path).name} (Chroma: {int(self.chroma_slider.get())}%)" if chroma_on else f"{Path(ov_path).name} (No Chroma)"
            else:
                ov_txt = "None"

            bgm_path = self.bgm_entry.get().strip()
            bgm_txt = f"{Path(bgm_path).name} ({self.bgm_vol_slider.get():.1f} dB)" if bgm_path else "None"

            sharpen = self.chk_voice_sharpen.get()
            vsep = self.chk_vocal_sep.get()
            audio_flags = []
            if sharpen: audio_flags.append("Sharpen")
            if vsep: audio_flags.append("VocalSep")
            flags_txt = f"[{', '.join(audio_flags)}]" if audio_flags else "Standard"

            # Color check
            c_vals = [int(self.color_temp_slider.get()), int(self.color_tone_slider.get()), int(self.color_sat_slider.get()), int(self.color_contrast_slider.get()), int(self.color_shadow_slider.get())]
            color_txt = "Custom" if any(v != 0 for v in c_vals) else "Default"

            out_mode = self.export_mode.get()
            if out_mode == "cloud":
                chunk_str = " · Auto-chunk" if getattr(self, "auto_chunk_var", None) and self.auto_chunk_var.get() else ""
                out_txt = f"Draft + Cloud Render ({self.res_combo.get()} · {self.fps_combo.get()} FPS{chunk_str})"
            else:
                out_txt = "CapCut PC Draft Only"

            summary = (
                f"INPUT\n"
                f"• {input_summary}\n"
                f"• Split: {seg_txt} · Workers: {workers}\n\n"
                f"RECIPE\n"
                f"• Video:   {v_spd} · Scale: {scale}\n"
                f"• Effect:  {eff_txt}\n"
                f"• Overlay: {ov_txt}\n"
                f"• Audio:   {flags_txt} · BGM: {bgm_txt}\n"
                f"• Color:   {color_txt}\n\n"
                f"OUTPUT\n"
                f"• {out_txt}"
            )
            self.summary_box.delete("1.0", "end")
            self.summary_box.insert("1.0", summary)

        except Exception:
            pass

    # --------------------------------------------------------------------------
    # Preset Operations
    # --------------------------------------------------------------------------
    def _load_presets(self):
        if PRESETS_FILE.exists():
            try:
                with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                    self.presets = json.load(f)
            except Exception:
                self.presets = dict(DEFAULT_PRESETS)

    def _save_presets_to_file(self):
        with open(PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.presets, f, indent=2, ensure_ascii=False)

    def _apply_preset_by_name(self, name: str):
        p = self.presets.get(name)
        if not p:
            return

        try:
            self.vspeed_slider.set(p.get("video", {}).get("speed", 1.1))
            self.scale_slider.set(p.get("video", {}).get("scale", 110))
            self.vol_slider.set(p.get("video", {}).get("volume_db", 20.0))

            eff = p.get("effect", {})
            if eff.get("name") in self.effect_combo.cget("values"):
                self.effect_combo.set(eff.get("name"))
            self.eff_speed_slider.set(eff.get("speed", 13))
            self.eff_air_slider.set(eff.get("air", 35))

            aud = p.get("audio", {})
            if aud.get("voice_sharpen"): self.chk_voice_sharpen.select()
            else: self.chk_voice_sharpen.deselect()

            if aud.get("vocal_sep"): self.chk_vocal_sep.select()
            else: self.chk_vocal_sep.deselect()

            if aud.get("bgm_path"):
                self.bgm_entry.delete(0, "end")
                self.bgm_entry.insert(0, aud.get("bgm_path"))
            self.bgm_vol_slider.set(aud.get("bgm_db", 0.0))

            ov = p.get("overlay", {})
            if ov.get("path"):
                self.ov_entry.delete(0, "end")
                self.ov_entry.insert(0, ov.get("path"))
            if ov.get("chroma_enabled"): self.chk_chroma.select()
            else: self.chk_chroma.deselect()
            self.chroma_slider.set(ov.get("chroma_intensity", 70))

            col = p.get("color", {})
            self.color_temp_slider.set(col.get("temperature", 0))
            self.color_tone_slider.set(col.get("tone", 0))
            self.color_sat_slider.set(col.get("saturation", 0))
            self.color_contrast_slider.set(col.get("contrast", 0))
            self.color_shadow_slider.set(col.get("shadow", 0))

            out = p.get("output", {})
            self.export_mode.set(out.get("mode", "cloud"))
            if out.get("resolution"): self.res_combo.set(out.get("resolution"))
            if out.get("fps"): self.fps_combo.set(str(out.get("fps")))

            self._on_output_mode_changed()
            self._update_live_summary()
            self._log(f"[Preset] Đã nạp thành công preset: {name}")

        except Exception as exc:
            self._log(f"[Preset] Lỗi áp dụng preset: {exc}")

    def _save_current_preset(self):
        dialog = ctk.CTkInputDialog(text="Nhập tên Preset mới:", title="Save Recipe Preset")
        name = dialog.get_input()
        if not name or not name.strip():
            return
        name = name.strip()

        preset_data = {
            "name": name,
            "video": {
                "speed": float(self.vspeed_slider.get()),
                "scale": float(self.scale_slider.get()),
                "volume_db": float(self.vol_slider.get()),
            },
            "effect": {
                "name": self.effect_combo.get(),
                "speed": int(self.eff_speed_slider.get()),
                "air": int(self.eff_air_slider.get()),
            },
            "audio": {
                "voice_sharpen": bool(self.chk_voice_sharpen.get()),
                "vocal_sep": bool(self.chk_vocal_sep.get()),
                "bgm_path": self.bgm_entry.get().strip(),
                "bgm_db": float(self.bgm_vol_slider.get()),
            },
            "overlay": {
                "path": self.ov_entry.get().strip(),
                "chroma_enabled": bool(self.chk_chroma.get()),
                "chroma_intensity": int(self.chroma_slider.get()),
            },
            "color": {
                "temperature": int(self.color_temp_slider.get()),
                "tone": int(self.color_tone_slider.get()),
                "saturation": int(self.color_sat_slider.get()),
                "contrast": int(self.color_contrast_slider.get()),
                "shadow": int(self.color_shadow_slider.get()),
            },
            "output": {
                "mode": self.export_mode.get(),
                "resolution": self.res_combo.get(),
                "fps": int(self.fps_combo.get()),
            },
        }

        self.presets[name] = preset_data
        self._save_presets_to_file()
        self.preset_combo.configure(values=list(self.presets.keys()))
        self.preset_combo.set(name)
        messagebox.showinfo("Preset Saved", f"Đã lưu preset '{name}' thành công!")

    def _delete_current_preset(self):
        cur = self.preset_combo.get()
        if cur in self.presets:
            if messagebox.askyesno("Delete Preset", f"Bạn có chắc muốn xóa preset '{cur}'?"):
                del self.presets[cur]
                self._save_presets_to_file()
                keys = list(self.presets.keys()) or ["Default"]
                self.preset_combo.configure(values=keys)
                self.preset_combo.set(keys[0])

    # --------------------------------------------------------------------------
    # Control Callbacks & Toggles
    # --------------------------------------------------------------------------
    def _browse_input_source(self):
        p = filedialog.askopenfilename(
            title="Chọn File Video Nguồn",
            filetypes=[("Video Files", "*.mp4 *.mov *.mkv *.avi *.flv")],
        )
        if p:
            self.input_path_entry.delete(0, "end")
            self.input_path_entry.insert(0, p)
            self.input_detected_lbl.configure(text=f"Video nguồn: {Path(p).name}", text_color=CLR_PRIMARY)
            if not self.is_processing:
                self.primary_action_btn.configure(state="normal")
        self._update_live_summary()

    def _browse_overlay_video(self):
        p = filedialog.askopenfilename(title="Chọn Overlay Video", filetypes=[("Video Files", "*.mp4 *.mov *.mkv *.avi")])
        if p:
            self.ov_entry.delete(0, "end")
            self.ov_entry.insert(0, p)
            self._update_live_summary()

    def _browse_bgm(self):
        p = filedialog.askopenfilename(title="Chọn Nhạc Nền", filetypes=[("Audio Files", "*.mp3 *.wav *.m4a *.aac *.mp4")])
        if p:
            self.bgm_entry.delete(0, "end")
            self.bgm_entry.insert(0, p)
            self._update_live_summary()

    def _toggle_chroma(self):
        on = self.chk_chroma.get()
        if on:
            self.chroma_slider.configure(state="normal")
        else:
            self.chroma_slider.configure(state="disabled")
        self._update_live_summary()

    def _reset_color(self):
        self.color_temp_slider.set(0)
        self.color_tone_slider.set(0)
        self.color_sat_slider.set(0)
        self.color_contrast_slider.set(0)
        self.color_shadow_slider.set(0)
        self._update_live_summary()

    def _on_output_mode_changed(self):
        mode = self.export_mode.get()
        btn_state = "disabled" if self.is_processing else "normal"
        if mode == "cloud":
            self.f_cloud_opts.pack(fill="x", padx=20, pady=6)
            self.primary_action_btn.configure(
                text="▶ CREATE & RENDER",
                state=btn_state,
                fg_color="#059669",
                hover_color="#047857",
            )
        else:
            self.f_cloud_opts.pack_forget()
            self.primary_action_btn.configure(
                text="▶ CREATE DRAFTS",
                state=btn_state,
                fg_color="#0284c7",
                hover_color="#0369a1",
            )
        self._update_live_summary()

    def _toggle_technical_log(self):
        if self.log_visible:
            self.log_textbox.pack_forget()
            self.f_log_actions.pack_forget()
            self.toggle_log_btn.configure(text="▶ Show Technical Log")
            self.log_visible = False
        else:
            self.f_log_actions.pack(side="right")
            self.log_textbox.pack(fill="both", expand=True, padx=16, pady=(4, 10))
            self.toggle_log_btn.configure(text="▼ Hide Technical Log")
            self.log_visible = True

    def _copy_log(self):
        txt = self.log_textbox.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(txt)
        messagebox.showinfo("Copied", "Technical log đã được sao chép.")

    def _clear_log(self):
        self.log_textbox.delete("1.0", "end")

    # --------------------------------------------------------------------------
    # PAGE: BATCH AUTOMATION WORKBENCH (100–200 Videos/Day)
    # --------------------------------------------------------------------------
    def _build_page_batch(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.content_container, fg_color="transparent")

        # Top Bar: Title & Live Stat Badges
        top_bar = ctk.CTkFrame(page, fg_color=CLR_BG_CARD, corner_radius=10)
        top_bar.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(
            top_bar,
            text="⚡ BATCH AUTOMATION (100–200 VIDEO/NGÀY)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=CLR_PRIMARY,
        ).pack(side="left", padx=16, pady=12)

        self.batch_stat_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
        self.batch_stat_frame.pack(side="right", padx=16, pady=8)

        self.lbl_stat_total = ctk.CTkLabel(self.batch_stat_frame, text="Tổng: 0", font=ctk.CTkFont(size=12, weight="bold"), fg_color="#1e293b", corner_radius=6, padx=8, pady=3)
        self.lbl_stat_total.pack(side="left", padx=3)

        self.lbl_stat_running = ctk.CTkLabel(self.batch_stat_frame, text="Đang chạy: 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#38bdf8", fg_color="#0c4a6e", corner_radius=6, padx=8, pady=3)
        self.lbl_stat_running.pack(side="left", padx=3)

        self.lbl_stat_done = ctk.CTkLabel(self.batch_stat_frame, text="Hoàn tất: 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#22c55e", fg_color="#14532d", corner_radius=6, padx=8, pady=3)
        self.lbl_stat_done.pack(side="left", padx=3)

        self.lbl_stat_failed = ctk.CTkLabel(self.batch_stat_frame, text="Lỗi: 0", font=ctk.CTkFont(size=12, weight="bold"), text_color="#ef4444", fg_color="#450a0a", corner_radius=6, padx=8, pady=3)
        self.lbl_stat_failed.pack(side="left", padx=3)

        # Configuration Panel
        cfg_panel = ctk.CTkFrame(page, fg_color=CLR_BG_CARD, corner_radius=10)
        cfg_panel.pack(fill="x", padx=16, pady=(0, 8))

        # Row 1: Source Files / Folder
        r1 = ctk.CTkFrame(cfg_panel, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(10, 4))

        ctk.CTkLabel(r1, text="Thư mục nguồn:", width=125, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.batch_input_entry = ctk.CTkEntry(r1, placeholder_text="Chọn Folder chứa hàng loạt video...", height=30, fg_color=CLR_BG_INPUT, border_color=CLR_BORDER)
        self.batch_input_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))

        ctk.CTkButton(r1, text="📁 Chọn Folder", width=105, height=30, command=self._browse_batch_input_folder).pack(side="left", padx=3)
        ctk.CTkButton(r1, text="➕ Thêm Files", width=95, height=30, fg_color="#334155", command=self._add_batch_files).pack(side="left", padx=3)
        ctk.CTkButton(r1, text="🗑 Xóa hết", width=75, height=30, fg_color="#450a0a", hover_color="#7f1d1d", command=self._clear_batch_queue).pack(side="left", padx=3)

        # Row 2: Destination Output Directory
        r2 = ctk.CTkFrame(cfg_panel, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=(4, 6))

        ctk.CTkLabel(r2, text="Thư mục xuất file:", width=125, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.batch_output_entry = ctk.CTkEntry(r2, height=30, fg_color=CLR_BG_INPUT, border_color=CLR_BORDER)
        self.batch_output_entry.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self.batch_output_entry.insert(0, str(DEFAULT_OUTPUT_DIR))

        ctk.CTkButton(r2, text="📂 Chọn Thư Mục", width=115, height=30, command=self._browse_batch_output_folder).pack(side="left", padx=3)
        ctk.CTkButton(r2, text="↗ Mở Thư Mục", width=105, height=30, fg_color="#334155", command=self._open_batch_output_folder).pack(side="left", padx=3)

        # Row 3: Preset, Resolution, FPS, Workers & Rotation
        r3 = ctk.CTkFrame(cfg_panel, fg_color="transparent")
        r3.pack(fill="x", padx=16, pady=(4, 12))

        ctk.CTkLabel(r3, text="Preset:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        p_keys = list(self.presets.keys()) if self.presets else ["Default"]
        self.batch_preset_combo = ctk.CTkComboBox(r3, values=p_keys, width=150, height=28)
        self.batch_preset_combo.pack(side="left", padx=(0, 10))
        if p_keys:
            self.batch_preset_combo.set(p_keys[0])

        ctk.CTkLabel(r3, text="Res:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self.batch_res_combo = ctk.CTkComboBox(r3, values=["720p", "1080p", "2k", "4k"], width=80, height=28)
        self.batch_res_combo.pack(side="left", padx=(0, 10))
        self.batch_res_combo.set("1080p")

        ctk.CTkLabel(r3, text="FPS:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self.batch_fps_combo = ctk.CTkComboBox(r3, values=["24", "25", "30", "50", "60"], width=65, height=28)
        self.batch_fps_combo.pack(side="left", padx=(0, 10))
        self.batch_fps_combo.set("30")

        ctk.CTkLabel(r3, text="Workers:", font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 4))
        self.batch_workers_combo = ctk.CTkComboBox(r3, values=["1", "2", "3", "4", "5", "8"], width=65, height=28)
        self.batch_workers_combo.pack(side="left", padx=(0, 14))
        self.batch_workers_combo.set("3")

        self.batch_rotate_var = ctk.BooleanVar(value=True)
        self.batch_rotate_chk = ctk.CTkCheckBox(
            r3,
            text="Xoay vòng Account Pro",
            variable=self.batch_rotate_var,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24",
        )
        self.batch_rotate_chk.pack(side="left", padx=(0, 14))

        # Main Action Buttons
        self.btn_batch_start = ctk.CTkButton(
            r3,
            text="▶ BẮT ĐẦU CHẠY HÀNG LOẠT",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=32,
            width=210,
            command=self._start_batch_thread,
        )
        self.btn_batch_start.pack(side="right", padx=(4, 0))

        self.btn_batch_stop = ctk.CTkButton(
            r3,
            text="⏹ DỪNG LẠI",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#ef4444",
            hover_color="#dc2626",
            height=32,
            width=95,
            state="disabled",
            command=self._stop_batch_thread,
        )
        self.btn_batch_stop.pack(side="right", padx=(0, 4))

        # Overall Progress Bar Card
        prog_f = ctk.CTkFrame(page, fg_color=CLR_BG_CARD, corner_radius=10)
        prog_f.pack(fill="x", padx=16, pady=(0, 8))

        p_hdr = ctk.CTkFrame(prog_f, fg_color="transparent")
        p_hdr.pack(fill="x", padx=16, pady=(8, 2))

        self.batch_prog_lbl = ctk.CTkLabel(p_hdr, text="● Sẵn sàng nạp hàng loạt video", font=ctk.CTkFont(size=12, weight="bold"), text_color=CLR_TXT_MUTED)
        self.batch_prog_lbl.pack(side="left")

        self.batch_pct_lbl = ctk.CTkLabel(p_hdr, text="0%", font=ctk.CTkFont(size=12, weight="bold"), text_color=CLR_TXT_MUTED)
        self.batch_pct_lbl.pack(side="right")

        self.batch_prog_bar = ctk.CTkProgressBar(prog_f, height=8, corner_radius=4)
        self.batch_prog_bar.pack(fill="x", padx=16, pady=(2, 10))
        self.batch_prog_bar.set(0.0)

        # Video Queue Table Card
        self.batch_table_card = ctk.CTkFrame(page, fg_color=CLR_BG_CARD, corner_radius=10)
        self.batch_table_card.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # Table Header
        th = ctk.CTkFrame(self.batch_table_card, height=32, fg_color="#181a20", corner_radius=6)
        th.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(th, text="#", width=35, font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
        ctk.CTkLabel(th, text="Tên File Video", width=340, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=8)
        ctk.CTkLabel(th, text="Dung lượng", width=95, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=4)
        ctk.CTkLabel(th, text="Trạng thái", width=160, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=8)
        ctk.CTkLabel(th, text="Tiến độ chi tiết", anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", fill="x", expand=True, padx=8)

        self.batch_queue_scroll = ctk.CTkScrollableFrame(self.batch_table_card, fg_color="transparent")
        self.batch_queue_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        return page

    def _browse_batch_input_folder(self):
        folder = filedialog.askdirectory(title="Chọn Folder chứa video hàng loạt")
        if folder:
            self.batch_input_entry.delete(0, "end")
            self.batch_input_entry.insert(0, folder)
            exts = (".mp4", ".mov", ".avi", ".mkv", ".flv")
            found = [Path(folder) / f for f in sorted(os.listdir(folder)) if (Path(folder) / f).is_file() and f.lower().endswith(exts)]
            self.batch_videos = found
            self._render_batch_queue_table()
            self._update_batch_stat_cards()

    def _add_batch_files(self):
        files = filedialog.askopenfilenames(
            title="Chọn các file video",
            filetypes=[("Video Files", "*.mp4 *.mov *.mkv *.avi *.flv")],
        )
        if files:
            existing = {str(p.resolve()) for p in self.batch_videos}
            for f in files:
                pf = Path(f).resolve()
                if str(pf) not in existing:
                    self.batch_videos.append(pf)
                    existing.add(str(pf))
            self._render_batch_queue_table()
            self._update_batch_stat_cards()

    def _clear_batch_queue(self):
        if self.batch_running:
            messagebox.showwarning("Đang chạy", "Tác vụ hàng loạt đang chạy, không thể xóa.")
            return
        self.batch_videos.clear()
        self.batch_items_ui.clear()
        self.batch_stats = {"total": 0, "running": 0, "done": 0, "failed": 0}
        self._render_batch_queue_table()
        self._update_batch_stat_cards()

    def _browse_batch_output_folder(self):
        folder = filedialog.askdirectory(title="Chọn Thư Mục Xuất Thành Phẩm")
        if folder:
            self.batch_output_entry.delete(0, "end")
            self.batch_output_entry.insert(0, folder)

    def _open_batch_output_folder(self):
        out_p = self.batch_output_entry.get().strip() or str(DEFAULT_OUTPUT_DIR)
        os.makedirs(out_p, exist_ok=True)
        subprocess.run(["explorer", str(Path(out_p).resolve())])

    def _update_batch_stat_cards(self):
        self.lbl_stat_total.configure(text=f"Tổng: {len(self.batch_videos)}")
        self.lbl_stat_running.configure(text=f"Đang chạy: {self.batch_stats['running']}")
        self.lbl_stat_done.configure(text=f"Hoàn tất: {self.batch_stats['done']}")
        self.lbl_stat_failed.configure(text=f"Lỗi: {self.batch_stats['failed']}")

    def _render_batch_queue_table(self):
        for w in self.batch_queue_scroll.winfo_children():
            w.destroy()
        self.batch_items_ui.clear()

        for idx, vp in enumerate(self.batch_videos, 1):
            row = ctk.CTkFrame(self.batch_queue_scroll, height=38, fg_color="#202329", corner_radius=6)
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text=str(idx), width=35, font=ctk.CTkFont(size=11), text_color=CLR_TXT_MUTED).pack(side="left", padx=4)
            ctk.CTkLabel(row, text=vp.name, width=340, anchor="w", font=ctk.CTkFont(size=12, weight="bold"), text_color=CLR_TXT_MAIN).pack(side="left", padx=8)

            try:
                sz_mb = vp.stat().st_size / (1024 * 1024)
                sz_str = f"{sz_mb:.1f} MB" if sz_mb < 1024 else f"{sz_mb/1024:.2f} GB"
            except Exception:
                sz_str = "N/A"
            ctk.CTkLabel(row, text=sz_str, width=95, anchor="w", font=ctk.CTkFont(size=11), text_color=CLR_TXT_MUTED).pack(side="left", padx=4)

            badge = ctk.CTkLabel(row, text="Chờ xử lý", width=140, font=ctk.CTkFont(size=11, weight="bold"), fg_color="#334155", corner_radius=6, padx=6, pady=2)
            badge.pack(side="left", padx=8)

            detail_lbl = ctk.CTkLabel(row, text="Trong hàng đợi", anchor="w", font=ctk.CTkFont(size=11), text_color=CLR_TXT_MUTED)
            detail_lbl.pack(side="left", fill="x", expand=True, padx=8)

            self.batch_items_ui[str(vp.resolve())] = {
                "row": row,
                "badge": badge,
                "detail": detail_lbl,
            }

    def _start_batch_thread(self):
        if self.batch_running:
            return
        if not self.batch_videos:
            messagebox.showwarning("Trống", "Vui lòng chọn ít nhất 1 video hoặc thư mục chứa video.")
            return

        out_dir = Path(self.batch_output_entry.get().strip() or str(DEFAULT_OUTPUT_DIR)).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        self.batch_running = True
        self.batch_stop_requested = False
        self.btn_batch_start.configure(state="disabled", text="⏳ ĐANG XỬ LÝ...")
        self.btn_batch_stop.configure(state="normal")
        self.batch_stats = {"total": len(self.batch_videos), "running": 0, "done": 0, "failed": 0}
        self._update_batch_stat_cards()

        threading.Thread(target=self._run_batch_worker, args=(out_dir,), daemon=True).start()

    def _stop_batch_thread(self):
        if not self.batch_running:
            return
        self.batch_stop_requested = True
        self._log("[!] Người dùng yêu cầu dừng tác vụ hàng loạt. Đang chờ các worker hiện tại hoàn tất...")
        self.btn_batch_stop.configure(state="disabled", text="⏳ Đang dừng...")

    def _run_batch_worker(self, out_dir: Path):
        try:
            workers_count = int(self.batch_workers_combo.get().strip() or "3")
        except Exception:
            workers_count = 3

        workers_count = max(1, min(workers_count, 8))
        preset_name = self.batch_preset_combo.get()
        selected_preset = self.presets.get(preset_name, {})
        definition = self.batch_res_combo.get()
        try:
            fps = int(self.batch_fps_combo.get())
        except Exception:
            fps = 30

        rotate_acc = self.batch_rotate_var.get()
        accounts = self.acc_mgr.list_accounts() if rotate_acc else []
        acc_index = 0
        acc_lock = threading.Lock()

        total = len(self.batch_videos)
        completed_count = 0
        comp_lock = threading.Lock()

        self._log(f"\n{'='*65}\n[*] BẮT ĐẦU CHẠY HÀNG LOẠT {total} VIDEO | WORKERS: {workers_count} | ROTATE ACCOUNTS: {rotate_acc}\n{'='*65}")

        def get_auth_for_job() -> CapCutAuth:
            nonlocal acc_index
            if rotate_acc and accounts:
                with acc_lock:
                    acc_info = accounts[acc_index % len(accounts)]
                    acc_index += 1
                auth = CapCutAuth()
                auth.load_cookies_from_string(acc_info.get("cookies", ""))
                return auth
            else:
                auth = CapCutAuth()
                auth.sync_all()
                return auth

        def update_item_ui(v_key: str, status_text: str, badge_color: str, detail: str):
            def _fn():
                ui = self.batch_items_ui.get(v_key)
                if ui:
                    ui["badge"].configure(text=status_text, fg_color=badge_color)
                    ui["detail"].configure(text=detail)
            self.after(0, _fn)

        def process_one(vp: Path, idx: int) -> bool:
            nonlocal completed_count
            v_key = str(vp.resolve())
            v_name = vp.name
            out_file = out_dir / f"rendered_{vp.stem}.mp4"

            if self.batch_stop_requested:
                update_item_ui(v_key, "Đã hủy", "#450a0a", "Dừng bởi người dùng")
                return False

            if out_file.exists():
                update_item_ui(v_key, "Đã có sẵn", "#1e293b", f"File đã tồn tại: {out_file.name}")
                with comp_lock:
                    completed_count += 1
                    self.batch_stats["done"] += 1
                    pct = int(completed_count / total * 100)
                    self.after(0, lambda: self.batch_prog_bar.set(pct / 100.0))
                    self.after(0, lambda: self.batch_pct_lbl.configure(text=f"{pct}%"))
                    self.after(0, self._update_batch_stat_cards)
                return True

            with comp_lock:
                self.batch_stats["running"] += 1
                self.after(0, self._update_batch_stat_cards)

            update_item_ui(v_key, "Khởi tạo", "#0c4a6e", "Đang nạp cấu hình và session...")
            t0 = time.time()

            try:
                # 1. Build draft params
                draft_params = {}
                if selected_preset:
                    v_cfg = selected_preset.get("video", {})
                    e_cfg = selected_preset.get("effect", {})
                    a_cfg = selected_preset.get("audio", {})
                    c_cfg = selected_preset.get("color", {})

                    draft_params["video_speed"] = v_cfg.get("speed", 1.0)
                    draft_params["scale_pct"] = v_cfg.get("scale", 100)
                    draft_params["volume_db"] = v_cfg.get("volume_db", 0.0)

                    if e_cfg.get("name") and e_cfg.get("name") != "Không có":
                        draft_params["effect_name"] = e_cfg["name"]
                        draft_params["effect_speed"] = float(e_cfg.get("speed", 13)) / 100.0
                        draft_params["effect_air"] = float(e_cfg.get("air", 35)) / 100.0

                    draft_params["voice_sharpen"] = a_cfg.get("voice_sharpen", False)
                    draft_params["vocal_sep"] = a_cfg.get("vocal_sep", False)
                    draft_params["color_temperature"] = c_cfg.get("temperature", 0)
                    draft_params["color_tone"] = c_cfg.get("tone", 0)
                    draft_params["color_saturation"] = c_cfg.get("saturation", 0)
                    draft_params["color_contrast"] = c_cfg.get("contrast", 0)
                    draft_params["color_shadow"] = c_cfg.get("shadow", 0)

                # 2. Make draft
                update_item_ui(v_key, "Tạo Draft", "#0284c7", "Đang dựng cấu trúc timeline...")
                draft_content, _, err = make_draft(vp=str(vp), **draft_params)
                if err:
                    raise RuntimeError(f"Tạo draft thất bại: {err}")

                # 3. Cloud Render with progress callbacks
                def sub_prog_cb(sub_pct: int, sub_msg: str):
                    if "Upload" in sub_msg or "Tải lên" in sub_msg:
                        update_item_ui(v_key, f"Upload {sub_pct}%", "#7c3aed", sub_msg)
                    elif "Render" in sub_msg:
                        update_item_ui(v_key, f"Render {sub_pct}%", "#d97706", sub_msg)
                    elif "Download" in sub_msg or "Tải về" in sub_msg:
                        update_item_ui(v_key, "Tải về", "#0284c7", sub_msg)

                auth_job = get_auth_for_job()
                downloaded = render_draft_cloud(
                    vp=str(vp),
                    draft_content=draft_content,
                    output_mp4=str(out_file),
                    definition=definition,
                    fps=fps,
                    log_cb=self._log,
                    progress_cb=sub_prog_cb,
                )

                elapsed = time.time() - t0
                update_item_ui(v_key, "Hoàn tất", "#16a34a", f"Thành công trong {elapsed:.1f}s -> {Path(downloaded).name}")
                with comp_lock:
                    completed_count += 1
                    self.batch_stats["running"] -= 1
                    self.batch_stats["done"] += 1
                    pct = int(completed_count / total * 100)
                    self.after(0, lambda: self.batch_prog_bar.set(pct / 100.0))
                    self.after(0, lambda: self.batch_pct_lbl.configure(text=f"{pct}%"))
                    self.after(0, lambda: self.batch_prog_lbl.configure(text=f"● Tiến độ: {completed_count}/{total} video"))
                    self.after(0, self._update_batch_stat_cards)
                return True

            except Exception as exc:
                elapsed = time.time() - t0
                err_msg = str(exc)
                self._log(f"[-] [Lỗi #{idx}] {v_name}: {err_msg}")
                update_item_ui(v_key, "Lỗi", "#dc2626", f"Lỗi ({elapsed:.1f}s): {err_msg[:60]}")
                with comp_lock:
                    completed_count += 1
                    self.batch_stats["running"] -= 1
                    self.batch_stats["failed"] += 1
                    pct = int(completed_count / total * 100)
                    self.after(0, lambda: self.batch_prog_bar.set(pct / 100.0))
                    self.after(0, lambda: self.batch_pct_lbl.configure(text=f"{pct}%"))
                    self.after(0, self._update_batch_stat_cards)
                return False

        with ThreadPoolExecutor(max_workers=workers_count) as executor:
            futures = [executor.submit(process_one, vp, i) for i, vp in enumerate(self.batch_videos, 1)]
            for _ in as_completed(futures):
                if self.batch_stop_requested:
                    break

        self.batch_running = False
        def finish_ui():
            self.btn_batch_start.configure(state="normal", text="▶ BẮT ĐẦU CHẠY HÀNG LOẠT")
            self.btn_batch_stop.configure(state="disabled", text="⏹ DỪNG LẠI")
            self._refresh_exports_table()
            done = self.batch_stats["done"]
            failed = self.batch_stats["failed"]
            msg = f"Đã xử lý xong hàng loạt!\n- Thành công: {done}/{total}\n- Lỗi: {failed}/{total}"
            messagebox.showinfo("Batch Hoàn Tất", msg)

        self.after(0, finish_ui)


    # --------------------------------------------------------------------------
    # PAGE 2: EFFECT LIBRARY (Catalog / Table View)
    # --------------------------------------------------------------------------
    def _build_page_effects(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.content_container, fg_color="transparent")

        # Header Search & Category Filter
        f_top = ctk.CTkFrame(page, fg_color=CLR_BG_CARD, corner_radius=10)
        f_top.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(f_top, text="EFFECT LIBRARY", font=ctk.CTkFont(size=15, weight="bold"), text_color=CLR_PRIMARY).pack(side="left", padx=16, pady=12)

        self.eff_search_entry = ctk.CTkEntry(f_top, placeholder_text="Search effects...", width=240, height=30, fg_color=CLR_BG_INPUT, border_color=CLR_BORDER)
        self.eff_search_entry.pack(side="left", padx=(10, 8))
        self.eff_search_entry.bind("<KeyRelease>", lambda e: self._render_effects_table())

        cats = ["All Categories"] + self.effects_catalog.get_categories()
        self.eff_cat_combo = ctk.CTkComboBox(f_top, values=cats, width=180, height=30, command=lambda v: self._render_effects_table())
        self.eff_cat_combo.pack(side="left")
        self.eff_cat_combo.set("All Categories")

        # Effects Scroll Table
        self.eff_scroll = ctk.CTkScrollableFrame(page, fg_color=CLR_BG_CARD, corner_radius=10)
        self.eff_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self._render_effects_table()
        return page

    def _render_effects_table(self):
        for w in self.eff_scroll.winfo_children():
            w.destroy()

        q = self.eff_search_entry.get().strip().lower()
        cat_filter = self.eff_cat_combo.get()

        all_effs = self.effects_catalog.list_all()

        # Table Header
        th = ctk.CTkFrame(self.eff_scroll, height=32, fg_color="#181a20", corner_radius=6)
        th.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(th, text="Effect Name", width=220, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=12)
        ctk.CTkLabel(th, text="Category", width=160, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkLabel(th, text="Description", anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", fill="x", expand=True)

        for eff in all_effs:
            if q and (q not in eff["name"].lower() and q not in eff["category"].lower()):
                continue
            if cat_filter != "All Categories" and eff["category"] != cat_filter:
                continue

            row = ctk.CTkFrame(self.eff_scroll, height=40, fg_color="#23262d", corner_radius=6)
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text=eff["name"], width=220, anchor="w", font=ctk.CTkFont(size=13, weight="bold"), text_color=CLR_PRIMARY).pack(side="left", padx=12)
            ctk.CTkLabel(row, text=eff["category"], width=160, anchor="w", font=ctk.CTkFont(size=12), text_color=CLR_TXT_MUTED).pack(side="left")
            ctk.CTkLabel(row, text=eff.get("description", ""), anchor="w", font=ctk.CTkFont(size=11), text_color=CLR_TXT_MUTED).pack(side="left", fill="x", expand=True)

            use_btn = ctk.CTkButton(
                row,
                text="Use in Recipe",
                width=110,
                height=26,
                fg_color="#0284c7",
                hover_color="#0369a1",
                font=ctk.CTkFont(size=11),
                command=lambda name=eff["name"]: self._select_effect_and_return(name),
            )
            use_btn.pack(side="right", padx=10)

    def _select_effect_and_return(self, eff_name: str):
        self.effect_combo.set(eff_name)
        self._switch_nav("create")
        self._update_live_summary()
        self._log(f"[Effect] Đã chọn hiệu ứng: {eff_name}")

    # --------------------------------------------------------------------------
    # PAGE 3: VOICE STUDIO (TTS 60% / 40%)
    # --------------------------------------------------------------------------
    def _build_page_voice(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.content_container, fg_color="transparent")

        top_f = ctk.CTkFrame(page, fg_color="transparent")
        top_f.pack(fill="both", expand=True, padx=16, pady=12)

        # 60% Left: Script Editor
        left_f = ctk.CTkFrame(top_f, fg_color=CLR_BG_CARD, corner_radius=10)
        left_f.pack(side="left", fill="both", expand=True, padx=(0, 10))

        ctk.CTkLabel(left_f, text="SCRIPT EDITOR", font=ctk.CTkFont(size=14, weight="bold"), text_color=CLR_PRIMARY).pack(anchor="w", padx=16, pady=(14, 8))

        self.voice_script_box = ctk.CTkTextbox(left_f, font=ctk.CTkFont(size=13), fg_color=CLR_BG_PANEL, corner_radius=8)
        self.voice_script_box.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.voice_script_box.insert("1.0", "Chào mừng bạn đến với CapCut Studio Pro! Video này được tự động hóa hoàn toàn.")
        self.voice_script_box.bind("<KeyRelease>", self._update_script_stats)

        self.script_stats_lbl = ctk.CTkLabel(left_f, text="84 ký tự · Ước tính: ~6 giây", font=ctk.CTkFont(size=12), text_color=CLR_TXT_MUTED)
        self.script_stats_lbl.pack(anchor="w", padx=16, pady=(0, 12))

        # 40% Right: Voice Controls & Preview
        right_f = ctk.CTkFrame(top_f, width=380, fg_color=CLR_BG_CARD, corner_radius=10)
        right_f.pack(side="right", fill="both")
        right_f.pack_propagate(False)

        ctk.CTkLabel(right_f, text="VOICE CONTROLS", font=ctk.CTkFont(size=14, weight="bold"), text_color=CLR_PRIMARY).pack(anchor="w", padx=16, pady=(14, 10))

        ctk.CTkLabel(right_f, text="Chọn giọng đọc:").pack(anchor="w", padx=16, pady=(4, 2))
        voices = self.voice_studio.get_voice_list()
        voice_names = [f"[{v['lang']}] {v['display_name']}" for v in voices]
        self.tts_voice_combo = ctk.CTkComboBox(right_f, values=voice_names, height=32)
        self.tts_voice_combo.pack(fill="x", padx=16, pady=(0, 10))
        if voice_names: self.tts_voice_combo.set(voice_names[0])

        self.tts_speed_slider = self._add_slider_ctrl(right_f, "Speed", 0.5, 2.0, 1.0, "x")

        # Preview Button
        self.tts_preview_btn = ctk.CTkButton(
            right_f,
            text="🔊  TẠO & NGHE THỬ",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            height=40,
            corner_radius=8,
            command=self._generate_tts_preview,
        )
        self.tts_preview_btn.pack(fill="x", padx=16, pady=(14, 6))

        self.tts_status_lbl = ctk.CTkLabel(right_f, text="Ready", font=ctk.CTkFont(size=12), text_color=CLR_TXT_MUTED)
        self.tts_status_lbl.pack(anchor="w", padx=16, pady=(0, 10))

        # Generated audio card
        self.f_tts_generated = ctk.CTkFrame(right_f, fg_color=CLR_BG_PANEL, corner_radius=8)
        self.f_tts_generated.pack(fill="x", padx=16, pady=6)

        ctk.CTkLabel(self.f_tts_generated, text="Generated Audio Ready", font=ctk.CTkFont(size=12, weight="bold"), text_color=CLR_SUCCESS).pack(anchor="w", padx=12, pady=(10, 4))
        self.last_generated_audio = ""

        self.add_to_recipe_btn = ctk.CTkButton(
            self.f_tts_generated,
            text="Add to Current Recipe as BGM",
            font=ctk.CTkFont(size=11),
            fg_color="#334155",
            hover_color="#475569",
            height=28,
            command=self._add_generated_tts_to_recipe,
        )
        self.add_to_recipe_btn.pack(fill="x", padx=12, pady=(0, 10))

        return page

    def _update_script_stats(self, *args):
        txt = self.voice_script_box.get("1.0", "end").strip()
        length = len(txt)
        est_sec = max(1, int(length / 14))
        self.script_stats_lbl.configure(text=f"{length} ký tự · Ước tính: ~{est_sec} giây")

    def _generate_tts_preview(self):
        text = self.voice_script_box.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Thiếu nội dung", "Vui lòng nhập văn bản cần tạo giọng đọc.")
            return

        selected_voice_str = self.tts_voice_combo.get()
        voice_type = "BV421_vivn_streaming"
        for v in self.voice_studio.get_voice_list():
            if v["display_name"] in selected_voice_str:
                voice_type = v["voice_type"]
                break

        rate = float(self.tts_speed_slider.get())

        def task():
            self._log(f"[*] Đang tạo giọng nói ({voice_type}, rate={rate:.1f})...")
            self.after(0, lambda: self.tts_status_lbl.configure(text="Đang kết nối CapCut Cloud TTS...", text_color=CLR_PRIMARY))
            ok, msg, file_path = self.voice_studio.synthesize(text=text, voice_type=voice_type, rate=rate)
            if ok and file_path:
                self.last_generated_audio = file_path
                self._log(f"[+] {msg}")
                self.after(0, lambda: self.tts_status_lbl.configure(text=f"Hoàn thành: {Path(file_path).name}", text_color=CLR_SUCCESS))
                if sys.platform == "win32":
                    os.startfile(file_path)
            else:
                self._log(f"[-] {msg}")
                self.after(0, lambda: self.tts_status_lbl.configure(text=msg, text_color=CLR_DANGER))

        threading.Thread(target=task, daemon=True).start()

    def _add_generated_tts_to_recipe(self):
        if not self.last_generated_audio or not os.path.isfile(self.last_generated_audio):
            messagebox.showwarning("Chưa có audio", "Vui lòng tạo giọng đọc trước.")
            return
        self.bgm_entry.delete(0, "end")
        self.bgm_entry.insert(0, self.last_generated_audio)
        self._switch_nav("create")
        self._update_live_summary()
        self._log(f"[Voice] Đã gán file giọng đọc vào BGM của Recipe: {Path(self.last_generated_audio).name}")

    # --------------------------------------------------------------------------
    # PAGE 4: EXPORTS HISTORY
    # --------------------------------------------------------------------------
    def _build_page_exports(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.content_container, fg_color="transparent")

        top_f = ctk.CTkFrame(page, fg_color=CLR_BG_CARD, corner_radius=10)
        top_f.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(top_f, text="EXPORTS HISTORY", font=ctk.CTkFont(size=15, weight="bold"), text_color=CLR_PRIMARY).pack(side="left", padx=16, pady=12)

        self.exp_search_entry = ctk.CTkEntry(top_f, placeholder_text="Search exports...", width=240, height=30, fg_color=CLR_BG_INPUT, border_color=CLR_BORDER)
        self.exp_search_entry.pack(side="left", padx=(10, 8))
        self.exp_search_entry.bind("<KeyRelease>", lambda e: self._refresh_exports_table())

        open_folder_btn = ctk.CTkButton(top_f, text="Open Output Folder", width=140, height=30, fg_color="#334155", hover_color="#475569", command=self._open_output_folder)
        open_folder_btn.pack(side="right", padx=16)

        # Table Scroll
        self.exp_scroll = ctk.CTkScrollableFrame(page, fg_color=CLR_BG_CARD, corner_radius=10)
        self.exp_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self._refresh_exports_table()
        return page

    def _refresh_exports_table(self):
        for w in self.exp_scroll.winfo_children():
            w.destroy()

        q = self.exp_search_entry.get().strip().lower()

        # Header
        th = ctk.CTkFrame(self.exp_scroll, height=32, fg_color="#181a20", corner_radius=6)
        th.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(th, text="File Name", width=280, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=12)
        ctk.CTkLabel(th, text="Size", width=110, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkLabel(th, text="Date Modified", width=160, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkLabel(th, text="Status", anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", fill="x", expand=True)

        output_dir = Path(__file__).resolve().parent
        mp4_files = sorted(output_dir.glob("*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)

        for f in mp4_files[:40]:
            if q and q not in f.name.lower():
                continue

            size_mb = f.stat().st_size / (1024 * 1024)
            mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime))

            row = ctk.CTkFrame(self.exp_scroll, height=38, fg_color="#23262d", corner_radius=6)
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text=f.name, width=280, anchor="w", font=ctk.CTkFont(size=13, weight="bold"), text_color=CLR_PRIMARY).pack(side="left", padx=12)
            ctk.CTkLabel(row, text=f"{size_mb:.2f} MB", width=110, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left")
            ctk.CTkLabel(row, text=mtime, width=160, anchor="w", font=ctk.CTkFont(size=12), text_color=CLR_TXT_MUTED).pack(side="left")
            ctk.CTkLabel(row, text="● Done", anchor="w", font=ctk.CTkFont(size=12, weight="bold"), text_color=CLR_SUCCESS).pack(side="left", fill="x", expand=True)

            play_btn = ctk.CTkButton(row, text="Play", width=65, height=26, fg_color="#0284c7", hover_color="#0369a1", command=lambda p=str(f): os.startfile(p) if sys.platform == "win32" else None)
            play_btn.pack(side="right", padx=10)

    def _open_output_folder(self):
        folder = str(Path(__file__).resolve().parent)
        if sys.platform == "win32":
            os.startfile(folder)

    # --------------------------------------------------------------------------
    # PAGE 5: ACCOUNT MANAGER (Compact Cards + Pool Table + Modal Add)
    # --------------------------------------------------------------------------
    def _build_page_accounts(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.content_container, fg_color="transparent")

        # Active Account Card
        card = ctk.CTkFrame(page, fg_color=CLR_BG_CARD, corner_radius=10)
        card.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(card, text="ACTIVE ACCOUNT", font=ctk.CTkFont(size=14, weight="bold"), text_color=CLR_PRIMARY).pack(anchor="w", padx=16, pady=(12, 8))

        grid = ctk.CTkFrame(card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(0, 10))

        self.acc_email_lbl = ctk.CTkLabel(grid, text="Email: ...", font=ctk.CTkFont(size=13))
        self.acc_email_lbl.grid(row=0, column=0, sticky="w", padx=(0, 30), pady=2)

        self.acc_plan_lbl = ctk.CTkLabel(grid, text="Plan: PRO / VIP", font=ctk.CTkFont(size=13, weight="bold"), text_color=CLR_SUCCESS)
        self.acc_plan_lbl.grid(row=0, column=1, sticky="w", padx=(0, 30), pady=2)

        self.acc_expire_lbl = ctk.CTkLabel(grid, text="Expires: ...", font=ctk.CTkFont(size=13, weight="bold"), text_color=CLR_WARNING)
        self.acc_expire_lbl.grid(row=1, column=0, sticky="w", padx=(0, 30), pady=2)

        self.acc_storage_lbl = ctk.CTkLabel(grid, text="Cloud Storage: 1024 GB", font=ctk.CTkFont(size=13))
        self.acc_storage_lbl.grid(row=1, column=1, sticky="w", padx=(0, 30), pady=2)

        btn_r = ctk.CTkFrame(card, fg_color="transparent")
        btn_r.pack(fill="x", padx=16, pady=(4, 12))

        ctk.CTkButton(
            btn_r,
            text="Refresh Session (Auto Login)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            height=30,
            command=self._refresh_active_cookie,
        ).pack(side="left")

        # Account Pool Table
        pool_f = ctk.CTkFrame(page, fg_color=CLR_BG_CARD, corner_radius=10)
        pool_f.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        p_hdr = ctk.CTkFrame(pool_f, fg_color="transparent")
        p_hdr.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(p_hdr, text="ACCOUNT POOL", font=ctk.CTkFont(size=14, weight="bold"), text_color=CLR_PRIMARY).pack(side="left")

        ctk.CTkButton(
            p_hdr,
            text="+ Add Account",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=28,
            command=self._open_add_account_modal,
        ).pack(side="right")

        self.acc_pool_scroll = ctk.CTkScrollableFrame(pool_f, fg_color="transparent")
        self.acc_pool_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self._render_account_pool_table()
        return page

    def _render_account_pool_table(self):
        for w in self.acc_pool_scroll.winfo_children():
            w.destroy()

        accounts = self.acc_mgr.list_accounts()

        # Header
        th = ctk.CTkFrame(self.acc_pool_scroll, height=30, fg_color="#181a20", corner_radius=6)
        th.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(th, text="Email", width=240, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=12)
        ctk.CTkLabel(th, text="Plan", width=90, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkLabel(th, text="Remaining", width=160, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkLabel(th, text="Status", anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", fill="x", expand=True)

        for acc in accounts:
            is_act = acc.get("is_active", False)
            row = ctk.CTkFrame(self.acc_pool_scroll, height=38, fg_color="#252930" if is_act else "#1f2228", corner_radius=6)
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text=acc["email"], width=240, anchor="w", font=ctk.CTkFont(size=13, weight="bold" if is_act else "normal"), text_color=CLR_PRIMARY if is_act else CLR_TXT_MAIN).pack(side="left", padx=12)
            ctk.CTkLabel(row, text="PRO" if acc.get("is_pro") else "FREE", width=90, anchor="w", font=ctk.CTkFont(size=12, weight="bold"), text_color=CLR_SUCCESS if acc.get("is_pro") else CLR_TXT_MUTED).pack(side="left")
            ctk.CTkLabel(row, text=self.acc_mgr.format_pro_remaining(acc.get("pro_expire_time", 0)), width=160, anchor="w", font=ctk.CTkFont(size=12), text_color=CLR_WARNING).pack(side="left")
            ctk.CTkLabel(row, text="● Active" if is_act else "Standby", anchor="w", font=ctk.CTkFont(size=12), text_color=CLR_SUCCESS if is_act else CLR_TXT_MUTED).pack(side="left", fill="x", expand=True)

            if not is_act:
                sw_btn = ctk.CTkButton(row, text="Set Active", width=80, height=24, font=ctk.CTkFont(size=11), fg_color="#0284c7", hover_color="#0369a1", command=lambda em=acc["email"]: self._switch_to_account(em))
                sw_btn.pack(side="right", padx=6)

            del_btn = ctk.CTkButton(row, text="Remove", width=60, height=24, font=ctk.CTkFont(size=11), fg_color=CLR_DANGER, hover_color="#b91c1c", command=lambda em=acc["email"]: self._delete_account(em))
            del_btn.pack(side="right", padx=4)

    def _open_add_account_modal(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Add CapCut Account")
        modal.geometry("420x300")
        modal.resizable(False, False)
        modal.transient(self)
        modal.grab_set()

        ctk.CTkLabel(modal, text="ADD CAPCUT ACCOUNT", font=ctk.CTkFont(size=15, weight="bold"), text_color=CLR_PRIMARY).pack(pady=(16, 10))

        f = ctk.CTkFrame(modal, fg_color="transparent")
        f.pack(fill="x", padx=24)

        ctk.CTkLabel(f, text="Email:").pack(anchor="w", pady=(4, 2))
        email_e = ctk.CTkEntry(f, placeholder_text="moehingletito854@outlook.com", height=30)
        email_e.pack(fill="x")

        ctk.CTkLabel(f, text="Password:").pack(anchor="w", pady=(8, 2))
        pwd_e = ctk.CTkEntry(f, placeholder_text="capcutpro2026", show="*", height=30)
        pwd_e.pack(fill="x")

        btn_row = ctk.CTkFrame(modal, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=20)

        def save():
            em = email_e.get().strip()
            pw = pwd_e.get().strip()
            if not em or not pw:
                messagebox.showwarning("Thiếu thông tin", "Vui lòng điền Email và Password.")
                return
            modal.destroy()
            self._execute_add_account(em, pw)

        ctk.CTkButton(btn_row, text="Cancel", width=90, fg_color="#334155", command=modal.destroy).pack(side="left")
        ctk.CTkButton(btn_row, text="Add & Login", width=120, fg_color="#059669", hover_color="#047857", command=save).pack(side="right")

    def _execute_add_account(self, email: str, pwd: str):
        def task():
            self.is_processing = True
            self._log(f"[*] Thêm tài khoản và kích hoạt đăng nhập: {email}...")
            ok, msg = self.acc_mgr.add_account(email, pwd, note="", auto_login_now=True, status_callback=self._log)
            if ok:
                self.auth.load_session()
                self._update_account_ui_success(self.acc_mgr.get_active_account())
                messagebox.showinfo("Thành công", msg)
            else:
                messagebox.showerror("Lỗi", msg)
            self.is_processing = False

        threading.Thread(target=task, daemon=True).start()

    def _switch_to_account(self, target_email: str):
        def task():
            self.is_processing = True
            self._log(f"[*] Đang chuyển sang tài khoản: {target_email}...")
            ok, msg = self.acc_mgr.switch_account(target_email, status_callback=self._log)
            if ok:
                self.auth.load_session()
                self._update_account_ui_success(self.acc_mgr.get_active_account())
                messagebox.showinfo("Thành công", msg)
            else:
                messagebox.showerror("Lỗi", msg)
            self.is_processing = False

        threading.Thread(target=task, daemon=True).start()

    def _refresh_active_cookie(self):
        def task():
            self.is_processing = True
            self._log("[*] Đang làm mới phiên cookie...")
            ok, msg = self.acc_mgr.refresh_active_account(status_callback=self._log)
            if ok:
                self.auth.load_session()
                self._update_account_ui_success(self.acc_mgr.get_active_account())
                messagebox.showinfo("Thành công", msg)
            else:
                messagebox.showerror("Lỗi", msg)
            self.is_processing = False

        threading.Thread(target=task, daemon=True).start()

    def _delete_account(self, email: str):
        if messagebox.askyesno("Confirm", f"Xóa tài khoản {email}?"):
            self.acc_mgr.remove_account(email)
            self._render_account_pool_table()

    # --------------------------------------------------------------------------
    # Initial Sync & Status Helpers
    # --------------------------------------------------------------------------
    def _initial_sync(self):
        threading.Thread(target=self._sync_active_account_worker, daemon=True).start()

    def _sync_active_account_worker(self):
        self._log("[*] Loading CapCut session...")
        active = self.acc_mgr.get_active_account()

        if self.auth.load_session():
            ok = self.auth.sync_all()
            if ok:
                self._update_account_ui_success(active)
                return

        if active and active.get("email") and active.get("password"):
            self._log(f"[*] Session needs refresh. Auto-logging in: {active['email']}...")
            ok, msg = self.acc_mgr.refresh_active_account(status_callback=self._log)
            if ok:
                self._update_account_ui_success(self.acc_mgr.get_active_account())
                return

        self._log("[-] Session invalid or not logged in.")
        self.after(0, lambda: self.hdr_cloud_badge.configure(text="● Offline", text_color=CLR_DANGER, fg_color="#450a0a"))

    def _update_account_ui_success(self, active_acc: Optional[Dict[str, Any]]):
        active = active_acc or self.acc_mgr.get_active_account()
        email = self.auth.email or (active.get("email") if active else "N/A")
        is_pro = self.auth.is_pro
        exp_time = self.auth.pro_expire_time
        rem_str = self.acc_mgr.format_pro_remaining(exp_time)

        def update():
            plan_str = f"PRO · {rem_str}" if is_pro else "FREE"
            self.hdr_account_badge.configure(
                text=plan_str,
                text_color=CLR_SUCCESS if is_pro else CLR_TXT_MUTED,
                fg_color="#14532d" if is_pro else "#262626",
            )
            self.hdr_user_btn.configure(text=f"Account: {email}")

            self.acc_email_lbl.configure(text=f"Email: {email}")
            self.acc_plan_lbl.configure(text=f"Plan: {'PRO / VIP' if is_pro else 'FREE'}", text_color=CLR_SUCCESS if is_pro else CLR_TXT_MUTED)
            exp_date = time.strftime("%b %d, %Y", time.localtime(exp_time)) if exp_time else "N/A"
            self.acc_expire_lbl.configure(text=f"Expires: {exp_date} ({rem_str})")

            self._render_account_pool_table()
            self._update_live_summary()
            self._log(f"[+] Synchronized account: {email} | {plan_str}")

        self.after(0, update)

    # --------------------------------------------------------------------------
    # Video Input Resolver
    # --------------------------------------------------------------------------
    def _get_video_list(self, folder_or_file: str) -> List[str]:
        exts = (".mp4", ".mov", ".avi", ".mkv", ".flv")
        p = Path(folder_or_file)
        if p.is_file() and p.suffix.lower() in exts:
            return [str(p)]
        if p.is_dir():
            return sorted([str(f) for f in p.iterdir() if f.is_file() and f.suffix.lower() in exts])
        return []

    # --------------------------------------------------------------------------
    # PIPELINE EXECUTION
    # --------------------------------------------------------------------------
    def _start_pipeline_thread(self):
        if self.is_processing:
            messagebox.showwarning("Busy", "Một tác vụ đang chạy. Vui lòng chờ.")
            return

        in_path = self.input_path_entry.get().strip()
        if not in_path or not os.path.exists(in_path):
            messagebox.showwarning("Missing Input", "Vui lòng chọn Folder hoặc File video hợp lệ.")
            return

        videos = self._get_video_list(in_path)
        if not videos:
            messagebox.showwarning("No Videos", f"Không tìm thấy video nào trong:\n{in_path}")
            return

        threading.Thread(target=self._run_pipeline_worker, args=(videos,), daemon=True).start()

    def _run_pipeline_worker(self, videos: List[str]):
        self.is_processing = True
        self.after(0, lambda: self.primary_action_btn.configure(state="disabled", text="⏳ PROCESSING..."))

        try:
            seg = int(self.seg_entry.get().strip() or "0")
            if seg < 0:
                seg = 0
        except Exception:
            seg = 0

        try:
            n_threads = int(self.workers_combo.get().strip() or "4")
        except Exception:
            n_threads = 4

        eff_name = self.effect_combo.get()
        eff_item = next((e for e in self.effects_catalog.list_all() if e["name"] == eff_name), None)
        eff_id = eff_item["id"] if eff_item else ""
        eff_path = self.effects_catalog.get_local_effect_path(eff_id) or ""

        eff_speed = float(self.eff_speed_slider.get()) / 100.0
        eff_air = float(self.eff_air_slider.get()) / 100.0
        video_speed = float(self.vspeed_slider.get())
        volume_db = float(self.vol_slider.get())
        scale_pct = float(self.scale_slider.get())
        voice_sharpen = self.chk_voice_sharpen.get()
        vocal_sep = self.chk_vocal_sep.get()

        color_temp = int(self.color_temp_slider.get())
        color_tone = int(self.color_tone_slider.get())
        color_sat = int(self.color_sat_slider.get())
        color_contrast = int(self.color_contrast_slider.get())
        color_shadow = int(self.color_shadow_slider.get())

        overlay_path = self.ov_entry.get().strip()
        overlay_blend = self.chk_chroma.get()
        chroma_intensity = float(self.chroma_slider.get()) / 100.0

        bgm_path = self.bgm_entry.get().strip()
        bgm_db = float(self.bgm_vol_slider.get())

        mode = self.export_mode.get()
        definition = self.res_combo.get()
        fps = int(self.fps_combo.get())

        self._log("\n" + "=" * 65)
        self._log(f" [CREATE & RUN JOB] Total videos: {len(videos)}, Workers: {n_threads}, Mode: {mode}")
        self._log("=" * 65)

        lock = threading.Lock()
        counter = [0]
        fails = []
        successes = []

        output_dir = Path(DEFAULT_OUTPUT_DIR).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        def process_single(vp: str) -> bool:
            name = Path(vp).name
            self._log(f"[*] Processing: {name}")

            draft_params = {
                "seg": seg,
                "effect_name": eff_name,
                "effect_id": eff_id,
                "effect_path": eff_path,
                "effect_speed": eff_speed,
                "effect_air": eff_air,
                "video_speed": video_speed,
                "volume_db": volume_db,
                "scale_pct": scale_pct,
                "voice_sharpen": voice_sharpen,
                "vocal_sep": vocal_sep,
                "color_temperature": color_temp,
                "color_tone": color_tone,
                "color_saturation": color_sat,
                "color_contrast": color_contrast,
                "color_shadow": color_shadow,
                "overlay_path": overlay_path,
                "overlay_blend": overlay_blend,
                "chroma_intensity": chroma_intensity,
                "bgm_path": bgm_path,
                "bgm_db": bgm_db,
            }

            if mode == "local":
                draft_content, _, err = make_draft(vp=vp, **draft_params)
                if err:
                    with lock:
                        fails.append(f"{name}: {err}")
                        counter[0] += 1
                        pct = int(counter[0] / len(videos) * 100)
                        self._update_progress(pct, f"[{counter[0]}/{len(videos)}] Failed: {name}")
                    return False

                d_name, d_dir = save_local_capcut_draft(vp, draft_content)
                with lock:
                    successes.append(name)
                    counter[0] += 1
                    pct = int(counter[0] / len(videos) * 100)
                    self._update_progress(pct, f"[{counter[0]}/{len(videos)}] Draft created: {d_name}")
                self._log(f"[+] Local Draft Ready: {d_name}")
                return True
            else:
                out_mp4 = str(output_dir / f"rendered_{Path(vp).stem}.mp4")
                try:
                    def render_sub_cb(sub_pct: int, sub_msg: str):
                        base_pct = int((counter[0] / len(videos)) * 100)
                        step_pct = int(sub_pct / len(videos))
                        self._update_progress(base_pct + step_pct, f"[{counter[0]+1}/{len(videos)}] {sub_msg}")

                    use_auto_chunk = getattr(self, "auto_chunk_var", None) and self.auto_chunk_var.get()

                    if use_auto_chunk:
                        downloaded = render_video_auto_chunked_cloud(
                            vp=vp,
                            draft_params=draft_params,
                            output_mp4=out_mp4,
                            chunk_duration=60,
                            max_chunk_workers=min(2, n_threads),
                            definition=definition,
                            fps=fps,
                            log_cb=self._log,
                            progress_cb=render_sub_cb,
                        )
                    else:
                        draft_content, _, err = make_draft(vp=vp, **draft_params)
                        if err:
                            raise RuntimeError(f"Lỗi tạo draft: {err}")
                        downloaded = render_draft_cloud(
                            vp=vp,
                            draft_content=draft_content,
                            output_mp4=out_mp4,
                            overlay_path=overlay_path,
                            bgm_path=bgm_path,
                            definition=definition,
                            fps=fps,
                            log_cb=self._log,
                            progress_cb=render_sub_cb,
                        )

                    with lock:
                        successes.append(name)
                        counter[0] += 1
                        pct = int(counter[0] / len(videos) * 100)
                        self._update_progress(pct, f"[{counter[0]}/{len(videos)}] Rendered: {name}")
                    self._log(f"[+] Cloud Render Succeeded: {downloaded}")
                    return True

                except Exception as exc:
                    with lock:
                        fails.append(f"{name}: {exc}")
                        counter[0] += 1
                        pct = int(counter[0] / len(videos) * 100)
                        self._update_progress(pct, f"[{counter[0]}/{len(videos)}] Render Error: {name}")
                    self._log(f"[-] Render Error: {name} -> {exc}")
                    return False

        with ThreadPoolExecutor(max_workers=n_threads) as executor:
            futures = [executor.submit(process_single, vp) for vp in videos]
            for f in as_completed(futures):
                pass

        self.after(0, self._refresh_exports_table)
        self._update_progress(100, f"Completed: {len(successes)}/{len(videos)} videos successful")

        summary_msg = f"Hoàn thành {len(successes)}/{len(videos)} video."
        if fails:
            summary_msg += "\n\nLỗi:\n" + "\n".join(fails[:5])

        self.is_processing = False
        def finish_job():
            self._on_output_mode_changed()
            self.primary_action_btn.configure(
                state="normal",
                text="▶ CREATE & RENDER" if self.export_mode.get() == "cloud" else "▶ CREATE DRAFTS",
            )
            messagebox.showinfo("Job Finished", summary_msg)

        self.after(0, finish_job)

    def _update_progress(self, pct: int, status_text: str):
        def update():
            self.queue_bar.set(pct / 100.0)
            self.queue_pct_lbl.configure(text=f"{pct}%")
            self.queue_status_lbl.configure(text=f"● {status_text}")
        self.after(0, update)

    def _log(self, text: str):
        def append():
            self.log_textbox.insert("end", f"{text}\n")
            self.log_textbox.see("end")
        self.after(0, append)


def main():
    app = CapCutStudioApp()
    app.mainloop()


if __name__ == "__main__":
    main()
