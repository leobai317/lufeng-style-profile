# -*- coding: utf-8 -*-
"""
为「无量化参考」的盲评裁判准备材料。

模拟一个"读过他不少文章、但没拿过风格说明书"的评审：
  · 给他 8 篇**真文**当校准样本（排除 3 篇对照稿，避免泄题）
  · 再给 4 篇待判稿（同样的 A/B/C/D）
  · **不给任何量化画像、不给问题清单**

这样测的是：仿稿能不能骗过一个只凭阅读经验的人。
"""
import os
import re
import json
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEAT = os.path.join(ROOT, "corpus_own", "_final.json")
OUT = os.path.join(ROOT, "评测", "盲测-现场-无参考")
EXCLUDE = {77, 207, 48}          # 三篇对照稿，不能出现在校准样本里
N_CALIB = 8


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(FEAT, encoding="utf-8") as f:
        rows = [r for r in json.load(f)
                if r["verdict"] == "确证" and not r["dup_of"] and r["genre"] == "下水议论文"]
    pool = [r for r in rows if r["n"] not in EXCLUDE]
    # 机械挑选：按字数与 1050 的差的绝对值排序，取前 8，且彼此字数不雷同
    pool.sort(key=lambda r: abs(r["chars"] - 1050))
    picked, seen = [], set()
    for r in pool:
        b = r["chars"] // 50
        if b in seen:
            continue
        picked.append(r)
        seen.add(b)
        if len(picked) == N_CALIB:
            break

    with open(os.path.join(OUT, "你读过他的文章.md"), "w", encoding="utf-8") as f:
        f.write("# 你之前读过的他的文章（8 篇）\n\n")
        f.write("> 以下都是这位作者本人写的下水议论文。请先读完，建立对他的直觉。\n\n---\n\n")
        for r in picked:
            f.write(f"**{r['headline']}**\n\n{r['text'].strip()}\n\n---\n\n")

    # 待判稿：从第一轮文件里抽出四篇，保持 A–D 标签与原顺序
    src = os.path.join(ROOT, "评测", "盲测-校准轮-第一轮-裸文.md")
    with open(src, encoding="utf-8") as f:
        txt = f.read()
    blocks = re.split(r"\n## 稿件 ", txt)[1:]
    with open(os.path.join(OUT, "待判稿.md"), "w", encoding="utf-8") as f:
        f.write("# 待判稿（4 篇）\n\n")
        f.write("> 其中若干篇不是他本人写的。请对每篇给 0–100 分：出自他本人之手的可能性。\n\n---\n\n")
        for b in blocks:
            label = b[0]
            rest = b[2:].strip()
            f.write(f"## 稿件 {label}\n\n{rest}\n\n---\n\n")

    print(f"校准样本 {len(picked)} 篇 → {OUT}")
    for r in picked:
        print(f"   #{r['n']:04d} {r['chars']:>4}字  {r['headline'][:34]}")
    print(f"\n待判稿 4 篇（A–D，与第一轮同序）")


if __name__ == "__main__":
    main()
