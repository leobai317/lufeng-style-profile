# -*- coding: utf-8 -*-
"""
找出他真正的段落级模板（而不是从少数篇目推出的"母版"）。

P1 段首连接词分布：他的段落通常怎么起头
P2 段落骨架：段落内是否呈「观点 → 例证 → 可见 → 不是吗」的顺序
P3 开篇方式：首段是「材料引述型」还是「直接判断型」
P4 收尾方式：末段是否有反问 / 号召
"""
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, "corpus_own", "confirmed")

OPENERS = ["还有，", "其实，", "当然，", "可见，", "时下，", "是啊，", "是啊", "试想",
           "那么，", "于是，", "总之，", "综上所述", "不可讳言", "一般来说", "一般而言",
           "话说回来", "有人", "有人说", "从", "在", "古人云", "俗话说"]


def load():
    out = []
    for fn in sorted(os.listdir(CONF)):
        if fn.endswith(".txt"):
            with open(os.path.join(CONF, fn), encoding="utf-8") as f:
                out.append((fn, f.read()))
    return out


def paras(t):
    return [p.strip() for p in re.split(r"\n\s*\n|\n", t) if len(p.strip()) >= 25]


def main():
    docs = load()
    all_paras = [p for _, t in docs for p in paras(t)]
    print(f"178 篇 / {len(all_paras)} 段\n")

    # P1 段首词
    print("[P1] 段首连接词分布（段落开头的 2–5 字）")
    c = Counter()
    for p in all_paras:
        for w in OPENERS:
            if p.startswith(w):
                c[w] += 1
                break
    tot = sum(c.values())
    for w, n in c.most_common(14):
        print(f"    {w:<8}{n:>4}　{n / len(all_paras) * 100:>5.1f}%")
    print(f"    合计有固定起头词的段落 {tot}/{len(all_paras)} = {tot / len(all_paras) * 100:.1f}%")

    # P2 段落骨架
    print("\n[P2] 段落骨架：例证后是否紧跟「可见」→ 段末是否「不是吗」")
    both = sum(1 for p in all_paras
               if "可见" in p and p.rstrip().endswith(("不是吗？", "不是吗", "不是吗?")))
    only_kj = sum(1 for p in all_paras if "可见" in p)
    only_bs = sum(1 for p in all_paras
                  if p.rstrip().endswith(("不是吗？", "不是吗", "不是吗?")))
    print(f"    含「可见」          {only_kj:>4}　{only_kj / len(all_paras) * 100:>5.1f}%")
    print(f"    段末「不是吗？」    {only_bs:>4}　{only_bs / len(all_paras) * 100:>5.1f}%")
    print(f"    两者同时具备        {both:>4}　{both / len(all_paras) * 100:>5.1f}%")

    # P3 开篇
    print("\n[P3] 开篇方式（首段特征）")
    p3 = Counter()
    for _, t in docs:
        ps = paras(t)
        if not ps:
            continue
        f = ps[0]
        if re.search(r"(阅读下面的材料|有人说|古人云|俗话说|材料|据统计|某)", f[:60]):
            p3["材料/引语引述型"] += 1
        elif re.search(r"(我以为|我认为|我是这样理解的|我的观点|我的回答|对此，我)", f[:120]):
            p3["直接亮观点型"] += 1
        elif re.search(r"(？|说说|谈|关于)", f[:60]):
            p3["设问/点题型"] += 1
        else:
            p3["其他"] += 1
    for k, v in p3.most_common():
        print(f"    {k:<14}{v:>4}　{v / len(docs) * 100:>5.1f}%")

    # P4 收尾
    print("\n[P4] 收尾方式（末段特征）")
    p4 = Counter()
    for _, t in docs:
        ps = paras(t)
        if not ps:
            continue
        l = ps[-1]
        has_q = "？" in l
        has_call = bool(re.search(r"(让我们|我们要|青年应|我们应|一起|必将|一定会|怎能不)", l))
        key = ("反问收尾" if has_q else "") + ("+号召" if has_call else "")
        p4[key or "陈述收尾"] += 1
    for k, v in p4.most_common():
        print(f"    {k or '陈述收尾':<14}{v:>4}　{v / len(docs) * 100:>5.1f}%")


if __name__ == "__main__":
    main()
