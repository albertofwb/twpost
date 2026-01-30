#!/usr/bin/env python3
"""
Twitter 互动功能模块
- 点赞 / 取消点赞
- 收藏 / 取消收藏
"""

import re
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from chrome_utils import CDP_URL, ensure_chrome_cdp


def extract_tweet_id(url: str) -> str | None:
    """从 URL 提取推文 ID"""
    match = re.search(r"/status/(\d+)", url)
    return match.group(1) if match else None


def like_tweet(url: str) -> bool:
    """点赞推文"""
    if not ensure_chrome_cdp():
        return False

    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        print(f"❌ 无效的推文 URL: {url}")
        return False

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"❌ 无法连接 CDP ({CDP_URL}): {e}")
            return False

        context = browser.contexts[0]
        page = context.new_page()

        try:
            print(f"📍 导航到推文页面...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector('[data-testid="like"]', timeout=30000)
            time.sleep(1)

            # 检查是否已点赞
            unlike_btn = page.locator('[data-testid="unlike"]').first
            
            if unlike_btn.count() > 0:
                print("⚠️ 这条推文已经点过赞了")
                return True

            print("❤️ 点赞中...")
            like_btn = page.locator('[data-testid="like"]').first
            like_btn.click()
            time.sleep(1)

            # 验证点赞成功
            if page.locator('[data-testid="unlike"]').count() > 0:
                print("✅ 点赞成功！")
                return True
            else:
                print("❌ 点赞可能失败")
                return False

        except PlaywrightTimeout as e:
            print(f"❌ 超时: {e}")
            return False
        except Exception as e:
            print(f"❌ 错误: {e}")
            return False
        finally:
            page.close()


def unlike_tweet(url: str) -> bool:
    """取消点赞"""
    if not ensure_chrome_cdp():
        return False

    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        print(f"❌ 无效的推文 URL: {url}")
        return False

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"❌ 无法连接 CDP ({CDP_URL}): {e}")
            return False

        context = browser.contexts[0]
        page = context.new_page()

        try:
            print(f"📍 导航到推文页面...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)

            unlike_btn = page.locator('[data-testid="unlike"]').first
            
            if unlike_btn.count() == 0:
                print("⚠️ 这条推文没有点过赞")
                return True

            print("💔 取消点赞中...")
            unlike_btn.click()
            time.sleep(1)

            print("✅ 取消点赞成功！")
            return True

        except PlaywrightTimeout as e:
            print(f"❌ 超时: {e}")
            return False
        except Exception as e:
            print(f"❌ 错误: {e}")
            return False
        finally:
            page.close()


def bookmark_tweet(url: str) -> bool:
    """收藏推文"""
    if not ensure_chrome_cdp():
        return False

    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        print(f"❌ 无效的推文 URL: {url}")
        return False

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"❌ 无法连接 CDP ({CDP_URL}): {e}")
            return False

        context = browser.contexts[0]
        page = context.new_page()

        try:
            print(f"📍 导航到推文页面...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector('[data-testid="bookmark"]', timeout=30000)
            time.sleep(1)

            # 检查是否已收藏
            unbookmark_btn = page.locator('[data-testid="removeBookmark"]').first
            
            if unbookmark_btn.count() > 0:
                print("⚠️ 这条推文已经收藏过了")
                return True

            print("🔖 收藏中...")
            bookmark_btn = page.locator('[data-testid="bookmark"]').first
            bookmark_btn.click()
            time.sleep(1)

            # 验证收藏成功
            if page.locator('[data-testid="removeBookmark"]').count() > 0:
                print("✅ 收藏成功！")
                return True
            else:
                print("❌ 收藏可能失败")
                return False

        except PlaywrightTimeout as e:
            print(f"❌ 超时: {e}")
            return False
        except Exception as e:
            print(f"❌ 错误: {e}")
            return False
        finally:
            page.close()


def unbookmark_tweet(url: str) -> bool:
    """取消收藏"""
    if not ensure_chrome_cdp():
        return False

    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        print(f"❌ 无效的推文 URL: {url}")
        return False

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"❌ 无法连接 CDP ({CDP_URL}): {e}")
            return False

        context = browser.contexts[0]
        page = context.new_page()

        try:
            print(f"📍 导航到推文页面...")
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)

            unbookmark_btn = page.locator('[data-testid="removeBookmark"]').first
            
            if unbookmark_btn.count() == 0:
                print("⚠️ 这条推文没有收藏过")
                return True

            print("🗑️ 取消收藏中...")
            unbookmark_btn.click()
            time.sleep(1)

            print("✅ 取消收藏成功！")
            return True

        except PlaywrightTimeout as e:
            print(f"❌ 超时: {e}")
            return False
        except Exception as e:
            print(f"❌ 错误: {e}")
            return False
        finally:
            page.close()
