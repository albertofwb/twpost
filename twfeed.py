#!/usr/bin/env python3
"""
Twitter 时间线抓取 + 互动工具
- 刷推：截图 + PaddleOCR 提取内容
- 互动：点赞/收藏推文
- 数据库：可选保存到 PostgreSQL
"""

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from chrome_utils import CDP_URL, ensure_chrome_cdp
from twitter_actions import like_tweet, unlike_tweet, bookmark_tweet, unbookmark_tweet
from tweet_db import save_ocr_result, get_recent_tweets


# 页面类型映射
FEED_TYPES = {
    "home": "https://x.com/home",
    "likes": "https://x.com/zimablue56/likes",  # 需要用户名
    "bookmarks": "https://x.com/i/bookmarks",
    "notifications": "https://x.com/notifications",
    "mentions": "https://x.com/notifications/mentions",  # @提及和回复
    "following": "https://x.com/home?filter=following",  # Following tab
}

FEED_NAMES = {
    "home": "时间线",
    "likes": "点赞",
    "bookmarks": "书签",
    "notifications": "通知",
    "mentions": "提及/回复",
    "following": "关注",
}

# 默认使用高分辨率，一次看更多内容
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 4000  # 高纵向分辨率

# PaddleOCR 脚本路径
PADDLE_OCR_DIR = Path.home() / "paddle-ocr"


