# -*- coding: utf-8 -*-
"""
为校准轮盲测挑选对照真文。

筛选条件（与生成稿同子类，保证可比）：
  · verdict=确证 且非重复收录
  · genre=下水议论文
  · 900–1150 字（与生成稿同级）
  · 题材落在「辩证·哲思」（与生成稿同题材域）
  · 组内互不重复

输出候选清单（含首段与末段摘要，便于人工定夺）。
"""
import os
import re
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEAT = os.path.join(ROOT, "corpus_own", "_final.json")

DIALECTIC = r"辩证|一概而论|矛盾|对立|统一|取舍|进退|尺度|边界|顺应|不顺应|片面|两端"


def paras(t):
    return [p.strip() for p in re.split(r"\n\s*\n|\n", t) if len(p.strip()) >= 25]


def main():
    with open(FEAT, encoding="utf-8") as f:
        rows = json.load(f)
    cand = [r for r in rows
            if r["verdict"] == "确证" and not r["dup_of"]
            and r["genre"] == "下水议论文"
            and 900 <= r["chars"] <= 1150
            and re.search(DIALECTIC, r["text"])]
    print(f"候选 {len(cand)} 篇（下水议论文 × 900–1150 字 × 辩证哲思域）\n")
    for r in sorted(cand, key=lambda x: -x["chars"]):
        ps = paras(r["text"])
        tail_q = sum(1 for p in ps if p.rstrip().endswith(("不是吗？", "不是吗")))
        print(f"#{r['n']:04d}  {r['chars']:>4}字  段落{len(ps):>2}  段末反问{tail_q}/{len(ps)}"
              f"  篇末反问{'有' if '？' in ps[-1] else '无'}  可见{r['text'].count('可见')}")
        print(f"       标题：{r['headline']}")
        print(f"       出处：{os.path.basename(r['src'])[:64]}")
        print(f"       首：{ps[0][:64]}…")
        print()


if __name__ == "__main__":
    main()
