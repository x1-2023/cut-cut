#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_auto_login.py - Automated CapCut Login & Cookie Harvester via Playwright
Automates opening https://www.capcut.com/login, filling email + password,
handling security/captcha steps, capturing full session cookies, and saving session.
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

sys.stdout.reconfigure(encoding="utf-8")

from core.auth import CapCutAuth

logger = logging.getLogger("CapCutAutoLogin")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class CapCutAutoLogin:
    """Automates Playwright browser interaction for CapCut account login & cookie extraction."""

    def __init__(self, auth: Optional[CapCutAuth] = None):
        self.auth = auth or CapCutAuth()

    def login_with_credentials(
        self,
        email: str,
        password: str,
        headless: bool = False,
        timeout_sec: int = 90,
        status_callback: Optional[callable] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Automates login using Email + Password.
        Launches browser (headless=False by default to allow manual drag of puzzle captcha if shown).
        Returns: (success: bool, message: str, session_data: dict)
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            msg = "Playwright chưa được cài đặt. Chạy: pip install playwright && playwright install chromium"
            if status_callback:
                status_callback(msg)
            return False, msg, {}

        def notify(txt: str):
            logger.info(txt)
            if status_callback:
                status_callback(txt)

        notify(f"[*] Bắt đầu tiến trình tự động đăng nhập: {email}")

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=headless)
            except Exception:
                try:
                    browser = p.chromium.launch(channel="chrome", headless=headless)
                except Exception as e:
                    return False, f"Không thể khởi chạy trình duyệt: {e}", {}

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="vi-VN",
            )
            page = context.new_page()

            try:
                notify("[*] Đang truy cập trang đăng nhập CapCut...")
                page.goto("https://www.capcut.com/login", wait_until="domcontentloaded", timeout=45000)
                time.sleep(2)

                # Step 1: Click 'Continue with email'
                notify("[*] Chọn hình thức: Đăng nhập bằng Email...")
                email_btn = page.locator('text="Continue with email"').first
                if email_btn.count() == 0:
                    email_btn = page.locator('text=/continue with email|tiếp tục với email/i').first

                if email_btn.count() > 0:
                    email_btn.click()
                    time.sleep(1.5)

                # Step 2: Fill Email
                notify(f"[*] Điền email: {email}...")
                email_inp = page.locator('input[placeholder*="email" i], input[type="email"], input[name="username"]').first
                if email_inp.count() == 0:
                    email_inp = page.locator('input').first

                email_inp.fill(email)
                time.sleep(1)

                # Step 3: Click Continue
                notify("[*] Bấm 'Continue'...")
                cont_btn = page.locator('button:has-text("Continue"), [role="button"]:has-text("Continue"), button:has-text("Tiếp tục")').first
                cont_btn.click()
                time.sleep(2.5)

                # Step 4: Fill Password
                notify("[*] Điền mật khẩu...")
                pwd_inp = page.locator('input[type="password"], input[placeholder*="password" i], input[name="password"]').first
                if pwd_inp.count() == 0:
                    pwd_inp = page.locator('input').last

                pwd_inp.fill(password)
                time.sleep(1)

                # Step 5: Click Sign In
                notify("[*] Bấm 'Sign in' để hoàn tất đăng nhập...")
                signin_btn = page.locator('button:has-text("Sign in"), [role="button"]:has-text("Sign in"), button:has-text("Đăng nhập")').first
                signin_btn.click()

                notify("[*] Đang chờ xác thực phiên và bắt giữ Cookie...")
                notify("    (Nếu màn hình hiện câu đố ghép hình/Captcha, vui lòng kéo thanh trượt trên cửa sổ trình duyệt)")

                # Step 6: Monitor for sessionid or sid_guard cookie
                start_time = time.time()
                logged_in = False
                captured_cookies: Dict[str, str] = {}

                while time.time() - start_time < timeout_sec:
                    cookies = context.cookies(["https://www.capcut.com", "https://edit-api-sg.capcut.com"])
                    c_dict = {c["name"]: c["value"] for c in cookies}

                    if "sessionid" in c_dict or "sid_guard" in c_dict:
                        notify("[+] Phát hiện đăng nhập thành công! Đang lưu trữ toàn bộ token...")
                        time.sleep(3)  # wait for all tokens and tickets to settle
                        cookies = context.cookies(["https://www.capcut.com", "https://edit-api-sg.capcut.com"])
                        captured_cookies = {c["name"]: c["value"] for c in cookies}
                        logged_in = True
                        break

                    time.sleep(1)

                browser.close()

                if not logged_in:
                    return False, f"Hết thời gian chờ xác thực ({timeout_sec}s). Không lấy được cookie.", {}

                # Step 7: Update and verify with CapCut Auth
                notify("[*] Đồng bộ trạng thái tài khoản với máy chủ CapCut...")
                self.auth.set_cookies(captured_cookies)
                self.auth.email = email
                self.auth.save_session()

                ok = self.auth.sync_all()
                if not ok:
                    return False, "Bắt được cookie nhưng API CapCut từ chối xác thực.", {}

                expire_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.auth.pro_expire_time)) if self.auth.pro_expire_time else "N/A"
                pro_status = f"PRO / VIP (Hạn: {expire_str})" if self.auth.is_pro else "FREE"
                success_msg = f"Đăng nhập thành công! UID: {self.auth.user_id} | {pro_status}"
                notify(f"[+] {success_msg}")

                result_data = {
                    "user_id": self.auth.user_id,
                    "screen_name": self.auth.screen_name,
                    "email": email,
                    "is_pro": self.auth.is_pro,
                    "pro_expire_time": self.auth.pro_expire_time,
                    "workspace_id": self.auth.workspace_id,
                    "space_id": self.auth.space_id,
                }
                return True, success_msg, result_data

            except Exception as exc:
                try:
                    browser.close()
                except Exception:
                    pass
                err_msg = f"Lỗi trong quá trình tự động đăng nhập: {exc}"
                notify(f"[-] {err_msg}")
                return False, err_msg, {}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CapCut Automated Login via Playwright")
    parser.add_argument("--email", "-e", type=str, default="moehingletito854@outlook.com", help="Email đăng nhập CapCut")
    parser.add_argument("--password", "-p", type=str, default="capcutpro2026", help="Mật khẩu đăng nhập")
    parser.add_argument("--headless", action="store_true", help="Chạy ẩn trình duyệt (không hiện cửa sổ)")
    parser.add_argument("--timeout", type=int, default=90, help="Thời gian chờ tối đa (giây)")
    args = parser.parse_args()

    auto = CapCutAutoLogin()
    ok, msg, data = auto.login_with_credentials(
        email=args.email,
        password=args.password,
        headless=args.headless,
        timeout_sec=args.timeout,
    )
    if ok:
        print("\n" + "=" * 60)
        print("[+] HOÀN TẤT TỰ ĐỘNG LẤY COOKIE CAPCUT!")
        print(f"    UID:        {data.get('user_id')}")
        print(f"    Gói Pro:    {'CÓ (PRO/VIP)' if data.get('is_pro') else 'KHÔNG (FREE)'}")
        print(f"    Hạn dùng:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data.get('pro_expire_time', 0)))}")
        print("=" * 60)
    else:
        print(f"\n[-] THẤT BẠI: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