def run_paddle_ocr(image_path: str) -> str | None:
    """调用 PaddleOCR 识别图片（默认纯文本输出）"""
    try:
        result = subprocess.run(
            ["uv", "run", "python", "ocr.py", image_path],
            cwd=PADDLE_OCR_DIR,
            capture_output=True,
            text=True,
            timeout=60,
            env={
                **dict(__import__("os").environ),
                "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True"
            }
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"❌ OCR 失败: {result.stderr}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"❌ OCR 错误: {e}", file=sys.stderr)
        return None


def capture_feed(
    feed_type: str = "home",
    scroll_times: int = 1,
    output_image: str | None = None,
    username: str | None = None,
    height: int = DEFAULT_HEIGHT,
    save_to_db: bool = False,
) -> str | None:
    """
    截取 Twitter 页面并用 PaddleOCR 提取文字
    
    Args:
        feed_type: 页面类型 (home/likes/bookmarks/notifications/following)
        scroll_times: 滚动次数，加载更多内容
        output_image: 可选，保存截图的路径
        username: 用户名（用于 likes 页面）
        height: viewport 高度
        save_to_db: 是否保存到数据库
    
    Returns:
        OCR 提取的文字内容，失败返回 None
    """
    total_start = time.time()
    timings = {}
    
    if not ensure_chrome_cdp():
        return None

    # 获取 URL
    if feed_type == "likes" and username:
        url = f"https://x.com/{username}/likes"
    else:
        url = FEED_TYPES.get(feed_type, FEED_TYPES["home"])
    
    feed_name = FEED_NAMES.get(feed_type, feed_type)

    with sync_playwright() as p:
        step_start = time.time()
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"❌ 无法连接 CDP ({CDP_URL}): {e}", file=sys.stderr)
            return None
        timings['cdp_connect'] = time.time() - step_start

        context = browser.contexts[0]
        page = context.new_page()
        
        # 设置大的 viewport 高度
        page.set_viewport_size({"width": DEFAULT_WIDTH, "height": height})

        try:
            print(f"📍 导航到 Twitter {feed_name}...", file=sys.stderr)
            step_start = time.time()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # 等待内容加载
            try:
                page.wait_for_selector('[data-testid="tweet"]', timeout=30000)
            except PlaywrightTimeout:
                # 有些页面可能没有推文，尝试等待其他元素
                page.wait_for_selector('[data-testid="primaryColumn"]', timeout=10000)
            
            time.sleep(2)
            timings['navigation'] = time.time() - step_start
            
            # 滚动加载更多内容
            step_start = time.time()
            for i in range(scroll_times):
                print(f"📜 滚动加载 ({i + 1}/{scroll_times})...", file=sys.stderr)
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                time.sleep(1.5)
            
            # 滚动回顶部
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(0.5)
            timings['scrolling'] = time.time() - step_start
            
            # 截图
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                screenshot_path = f.name
            
            print("📸 截图中...", file=sys.stderr)
            step_start = time.time()
            page.screenshot(path=screenshot_path, full_page=False)
            timings['screenshot'] = time.time() - step_start
            
            # 保存截图（如果指定了路径）
            if output_image:
                import shutil
                shutil.copy(screenshot_path, output_image)
                print(f"💾 截图已保存: {output_image}", file=sys.stderr)
            
            # PaddleOCR 提取文字
            print("🔍 OCR 识别中 (PaddleOCR)...", file=sys.stderr)
            step_start = time.time()
            result = run_paddle_ocr(screenshot_path)
            timings['ocr'] = time.time() - step_start
            
            # 清理临时文件
            Path(screenshot_path).unlink(missing_ok=True)
            
            if not result:
                print("❌ OCR 未识别到文字", file=sys.stderr)
                return None
            
            # 打印计时统计
            timings['total'] = time.time() - total_start
            print(f"✅ OCR 完成", file=sys.stderr)
            print(f"⏱️  计时统计:", file=sys.stderr)
            print(f"   CDP连接: {timings.get('cdp_connect', 0):.2f}s", file=sys.stderr)
            print(f"   页面加载: {timings.get('navigation', 0):.2f}s", file=sys.stderr)
            print(f"   滚动加载: {timings.get('scrolling', 0):.2f}s", file=sys.stderr)
            print(f"   截图: {timings.get('screenshot', 0):.2f}s", file=sys.stderr)
            print(f"   OCR: {timings.get('ocr', 0):.2f}s", file=sys.stderr)
            print(f"   总计: {timings.get('total', 0):.2f}s", file=sys.stderr)
            
            # 保存到数据库
            if save_to_db:
                try:
                    saved_count, tweets = save_ocr_result(result)
                    print(f"💾 已保存 {saved_count} 条推文到数据库", file=sys.stderr)
                except Exception as e:
                    print(f"⚠️ 数据库保存失败: {e}", file=sys.stderr)
            
            return result

        except PlaywrightTimeout as e:
            print(f"❌ 超时: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"❌ 错误: {e}", file=sys.stderr)
            return None
        finally:
            page.close()


def main():
    parser = argparse.ArgumentParser(
        description="Twitter 刷推 + 互动工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  twfeed                         # 刷时间线
  twfeed -t bookmarks            # 刷书签
  twfeed -t likes                # 刷点赞
  twfeed -t mentions             # 查看@和回复
  twfeed --scroll 2              # 多滚动几次
  twfeed --image out.png         # 同时保存截图
  twfeed --height 6000           # 更大的纵向分辨率
  twfeed --save                  # 保存到数据库
  twfeed --list                  # 查看最近保存的推文
  
  twfeed like URL                # 点赞推文
  twfeed unlike URL              # 取消点赞
  twfeed bookmark URL            # 收藏推文
  twfeed unbookmark URL          # 取消收藏

页面类型 (-t/--type):
  home         首页时间线 (默认)
  following    关注的人
  likes        点赞
  bookmarks    书签/收藏
  notifications 通知
  mentions     @提及和回复
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="互动命令")
    
    # like 子命令
    like_parser = subparsers.add_parser("like", help="点赞推文")
    like_parser.add_argument("url", help="推文 URL")
    
    # unlike 子命令
    unlike_parser = subparsers.add_parser("unlike", help="取消点赞")
    unlike_parser.add_argument("url", help="推文 URL")
    
    # bookmark 子命令
    bookmark_parser = subparsers.add_parser("bookmark", help="收藏推文")
    bookmark_parser.add_argument("url", help="推文 URL")
    
    # unbookmark 子命令
    unbookmark_parser = subparsers.add_parser("unbookmark", help="取消收藏")
    unbookmark_parser.add_argument("url", help="推文 URL")
    
    # 刷推参数
    parser.add_argument("-t", "--type", choices=list(FEED_TYPES.keys()), default="home", help="页面类型")
    parser.add_argument("-u", "--user", metavar="USERNAME", default="zimablue56", help="用户名 (用于 likes)")
    parser.add_argument("-s", "--scroll", type=int, default=1, help="滚动次数 (默认 1)")
    parser.add_argument("-i", "--image", metavar="FILE", help="保存截图的路径")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help=f"viewport 高度 (默认 {DEFAULT_HEIGHT})")
    parser.add_argument("--save", action="store_true", help="保存推文到数据库")
    parser.add_argument("--list", action="store_true", dest="list_db", help="查看最近保存的推文")
    parser.add_argument("--headless", action="store_true", default=True, help="使用 Chrome headless 模式 (默认启用)")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="禁用 headless 模式，使用可见浏览器")

    args = parser.parse_args()
    
    # Set headless mode via environment variable
    if args.headless:
        import os
        os.environ["CHROME_HEADLESS"] = "1"

    # 处理互动命令
    if args.command == "like":
        success = like_tweet(args.url)
        sys.exit(0 if success else 1)
    elif args.command == "unlike":
        success = unlike_tweet(args.url)
        sys.exit(0 if success else 1)
    elif args.command == "bookmark":
        success = bookmark_tweet(args.url)
        sys.exit(0 if success else 1)
    elif args.command == "unbookmark":
        success = unbookmark_tweet(args.url)
        sys.exit(0 if success else 1)
    
    # 查看数据库中的推文
    if args.list_db:
        tweets = get_recent_tweets(20)
        if tweets:
            for t in tweets:
                content_preview = t['content'][:60].replace('\n', ' ') if t['content'] else ""
                print(f"[{t['scraped_at']}] {t['author']}: {content_preview}...")
                if t['likes'] or t['retweets'] or t['views']:
                    print(f"  ❤️ {t['likes'] or 0} 🔁 {t['retweets'] or 0} 👁️ {t['views'] or 0}")
        else:
            print("数据库中没有推文")
        sys.exit(0)
    
    # 默认：刷推
    text = capture_feed(
        feed_type=args.type,
        scroll_times=args.scroll,
        output_image=args.image,
        username=args.user,
        height=args.height,
        save_to_db=args.save,
    )
    
    if text:
        print(text)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
