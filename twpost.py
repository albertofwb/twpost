#!/usr/bin/env python3
"""CLI tool to post tweets via Chrome CDP."""

import argparse
import sys
import time
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from chrome_utils import CDP_URL, ensure_chrome_cdp


def extract_tweet_id(url: str) -> str | None:
    """Extract tweet ID from URL."""
    match = re.search(r"/status/(\d+)", url)
    return match.group(1) if match else None


def wait_and_click(page, selector: str, timeout: int = 10000):
    """Wait for element and click it."""
    element = page.wait_for_selector(selector, timeout=timeout)
    element.click()
    return element


def post_tweet(text: str, reply_to: str | None = None, image: str | None = None) -> bool:
    """Post a tweet using Chrome CDP connection."""
    if not ensure_chrome_cdp():
        return False

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"❌ 无法连接 CDP ({CDP_URL}): {e}")
            print("请确保 Chrome 已启动并开启了远程调试端口")
            return False

        context = browser.contexts[0]
        page = context.new_page()

        try:
            if reply_to:
                # 回复模式：先导航到推文页面
                tweet_id = extract_tweet_id(reply_to)
                if not tweet_id:
                    print(f"❌ 无效的推文 URL: {reply_to}")
                    return False

                print(f"📍 导航到推文页面...")
                page.goto(reply_to, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_selector('[data-testid="reply"]', timeout=30000)
                time.sleep(1)

                # 点击回复按钮
                print("💬 点击回复...")
                reply_btn = page.locator('[data-testid="reply"]').first
                reply_btn.click()
                time.sleep(1)

            else:
                # 发新推文：去首页
                print("📍 导航到 X 首页...")
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_selector('[data-testid="tweetTextarea_0"]', timeout=30000)
                time.sleep(1)

            # 找到输入框
            print("✍️  输入内容...")
            editor = page.locator('[data-testid="tweetTextarea_0"]').first
            editor.click()
            time.sleep(0.5)
            editor.fill(text)
            time.sleep(0.5)

            # 上传图片（如果有）
            if image:
                image_path = Path(image).expanduser().resolve()
                if not image_path.exists():
                    print(f"❌ 图片不存在: {image_path}")
                    return False

                print(f"🖼️  上传图片: {image_path}")
                file_input = page.locator('input[type="file"][accept*="image"]').first
                file_input.set_input_files(str(image_path))
                time.sleep(2)  # 等待上传

            # 点击发送按钮
            print("🚀 发送推文...")
            if reply_to:
                send_btn = page.locator('[data-testid="tweetButton"]').first
            else:
                send_btn = page.locator('[data-testid="tweetButtonInline"]').first

            send_btn.click()
            time.sleep(3)  # 等待发送完成

            print("✅ 发送成功！")
            return True

        except PlaywrightTimeout as e:
            print(f"❌ 超时: {e}")
            return False
        except Exception as e:
            print(f"❌ 错误: {e}")
            return False
        finally:
            pass  # 保持页面打开


def main():
    parser = argparse.ArgumentParser(
        description="发推文 CLI 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  twpost "Hello World!"                          # 发新推文
  twpost --reply URL "回复内容"                  # 回复推文
  twpost --image photo.jpg "带图推文"            # 带图片
  twpost --reply URL --image pic.png "带图回复"  # 带图回复
        """,
    )
    parser.add_argument("text", help="推文内容")
    parser.add_argument("-r", "--reply", metavar="URL", help="要回复的推文 URL")
    parser.add_argument("-i", "--image", metavar="FILE", help="要附加的图片")

    args = parser.parse_args()

    if not args.text.strip():
        print("❌ 推文内容不能为空")
        sys.exit(1)

    success = post_tweet(args.text, reply_to=args.reply, image=args.image)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
