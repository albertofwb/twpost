#!/usr/bin/env python3
"""
测试拦截 Twitter XHR 请求获取推文数据
用 CDP 监听网络请求，捕获 Twitter API 响应
"""

import asyncio
import json
import sys
from playwright.async_api import async_playwright

# Twitter API 相关的 URL 模式
TWITTER_API_PATTERNS = [
    'api.twitter.com',
    'HomeTimeline',
    'HomeLatestTimeline', 
    'UserTweets',
    'TweetDetail'
]

captured_tweets = []

async def should_capture(url: str) -> bool:
    """判断是否应该捕获这个请求"""
    return any(pattern in url for pattern in TWITTER_API_PATTERNS)

async def parse_twitter_response(response_body: str) -> list:
    """解析 Twitter API 响应，提取推文"""
    try:
        data = json.loads(response_body)
        tweets = []
        
        # Twitter API 响应结构：data.home.home_timeline_urt.instructions
        if 'data' in data:
            # 遍历可能的嵌套结构
            for key, value in data.get('data', {}).items():
                if isinstance(value, dict):
                    instructions = value.get('instructions', [])
                    for instruction in instructions:
                        if instruction.get('type') == 'TimelineAddEntries':
                            entries = instruction.get('entries', [])
                            for entry in entries:
                                content = entry.get('content', {})
                                if content.get('entryType') == 'TimelineTimelineItem':
                                    item_content = content.get('itemContent', {})
                                    if item_content.get('itemType') == 'TimelineTweet':
                                        tweet_results = item_content.get('tweet_results', {})
                                        result = tweet_results.get('result', {})
                                        if result.get('__typename') == 'Tweet':
                                            legacy = result.get('legacy', {})
                                            user = result.get('core', {}).get('user_results', {}).get('result', {}).get('legacy', {})
                                            
                                            tweet = {
                                                'text': legacy.get('full_text', ''),
                                                'user_name': user.get('name', ''),
                                                'screen_name': user.get('screen_name', ''),
                                                'created_at': legacy.get('created_at', ''),
                                                'favorite_count': legacy.get('favorite_count', 0),
                                                'retweet_count': legacy.get('retweet_count', 0),
                                                'id': legacy.get('id_str', ''),
                                            }
                                            tweets.append(tweet)
        
        return tweets
    except Exception as e:
        print(f"❌ 解析响应失败: {e}", file=sys.stderr)
        return []

async def main():
    print("🚀 启动 Twitter XHR 拦截测试...")
    
    async with async_playwright() as p:
        # 连接到已有的 Chrome (端口 9222)
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"❌ 无法连接到 Chrome CDP (localhost:9222): {e}")
            print("请先运行: google-chrome --remote-debugging-port=9222")
            return
        
        # 使用第一个已有页面或创建新页面
        contexts = browser.contexts
        if contexts:
            context = contexts[0]
            pages = context.pages
            if pages:
                page = pages[0]
            else:
                page = await context.new_page()
        else:
            print("❌ 没有可用的浏览器上下文")
            return
        
        print(f"📄 使用页面: {page.url}")
        
        # 启用网络监听
        async def handle_response(response):
            url = response.url
            if await should_capture(url):
                print(f"\n🎯 捕获到 API 请求: {url[:100]}...")
                try:
                    body = await response.text()
                    tweets = await parse_twitter_response(body)
                    if tweets:
                        print(f"✅ 提取到 {len(tweets)} 条推文")
                        for tweet in tweets:
                            print(f"  📝 @{tweet['screen_name']}: {tweet['text'][:50]}...")
                            captured_tweets.append(tweet)
                    else:
                        print("⚠️  没有提取到推文数据")
                        # 调试：打印部分响应
                        if len(body) > 200:
                            print(f"  响应预览: {body[:200]}...")
                except Exception as e:
                    print(f"  ❌ 处理响应失败: {e}")
        
        page.on('response', handle_response)
        
        # 打开 Twitter
        print("\n🌐 导航到 Twitter...")
        try:
            await page.goto('https://twitter.com/home', wait_until='networkidle', timeout=30000)
        except Exception as e:
            print(f"⚠️  导航超时或失败: {e}")
            print("  (可能已经在 Twitter 页面，继续监听...)")
        
        # 等待一段时间收集数据
        print("\n⏳ 监听 30 秒，滚动页面可触发更多请求...")
        await asyncio.sleep(30)
        
        # 输出结果
        print(f"\n\n📊 总共捕获 {len(captured_tweets)} 条推文")
        
        if captured_tweets:
            print("\n💾 保存到 tweets_xhr_test.json")
            with open('tweets_xhr_test.json', 'w', encoding='utf-8') as f:
                json.dump(captured_tweets, f, ensure_ascii=False, indent=2)
            
            # 打印前 3 条
            print("\n📋 示例推文:")
            for i, tweet in enumerate(captured_tweets[:3], 1):
                print(f"\n{i}. @{tweet['screen_name']} ({tweet['created_at']})")
                print(f"   {tweet['text'][:100]}...")
                print(f"   ❤️ {tweet['favorite_count']} | 🔁 {tweet['retweet_count']}")

if __name__ == '__main__':
    asyncio.run(main())
