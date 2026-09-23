#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_draft_core.py - Core CapCut Draft Generator & Cloud Render Bridge
Directly integrates the proven production logic from capcut_tool.py:
- Multi-track assembly: Video segments, speeds, canvas, placeholder info, vocal separation
- Color grading: Temperature, Tone, Saturation, Contrast, Shadow
- Voice sharpening audio effect (7491147795483659521)
- Video effects with speed & air animation
- Green screen overlay video with chroma keying (intensity & smoothing)
- Background music (BGM) looping across timeline
- Cloud Render adapter: Bridges local draft_content to ByteDance VOD TOS & Cloud Render API
"""

import os
import sys
import re
import json
import uuid
import time
import math
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable

sys.stdout.reconfigure(encoding="utf-8")

BASE_CAPCUT = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CapCut")
CAPCUT_DIR = os.path.join(BASE_CAPCUT, "User Data", "Projects", "com.lveditor.draft")


def get_duration(path: str) -> Tuple[Optional[float], int, int]:
    """Retrieve duration and dimensions via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(r.stdout)
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                dur = s.get("duration")
                if dur is None:
                    # Try format duration
                    pass
                return float(dur or 0), int(s.get("width", 1920)), int(s.get("height", 1080))
    except Exception:
        pass
    return None, 1920, 1080


def db_to_volume(db: float) -> float:
    """Convert decibels to linear volume factor."""
    if db == 0.0:
        return 1.0
    return round(10 ** (db / 20.0), 4)


