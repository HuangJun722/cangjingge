"""
藏经阁 - 副业机会采集与评分

V1 目标：中文为主，寻找 3-7 天可低成本验证的小机会。
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OPPORTUNITIES_PATH = DATA_DIR / "opportunities.json"
SOURCES_PATH = DATA_DIR / "sources.json"
MANUAL_SEEDS_PATH = DATA_DIR / "manual_seeds.json"

try:
    from zoneinfo import ZoneInfo
    CN_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    CN_TZ = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
}

TRACK_KEYWORDS = {
    "AI 工具/服务": ["ai", "AI", "智能体", "自动化", "提示词", "简历", "PPT", "图片", "剪辑", "数字人"],
    "平台轻服务": ["闲鱼", "接单", "代做", "代运营", "服务", "兼职", "副业"],
    "内容/IP/知识产品": ["小红书", "公众号", "抖音", "课程", "资料包", "社群", "知识付费", "IP"],
    "电商/平台": ["电商", "淘宝", "拼多多", "私域", "直播", "选品", "店铺", "跨境"],
    "本地生活": ["本地生活", "门店", "团购", "探店", "点评", "商家"],
    "自动化/代运营": ["自动化", "脚本", "工作流", "代运营", "SOP", "批量"],
}

POSITIVE_SIGNALS = [
    "求", "怎么", "教程", "模板", "接单", "付费", "报价", "代做", "招募", "招聘",
    "变现", "成交", "订单", "客户", "私信", "咨询", "需求", "痛点", "复购",
    "有人", "抱怨", "不会", "缺少",
]

RISK_SIGNALS = [
    "暴富", "躺赚", "日入", "稳赚", "无脑", "搬运", "灰产", "封号", "割韭菜",
    "刷单", "矩阵", "引流黑科技", "破解", "盗版", "采集号",
]

LOW_COST_SIGNALS = [
    "模板", "文档", "脚本", "服务", "咨询", "代做", "清单", "教程", "样例",
    "不需要囤货", "不需要复杂开发", "3 天", "三天", "上架", "服务帖",
]


def cn_now():
    return datetime.now(CN_TZ)


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_space(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def infer_track(text, fallback="未归类"):
    scores = {}
    for track, keywords in TRACK_KEYWORDS.items():
        scores[track] = sum(1 for kw in keywords if kw.lower() in text.lower())
    best = max(scores.items(), key=lambda item: item[1])
    return best[0] if best[1] else fallback


def score_opportunity(item):
    text = " ".join([
        item.get("title", ""),
        item.get("summary", ""),
        item.get("paid_signal", ""),
        item.get("risk_note", ""),
        " ".join(item.get("evidence", [])),
    ])
    demand = min(10, 4 + sum(1 for kw in POSITIVE_SIGNALS if kw in text))
    paid = 3 + sum(2 for kw in ["付费", "报价", "成交", "订单", "客户", "收款", "接单", "按单", "收费", "客单"] if kw in text)
    paid = min(10, paid)
    low_cost = 4 + sum(1 for kw in LOW_COST_SIGNALS if kw in text)
    low_cost = min(10, low_cost)
    asset = 3 + sum(1 for kw in ["模板", "清单", "脚本", "SOP", "案例", "工具库", "话术", "prompt"] if kw in text)
    asset = min(10, asset)
    crowding = min(10, 2 + sum(1 for kw in ["很多人", "同质化", "拥挤", "泛滥", "卷"] if kw in text))
    risk = min(10, sum(2 for kw in RISK_SIGNALS if kw in text))

    total = round(demand * 0.24 + paid * 0.24 + low_cost * 0.26 + asset * 0.16 - crowding * 0.05 - risk * 0.15, 2)
    if risk >= 6:
        verdict = "高风险"
    elif total >= 5.2:
        verdict = "可试"
    elif total >= 4.0:
        verdict = "观察"
    else:
        verdict = "暂缓"

    item["scores"] = {
        "total": total,
        "demand": demand,
        "paid": paid,
        "low_cost": low_cost,
        "asset": asset,
        "crowding": crowding,
        "risk": risk,
    }
    item["verdict"] = verdict
    return item


def opportunity_from_seed(seed):
    title = normalize_space(seed.get("title"))
    track = seed.get("track") or infer_track(title)
    item = {
        "id": "manual-" + re.sub(r"[^a-z0-9]+", "-", title.lower())[:60].strip("-"),
        "title": title,
        "track": track,
        "platform": seed.get("platform", "人工观察"),
        "source_url": seed.get("source_url", ""),
        "summary": normalize_space(seed.get("summary") or " / ".join(seed.get("evidence", [])[:2])),
        "evidence": seed.get("evidence", []),
        "paid_signal": seed.get("paid_signal", "待验证"),
        "risk_note": seed.get("risk_note", "待观察"),
        "first_test": seed.get("first_test", "用 3 天做一个最小供给，观察咨询和成交信号"),
        "asset": seed.get("asset", "可沉淀为案例和模板"),
        "date": seed.get("date") or cn_now().strftime("%Y-%m-%d"),
        "updated_at": cn_now().isoformat(timespec="seconds"),
    }
    return score_opportunity(item)


def fetch_rss_source(source):
    url = source.get("url")
    if not url:
        return []
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code >= 400:
            return []
        parsed = feedparser.parse(res.text)
    except Exception:
        return []

    items = []
    for entry in parsed.entries[:12]:
        title = normalize_space(entry.get("title"))
        summary = normalize_space(re.sub("<[^>]+>", "", entry.get("summary", "")))
        text = title + " " + summary
        if not any(kw.lower() in text.lower() for values in TRACK_KEYWORDS.values() for kw in values):
            continue
        track = infer_track(text, source.get("track", "未归类"))
        link = entry.get("link", "")
        published = entry.get("published") or entry.get("updated") or cn_now().strftime("%Y-%m-%d")
        seed = {
            "title": title,
            "platform": source.get("platform") or source.get("name"),
            "track": track,
            "source_url": link,
            "summary": summary[:220],
            "evidence": [
                "公开内容源出现相关信号",
                "标题或摘要命中副业机会关键词",
            ],
            "paid_signal": "待验证：需要进一步查看评论、交易页或同类报价",
            "risk_note": "公开内容信号较弱，需防止把资讯误判为可做机会",
            "first_test": "用关键词在小红书/闲鱼/知乎做二次验证，找 3 个真实需求或报价样本",
            "asset": "关键词清单、案例库、验证记录",
            "date": cn_now().strftime("%Y-%m-%d"),
            "published": published,
        }
        item = opportunity_from_seed(seed)
        item["id"] = "rss-" + re.sub(r"[^a-z0-9]+", "-", (link or title).lower())[:80].strip("-")
        items.append(item)
    return items


def dedupe(items):
    seen = set()
    result = []
    for item in sorted(items, key=lambda it: it.get("scores", {}).get("total", 0), reverse=True):
        key = re.sub(r"\W+", "", item.get("title", "").lower())[:40]
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def main():
    sources = read_json(SOURCES_PATH, [])
    seeds = read_json(MANUAL_SEEDS_PATH, [])
    items = [opportunity_from_seed(seed) for seed in seeds]
    for source in sources:
        if source.get("enabled") and source.get("type") == "rss":
            items.extend(fetch_rss_source(source))

    items = dedupe(items)
    payload = {
        "generated_at": cn_now().isoformat(timespec="seconds"),
        "positioning": "中文副业机会私人看板，优先寻找 3-7 天可低成本验证的小机会。",
        "opportunities": items[:80],
    }
    write_json(OPPORTUNITIES_PATH, payload)
    print(f"OK | opportunities={len(payload['opportunities'])} | generated_at={payload['generated_at']}")


if __name__ == "__main__":
    main()
