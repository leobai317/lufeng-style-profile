# -*- coding: utf-8 -*-
"""
批判性审视 · 可量化指标

不是评好坏，而是量「套路化程度」——哪些是他稳定的方法，哪些已经变成不动脑的条件反射。
全部在本人确证文本（corpus_own/confirmed/，214 段）上算。

指标
  A 母版复用率    三段递进的价值排序词覆盖多少段
  B 反问收束率    以「不是吗？」收尾的段落占比（区分"段末"与"段中"）
  C 素材集中度    top 素材覆盖的段落占比 + 同素材跨段重复次数
  D 论证型式      「试想，若…怎/哪…」固定句型的出现率
  E 公式化短语    跨段重复的 12 字串（stock phrase）排行榜
  F 立场先行      结论词（向善/主体性/温度/家国）出现在"可见"之前的比例
"""
import os
import re
import sys
import json
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, "corpus_own", "confirmed")

ARCH_TIER = [
    r"第一位的是?", r"最为根本", r"最值得做", r"前提是", r"关键在于", r"根本在于",
    r"首要的是?", r"第一要务", r"最要紧的",
]
MATERIALS = ["毛泽东", "史铁生", "黄文秀", "路遥", "鲁迅", "袁隆平",
             "陶行知", "苏轼", "习近平", "钱学森", "张桂梅", "钟南山"]
VALUES = ["向善", "主体性", "创造性", "温度", "求真", "家国", "初心", "使命"]


def load():
    out = []
    for fn in sorted(os.listdir(CONF)):
        if fn.endswith(".txt"):
            with open(os.path.join(CONF, fn), encoding="utf-8") as f:
                out.append((fn, f.read()))
    return out


def paragraphs(text):
    ps = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if len(p.strip()) >= 25]
    return ps


def main():
    docs = load()
    total_chars = sum(len(t) for _, t in docs)
    all_paras = []
    for fn, t in docs:
        for p in paragraphs(t):
            all_paras.append((fn, p))

    print(f"确证集：{len(docs)} 段 / {total_chars:,} 字 / {len(all_paras)} 个段落\n")

    # A 母版复用率
    hit = sum(1 for _, t in docs if any(re.search(p, t) for p in ARCH_TIER))
    print(f"[A] 三段递进价值排序词  命中 {hit}/{len(docs)} 段 = {hit / len(docs) * 100:.1f}%")

    # B 反问收束率
    tail = sum(1 for _, p in all_paras if p.rstrip().endswith(("不是吗？", "不是吗?", "不是吗")))
    mid = sum(1 for _, p in all_paras if "不是吗" in p)
    print(f"[B] 段末以「不是吗？」收尾 {tail}/{len(all_paras)} 段 = {tail / len(all_paras) * 100:.1f}%"
          f"　（含该句的段落 {mid}/{len(all_paras)} = {mid / len(all_paras) * 100:.1f}%）")

    # C 素材集中度
    print("\n[C] 素材复用")
    cnt = Counter()
    doc_of = defaultdict(set)
    for fn, t in docs:
        for m in MATERIALS:
            if m in t:
                cnt[m] += t.count(m)
                doc_of[m].add(fn)
    print(f"    {'素材':<8}{'出现':>6}{'覆盖段数':>9}{'占比':>8}")
    for m, c in cnt.most_common():
        print(f"    {m:<8}{c:>6}{len(doc_of[m]):>9}{len(doc_of[m]) / len(docs) * 100:>7.1f}%")
    top6 = sum(len(doc_of[m]) for m, _ in cnt.most_common(6))
    print(f"    top6 素材的覆盖段次合计 {top6}（去重后单段可能含多个素材）")

    # D 反事实推演
    pat = re.compile(r"试想[，,].{0,40}?(怎|哪|岂|何)")
    d_hit = sum(1 for _, t in docs if pat.search(t))
    d_total = sum(len(pat.findall(t)) for _, t in docs)
    print(f"\n[D] 「试想，若…怎/哪…」固定句型：{d_hit}/{len(docs)} 段命中 = {d_hit / len(docs) * 100:.1f}%"
          f"，共 {d_total} 处")

    # E 跨段重复的 stock phrase
    print("\n[E] 跨段重复短句（≥8 字，出现在 ≥3 个不同段落）")
    phrase_owner = defaultdict(set)
    for fn, t in docs:
        for sent in re.split(r"[。！？；…\n]", t):
            s = re.sub(r"\s", "", sent)
            s = re.sub(r"[“”「」《》（）()\"']", "", s)
            if 8 <= len(s) <= 30:
                phrase_owner[s].add(fn)
    stock = [(s, len(own)) for s, own in phrase_owner.items() if len(own) >= 3]
    stock.sort(key=lambda x: -x[1])
    for s, n in stock[:25]:
        print(f"    {n:>3} 段　{s}")

    # F 立场先行
    print("\n[F] 结论词与「可见」的先后（同段内）")
    lead = same = 0
    for _, p in all_paras:
        vi = p.find("可见")
        if vi < 0:
            continue
        vpos = [p.find(v) for v in VALUES if p.find(v) >= 0]
        if not vpos:
            continue
        if min(vpos) < vi:
            lead += 1
        else:
            same += 1
    print(f"    同段含「可见」且含立场词：立场词先出现 {lead} 段 / ")
    print(f"    「可见」先出现 {same} 段")


if __name__ == "__main__":
    main()
