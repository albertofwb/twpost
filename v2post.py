#!/usr/bin/env python3
"""CLI tool to post topics on V2EX via Chrome CDP."""

import argparse
import subprocess
import socket
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"


def is_port_open(port: int) -> bool:
    """Check if a port is open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_chrome_cdp():
    """Ensure Chrome is running with CDP enabled."""
    if is_port_open(CDP_PORT):
        return True

    print(f"CDP 端口 {CDP_PORT} 未开启，正在重启 Chrome...")

    # Kill existing Chrome processes (force kill)
    subprocess.run(["pkill", "-9", "-f", "chrome"], capture_output=True)
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


def post_v2ex(title: str, content: str, node: str = "share") -> bool:
    """Post a topic on V2EX using Chrome CDP connection."""
    if not ensure_chrome_cdp():
        return False

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"无法连接 CDP ({CDP_URL}): {e}")
            print("请确保 Chrome 已启动并开启了远程调试端口")
            return False

        context = browser.contexts[0]
        page = context.new_page()

        try:
            # 导航到发帖页面
            new_topic_url = f"https://www.v2ex.com/new/{node}"
            print(f"导航到 V2EX 发帖页面: {new_topic_url}")
            page.goto(new_topic_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)

            # 检查是否需要登录
            if page.locator('input[name="u"]').count() > 0:
                print("请先在 Chrome 中登录 V2EX")
                return False

            # 选择 Markdown 编辑器（selectboxit 下拉组件）
            print("选择 Markdown 格式...")
            try:
                # 点击下拉按钮打开选项
                dropdown_btn = page.locator('#select_syntaxSelectBoxIt')
                dropdown_btn.click()
                time.sleep(0.3)
                # 选择 Markdown 选项 (data-val="1")
                markdown_option = page.locator('li[data-val="1"]')
                markdown_option.click()
                time.sleep(0.5)
            except Exception as e:
                print(f"选择 Markdown 失败: {e}")

            # 填写标题
            print("填写标题...")
            title_input = page.locator('#topic_title')
            title_input.wait_for(timeout=10000)
            title_input.click()
            title_input.fill(title)
            time.sleep(0.5)

            # 填写内容
            print("填写内容...")
            content_input = page.locator('#topic_content')
            content_input.click()
            content_input.fill(content)
            time.sleep(0.5)

            # 点击发布按钮
            print("发布主题...")
            submit_btn = page.locator('button[type="submit"]:has-text("创建")')
            submit_btn.click()
            time.sleep(3)  # 等待发布完成

            # 检查是否成功（URL 应该变成主题页面）
            current_url = page.url
            if "/t/" in current_url:
                print(f"发布成功！主题链接: {current_url}")
                return True
            else:
                print("发布可能失败，请检查页面状态")
                return False

        except PlaywrightTimeout as e:
            print(f"超时: {e}")
            return False
        except Exception as e:
            print(f"错误: {e}")
            return False
        finally:
            page.close()


def main():
    parser = argparse.ArgumentParser(
        description="V2EX 发帖 CLI 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  v2post -t "标题" -c "内容"                    # 发到默认节点 (share)
  v2post -t "标题" -c "内容" -n python          # 发到 python 节点
  v2post -t "标题" -c "内容" -n programmer      # 发到 programmer 节点

常用节点:
  share       - 分享发现
  python      - Python
  programmer  - 程序员
  jobs        - 酷工作
  qna         - 问与答
  apple       - Apple
  create      - 分享创造
        """,
    )
    parser.add_argument("-t", "--title", required=True, help="主题标题")
    parser.add_argument("-c", "--content", required=True, help="主题内容")
    parser.add_argument("-n", "--node", default="share", help="节点名称 (默认: share)")

    args = parser.parse_args()

    if not args.title.strip():
        print("标题不能为空")
        sys.exit(1)

    if not args.content.strip():
        print("内容不能为空")
        sys.exit(1)

    success = post_v2ex(args.title, args.content, node=args.node)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
