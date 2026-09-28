# -*- coding: utf-8 -*-
"""
把复核结论叠加到清洗后的语料上，产出最终交付物。

  1) corpus_own/confirmed/     确证段（进统计池；其中「完整篇章+高置信+下水议论文」再进示例池）
  2) corpus_own/flagged/       存疑段（只留档，不进任何用途）
  3) lf-本人语料库.md       主交付：三档清单 + 标签 + 统计 + 重算指纹 + 素材名单
  4) corpus_own/_final.json    全量标注（含判据与证据）

复核结论来源：_verdict_1..6.json（六批并行复核），叠加下方 OVERRIDES（我逐条核验后的改判）。
"""
import os
import re
import sys
import json
import shutil
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "corpus_own")
CONF = os.path.join(OUT, "confirmed")
FLAG = os.path.join(OUT, "flagged")
DUP = os.path.join(OUT, "duplicates")
DOC = os.path.join(ROOT, "产出", "lf-本人语料库.md")

# —— 人工改判：自动判定出错时，在此逐条覆盖 ——
# 格式：段号: (判定, 文体, 完整度, 置信度, 判据)
#
# 本项目实测的典型情形（写在这里供参考，实际使用时按自己的语料填写）：
#   自动复核把「尾部混入了他人文章」误读成「这是别人的习作」，于是把真文判成排除。
#   回原文核对**署名行的位置与版式**后修正——判据是署名+版式优先，不是文风像不像。
OVERRIDES = {
    3: ("确证", "下水议论文", "完整篇章", "高",
        "正文含『不是吗』×3、『可见』×2；尾部他人附录已由 R8 剥离"),
}

MATERIALS = ["毛泽东", "史铁生", "黄文秀", "路遥", "鲁迅", "袁隆平", "陶渊明",
             "钱学森", "苏轼", "项羽", "长征", "全红婵", "钟南山"]
FP_ITEMS = [("不是吗？", ["不是吗"]), ("可见，", ["可见"]), ("试想", ["试想"]),
            ("须", ["须"]), ("方可/方能", ["方可", "方能"]), ("？", ["？"]),
            ("省略号……", ["……"]), ("价值词", ["主体性", "创造性", "向善", "求真", "辩证"])]


