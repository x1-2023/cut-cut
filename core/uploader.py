#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_uploader.py - CapCut Web ByteDance VOD & TOS Chunked Media Uploader
Uploads video and audio assets to CapCut Cloud storage using AWS SigV4 authorization.
"""

import os
import sys
import time
import json
import hmac
import hashlib
import binascii
import datetime as dt
import urllib.request
import urllib.parse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Callable, List

sys.stdout.reconfigure(encoding="utf-8")

from core.auth import CapCutAuth
from config.settings import VOD_HOST, VOD_SPACE, VOD_REGION, VOD_SERVICE

VOD_REGION = "sdwdmwlll"
VOD_SERVICE = "vod"
VOD_HOST = "vod-ap-singapore-1.bytevcloudapi.com"
VOD_SPACE = "capcut_vcloud_upload_sg"
CHUNK_SIZE = 3 * 1024 * 1024  # 3MB per chunk (standard CapCut web chunk size)

class CapCutUploader:
    """Handles multi-part chunked upload to ByteDance VOD/TOS infrastructure."""

    def __init__(self, auth: Optional[CapCutAuth] = None):
        self.auth = auth or CapCutAuth()
        if not self.auth.user_id:
            if not self.auth.sync_all():
                raise RuntimeError("CapCut session not authenticated. Run 'py -3.14 capcut_auth.py --login' first.")

    @staticmethod
    def calc_md5(file_path: Path | str) -> str:
        """Calculate MD5 hex of local file."""
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _aws_sigv4_headers(method: str, url: str, body: bytes, creds: Dict[str, Any]) -> Dict[str, str]:
        """Generate AWS SigV4 signed headers for ByteDance VOD API."""
        parsed = urllib.parse.urlsplit(url)
        now = dt.datetime.now(dt.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        http_date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

        query = "&".join(
            f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
            for k, v in sorted(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        )
        signed_headers = "x-amz-date;x-amz-security-token"
        canon_headers = f"x-amz-date:{amz_date}\nx-amz-security-token:{creds['session_token']}\n"
        payload_hash = hashlib.sha256(body).hexdigest()
        canon_req = f"{method}\n{parsed.path}\n{query}\n{canon_headers}\n{signed_headers}\n{payload_hash}"
        scope = f"{date_stamp}/{VOD_REGION}/{VOD_SERVICE}/aws4_request"
        str_to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{hashlib.sha256(canon_req.encode('utf-8')).hexdigest()}"

        k_date = hmac.new(("AWS4" + creds["secret_access_key"]).encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
        k_region = hmac.new(k_date, VOD_REGION.encode("utf-8"), hashlib.sha256).digest()
        k_service = hmac.new(k_region, VOD_SERVICE.encode("utf-8"), hashlib.sha256).digest()
        signing_key = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
        sig = hmac.new(signing_key, str_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        return {
            "Authorization": f"AWS4-HMAC-SHA256 Credential={creds['access_key_id']}/{scope}, SignedHeaders={signed_headers}, Signature={sig}",
            "Date": http_date,
            "X-Amz-Date": amz_date,
            "X-Amz-Security-Token": creds["session_token"],
            "User-Agent": f"BDFileUpload({int(time.time() * 1000)})",
            "accept-encoding": "identity",
            "tdid": "",
            "pf": "7",
            "store-country-code": "vn",
            "store-country-code-src": "uid",
        }

    def prepare_upload(self, md5_hex: str, file_size: int, file_type: str = "video") -> Tuple[Dict[str, Any], str]:
        """Step 1: Request STS security token from CapCut API."""
        url = "https://edit-api-sg.capcut.com/lv/v1/asset/prepare_upload_cloud"
        payload = {
            "workspace_id": str(self.auth.workspace_id),
            "space_id": "0",
            "md5": md5_hex,
            "size": file_size,
            "file_type": file_type,
            "is_web_user": True,
        }
        res = self.auth._request("POST", url, payload)
        if res.get("ret") != "0":
            raise RuntimeError(f"prepare_upload_cloud failed: {res}")
        data = res["data"]
        return data["security_token"], data.get("upload_id", "")

    def apply_upload_inner(self, creds: Dict[str, Any], file_size: int, file_type: str = "video") -> Dict[str, Any]:
        """Step 2: Request ByteDance VOD upload node and TOS endpoint."""
        query = urllib.parse.urlencode({
            "Action": "ApplyUploadInner",
            "Version": "2020-11-19",
            "SpaceName": VOD_SPACE,
            "FileType": file_type,
            "IsInner": "1",
            "FileSize": str(file_size),
            "device_platform": "web",
        })
        url = f"https://{VOD_HOST}/?{query}"
        headers = self._aws_sigv4_headers("GET", url, b"", creds)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        nodes = data.get("Result", {}).get("InnerUploadAddress", {}).get("UploadNodes", [])
        if not nodes:
            raise RuntimeError(f"No VOD upload nodes returned: {data}")
        return nodes[0]

    def init_upload_multipart(self, upload_host: str, store_uri: str, auth_token: str) -> str:
        """Step 3a: Initialize multipart upload session on TOS (phase=init)."""
        init_url = f"https://{upload_host}/upload/v1/{store_uri}?uploadmode=part&phase=init"
        headers = {
            "Authorization": auth_token,
            "X-Storage-U": urllib.parse.quote(str(self.auth.user_id)),
            "User-Agent": f"BDFileUpload({int(time.time() * 1000)})",
        }
        req = urllib.request.Request(init_url, data=b"", headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        upload_id = data.get("data", {}).get("uploadid")
        if not upload_id:
            raise RuntimeError(f"TOS phase=init failed: {data}")
        return upload_id

    def upload_chunks(
        self,
        file_path: Path,
        upload_host: str,
        store_uri: str,
        upload_id: str,
        auth_token: str,
        file_size: int,
        max_workers: int = 8,
    ) -> List[str]:
        """Step 3b: Transfer chunks in dynamic blocks (up to 20MB for large files) to TOS storage using parallel workers."""
        if file_size > 1024 * 1024 * 1024:  # > 1GB
            chunk_size = 20 * 1024 * 1024
        elif file_size > 200 * 1024 * 1024:  # > 200MB
            chunk_size = 10 * 1024 * 1024
        elif file_size > 50 * 1024 * 1024:  # > 50MB
            chunk_size = 5 * 1024 * 1024
        else:
            chunk_size = CHUNK_SIZE

        total_parts = (file_size + chunk_size - 1) // chunk_size
        part_crc_list: List[Optional[str]] = [None] * total_parts

        print(f"[*] Uploading {file_size / (1024*1024):.2f} MB in {total_parts} part(s) ({chunk_size//(1024*1024)}MB/part, {max_workers} workers)...")

        uploaded_bytes = 0
        progress_lock = threading.Lock()
        started_time = time.monotonic()

        def _upload_single_part(part_idx: int, offset: int, length: int) -> Tuple[int, str]:
            nonlocal uploaded_bytes
            with open(file_path, "rb") as f:
                f.seek(offset)
                chunk = f.read(length)

            crc_hex = f"{binascii.crc32(chunk) & 0xFFFFFFFF:08x}"
            transfer_url = (
                f"https://{upload_host}/upload/v1/{store_uri}?"
                f"uploadid={upload_id}&part_number={part_idx}&phase=transfer&part_offset={offset}"
            )
            headers = {
                "Authorization": auth_token,
                "X-Upload-Content-CRC32": crc_hex,
                "Content-Type": "application/octet-stream",
                "User-Agent": f"BDFileUpload({int(time.time() * 1000)})",
            }

            for attempt in range(4):
                try:
                    req = urllib.request.Request(transfer_url, data=chunk, headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        _ = resp.read()
                    break
                except Exception as exc:
                    if attempt == 3:
                        raise RuntimeError(f"Failed chunk #{part_idx} after 4 attempts: {exc}")
                    time.sleep(1 + attempt)

            with progress_lock:
                uploaded_bytes += length
                elapsed = max(0.1, time.monotonic() - started_time)
                speed_mbps = (uploaded_bytes / (1024 * 1024)) / elapsed
                pct = min(100.0, (uploaded_bytes / file_size) * 100)
                sys.stdout.write(
                    f"\r[+] Progress: {pct:5.1f}% ({uploaded_bytes / (1024*1024):.1f}/{file_size / (1024*1024):.1f} MB, {speed_mbps:.1f} MB/s)  "
                )
                sys.stdout.flush()

            return part_idx, f"{part_idx}:{crc_hex}"

        parts_to_upload = []
        for idx in range(total_parts):
            p_idx = idx + 1
            offset = idx * chunk_size
            length = min(chunk_size, file_size - offset)
            parts_to_upload.append((p_idx, offset, length))

        if total_parts <= 2:
            for p_idx, offset, length in parts_to_upload:
                _, crc_entry = _upload_single_part(p_idx, offset, length)
                part_crc_list[p_idx - 1] = crc_entry
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_upload_single_part, p, off, l) for p, off, l in parts_to_upload]
                for fut in as_completed(futures):
                    p_idx, crc_entry = fut.result()
                    part_crc_list[p_idx - 1] = crc_entry

        print()
        return [p for p in part_crc_list if p is not None]

    def finish_upload_parts(self, upload_host: str, store_uri: str, upload_id: str, auth_token: str, part_crc_list: List[str]):
        """Step 4: Finish multipart transfer on TOS (phase=finish)."""
        finish_url = f"https://{upload_host}/upload/v1/{store_uri}?uploadmode=part&phase=finish&uploadid={upload_id}"
        finish_body = ",".join(part_crc_list).encode("utf-8")
        headers = {
            "Authorization": auth_token,
            "X-Storage-U": urllib.parse.quote(str(self.auth.user_id)),
            "Content-Type": "text/plain;charset=UTF-8",
            "User-Agent": f"BDFileUpload({int(time.time() * 1000)})",
        }
        for attempt in range(4):
            try:
                req = urllib.request.Request(finish_url, data=finish_body, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=180) as resp:
                    raw = resp.read().decode("utf-8")
                    data = json.loads(raw)
                    if data.get("code") != 2000:
                        raise RuntimeError(f"TOS phase=finish failed: {data}")
                    return
            except Exception as exc:
                if attempt == 3:
                    raise RuntimeError(f"TOS phase=finish failed after 4 attempts: {exc}")
                print(f"[!] Warning: TOS phase=finish attempt {attempt+1} failed ({exc}). Retrying in {3 + attempt*2}s...")
                time.sleep(3 + attempt * 2)

    def commit_upload_inner(self, creds: Dict[str, Any], session_key: str) -> Dict[str, Any]:
        """Step 5: Commit upload to ByteDance VOD to finalize metadata."""
        query = urllib.parse.urlencode({
            "Action": "CommitUploadInner",
            "Version": "2020-11-19",
            "SpaceName": VOD_SPACE,
            "device_platform": "web",
        })
        url = f"https://{VOD_HOST}/?{query}"
        commit_body = json.dumps({
            "Functions": [{"Input": {"SnapshotTime": 0.0}, "Name": "Snapshot"}],
            "SessionKey": session_key,
        }).encode("utf-8")
        headers = self._aws_sigv4_headers("POST", url, commit_body, creds)
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=commit_body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data.get("Result", {}).get("Results", [])
        if not results:
            raise RuntimeError(f"CommitUploadInner failed: {data}")
        return results[0]

    def register_cloud_asset(
        self,
        file_path: Path,
        store_uri: str,
        vid: str,
        md5_hex: str,
        file_size: int,
        upload_id: str,
        file_type: str = "video",
    ) -> Dict[str, Any]:
        """Step 6: Register asset into CapCut Workspace Catalog."""
        url = "https://edit-api-sg.capcut.com/lv/v1/asset/create_cloud_asset"
        payload = {
            "everphoto_id": self.auth.space_id or str(self.auth.user_id),
            "is_web_user": True,
            "asset": {
                "uri": store_uri,
                "size": file_size,
                "workspace_id": str(self.auth.workspace_id),
                "filename": file_path.name,
                "upload_id": upload_id,
                "preserve_video_multi_definition": True,
                "if_image_async_resize": True,
                "transcode_template_type": 0,
                "permission": 0,
                "space_id": "0",
                "flags": 0,
                "file_type": file_type,
                "folder_id": "-1",
                "meta": json.dumps({"vid": vid}),
                "md5": md5_hex,
                "no_copy": False,
            }
        }
        try:
            res = self.auth._request("POST", url, payload, extra_headers={"appvr": "8.4.0"})
            if res.get("ret") == "0":
                data = res.get("data", {}) or {}
                asset_id = data.get("cloud_asset", {}).get("asset_id") or data.get("asset_id")
                print(f"[+] Asset registered in CapCut Workspace: asset_id={asset_id}")
            return res.get("data", {}) or {}
        except Exception as e:
            print(f"[!] Warning during asset registration: {e}")
            return {}

    def upload(self, file_path: str | Path, file_type: str = "video") -> Dict[str, Any]:
        """Execute full upload pipeline for a media file."""
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        file_size = path.stat().st_size
        print(f"[*] Analyzing file: {path.name} ({file_size} bytes)")
        md5_hex = self.calc_md5(path)
        print(f"[+] MD5: {md5_hex}")

        # 1. Prepare upload
        print("[*] Requesting STS upload token...")
        creds, upload_id = self.prepare_upload(md5_hex, file_size, file_type)

        # 2. Apply Upload Inner
        print("[*] Allocating VOD upload node...")
        node = self.apply_upload_inner(creds, file_size, file_type)
        store = node["StoreInfos"][0]
        upload_host = node["UploadHost"]
        store_uri = store["StoreUri"]
        auth_token = store["Auth"]
        vid = node.get("Vid") or (node.get("Vids") or [""])[0]

        print(f"[+] VOD Node ready: Vid={vid}")
        print(f"[+] Storage Target: https://{upload_host}/{store_uri}")

        # 3. Initialize TOS multipart upload
        print("[*] Initializing multipart on TOS...")
        tos_upload_id = self.init_upload_multipart(upload_host, store_uri, auth_token)

        # 4. Transfer chunks
        part_crc_list = self.upload_chunks(path, upload_host, store_uri, tos_upload_id, auth_token, file_size)

        # 5. Finish parts
        print("[*] Finalizing parts on TOS...")
        self.finish_upload_parts(upload_host, store_uri, tos_upload_id, auth_token, part_crc_list)

        # 5. Commit VOD
        print("[*] Committing to ByteDance VOD...")
        commit_res = self.commit_upload_inner(creds, node["SessionKey"])
        video_meta = commit_res.get("VideoMeta", {})
        duration_sec = float(video_meta.get("Duration") or 0.0)
        duration_us = int(duration_sec * 1e6)

        # 6. Register into workspace
        asset_reg = self.register_cloud_asset(path, store_uri, vid, md5_hex, file_size, upload_id, file_type)

        virtual_path = f"/{md5_hex}.mp4"

        result = {
            "vid": vid,
            "store_uri": store_uri,
            "md5": md5_hex,
            "size": file_size,
            "duration_us": duration_us,
            "duration_sec": duration_sec,
            "width": video_meta.get("Width", 1920),
            "height": video_meta.get("Height", 1080),
            "format": video_meta.get("Format", "mp4"),
            "file_name": path.name,
            "virtual_path": virtual_path,
            "asset_id": asset_reg.get("asset_id", ""),
        }
        print(f"[+] Media upload SUCCESS: Vid={vid}, Duration={duration_sec:.2f}s, VirtualPath={virtual_path}")
        return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CapCut Cloud Media Uploader")
    parser.add_argument("file", type=str, help="Path to video or audio file to upload")
    parser.add_argument("--type", type=str, default="video", choices=["video", "audio"], help="Media type (video/audio)")
    args = parser.parse_args()

    uploader = CapCutUploader()
    res = uploader.upload(args.file, args.type)
    print("\n--- UPLOAD RESULT ---")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
