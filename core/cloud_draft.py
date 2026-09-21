#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_cloud_draft.py - CapCut Web Cloud Draft Manager & Effect Adapter
Transforms local draft structures (draft_content.json) into CapCut Cloud drafts,
attaches effects/filters/subtitles, and saves them to the cloud editor.
"""

import os
import sys
import time
import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

sys.stdout.reconfigure(encoding="utf-8")

from core.auth import CapCutAuth

class CapCutCloudDraft:
    """Creates, adapts, and saves video drafts to CapCut Web cloud."""

    def __init__(self, auth: Optional[CapCutAuth] = None):
        self.auth = auth or CapCutAuth()
        if not self.auth.user_id:
            if not self.auth.sync_all():
                raise RuntimeError("CapCut session not authenticated.")

    # --------------------------------------------------------------------------
    # Effect Catalog Queries
    # --------------------------------------------------------------------------
    def query_effect_panels(self) -> Dict[str, Any]:
        """Fetch effect panels (video_effects, stickers, filters, text_effects)."""
        url = f"https://edit-api-sg.capcut.com/artist/v1/panel/get_panel_info?aid={self.auth.aid}&version_name={self.auth.appvr}&device_platform={self.auth.pf}"
        return self.auth._request("POST", url, {
            "app_id": int(self.auth.aid),
            "panel": "video_web",
            "get_res_category_count": 20,
            "resource_count": 20,
            "get_resource": True,
            "only_commercial": False,
        })

    def get_effects_by_category(self, category_id: int, panel: str = "video") -> List[Dict[str, Any]]:
        """Fetch effect list by category ID."""
        url = f"https://edit-api-sg.capcut.com/artist/v1/effect/get_resources_by_category_id?aid={self.auth.aid}&version_name={self.auth.appvr}&device_platform={self.auth.pf}"
        res = self.auth._request("POST", url, {
            "panel": panel,
            "category_id": category_id,
            "pack_optional": {"need_thumb": True}
        })
        return res.get("data", {}).get("effects", [])

    # --------------------------------------------------------------------------
    # Draft Construction
    # --------------------------------------------------------------------------
    @staticmethod
    def create_simple_draft(
        video_meta: Dict[str, Any],
        effect_info: Optional[Dict[str, Any]] = None,
        canvas_width: int = 1920,
        canvas_height: int = 1080,
        fps: float = 30.0,
    ) -> Dict[str, Any]:
        """
        Build a valid CapCut draft structure matching the golden cloud schema.
        Uses real_draft_content.json as base template when available.
        """
        duration_us = video_meta["duration_us"]
        virtual_path = video_meta.get("virtual_path") or f"/{video_meta.get('md5', '')}.mp4"
        template_file = Path(__file__).parent / "real_draft_content.json"

        if template_file.is_file():
            with open(template_file, "r", encoding="utf-8") as f:
                draft_content = json.load(f)

            new_draft_id = str(uuid.uuid4()).upper()
            draft_content["id"] = new_draft_id
            draft_content["duration"] = duration_us
            draft_content["fps"] = int(fps)
            if "canvas_config" in draft_content:
                draft_content["canvas_config"]["width"] = canvas_width
                draft_content["canvas_config"]["height"] = canvas_height

            v0 = draft_content["materials"]["videos"][0]
            v0_id = str(uuid.uuid4()).upper()
            v0["id"] = v0_id
            v0["path"] = virtual_path
            v0["duration"] = duration_us
            v0["width"] = video_meta.get("width", canvas_width)
            v0["height"] = video_meta.get("height", canvas_height)
            v0["material_name"] = video_meta.get("file_name", "video.mp4")

            seg0 = draft_content["tracks"][0]["segments"][0]
            seg0["material_id"] = v0_id
            seg0["source_timerange"] = {"duration": duration_us, "start": 0}
            seg0["target_timerange"] = {"duration": duration_us, "start": 0}

            if effect_info:
                eff_id = str(uuid.uuid4()).upper()
                draft_content["materials"]["effects"].append({
                    "id": eff_id,
                    "resource_id": str(effect_info.get("resource_id", effect_info.get("id", ""))),
                    "third_resource_id": str(effect_info.get("resource_id", effect_info.get("id", ""))),
                    "name": effect_info.get("name", "Video Effect"),
                    "type": effect_info.get("type", "video_effect"),
                    "sub_type": "none",
                    "path": effect_info.get("path", ""),
                    "adjust_params": effect_info.get("adjust_params", []),
                })
                if "extra_material_refs" in seg0:
                    seg0["extra_material_refs"].append(eff_id)

            return draft_content

        # Fallback standard structure
        video_material_id = str(uuid.uuid4())
        video_segment_id = str(uuid.uuid4())
        video_track_id = str(uuid.uuid4())

        draft_content = {
            "canvas_config": {"height": canvas_height, "width": canvas_width, "ratio": "original"},
            "duration": duration_us,
            "fps": fps,
            "materials": {
                "videos": [
                    {
                        "id": video_material_id,
                        "duration": duration_us,
                        "height": video_meta.get("height", canvas_height),
                        "width": video_meta.get("width", canvas_width),
                        "material_name": video_meta.get("file_name", "video.mp4"),
                        "path": virtual_path,
                        "type": "video",
                        "version": 400000,
                        "new_version": "127.0.0",
                        "crop": {"lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0, "lower_right_y": 1.0, "upper_left_x": 0.0, "upper_left_y": 0.0, "upper_right_x": 1.0, "upper_right_y": 0.0},
                    }
                ],
                "audios": [],
                "effects": [],
                "speeds": [
                    {"curve_speed": None, "id": str(uuid.uuid4()), "mode": 0, "speed": 1.0, "type": "speed"}
                ],
                "transitions": [],
                "canvases": [],
                "sound_channel_mappings": [],
                "placeholders": [],
            },
            "tracks": [
                {
                    "id": video_track_id,
                    "type": "video",
                    "segments": [
                        {
                            "id": video_segment_id,
                            "material_id": video_material_id,
                            "source_timerange": {"duration": duration_us, "start": 0},
                            "target_timerange": {"duration": duration_us, "start": 0},
                            "speed": 1.0,
                            "volume": 1.0,
                            "render_index": 0,
                            "clip": {
                                "alpha": 1.0,
                                "flip": {"horizontal": False, "vertical": False},
                                "rotation": 0.0,
                                "scale": {"x": 1.0, "y": 1.0},
                                "transform": {"x": 0.0, "y": 0.0},
                            },
                        }
                    ],
                }
            ],
        }
        return draft_content

    # --------------------------------------------------------------------------
    # Save Cloud Draft API (/lv/v1/editor/video_draft/save)
    # --------------------------------------------------------------------------
    def save_draft(
        self,
        draft_content: Dict[str, Any],
        uploaded_assets: List[Dict[str, Any]],
        draft_id: Optional[str] = None,
        draft_title: str = "Cloud Draft",
    ) -> Tuple[str, str]:
        """
        Save draft to CapCut Web Cloud Editor.
        Returns: (draft_id, package_id)
        """
        url = "https://edit-api-sg.capcut.com/lv/v1/editor/video_draft/save"
        draft_key = draft_id or str(uuid.uuid4()).upper()
        draft_json_str = json.dumps(draft_content, ensure_ascii=False)
        now_ms = int(time.time() * 1000)

        package_assets = []
        total_assets_size = 0
        for asset in uploaded_assets:
            sz = asset.get("size", 0)
            md5 = asset.get("md5", "")
            vpath = asset.get("virtual_path") or f"/{md5}.mp4"
            total_assets_size += sz
            package_assets.append({
                "md5": md5,
                "source_path": vpath,
                "size": sz,
                "meta": json.dumps({"visible": True}),
            })

        def _make_source():
            return {
                "owner": str(self.auth.user_id),
                "platform": "browser",
                "systemVersion": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "appVersion": "15.4.0",
                "createTime": now_ms,
                "commitId": str(uuid.uuid4()),
            }

        cloud_meta = {
            "uploadSource": _make_source(),
            "createSource": _make_source(),
            "draft": {
                "id": draft_key,
                "name": draft_title,
                "type": 0,
                "duration": draft_content.get("duration", 0),
                "updateTime": now_ms,
                "size": total_assets_size + len(draft_json_str),
                "version": "127.0.0",
                "platformSupport": "browser",
                "isMainTrackEmpty": False,
                "isScriptTemplate": False,
                "isBusiness": False,
                "itemType": 0,
                "renderIndexTrackMode": False,
                "createScenario": "youtube_ads",
                "transferedFrom": 0,
            }
        }

        payload = {
            "workspace_id": str(self.auth.workspace_id),
            "package_type": 2,
            "package_key": draft_key,
            "base_package_id": "0",
            "template_data": draft_json_str,
            "template_meta": json.dumps(cloud_meta, ensure_ascii=False),
            "is_cover_change": False,
            "cover_image_content": "",
            "package_assets": package_assets,
            "render_mutable_list": [],
            "render_segment_list": [],
            "device_id": str(self.auth.device_id),
        }

        extra_headers = {
            "appvr": "8.4.0",
            "origin": "https://www.capcut.com",
            "referer": "https://www.capcut.com/",
        }

        print(f"[*] Saving draft '{draft_key}' to CapCut Cloud Editor (/lv/v1/editor/video_draft/save)...")
        res = self.auth._request("POST", url, payload, extra_headers=extra_headers, timeout=120, retries=3)

        if res.get("ret") != "0":
            raise RuntimeError(f"Save draft failed: {res}")

        data = res.get("data", {})
        package_id = data.get("package_id") or ""
        print(f"[+] Cloud Draft SAVED: DraftKey={draft_key}, PackageID={package_id}")
        return draft_key, package_id


def main():
    import argparse
    from capcut_uploader import CapCutUploader

    parser = argparse.ArgumentParser(description="CapCut Cloud Draft Creator")
    parser.add_argument("file", type=str, help="Path to video to create draft with")
    parser.add_argument("--title", type=str, default="Demo Cloud Draft", help="Draft title")
    args = parser.parse_args()

    auth = CapCutAuth()
    uploader = CapCutUploader(auth)
    asset = uploader.upload(args.file)

    draft_mgr = CapCutCloudDraft(auth)
    draft_content = draft_mgr.create_simple_draft(asset)
    draft_id, pkg_id = draft_mgr.save_draft(draft_content, [asset], args.title)

    print("\n--- DRAFT READY FOR CLOUD RENDER ---")
    print(f"DraftID:   {draft_id}")
    print(f"PackageID: {pkg_id}")


if __name__ == "__main__":
    main()
