#!/usr/bin/env python3
"""
测试提取单条推文的详细信息
从 tweets_xhr_test.json 读取一条推文，打开详情页分析
"""

import asyncio
import json
import sys
from playwright.async_api import async_playwright

async def main():
    # 读取之前抓到的推文数据
    try:
        with open('tweets_xhr_test.json', 'r', encoding='utf-8') as f:
            tweets = json.load(f)
    except FileNotFoundError:
        print("❌ 找不到 tweets_xhr_test.json，请先运行 tw_xhr_test.py")
        return
    
    if not tweets:
        print("❌ JSON 文件为空")
        return
    
    # 取第一条推文
    tweet = tweets[0]
    tweet_id = tweet['id']
    
    print(f"📝 测试推文:")
    print(f"   ID: {tweet_id}")
    print(f"   内容: {tweet['text'][:100]}...")
    print(f"   点赞: {tweet['favorite_count']} | 转发: {tweet['retweet_count']}")
    
    # 构造推文 URL
    # Twitter URL 格式: https://twitter.com/i/web/status/{tweet_id}
    # 或: https://x.com/任意用户名/status/{tweet_id}
    tweet_url = f"https://x.com/i/status/{tweet_id}"
    print(f"\n🌐 推文链接: {tweet_url}")
    
    async with async_playwright() as p:
        # 连接到已有的 Chrome
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        except Exception as e:
            print(f"❌ 无法连接到 Chrome CDP: {e}")
            return
        
        contexts = browser.contexts
        if contexts:
            context = contexts[0]
            pages = context.pages
            page = pages[0] if pages else await context.new_page()
        else:
            print("❌ 没有可用的浏览器上下文")
            return
        
        print(f"\n📄 当前页面: {page.url}")
        
        # 设置 XHR 监听
        captured_data = {}
        
        async def handle_response(response):
            url = response.url
            # 监听推文详情 API
            if 'TweetDetail' in url or 'TweetResultByRestId' in url:
                content_type = response.headers.get('content-type', '')
                if 'json' in content_type:
                    print(f"\n🎯 捕获详情 API: ...{url[-80:]}")
                    try:
                        body = await response.text()
                        data = json.loads(body)
                        captured_data['detail'] = data
                        print(f"✅ 捕获到详情数据 ({len(body)} 字符)")
                    except Exception as e:
                        print(f"  ❌ 解析失败: {e}")
        
        page.on('response', handle_response)
        
        # 打开推文详情页
        print(f"\n🚀 打开推文详情页...")
        try:
            await page.goto(tweet_url, wait_until='networkidle', timeout=15000)
            print("✅ 页面加载完成")
        except Exception as e:
            print(f"⚠️  导航超时或失败: {e}")
            print("  继续分析...")
        
        # 等待一下，确保数据加载
        await asyncio.sleep(2)
        
        # 分析捕获的数据
        if 'detail' in captured_data:
            print("\n📊 分析详情数据...")
            detail = captured_data['detail']
            
            # 保存原始数据
            with open('tweet_detail_raw.json', 'w', encoding='utf-8') as f:
                json.dump(detail, f, ensure_ascii=False, indent=2)
            print("💾 原始数据已保存到 tweet_detail_raw.json")
            
            # 尝试提取关键信息
            try:
                # Twitter API 响应结构很复杂，我们需要递归查找
                def find_tweet_data(obj, path=""):
                    """递归查找推文数据"""
                    if isinstance(obj, dict):
                        # 查找推文对象
                        if obj.get('__typename') == 'Tweet':
                            return obj
                        # 递归查找
                        for key, value in obj.items():
                            result = find_tweet_data(value, f"{path}.{key}")
                            if result:
                                return result
                    elif isinstance(obj, list):
                        for i, item in enumerate(obj):
                            result = find_tweet_data(item, f"{path}[{i}]")
                            if result:
                                return result
                    return None
                
                tweet_obj = find_tweet_data(detail)
                
                if tweet_obj:
                    print("\n✅ 找到推文对象！")
                    
                    # 提取用户信息 - 尝试多个可能的路径
                    legacy = tweet_obj.get('legacy', {})
                    core_user = tweet_obj.get('core', {})
                    user_results = core_user.get('user_results', {})
                    user_result = user_results.get('result', {})
                    user_legacy = user_result.get('legacy', {})
                    user_core = user_result.get('core', {})
                    
                    extracted = {
                        'tweet_id': tweet_id,
                        'text': legacy.get('full_text', ''),
                        'user': {
                            'name': user_core.get('name', '') or user_legacy.get('name', ''),
                            'screen_name': user_core.get('screen_name', '') or user_legacy.get('screen_name', ''),
                            'description': user_legacy.get('description', ''),
                            'followers_count': user_legacy.get('followers_count', 0),
                            'friends_count': user_legacy.get('friends_count', 0),
                        },
                        'created_at': legacy.get('created_at', ''),
                        'favorite_count': legacy.get('favorite_count', 0),
                        'retweet_count': legacy.get('retweet_count', 0),
                        'reply_count': legacy.get('reply_count', 0),
                        'quote_count': legacy.get('quote_count', 0),
                    }
                    
                    print("\n📋 提取的信息:")
                    print(f"  用户: {extracted['user']['name']} (@{extracted['user']['screen_name']})")
                    print(f"  简介: {extracted['user']['description'][:80]}...")
                    print(f"  粉丝: {extracted['user']['followers_count']} | 关注: {extracted['user']['friends_count']}")
                    print(f"  内容: {extracted['text'][:100]}...")
                    print(f"  点赞: {extracted['favorite_count']} | 转发: {extracted['retweet_count']} | 回复: {extracted['reply_count']}")
                    
                    # 保存提取的数据
                    with open('tweet_detail_extracted.json', 'w', encoding='utf-8') as f:
                        json.dump(extracted, f, ensure_ascii=False, indent=2)
                    print("\n💾 已保存到 tweet_detail_extracted.json")
                    
                else:
                    print("⚠️  未找到推文对象，数据结构可能不同")
                    print("   请查看 tweet_detail_raw.json 分析结构")
                    
            except Exception as e:
                print(f"❌ 提取信息失败: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("\n⚠️  未捕获到详情 API 响应")
            print("   可能推文已在当前页面，或需要等待更长时间")

if __name__ == '__main__':
    asyncio.run(main())
