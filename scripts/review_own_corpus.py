# -*- coding: utf-8 -*-
"""
lf本人语料库 · 复核工作台的数据准备脚本

做三件事：
  1) 复用 extract_own_corpus 的署名行切分逻辑，把 216 段落盘成独立文件
  2) 为每段计算「特征 + 风险旗标」，输出 _features.json
  3) 按风险分档（low / mid / high），供逐段复核时决定读多深

复核判据（设计定稿）：
  署名优先、版式校验；指纹只用于提示可疑，不用于否决。
  分三档：确证 / 存疑 / 排除。不删只标。

输出目录：corpus_own/
  raw/own_0001.txt        切出的段落原文
  _features.json          每段的元数据、特征、旗标、档位
"""
import os
import re
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_own_corpus import load_dedup, looks_like_byline, NAME

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "corpus_own")
RAW = os.path.join(OUT, "raw")

# —— 源文件类别（按文件名推断）——
CATEGORY_RULES = [
    ("号外", ["号外"]),
    ("前文后赏", ["前文后赏"]),
    ("预告公告", ["预告", "休刊", "复刊", "贺信", "贺报", "公告", "专号", "特刊", "庆典"]),
    ("课本诗", ["课本诗"]),
    ("诗歌组诗", ["诗歌", "组诗"]),
    ("同题共写", ["同题共写", "同题写作", "共写展示", "师生共写"]),
    ("竞猜押宝", ["竞猜", "猜题", "押宝"]),
    ("评点赏读", ["评点", "赏读", "赏析"]),
]

# —— 评点口吻词（出现在段末 → 说明"前文"是别人的）——
COMMENT_WORDS = [
    "这篇下水文", "典范之作", "值得广大师生", "值得师生", "值得借鉴",
    "这篇作文", "这篇文章", "笔者", "作文讲究", "堪称", "立意高远",
    "结构严谨", "论证充分", "文脉贯通", "值得学习",
]

# —— 第三方标题迹象：段尾出现无标点的短行 ——
TITLE_TAIL_MIN, TITLE_TAIL_MAX = 4, 22


def category_of(filename: str) -> str:
    for label, kws in CATEGORY_RULES:
        if any(k in filename for k in kws):
            return label
    return "其他"


def headline_above(lines, byline_idx):
    """取署名行上方最近的非空行作为标题"""
    for k in range(byline_idx - 1, max(-1, byline_idx - 5), -1):
        if k < 0:
            break
        s = lines[k].strip()
        if not s or s in ("图片", "视频"):
            continue
        return s[:80]
    return ""


def tail_title_suspect(seg: str):
    """段尾是否挂着疑似他人标题的短行"""
    lines = [l.strip() for l in seg.splitlines() if l.strip()]
    for l in lines[-4:]:
        if len(l) < TITLE_TAIL_MIN or len(l) > TITLE_TAIL_MAX:
            continue
        if l[-1] in "，。！？：；、）】”』…—,.:;)":
            continue
        if looks_like_byline(l):
            continue
        if l.startswith(("“", "「", "—", "【")):
            continue
        # 含书名号/引号的一般是标题
        return l
    return None


def build():
    os.makedirs(RAW, exist_ok=True)
    docs = load_dedup()
    records = []
    n = 0

    for title, (fn, txt) in sorted(docs.items()):
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
            if len(seg) < 120:
                continue

            n += 1
            cat = category_of(fn)
            chars = len(seg)
            c_bushi = seg.count("不是吗")
            c_kejian = seg.count("可见")
            c_q = seg.count("？") + seg.count("?")
            c_ell = seg.count("……")
            per_k = lambda c: round(c / chars * 1000, 3)
            tail30 = seg[int(chars * 0.7):]

            flags = []
            if cat in ("预告公告", "竞猜押宝"):
                flags.append("运营文案类")
            if any(w in tail30 for w in COMMENT_WORDS):
                flags.append("段末含评点口吻")
            tt = tail_title_suspect(seg)
            if tt:
                flags.append(f"段尾疑似他人标题「{tt}」")
            if chars < 400:
                flags.append("过短")
            if chars >= 2000:
                flags.append("超长")
            if chars >= 500 and c_bushi == 0:
                flags.append("无『不是吗』")
            if cat == "课本诗" or cat == "诗歌组诗":
                flags.append("诗歌体")

            # 风险分档：有结构性疑点 → high；仅文体/长度异常 → mid；干净 → low
            structural = ("段末含评点口吻" in flags) or any(f.startswith("段尾疑似") for f in flags)
            if structural:
                risk = "high"
            elif flags:
                risk = "mid"
            else:
                risk = "low"

            outfile = os.path.join(RAW, f"own_{n:04d}.txt")
            with open(outfile, "w", encoding="utf-8") as f:
                f.write(seg)

            records.append({
                "n": n,
                "file": f"raw/own_{n:04d}.txt",
                "src": fn,
                "category": cat,
                "headline": headline_above(lines, i),
                "chars": chars,
                "risk": risk,
                "flags": flags,
                "fp": {
                    "bushi": c_bushi, "bushi_per_k": per_k(c_bushi),
                    "kejian": c_kejian, "kejian_per_k": per_k(c_kejian),
                    "q": c_q, "q_per_k": per_k(c_q),
                    "ellipsis": c_ell, "ellipsis_per_k": per_k(c_ell),
                },
                "head": seg[:150],
                "tail": seg[-150:],
                "verdict": None,     # 复核结论：确证 / 存疑 / 排除
                "reason": None,      # 判据
                "tags": [],          # 文体 / 完整度 / 置信度
            })

    with open(os.path.join(OUT, "_features.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)

    # —— 汇总 ——
    from collections import Counter
    print(f"落盘段落数        : {n} → {RAW}")
    print(f"风险分档          : " + " / ".join(f"{k}:{v}" for k, v in Counter(r["risk"] for r in records).items()))
    print(f"源类别分布        : " + " / ".join(f"{k}:{v}" for k, v in Counter(r["category"] for r in records).most_common()))
    print(f"总字数            : {sum(r['chars'] for r in records):,}")
    print("\n各旗标命中数：")
    for k, v in Counter(f.split("「")[0] for r in records for f in r["flags"]).most_common():
        print(f"   {k:<16}{v}")
    print("\n高风险段（需读全文）：")
    for r in records:
        if r["risk"] == "high":
            print(f"   {r['n']:>4}  {r['chars']:>5}字  {r['flags']}  ← {os.path.basename(r['src'])[:60]}")


if __name__ == "__main__":
    build()
