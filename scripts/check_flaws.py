# -*- coding: utf-8 -*-
"""
验证第三位裁判的核心指控：「C 太顺、太齐、太干净，没有他的毛边」。

裁判③说这 8 篇真文里有：
  · 呼喊式感叹（"斯言诚哉！斯言诚哉！"）
  · 整句复读（一个意思原封不动重复三四遍）
  · 重字/别字/掉字

前两条可以量化。测三件事：
  M1 感叹号密度（/千字）
  M2 同篇内整句复读率（≥12 字的句子在同篇出现 ≥2 次）
  M3 叠字/重复字异常（如"要要""便便"），以及"啥/为啥/大家伙"等口语词密度

对照：下水议论文子类 vs 首篇仿稿
"""
import os
import re
import sys
import json
import statistics
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import (find_profile, baseline as profile_baseline,  # noqa: E402
                        truth as profile_truth, caliber_line, project_root)

# 项目根：STYLE_PROJECT 优先，其次脚本的上一级（脚本被复制进 skill 后靠 STYLE_PROJECT / cwd）
ROOT = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FEAT = os.path.join(ROOT, "corpus_own", "_final.json")
DRAFT = os.path.join(ROOT, "首篇-裸文版.md")

PROFILE, PROFILE_PATH = find_profile()
PROFILE_BASE = profile_baseline(PROFILE, "flaws")
PROFILE_TRUTH = profile_truth(PROFILE, "flaws")

COLLOQ = ["啥", "大家伙", "这把", "搞的", "咋", "一下子", "啊", "呢"]


def split_sents(t):
    parts = re.split(r"[。！？；\n…]", t)
    return [re.sub(r"\s", "", p) for p in parts]


def metrics(text, label):
    text = re.sub(r"\s", "", text)
    nc = len(text) or 1
    sents = split_sents(text)
    # 整句复读：≥12 字的句子在同篇出现 ≥2 次（去重后统计被复读的字数占比）
    c = Counter(s for s in sents if len(s) >= 12)
    rep = {s: n for s, n in c.items() if n >= 2}
    rep_chars = sum(len(s) * n for s, n in rep.items()) + sum(
        len(s) for s in sents if len(s) < 12 and c.get(s, 0) >= 2)
    # 叠字异常：AA 式连续重复字（排除正常叠词）
    NORMAL_REDUP = {"渐渐", "慢慢", "稍稍", "常常", "纷纷", "人人", "天天", "年年",
                    "刚刚", "明明", "深深", "轻轻", "默默", "静静", "重重", "层层",
                    "滴滴", "点点", "丝丝", "阵阵", "处处", "时时", "刻刻", "念念"}
    aa = [m.group(0) for m in re.finditer(r"([\u4e00-\u9fa5])\1", text)
          if m.group(0) not in NORMAL_REDUP]
    return {
        "label": label, "chars": nc,
        "tan_pk": round(text.count("！") / nc * 1000, 2),
        "q_pk": round(text.count("？") / nc * 1000, 2),
        "rep_ratio": round(rep_chars / nc * 100, 1),
        "rep_types": len(rep),
        "aa_pk": round(len(aa) / nc * 1000, 2),
        "aa_samples": "、".join(aa[:8]),
        "collq_pk": round(sum(text.count(w) for w in COLLOQ) / nc * 1000, 2),
    }


def main():
    draft_path = sys.argv[1] if len(sys.argv) > 1 else DRAFT
    agg = []
    if os.path.exists(FEAT):
        with open(FEAT, encoding="utf-8") as f:
            rows = [r for r in json.load(f)
                    if r["verdict"] == "确证" and not r["dup_of"] and r["genre"] == "下水议论文"]
        agg = [metrics(r["text"], f"#{r['n']}") for r in rows]

    print(caliber_line(PROFILE, PROFILE_PATH))
    print(f"下水议论文 {len(agg)} 篇" if agg else "本机无语料 → 只用 profile 基线（skill 独立运行模式）")
    print()

    def mean(k):
        if PROFILE_TRUTH.get(k):
            return PROFILE_TRUTH[k]["mean"]
        return sum(a[k] for a in agg) / len(agg)

    def median(k):
        if PROFILE_BASE and k in PROFILE_BASE:
            return PROFILE_BASE[k]
        return statistics.median(a[k] for a in agg)

    hdr = f"{'指标':<22}{'子类均值':>12}{'中位':>8}{'仿稿':>10}   判定"
    print(hdr)
    print("-" * 68)

    with open(draft_path, encoding="utf-8") as f:
        dl = [ln for ln in f.read().splitlines() if ln.strip()]
    draft = metrics("\n".join(dl[1:]), "仿稿")

    for key, name, hi_better in [
        ("tan_pk", "感叹号/千字", True),
        ("q_pk", "问号/千字", None),
        ("rep_ratio", "整句复读字数占比%", True),
        ("aa_pk", "叠字异常/千字", True),
        ("collq_pk", "口语词/千字", True),
    ]:
        m, med, dv = mean(key), median(key), draft[key]
        if hi_better is None:
            verdict = "—"
        elif dv < med * 0.5:
            verdict = "❌ 明显低于子类"
        elif dv < med * 0.8:
            verdict = "⚠ 偏低"
        else:
            verdict = "OK"
        print(f"{name:<22}{m:>12.2f}{med:>8.2f}{dv:>10.2f}   {verdict}")

    if agg:
        print(f"\n仿稿叠字异常样本：{draft['aa_samples'] or '（无）'}")
        print(f"子类典型叠字异常 Top5：")
        for a in sorted(agg, key=lambda x: -x["aa_pk"])[:5]:
            print(f"   {a['label']:<8}{a['aa_pk']:>6.2f}/千字  {a['aa_samples'][:40]}")
        print(f"\n仿稿整句复读：{draft['rep_types']} 种 / 占比 {draft['rep_ratio']}%")
        print(f"子类整句复读：均值 {mean('rep_types'):.1f} 种 / 占比 {mean('rep_ratio'):.1f}%")


if __name__ == "__main__":
    main()
