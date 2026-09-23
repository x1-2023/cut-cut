# -*- coding: utf-8 -*-
"""
core/vocal_separator.py - CapCut Cloud AI Vocal Separation Engine
Reverses CapCut Desktop AI Vocal Separation (type 6, separate_type: "human").
Isolates vocals / dialogue / speech and strips music / instruments.
Handles audio extraction, chunked TOS upload, cloud AI task dispatch,
automatic segment slicing for audio > 14 minutes, and lossless concatenation.
"""

import os
import sys
import json
import time
import uuid
import shutil
import binascii
import hashlib
import hmac
import subprocess
import datetime as dt
from pathlib import Path
from typing import Optional, Callable, Tuple, List, Dict, Any
from urllib.parse import urlencode, parse_qsl, quote, urlsplit

import requests

from config.settings import SESSION_FILE, DEFAULT_OUTPUT_DIR


# -------------------------------------------------------------------------
# Cryptography & Signing Utilities
# -------------------------------------------------------------------------

def compact_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def sha256_hex(data: Any) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hmac_sha256(key: Any, msg: Any) -> bytes:
    if isinstance(key, str):
        key = key.encode("utf-8")
    if isinstance(msg, str):
        msg = msg.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).digest()


def aws4_signing_key(secret_access_key: str, date_stamp: str, region: str = "sdwdmwlll", service: str = "vod") -> bytes:
    k_date = hmac_sha256("AWS4" + secret_access_key, date_stamp)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    return hmac_sha256(k_service, "aws4_request")


def canonical_query(url: str) -> str:
    pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    return "&".join(
        quote(str(k), safe="-_.~") + "=" + quote(str(v), safe="-_.~") for k, v in sorted(pairs)
    )


