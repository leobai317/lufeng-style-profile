# -*- coding: utf-8 -*-
"""
在"lf本人段落"上重算语言指纹，与全量口径对照。

动机：报告里的指纹（"不是吗？"687 次等）是在 600 篇 / 203.4 万字上算的，
其中混有大量师生作品与学术转载，频次被稀释、也被个别话题（如"长征"）
的合集类篇目拉偏。本脚本把两个口径并排算，看差异。

两个口径：
  A. 本人段落：按署名行从 wxfetch 切出的 216 段（仅他本人文本）
  B. 全量：600 篇去重文件全文

指标统一为「每千字频次」+「段落覆盖率」，两者分母不同需注意：
  - 覆盖率的分母：A 是 216 个本人段落；B 是 600 篇文档（非段落）
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_own_corpus import load_dedup, looks_like_byline, NAME

FINGERPRINTS = [
    ("不是吗？", ["不是吗"]),
    ("可见，", ["可见"]),
    ("试想", ["试想"]),
    ("须", ["须"]),
    ("方可/方能", ["方可", "方能"]),
    ("价值词", ["主体性", "创造性", "温度", "向善", "求真", "辩证", "一概而论"]),
    ("？", ["？"]),
    ("省略号……", ["……"]),
]

MATERIALS = [
    "鲁迅", "苏轼", "毛泽东", "史铁生", "袁隆平", "路遥", "黄文秀",
    "陶渊明", "钱学森", "项羽", "长征", "全红婵", "钟南山", "苏轼",
]


def split_docs_into_own_segments():
    """按署名行切出本人段落（与 extract_own_corpus 同规则）"""
    docs = load_dedup()
    segs = []
    for title, (fn, txt) in docs.items():
        lines = txt.splitlines()
        marks = []
        for i, ln in enumerate(lines):
            nm = looks_like_byline(ln)
            if nm:
                marks.append((i, nm))
        for j, (i, nm) in enumerate(marks):
            if nm != NAME:
                continue
            end = marks[j + 1][0] if j + 1 < len(marks) else len(lines)
            seg = "\n".join(lines[i + 1:end]).strip()
            seg = re.sub(r"^\s*(图片|视频)\s*$", "", seg, flags=re.M)
            seg = re.sub(r"\n{3,}", "\n\n", seg).strip()
            if len(seg) >= 120:
                segs.append(seg)
    return segs


def report(label, units, unit_name):
    """units: 文本单元列表（本人段落 / 整篇文档）"""
    text = "".join(units)
    n_chars = len(text)
    n_units = len(units)

    print(f"\n{'='*68}")
    print(f"【{label}】{n_units} 个{unit_name} / {n_chars:,} 字")
    print(f"{'='*68}")
    print(f"{'指纹项':<14}{'次数':>7}{'每千字':>10}{'单位覆盖率':>12}")

    for name, words in FINGERPRINTS:
        cnt = sum(text.count(w) for w in words)
        per_k = cnt / n_chars * 1000
        cover = sum(1 for s in units if any(w in s for w in words)) / n_units * 100
        print(f"{name:<14}{cnt:>7}{per_k:>10.2f}{cover:>11.1f}%")

    print(f"\n{'素材':<10}{'次数':>7}{'每千字':>10}")
    for w in dict.fromkeys(MATERIALS):
        cnt = text.count(w)
        print(f"{w:<10}{cnt:>7}{cnt / n_chars * 1000:>10.2f}")


def main():
    own_segs = split_docs_into_own_segments()
    report("A 本人段落口径", own_segs, "本人段落")

    docs = load_dedup()
    report("B 全量口径（含师生收录件）", [t for _, t in docs.values()], "文档")


if __name__ == "__main__":
    main()
