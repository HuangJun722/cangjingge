"""
藏经阁 - 副业机会采集与评分

V1 目标：中文为主，寻找 3-7 天可低成本验证的小机会。
"""

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

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

EVIDENCE_TYPES = {
    "demand": ["求助", "求推荐", "怎么做", "不会", "缺少", "痛点", "咨询", "私信", "有人问", "招聘", "招募"],
    "paid": ["付费", "报价", "成交", "订单", "收款", "接单", "收费", "客单", "购买", "下单", "佣金"],
    "low_cost": ["模板", "文档", "脚本", "清单", "教程", "样例", "SOP", "prompt", "上架", "服务帖", "交付"],
    "social": ["小红书", "知乎", "抖音", "B站", "微博", "评论", "收藏", "私信", "帖子"],
    "market": ["榜单", "增长", "融资", "新品", "下载", "流量", "商家", "卖家", "平台"],
}

POSITIVE_SIGNALS = [
    "求助", "求推荐", "怎么做", "教程", "模板", "接单", "付费", "报价", "代做", "招募", "招聘",
    "变现", "成交", "订单", "客户", "私信", "咨询", "需求", "痛点", "复购",
    "有人问", "抱怨", "不会", "缺少",
]

RISK_SIGNALS = [
    "暴富", "躺赚", "日入", "稳赚", "无脑", "搬运", "灰产", "封号", "割韭菜",
    "刷单", "矩阵", "引流黑科技", "破解", "盗版", "采集号",
]

LOW_COST_SIGNALS = [
    "模板", "文档", "脚本", "服务", "咨询", "代做", "清单", "教程", "样例",
    "不需要囤货", "不需要复杂开发", "3 天", "三天", "上架", "服务帖",
]

WEAK_INFO_PATTERNS = [
    "快讯", "早报", "周报", "融资", "发布会", "大会", "财报", "排行榜",
    "值得关注的 App", "行业动态", "观点", "访谈",
]

SOURCE_TIER_WEIGHT = {
    "manual": 1.0,
    "vertical": 0.9,
    "market": 0.8,
    "search": 0.72,
    "social": 0.68,
}


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


def strip_html(text):
    return normalize_space(re.sub("<[^>]+>", "", str(text or "")))


def evidence_types_for(text):
    found = []
    low = text.lower()
    for evidence_type, keywords in EVIDENCE_TYPES.items():
        if any(kw.lower() in low for kw in keywords):
            found.append(evidence_type)
    return found


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
    evidence_types = item.get("evidence_types") or evidence_types_for(text)
    tier = item.get("source_tier", "market")
    tier_weight = SOURCE_TIER_WEIGHT.get(tier, 0.75)

    demand = min(10, 4 + sum(1 for kw in POSITIVE_SIGNALS if kw in text))
    if "demand" in evidence_types:
        demand += 1
    if "social" in evidence_types:
        demand += 1
    demand = min(10, demand)
    paid = 3 + sum(2 for kw in ["付费", "报价", "成交", "订单", "客户", "收款", "接单", "按单", "收费", "客单"] if kw in text)
    if "paid" in evidence_types:
        paid += 1
    paid = min(10, paid)
    low_cost = 4 + sum(1 for kw in LOW_COST_SIGNALS if kw in text)
    if "low_cost" in evidence_types:
        low_cost += 1
    low_cost = min(10, low_cost)
    asset = 3 + sum(1 for kw in ["模板", "清单", "脚本", "SOP", "案例", "工具库", "话术", "prompt"] if kw in text)
    asset = min(10, asset)
    crowding = min(10, 2 + sum(1 for kw in ["很多人", "同质化", "拥挤", "泛滥", "卷"] if kw in text))
    risk = min(10, sum(2 for kw in RISK_SIGNALS if kw in text))

    base_total = demand * 0.24 + paid * 0.24 + low_cost * 0.26 + asset * 0.16 - crowding * 0.05 - risk * 0.15
    if any(pattern.lower() in text.lower() for pattern in WEAK_INFO_PATTERNS) and not {"demand", "paid"} & set(evidence_types):
        base_total -= 0.55
    if len(evidence_types) >= 3:
        base_total += 0.35
    total = round(max(0, min(10, base_total * tier_weight + (1 - tier_weight) * 3.8)), 2)
    if risk >= 6:
        verdict = "高风险"
    elif total >= 5.2 and {"demand", "paid", "low_cost"} & set(evidence_types):
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
    item["evidence_types"] = evidence_types
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
        "evidence_types": seed.get("evidence_types", []),
        "paid_signal": seed.get("paid_signal", "待验证"),
        "risk_note": seed.get("risk_note", "待观察"),
        "first_test": seed.get("first_test", "用 3 天做一个最小供给，观察咨询和成交信号"),
        "asset": seed.get("asset", "可沉淀为案例和模板"),
        "source_tier": seed.get("source_tier", "manual"),
        "source_type": seed.get("source_type", "manual"),
        "review_note": seed.get("review_note", ""),
        "date": seed.get("date") or cn_now().strftime("%Y-%m-%d"),
        "updated_at": cn_now().isoformat(timespec="seconds"),
    }
    return score_opportunity(item)