def make_draft(
    vp: str,
    seg: int = 600,
    effect_name: str = "Không có",
    effect_id: str = "",
    effect_path: str = "",
    effect_speed: float = 0.13,
    effect_air: float = 0.35,
    video_speed: float = 1.0,
    volume_db: float = 0.0,
    scale_pct: float = 120.0,
    voice_sharpen: bool = False,
    vocal_sep: bool = False,
    vocal_path: str = "",
    color_temperature: int = 0,
    color_tone: int = 0,
    color_saturation: int = 0,
    color_contrast: int = 0,
    color_shadow: int = 0,
    overlay_path: str = "",
    overlay_blend: bool = True,
    chroma_intensity: float = 0.7,
    bgm_path: str = "",
    bgm_db: float = 0.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    Builds the complete CapCut draft data structure (draft_content).
    Returns: (draft_content_dict, draft_dir, error_message)
    """
    duration, width, height = get_duration(vp)
    if not duration or duration <= 0:
        return None, None, f"Không đọc được video: {vp}"

    real_duration = duration / video_speed
    duration_us = int(real_duration * 1e6)

    # Safe / Adaptive segmentation:
    # If seg <= 0 or seg >= real_duration, keep 1 continuous segment (ideal for long videos & cloud render)
    if not seg or float(seg) <= 0 or float(seg) >= real_duration:
        seg_actual = real_duration
        num_seg = 1
    else:
        seg_actual = float(seg)
        num_seg = math.ceil(real_duration / seg_actual)
        # Cap excessive segments to avoid overwhelming cloud render API
        if num_seg > 60:
            num_seg = 60
            seg_actual = real_duration / 60

    mat_name = os.path.basename(vp)
    mat_id = str(uuid.uuid4()).upper()
    track_id = str(uuid.uuid4()).upper()
    volume = db_to_volume(volume_db)
    has_vocal_audio = bool(vocal_path and os.path.exists(vocal_path))
    video_seg_volume = 0.0 if has_vocal_audio else volume
    scale = scale_pct / 100.0

    segments = []
    speeds, canvases, phs, scs, mcs, vss = [], [], [], [], [], []

    for i in range(num_seg):
        cs = i * seg_actual
        ce = min(cs + seg_actual, real_duration)
        cd = ce - cs
        src_cs = cs * video_speed
        src_cd = cd * video_speed
        sid = str(uuid.uuid4()).upper()
        spid = str(uuid.uuid4()).upper()
        caid = str(uuid.uuid4()).upper()
        phid = str(uuid.uuid4()).upper()
        scid = str(uuid.uuid4()).upper()
        mcid = str(uuid.uuid4()).upper()
        vsid = str(uuid.uuid4()).upper()

        segments.append({
            "id": sid,
            "source_timerange": {"start": int(src_cs * 1e6), "duration": int(src_cd * 1e6)},
            "target_timerange": {"start": int(cs * 1e6), "duration": int(cd * 1e6)},
            "render_timerange": {"start": 0, "duration": 0},
            "desc": "",
            "state": 0,
            "speed": video_speed,
            "is_loop": False,
            "is_tone_modify": False,
            "reverse": False,
            "intensifies_audio": False,
            "cartoon": False,
            "volume": video_seg_volume,
            "last_nonzero_volume": volume,
            "clip": {
                "scale": {"x": scale, "y": scale},
                "rotation": 0.0,
                "transform": {"x": 0.0, "y": 0.0},
                "flip": {"vertical": False, "horizontal": False},
                "alpha": 1.0,
            },
            "uniform_scale": {"on": True, "value": scale},
            "material_id": mat_id,
            "extra_material_refs": [spid, phid, caid, scid, mcid, vsid],
            "render_index": 0,
            "keyframe_refs": [],
            "enable_lut": True,
            "enable_adjust": True,
            "enable_hsl": False,
            "visible": True,
            "group_id": "",
            "enable_color_curves": True,
            "enable_hsl_curves": True,
            "track_render_index": 0,
            "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
            "enable_color_wheels": True,
            "track_attribute": 0,
            "is_placeholder": False,
            "template_id": "",
            "template_scene": "default",
            "common_keyframes": [],
            "caption_info": None,
            "source": "segmentsourcenormal",
            "enable_mask_stroke": False,
            "enable_mask_shadow": False,
            "enable_color_adjust_pro": False,
        })
        speeds.append({"id": spid, "type": "speed", "mode": 0, "speed": video_speed, "curve_speed": None})
        canvases.append({"id": caid, "type": "canvas_color", "color": "", "blur": 0.0, "image": "", "album_image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": ""})
        phs.append({"id": phid, "type": "placeholder_info", "meta_type": "none", "res_path": "", "res_text": "", "error_path": "", "error_text": ""})
        scs.append({"id": scid, "type": "none", "audio_channel_mapping": 0, "is_config_open": False})
        mcs.append({"id": mcid, "is_color_clip": False, "is_gradient": False, "solid_color": "", "gradient_colors": [], "gradient_percents": [], "gradient_angle": 90.0, "width": 0.0, "height": 0.0})
        vss.append({"id": vsid, "type": "vocal_separation", "choice": 0, "removed_sounds": [], "time_range": None, "production_path": "", "final_algorithm": "", "enter_from": ""})

    audio_effects = []
    color_effects_list = []

    # Color grading
    COLOR_RID = "7501974767453474064"
    color_map = [
        ("temperature", color_temperature, "v3"),
        ("tone", color_tone, "v3"),
        ("saturation", color_saturation, "v1"),
        ("contrast", color_contrast, "v3"),
        ("shadow", color_shadow, "v3"),
    ]
    color_effect_ids = []
    for ctype, cval, cver in color_map:
        if cval != 0:
            cid = str(uuid.uuid4()).upper()
            color_effect_ids.append(cid)
            color_effects_list.append({
                "id": cid,
                "effect_id": COLOR_RID,
                "resource_id": COLOR_RID,
                "third_resource_id": "",
                "name": "",
                "report_name": "",
                "type": ctype,
                "sub_type": "none",
                "path": "",
                "value": round(cval / 50.0, 6),
                "visible": True,
                "item_effect_type": 0,
                "category_id": "",
                "category_name": "",
                "category_key": "",
                "sub_category_id": "",
                "sub_category_name": "",
                "platform": "all",
                "apply_target_type": 0,
                "source_platform": 1,
                "version": cver,
                "adjust_params": [],
                "time_range": None,
                "formula_id": "",
                "enable_skin_tone_correction": False,
                "algorithm_artifact_path": "",
                "intensity_key": "",
                "face_adjust_params": [],
                "exclusion_group": [],
                "panel_id": "",
                "bloom_params": None,
                "request_id": "",
                "color_match_info": {"target_feature_path": "", "source_feature_path": "", "target_image_path": ""},
                "multi_language_current": "",
                "lumi_hub_path": "",
                "covering_relation_change": 0,
                "beauty_face_auto_preset_id": "",
                "beauty_body_auto_preset_id": "",
                "beauty_face_auto_retouch_info": {"face_id": [], "beauty_face_auto_retouch_id": ""},
                "smart_color_mode": 0,
            })

    for seg_item in segments:
        seg_item["extra_material_refs"].extend(color_effect_ids)

    # Voice Sharpen
    if voice_sharpen:
        ae_id = str(uuid.uuid4()).upper()
        ae_const_id = str(uuid.uuid4()).upper()
        audio_effects.append({
            "id": ae_id,
            "constant_material_id": ae_const_id,
            "type": "audio_effect",
            "name": "Giọng nói sắc nét",
            "path": "",
            "production_path": "",
            "sub_type": 1,
            "time_range": {"start": 0, "duration": 0},
            "speaker_id": "",
            "resource_id": "7491147795483659521",
            "third_resource_id": "0",
            "source_platform": 1,
            "category_id": "sound_effect",
            "category_name": "Bộ lọc giọng nói",
            "audio_adjust_params": [{"value": 1.0, "default_value": 1.0, "parameterIndex": 0, "portIndex": 0, "name": "strength", "min_value": 0.0, "max_value": 1.0}],
            "is_vc_clone_tone": False,
            "vc_type": "none",
            "is_ugc": False,
        })
        for seg_item in segments:
            seg_item["extra_material_refs"].append(ae_id)

    # Vocal Separation
    if vocal_sep:
        for v in vss:
            v["choice"] = 2
            v["final_algorithm"] = "vocal_separate"
            v["enter_from"] = "timeline_menu"
            v["time_range"] = {"start": 0, "duration": int(duration * 1e6)}

    tracks = [{"id": track_id, "type": "video", "segments": segments, "flag": 0, "attribute": 0, "name": "", "is_default_name": True}]
    video_effects = []

    # Video Effect
    if effect_id and effect_id != "Không có":
        eff_mat_id = str(uuid.uuid4()).upper()
        eff_track_id = str(uuid.uuid4()).upper()
        eff_seg = {
            "id": str(uuid.uuid4()).upper(),
            "source_timerange": None,
            "target_timerange": {"start": 0, "duration": duration_us},
            "render_timerange": {"start": 0, "duration": 0},
            "desc": "",
            "state": 0,
            "speed": 1.0,
            "is_loop": False,
            "is_tone_modify": False,
            "reverse": False,
            "intensifies_audio": False,
            "cartoon": False,
            "volume": 1.0,
            "last_nonzero_volume": 1.0,
            "clip": None,
            "uniform_scale": None,
            "material_id": eff_mat_id,
            "extra_material_refs": [],
            "render_index": 11000,
            "keyframe_refs": [],
            "enable_lut": False,
            "enable_adjust": False,
            "enable_hsl": False,
            "visible": True,
            "group_id": "",
            "enable_color_curves": True,
            "enable_hsl_curves": True,
            "track_render_index": 1,
            "hdr_settings": None,
            "enable_color_wheels": True,
            "track_attribute": 0,
            "is_placeholder": False,
            "template_id": "",
            "template_scene": "default",
            "common_keyframes": [],
            "caption_info": None,
            "source": "segmentsourcenormal",
            "enable_mask_stroke": False,
            "enable_mask_shadow": False,
            "enable_color_adjust_pro": False,
        }
        tracks.append({"id": eff_track_id, "type": "effect", "segments": [eff_seg], "flag": 0, "attribute": 0, "name": "", "is_default_name": True})
        video_effects.append({
            "id": eff_mat_id,
            "effect_id": effect_id,
            "resource_id": effect_id,
            "name": effect_name,
            "type": "video_effect",
            "sub_type": 0,
            "bind_segment_id": "",
            "transparent_params": "",
            "path": effect_path.replace("\\", "/"),
            "value": 1.0,
            "category_id": "1111",
            "category_name": "Hiệu ứng video",
            "platform": "all",
            "apply_target_type": 2,
            "source_platform": 1,
            "version": "",
            "item_effect_type": 0,
            "adjust_params": [
                {"name": "effects_adjust_speed", "value": effect_speed, "default_value": 0.33},
                {"name": "effects_adjust_background_animation", "value": effect_air, "default_value": 1.0},
            ],
            "time_range": None,
            "formula_id": "",
            "apply_time_range": None,
            "render_index": 0,
            "track_render_index": 0,
            "common_keyframes": [],
            "request_id": "",
            "algorithm_artifact_path": "",
            "disable_effect_faces": [],
            "covering_relation_change": 0,
            "enable_mask": True,
            "effect_mask": [],
            "enable_video_mask_stroke": True,
            "enable_video_mask_shadow": True,
        })

    # Overlay video with green screen removal
    overlay_mats = []
    chromas_list = []
    if overlay_path and os.path.exists(overlay_path):
        ov_mat_id = str(uuid.uuid4()).upper()
        ov_track_id = str(uuid.uuid4()).upper()
        ov_spid = str(uuid.uuid4()).upper()
        ov_caid = str(uuid.uuid4()).upper()
        ov_phid = str(uuid.uuid4()).upper()
        ov_scid = str(uuid.uuid4()).upper()
        ov_mcid = str(uuid.uuid4()).upper()
        ov_vsid = str(uuid.uuid4()).upper()
        ov_chroma_id = str(uuid.uuid4()).upper() if overlay_blend else None

        ov_dur, ov_w, ov_h = get_duration(overlay_path)
        ov_dur = ov_dur or duration
        ov_dur_us = int(ov_dur * 1e6)
        ov_name = os.path.basename(overlay_path)

        ov_seg = {
            "id": str(uuid.uuid4()).upper(),
            "source_timerange": {"start": 0, "duration": ov_dur_us},
            "target_timerange": {"start": 0, "duration": duration_us},
            "render_timerange": {"start": 0, "duration": 0},
            "desc": "",
            "state": 0,
            "speed": 1.0,
            "is_loop": True,
            "is_tone_modify": False,
            "reverse": False,
            "intensifies_audio": False,
            "cartoon": False,
            "volume": 0.0,
            "last_nonzero_volume": 0.0,
            "clip": {"scale": {"x": 1.0, "y": 1.0}, "rotation": 0.0, "transform": {"x": 0.0, "y": 0.0}, "flip": {"vertical": False, "horizontal": False}, "alpha": 1.0},
            "uniform_scale": {"on": True, "value": 1.0},
            "material_id": ov_mat_id,
            "extra_material_refs": [ov_spid, ov_phid, ov_caid, ov_scid, ov_mcid, ov_vsid] + ([ov_chroma_id] if ov_chroma_id else []),
            "render_index": 1,
            "keyframe_refs": [],
            "enable_lut": True,
            "enable_adjust": True,
            "enable_hsl": False,
            "visible": True,
            "group_id": "",
            "enable_color_curves": True,
            "enable_hsl_curves": True,
            "track_render_index": 1,
            "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
            "enable_color_wheels": True,
            "track_attribute": 0,
            "is_placeholder": False,
            "template_id": "",
            "template_scene": "default",
            "common_keyframes": [],
            "caption_info": None,
            "source": "segmentsourcenormal",
            "enable_mask_stroke": False,
            "enable_mask_shadow": False,
            "enable_color_adjust_pro": False,
        }
        tracks.append({"id": ov_track_id, "type": "video", "segments": [ov_seg], "flag": 0, "attribute": 1, "name": "", "is_default_name": True})
        speeds.append({"id": ov_spid, "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None})
        canvases.append({"id": ov_caid, "type": "canvas_color", "color": "", "blur": 0.0, "image": "", "album_image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": ""})
        phs.append({"id": ov_phid, "type": "placeholder_info", "meta_type": "none", "res_path": "", "res_text": "", "error_path": "", "error_text": ""})
        scs.append({"id": ov_scid, "type": "none", "audio_channel_mapping": 0, "is_config_open": False})
        mcs.append({"id": ov_mcid, "is_color_clip": False, "is_gradient": False, "solid_color": "", "gradient_colors": [], "gradient_percents": [], "gradient_angle": 90.0, "width": 0.0, "height": 0.0})
        vss.append({"id": ov_vsid, "type": "vocal_separation", "choice": 0, "removed_sounds": [], "time_range": None, "production_path": "", "final_algorithm": "", "enter_from": ""})

        if ov_chroma_id:
            chromas_list.append({
                "id": ov_chroma_id,
                "type": "chroma",
                "color": "#00b13dff",
                "intensity_value": round(chroma_intensity, 2),
                "shadow_value": 0.0,
                "path": "",
                "resource_id": "",
                "should_transfer_color": True,
                "edge_smooth_value": 0.0,
                "spill_value": 0.0,
                "version": "v2",
            })

        overlay_mats.append({
            "id": ov_mat_id,
            "unique_id": "",
            "type": "video",
            "duration": ov_dur_us,
            "path": overlay_path.replace("\\", "/"),
            "media_path": "",
            "local_id": "",
            "has_audio": False,
            "reverse_path": "",
            "intensifies_path": "",
            "reverse_intensifies_path": "",
            "intensifies_audio_path": "",
            "cartoon_path": "",
            "width": ov_w,
            "height": ov_h,
            "material_name": ov_name,
            "crop": {"upper_left_x": 0.0, "upper_left_y": 0.0, "upper_right_x": 1.0, "upper_right_y": 0.0, "lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0, "lower_right_y": 1.0},
            "crop_ratio": "free",
            "audio_fade": None,
            "crop_scale": 1.0,
            "extra_type_option": 0,
            "stable": {"stable_level": 0, "matrix_path": "", "time_range": {"start": 0, "duration": 0}},
            "matting": {"flag": 0, "path": "", "interactiveTime": [], "has_use_quick_brush": False, "strokes": [], "has_use_quick_eraser": False, "expansion": 0, "feather": 0, "reverse": False, "custom_matting_id": "", "enable_matting_stroke": False},
            "source": 0,
            "source_platform": 0,
            "formula_id": "",
            "check_flag": 62978047,
            "video_algorithm": {"algorithms": [], "time_range": None, "path": "", "gameplay_configs": [], "ai_in_painting_config": [], "complement_frame_config": None, "motion_blur_config": None, "deflicker": None, "noise_reduction": None, "quality_enhance": None, "super_resolution": None, "ai_background_configs": [], "smart_complement_frame": None, "aigc_generate": None, "aigc_generate_list": [], "mouth_shape_driver": None, "ai_expression_driven": None, "ai_motion_driven": None, "image_interpretation": None, "story_video_modify_video_config": {"task_id": "", "is_overwrite_last_video": False, "tracker_task_id": ""}, "skip_algorithm_index": []},
            "is_unified_beauty_mode": False,
            "object_locked": None,
            "picture_from": "none",
            "picture_set_category_id": "",
            "picture_set_category_name": "",
            "team_id": "",
            "local_material_id": "",
            "origin_material_id": "",
            "request_id": "",
            "has_sound_separated": False,
            "is_text_edit_overdub": False,
            "is_ai_generate_content": False,
            "aigc_type": "none",
            "is_copyright": False,
            "live_photo_timestamp": -1,
            "live_photo_cover_path": "",
        })

    # Vocal Isolated Audio (from AI Vocal Separation)
    vocal_mats = []
    if vocal_path and os.path.exists(vocal_path):
        vocal_mat_id = str(uuid.uuid4()).upper()
        vocal_track_id = str(uuid.uuid4()).upper()
        vocal_name = os.path.basename(vocal_path)
        vocal_volume = volume  # Uses user's configured volume

        vocal_dur, _, _ = get_duration(vocal_path)
        vocal_dur = vocal_dur or real_duration
        vocal_dur_us = int(vocal_dur * 1e6)

        vocal_spid = str(uuid.uuid4()).upper()
        vocal_phid = str(uuid.uuid4()).upper()
        vocal_scid = str(uuid.uuid4()).upper()

        speeds.append({"id": vocal_spid, "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None})
        phs.append({"id": vocal_phid, "type": "placeholder_info", "meta_type": "none", "res_path": "", "res_text": "", "error_path": "", "error_text": ""})
        scs.append({"id": vocal_scid, "type": "none", "audio_channel_mapping": 0, "is_config_open": False})

        vocal_segs = []
        timeline_pos = 0
        while timeline_pos < duration_us:
            seg_dur = min(vocal_dur_us, duration_us - timeline_pos)
            vocal_segs.append({
                "id": str(uuid.uuid4()).upper(),
                "source_timerange": {"start": 0, "duration": seg_dur},
                "target_timerange": {"start": timeline_pos, "duration": seg_dur},
                "render_timerange": {"start": 0, "duration": 0},
                "desc": "",
                "state": 0,
                "speed": 1.0,
                "is_loop": False,
                "is_tone_modify": False,
                "reverse": False,
                "intensifies_audio": False,
                "cartoon": False,
                "volume": vocal_volume,
                "last_nonzero_volume": vocal_volume,
                "clip": None,
                "uniform_scale": None,
                "material_id": vocal_mat_id,
                "extra_material_refs": [vocal_spid, vocal_phid, vocal_scid],
                "render_index": 0,
                "keyframe_refs": [],
                "enable_lut": False,
                "enable_adjust": False,
                "enable_hsl": False,
                "visible": True,
                "group_id": "",
                "enable_color_curves": True,
                "enable_hsl_curves": True,
                "track_render_index": 0,
                "hdr_settings": None,
                "enable_color_wheels": True,
                "track_attribute": 0,
                "is_placeholder": False,
                "template_id": "",
                "template_scene": "default",
                "common_keyframes": [],
                "caption_info": None,
                "source": "segmentsourcenormal",
                "enable_mask_stroke": False,
                "enable_mask_shadow": False,
                "enable_color_adjust_pro": False,
            })
            timeline_pos += seg_dur

        tracks.append({"id": vocal_track_id, "type": "audio", "segments": vocal_segs, "flag": 0, "attribute": 0, "name": "Vocal Track", "is_default_name": False})
        vocal_mats.append({
            "id": vocal_mat_id,
            "unique_id": "",
            "type": "extract_music",
            "name": vocal_name,
            "duration": vocal_dur_us,
            "path": vocal_path.replace("\\", "/"),
            "category_name": "local",
            "wave_points": [],
            "music_id": "",
            "app_id": 0,
            "text_id": "",
            "tone_type": "",
            "source_platform": 0,
            "video_id": "",
            "effect_id": "",
            "resource_id": "",
            "third_resource_id": "",
            "category_id": "",
            "intensifies_path": "",
            "formula_id": "",
            "check_flag": 1,
            "team_id": "",
            "local_material_id": "",
            "tone_speaker": "",
        })

    # BGM Audio
    bgm_mats = []
    if bgm_path and os.path.exists(bgm_path):
        bgm_mat_id = str(uuid.uuid4()).upper()
        bgm_track_id = str(uuid.uuid4()).upper()
        bgm_name = os.path.basename(bgm_path)
        bgm_volume = db_to_volume(bgm_db)

        bgm_dur, _, _ = get_duration(bgm_path)
        bgm_dur = bgm_dur or duration
        bgm_dur_us = int(bgm_dur * 1e6)

        bgm_spid = str(uuid.uuid4()).upper()
        bgm_phid = str(uuid.uuid4()).upper()
        bgm_scid = str(uuid.uuid4()).upper()

        speeds.append({"id": bgm_spid, "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None})
        phs.append({"id": bgm_phid, "type": "placeholder_info", "meta_type": "none", "res_path": "", "res_text": "", "error_path": "", "error_text": ""})
        scs.append({"id": bgm_scid, "type": "none", "audio_channel_mapping": 0, "is_config_open": False})

        bgm_segs = []
        timeline_pos = 0
        while timeline_pos < duration_us:
            seg_dur = min(bgm_dur_us, duration_us - timeline_pos)
            bgm_segs.append({
                "id": str(uuid.uuid4()).upper(),
                "source_timerange": {"start": 0, "duration": seg_dur},
                "target_timerange": {"start": timeline_pos, "duration": seg_dur},
                "render_timerange": {"start": 0, "duration": 0},
                "desc": "",
                "state": 0,
                "speed": 1.0,
                "is_loop": False,
                "is_tone_modify": False,
                "reverse": False,
                "intensifies_audio": False,
                "cartoon": False,
                "volume": bgm_volume,
                "last_nonzero_volume": bgm_volume,
                "clip": None,
                "uniform_scale": None,
                "material_id": bgm_mat_id,
                "extra_material_refs": [bgm_spid, bgm_phid, bgm_scid],
                "render_index": 0,
                "keyframe_refs": [],
                "enable_lut": False,
                "enable_adjust": False,
                "enable_hsl": False,
                "visible": True,
                "group_id": "",
                "enable_color_curves": True,
                "enable_hsl_curves": True,
                "track_render_index": 0,
                "hdr_settings": None,
                "enable_color_wheels": True,
                "track_attribute": 0,
                "is_placeholder": False,
                "template_id": "",
                "template_scene": "default",
                "common_keyframes": [],
                "caption_info": None,
                "source": "segmentsourcenormal",
                "enable_mask_stroke": False,
                "enable_mask_shadow": False,
                "enable_color_adjust_pro": False,
            })
            timeline_pos += seg_dur

        tracks.append({"id": bgm_track_id, "type": "audio", "segments": bgm_segs, "flag": 0, "attribute": 0, "name": "", "is_default_name": True})
        bgm_mats.append({
            "id": bgm_mat_id,
            "unique_id": "",
            "type": "extract_music",
            "name": bgm_name,
            "duration": bgm_dur_us,
            "path": bgm_path.replace("\\", "/"),
            "category_name": "local",
            "wave_points": [],
            "music_id": "",
            "app_id": 0,
            "text_id": "",
            "tone_type": "",
            "source_platform": 0,
            "video_id": "",
            "effect_id": "",
            "resource_id": "",
            "third_resource_id": "",
            "category_id": "",
            "intensifies_path": "",
            "formula_id": "",
            "check_flag": 1,
            "team_id": "",
            "local_material_id": "",
            "tone_speaker": "",
            "mock_tone_speaker": "",
            "tone_effect_id": "",
            "tone_effect_name": "",
            "tone_platform": "",
            "cloned_model_type": "",
            "tone_category_id": "",
            "tone_category_name": "",
            "request_id": "",
            "query": "",
            "search_id": "",
            "is_text_edit_overdub": False,
            "is_ugc": False,
            "is_ai_clone_tone": False,
            "is_ai_clone_tone_post": False,
            "source_from": "",
            "copyright_limit_type": "none",
            "aigc_history_id": "",
            "aigc_item_id": "",
            "music_source": "",
            "pgc_id": "",
            "pgc_name": "",
            "similiar_music_info": {"original_song_id": "", "original_song_name": ""},
            "ai_music_type": 0,
            "ai_music_enter_from": "",
            "lyric_type": 0,
            "tts_task_id": "",
            "tts_generate_scene": "",
            "ai_music_generate_scene": 0,
            "tts_benefit_info": {"benefit_type": "none", "benefit_log_id": "", "benefit_log_extra": "", "benefit_amount": -1},
        })

    # Assemble complete draft_content dictionary
    draft_content = {
        "id": str(uuid.uuid4()).upper(),
        "version": 360000,
        "new_version": "163.0.0",
        "name": "",
        "duration": duration_us,
        "create_time": 0,
        "update_time": 0,
        "fps": 30.0,
        "is_drop_frame_timecode": False,
        "color_space": 0,
        "config": {
            "video_mute": False,
            "record_audio_last_index": 1,
            "extract_audio_last_index": 1,
            "original_sound_last_index": 1,
            "subtitle_recognition_id": "",
            "subtitle_taskinfo": [],
            "lyrics_recognition_id": "",
            "lyrics_taskinfo": [],
            "subtitle_sync": True,
            "lyrics_sync": True,
            "sticker_max_index": 1,
            "adjust_max_index": 1,
            "material_save_mode": 0,
            "export_range": None,
            "maintrack_adsorb": True,
            "combination_max_index": 1,
            "attachment_info": [],
            "zoom_info_params": None,
            "system_font_list": [],
            "multi_language_mode": "none",
            "multi_language_main": "none",
            "multi_language_current": "none",
            "multi_language_list": [],
            "subtitle_keywords_config": None,
            "use_float_render": False,
        },
        "canvas_config": {"ratio": "original", "width": width, "height": height, "background": None},
        "tracks": tracks,
        "group_container": None,
        "materials": {
            "videos": [{
                "id": mat_id,
                "unique_id": "",
                "type": "video",
                "duration": int(duration * 1e6),
                "path": vp.replace("\\", "/"),
                "media_path": "",
                "local_id": "",
                "has_audio": True,
                "reverse_path": "",
                "intensifies_path": "",
                "reverse_intensifies_path": "",
                "intensifies_audio_path": "",
                "cartoon_path": "",
                "width": width,
                "height": height,
                "material_name": mat_name,
                "crop": {"upper_left_x": 0.0, "upper_left_y": 0.0, "upper_right_x": 1.0, "upper_right_y": 0.0, "lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0, "lower_right_y": 1.0},
                "crop_ratio": "free",
                "audio_fade": None,
                "crop_scale": 1.0,
                "extra_type_option": 0,
                "stable": {"stable_level": 0, "matrix_path": "", "time_range": {"start": 0, "duration": 0}},
                "matting": {"flag": 0, "path": "", "interactiveTime": [], "has_use_quick_brush": False, "strokes": [], "has_use_quick_eraser": False, "expansion": 0, "feather": 0, "reverse": False, "custom_matting_id": "", "enable_matting_stroke": False},
                "source": 0,
                "source_platform": 0,
                "formula_id": "",
                "check_flag": 62978047,
                "video_algorithm": {"algorithms": [], "time_range": None, "path": "", "gameplay_configs": [], "ai_in_painting_config": [], "complement_frame_config": None, "motion_blur_config": None, "deflicker": None, "noise_reduction": None, "quality_enhance": None, "super_resolution": None, "ai_background_configs": [], "smart_complement_frame": None, "aigc_generate": None, "aigc_generate_list": [], "mouth_shape_driver": None, "ai_expression_driven": None, "ai_motion_driven": None, "image_interpretation": None, "story_video_modify_video_config": {"task_id": "", "is_overwrite_last_video": False, "tracker_task_id": ""}, "skip_algorithm_index": []},
                "is_unified_beauty_mode": False,
                "object_locked": None,
                "picture_from": "none",
                "picture_set_category_id": "",
                "picture_set_category_name": "",
                "team_id": "",
                "local_material_id": "",
                "origin_material_id": "",
                "request_id": "",
                "has_sound_separated": False,
                "is_text_edit_overdub": False,
                "is_ai_generate_content": False,
                "aigc_type": "none",
                "is_copyright": False,
                "live_photo_timestamp": -1,
                "live_photo_cover_path": "",
            }] + overlay_mats,
            "video_effects": video_effects,
            "flowers": [],
            "tail_leaders": [],
            "audios": vocal_mats + bgm_mats,
            "images": [],
            "texts": [],
            "effects": color_effects_list,
            "stickers": [],
            "transitions": [],
            "audio_effects": audio_effects,
            "audio_fades": [],
            "beats": [],
            "material_animations": [],
            "placeholders": phs,
            "placeholder_infos": [],
            "speeds": speeds,
            "canvases": canvases,
            "common_mask": [],
            "chromas": chromas_list,
            "text_templates": [],
            "realtime_denoises": [],
            "audio_pannings": [],
            "audio_pitch_shifts": [],
            "video_trackings": [],
            "hsl": [],
            "drafts": [],
            "color_curves": [],
            "hsl_curves": [],
            "primary_color_wheels": [],
            "log_color_wheels": [],
            "audio_balances": [],
            "handwrites": [],
            "manual_deformations": [],
            "shapes": [],
            "sound_channel_mappings": scs,
            "green_screens": [],
            "material_colors": mcs,
            "vocal_separations": vss,
            "smart_crops": [],
            "ai_translates": [],
            "audio_track_indexes": [],
            "loudnesses": [],
            "vocal_beautifys": [],
        },
        "keyframes": {"videos": [], "audios": [], "texts": [], "stickers": [], "filters": [], "adjusts": [], "handwrites": [], "effects": []},
        "keyframe_graph_list": [],
        "platform": {"os": "windows", "os_version": "10.0.19045", "app_id": 359289, "app_version": "8.3.0", "app_source": "cc", "device_id": "", "hard_disk_id": "", "mac_address": ""},
        "last_modified_platform": {"os": "windows", "os_version": "10.0.19045", "app_id": 359289, "app_version": "8.3.0", "app_source": "cc", "device_id": "", "hard_disk_id": "", "mac_address": ""},
        "mutable_config": None,
        "cover": None,
        "retouch_cover": None,
        "extra_info": None,
        "relationships": [],
        "render_index_track_mode_on": True,
        "free_render_index_mode_on": False,
        "static_cover_image_path": "",
        "source": "default",
        "draft_type": "video",
    }

    return draft_content, None, None


def save_local_capcut_draft(
    vp: str,
    draft_content: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Saves draft_content and draft_meta_info to CapCut PC directory.
    Returns: (draft_name, draft_dir)
    """
    video_stem = os.path.splitext(os.path.basename(vp))[0]
    video_stem = re.sub(r'[\\/:*?"<>|]', '_', video_stem)[:80]
    draft_name = video_stem
    base_name = draft_name
    counter = 1

    os.makedirs(CAPCUT_DIR, exist_ok=True)
    while os.path.exists(os.path.join(CAPCUT_DIR, draft_name)):
        draft_name = f"{base_name}_{counter}"
        counter += 1

    draft_dir = os.path.join(CAPCUT_DIR, draft_name)
    os.makedirs(draft_dir, exist_ok=True)

    with open(os.path.join(draft_dir, "draft_content.json"), "w", encoding="utf-8") as f:
        json.dump(draft_content, f, ensure_ascii=False)

    duration_us = draft_content.get("duration", 0)
    duration_s = duration_us / 1e6
    width = draft_content.get("canvas_config", {}).get("width", 1920)
    height = draft_content.get("canvas_config", {}).get("height", 1080)
    now_us = int(time.time() * 1e6)
    mat_name = os.path.basename(vp)

    meta = {
        "draft_cover": "draft_cover.jpg",
        "draft_fold_path": draft_dir.replace("\\", "/"),
        "draft_id": str(uuid.uuid4()).upper(),
        "draft_is_ae_produce": False,
        "draft_is_ai_shorts": False,
        "draft_is_invisible": False,
        "draft_materials": [
            {
                "type": 0,
                "value": [{
                    "create_time": int(time.time()),
                    "duration": duration_us,
                    "extra_info": mat_name,
                    "file_Path": vp.replace("\\", "/"),
                    "height": height,
                    "id": str(uuid.uuid4()),
                    "import_time": int(time.time()),
                    "import_time_ms": now_us,
                    "item_source": 1,
                    "md5": "",
                    "metetype": "video",
                    "roughcut_time_range": {"duration": duration_us, "start": 0},
                    "sub_time_range": {"duration": -1, "start": -1},
                    "type": 0,
                    "width": width,
                }]
            },
            {"type": 1, "value": []},
            {"type": 2, "value": []},
            {"type": 3, "value": []},
            {"type": 6, "value": []},
            {"type": 7, "value": []},
            {"type": 8, "value": []},
        ],
        "draft_materials_copied_info": [],
        "draft_name": draft_name,
        "draft_need_rename_folder": False,
        "draft_root_path": CAPCUT_DIR.replace("\\", "/"),
        "draft_segment_extra_info": [],
        "draft_timeline_materials_size_": 0,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_draft_removed": 0,
        "tm_duration": duration_us,
        "cloud_draft_sync": False,
        "draft_cloud_last_action_download": False,
    }

    with open(os.path.join(draft_dir, "draft_meta_info.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    return draft_name, draft_dir


def render_draft_cloud(
    vp: str,
    draft_content: Dict[str, Any],
    output_mp4: str,
    overlay_path: str = "",
    bgm_path: str = "",
    vocal_path: str = "",
    definition: str = "1080p",
    fps: int = 30,
    auto_caption: bool = False,
    caption_language: str = "vi-VN",
    caption_style: str = "TikTok Viral (Vàng viền đen)",
    compress_crf: bool = False,
    crf: int = 24,
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> str:
    """
    Renders draft_content on CapCut Cloud without opening CapCut PC.
    1. Uploads primary video, overlay video, isolated vocal audio, and BGM to CapCut TOS VOD.
    2. Maps local file paths in draft_content to cloud virtual paths (/<md5>.mp4, /<md5>.wav).
    3. If auto_caption enabled, recognizes speech via CapCut Cloud ASR and injects subtitles with style.
    4. Saves Cloud Draft via CapCut Web API.
    5. Triggers Cloud Render task and polls until MP4 download completes.
    """
    def log(msg: str):
        now_str = time.strftime("[%H:%M:%S]")
        formatted = msg if (msg.startswith("[") and len(msg) >= 10 and msg[3] == ":" and msg[6] == ":") else f"{now_str} {msg}"
        if log_cb:
            log_cb(formatted)
        else:
            print(formatted, flush=True)

    t_render_start = time.time()
    from core.auth import CapCutAuth
    from core.uploader import CapCutUploader
    from core.cloud_draft import CapCutCloudDraft
    from core.render_client import CapCutRender

    auth = CapCutAuth()
    if not auth.user_id:
        if not auth.sync_all():
            raise RuntimeError("Phiên CapCut chưa xác thực hoặc hết hạn.")

    uploader = CapCutUploader(auth)
    draft_mgr = CapCutCloudDraft(auth)
    renderer = CapCutRender(auth)

    out_path = Path(output_mp4).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Upload assets
    uploaded_assets = []
    local_path_to_md5 = {}

    log("[BƯỚC 1/4] Đang tải video chính lên CapCut Cloud Storage (TOS/VOD)...")
    if progress_cb:
        progress_cb(10, "Đang tải video chính lên Cloud...")
    main_asset = uploader.upload(vp)
    uploaded_assets.append(main_asset)
    v_path_main = f"/{main_asset['md5']}.mp4"
    local_path_to_md5[v_path_main] = main_asset["md5"]
    log(f"[+] Video chính đã tải lên: MD5={main_asset['md5']}")

    # Overlay upload if present
    if overlay_path and os.path.isfile(overlay_path):
        log("[BƯỚC 1/4] Đang tải video lớp phủ (Overlay) lên Cloud...")
        if progress_cb:
            progress_cb(20, "Đang tải video lớp phủ lên Cloud...")
        ov_asset = uploader.upload(overlay_path)
        uploaded_assets.append(ov_asset)
        v_path_ov = f"/{ov_asset['md5']}.mp4"
        local_path_to_md5[v_path_ov] = ov_asset["md5"]

        # Patch overlay path in materials
        for vmat in draft_content.get("materials", {}).get("videos", []):
            if vmat.get("path") == overlay_path.replace("\\", "/"):
                vmat["path"] = v_path_ov
                vmat["version"] = 400000
                vmat["new_version"] = "127.0.0"

    # Vocal isolated audio upload if present
    if vocal_path and os.path.isfile(vocal_path):
        log("[BƯỚC 1/4] Đang tải audio giọng nói đã tách (Vocal) lên Cloud...")
        if progress_cb:
            progress_cb(25, "Đang tải audio vocal lên Cloud...")
        vocal_asset = uploader.upload(vocal_path, file_type="audio")
        uploaded_assets.append(vocal_asset)
        v_path_vocal = f"/{vocal_asset['md5']}.wav"
        local_path_to_md5[v_path_vocal] = vocal_asset["md5"]

        for amat in draft_content.get("materials", {}).get("audios", []):
            if amat.get("path") == vocal_path.replace("\\", "/"):
                amat["path"] = v_path_vocal

    # BGM upload if present
    if bgm_path and os.path.isfile(bgm_path):
        log("[BƯỚC 1/4] Đang tải nhạc nền (BGM) lên Cloud...")
        if progress_cb:
            progress_cb(28, "Đang tải nhạc nền lên Cloud...")
        bgm_asset = uploader.upload(bgm_path, file_type="audio")
        uploaded_assets.append(bgm_asset)
        v_path_bgm = f"/{bgm_asset['md5']}.mp3"
        local_path_to_md5[v_path_bgm] = bgm_asset["md5"]

        for amat in draft_content.get("materials", {}).get("audios", []):
            if amat.get("path") == bgm_path.replace("\\", "/"):
                amat["path"] = v_path_bgm

    # Patch primary video path in draft_content
    if draft_content.get("materials", {}).get("videos"):
        draft_content["materials"]["videos"][0]["path"] = v_path_main
        draft_content["materials"]["videos"][0]["version"] = 400000
        draft_content["materials"]["videos"][0]["new_version"] = "127.0.0"

    # 1.5 Auto-caption recognition & injection if enabled
    if auto_caption:
        log(f"[BƯỚC 1.5/4] Đang gửi âm thanh lên CapCut Cloud AI nhận dạng phụ đề ({caption_language})...")
        if progress_cb:
            progress_cb(35, f"Đang nhận diện giọng nói ({caption_language})...")
        try:
            from core.auto_caption import CapCutAutoCaption
            captioner = CapCutAutoCaption()
            utterances = captioner.transcribe(vp, language=caption_language, log_cb=log)
            if utterances:
                draft_content = captioner.inject_subtitles_to_draft(
                    draft_content, utterances, style_name=caption_style
                )
                log(f"[+] Đã gắn {len(utterances)} đoạn phụ đề (Style: {caption_style}) vào timeline thành công.")
            else:
                log("[i] Không phát hiện giọng nói trong video (bỏ qua gắn phụ đề).")
        except Exception as c_err:
            log(f"[!] Cảnh báo: Nhận diện phụ đề gặp sự cố ({c_err}), tiếp tục render video...")

    # 2. Save Cloud Draft
    log("[BƯỚC 2/4] Đang lưu trữ Cloud Draft lên CapCut Workspace...")
    if progress_cb:
        progress_cb(40, "Đang đồng bộ Cloud Draft...")
    draft_id = str(uuid.uuid4()).upper()
    draft_title = f"Render_{Path(vp).stem}"

    draft_id, package_id = draft_mgr.save_draft(
        draft_content=draft_content,
        uploaded_assets=uploaded_assets,
        draft_id=draft_id,
        draft_title=draft_title,
    )
    log(f"[+] Đã lưu Cloud Draft thành công. Package ID: {package_id}")

    # 3. Create Cloud Render Task
    log(f"[BƯỚC 3/4] Khởi tạo Cloud Render Task ({definition} @ {fps}fps)...")
    if progress_cb:
        progress_cb(50, "Khởi tạo Render Task...")

    duration_us = draft_content.get("duration", main_asset.get("duration_us", 0))
    duration_s = duration_us / 1e6
    log(f"[*] Thời lượng video: {duration_s/60:.1f} phút ({duration_s:.1f}s)")

    task_id = renderer.create_render_task(
        draft_id=draft_id,
        package_id=package_id,
        video_name=out_path.name,
        duration_us=duration_us,
        fps=fps,
        definition=definition,
        local_path_to_md5=local_path_to_md5,
    )
    log(f"[+] Task Render đã sẵn sàng trên Cloud: {task_id}")

    # 4. Polling & Download
    log("[BƯỚC 4/4] Giám sát tiến độ Render và tự động tải file MP4...")

    def render_progress_cb(p: int, status_str: str):
        mapped_pct = 50 + int(p * 0.48)
        if progress_cb:
            progress_cb(mapped_pct, f"Đang render trên Cloud: {p}%")
        log(f"[*] Tiến độ Render: {p}% (Trạng thái: {status_str})")

    downloaded = renderer.wait_and_download(
        task_id=task_id,
        output_path=str(out_path),
        poll_interval_sec=3.0,
        timeout_sec=900.0,
        progress_cb=render_progress_cb,
    )

    if compress_crf and os.path.exists(downloaded):
        from core.chunk_engine import compress_video_crf
        if progress_cb:
            progress_cb(96, f"Đang nén tối ưu dung lượng (CRF {crf})...")
        downloaded = compress_video_crf(downloaded, crf=crf, log_cb=log, progress_cb=progress_cb)

    elapsed_render = time.time() - t_render_start
    m, s = divmod(int(elapsed_render), 60)
    h, m = divmod(m, 60)
    t_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    if progress_cb:
        progress_cb(100, f"Hoàn tất trong {t_str}! File video đã được tải về máy.")
    log(f"[+] HOÀN THÀNH XUẤT VIDEO trong {t_str} ({elapsed_render:.1f}s): {downloaded}")
    return downloaded


def render_video_auto_chunked_cloud(
    vp: str,
    draft_params: Dict[str, Any],
    output_mp4: str,
    chunk_duration: int = 1200,
    max_chunk_workers: int = 2,
    definition: str = "1080p",
    fps: int = 30,
    auto_caption: bool = False,
    caption_language: str = "vi-VN",
    caption_style: str = "TikTok Viral (Vàng viền đen)",
    compress_crf: bool = False,
    crf: int = 24,
    log_cb: Optional[Callable[[str], None]] = None,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> str:
    """
    Renders any video (from 1 minute up to 1h30m+) via CapCut Cloud safely.
    - If video duration <= (chunk_duration + 30): performs standard single cloud render.
    - If video duration > (chunk_duration + 30):
      1. Slices video into <= chunk_duration chunks via ffmpeg stream copy (zero re-encode).
      2. Renders each chunk in parallel via thread pool on CapCut Cloud.
      3. Seamlessly concatenates rendered chunks using ffmpeg concat demuxer.
      4. Cleans up temporary chunk files.
    """
    def log(msg: str):
        now_str = time.strftime("[%H:%M:%S]")
        formatted = msg if (msg.startswith("[") and len(msg) >= 10 and msg[3] == ":" and msg[6] == ":") else f"{now_str} {msg}"
        if log_cb:
            log_cb(formatted)
        else:
            print(formatted, flush=True)

    t_chunked_start = time.time()
    from core.chunk_engine import get_media_duration, split_video, concat_videos, cleanup_chunks
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    in_file = Path(vp).resolve()
    out_file = Path(output_mp4).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    dur = get_media_duration(str(in_file))
    log(f"[*] Phân tích video: {in_file.name} | Thời lượng: {dur:.1f}s ({dur/60:.1f} phút)")

    # 1. AI Vocal Separation if enabled (mute original audio, keep vocals)
    vocal_sep = draft_params.get("vocal_sep", False)
    vocal_full_path = None
    if vocal_sep:
        log("[BƯỚC 1/4] Kích hoạt CapCut AI Vocal Separation: Đang tách giọng nói, loại bỏ nhạc nền cũ...")
        if progress_cb:
            progress_cb(8, "Đang bóc tách giọng nói AI (Vocal Separation)...")
        try:
            from core.vocal_separator import CapCutVocalSeparator
            separator = CapCutVocalSeparator()
            vocal_full_path = separator.separate_video(
                str(in_file),
                log_cb=log,
                progress_cb=lambda p, m: progress_cb(min(25, int(p * 0.25)), m) if progress_cb else None,
            )
            log(f"[+] Tách vocal thành công: {Path(vocal_full_path).name}")
            draft_params["vocal_path"] = vocal_full_path
        except Exception as v_err:
            log(f"[!] Cảnh báo: Tách vocal AI gặp sự cố ({v_err}), tiếp tục render với âm thanh gốc...")

    full_utterances = []
    if auto_caption:
        log(f"[BƯỚC 1.5/4] Đang gửi âm thanh lên CapCut Cloud AI nhận dạng phụ đề ({caption_language})...")
        if progress_cb:
            progress_cb(26, f"Đang nhận diện giọng nói ({caption_language})...")
        try:
            from core.auto_caption import CapCutAutoCaption
            captioner = CapCutAutoCaption()
            transcribe_target = vocal_full_path if (vocal_full_path and os.path.exists(vocal_full_path)) else str(in_file)
            full_utterances = captioner.transcribe(transcribe_target, language=caption_language, log_cb=log)
            if full_utterances:
                log(f"[+] Nhận diện thành công: {len(full_utterances)} câu phụ đề thoại.")
            else:
                log("[i] Không phát hiện giọng nói trong video (bỏ qua gắn phụ đề).")
        except Exception as c_err:
            log(f"[!] Cảnh báo: Nhận diện phụ đề gặp sự cố ({c_err}), tiếp tục render video...")

    if dur <= (chunk_duration + 30):
        # Video length <= chunk limit: direct 1-task cloud render
        log(f"[*] Thời lượng video ({dur:.1f}s <= {chunk_duration+30}s). Render trực tiếp 1 task Cloud...")
        draft_content, err, _ = make_draft(vp=str(in_file), **draft_params)
        if err:
            raise RuntimeError(f"Lỗi tạo draft: {err}")
        if full_utterances:
            from core.auto_caption import CapCutAutoCaption
            draft_content = CapCutAutoCaption.inject_subtitles_to_draft(
                draft_content, full_utterances, style_name=caption_style
            )
            log(f"[+] Đã gắn {len(full_utterances)} đoạn phụ đề (Style: {caption_style}) vào timeline.")

        return render_draft_cloud(
            vp=str(in_file),
            draft_content=draft_content,
            output_mp4=str(out_file),
            overlay_path=draft_params.get("overlay_path", ""),
            bgm_path=draft_params.get("bgm_path", ""),
            vocal_path=draft_params.get("vocal_path", ""),
            definition=definition,
            fps=fps,
            auto_caption=False,
            caption_language=caption_language,
            caption_style=caption_style,
            compress_crf=compress_crf,
            crf=crf,
            log_cb=log_cb,
            progress_cb=progress_cb,
        )

    # Long video -> Auto-chunk pipeline
    chunks_temp_dir = out_file.parent / f".chunks_{in_file.stem}_{int(time.time())}"
    chunks = split_video(
        input_path=str(in_file),
        chunk_duration=chunk_duration,
        temp_dir=str(chunks_temp_dir),
        log_cb=log,
    )
    total_chunks = len(chunks)
    log(f"[+] Đã chia nhỏ video thành {total_chunks} phân đoạn (mỗi đoạn tối đa {chunk_duration}s).")
    log(f"[*] Bắt đầu render song song {total_chunks} phân đoạn với {max_chunk_workers} workers...")

    # Worker pool to render chunks
    rendered_chunk_paths = [None] * total_chunks
    completed_chunks = [0]
    lock = threading.Lock()

    def process_one_chunk(chunk_info: Dict[str, Any]) -> Tuple[int, str]:
        c_idx = chunk_info["index"]
        c_path = chunk_info["path"]
        c_out_mp4 = str(chunks_temp_dir / f"rendered_part_{c_idx:03d}.mp4")

        # Create draft specifically for this chunk (seg=0 to keep 1 clip)
        c_params = dict(draft_params)
        c_params["seg"] = 0

        # Slice vocal audio for this chunk if vocal separation was active
        if vocal_full_path and os.path.exists(vocal_full_path):
            from core.vocal_separator import slice_audio
            c_start_s = float(chunk_info.get("start", c_idx * chunk_duration))
            c_dur_s = float(chunk_info.get("duration", chunk_duration))
            c_vocal_wav = str(chunks_temp_dir / f"vocal_part_{c_idx:03d}.wav")
            slice_audio(vocal_full_path, c_start_s, c_dur_s, c_vocal_wav)
            c_params["vocal_path"] = c_vocal_wav

        c_draft, c_err, _ = make_draft(vp=c_path, **c_params)
        if c_err:
            raise RuntimeError(f"Lỗi tạo draft cho chunk {c_idx}: {c_err}")

        # Inject slice of subtitles for this chunk
        if full_utterances:
            from core.auto_caption import CapCutAutoCaption
            c_start_s = float(chunk_info.get("start", c_idx * chunk_duration))
            c_dur_s = float(chunk_info.get("duration", chunk_duration))
            c_start_ms = int(c_start_s * 1000)
            c_end_ms = int((c_start_s + c_dur_s) * 1000)
            chunk_utts = []
            for u in full_utterances:
                if u["start_ms"] >= c_start_ms and u["start_ms"] < c_end_ms:
                    chunk_utts.append({
                        "text": u["text"],
                        "start_ms": max(0, u["start_ms"] - c_start_ms),
                        "end_ms": max(0, u["end_ms"] - c_start_ms),
                        "words": u.get("words", []),
                    })
            if chunk_utts:
                c_draft = CapCutAutoCaption.inject_subtitles_to_draft(
                    c_draft, chunk_utts, style_name=caption_style
                )

        def chunk_progress_cb(p: int, s_msg: str):
            with lock:
                base_pct = int((completed_chunks[0] / total_chunks) * 90)
                cur_chunk_contrib = int((p / 100.0) * (90.0 / total_chunks))
                total_pct = min(90, base_pct + cur_chunk_contrib)
                if progress_cb:
                    progress_cb(total_pct, f"Phân đoạn [{c_idx+1}/{total_chunks}]: {s_msg}")

        log(f"[*] [Phân đoạn {c_idx+1}/{total_chunks}] Bắt đầu đẩy lên Cloud Render...")
        c_downloaded = render_draft_cloud(
            vp=c_path,
            draft_content=c_draft,
            output_mp4=c_out_mp4,
            overlay_path=draft_params.get("overlay_path", ""),
            bgm_path=draft_params.get("bgm_path", ""),
            vocal_path=c_params.get("vocal_path", ""),
            definition=definition,
            fps=fps,
            log_cb=lambda m: log(f"[{c_idx+1}/{total_chunks}] {m}"),
            progress_cb=chunk_progress_cb,
        )

        with lock:
            completed_chunks[0] += 1
            pct = int((completed_chunks[0] / total_chunks) * 90)
            log(f"[+] [Phân đoạn {c_idx+1}/{total_chunks}] Render hoàn thành: {Path(c_downloaded).name}")
            if progress_cb:
                progress_cb(pct, f"Đã hoàn thành {completed_chunks[0]}/{total_chunks} phân đoạn")

        return c_idx, c_downloaded

    # Run in ThreadPoolExecutor
    n_workers = min(max_chunk_workers, total_chunks)
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        future_map = {executor.submit(process_one_chunk, ch): ch["index"] for ch in chunks}
        for fut in as_completed(future_map):
            c_idx = future_map[fut]
            try:
                ret_idx, ret_path = fut.result()
                rendered_chunk_paths[ret_idx] = ret_path
            except Exception as e:
                log(f"[!] Lỗi render ở phân đoạn {c_idx+1}: {e}")
                raise e

    # Check that all chunks rendered
    if any(p is None for p in rendered_chunk_paths):
        missing = [i for i, p in enumerate(rendered_chunk_paths) if p is None]
        raise RuntimeError(f"Thiếu các phân đoạn render: {missing}")

    # Concat all chunks
    log(f"[*] Ghép nối liền mạch {total_chunks} phân đoạn thành video hoàn chỉnh...")
    if progress_cb:
        progress_cb(95, "Đang ghép nối các phân đoạn (FFmpeg Concat Stream Copy)...")

    final_mp4 = concat_videos(rendered_chunk_paths, str(out_file), log_cb=log)

    # Clean up temp chunks
    log(f"[*] Dọn dẹp dữ liệu tạm thời: {chunks_temp_dir.name}...")
    cleanup_chunks(str(chunks_temp_dir))

    # Optional fast CRF compression if user requested storage optimization
    if compress_crf and os.path.exists(final_mp4):
        from core.chunk_engine import compress_video_crf
        if progress_cb:
            progress_cb(96, f"Đang nén tối ưu dung lượng (CRF {crf})...")
        final_mp4 = compress_video_crf(final_mp4, crf=crf, log_cb=log, progress_cb=progress_cb)

    elapsed_total = time.time() - t_chunked_start
    m, s = divmod(int(elapsed_total), 60)
    h, m = divmod(m, 60)
    t_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    if progress_cb:
        progress_cb(100, f"Hoàn tất xuất video hoàn chỉnh trong {t_str}!")
    log(f"[+] HOÀN THÀNH TOÀN BỘ VIDEO ({dur/60:.1f} phút) trong {t_str} ({elapsed_total:.1f}s): {final_mp4}")
    return final_mp4

