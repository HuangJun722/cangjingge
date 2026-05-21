"""
生成藏经阁静态看板。
"""

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Template

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "opportunities.json"
TEMPLATE_PATH = ROOT / "scripts" / "template.html"
OUTPUT_PATH = ROOT / "docs" / "index.html"

try:
    from zoneinfo import ZoneInfo
    CN_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    CN_TZ = timezone(timedelta(hours=8))


def read_payload():
    if not DATA_PATH.exists():
        return {"generated_at": "", "opportunities": []}
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def cn_label(iso_text):
    if not iso_text:
        return "尚未生成"
    try:
        dt = datetime.fromisoformat(iso_text)
    except ValueError:
        return iso_text
    return dt.strftime("%Y年%m月%d日 %H:%M")


def main():
    payload = read_payload()
    opportunities = payload.get("opportunities", [])
    top = [o for o in opportunities if o.get("verdict") == "可试"][:5]
    watch = [o for o in opportunities if o.get("verdict") == "观察"][:12]
    risks = [o for o in opportunities if o.get("verdict") == "高风险"][:8]
    if len(top) < 5:
        top = opportunities[:5]

    track_counts = Counter(o.get("track", "未归类") for o in opportunities)
    verdict_counts = Counter(o.get("verdict", "未知") for o in opportunities)
    by_track = defaultdict(list)
    for item in opportunities:
        by_track[item.get("track", "未归类")].append(item)

    template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
    html = template.render(
        generated_at=cn_label(payload.get("generated_at")),
        raw_generated_at=payload.get("generated_at", ""),
        positioning=payload.get("positioning", ""),
        opportunities=opportunities,
        top=top,
        watch=watch,
        risks=risks,
        track_counts=track_counts.most_common(),
        verdict_counts=verdict_counts,
        by_track=dict(by_track),
        opportunities_json=json.dumps(opportunities, ensure_ascii=False),
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(line.rstrip() for line in html.splitlines()) + "\n", encoding="utf-8")
    print(f"OK | generated {OUTPUT_PATH} | opportunities={len(opportunities)}")


if __name__ == "__main__":
    main()