def build_seed_from_source(source, title, summary, link, published=""):
    text = title + " " + summary
    evidence_types = evidence_types_for(text)
    if not evidence_types and not any(kw.lower() in text.lower() for values in TRACK_KEYWORDS.values() for kw in values):
        return None

    track = infer_track(text, source.get("track", "未归类"))
    source_type = source.get("type", "rss")
    source_tier = source.get("tier") or ("social" if source_type == "search" else "vertical")
    evidence = [
        f"{source.get('platform') or source.get('name')} 出现相关公开信号",
        "标题或摘要命中需求、付费、低成本验证或平台趋势关键词",
    ]
    if "social" in evidence_types:
        evidence.append("搜索词指向社媒/社区讨论，需要人工二次抽样确认")
    if "paid" in evidence_types:
        evidence.append("文本中出现付费、报价、成交或接单线索")

    seed = {
        "title": title,
        "platform": source.get("platform") or source.get("name"),
        "track": track,
        "source_url": link,
        "summary": summary[:260],
        "evidence": evidence,
        "evidence_types": evidence_types,
        "paid_signal": "待验证：查看评论、交易页、服务帖或同类报价，确认是否有真实付费",
        "risk_note": "自动采集线索只代表早期信号，需防止把资讯热度误判为可做机会",
        "first_test": source.get("first_test") or "用关键词在小红书/闲鱼/知乎做二次验证，找 3 个真实需求或报价样本",
        "asset": "关键词清单、案例库、验证记录、交付模板",
        "date": cn_now().strftime("%Y-%m-%d"),
        "published": published,
        "source_tier": source_tier,
        "source_type": source_type,
    }
    return seed


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
    limit = int(source.get("limit", 12))
    for entry in parsed.entries[:limit]:
        title = normalize_space(entry.get("title"))
        summary = strip_html(entry.get("summary", ""))
        if not title:
            continue
        link = entry.get("link", "")
        published = entry.get("published") or entry.get("updated") or cn_now().strftime("%Y-%m-%d")
        seed = build_seed_from_source(source, title, summary, link, published)
        if not seed:
            continue
        item = opportunity_from_seed(seed)
        item["id"] = "rss-" + re.sub(r"[^a-z0-9]+", "-", (link or title).lower())[:80].strip("-")
        items.append(item)
    return items


def fetch_search_source(source):
    query = source.get("query", "")
    if not query:
        return []
    rss_url = "https://www.bing.com/news/search?q=" + requests.utils.quote(query) + "&format=rss"
    rss_source = {**source, "url": rss_url, "type": "search", "tier": source.get("tier", "search")}
    items = fetch_rss_source(rss_source)
    if items:
        return items

    soup = None
    for engine_url, params in [
        ("https://www.bing.com/search", {"q": query}),
        ("https://duckduckgo.com/html/", {"q": query}),
    ]:
        try:
            res = requests.get(engine_url, params=params, headers=HEADERS, timeout=12)
            if res.status_code >= 400:
                continue
            candidate = BeautifulSoup(res.text, "html.parser")
            if candidate.select("li.b_algo") or candidate.select(".result"):
                soup = candidate
                break
        except Exception:
            continue
    if soup is None:
        return []

    results = []
    raw_hits = []
    nodes = soup.select("li.b_algo") or soup.select(".result")
    for node in nodes[: int(source.get("limit", 8))]:
        title_node = node.select_one("h2 a") or node.select_one(".result__title a")
        if not title_node:
            continue
        title = normalize_space(title_node.get_text(" "))
        link = title_node.get("href", "")
        summary_node = node.select_one(".b_caption p") or node.select_one(".result__snippet")
        summary = normalize_space((summary_node or node).get_text(" "))
        raw_hits.append({"title": title, "summary": summary, "url": link})
    if not raw_hits:
        return results

    title = source.get("opportunity_title") or f"{source.get('platform') or source.get('name')}：{query}"
    top_titles = [hit["title"] for hit in raw_hits[:3] if hit.get("title")]
    seed = {
        "title": title,
        "platform": source.get("platform") or source.get("name"),
        "track": source.get("track") or infer_track(query),
        "source_url": raw_hits[0].get("url", ""),
        "summary": source.get("summary") or f"围绕“{query}”的公开搜索结果已出现，可作为需求抽样入口。",
        "evidence": [
            "公开搜索返回相关结果，说明该方向有可抽样讨论或供给",
            "搜索样本：" + "；".join(top_titles),
            "该层只作为弱信号，需要人工抽样验证评论、报价或服务帖",
        ],
        "evidence_types": source.get("evidence_types") or ["social", "demand", "low_cost"],
        "paid_signal": source.get("paid_signal") or "待验证：继续查找服务帖、报价页、评论区咨询或成交截图",
        "risk_note": source.get("risk_note") or "搜索层容易混入 SEO 和泛资讯，不满足真实付费证据前只放观察池",
        "first_test": source.get("first_test") or "用同一关键词在小红书/闲鱼/知乎人工抽样 10 条，记录真实需求和报价",
        "asset": source.get("asset") or "关键词库、需求样本表、服务帖标题和交付模板",
        "date": cn_now().strftime("%Y-%m-%d"),
        "source_tier": source.get("tier", "social"),
        "source_type": "search",
    }
    item = opportunity_from_seed(seed)
    item["id"] = "search-query-" + re.sub(r"[^a-z0-9]+", "-", query.lower())[:80].strip("-")
    return [item]


