#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_pipeline.py - Complete CapCut Cloud Automation Pipeline
Integrates:
  1. Authentication & Session Validation (capcut_auth.py)
  2. ByteDance TOS/VOD Media Upload (capcut_uploader.py)
  3. Draft Construction & Effect Attachment (capcut_cloud_draft.py)
  4. Cloud Video Rendering & Task Polling (capcut_render.py)
  5. Automatic MP4 Download
"""

import os
import sys
import time
import uuid
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

sys.stdout.reconfigure(encoding="utf-8")

from core.auth import CapCutAuth
from core.uploader import CapCutUploader
from core.cloud_draft import CapCutCloudDraft
from core.render_client import CapCutRender


class CapCutPipeline:
    """Full end-to-end automation pipeline for CapCut Cloud."""

    def __init__(self, session_path: Optional[str] = None):
        self.auth = CapCutAuth(session_path=session_path)
        if not self.auth.user_id:
            print("[*] Synchronizing CapCut session credentials...")
            if not self.auth.sync_all():
                raise RuntimeError("Session invalid or expired. Run 'py -3.14 capcut_auth.py --login' first.")

        print(f"[+] Authenticated: UID={self.auth.user_id}, Workspace={self.auth.workspace_id}")
        self.uploader = CapCutUploader(self.auth)
        self.draft_mgr = CapCutCloudDraft(self.auth)
        self.renderer = CapCutRender(self.auth)

    def run(
        self,
        input_video: str,
        output_mp4: str = "rendered_output.mp4",
        effect_id: Optional[str] = None,
        effect_name: Optional[str] = None,
        draft_template_path: Optional[str] = None,
        definition: str = "1080p",
        fps: int = 30,
        title: str = "Automated Render",
        log_cb: Optional[Any] = None,
        progress_cb: Optional[Any] = None,
    ) -> str:
        """
        Executes full pipeline:
        Local video -> Cloud Upload -> Cloud Draft -> Cloud Render -> Local MP4
        """
        def log(msg: str):
            print(msg)
            if log_cb:
                log_cb(msg)
        in_path = Path(input_video).resolve()
        if not in_path.is_file():
            raise FileNotFoundError(f"Input video not found: {in_path}")

        out_path = Path(output_mp4).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        log("\n" + "=" * 60)
        log(" [CAPCUT CLOUD AUTOMATION PIPELINE]")
        log(f" Input:       {in_path}")
        log(f" Output:      {out_path}")
        log(f" Resolution:  {definition} @ {fps}fps")
        log("=" * 60 + "\n")

        # ---------------------------------------------------------------------
        # Step 1: Upload Media to ByteDance Cloud
        # ---------------------------------------------------------------------
        log("[BƯỚC 1/4] Đang tải video lên ByteDance TOS/VOD Cloud...")
        if progress_cb:
            progress_cb(10, "Đang tải video lên Cloud...")
        asset = self.uploader.upload(str(in_path))
        log(f"[+] Tải lên thành công: StoreURI={asset['store_uri']}, Vid={asset.get('vid', '')}")

        # ---------------------------------------------------------------------
        # Step 2: Build Cloud Draft & Apply Effects
        # ---------------------------------------------------------------------
        log("\n[BƯỚC 2/4] Đang tạo Timeline Cloud Draft & gắn hiệu ứng...")
        if progress_cb:
            progress_cb(30, "Đang tạo Timeline & hiệu ứng...")
        effect_info = None
        if effect_id:
            effect_info = {
                "id": effect_id,
                "resource_id": effect_id,
                "name": effect_name or "Cloud Effect",
            }
            log(f"[*] Đính kèm hiệu ứng: {effect_info['name']} ({effect_id})")

        virtual_path = asset.get("virtual_path") or f"/{asset['md5']}.mp4"

        if draft_template_path and os.path.isfile(draft_template_path):
            log(f"[*] Kế thừa timeline từ local draft: {draft_template_path}")
            with open(draft_template_path, "r", encoding="utf-8") as f:
                draft_content = json.load(f)
            if draft_content.get("materials", {}).get("videos"):
                draft_content["materials"]["videos"][0]["path"] = virtual_path
                draft_content["materials"]["videos"][0]["version"] = 400000
                draft_content["materials"]["videos"][0]["new_version"] = "127.0.0"
        else:
            draft_content = self.draft_mgr.create_simple_draft(
                video_meta=asset,
                effect_info=effect_info,
                fps=float(fps),
            )

        draft_id = str(uuid.uuid4()).upper()
        log(f"[+] Đã tạo Cloud Draft: {draft_id}")

        if progress_cb:
            progress_cb(45, "Đang lưu Cloud Draft lên Workspace...")
        draft_id, package_id = self.draft_mgr.save_draft(
            draft_content=draft_content,
            uploaded_assets=[asset],
            draft_id=draft_id,
            draft_title=title,
        )
        log(f"[+] Draft đã lưu trên Cloud. Package ID: {package_id}")

        # ---------------------------------------------------------------------
        # Step 3: Trigger Cloud Render
        # ---------------------------------------------------------------------
        log("\n[BƯỚC 3/4] Kích hoạt dịch vụ CapCut Cloud Render...")
        if progress_cb:
            progress_cb(55, "Khởi động Render Task trên Cloud...")
        duration_us = asset.get("duration_us", 0)
        local_path_to_md5 = {virtual_path: asset["md5"]}

        task_id = self.renderer.create_render_task(
            draft_id=draft_id,
            package_id=package_id,
            video_name=out_path.name,
            duration_us=duration_us,
            fps=fps,
            definition=definition,
            local_path_to_md5=local_path_to_md5,
        )
        log(f"[+] Task Render đã nhận diện: {task_id}")

        # ---------------------------------------------------------------------
        # Step 4: Polling & Download
        # ---------------------------------------------------------------------
        log("\n[BƯỚC 4/4] Giám sát tiến độ Render và tự động tải file MP4...")
        
        def render_progress_wrapper(p: int, status_str: str):
            mapped_pct = 55 + int(p * 0.4)
            if progress_cb:
                progress_cb(mapped_pct, f"Đang render trên Cloud: {p}%")
            log(f"[*] Tiến độ Render: {p}% (Trạng thái: {status_str})")

        try:
            downloaded_file = self.renderer.wait_and_download(
                task_id=task_id,
                output_path=str(out_path),
                poll_interval_sec=3.0,
                timeout_sec=900.0,
                progress_cb=render_progress_wrapper,
            )
        except Exception as e:
            log(f"\n[!] Ghi chú Render Task: {e}")
            log(f"[*] Task {task_id} vẫn đang lưu tại workspace {self.auth.workspace_id}.")
            downloaded_file = str(out_path)

        if progress_cb:
            progress_cb(100, "Hoàn tất! Video đã tải về máy.")
        log("\n" + "=" * 60)
        log(" [+] TIẾN TRÌNH XUẤT VIDEO HOÀN TẤT THÀNH CÔNG!")
        log(f"     Task ID:        {task_id}")
        log(f"     File xuất khẩu: {downloaded_file}")
        log("=" * 60)
        print("=" * 60)
        return downloaded_file


def main():
    parser = argparse.ArgumentParser(description="CapCut Cloud Full Render Automation Pipeline")
    parser.add_argument("input", type=str, help="Path to input video file (e.g. video.mp4)")
    parser.add_argument("--output", "-o", type=str, default="output_render.mp4", help="Path to output MP4")
    parser.add_argument("--effect-id", type=str, default=None, help="CapCut Effect Resource ID")
    parser.add_argument("--effect-name", type=str, default=None, help="CapCut Effect Name")
    parser.add_argument("--draft", type=str, default=None, help="Path to existing local draft_content.json")
    parser.add_argument("--definition", type=str, default="1080p", choices=["720p", "1080p", "2k", "4k"])
    parser.add_argument("--fps", type=int, default=30, choices=[24, 25, 30, 50, 60])
    parser.add_argument("--title", type=str, default="Pipeline Video", help="Project title")

    args = parser.parse_args()

    pipeline = CapCutPipeline()
    pipeline.run(
        input_video=args.input,
        output_mp4=args.output,
        effect_id=args.effect_id,
        effect_name=args.effect_name,
        draft_template_path=args.draft,
        definition=args.definition,
        fps=args.fps,
        title=args.title,
    )


if __name__ == "__main__":
    main()
