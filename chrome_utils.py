#!/usr/bin/env python3
"""Chrome CDP utilities for browser automation."""

import socket
import subprocess
import time
from pathlib import Path


CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"


def is_port_open(port: int) -> bool:
    """Check if a port is open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_chrome_cdp() -> bool:
    """Ensure Chrome is running with CDP enabled."""
    if is_port_open(CDP_PORT):
        return True

    print(f"CDP 端口 {CDP_PORT} 未开启，正在重启 Chrome...")

    # Kill existing Chrome processes (force kill, exclude this script)
    subprocess.run(["pkill", "-9", "-f", "google-chrome"], capture_output=True)
    time.sleep(2)

    # Start Chrome with CDP using dedicated profile
    chrome_data_dir = Path(__file__).parent / ".chrome"
    subprocess.Popen(
        ["google-chrome", f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={chrome_data_dir}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for CDP to be ready
    for _ in range(3):
        time.sleep(1)
        if is_port_open(CDP_PORT):
            print("Chrome CDP 已就绪")
            time.sleep(2)  # Extra wait for full initialization
            return True

    print("Chrome 启动超时")
    return False


if __name__ == "__main__":
    import sys
    success = ensure_chrome_cdp()
    sys.exit(0 if success else 1)