def fetch_html_source(source):
    url = source.get("url")
    if not url:
        return []
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code >= 400:
            return []
        soup = BeautifulSoup(res.text, "html.parser")
    except Exception:
        return []

    items = []
    selector = source.get("selector", "article, .post, .item, li")
    title_selector = source.get("title_selector", "h1,h2,h3,a")
    for node in soup.select(selector)[: int(source.get("limit", 10))]:
        title_node = node.select_one(title_selector)
        if not title_node:
            continue
        title = normalize_space(title_node.get_text(" "))
        if len(title) < 8:
            continue
        link_node = title_node if title_node.name == "a" else title_node.find_parent("a") or node.select_one("a")
        link = link_node.get("href", "") if link_node else ""
        if link.startswith("/"):
            link = url.rstrip("/") + link
        summary = normalize_space(node.get_text(" "))[:260]
        seed = build_seed_from_source(source, title, summary, link)
        if not seed:
            continue
        item = opportunity_from_seed(seed)
        item["id"] = "html-" + re.sub(r"[^a-z0-9]+", "-", (link or title).lower())[:80].strip("-")
        items.append(item)
    return items


def heuristic_second_pass(item):
    evidence_types = set(item.get("evidence_types") or [])
    score = item.get("scores", {}).get("total", 0)
    title = item.get("title", "")
    summary = item.get("summary", "")
    text = f"{title} {summary} {' '.join(item.get('evidence', []))}"
    if any(risk in text for risk in RISK_SIGNALS):
        item["review_note"] = "规则复核：含高风险词，进入避坑或观察。"
        item["verdict"] = "高风险"
        return item
    source_type = item.get("source_type")
    source_tier = item.get("source_tier")
    weak_info = any(pattern.lower() in text.lower() for pattern in WEAK_INFO_PATTERNS)
    has_paid_path = "paid" in evidence_types and ("low_cost" in evidence_types or "demand" in evidence_types)
    has_social_demand_path = source_tier == "social" and "demand" in evidence_types and "low_cost" in evidence_types

    if source_type in {"rss", "html"} and (weak_info or not has_paid_path):
        item["review_note"] = "规则复核：偏资讯，缺少需求/付费/低成本证据，降为观察。"
        item["verdict"] = "观察" if score >= 3.6 else "暂缓"
        return item
    if source_type == "search" and not (has_paid_path or has_social_demand_path):
        item["review_note"] = "规则复核：搜索信号较弱，需要人工抽样。"
        item["verdict"] = "观察"
        return item
    if source_type == "search":
        item["review_note"] = "规则复核：搜索层只作为需求假设，需人工补报价/成交证据后再升为可试。"
        item["verdict"] = "观察"
        return item
    item["review_note"] = "规则复核：证据链基本成立，可进入看板。"
    return item


def ai_second_pass(items):
    """Optional LLM review. Without a key, use deterministic review so CI remains stable."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return [heuristic_second_pass(item) for item in items]
    # Keep the first version conservative: no hard dependency on remote model success.
    try:
        reviewed = []
        for item in items:
            reviewed.append(heuristic_second_pass(item))
        return reviewed
    except Exception:
        return [heuristic_second_pass(item) for item in items]


def dedupe(items):
    seen = set()
    result = []
    for item in sorted(items, key=lambda it: it.get("scores", {}).get("total", 0), reverse=True):
        key = re.sub(r"\W+", "", item.get("title", "").lower())[:48]
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
        if not source.get("enabled"):
            continue
        if source.get("type") == "rss":
            items.extend(fetch_rss_source(source))
        elif source.get("type") == "search":
            items.extend(fetch_search_source(source))
        elif source.get("type") == "html":
            items.extend(fetch_html_source(source))
        time.sleep(float(source.get("sleep", 0.2)))

    items = dedupe(items)
    items = ai_second_pass(items)
    items = [item for item in items if item.get("verdict") != "暂缓"]
    payload = {
        "generated_at": cn_now().isoformat(timespec="seconds"),
        "positioning": "中文副业机会私人看板，优先寻找 3-7 天可低成本验证的小机会。",
        "review_mode": "ai_optional_heuristic_fallback",
        "opportunities": items[:80],
    }
    write_json(OPPORTUNITIES_PATH, payload)
    print(f"OK | opportunities={len(payload['opportunities'])} | generated_at={payload['generated_at']}")


if __name__ == "__main__":
    main()
