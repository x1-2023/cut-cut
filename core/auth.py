#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_auth.py - CapCut Web Session & Authentication Manager
Handles session persistence, 1-click browser login via Playwright, manual cookie import,
account verification, workspace resolution, and Pro/VIP status.
"""

import os
import sys
import time
import json
import uuid
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

sys.stdout.reconfigure(encoding="utf-8")

from config.settings import SESSION_FILE, APP_ID, APP_VERSION

class CapCutAuth:
    """Manages CapCut Web authentication, session tokens, and workspace metadata."""

    def __init__(self, session_path: Optional[Path] = None):
        self.session_path = session_path or SESSION_FILE
        self.aid = str(APP_ID)
        self.pf = "7"  # Web platform
        self.appvr = "5.8.0"
        self.sdk_version = "48.0.0"
        self.account_sdk_version = "2.1.10-tiktok"

        self.device_id = ""
        self.webid = ""
        self.cookies_dict: Dict[str, str] = {}
        self.user_id: str = ""
        self.screen_name: str = ""
        self.email: str = ""
        self.workspace_id: str = ""
        self.space_id: str = ""
        self.is_pro: bool = False
        self.pro_expire_time: int = 0

        self.load_session()

    # --------------------------------------------------------------------------
    # Cryptographic Signing & Headers
    # --------------------------------------------------------------------------
    def _make_sign(self, url: str, device_time: str, appvr: Optional[str] = None) -> str:
        """Calculate exact CapCut Web MD5 signature: 9e2c|<path[-7:]>|7|<appvr>|<time>||11ac"""
        pathname = urllib.parse.urlsplit(url).path
        ver = appvr or self.appvr
        sign_parts = ["9e2c", pathname[-7:], self.pf, ver, str(device_time), "", "11ac"]
        sign_str = "|".join(sign_parts)
        return hashlib.md5(sign_str.encode("utf-8")).hexdigest().lower()

    def get_cookie_header(self) -> str:
        """Return formatted Cookie header string."""
        return "; ".join(f"{k}={v}" for k, v in self.cookies_dict.items())

    def _build_headers(self, url: str, extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Build standard HTTP request headers required by CapCut Web API."""
        now = str(int(time.time()))
        appvr_to_use = (extra_headers.get("appvr") if extra_headers else None) or self.appvr
        headers = {
            "Cookie": self.get_cookie_header(),
            "Origin": "https://www.capcut.com",
            "Referer": "https://www.capcut.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "pf": self.pf,
            "appvr": appvr_to_use,
            "sign-ver": "1",
            "app-sdk-version": self.sdk_version,
            "device-time": now,
            "tdid": "",
            "store-country-code": "vn",
            "store-country-code-src": "uid",
            "sign": self._make_sign(url, now, appvr=appvr_to_use),
        }
        if self.webid:
            headers["web_id"] = self.webid
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _request(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        timeout: int = 60,
        retries: int = 3,
    ) -> Dict[str, Any]:
        """Execute JSON HTTP request with configurable timeout and retry logic."""
        data = json.dumps(body).encode("utf-8") if body is not None else None
        last_exc = None
        for attempt in range(max(1, retries)):
            headers = self._build_headers(url, extra_headers)
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    self._update_cookies_from_response(resp)
                    return json.loads(raw)
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="ignore")
                if 400 <= exc.code < 500 and exc.code != 429:
                    raise RuntimeError(f"HTTP {exc.code} for {url}: {err_body}") from exc
                last_exc = RuntimeError(f"HTTP {exc.code} for {url}: {err_body}")
            except Exception as exc:
                last_exc = exc

            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))

        raise RuntimeError(f"Request failed for {url}: {last_exc}") from last_exc

    def _update_cookies_from_response(self, resp: Any):
        """Update cookie store from Set-Cookie headers."""
        raw_headers = resp.headers.get_all("Set-Cookie") if hasattr(resp.headers, "get_all") else []
        headers = raw_headers or []
        for cookie_str in headers:
            parts = cookie_str.split(";")[0].split("=", 1)
            if len(parts) == 2:
                name, val = parts[0].strip(), parts[1].strip()
                self.cookies_dict[name] = val

    # --------------------------------------------------------------------------
    # Cookie & Session Management
    # --------------------------------------------------------------------------
    @staticmethod
    def parse_cookie_string(cookie_str: str) -> Dict[str, str]:
        """Parse raw cookie string into dictionary."""
        cookies = {}
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                cookies[k.strip()] = v.strip()
        return cookies

    def set_cookies(self, cookie_input: str | Dict[str, str]):
        """Set cookies from either raw string or dict."""
        if isinstance(cookie_input, str):
            self.cookies_dict = self.parse_cookie_string(cookie_input)
        elif isinstance(cookie_input, dict):
            self.cookies_dict = dict(cookie_input)

        if not self.device_id:
            self.device_id = str(uuid.uuid4().int)[:19]
        if not self.webid:
            self.webid = str(uuid.uuid4().int)[:19]

    def save_session(self):
        """Persist session metadata and cookies to disk."""
        data = {
            "device_id": self.device_id,
            "webid": self.webid,
            "user_id": self.user_id,
            "screen_name": self.screen_name,
            "email": self.email,
            "workspace_id": self.workspace_id,
            "space_id": self.space_id,
            "is_pro": self.is_pro,
            "pro_expire_time": self.pro_expire_time,
            "cookies": self.cookies_dict,
            "updated_at": int(time.time()),
        }
        with open(self.session_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[+] Session saved to: {self.session_path}")

    def load_session(self) -> bool:
        """Load session from disk if exists."""
        if not self.session_path.exists():
            return False
        try:
            with open(self.session_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.device_id = data.get("device_id") or str(uuid.uuid4().int)[:19]
            self.webid = data.get("webid") or str(uuid.uuid4().int)[:19]
            self.user_id = data.get("user_id", "")
            self.screen_name = data.get("screen_name", "")
            self.email = data.get("email", "")
            self.workspace_id = data.get("workspace_id", "")
            self.space_id = data.get("space_id", "")
            self.is_pro = data.get("is_pro", False)
            self.pro_expire_time = data.get("pro_expire_time", 0)
            self.cookies_dict = data.get("cookies", {})
            return bool(self.cookies_dict)
        except Exception:
            return False

    # --------------------------------------------------------------------------
    # 1-Click Interactive Browser Login (Playwright)
    # --------------------------------------------------------------------------
    def browser_login(self, timeout_sec: int = 180) -> bool:
        """Launch visible browser, wait for user login, and automatically save cookies."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[-] Playwright is not installed. Install via: pip install playwright && playwright install chromium")
            return False

        print("\n=======================================================")
        print("[*] ĐANG MỞ TRÌNH DUYỆT ĐỂ ĐĂNG NHẬP CAPCUT...")
        print("    Bạn có thể đăng nhập bằng Google, TikTok, Email hoặc quét mã QR.")
        print(f"    Chờ tối đa {timeout_sec} giây cho đến khi đăng nhập hoàn tất...")
        print("=======================================================\n")

        with sync_playwright() as p:
            # Launch visible chromium browser
            try:
                browser = p.chromium.launch(headless=False)
            except Exception:
                # Fallback to system chrome
                browser = p.chromium.launch(channel="chrome", headless=False)

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()
            page.goto("https://www.capcut.com/login", wait_until="domcontentloaded")

            start_time = time.time()
            logged_in = False

            while time.time() - start_time < timeout_sec:
                cookies = context.cookies(["https://www.capcut.com", "https://edit-api-sg.capcut.com"])
                c_dict = {c["name"]: c["value"] for c in cookies}

                # CapCut sets sessionid or sid_guard upon successful authentication
                if "sessionid" in c_dict or "sid_guard" in c_dict:
                    print("\n[+] Phát hiện phiên đăng nhập thành công!")
                    time.sleep(3)  # wait for all tokens to settle
                    # Grab latest refreshed cookies
                    cookies = context.cookies(["https://www.capcut.com", "https://edit-api-sg.capcut.com"])
                    self.set_cookies({c["name"]: c["value"] for c in cookies})
                    self.save_session()
                    logged_in = True
                    break

                time.sleep(1)

            browser.close()

            if not logged_in:
                print("[-] Quá thời gian chờ đăng nhập.")
                return False

            print("[*] Đang đồng bộ thông tin tài khoản và workspace...")
            return self.sync_all()

    # --------------------------------------------------------------------------
    # Authentication & Profile Verification
    # --------------------------------------------------------------------------
    def verify_session(self) -> Tuple[bool, Dict[str, Any]]:
        """Verify current cookies by querying account info endpoint."""
        if not self.cookies_dict:
            return False, {"error": "No cookies configured."}

        url = f"https://www.capcut.com/passport/web/account/info/?aid={self.aid}&account_sdk_source=web&sdk_version={self.account_sdk_version}&language=vi-VN"
        try:
            res = self._request("GET", url)
            user_data = res.get("data", {})
            uid = str(user_data.get("user_id") or user_data.get("user_id_str") or "")
            if uid and uid != "0":
                self.user_id = uid
                self.screen_name = user_data.get("screen_name", "")
                self.email = user_data.get("email", "")
                return True, user_data
            return False, {"error": "Session invalid or expired", "raw": res}
        except Exception as exc:
            return False, {"error": str(exc)}

    # --------------------------------------------------------------------------
    # Workspaces & Subscriptions
    # --------------------------------------------------------------------------
    def fetch_workspaces(self) -> List[Dict[str, Any]]:
        """Fetch all workspaces associated with current account."""
        url = "https://edit-api-sg.capcut.com/cc/v1/workspace/get_user_workspaces"
        payload = {"cursor": "0", "count": 50, "need_convert_workspace": True}
        res = self._request("POST", url, payload)
        infos = res.get("data", {}).get("workspace_infos", [])
        if infos and not self.workspace_id:
            self.workspace_id = infos[0]["workspace_id"]
            self.space_id = infos[0].get("space_id", "")
        return infos

    def fetch_subscription(self) -> Dict[str, Any]:
        """Fetch Pro/VIP subscription details."""
        url = "https://commerce-api-sg.capcut.com/commerce/v1/subscription/user_info"
        payload = {"aid": self.aid, "scene": "vip"}
        try:
            res = self._request("POST", url, payload)
            resp_str = res.get("response", "{}")
            info = json.loads(resp_str) if isinstance(resp_str, str) else resp_str
            self.is_pro = bool(info.get("flag", False))
            self.pro_expire_time = int(info.get("end_time", 0))
            return info
        except Exception:
            return {"flag": False}

    def fetch_storage_quota(self) -> Dict[str, Any]:
        """Fetch cloud storage capacity for workspace."""
        if not self.workspace_id:
            return {}
        url = "https://commerce-api-sg.capcut.com/commerce/v1/subscription/workspace/space_list"
        payload = {"aid": int(self.aid), "workspace_id": self.workspace_id}
        try:
            res = self._request("POST", url, payload)
            resp_str = res.get("response", "{}")
            return json.loads(resp_str) if isinstance(resp_str, str) else resp_str
        except Exception:
            return {}

    # --------------------------------------------------------------------------
    # Sync All & Status Report
    # --------------------------------------------------------------------------
    def sync_all(self) -> bool:
        """Run full check: account -> workspaces -> subscription -> save session."""
        ok, acc_info = self.verify_session()
        if not ok:
            print(f"[-] Session verification failed: {acc_info.get('error')}")
            return False

        print(f"[+] Đã đăng nhập: {self.screen_name} (UID: {self.user_id})")
        if self.email:
            print(f"    Email: {self.email}")
        self.save_session()

        # Fetch Workspaces
        workspaces = self.fetch_workspaces()
        print(f"[+] Tìm thấy {len(workspaces)} workspace:")
        for ws in workspaces:
            active_mark = " (MẶC ĐỊNH)" if ws.get("workspace_id") == self.workspace_id else ""
            print(f"    - [{ws.get('workspace_id')}] {ws.get('name')} | Role: {ws.get('role')}{active_mark}")

        # Fetch Pro
        sub = self.fetch_subscription()
        if self.is_pro:
            expire_dt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.pro_expire_time))
            print(f"[+] Gói tài khoản: PRO / VIP (Hạn dùng: {expire_dt})")
        else:
            print("[+] Gói tài khoản: FREE (Miễn phí)")

        # Fetch Storage
        quota = self.fetch_storage_quota()
        if "space_list" in quota and quota["space_list"]:
            space = quota["space_list"][0]
            capacity_gb = space.get("space_capacity", 0) / (1024**3)
            print(f"[+] Dung lượng Cloud: {capacity_gb:.1f} GB")

        self.save_session()
        return True


def main():
    import argparse

    parser = argparse.ArgumentParser(description="CapCut Web Authentication Manager")
    parser.add_argument("--login", action="store_true", help="Mở trình duyệt đăng nhập 1 lần và tự động lưu cookie")
    parser.add_argument("--set-cookie", type=str, help="Chuỗi cookie thủ công từ DevTools")
    parser.add_argument("--cookie-file", type=str, help="Đường dẫn file text chứa chuỗi cookie")
    parser.add_argument("--status", action="store_true", help="Kiểm tra trạng thái session hiện tại")
    parser.add_argument("--workspace", type=str, help="Chọn workspace ID mặc định")
    args = parser.parse_args()

    auth = CapCutAuth()

    if args.login:
        if auth.browser_login():
            print("\n[+] ĐĂNG NHẬP VÀ LƯU SESSION THÀNH CÔNG! Các tool sau sẽ tự động sử dụng session này.")
        else:
            sys.exit(1)
        return

    if args.set_cookie:
        auth.set_cookies(args.set_cookie)
        if args.workspace:
            auth.workspace_id = args.workspace
        print("[*] Đang xác thực cookie cung cấp...")
        if auth.sync_all():
            print("\n[+] Xác thực THÀNH CÔNG! Session đã được lưu.")
        else:
            sys.exit(1)
        return

    if args.cookie_file:
        path = Path(args.cookie_file)
        if not path.exists():
            print(f"[-] Không tìm thấy file: {path}")
            sys.exit(1)
        raw_cookie = path.read_text(encoding="utf-8").strip()
        auth.set_cookies(raw_cookie)
        if args.workspace:
            auth.workspace_id = args.workspace
        print(f"[*] Đang xác thực cookie từ file {path}...")
        if auth.sync_all():
            print("\n[+] Xác thực THÀNH CÔNG! Session đã được lưu.")
        else:
            sys.exit(1)
        return

    # Default / Status mode
    if auth.load_session():
        print(f"[*] Đã tìm thấy session lưu tại: {auth.session_path}")
        if args.workspace:
            auth.workspace_id = args.workspace
        if auth.sync_all():
            print("\n[+] Session đang HOẠT ĐỘNG tốt. Sẵn sàng cho Phase Upload / Draft / Render.")
        else:
            print("\n[-] Session đã hết hạn. Vui lòng đăng nhập lại:")
            print("    py -3.14 capcut_auth.py --login")
            print("    hoặc: py -3.14 capcut_auth.py --set-cookie \"...\"")
            sys.exit(1)
    else:
        print("[-] Chưa có session nào được lưu. Có thể đăng nhập bằng 2 cách:")
        print("  Cách 1 (Khuyên dùng - Tự động 100%):")
        print("    py -3.14 capcut_auth.py --login")
        print("    (Lệnh này sẽ mở trình duyệt để bạn đăng nhập Google/TikTok/QR, tự động tóm cookie lưu vĩnh viễn)")
        print("\n  Cách 2 (Thủ công):")
        print('    py -3.14 capcut_auth.py --set-cookie "sessionid=...; sid_guard=..."')
        print("    hoặc lưu chuỗi cookie vào file và chạy:")
        print("    py -3.14 capcut_auth.py --cookie-file capcut_cookie.txt")
        sys.exit(1)


if __name__ == "__main__":
    main()
