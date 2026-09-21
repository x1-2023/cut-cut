#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cli/batch_runner.py - Headless High-Throughput Batch Automation CLI for CapCut Cloud
Supports 100 - 200+ videos/day with parallel workers and multi-account rotation.
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.stdout.reconfigure(encoding="utf-8")

from config.settings import PRESETS_FILE, DEFAULT_OUTPUT_DIR
from core.auth import CapCutAuth
from core.draft_builder import make_draft, render_draft_cloud
from core.account_manager import CapCutAccountManager


def load_presets() -> Dict[str, Any]:
    if PRESETS_FILE.exists():
        try:
            with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


class BatchProcessor:
    def __init__(
        self,
        workers: int = 3,
        preset_name: str = "",
        definition: str = "1080p",
        fps: int = 30,
        output_dir: str = "",
        rotate_accounts: bool = False,
        auto_caption: bool = False,
        caption_lang: str = "vi-VN",
    ):
        self.workers = max(1, min(workers, 8))
        self.preset_name = preset_name
        self.definition = definition
        self.fps = fps
        self.output_dir = Path(output_dir).resolve() if output_dir else DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.rotate_accounts = rotate_accounts
        self.auto_caption = auto_caption
        self.caption_lang = caption_lang

        self.presets = load_presets()
        self.selected_preset = self.presets.get(preset_name, {})

        # Multi-account setup
        self.acc_mgr = CapCutAccountManager()
        self.accounts = self.acc_mgr.list_accounts() if rotate_accounts else []
        self.acc_index = 0
        self.acc_lock = threading.Lock()

        # Stats
        self.stats_lock = threading.Lock()
        self.success_list: List[str] = []
        self.failed_list: List[Tuple[str, str]] = []
        self.total_processed = 0

    def get_auth_for_job(self) -> CapCutAuth:
        """Returns authenticated session, rotating across active accounts if enabled."""
        if self.rotate_accounts and self.accounts:
            with self.acc_lock:
                acc_info = self.accounts[self.acc_index % len(self.accounts)]
                self.acc_index += 1
            auth = CapCutAuth()
            auth.load_cookies_from_string(acc_info.get("cookies", ""))
            return auth
        else:
            auth = CapCutAuth()
            auth.sync_all()
            return auth

    def process_video(self, video_path: Path, idx: int, total: int) -> bool:
        v_name = video_path.name
        print(f"\n[{idx}/{total}] [*] STARTING: {v_name}")
        t_start = time.time()

        out_file = self.output_dir / f"rendered_{video_path.stem}.mp4"
        if out_file.exists():
            print(f"[{idx}/{total}] [i] File already exists, skipping: {out_file.name}")
            with self.stats_lock:
                self.success_list.append(v_name)
                self.total_processed += 1
            return True

        try:
            # Build draft parameters from preset
            draft_params: Dict[str, Any] = {}
            if self.selected_preset:
                v_cfg = self.selected_preset.get("video", {})
                e_cfg = self.selected_preset.get("effect", {})
                a_cfg = self.selected_preset.get("audio", {})
                c_cfg = self.selected_preset.get("color", {})

                draft_params["speed"] = v_cfg.get("speed", 1.0)
                draft_params["scale"] = v_cfg.get("scale", 100)
                draft_params["vol_db"] = v_cfg.get("volume_db", 0.0)

                if e_cfg.get("name"):
                    draft_params["effect_name"] = e_cfg["name"]
                    draft_params["effect_params"] = {
                        k: v for k, v in e_cfg.items() if k != "name"
                    }

                draft_params["vocal_sep"] = a_cfg.get("vocal_sep", False)
                draft_params["color_params"] = c_cfg

            # 1. Make draft
            draft_content, _, err = make_draft(vp=str(video_path), **draft_params)
            if err:
                raise RuntimeError(f"Draft creation failed: {err}")

            # 2. Render cloud
            downloaded = render_draft_cloud(
                vp=str(video_path),
                draft_content=draft_content,
                output_mp4=str(out_file),
                definition=self.definition,
                fps=self.fps,
                auto_caption=self.auto_caption,
                caption_language=self.caption_lang,
                log_cb=None,
                progress_cb=None,
            )

            dur = time.time() - t_start
            print(f"[{idx}/{total}] [+] COMPLETED in {dur:.1f}s: {v_name} -> {Path(downloaded).name}")

            with self.stats_lock:
                self.success_list.append(v_name)
                self.total_processed += 1
            return True

        except Exception as exc:
            dur = time.time() - t_start
            print(f"[{idx}/{total}] [-] FAILED after {dur:.1f}s: {v_name} -> {exc}")
            with self.stats_lock:
                self.failed_list.append((v_name, str(exc)))
                self.total_processed += 1
            return False

    def run(self, video_files: List[Path]):
        total = len(video_files)
        print("\n" + "=" * 65)
        print(" [CAPCUT CLOUD HIGH-THROUGHPUT BATCH ENGINE]")
        print(f" Total Queue:       {total} video(s)")
        print(f" Concurrency:       {self.workers} parallel worker(s)")
        print(f" Output Target:     {self.definition} @ {self.fps}fps")
        print(f" Preset Selected:   {self.preset_name or 'Default Clean'}")
        print(f" Output Directory:  {self.output_dir}")
        print(f" Account Rotation:  {'ON (' + str(len(self.accounts)) + ' accounts)' if self.rotate_accounts else 'OFF (Current PRO)'}")
        print("=" * 65 + "\n")

        start_all = time.time()

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self.process_video, v, i + 1, total): v
                for i, v in enumerate(video_files)
            }
            for fut in as_completed(futures):
                _ = fut.result()

        total_elapsed = time.time() - start_all
        rate = (len(self.success_list) / (total_elapsed / 3600.0)) if total_elapsed > 0 else 0

        print("\n" + "=" * 65)
        print(" [BATCH PROCESSING SUMMARY REPORT]")
        print(f" Total Time:        {total_elapsed/60:.1f} minutes ({total_elapsed:.1f}s)")
        print(f" Success:           {len(self.success_list)}/{total} ({len(self.success_list)/max(1,total)*100:.1f}%)")
        print(f" Failed:            {len(self.failed_list)}/{total}")
        print(f" Actual Velocity:   {rate:.1f} videos/hour (Estimate: {rate*24:.0f} videos/24h)")
        print("=" * 65)

        if self.failed_list:
            print("\nFailures:")
            for name, err in self.failed_list[:10]:
                print(f" - {name}: {err}")
            if len(self.failed_list) > 10:
                print(f" ... and {len(self.failed_list)-10} more.")


