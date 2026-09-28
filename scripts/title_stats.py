# -*- coding: utf-8 -*-
"""标题画像：他给文章起名的实际习惯（此前完全没统计过）。

口径：确证去重集的下水议论文子类。字数一律剥离空白。
"""
import json
import os
import re
import statistics
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from profile_io import project_root  # noqa: E402

ROOT = project_root(ROOT)
FINAL = os.path.join(ROOT, "corpus_own", "_final.json")


def load(genre="下水议论文"):
    rows = json.load(open(FINAL, encoding="utf-8"))
    conf = [r for r in rows if r["verdict"] == "确证" and not r["dup_of"]]
    if genre:
        conf = [r for r in conf if r["genre"] == genre]
    return [r for r in conf if (r.get("headline") or "").strip()]


def clean(t):
    return re.sub(r"\s", "", t)


def has(t, *chars):
    return any(c in t for c in chars)


def analyze(titles):
    n = len(titles)
    L = [clean(t) for t in titles]
    lens = sorted(len(x) for x in L)

    def pct(k):
        return f"{k}/{n} = {k / n * 100:.1f}%"

    print(f"=== 标题总量 {n} 条 ===")
    print(f"长度（剥离空白）：中位 {statistics.median(lens):.0f}  均值 {statistics.mean(lens):.1f}  "
          f"P25 {lens[n//4]}  P75 {lens[3*n//4]}  最短 {lens[0]}  最长 {lens[-1]}")
    print()

    print("=== 分隔符 / 标记的使用率 ===")
    feats = [
        ("冒号「：」", ("：", ":")),
        ("逗号「，」", ("，",)),
        ("顿号「、」", ("、",)),
        ("中点「·／•」", ("·", "•")),
        ("问号「？」", ("？", "?")),
        ("引号「\"\"」", ("“", "”")),
        ("书名号「《》」", ("《", "》")),
        ("破折号「——」", ("——", "—")),
        ("第一人称「我」", ("我",)),
        ("半文言（方／须／亦／岂）", ("方", "须", "亦", "岂")),
    ]
    for name, chars in feats:
        hits = [t for t in L if has(t, *chars)]
        print(f"  {name:<22}{pct(len(hits))}")

    print()
    print("=== 结构类型 ===")
    colon = [t for t in L if has(t, "：", ":")]
    two_part = [t for t in L if has(t, "，", "；") and not has(t, "：", ":")]
    three_part = [t for t in L if len(re.split(r"[、·•，,]", t)) >= 3]
    plain = [t for t in L if not has(t, "：", ":", "，", "；", "、", "·", "•")]
    print(f"  冒号式（前件：后件）    {pct(len(colon))}")
    print(f"  逗号双分句式            {pct(len(two_part))}")
    print(f"  三项以上并列（、·•，）  {pct(len(three_part))}")
    print(f"  单句无标记              {pct(len(plain))}")

    print()
    print("=== 高频首 2 字 ===")
    for w, c in Counter(x[:2] for x in L).most_common(12):
        print(f"  {w}  ×{c}")
    print()
    print("=== 高频尾 2 字 ===")
    for w, c in Counter(x[-2:] for x in L).most_common(12):
        print(f"  {w}  ×{c}")
    print()
    print("=== 含「之」的标题（「X之Y」式）===")
    zhi = [t for t in L if "之" in t]
    print(f"  {pct(len(zhi))}  " + " / ".join(zhi[:10]))
    print()
    print("=== 含「由…想到的」「说X」「也谈」类 ===")
    for pat in ("由", "想到", "也说", "说“", "漫想", "断想", "随想", "浅说", "小议"):
        hits = [t for t in L if pat in t]
        if hits:
            print(f"  {pat:<6}{pct(len(hits))}  " + " / ".join(hits[:6]))


def compare_drafts(titles):
    print()
    print("=" * 70)
    print("=== 三篇仿稿的标题 vs 他的习惯 ===")
    ROOT2 = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for pre in ("首篇", "第二篇", "第三篇"):
        p = os.path.join(ROOT2, "稿件", f"{pre}-裸文版.md")
        if not os.path.exists(p):
            continue
        first = [l for l in open(p, encoding="utf-8").read().splitlines() if l.strip()][0]
        t = clean(re.sub(r"^#\s*", "", first))
        marks = []
        if has(t, "：", ":"):
            marks.append("冒号式")
        if has(t, "，"):
            marks.append("双分句")
        if has(t, "、", "·", "•"):
            marks.append("并列")
        if not marks:
            marks.append("单句无标记")
        print(f"  {pre:<5}{len(t):>3} 字  [{'+'.join(marks)}]  {t}")


def main():
    titles = [r["headline"] for r in load()]
    analyze(titles)
    compare_drafts(titles)


if __name__ == "__main__":
    main()
