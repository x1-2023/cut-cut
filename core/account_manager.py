#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
capcut_account_manager.py - CapCut Pro Account Pool & Automated Rotation
Manages multiple CapCut accounts, tracks VIP/Pro expiration timestamps,
and handles 1-click automatic switching/rotation using CapCutAutoLogin.
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

sys.stdout.reconfigure(encoding="utf-8")

from core.auth import CapCutAuth
# from core.auto_login import CapCutAutoLogin

from config.settings import ACCOUNTS_FILE


class CapCutAccountManager:
    """Manages CapCut Pro accounts repository and automatic rotation."""

    def __init__(self, filepath: Optional[Path] = None):
        self.filepath = filepath or ACCOUNTS_FILE
        self.accounts: List[Dict[str, Any]] = []
        self.load_accounts()

    def load_accounts(self):
        """Load accounts from JSON storage. Seeds default account if file is empty."""
        if not self.filepath.exists():
            # Seed default user account
            self.accounts = [
                {
                    "email": "moehingletito854@outlook.com",
                    "password": "capcutpro2026",
                    "is_active": True,
                    "note": "Tài khoản Pro chính",
                    "user_id": "7661639738788955144",
                    "screen_name": "user121842414877",
                    "is_pro": True,
                    "pro_expire_time": 1790405329,
                    "last_checked": int(time.time()),
                }
            ]
            self.save_accounts()
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self.accounts = json.load(f)
        except Exception:
            self.accounts = []

    def save_accounts(self):
        """Save account list to disk."""
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.accounts, f, indent=2, ensure_ascii=False)

    def get_active_account(self) -> Optional[Dict[str, Any]]:
        """Return currently active account."""
        for acc in self.accounts:
            if acc.get("is_active"):
                return acc
        if self.accounts:
            self.accounts[0]["is_active"] = True
            self.save_accounts()
            return self.accounts[0]
        return None

    def list_accounts(self) -> List[Dict[str, Any]]:
        """Return list of all registered accounts."""
        return list(self.accounts)

    def add_account(
        self,
        email: str,
        password: str,
        note: str = "",
        auto_login_now: bool = False,
        status_callback: Optional[callable] = None,
    ) -> Tuple[bool, str]:
        """Add new account to pool, optionally logging in immediately."""
        email = email.strip()
        password = password.strip()
        if not email or not password:
            return False, "Email và mật khẩu không được để trống."

        # Check existing
        for acc in self.accounts:
            if acc["email"].lower() == email.lower():
                acc["password"] = password
                acc["note"] = note or acc.get("note", "")
                self.save_accounts()
                if auto_login_now:
                    return self.switch_account(email, status_callback=status_callback)
                return True, f"Đã cập nhật tài khoản: {email}"

        new_acc = {
            "email": email,
            "password": password,
            "is_active": len(self.accounts) == 0,
            "note": note,
            "user_id": "",
            "screen_name": "",
            "is_pro": False,
            "pro_expire_time": 0,
            "last_checked": 0,
        }
        self.accounts.append(new_acc)
        self.save_accounts()

        if auto_login_now:
            return self.switch_account(email, status_callback=status_callback)
        return True, f"Đã thêm tài khoản: {email}"

    def remove_account(self, email: str) -> bool:
        """Remove an account by email."""
        initial_len = len(self.accounts)
        self.accounts = [a for a in self.accounts if a["email"].lower() != email.lower()]
        if len(self.accounts) < initial_len:
            if not any(a.get("is_active") for a in self.accounts) and self.accounts:
                self.accounts[0]["is_active"] = True
            self.save_accounts()
            return True
        return False

    def switch_account(
        self,
        target_email: str,
        headless: bool = False,
        status_callback: Optional[callable] = None,
    ) -> Tuple[bool, str]:
        """
        Switches active account to target_email, automatically logs in via Playwright,
        retrieves cookies, and updates session.
        """
        target_acc = None
        for acc in self.accounts:
            if acc["email"].lower() == target_email.lower():
                target_acc = acc
                break

        if not target_acc:
            return False, f"Không tìm thấy tài khoản {target_email} trong danh sách."

        if status_callback:
            status_callback(f"[*] Đang chuyển sang tài khoản: {target_email}...")

        auto_login = CapCutAutoLogin()
        ok, msg, data = auto_login.login_with_credentials(
            email=target_acc["email"],
            password=target_acc["password"],
            headless=headless,
            status_callback=status_callback,
        )

        if ok:
            for acc in self.accounts:
                acc["is_active"] = (acc["email"].lower() == target_email.lower())

            target_acc["user_id"] = data.get("user_id", "")
            target_acc["screen_name"] = data.get("screen_name", "")
            target_acc["is_pro"] = data.get("is_pro", False)
            target_acc["pro_expire_time"] = data.get("pro_expire_time", 0)
            target_acc["last_checked"] = int(time.time())
            self.save_accounts()
            return True, f"Đã chuyển và đăng nhập thành công: {target_email}"
        else:
            return False, f"Lỗi đăng nhập: {msg}"

    def refresh_active_account(self, status_callback: Optional[callable] = None) -> Tuple[bool, str]:
        """Re-login active account to refresh cookies."""
        active = self.get_active_account()
        if not active:
            return False, "Chưa có tài khoản nào được kích hoạt."
        return self.switch_account(active["email"], status_callback=status_callback)

    @staticmethod
    def format_pro_remaining(expire_timestamp: int) -> str:
        """Format remaining time until Pro expiration."""
        if not expire_timestamp:
            return "N/A"
        diff_sec = expire_timestamp - int(time.time())
        if diff_sec <= 0:
            return "ĐÃ HẾT HẠN PRO!"
        days = diff_sec // 86400
        hours = (diff_sec % 86400) // 3600
        mins = (diff_sec % 3600) // 60
        if days > 0:
            return f"Còn {days} ngày {hours} giờ"
        if hours > 0:
            return f"Còn {hours} giờ {mins} phút"
        return f"Còn {mins} phút (Sắp hết hạn!)"

    def is_expiring_soon(self, threshold_hours: int = 24) -> bool:
        """Check if current active account will expire within threshold hours."""
        active = self.get_active_account()
        if not active or not active.get("is_pro") or not active.get("pro_expire_time"):
            return False
        diff_sec = active["pro_expire_time"] - int(time.time())
        return 0 < diff_sec <= (threshold_hours * 3600)


def main():
    mgr = CapCutAccountManager()
    active = mgr.get_active_account()
    print("=== CAPCUT ACCOUNT MANAGER ===")
    print(f"Total accounts: {len(mgr.list_accounts())}")
    if active:
        print(f"Active Account: {active['email']} (UID: {active.get('user_id')})")
        print(f"Pro Status:     {'PRO / VIP' if active.get('is_pro') else 'FREE'}")
        print(f"Remaining:      {mgr.format_pro_remaining(active.get('pro_expire_time', 0))}")


if __name__ == "__main__":
    main()