def scan_videos(input_paths: List[str]) -> List[Path]:
    results = []
    valid_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}
    for p_str in input_paths:
        p = Path(p_str).resolve()
        if p.is_file() and p.suffix.lower() in valid_exts:
            results.append(p)
        elif p.is_dir():
            for f in p.iterdir():
                if f.is_file() and f.suffix.lower() in valid_exts:
                    results.append(f)
    seen = set()
    unique_results = []
    for r in results:
        if str(r) not in seen:
            seen.add(str(r))
            unique_results.append(r)
    return unique_results


def run_cli_entry():
    parser = argparse.ArgumentParser(description="CapCut Cloud High-Throughput Batch Automation CLI")
    parser.add_argument("-i", "--inputs", nargs="+", default=[], help="Input video file(s) or folder(s)")
    parser.add_argument("-o", "--output-dir", default="", help="Directory to save rendered videos")
    parser.add_argument("-w", "--workers", type=int, default=3, help="Concurrent render workers (recommended 3-5)")
    parser.add_argument("-p", "--preset", default="", help="Preset name from presets.json")
    parser.add_argument("-d", "--definition", default="1080p", choices=["720p", "1080p", "2k", "4k"], help="Resolution")
    parser.add_argument("--fps", type=int, default=30, choices=[24, 25, 30, 50, 60], help="Frames per second")
    parser.add_argument("--rotate-accounts", action="store_true", help="Rotate across multiple accounts in accounts.json")
    parser.add_argument("--caption", action="store_true", help="Auto-generate and burn-in AI speech subtitles")
    parser.add_argument("--caption-lang", default="vi-VN", help="Language for speech recognition (e.g. vi-VN, en-US, auto)")
    parser.add_argument("--list-presets", action="store_true", help="List available presets and exit")

    args = parser.parse_args()

    if args.list_presets:
        presets = load_presets()
        print("\nAvailable Presets:")
        for name, data in presets.items():
            eff = data.get("effect", {}).get("name", "None")
            mode = data.get("output", {}).get("mode", "cloud")
            print(f"  - [{name}] (Effect: {eff}, Mode: {mode})")
        return

    if not args.inputs:
        parser.print_help()
        sys.exit(1)

    video_files = scan_videos(args.inputs)
    if not video_files:
        print("[!] Không tìm thấy video hợp lệ nào từ đường dẫn đã chỉ định.")
        sys.exit(1)

    processor = BatchProcessor(
        workers=args.workers,
        preset_name=args.preset,
        definition=args.definition,
        fps=args.fps,
        output_dir=args.output_dir,
        rotate_accounts=args.rotate_accounts,
        auto_caption=args.caption,
        caption_lang=args.caption_lang,
    )
    processor.run(video_files)


if __name__ == "__main__":
    run_cli_entry()