def load_dedup_map():
    """读 _duplicates.json，把每个重复簇的成员映射到簇内最长的那一份（代表）。

    同一篇文章会被号外合集、前文后赏、独立发布各收一次，
    不去重会让该文的语言特征被重复计权（实测影响 17.9% 的语料量）。
    """
    p = os.path.join(OUT, "_duplicates.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    with open(os.path.join(OUT, "_features.json"), encoding="utf-8") as f:
        chars = {f"own_{r['n']:04d}": r["cleaned"]["chars"] for r in json.load(f)}
    m = {}
    for cluster in data.get("clusters", []):
        rep = max(cluster, key=lambda n: chars.get(n, 0))
        for n in cluster:
            if n != rep:
                m[n] = rep
    return m


def load_all():
    with open(os.path.join(OUT, "_features.json"), encoding="utf-8") as f:
        feats = {r["n"]: r for r in json.load(f)}
    verdicts = {}
    for b in range(1, 7):
        p = os.path.join(OUT, f"_verdict_{b}.json")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for v in json.load(f):
                verdicts[v["n"]] = v
    return feats, verdicts


def main():
    feats, verdicts = load_all()
    dup_map = load_dedup_map()
    # 清空输出目录再拷，否则上一轮的残留会混进统计
    for d in (CONF, FLAG, DUP):
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.endswith(".txt"):
                    os.remove(os.path.join(d, fn))
        else:
            os.makedirs(d, exist_ok=True)

    rows = []
    for n in sorted(feats):
        r = feats[n]
        v = verdicts.get(n, {})
        key = f"own_{n:04d}"
        rec = {
            "n": n, "key": key, "src": r["src"], "category": r["category"],
            "headline": r["headline"],
            "verdict": v.get("verdict"), "genre": v.get("genre"),
            "completeness": v.get("completeness"), "confidence": v.get("confidence"),
            "reason": v.get("reason"), "evidence": v.get("evidence"),
            "overridden": False,
            "dup_of": dup_map.get(key),
        }
        if n in OVERRIDES:
            (rec["verdict"], rec["genre"], rec["completeness"],
             rec["confidence"], rec["reason"]) = OVERRIDES[n]
            rec["reason"] = "【改判】" + rec["reason"]
            rec["overridden"] = True

        with open(os.path.join(OUT, r["cleaned"]["file"]), encoding="utf-8") as f:
            text = f.read()
        rec["chars"] = len(text)
        rec["text"] = text
        dest = CONF if (rec["verdict"] == "确证" and not rec["dup_of"]) else (
            DUP if rec["verdict"] == "确证" else FLAG)
        shutil.copy(os.path.join(OUT, r["cleaned"]["file"]),
                    os.path.join(dest, f"own_{n:04d}.txt"))
        rows.append(rec)

    with open(os.path.join(OUT, "_final.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)

    conf_all = [r for r in rows if r["verdict"] == "确证"]
    flag = [r for r in rows if r["verdict"] == "存疑"]
    conf = [r for r in conf_all if not r["dup_of"]]      # 去重后：主口径
    dups = [r for r in conf_all if r["dup_of"]]

    def fp_of(rs):
        b = "".join(r["text"] for r in rs)
        n = len(b) or 1
        out = []
        for name, words in FP_ITEMS:
            c = sum(b.count(w) for w in words)
            cover = sum(1 for r in rs if any(w in r["text"] for w in words)) / len(rs) * 100
            out.append((name, c, c / n * 1000, cover))
        return out, n

    fp, nc = fp_of(conf)
    fp_all, nc_all = fp_of(conf_all)
    body = "".join(r["text"] for r in conf)

    # —— 示例池：确证 + 完整篇章 + 高置信 + 下水议论文 + 800–1600 字 ——
    pool = [r for r in conf
            if r["completeness"] == "完整篇章" and r["confidence"] == "高"
            and r["genre"] == "下水议论文" and 800 <= r["chars"] <= 1600]

    md = []
    md.append("# lf本人语料库\n")
    md.append("> 来源：公众号「示例教研公众号」（`example_account`）全量抓取文本 "
              "`wxfetch/`（631 文件 / 去重 600 篇）。\n"
              "> 方法：按**署名行**（「示例市教研院　lf」等 5 种单位写法）程序化切分 → "
              "规则清洗（剥图片名、他人署名、栏目标题、评点夹批、总评块）→ **逐段人工复核**。\n"
              "> 复核判据：**署名 + 版式优先；语言指纹只提示可疑，不用于否决**。分三档：确证 / 存疑 / 排除。\n"
              "> **不删只标**：全文版在 `corpus_own/raw/`，纯净版在 `corpus_own/clean/`，"
              "剪掉的内容全部记录在 `_features.json`。\n")
    md.append(f"\n## 总览\n")
    md.append("| 指标 | 数值 |\n|---|---|\n")
    md.append(f"| 切出段数 | {len(rows)} |\n")
    md.append(f"| 确证段数 | {len(conf_all)} |\n")
    md.append(f"| 其中重复收录 | **{len(dups)} 段**（同一篇文章被合集/栏目重复发布，已折叠）|\n")
    md.append(f"| **确证去重后** | **{len(conf)} 篇 / {nc:,} 字** ← 全部统计的主口径 |\n")
    md.append(f"| 存疑 | {len(flag)} 段 / {sum(r['chars'] for r in flag):,} 字 |\n")
    md.append(f"| 排除 | {len(rows) - len(conf_all) - len(flag)} 段 |\n")
    clean_total = sum(r["cleaned"]["chars"] for r in feats.values())
    raw_total = sum(r["chars"] for r in feats.values())
    md.append(f"| 原始切分 | {raw_total:,} 字 |\n")
    md.append(f"| 清洗后（216 段纯净版）| {clean_total:,} 字（剪除 {raw_total - clean_total:,} 字 / "
              f"{(raw_total - clean_total) / raw_total * 100:.1f}%）|\n")
    md.append(f"| 改判段数 | {sum(1 for r in rows if r['overridden'])} 段（子代理判错，我核原文后修正）|\n")

    md.append("\n## 语言指纹（去重后主口径，可复现）\n")
    md.append("> 这两个数是**分布值**，不是「出现过 N 次」。"
              "末列为**未去重**时的值——同一篇文章被重复收录会把它自己的特征重复计权，"
              "实测这一项影响约 18% 的语料量。\n\n")
    md.append("| 指纹项 | 次数 | 每千字 | 段落覆盖率 | 未去重每千字 | 偏差 |\n|---|---|---|---|---|---|\n")
    for (name, c, per_k, cover), (_, _, per_k_all, _) in zip(fp, fp_all):
        delta = (per_k_all - per_k) / per_k * 100 if per_k else 0
        md.append(f"| {name} | {c} | {per_k:.2f} | {cover:.1f}% | {per_k_all:.2f} | "
                  f"{delta:+.1f}% |\n")

    md.append("\n### 与蒸馏报告第 3 版（全量 196 万字口径）的对照\n")
    CONTRAST = {"不是吗？": 0.35, "可见，": 0.27, "试想": 0.04, "须": 0.20,
                "方可/方能": 0.25, "？": 1.66, "省略号……": 0.64, "价值词": 0.30}
    md.append("| 指纹项 | 本人确证集（每千字） | 全量口径（每千字） | 倍数 |\n|---|---|---|---|\n")
    for name, c, per_k, cover in fp:
        base = CONTRAST.get(name)
        if base:
            md.append(f"| {name} | {per_k:.2f} | {base:.2f} | **{per_k / base:.1f}×** |\n")

    md.append("\n## 重复收录（去重前必须知道的事）\n")
    md.append(f"> 该号的运营方式决定了同一篇文章会被**重复发布**：先在「同题共写」或「号外」里作为合集的一篇出现，"
              f"再被「前文后赏」单独拿出来配点评，有时还会独立成篇。\n"
              f"> 实测 **{len(dups)} 段属于重复收录**（用 5-gram Jaccard ≥ 0.55 判定），"
              f"不去重会让这些文章的**语言特征被重复计权**，也会让「跨段重复短句」这类套路化指标失真。\n"
              f"> 处理方式仍是**不删只标**：`_final.json` 里每段带 `dup_of` 字段指向保留的那一份。\n\n")
    by_rep = {}
    for r in dups:
        by_rep.setdefault(r["dup_of"], []).append(r)
    md.append("| 保留 | 折叠掉的重复 | 原标题 |\n|---|---|---|\n")
    for rep, members in sorted(by_rep.items(), key=lambda x: -len(x[1])):
        names = "、".join(m["key"].replace("own_", "") for m in sorted(members, key=lambda x: x["key"]))
        head = next((r["headline"] for r in conf_all if r["key"] == rep), "")
        md.append(f"| `{rep}` | {names} | {(head or '')[:30]} |\n")

    md.append("\n## 素材名单（去重后主口径）\n")
    md.append("| 素材 | 次数 | 每千字 |\n|---|---|---|\n")
    for w in MATERIALS:
        c = body.count(w)
        md.append(f"| {w} | {c} | {c / nc * 1000:.2f} |\n")
    md.append("\n> 蒸馏报告第 3 版把「苏轼 128 次、长征反复出现」列为核心素材——"
              "那是在含师生收录件的全量上算的。**在他的本人文本里，苏轼与长征几乎不出现。**\n")

    md.append("\n## 文体与完整度分布（确证集）\n")
    for label, key in [("文体", "genre"), ("完整度", "completeness"), ("置信度", "confidence")]:
        cnt = Counter(r[key] for r in conf)
        md.append(f"\n**{label}**：" + " / ".join(f"{k} {v}" for k, v in cnt.most_common()) + "\n")

    md.append(f"\n## 仿写示例池（{len(pool)} 篇）\n")
    md.append("> 筛选条件：确证 × 完整篇章 × 高置信 × 下水议论文 × 800–1600 字。"
              "供生成管线的 few-shot 使用。\n\n")
    md.append("| # | 字数 | 原标题 | 出处 |\n|---|---|---|---|\n")
    for r in sorted(pool, key=lambda x: -x["chars"]):
        md.append(f"| {r['n']:04d} | {r['chars']} | {r['headline']} | `{r['src'][:44]}` |\n")

    md.append(f"\n## 存疑清单（{len(flag)} 段，只留档、不进任何用途）\n")
    md.append("| # | 字数 | 原标题 | 判据 |\n|---|---|---|---|\n")
    for r in flag:
        md.append(f"| {r['n']:04d} | {r['chars']} | {r['headline']} | {r['reason']} |\n")

    md.append(f"\n## 全部确证段（{len(conf)} 段）\n")
    md.append("| # | 字数 | 文体 | 完整度 | 置信度 | 原标题 | 判据 |\n|---|---|---|---|---|---|---|\n")
    for r in conf:
        rs = r["reason"] or ""
        rs = re.sub(r"\s+", " ", rs)[:70]
        rs = rs.replace("|", "/")
        hl = (r["headline"] or "").replace("|", "/")[:26]
        md.append(f"| {r['n']:04d} | {r['chars']} | {r['genre']} | {r['completeness']} | "
                  f"{r['confidence']} | {hl} | {rs} |\n")

    md.append("\n---\n\n## 工具链\n\n")
    md.append("| 脚本 | 作用 |\n|---|---|\n")
    md.append("| `tools/extract_own_corpus.py` | 按署名行切分本人段落（`--emit` 导出 / `--tails` 查边界）|\n")
    md.append("| `tools/review_own_corpus.py` | 落盘 216 段 + 计算风险旗标（R1–R6 特征）|\n")
    md.append("| `tools/clean_own_corpus.py` | 清洗流水线 A–E（R1–R8 八条剥离规则，逐条记账）|\n")
    md.append("| `tools/dump_review_batches.py` | 打包自包含复核任务书 |\n")
    md.append("| `tools/diag_segment.py` | 按序号打印署名行上下文（诊断切分错误）|\n")
    md.append("| `tools/fingerprint.py` | 双口径语言指纹对照 |\n")
    md.append("| `tools/aggregate_corpus.py` | 叠加复核结论、出最终库与本文件 |\n")

    with open(DOC, "w", encoding="utf-8") as f:
        f.write("".join(md))

    print(f"确证（去重后）{len(conf)} 篇 / {nc:,} 字 → corpus_own/confirmed/")
    print(f"重复收录 {len(dups)} 段 → corpus_own/duplicates/")
    print(f"存疑 {len(flag)} 段 → corpus_own/flagged/")
    print(f"改判 {sum(1 for r in rows if r['overridden'])} 段")
    print(f"示例池 {len(pool)} 篇")
    print(f"已写出 {DOC}")


if __name__ == "__main__":
    main()
