-- 扩展 tweets 表以支持 XHR 拦截数据
-- 2026-01-31 by Mooer

-- 添加 tweet_id（唯一索引）
ALTER TABLE tweets ADD COLUMN IF NOT EXISTS tweet_id VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tweets_tweet_id ON tweets(tweet_id) WHERE tweet_id IS NOT NULL;

-- 添加更多互动数据
ALTER TABLE tweets ADD COLUMN IF NOT EXISTS reply_count INT;
ALTER TABLE tweets ADD COLUMN IF NOT EXISTS quote_count INT;

-- 添加用户详细信息
ALTER TABLE tweets ADD COLUMN IF NOT EXISTS user_followers INT;
ALTER TABLE tweets ADD COLUMN IF NOT EXISTS user_friends INT;
ALTER TABLE tweets ADD COLUMN IF NOT EXISTS user_description TEXT;

-- 添加数据来源标记
ALTER TABLE tweets ADD COLUMN IF NOT EXISTS data_source VARCHAR(20) DEFAULT 'ocr';

-- 添加原始 JSON 数据（可选，用于调试和未来扩展）
ALTER TABLE tweets ADD COLUMN IF NOT EXISTS raw_json JSONB;

-- 添加索引优化查询
CREATE INDEX IF NOT EXISTS idx_tweets_data_source ON tweets(data_source);
CREATE INDEX IF NOT EXISTS idx_tweets_scraped_at ON tweets(scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_tweets_created_at ON tweets(created_at DESC) WHERE created_at IS NOT NULL;

-- 添加注释
COMMENT ON COLUMN tweets.tweet_id IS 'Twitter推文唯一ID（从XHR获取）';
COMMENT ON COLUMN tweets.data_source IS '数据来源: ocr=OCR识别, xhr=API拦截';
COMMENT ON COLUMN tweets.raw_json IS '原始JSON数据（仅XHR来源）';