def aws4_authorization(
    method: str,
    url: str,
    body: bytes,
    access_key_id: str,
    secret_access_key: str,
    session_token: str,
    amz_date: str,
    region: str = "sdwdmwlll",
    service: str = "vod",
) -> str:
    date_stamp = amz_date[:8]
    scope = f"{date_stamp}/{region}/{service}/aws4_request"
    signed_headers = "x-amz-date;x-amz-security-token"
    canonical_headers = f"x-amz-date:{amz_date}\nx-amz-security-token:{session_token}\n"
    canonical_request = "\n".join(
        [method, urlsplit(url).path, canonical_query(url), canonical_headers, signed_headers, sha256_hex(body)]
    )
    string_to_sign = "\n".join(
        ["AWS4-HMAC-SHA256", amz_date, scope, sha256_hex(canonical_request)]
    )
    signature = hmac.new(
        aws4_signing_key(secret_access_key, date_stamp, region, service),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"AWS4-HMAC-SHA256 Credential={access_key_id}/{scope}, SignedHeaders={signed_headers}, Signature={signature}"


def utc_now_for_vod() -> Tuple[str, str]:
    now = dt.datetime.now(dt.timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%a, %d %b %Y %H:%M:%S GMT")


def crc32_hex(data: bytes) -> str:
    return f"{binascii.crc32(data) & 0xFFFFFFFF:08x}"


def make_sign_header(url: str, appvr: str, device_time: str, tdid: str, pf: str = "4") -> str:
    path = url.split("?", 1)[0]
    sign_str = f"9e2c|{path[-7:]}|{pf}|{appvr}|{device_time}|{tdid}|11ac"
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest()


# -------------------------------------------------------------------------
# FFmpeg Helper Utilities
# -------------------------------------------------------------------------

def get_audio_duration(file_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(res.stdout.strip() or 0.0)


def extract_audio_to_wav(video_or_audio_path: str, output_wav: str) -> str:
    Path(output_wav).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-i", video_or_audio_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        output_wav,
        "-y",
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_wav


def slice_audio(input_wav: str, start_sec: float, duration_sec: float, output_part: str) -> str:
    Path(output_part).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-ss", str(start_sec),
        "-t", str(duration_sec),
        "-i", input_wav,
        "-c", "copy",
        output_part,
        "-y",
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_part


def concat_wav_files(part_paths: List[str], final_wav: str) -> str:
    Path(final_wav).parent.mkdir(parents=True, exist_ok=True)
    concat_list_file = Path(final_wav).parent / f"concat_list_{int(time.time()*1000)}.txt"
    with open(concat_list_file, "w", encoding="utf-8") as f:
        for p in part_paths:
            # Escape single quotes and backslashes for ffmpeg concat
            p_esc = str(Path(p).resolve()).replace("\\", "/")
            f.write(f"file '{p_esc}'\n")

    cmd = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        final_wav,
        "-y",
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    finally:
        if concat_list_file.exists():
            concat_list_file.unlink()
    return final_wav


# -------------------------------------------------------------------------
# CapCut Vocal Separator Engine
# -------------------------------------------------------------------------

class CapCutVocalSeparator:
    """
    Reverse-engineered CapCut Cloud AI Vocal Separation client.
    Connects to editor-api-sg.capcutapi.com using active session cookies.
    """

    def __init__(self, session_path: Optional[str] = None):
        if session_path and Path(session_path).exists():
            sess_file = Path(session_path)
        elif SESSION_FILE.exists():
            sess_file = SESSION_FILE
        else:
            fallback = Path(r"E:\.capcut\capcut_session.json")
            sess_file = fallback if fallback.exists() else SESSION_FILE

        with open(sess_file, "r", encoding="utf-8") as f:
            self.session_data = json.load(f)

        self.cookies = self.session_data.get("cookies", {})
        self.cookie_header = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
        self.uid = str(self.session_data.get("user_id", "7661639738788955144"))

        # Windows Client Parameters matching CapCut PC
        self.appvr = "9.6.0"
        self.device_id = "7512095964732556801"
        self.iid = "7664573462719072001"
        self.tdid = "7512095964732556801"
        self.channel = "capcutpc_0"
        self.pf = "4"
        self.aid = "359289"
        self.loc = "VN"

        self.http = requests.Session()

    def _get_pc_headers(self, url: str, body_text: str = "") -> Dict[str, str]:
        device_time = str(int(time.time()))
        sign = make_sign_header(url, self.appvr, device_time, self.tdid, pf=self.pf)
        ss_stub = hashlib.md5(body_text.encode("utf-8")).hexdigest() if body_text else ""
        trace_seed = uuid.uuid4().hex[:32]
        trace_id = f"00-{trace_seed}-{trace_seed[:16]}-01"

        headers = {
            "Host": "editor-api-sg.capcutapi.com",
            "Content-Type": "application/json",
            "App-Sdk-Version": self.appvr,
            "appID": self.aid,
            "appvr": self.appvr,
            "ch": self.channel,
            "device-platform": "windows",
            "device-time": device_time,
            "lan": "en",
            "loc": self.loc,
            "pf": self.pf,
            "sign": sign,
            "sign-ver": "1",
            "tdid": self.tdid,
            "sdk-version": "2",
            "Cookie": self.cookie_header,
            "User-Agent": "Cronet/TTNetVersion:36f89019 2026-09-15 QuicVersion:55af8b7a 2024-11-18",
            "store-country-code": self.loc.lower(),
            "store-country-code-src": "uid",
            "x-tt-trace-id": trace_id,
        }
        if ss_stub:
            headers["x-ss-stub"] = ss_stub
            headers["X-SS-DP"] = self.aid
        return headers

    def _upload_wav_to_tos(self, wav_path: str, log_cb: Optional[Callable[[str], None]] = None, max_retries: int = 5) -> Tuple[str, int]:
        """
        Upload single WAV file in 5MB chunks to ByteDance TOS space cc_pc_audio_separation_sg.
        Retries automatically on network or rate limit errors.
        Returns: (vid, duration_ms)
        """
        def _log(msg: str):
            if log_cb:
                log_cb(msg)

        path_obj = Path(wav_path)
        if not path_obj.exists():
            raise FileNotFoundError(f"WAV file not found: {wav_path}")

        with open(wav_path, "rb") as f:
            audio_bytes = f.read()

        file_size = len(audio_bytes)
        part_crc = crc32_hex(audio_bytes)
        _log(f"[*] Kích thước audio: {file_size:,} bytes")

        for attempt in range(1, max_retries + 1):
            try:
                # 1. upload_sign
                q_params = {
                    "version_code": self.appvr,
                    "uid": self.uid,
                    "channel": self.channel,
                    "effect_sdk_version": "22.3.0",
                    "aid": self.aid,
                    "device_id": self.device_id,
                    "version_name": self.appvr,
                    "device_platform": "windows",
                    "region": self.loc,
                    "biz_id": "106",
                }
                sign_url = f"https://editor-api-sg.capcutapi.com/lv/v1/upload_sign?{urlencode(q_params)}"
                sign_body = compact_json({"biz": "cc_pc_audio_separation", "key_version": "v5"})
                resp = self.http.post(sign_url, headers=self._get_pc_headers(sign_url, sign_body), data=sign_body.encode("utf-8"), timeout=35)
                sign_res = resp.json()
                if sign_res.get("ret") != "0":
                    raise RuntimeError(f"Lỗi xin quyền upload TOS (upload_sign, ret={sign_res.get('ret')}): {sign_res}")

                creds = sign_res["data"]
                space_name = creds["space_name"]
                domain = creds["domain"]
                region = creds.get("region", "sdwdmwlll")

                # 2. ApplyUploadInner
                apply_params = {
                    "Action": "ApplyUploadInner",
                    "SpaceName": space_name,
                    "UseQuic": "false",
                    "Version": "2020-11-19",
                    "device_platform": "win",
                }
                apply_url = f"https://{domain}/top/v1?{urlencode(apply_params)}"
                amz_date, http_date = utc_now_for_vod()
                auth_head = aws4_authorization(
                    "GET", apply_url, b"", creds["access_key_id"], creds["secret_access_key"], creds["session_token"], amz_date, region=region
                )
                apply_headers = {
                    "Authorization": auth_head,
                    "Date": http_date,
                    "User-Agent": f"BDFileUpload({int(time.time()*1000)})",
                    "X-Amz-Date": amz_date,
                    "X-Amz-Expires": "31536000",
                    "X-Amz-Security-Token": creds["session_token"],
                    "accept-encoding": "identity",
                    "store-country-code": self.loc.lower(),
                    "store-country-code-src": "uid",
                    "tdid": self.tdid,
                    "pf": self.pf,
                }
                resp = self.http.get(apply_url, headers=apply_headers, timeout=35)
                apply_res = resp.json()
                inner_addr = apply_res.get("Result", {}).get("InnerUploadAddress")
                if not inner_addr or not inner_addr.get("UploadNodes"):
                    raise RuntimeError(f"Lỗi khởi tạo upload node TOS (ApplyUploadInner): {apply_res}")

                node = inner_addr["UploadNodes"][0]
                vid = node.get("Vid") or node.get("Vids")[0]
                store = node["StoreInfos"][0]
                upload_host = node["UploadHost"]
                store_uri = store["StoreUri"]
                upload_id = store["UploadID"]
                upload_auth = store["Auth"]
                session_key = node["SessionKey"]

                # 3. Transfer binary chunks (5MB chunks)
                chunk_size = 5 * 1024 * 1024
                chunks = [audio_bytes[i:i + chunk_size] for i in range(0, file_size, chunk_size)]
                num_parts = len(chunks)
                _log(f"[*] Đang tải dữ liệu audio lên Cloud ({num_parts} phân đoạn 5MB)...")

                part_records = []
                for part_num, chunk_data in enumerate(chunks):
                    chunk_crc = crc32_hex(chunk_data)
                    part_records.append(f"{part_num}:{chunk_crc}")
                    transfer_url = f"https://{upload_host}/upload/v1/{store_uri}?{urlencode({'uploadid': upload_id, 'part_number': str(part_num), 'phase': 'transfer'})}"
                    trans_headers = {
                        "Authorization": upload_auth,
                        "Date": utc_now_for_vod()[1],
                        "User-Agent": f"BDFileUpload({int(time.time()*1000)})",
                        "accept-encoding": "identity",
                        "store-country-code": self.loc.lower(),
                        "store-country-code-src": "uid",
                        "tdid": self.tdid,
                        "pf": self.pf,
                        "X-Upload-Content-CRC32": chunk_crc,
                    }
                    chunk_uploaded = False
                    for chunk_try in range(1, 4):
                        try:
                            resp = self.http.post(transfer_url, headers=trans_headers, data=chunk_data, timeout=180)
                            if resp.status_code < 400:
                                chunk_uploaded = True
                                break
                            _log(f"[!] Lỗi tải chunk {part_num} (HTTP {resp.status_code}), thử lại lần {chunk_try}/3...")
                            time.sleep(2)
                        except Exception as ce:
                            _log(f"[!] Socket timeout chunk {part_num} ({ce}), thử lại lần {chunk_try}/3...")
                            time.sleep(3)
                    if not chunk_uploaded:
                        raise RuntimeError(f"Tải chunk {part_num} lên TOS thất bại sau 3 lần thử.")

                # 4. Finish upload
                finish_url = f"https://{upload_host}/upload/v1/{store_uri}?{urlencode({'uploadmode': 'part', 'phase': 'finish', 'uploadid': upload_id})}"
                finish_headers = {
                    "Authorization": upload_auth,
                    "Date": utc_now_for_vod()[1],
                    "User-Agent": f"BDFileUpload({int(time.time()*1000)})",
                    "accept-encoding": "identity",
                    "store-country-code": self.loc.lower(),
                    "store-country-code-src": "uid",
                    "tdid": self.tdid,
                    "pf": self.pf,
                }
                finish_data = ",".join(part_records).encode("utf-8")
                resp = self.http.post(finish_url, headers=finish_headers, data=finish_data, timeout=35)
                if resp.status_code >= 400:
                    raise RuntimeError(f"Finish upload thất bại HTTP {resp.status_code}: {resp.text}")

                # 5. Commit upload
                commit_url = f"https://{domain}/top/v1?{urlencode({'Action': 'CommitUploadInner', 'SpaceName': space_name, 'Version': '2020-11-19', 'device_platform': 'win'})}"
                commit_body = compact_json({"Functions": [{"Input": {"SnapshotTime": 0.0}, "Name": "Snapshot"}], "SessionKey": session_key})
                amz_date, http_date = utc_now_for_vod()
                commit_auth = aws4_authorization(
                    "POST", commit_url, commit_body.encode("utf-8"), creds["access_key_id"], creds["secret_access_key"], creds["session_token"], amz_date, region=region
                )
                commit_headers = {
                    "Authorization": commit_auth,
                    "Date": http_date,
                    "User-Agent": f"BDFileUpload({int(time.time()*1000)})",
                    "X-Amz-Date": amz_date,
                    "X-Amz-Expires": "31536000",
                    "X-Amz-Security-Token": creds["session_token"],
                    "accept-encoding": "identity",
                    "store-country-code": self.loc.lower(),
                    "store-country-code-src": "uid",
                    "tdid": self.tdid,
                    "pf": self.pf,
                }
                resp = self.http.post(commit_url, headers=commit_headers, data=commit_body.encode("utf-8"), timeout=60)
                commit_res = resp.json()
                commit_results = commit_res.get("Result", {}).get("Results", [])
                if not commit_results:
                    raise RuntimeError(f"CommitUploadInner thất bại: {commit_res}")

                final_vid = commit_results[0].get("Vid") or vid
                meta = commit_results[0].get("VideoMeta", {})
                duration_sec = float(meta.get("Duration") or 0.0)
                duration_ms = int(duration_sec * 1000)
                _log(f"[+] Audio đã lưu trữ TOS: VID={final_vid} ({duration_sec:.2f}s)")
                return final_vid, duration_ms

            except Exception as exc:
                if attempt < max_retries:
                    wait_s = min(30, 5 * attempt)
                    _log(f"[!] Upload TOS gặp lỗi ({exc}). Đang chờ {wait_s}s thử lại lần {attempt + 1}/{max_retries}...")
                    time.sleep(wait_s)
                else:
                    raise exc

    def _execute_separation_task(
        self,
        vid: str,
        duration_ms: int,
        output_wav: str,
        separate_type: str = "human",
        log_cb: Optional[Callable[[str], None]] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        max_task_retries: int = 8,
    ) -> str:
        """
        Creates AI task (type=6), polls for completion with resilient error handling,
        and downloads isolated vocal WAV.
        """
        def _log(msg: str):
            if log_cb:
                log_cb(msg)

        def _prog(pct: int, msg: str):
            if progress_cb:
                progress_cb(pct, msg)

        _log(f"[*] Bắt đầu tác vụ AI tách vocal (type=6, separate_type='{separate_type}')...")
        _prog(10, "Đang gửi yêu cầu tách vocal lên AI Cloud...")

        babi = {
            "feature_entrance": "editor",
            "feature_entrance_detail": "editor-feature-audio-sound_separation",
            "feature_key": "sound_separation",
            "scenario": "video_editor",
        }

        poll_query = {
            "device_brand": "American Megatrends Inc.",
            "device_id": self.device_id,
            "iid": self.iid,
            "aid": self.aid,
            "region": self.loc,
            "device_platform": "windows",
            "babi_param": compact_json(babi),
            "app_name": "CapCut",
            "device_type": "",
            "channel": self.channel,
            "os_version": "10.0.26100",
            "version_code": self.appvr,
            "version_name": self.appvr,
        }
        query_url = f"https://editor-api-sg.capcutapi.com/lv/v1/common_task/query?{urlencode(poll_query)}"

        for retry_idx in range(1, max_task_retries + 1):
            try:
                task_uuid = str(uuid.uuid4())
                batch_uuid = str(uuid.uuid4())
                ctx_uuid = str(uuid.uuid4())
                mat_uuid = str(uuid.uuid4())

                inner_payload = compact_json({
                    "audio_duration": duration_ms,
                    "enable_trim": False,
                    "material_list": [
                        {
                            "format": {"input": "wav", "output": "wav"},
                            "id": mat_uuid,
                            "source": vid,
                            "source_type": "vid_origin",
                            "type": "audio",
                        }
                    ],
                    "separate_type": separate_type,
                })

                new_body = {
                    "bind_id": task_uuid,
                    "can_queue": True,
                    "enter_from": "vc_sound_separate",
                    "tasks": [
                        {
                            "batch_task_id": batch_uuid,
                            "context": ctx_uuid,
                            "payload": inner_payload,
                            "type": 6,
                        }
                    ],
                }
                body_text = compact_json(new_body)

                q_params = {
                    "aid": self.aid,
                    "region": self.loc,
                    "device_platform": "windows",
                    "babi_param": compact_json(babi),
                }
                new_url = f"https://editor-api-sg.capcutapi.com/lv/v1/common_task/new?{urlencode(q_params)}"
                resp = self.http.post(new_url, headers=self._get_pc_headers(new_url, body_text), data=body_text.encode("utf-8"), timeout=35)
                new_res = resp.json()
                if new_res.get("ret") != "0":
                    err_msg = new_res.get("errmsg") or new_res.get("message") or str(new_res)
                    raise RuntimeError(f"Tạo task tách vocal thất bại (ret={new_res.get('ret')}): {err_msg}")

                tasks = new_res.get("data", {}).get("tasks", [])
                if not tasks:
                    raise RuntimeError(f"Không nhận được task info từ server: {new_res}")

                task_info = tasks[0]
                task_id = task_info["id"]
                token = task_info.get("token")
                _log(f"[+] Task ID tách vocal: {task_id}")

                # Polling loop (max 180 attempts * 2.5s = 450s = 7.5 phút)
                query_body = {"tasks": [{"id": task_id}]}
                if token:
                    query_body["tasks"][0]["token"] = token
                query_body_text = compact_json(query_body)

                download_url = None
                max_attempts = 180

                for attempt in range(1, max_attempts + 1):
                    time.sleep(2.5)
                    try:
                        q_resp = self.http.post(
                            query_url,
                            headers=self._get_pc_headers(query_url, query_body_text),
                            data=query_body_text.encode("utf-8"),
                            timeout=30,
                        )
                        q_res = q_resp.json()
                    except Exception as net_err:
                        _log(f"[~] Polling #{attempt} gặp lỗi mạng ({net_err}), tiếp tục đợi...")
                        continue

                    tasks_q = q_res.get("data", {}).get("tasks", [])
                    if not tasks_q:
                        continue

                    t = tasks_q[0]
                    status = t.get("status")
                    progress = t.get("progress", 0)
                    calc_pct = min(90, 15 + int(progress * 0.75))
                    _prog(calc_pct, f"AI đang bóc tách giọng nói ({progress}%)...")

                    if status in ("succeed", "success"):
                        task_payload = json.loads(t.get("payload", "{}"))
                        mat_list = task_payload.get("material_list", [])
                        if mat_list:
                            download_url = mat_list[0].get("source")
                            _log("[+] AI đã tách vocal thành công trên Cloud!")
                            break
                    elif status == "failed":
                        err_code = t.get("err_code")
                        err_msg = t.get("err_msg", "")
                        raise RuntimeError(f"ByteDance AI báo lỗi tách vocal (Code {err_code}): {err_msg}")

                if not download_url:
                    raise TimeoutError(f"Hết thời gian chờ phản hồi từ AI Vocal Separation ({max_attempts * 2.5:.0f}s).")

                # Download result
                _prog(92, "Đang tải audio vocal sạch về máy...")
                _log(f"[*] Đang tải vocal sạch từ CDN về: {output_wav}")
                Path(output_wav).parent.mkdir(parents=True, exist_ok=True)

                dl_success = False
                for dl_try in range(1, 4):
                    try:
                        dl_resp = self.http.get(download_url, stream=True, timeout=120)
                        dl_resp.raise_for_status()
                        with open(output_wav, "wb") as f:
                            for chunk in dl_resp.iter_content(chunk_size=65536):
                                f.write(chunk)
                        if os.path.exists(output_wav) and os.path.getsize(output_wav) > 1024:
                            dl_success = True
                            break
                    except Exception as dl_err:
                        _log(f"[!] Lỗi tải file từ CDN ({dl_err}), thử lại lần {dl_try}/3...")
                        time.sleep(3)

                if not dl_success:
                    raise RuntimeError("Tải vocal sạch từ CDN thất bại sau 3 lần thử.")

                _prog(100, "Hoàn tất tách vocal!")
                _log(f"[+] Đã lưu file vocal: {output_wav} ({os.path.getsize(output_wav):,} bytes)")
                return output_wav

            except Exception as exc:
                if retry_idx < max_task_retries:
                    wait_sec = min(60, 10 + (retry_idx - 1) * 10)
                    _log(f"[!] Lỗi tác vụ tách vocal ({exc}). Đang chờ {wait_sec}s để hồi phục rate limit rồi thử lại lần {retry_idx + 1}/{max_task_retries}...")
                    time.sleep(wait_sec)
                else:
                    raise exc

    def separate_audio(
        self,
        audio_wav_path: str,
        output_wav: Optional[str] = None,
        separate_type: str = "human",
        log_cb: Optional[Callable[[str], None]] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """
        Process audio file with automatic chunking if duration > 14 minutes (840s).
        Uses safe 5-minute (300s) slices with persistent retries and safe cooldowns.
        NEVER silently falls back to unseparated original audio.
        """
        def _log(msg: str):
            if log_cb:
                log_cb(msg)

        def _prog(pct: int, msg: str):
            if progress_cb:
                progress_cb(pct, msg)

        total_duration = get_audio_duration(audio_wav_path)
        if not output_wav:
            out_dir = DEFAULT_OUTPUT_DIR / "temp_vocals"
            out_dir.mkdir(parents=True, exist_ok=True)
            output_wav = str(out_dir / f"vocals_{int(time.time()*1000)}.wav")

        MAX_SEGMENT_SEC = 300.0  # 5 minutes per segment: fast, robust, and safe for SAMI gateway

        # Case 1: Audio <= 14 minutes -> single task with persistent retries
        if total_duration <= 840.0:
            _log(f"[*] Audio thời lượng: {total_duration:.2f}s (<= 14 phút) -> Xử lý trực tiếp 1 task duy nhất")
            max_single_tries = 8
            for single_try in range(1, max_single_tries + 1):
                try:
                    vid, duration_ms = self._upload_wav_to_tos(audio_wav_path, log_cb=_log)
                    if duration_ms <= 0:
                        duration_ms = int(total_duration * 1000)
                    return self._execute_separation_task(
                        vid=vid,
                        duration_ms=duration_ms,
                        output_wav=output_wav,
                        separate_type=separate_type,
                        log_cb=_log,
                        progress_cb=_prog,
                        max_task_retries=5,
                    )
                except Exception as s_err:
                    if single_try < max_single_tries:
                        wait_sec = min(60, 10 + (single_try - 1) * 10)
                        _log(f"[!] Lỗi tách vocal ({s_err}). Đang đợi {wait_sec}s thử lại lần {single_try + 1}/{max_single_tries}...")
                        time.sleep(wait_sec)
                    else:
                        raise RuntimeError(f"Tách vocal thất bại sau {max_single_tries} lần thử kiên trì: {s_err}")

        # Case 2: Audio > 14 minutes -> slice into segments <= 5 mins each, process and concat
        _log(f"[*] Audio thời lượng: {total_duration:.2f}s (> 14 phút) -> Tự động chia thành các đoạn 5 phút để bảo đảm ổn định")
        temp_dir = Path(output_wav).parent / f"slices_{int(time.time()*1000)}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        sliced_parts = []
        cur_pos = 0.0
        idx = 1
        while cur_pos < total_duration:
            seg_dur = min(MAX_SEGMENT_SEC, total_duration - cur_pos)
            part_wav = str(temp_dir / f"part_{idx:03d}.wav")
            slice_audio(audio_wav_path, cur_pos, seg_dur, part_wav)
            sliced_parts.append((part_wav, cur_pos, seg_dur))
            cur_pos += seg_dur
            idx += 1

        total_parts = len(sliced_parts)
        _log(f"[+] Đã chia thành {total_parts} phân đoạn audio (mỗi đoạn tối đa 5 phút).")

        vocal_results = []
        for i, (p_wav, p_start, p_dur) in enumerate(sliced_parts, 1):
            _log(f"[*] [Phân đoạn {i}/{total_parts}] Đang tải lên và xử lý tách vocal...")
            _prog(int((i - 1) / total_parts * 85), f"Đang tách vocal phân đoạn {i}/{total_parts}...")
            v_part_out = str(temp_dir / f"vocal_part_{i:03d}.wav")

            seg_success = False
            max_seg_attempts = 10
            for seg_attempt in range(1, max_seg_attempts + 1):
                try:
                    p_vid, p_dur_ms = self._upload_wav_to_tos(p_wav, log_cb=_log, max_retries=4)
                    if p_dur_ms <= 0:
                        p_dur_ms = int(p_dur * 1000)
                    self._execute_separation_task(
                        vid=p_vid,
                        duration_ms=p_dur_ms,
                        output_wav=v_part_out,
                        separate_type=separate_type,
                        log_cb=_log,
                        progress_cb=lambda p, m: _prog(min(90, int((i - 1) / total_parts * 85) + int(p / total_parts * 0.85)), m),
                        max_task_retries=4,
                    )
                    if os.path.exists(v_part_out) and os.path.getsize(v_part_out) > 4096:
                        seg_success = True
                        break
                    else:
                        raise RuntimeError("File vocal sau khi tải về bị rỗng hoặc không hợp lệ.")
                except Exception as seg_err:
                    if seg_attempt < max_seg_attempts:
                        backoff = min(60, 10 + (seg_attempt - 1) * 10)
                        _log(f"[!] Phân đoạn {i}/{total_parts} gặp sự cố ({seg_err}). Đang chờ {backoff}s để hồi phục rate limit rồi thử lại lần {seg_attempt + 1}/{max_seg_attempts} (kiên trì xử lý để đảm bảo không dùng audio gốc)...")
                        time.sleep(backoff)
                    else:
                        raise RuntimeError(f"Phân đoạn {i}/{total_parts} thất bại hoàn toàn sau {max_seg_attempts} lần thử kiên trì: {seg_err}")

            if not seg_success:
                raise RuntimeError(f"Không thể tách vocal cho phân đoạn {i}/{total_parts}.")

            vocal_results.append(v_part_out)
            _log(f"[+] Phân đoạn {i}/{total_parts} hoàn tất thành công! Nghỉ an toàn 8s trước phân đoạn tiếp theo...")
            time.sleep(8)

        # Concatenate back to full file
        _log("[*] Đang ghép nối các phân đoạn vocal thành file hoàn chỉnh...")
        _prog(95, "Đang ghép nối các đoạn vocal...")
        concat_wav_files(vocal_results, output_wav)

        # Clean up temporary sliced files
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        _prog(100, "Hoàn tất tách vocal video dài!")
        _log(f"[+] Đã ghép nối thành công file vocal hoàn chỉnh: {output_wav}")
        return output_wav

    def separate_video(
        self,
        video_path: str,
        output_wav: Optional[str] = None,
        separate_type: str = "human",
        log_cb: Optional[Callable[[str], None]] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
    ) -> str:
        """
        High-level wrapper: Extracts audio from video -> runs vocal separation -> returns isolated vocal WAV.
        """
        def _log(msg: str):
            if log_cb:
                log_cb(msg)

        def _prog(pct: int, msg: str):
            if progress_cb:
                progress_cb(pct, msg)

        _log(f"[*] Trích xuất âm thanh từ video: {Path(video_path).name}")
        _prog(5, "Đang trích xuất audio từ video...")

        out_dir = DEFAULT_OUTPUT_DIR / "temp_vocals"
        out_dir.mkdir(parents=True, exist_ok=True)
        temp_input_wav = str(out_dir / f"raw_audio_{int(time.time()*1000)}.wav")

        extract_audio_to_wav(video_path, temp_input_wav)

        try:
            result_wav = self.separate_audio(
                audio_wav_path=temp_input_wav,
                output_wav=output_wav,
                separate_type=separate_type,
                log_cb=_log,
                progress_cb=_prog,
            )
            return result_wav
        finally:
            if Path(temp_input_wav).exists():
                try:
                    Path(temp_input_wav).unlink()
                except Exception:
                    pass
