#!/usr/bin/env python3
"""
推文数据库保存模块
- 解析 OCR 结果，提取结构化推文数据
- 保存到 PostgreSQL 数据库
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values


# 数据库连接配置 (Docker PostgreSQL)
DB_CONFIG = {
    "host": "172.21.0.3",
    "port": 5432,
    "user": "cloudreve",
    "password": "",  # trust auth
    "database": "cloudreve",
}


@dataclass
class Tweet:
    """推文数据结构"""
    author: str  # @handle
    author_name: str  # 显示名
    content: str
    tweet_url: Optional[str] = None
    likes: Optional[int] = None
    retweets: Optional[int] = None
    views: Optional[int] = None
    created_at: Optional[datetime] = None
    voice_file: Optional[str] = None
    voice_text: Optional[str] = None
    is_liked: bool = False
    is_bookmarked: bool = False
    liked_at: Optional[datetime] = None
    bookmarked_at: Optional[datetime] = None
    # XHR 扩展字段
    tweet_id: Optional[str] = None
    reply_count: Optional[int] = None
    quote_count: Optional[int] = None
    user_followers: Optional[int] = None
    user_friends: Optional[int] = None
    user_description: Optional[str] = None
    data_source: str = "ocr"  # 'ocr' or 'xhr'
    raw_json: Optional[dict] = None


def parse_count(text: str) -> Optional[int]:
    """解析数字（支持 K/M 后缀）"""
    if not text:
        return None
    text = text.strip().upper().replace(",", "")
    try:
        if "K" in text:
            return int(float(text.replace("K", "")) * 1000)
        elif "M" in text:
            return int(float(text.replace("M", "")) * 1_000_000)
        else:
            return int(float(text))
    except (ValueError, TypeError):
        return None


def parse_ocr_to_tweets(ocr_text: str) -> list[Tweet]:
    """
    解析 OCR 文本，提取推文列表
    
    OCR 格式通常是：
    - 用户名和 @handle
    - 时间（如 "3h", "May 15"）
    - 正文内容
    - 互动数据（回复、转推、点赞、浏览量等）
    """
    tweets = []
    
    # 用正则匹配推文块
    # 典型模式: @handle · 时间
    # 或者: 显示名\n@handle
    
    # 按行分割
    lines = ocr_text.strip().split("\n")
    
    current_tweet = None
    content_lines = []
    
    # 匹配 @用户名 模式
    handle_pattern = re.compile(r"@([A-Za-z0-9_]+)")
    # 匹配互动数据模式（数字+K/M）
    stats_pattern = re.compile(r"^[\d,.]+[KMkm]?$")
    # 匹配时间模式
    time_pattern = re.compile(r"^\d+[hms]$|^\d+小时$|^[A-Z][a-z]{2}\s+\d+$|^\d{1,2}月\d{1,2}日$")
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # 跳过空行和噪音
        if not line or line in ["Following", "For you", "Show more", "..."]:
            i += 1
            continue
        
        # 检测新推文的开始：@handle 模式
        handle_match = handle_pattern.search(line)
        
        if handle_match and (
            line.startswith("@") or 
            "·" in line or
            (i > 0 and not lines[i-1].strip())  # 空行后的 @
        ):
            # 保存上一条推文
            if current_tweet and content_lines:
                current_tweet.content = "\n".join(content_lines).strip()
                if current_tweet.content:  # 只保存有内容的
                    tweets.append(current_tweet)
            
            # 开始新推文
            author = handle_match.group(1)
            author_name = ""
            
            # 尝试从上一行获取显示名
            if i > 0:
                prev_line = lines[i-1].strip()
                if prev_line and not handle_pattern.match(prev_line) and not stats_pattern.match(prev_line):
                    author_name = prev_line
            
            current_tweet = Tweet(
                author=f"@{author}",
                author_name=author_name,
                content=""
            )
            content_lines = []
            i += 1
            continue
        
        # 检测互动数据行
        if current_tweet and stats_pattern.match(line):
            # 可能是 likes/retweets/views
            # 通常按顺序出现，尝试解析
            count = parse_count(line)
            if count is not None:
                if current_tweet.views is None and count > 100:
                    current_tweet.views = count
                elif current_tweet.likes is None:
                    current_tweet.likes = count
                elif current_tweet.retweets is None:
                    current_tweet.retweets = count
            i += 1
            continue
        
        # 跳过时间戳行
        if time_pattern.match(line):
            i += 1
            continue
        
        # 累积内容
        if current_tweet:
            # 过滤掉一些 UI 噪音
            if line not in ["Reply", "Repost", "Like", "Share", "Bookmark", "Views", 
                           "回复", "转推", "喜欢", "分享", "书签", "浏览"]:
                content_lines.append(line)
        
        i += 1
    
    # 保存最后一条推文
    if current_tweet and content_lines:
        current_tweet.content = "\n".join(content_lines).strip()
        if current_tweet.content:
            tweets.append(current_tweet)
    
    return tweets


def tweet_from_xhr_json(data: dict) -> Tweet:
    """
    从 XHR 拦截的 JSON 数据构造 Tweet 对象
    
    Args:
        data: XHR 响应解析出的推文字典，支持两种格式：
            1. 嵌套格式: {"tweet_id": "...", "user": {...}, ...}
            2. 扁平格式: {"id": "...", "user_name": "...", "screen_name": "...", ...}
    
    Returns:
        Tweet 对象
    """
    from dateutil import parser as date_parser
    
    # 兼容两种数据格式
    user = data.get("user", {})
    tweet_id = data.get("tweet_id") or data.get("id")
    user_name = user.get("name", "") or data.get("user_name", "")
    screen_name = user.get("screen_name", "") or data.get("screen_name", "")
    user_description = user.get("description", "") or data.get("user_description", "")
    user_followers = user.get("followers_count") or data.get("user_followers")
    user_friends = user.get("friends_count") or data.get("user_friends")
    
    # 解析时间
    created_at = None
    if data.get("created_at"):
        try:
            created_at = date_parser.parse(data["created_at"])
        except:
            pass
    
    # 构造推文 URL
    tweet_url = None
    if tweet_id and screen_name:
        tweet_url = f"https://x.com/{screen_name}/status/{tweet_id}"
    
    return Tweet(
        tweet_id=tweet_id,
        author=f"@{screen_name}" if screen_name else "",
        author_name=user_name,
        content=data.get("text", ""),
        tweet_url=tweet_url,
        likes=data.get("favorite_count"),
        retweets=data.get("retweet_count"),
        reply_count=data.get("reply_count"),
        quote_count=data.get("quote_count"),
        user_followers=user_followers,
        user_friends=user_friends,
        user_description=user_description,
        created_at=created_at,
        data_source="xhr",
        raw_json=data
    )


def get_db_connection():
    """获取数据库连接"""
    return psycopg2.connect(**DB_CONFIG)


def save_tweets(tweets: list[Tweet]) -> int:
    """
    保存推文到数据库（支持 OCR 和 XHR 数据）
    
    Returns:
        成功保存的推文数量
    """
    if not tweets:
        return 0
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 准备数据
        data = []
        for t in tweets:
            # 将 raw_json 转为 JSON 字符串
            import json
            raw_json_str = json.dumps(t.raw_json) if t.raw_json else None
            
            data.append((
                t.author,
                t.author_name,
                t.content,
                t.tweet_url,
                t.voice_file,
                t.voice_text,
                t.likes,
                t.retweets,
                t.views,
                t.created_at,
                t.tweet_id,
                t.reply_count,
                t.quote_count,
                t.user_followers,
                t.user_friends,
                t.user_description,
                t.data_source,
                raw_json_str
            ))
        
        # 分离有 tweet_id 和没有 tweet_id 的数据
        data_with_id = [d for d in data if d[10] is not None]  # d[10] = tweet_id
        data_without_id = [d for d in data if d[10] is None]
        
        # 有 tweet_id 的使用 ON CONFLICT
        if data_with_id:
            sql_with_conflict = """
                INSERT INTO tweets 
                (author, author_name, content, tweet_url, voice_file, voice_text, 
                 likes, retweets, views, created_at,
                 tweet_id, reply_count, quote_count, user_followers, user_friends, 
                 user_description, data_source, raw_json)
                VALUES %s
                ON CONFLICT (tweet_id) 
                DO UPDATE SET
                    likes = EXCLUDED.likes,
                    retweets = EXCLUDED.retweets,
                    reply_count = EXCLUDED.reply_count,
                    quote_count = EXCLUDED.quote_count,
                    views = EXCLUDED.views
            """
            execute_values(cur, sql_with_conflict, data_with_id)
        
        # 没有 tweet_id 的直接插入
        if data_without_id:
            sql_normal = """
                INSERT INTO tweets 
                (author, author_name, content, tweet_url, voice_file, voice_text, 
                 likes, retweets, views, created_at,
                 tweet_id, reply_count, quote_count, user_followers, user_friends, 
                 user_description, data_source, raw_json)
                VALUES %s
            """
            execute_values(cur, sql_normal, data_without_id)
        
        conn.commit()
        return len(data)
        
    except psycopg2.Error as e:
        print(f"❌ 数据库错误: {e}")
        if conn:
            conn.rollback()
        return 0
    finally:
        if conn:
            conn.close()


def save_ocr_result(ocr_text: str) -> tuple[int, list[Tweet]]:
    """
    解析 OCR 结果并保存到数据库
    
    Args:
        ocr_text: OCR 识别的文本
    
    Returns:
        (保存数量, 推文列表)
    """
    tweets = parse_ocr_to_tweets(ocr_text)
    saved = save_tweets(tweets)
    return saved, tweets


def mark_liked(tweet_url: str = None, tweet_id: int = None, liked: bool = True) -> bool:
    """
    标记推文为已点赞
    
    Args:
        tweet_url: 推文 URL（优先）
        tweet_id: 数据库 ID
        liked: True=点赞, False=取消点赞
    
    Returns:
        是否成功
    """
    if not tweet_url and not tweet_id:
        return False
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if liked:
            if tweet_url:
                cur.execute(
                    "UPDATE tweets SET is_liked = TRUE, liked_at = NOW() WHERE tweet_url = %s",
                    (tweet_url,)
                )
            else:
                cur.execute(
                    "UPDATE tweets SET is_liked = TRUE, liked_at = NOW() WHERE id = %s",
                    (tweet_id,)
                )
        else:
            if tweet_url:
                cur.execute(
                    "UPDATE tweets SET is_liked = FALSE, liked_at = NULL WHERE tweet_url = %s",
                    (tweet_url,)
                )
            else:
                cur.execute(
                    "UPDATE tweets SET is_liked = FALSE, liked_at = NULL WHERE id = %s",
                    (tweet_id,)
                )
        
        conn.commit()
        return cur.rowcount > 0
        
    except psycopg2.Error as e:
        print(f"❌ 数据库错误: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def mark_bookmarked(tweet_url: str = None, tweet_id: int = None, bookmarked: bool = True) -> bool:
    """
    标记推文为已收藏
    
    Args:
        tweet_url: 推文 URL（优先）
        tweet_id: 数据库 ID
        bookmarked: True=收藏, False=取消收藏
    
    Returns:
        是否成功
    """
    if not tweet_url and not tweet_id:
        return False
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if bookmarked:
            if tweet_url:
                cur.execute(
                    "UPDATE tweets SET is_bookmarked = TRUE, bookmarked_at = NOW() WHERE tweet_url = %s",
                    (tweet_url,)
                )
            else:
                cur.execute(
                    "UPDATE tweets SET is_bookmarked = TRUE, bookmarked_at = NOW() WHERE id = %s",
                    (tweet_id,)
                )
        else:
            if tweet_url:
                cur.execute(
                    "UPDATE tweets SET is_bookmarked = FALSE, bookmarked_at = NULL WHERE tweet_url = %s",
                    (tweet_url,)
                )
            else:
                cur.execute(
                    "UPDATE tweets SET is_bookmarked = FALSE, bookmarked_at = NULL WHERE id = %s",
                    (tweet_id,)
                )
        
        conn.commit()
        return cur.rowcount > 0
        
    except psycopg2.Error as e:
        print(f"❌ 数据库错误: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


def save_xhr_tweets_from_json(json_file: str) -> int:
    """
    从 XHR 拦截的 JSON 文件批量保存推文
    
    Args:
        json_file: JSON 文件路径（tweets_xhr_test.json 等）
    
    Returns:
        成功保存的推文数量
    """
    import json
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data_list = json.load(f)
        
        if not isinstance(data_list, list):
            print(f"❌ JSON 文件格式错误，期望列表")
            return 0
        
        tweets = [tweet_from_xhr_json(d) for d in data_list]
        saved = save_tweets(tweets)
        print(f"✅ 从 {json_file} 保存了 {saved} 条推文")
        return saved
        
    except FileNotFoundError:
        print(f"❌ 文件不存在: {json_file}")
        return 0
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        return 0


def get_recent_tweets(limit: int = 20, data_source: str = None) -> list[dict]:
    """
    获取最近保存的推文
    
    Args:
        limit: 返回数量
        data_source: 筛选来源 ('ocr', 'xhr', None=全部)
    
    Returns:
        推文列表
    """
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if data_source:
            cur.execute("""
                SELECT id, scraped_at, author, author_name, content, 
                       likes, retweets, views, reply_count, data_source, tweet_id
                FROM tweets 
                WHERE data_source = %s
                ORDER BY scraped_at DESC 
                LIMIT %s
            """, (data_source, limit))
        else:
            cur.execute("""
                SELECT id, scraped_at, author, author_name, content, 
                       likes, retweets, views, reply_count, data_source, tweet_id
                FROM tweets 
                ORDER BY scraped_at DESC 
                LIMIT %s
            """, (limit,))
        
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
        
    except psycopg2.Error as e:
        print(f"❌ 数据库错误: {e}")
        return []
    finally:
        if conn:
            conn.close()


# CLI 测试入口
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "list":
            # 列出最近的推文
            data_source = sys.argv[2] if len(sys.argv) > 2 else None
            tweets = get_recent_tweets(10, data_source)
            for t in tweets:
                source = t.get('data_source', 'ocr')
                tid = t.get('tweet_id', 'N/A')
                print(f"[{t['scraped_at']}] [{source}] {t['author']}: {t['content'][:50]}...")
                if source == 'xhr':
                    print(f"  └─ ID:{tid} 💬{t.get('reply_count', 0)}")
        
        elif sys.argv[1] == "import-xhr":
            # 导入 XHR JSON 数据
            if len(sys.argv) < 3:
                print("Usage: python tweet_db.py import-xhr <json_file>")
                print("Example: python tweet_db.py import-xhr tweets_xhr_test.json")
            else:
                json_file = sys.argv[2]
                saved = save_xhr_tweets_from_json(json_file)
                print(f"\n📊 总计保存: {saved} 条推文")
        
        elif sys.argv[1] == "test":
            # 测试解析
            test_ocr = """
Albert Wang
@test_user · 3h
这是一条测试推文
1.2K
456
10K

Another User
@another · 5h
Another test tweet content here
789
123
5.6K
"""
            tweets = parse_ocr_to_tweets(test_ocr)
            print(f"解析到 {len(tweets)} 条推文:")
            for t in tweets:
                print(f"  - {t.author} ({t.author_name}): {t.content[:30]}...")
                print(f"    likes={t.likes}, retweets={t.retweets}, views={t.views}")
    else:
        print("Usage:")
        print("  python tweet_db.py list [ocr|xhr]     - 列出最近推文")
        print("  python tweet_db.py import-xhr <file>  - 导入XHR JSON数据")
        print("  python tweet_db.py test               - 测试OCR解析")
