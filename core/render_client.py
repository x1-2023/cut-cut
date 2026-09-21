#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_render.py - CapCut Cloud Video Renderer & Poller
Submits cloud rendering tasks to CapCut Web backend, polls progress in real-time,
and downloads the rendered MP4 video upon completion.
"""

import os
import sys
import time
import uuid
import json
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional, Callable

sys.stdout.reconfigure(encoding="utf-8")

from core.auth import CapCutAuth

class CapCutRender:
    """Manages CapCut Cloud Render tasks and MP4 exports."""

    def __init__(self, auth: Optional[CapCutAuth] = None):
        self.auth = auth or CapCutAuth()
        if not self.auth.user_id:
            if not self.auth.sync_all():
                raise RuntimeError("CapCut session not authenticated.")

    def create_render_task(
        self,
        draft_id: str,
        package_id: str,
        video_name: str = "rendered_video.mp4",
        duration_us: int = 0,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        definition: str = "1080p",
        quality: int = 1,
        format_type: str = "mp4",
        local_path_to_md5: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Submits a video rendering job to CapCut Cloud Render service.
        Returns: task_id string.
        """
        url = "https://edit-api-sg.capcut.com/lv/v1/render_task/create"
        now_ms = int(time.time() * 1000)
        submit_id = f"{now_ms}_{uuid.uuid4().hex[:8]}"

        # Duration in seconds (float) matching CapCut Web HAR (e.g. 1141.105454)
        if duration_us > 10000:
            duration_sec = round(duration_us / 1e6, 6)
        else:
            duration_sec = float(duration_us)

        extra = {
            "filmGeneratedBy": draft_id,
            "uploadSource": {
                "owner": str(self.auth.user_id),
                "platform": "browser",
                "systemVersion": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "appVersion": "15.4.0",
                "createTime": now_ms,
            },
            "packageType": 0,
            "packageTransferedFrom": 0,
            "packageScriptInfo": {},
            "packageSmartToolsInfo": {},
            "templateId": "",
            "videoTypeList": "",
        }

        payload: Dict[str, Any] = {
            "app_id": int(self.auth.aid),
            "app_version": "15.4.0",
            "sdk_version": "19.3.0",
            "width": width,
            "height": height,
            "fps": fps,
            "format": format_type,
            "quality": quality,
            "definition": definition,
            "draft_id": draft_id,
            "package_id": package_id,
            "video_id": str(uuid.uuid4()),
            "from_workspace_id": str(self.auth.workspace_id),
            "to_workspace_id": str(self.auth.workspace_id),
            "video_name": video_name,
            "duration": duration_sec,
            "submit_id": submit_id,
            "extra": json.dumps(extra),
            "region": "VN",
            "type": 0,
            "force_export": False,
            "uid": str(self.auth.user_id),
            "is_unify_task": False,
            "cc_web_version": 0,
            "enable_cover": False,
        }

        if local_path_to_md5:
            payload["local_path_to_md5"] = local_path_to_md5

        extra_headers = {
            "appvr": "8.4.0",
            "origin": "https://www.capcut.com",
            "referer": "https://www.capcut.com/",
        }

        print(f"[*] Submitting cloud render task for draft '{draft_id}' ({definition}, {fps}fps, duration={duration_sec}s)...")
        res = self.auth._request("POST", url, payload, extra_headers=extra_headers)

        if res.get("ret") != "0":
            raise RuntimeError(f"Failed to create render task: {res}")

        task_id = res.get("data", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in response: {res}")

        print(f"[+] Render task created successfully. Task ID: {task_id}")
        return str(task_id)

    def query_render_task(self, task_id: str) -> Dict[str, Any]:
        """Query render task status via /lv/v1/render_task/batch_get."""
        url = "https://edit-api-sg.capcut.com/lv/v1/render_task/batch_get"
        payload = {
            "task_ids": [task_id],
            "need_task_info": True,
            "need_media_info": True,
            "force_export": False,
        }
        res = self.auth._request("POST", url, payload)

        if res.get("ret") != "0":
            raise RuntimeError(f"Query render task failed: {res}")

        tasks = res.get("data", {}).get("render_task", {})
        task_info = tasks.get(task_id)
        if not task_info:
            raise RuntimeError(f"Task {task_id} not found in query response.")

        return task_info

    def cancel_render_task(self, task_id: str) -> bool:
        """Cancel a running render task."""
        url = "https://edit-api-sg.capcut.com/lv/v1/render_task/cancel"
        payload = {"task_ids": [task_id]}
        res = self.auth._request("POST", url, payload)
        return res.get("ret") == "0"

    def wait_and_download(
        self,
        task_id: str,
        output_path: str,
        poll_interval_sec: float = 3.0,
        timeout_sec: float = 600.0,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """
        Polls render task until completion and downloads the final MP4.
        Returns: absolute path to downloaded MP4 file.
        """
        start_time = time.time()
        print(f"[*] Monitoring render task {task_id}...")

        while True:
            if time.time() - start_time > timeout_sec:
                raise TimeoutError(f"Render task {task_id} timed out after {timeout_sec}s.")

            info = self.query_render_task(task_id)
            status = info.get("status")
            progress = info.get("progress", 0)
            file_id = info.get("file_id")

            if progress_cb:
                progress_cb(progress, str(status))

            # Status codes:
            # 0: Queued / Initializing
            # 1: Rendering (or complete when progress=100 with file_id)
            # 2: Transcoding / Finalizing
            # 3: Finished / Success
            # -1: Failed
            if status == 3 or (status == 1 and progress == 100 and file_id):
                print(f"\n[+] Render processing completed! (Progress: {progress}%, Status: {status})")
                print(f"[*] Resolving download URL for file_id: {file_id or task_id}...")
                video_url = self._resolve_download_url(info)

                if video_url:
                    return self._download_file(video_url, output_path)

                if status == 3 and not video_url:
                    raise RuntimeError(f"Render completed but video URL could not be resolved: {info}")

            elif status == -1:
                err_code = str(info.get("task_err_code", "UNKNOWN"))
                ret_code = str(info.get("render_ret_code", ""))
                if err_code == "19070005" or ret_code == "19070005":
                    raise RuntimeError(
                        f"Máy chủ CapCut Cloud đang quá tải hoặc video quá dài (Lỗi 19070005: Hiện có quá nhiều người đang sử dụng tính năng này). "
                        f"Khuyến nghị: Chuyển 'Chế độ render' sang 'Lưu CapCut PC Draft' (Local) để render trực tiếp không giới hạn thời lượng, hoặc thử lại sau."
                    )
                raise RuntimeError(f"Render task failed on cloud! Error Code: {err_code}, Ret Code: {ret_code}")

            elapsed = int(time.time() - start_time)
            sys.stdout.write(f"\r[*] Rendering progress: {progress}% [Status: {status}] ({elapsed}s elapsed)...")
            sys.stdout.flush()

            time.sleep(poll_interval_sec)

    def _resolve_download_url(self, task_info: Dict[str, Any]) -> str:
        """Resolve download URL using ever_photo external download endpoint or task URLs."""
        if task_info.get("video_url"):
            return task_info["video_url"]
        if task_info.get("origin_download_link"):
            return task_info["origin_download_link"]

        file_id = task_info.get("file_id")
        if file_id:
            try:
                url = "https://edit-api-sg.capcut.com/lv/v1/ever_photo/get_external_download_url"
                payload = {
                    "asset_id": str(file_id),
                    "workspace_id": str(self.auth.workspace_id),
                    "max_time": 3600,
                    "ttl": 3600,
                }
                res = self.auth._request("POST", url, payload, extra_headers={"appvr": "8.4.0"})
                if res.get("ret") == "0":
                    download_url = res.get("data", {}).get("download_url", "")
                    if download_url:
                        return download_url
            except Exception as e:
                print(f"[!] Warning: ever_photo download URL resolution failed: {e}")

        return ""

    def _download_file(self, url: str, output_path: str) -> str:
        """Download file with progress indicator."""
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        print(f"\n[*] Downloading rendered video to: {out}...")

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.capcut.com/",
            }
        )

        with urllib.request.urlopen(req) as resp, open(out, "wb") as f:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 64 * 1024

            while True:
                chunk = resp.read(block_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    pct = int(downloaded * 100 / total_size)
                    mb = downloaded / (1024 * 1024)
                    total_mb = total_size / (1024 * 1024)
                    sys.stdout.write(f"\r    Downloaded: {mb:.1f}/{total_mb:.1f} MB ({pct}%)")
                    sys.stdout.flush()

        print(f"\n[+] Video saved successfully: {out} ({os.path.getsize(out)} bytes)")
        return str(out)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CapCut Cloud Video Renderer")
    subparsers = parser.add_subparsers(dest="cmd")

    create_p = subparsers.add_parser("create", help="Create render task")
    create_p.add_argument("--draft-id", required=True, help="Cloud Draft ID")
    create_p.add_argument("--package-id", default="", help="Cloud Package ID")
    create_p.add_argument("--name", default="video.mp4", help="Output filename")
    create_p.add_argument("--duration", type=int, default=0, help="Duration in microseconds")
    create_p.add_argument("--definition", default="1080p", choices=["720p", "1080p", "2k", "4k"])

    poll_p = subparsers.add_parser("poll", help="Poll existing render task")
    poll_p.add_argument("--task-id", required=True, help="Task ID")
    poll_p.add_argument("--output", default="output.mp4", help="Output file path")

    args = parser.parse_args()
    auth = CapCutAuth()
    renderer = CapCutRender(auth)

    if args.cmd == "create":
        pkg_id = args.package_id or args.draft_id
        task_id = renderer.create_render_task(
            draft_id=args.draft_id,
            package_id=pkg_id,
            video_name=args.name,
            duration_us=args.duration,
            definition=args.definition,
        )
        print(f"Task ID: {task_id}")

    elif args.cmd == "poll":
        renderer.wait_and_download(args.task_id, args.output)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
