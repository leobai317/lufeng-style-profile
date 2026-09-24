# -*- coding: utf-8 -*-
"""
分目别类的补充维度（补 `strata_stats.py` 缺失的两块）：

  D7 标点密度      —— 最表层、最显眼，却长期没进任何交付物
  D8 句法与冗余    —— 三轮独立评审唯一致命的判决指向这里（"太精炼" vs "絮的、重复的"）
  D9 规劝虚词分布  —— 逐篇分布，用来纠正「3.82/千字」那个错误阈值

为什么要单列这三块：
  1. 标点与句长是**不看内容就能识破**的层。实测三篇仿稿在标点这一层反复翻车
     （首篇破折号 3 处、应为 0；第二篇顿号 0.95、子类中位 4.76；引号 26.57、中位 7.77）。
  2. 冗余在直觉上是"写作瑕疵"，仿写者会下意识回避——而它恰恰是这个作者最显眼的语言体质。
     三次独立评审（2 AI + 1 人类专家）都指向它，但此前只存在于临时脚本输出里。
  3. 「3.82/千字」的半文言阈值里混着 284 个「当…时」时间从句，据它仿写会导致三篇齐刷刷堆文言。
     这里给出逐篇分布，说明为什么该改用**出现次数带**而不是每千字率。

口径（全文统一，勿混）：
  确证去重（_final.json 中 verdict=确证 且 dup_of 为空）
  字数 = **剥离空白**后的字符数（与 check_flaws2 / check_verbosity / check_draft 一致）
  标点 = 字符计数（引号计 “ ” 两字符；破折号计「——」出现次数；省略号计「……」出现次数）
  指标 = 先逐篇算，再取均值 / 中位（**不是**先拼全集再算）

用法：
  python strata_extra.py                  # 打印 + 写入 _logs/strata_extra.md
  python strata_extra.py --json out.json  # 另存结构化结果
"""
import argparse
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import project_root   # noqa: E402

# 项目根：STYLE_PROJECT 优先，其次脚本的上一级（脚本被复制进 skill 后靠 STYLE_PROJECT / cwd）
ROOT = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FEAT = os.path.join(ROOT, "corpus_own", "_final.json")
OUT_MD = os.path.join(ROOT, "_logs", "strata_extra.md")

# D7：标点 → (计法, 说明)
MARKS = [
    ("顿号", lambda t: t.count("、"), "他大量用顿号并列**词组**（\"准确、细腻、严肃的表达能力\"）"),
    ("引号", lambda t: t.count("“") + t.count("”"), "概念引号；堆积到 3 倍以上会立刻显假"),
    ("感叹号", lambda t: t.count("！") + t.count("!"), "呼喊式习惯（\"斯言诚哉！斯言诚哉！\"），最显眼也最容易漏查"),
    ("问号", lambda t: t.count("？") + t.count("?"), "反问是人物设定，密度掉了就不像"),
    ("分号", lambda t: t.count("；"), "用得少；**分号会断句**——想写长句就先别用分号"),
    ("省略号", lambda t: t.count("……"), "**文体差异极大**：散文特征，不是议论文特征"),
    ("破折号", lambda t: t.count("——"), "中位为 0——**不用才是常态**，用了就会判偏高"),
    ("括号", lambda t: t.count("（"), "中位为 0，同上"),
]

# D9：规劝虚词。「须／方可／方能」无歧义；「当」必须剔除（多为「当…时」时间从句）
ARCH_UNAMBIG = ["须", "方可", "方能", "务必", "势必"]
ARCH_AMBIG = ["当"]


def sent_lens(t):
    """句长：只用**中文**句末标点断句。

    不要加 ASCII 的 ! ? ;——中文行文里它们多出现在引文或标记里，
    加进来会把句子切碎，句长均值与长句占比都会系统性偏低。
    口径必须与 `check_verbosity.py` 一致，否则同一批语料会出两组数
    （实测差异：句长均值中位 31.3 vs 31.6、长句占比中位 9.9% vs 10.2%）。
    """
    return [len(s.strip()) for s in re.split(r"[。！？；]", t) if s.strip()]


def ngram_dup(t, n):
    """复读度 = 1 - 唯一 n-gram / 总 n-gram。越高越"絮"。"""
    s = re.sub(r"\s", "", t)
    if len(s) < n:
        return 0.0, 0
    gs = [s[i:i + n] for i in range(len(s) - n + 1)]
    dup_instances = len(gs) - len(set(gs))
    return 1 - len(set(gs)) / len(gs), dup_instances


def paras(t):
    return [p.strip() for p in re.split(r"\n\s*\n|\n", t) if len(p.strip()) >= 25]


def per_article(t):
    nc = len(re.sub(r"\s", "", t)) or 1
    d = {f"mark:{name}": fn(t) / nc * 1000 for name, fn, _ in MARKS}
    lens = sent_lens(t)
    red5, dup5 = ngram_dup(t, 5)
    red3, _ = ngram_dup(t, 3)
    red9, _ = ngram_dup(t, 9)
    pl = [len(p) for p in paras(t)]
    d.update({
        "sent_mean": statistics.mean(lens) if lens else 0,
        "sent_med": statistics.median(lens) if lens else 0,
        "long_pct": sum(1 for x in lens if x > 60) / len(lens) * 100 if lens else 0,
        "red3": red3, "red5": red5, "red9": red9, "dup5": dup5,
        "para_med": statistics.median(pl) if pl else 0,
        "arch": sum(t.count(w) for w in ARCH_UNAMBIG),
        "arch_amb": sum(t.count(w) for w in ARCH_AMBIG),
        "arch_pk": sum(t.count(w) for w in ARCH_UNAMBIG) / nc * 1000,
        # 旧口径：把「当」也算进文言虚词（错）——保留只为对照，说明 3.8x 是怎么来的
        "arch_amb_pk": sum(t.count(w) for w in ARCH_UNAMBIG + ARCH_AMBIG) / nc * 1000,
    })
    return d


