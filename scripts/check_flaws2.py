# -*- coding: utf-8 -*-
"""
针对四位裁判（含 1 位人类专家）指出的四处破绽，逐条量化——先验证指控是否成立，再决定改不改。

  Ａ 例证后是否追「可见」：含人物素材的段落里，有多少在后面（本段或下一段）接上「可见」或反问
  Ｂ 段落长短的起伏：段长的变异系数 CV、以及最长/最短比
  Ｃ 贴标签式起句：「正面最典型的」「反面最典型的」这类，他本人用不用
  Ｄ 其他标点密度：分号、顿号、破折号、引号、括号（感叹号已单独查过）

对照：下水议论文子类 vs 首篇
"""
import os
import re
import sys
import json
import statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import (find_profile, baseline as profile_baseline,  # noqa: E402
                        truth as profile_truth, caliber_line, project_root)

# 项目根：STYLE_PROJECT 优先，其次脚本的上一级（脚本被复制进 skill 后靠 STYLE_PROJECT / cwd）
ROOT = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FEAT = os.path.join(ROOT, "corpus_own", "_final.json")
# ⚠ 稿件路径**必须在 main() 里取**，不能放模块级——否则被别的脚本 import 时
#   会把那个脚本的 argv 当成稿件路径。
DEFAULT_DRAFT = os.path.join(ROOT, "稿件", "首篇-裸文版.md")

PROFILE, PROFILE_PATH = find_profile()
PROFILE_BASE = profile_baseline(PROFILE, "flaws2")
PROFILE_TRUTH = profile_truth(PROFILE, "flaws2")

MATERIALS = ["毛泽东", "史铁生", "黄文秀", "鲁迅", "路遥", "张桂梅", "袁隆平",
             "陶行知", "钱学森", "苏轼", "陶渊明", "钟南山"]

LABEL_OPENERS = ["正面最典型的", "反面最典型的", "最典型的", "最典型的是",
                 "正面最突出", "反面最突出", "正面例证", "反面例证"]


def paras(t):
    return [p.strip() for p in re.split(r"\n\s*\n|\n", t) if len(p.strip()) >= 25]


def metrics(text):
    ps = paras(text)
    if not ps:
        return None
    # A 例证段是否收口
    ev, ev_closed = 0, 0
    for i, p in enumerate(ps):
        if any(m in p for m in MATERIALS):
            ev += 1
            nxt = ps[i + 1] if i + 1 < len(ps) else ""
            if ("可见" in p) or ("可见" in nxt) or p.rstrip().endswith(("不是吗？", "不是吗")):
                ev_closed += 1
    # B 段长起伏
    lens = [len(p) for p in ps]
    cv = statistics.pstdev(lens) / (sum(lens) / len(lens)) if len(lens) > 1 else 0
    # C 贴标签
    labels = sum(text.count(w) for w in LABEL_OPENERS)
    # D 其他标点
    # ⚠ 逐篇值**不要**先 round 再取均值/中位——round 会改变中位（实测分号中位
    #   会从 2.06 变 2.05），与 strata_extra.py 对不上。只在打印时格式化。
    nc = len(re.sub(r"\s", "", text)) or 1
    return {
        "paras": len(ps),
        "ev": ev, "ev_closed": ev_closed,
        "ev_rate": round(ev_closed / ev * 100, 1) if ev else None,
        "cv": round(cv, 3), "len_min": min(lens), "len_max": max(lens),
        "ratio": round(max(lens) / min(lens), 2),
        "labels": labels,
        "semicolon": text.count("；") / nc * 1000,
        "pause": text.count("、") / nc * 1000,
        "dash": text.count("——") / nc * 1000,
        "quote": (text.count("“") + text.count("”")) / nc * 1000,
        "paren": text.count("（") / nc * 1000,
    }


def kejian_new_material(text, mats):
    """第 03 轮 §4.2：「可见」是否被拿来引入**新**例证。

    真值（118 篇全量核验）：262 个「可见」句里只有 1 句（0.4%）引入首次出现的素材。
    所以仿写时**不用**这种写法——但反过来，它也不能当作"非他所写"的证据
    （稀有 ≠ 非他，见项目铁律）。
    """
    seen, bad = set(), []
    for p in re.split(r"\n+", text):
        for s in re.split(r"(?<=[。！？；])", p):
            s = s.strip()
            if not s:
                continue
            if "可见" in s:
                fresh = [m for m in mats if m in s and m not in seen]
                if fresh:
                    bad.append((fresh, s[:50]))
            for m in mats:
                if m in s:
                    seen.add(m)
    return bad


