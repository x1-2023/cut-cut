@echo off
title CapCut Automation Studio Pro
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================================
echo   Khởi động CapCut Automation Studio Pro...
echo ===================================================

where py >nul 2>nul
if %errorlevel% equ 0 (
    py run_gui.py
) else (
    python run_gui.py
)

if %errorlevel% neq 0 (
    echo.
    echo [!] Gặp lỗi khi chạy ứng dụng. Nhấn phím bất kỳ để thoát...
    pause >nul
)
