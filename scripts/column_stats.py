# -*- coding: utf-8 -*-
"""统计该号七个固定栏目在 600 篇全量里的出现次数（按标题关键词）。"""
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_own_corpus import load_dedup

COLUMNS = [
    ("号外", ["号外"]),
    ("课本诗", ["课本诗"]),
    ("前文后赏", ["前文后赏"]),
    ("同题共写", ["同题共写", "同题写作", "师生共写", "共写展示"]),
    ("组诗", ["组诗"]),
    ("预告/休刊/复刊", ["预告", "休刊", "复刊"]),
    ("竞猜押宝", ["竞猜", "猜题", "押宝"]),
]

docs = load_dedup()
titles = list(docs.keys())
print(f"全量去重后 {len(titles)} 篇\n")
print(f"{'栏目':<16}{'篇数':>6}")
for label, kws in COLUMNS:
    n = sum(1 for t in titles if any(k in t for k in kws))
    print(f"{label:<16}{n:>6}")

# 本人确证段里，他真正参与了多少
import json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "corpus_own", "_final.json"), encoding="utf-8") as f:
    rows = json.load(f)
conf = [r for r in rows if r["verdict"] == "确证"]
own_col = Counter()
for r in conf:
    hit = "其他"
    for label, kws in COLUMNS:
        if any(k in r["src"] for k in kws):
            hit = label
            break
    own_col[hit] += 1
print("\n本人确证段（214 段）的栏目归属：")
for k, v in own_col.most_common():
    print(f"   {k:<16}{v:>5}")