def main():
    DRAFT = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DRAFT
    ms_all, ms_ev = [], []
    if os.path.exists(FEAT):
        with open(FEAT, encoding="utf-8") as f:
            rows = [r for r in json.load(f)
                    if r["verdict"] == "确证" and not r["dup_of"] and r["genre"] == "下水议论文"]
        ms_all = [m for m in (metrics(r["text"]) for r in rows) if m]
        ms_ev = [m for m in ms_all if m["ev"] > 0]

    print(caliber_line(PROFILE, PROFILE_PATH))
    if ms_all:
        print(f"语料：下水议论文 {len(ms_all)} 篇；其中含人物素材 {len(ms_ev)} 篇")
    else:
        print("语料：不在本机 → 只用 profile 基线（skill 独立运行模式）")
    print("基线口径：A（例证段收口率）只在**含人物素材的篇目**上算；"
          "B/C/D（段长起伏、贴标签、标点密度）在**全部篇目**上算。")
    print("          ⚠ 早前把标点也放在『含人物素材』子集上算并当『子类中位』写进文档——")
    print("            该子集只有 46/118 篇，顿号中位因此虚高 31%（4.76 vs 全量 3.62）。已修正。\n")

    if not os.path.exists(DRAFT):
        print(f"找不到稿件：{DRAFT}")
        sys.exit(2)
    with open(DRAFT, encoding="utf-8") as f:
        dl = [ln for ln in f.read().splitlines() if ln.strip()]
    if len(dl) < 2:
        print(f"稿件 {os.path.basename(DRAFT)} 只有标题行／为空，无法计算指标。")
        sys.exit(2)
    d = metrics("\n".join(dl[1:]))
    if d is None:
        # 稿件里没有任何 ≥25 字的段落（例如拿一小段占位文本试跑）。
        # 早前会直接拿 None 往下走，在比较时抛 TypeError 崩掉整个脚本。
        print(f"稿件 {os.path.basename(DRAFT)} 里没有 ≥25 字的段落，无法计算任一指标。")
        sys.exit(2)

    print(f"{'指标':<26}{'子类均值':>10}{'中位':>9}{'仿稿':>10}   判定")
    print("-" * 70)
    for key, name, rule, use in [
        ("ev_rate", "例证段收口率 %", "higher", ms_ev),
        ("cv", "段长变异系数 CV", "higher", ms_all),
        ("ratio", "最长/最短段比", "higher", ms_all),
        ("labels", "贴标签起句次数", "lower", ms_all),
        ("semicolon", "分号/千字", "band", ms_all),
        ("pause", "顿号/千字", "band", ms_all),
        ("dash", "破折号/千字", "band", ms_all),
        ("quote", "引号/千字", "band", ms_all),
        ("paren", "括号/千字", "band", ms_all),
    ]:
        if PROFILE_BASE and key in PROFILE_BASE:
            med = PROFILE_BASE[key]          # profile 优先：跨环境可复现
            avg = PROFILE_TRUTH.get(key, {}).get("mean", med)
        else:
            vals = [m[key] for m in use if m[key] is not None]
            if not vals:
                continue
            med = statistics.median(vals)
            avg = sum(vals) / len(vals)
        dv = d[key]
        if dv is None:
            # 稿件侧算不出这一项（如全文无人物素材 → 例证段收口率无定义）。
            # 早前这里会直接拿 None 去比较，抛 TypeError 崩掉整个脚本。
            print(f"{name:<26}{avg:>10.2f}{med:>9.2f}{'—':>10}   稿件无此项（跳过）")
            continue
        if rule == "higher":
            verdict = "❌ 明显偏低" if dv < med * 0.6 else ("⚠ 偏低" if dv < med * 0.85 else "OK")
        elif rule == "lower":
            # ⚠ 中位为 0 时**比率判据失效**：`dv > med*3` 会退化成 `dv > 0`，
            # 于是任何非零值都判"明显偏高"。
            # 而「贴标签起句」他本人是在用的：9/118 篇（7.6%），最多的一篇用了 4 次。
            # 照旧判据，他自己那 9 篇也会全被判违规——判据在惩罚真文。
            # 改用**他本人的分布上界**：超过他任何一篇才算越界；1..上界之间只提示。
            if med > 0:
                verdict = "❌ 明显偏高" if dv > med * 3 else "OK"
            else:
                dist = (PROFILE_TRUTH or {}).get(key) or {}
                cap = dist.get("max")
                if cap is None:
                    vals = [m[key] for m in use if m[key] is not None]
                    cap = max(vals) if vals else 0
                share = dist.get("_coverage")
                if dv > cap:
                    verdict = f"❌ 超过他本人最大值（{cap:.0f} 次）"
                elif dv >= 1:
                    verdict = (f"⚠ 稀疏手法：他仅少数篇目用、{cap:.0f} 次封顶"
                               f"{f'（覆盖 {share:.1%}）' if share else ''}——确认是刻意选择")
                else:
                    verdict = "OK"
        else:
            verdict = "—" if dv == 0 and med == 0 else (
                "❌ 为 0" if dv == 0 and med > 1 else
                ("⚠ 偏低" if dv < med * 0.5 else ("⚠ 偏高" if dv > med * 2 else "OK")))
        print(f"{name:<26}{avg:>10.2f}{med:>9.2f}{dv:>10.2f}   {verdict}")

    print(f"\n仿稿段长：{d['paras']} 段，最短 {d['len_min']} 字 / 最长 {d['len_max']} 字")
    print(f"仿稿例证段：{d['ev']} 段，其中收口 {d['ev_closed']} 段")

    # ── 第 03 轮 §4.2：「可见」不得借来引入新例证 ────────────────────
    mats = (PROFILE or {}).get("wordlists", {}).get("materials_ok") or MATERIALS
    bad = kejian_new_material("\n".join(dl[1:]), mats)
    print("\n「可见」是否借来引入新例证（真文 1/262 = 0.4%）：")
    if bad:
        for fresh, s in bad:
            print(f"  ⚠ 引入新素材 {'、'.join(fresh)}：{s}…")
    else:
        print("  ✓ 无（「可见」都由已给出的例证推出结论）")


if __name__ == "__main__":
    main()