def agg(ms, key):
    vals = [m[key] for m in ms]
    return statistics.mean(vals), statistics.median(vals)


def fmt(ms, key, nd=2):
    """均值（中位）。两者相等时（小样本组常见）只写一个数，避免「5.90 (5.90)」这种冗余。"""
    a, m = agg(ms, key)
    if round(a, nd) == round(m, nd):
        return f"{a:.{nd}f}"
    return f"{a:.{nd}f} ({m:.{nd}f})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    with open(FEAT, encoding="utf-8") as f:
        rows = [r for r in json.load(f) if r["verdict"] == "确证" and not r["dup_of"]]

    from collections import Counter
    genres = [g for g, c in Counter(r["genre"] for r in rows).most_common()]

    L = []
    L.append(f"# 分目别类 · 补充维度（D7 标点 / D8 句法与冗余 / D9 规劝虚词）\n")
    L.append(f"> 口径：确证去重 **{len(rows)} 篇 / {sum(r['chars'] for r in rows):,} 字**；"
             f"字数=剥离空白，**先逐篇算再取均值/中位**。")
    L.append(f"> 脚本：`tools/strata_extra.py`（可重跑）。数值由脚本产出，非手抄。\n")

    # ---------- D7 标点 ----------
    L.append("## D7 标点密度（每千字，格式＝均值（中位））\n")
    heads = ["文体", "篇数"] + [n for n, _, _ in MARKS]
    L.append("| " + " | ".join(heads) + " |")
    L.append("|" + "---|" * len(heads))
    for g in genres:
        ms = [per_article(r["text"]) for r in rows if r["genre"] == g]
        if not ms:
            continue
        cells = [f"{fmt(ms, 'mark:' + n, 2)}" for n, _, _ in MARKS]
        L.append(f"| **{g}** | {len(ms)} | " + " | ".join(cells) + " |")
    L.append("")
    for n, _, note in MARKS:
        L.append(f"- **{n}**：{note}")

    # ---------- D8 句法与冗余 ----------
    # 不重复给「段中位」——D1/D6 已有（且那里是**合并全部段落**取中位，
    # 这里是逐篇中位再取中位，两个口径不等价，同列会打架）。
    L.append("\n## D8 句法与冗余（「像不像」的头等指标）\n")
    heads8 = ["文体", "篇数", "句长均值", "句长中位", "长句(>60)占比%",
              "复读度3", "复读度5", "复读度9", "单篇重复5-gram实例"]
    L.append("| " + " | ".join(heads8) + " |")
    L.append("|" + "---|" * len(heads8))
    for g in genres:
        ms = [per_article(r["text"]) for r in rows if r["genre"] == g]
        if not ms:
            continue
        L.append(f"| **{g}** | {len(ms)} | "
                 + " | ".join([fmt(ms, "sent_mean", 1), fmt(ms, "sent_med", 1),
                               fmt(ms, "long_pct", 1), f"{fmt(ms, 'red3', 3)}",
                               f"{fmt(ms, 'red5', 3)}", f"{fmt(ms, 'red9', 3)}",
                               f"{fmt(ms, 'dup5', 1)}"])
                 + " |")

    # ---------- D9 规劝虚词 ----------
    L.append("\n## D9 规劝虚词：为什么阈值必须改用「出现次数」\n")
    L.append("| 文体 | 篇数 | 逐篇均值 | 中位 | P75 | 最大 | 含≥1 次的篇数占比 | 无歧义/千字 | **旧口径(含「当」)/千字** |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    arch_json = {}
    for g in genres:
        ms = [per_article(r["text"]) for r in rows if r["genre"] == g]
        if not ms:
            continue
        vals = sorted(m["arch"] for m in ms)
        n = len(vals)
        cover = sum(1 for v in vals if v >= 1) / n * 100
        L.append(f"| **{g}** | {n} | {statistics.mean(vals):.2f} | {statistics.median(vals):.0f} | "
                 f"{vals[3 * n // 4]:.0f} | {max(vals)} | {cover:.1f}% | "
                 f"{agg(ms, 'arch_pk')[0]:.2f} | **{agg(ms, 'arch_amb_pk')[0]:.2f}** |")
        arch_json[g] = {"n": n, "mean": statistics.mean(vals), "median": statistics.median(vals),
                        "p75": vals[3 * n // 4], "max": max(vals), "cover_pct": cover}
        # 逐词覆盖
        words = {w: sum(1 for r in rows if r["genre"] == g and w in r["text"]) for w in ARCH_UNAMBIG}
        L.append(f"    - 逐词覆盖（篇）：" + "／".join(f"{w} {c}" for w, c in words.items()))

    L.append("\n**读法**：议论文的逐篇**中位为 0**、P75 只有 2 处——"
             "也就是说**过半篇目一次都不用**。所以目标必须写成"
             "「全文 0–3 处」这样的**次数带**，不能写成「3–5 处/千字」"
             "（后者来自把「当…时」从句也计入的 3.8x，是错的）。"
             "在 1000 字量级上每千字率还会被整数量化（2 次=1.75/千字、3 次=2.62/千字，中间无取值），"
             "照区间设目标会导致自检必然「未达」，而这跟稿子好坏无关。\n")

    out = "\n".join(L)
    os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(out + "\n")
    print(out)
    print(f"\n[written] {OUT_MD}")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump({"arch": arch_json}, f, ensure_ascii=False, indent=2)
        print(f"[written] {args.json_out}")


if __name__ == "__main__":
    main()
