# -*- coding: utf-8 -*-
"""
量化验证三位裁判（校准轮 AI、人类专家、本轮 AI）共同指向的一条指控：

    仿稿「太精炼、太齐整」；而他本人是「絮的、重复的、把话说满的」。

逐条量化，成立的才改：
  A 复读度——字符级 n-gram 的重复率（"同一个短语反复用"）
  B 句长分布——平均句长、长句占比（"句子长而絮"）
  C 篇末姿态——是否必定给结论/呼告（"从不留悬念"）
  D 素材光谱——人名 vs 政策/事件/机构（"领袖、政策、党史才是他例证的重心"）

对照：下水议论文子类（确证去重 118 篇） vs 三篇仿稿

用法：python check_verbosity.py
"""
import collections
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import (find_profile, baseline as profile_baseline,  # noqa: E402
                        truth as profile_truth, caliber_line, project_root)

# 项目根：STYLE_PROJECT 优先，其次脚本的上一级（脚本被复制进 skill 后靠 STYLE_PROJECT / cwd）
ROOT = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FEAT = os.path.join(ROOT, "corpus_own", "_final.json")
DRAFTS = ["首篇-裸文版.md", "第二篇-裸文版.md", "第三篇-裸文版.md"]

PROFILE, PROFILE_PATH = find_profile()
PROFILE_BASE = profile_baseline(PROFILE, "verbosity")
PROFILE_TRUTH = profile_truth(PROFILE, "verbosity")

# D：政策/事件/机构类素材词（非人名，但属于"宏大叙事"层）
POLICY_WORDS = [
    "习主席", "习近平", "五年规划", "十四五", "一带一路", "长江禁渔", "生态文明",
    "脱贫攻坚", "脱贫", "乡村振兴", "改革开放", "高考改革", "抗疫", "中国梦",
    "中华民族伟大复兴", "两个一百年", "绿水青山", "金山银山", "国家队", "党",
]

# C：篇末"给结论/呼告"的标记
CLOSING_MARKERS = ["不是吗", "我想，是的", "充满信心", "让我们", "你以为呢", "你体会到",
                   "你想到了吗", "为你点赞", "呢？", "吧！"]


def sentences(t):
    return [s.strip() for s in re.split(r"[。！？；]", t) if s.strip()]


def ngram_redundancy(t, n):
    """复读度 = 1 - 唯一n-gram数/总n-gram数。越高越"絮"。"""
    s = re.sub(r"\s", "", t)
    if len(s) < n:
        return 0.0
    gs = [s[i:i + n] for i in range(len(s) - n + 1)]
    return 1 - len(set(gs)) / len(gs)


def metrics(t):
    sents = sentences(t)
    lens = [len(s) for s in sents]
    para = [p for p in re.split(r"\n\s*\n|\n", t) if len(p.strip()) >= 25]
    return {
        "chars": len(re.sub(r"\s", "", t)),
        "sent_med": statistics.median(lens) if lens else 0,
        "sent_mean": statistics.mean(lens) if lens else 0,
        "long_sent_pct": sum(1 for x in lens if x > 60) / len(lens) * 100 if lens else 0,
        "red3": ngram_redundancy(t, 3),
        "red5": ngram_redundancy(t, 5),
        "red9": ngram_redundancy(t, 9),
        "policy_hits": sum(t.count(w) for w in POLICY_WORDS),
        "policy_pk": sum(t.count(w) for w in POLICY_WORDS) / max(1, len(re.sub(r"\s", "", t))) * 1000,
        "closing": [m for m in CLOSING_MARKERS if m in para[-1]] if para else [],
    }


def _short(fn):
    """表头用的短标签：去掉扩展名与「-裸文版」后缀，最多 10 字。
    不要用 fn[2:5] 这种硬切——换个文件名就会切出乱码标签。"""
    s = os.path.splitext(os.path.basename(fn))[0].replace("-裸文版", "")
    return s[:10] or "稿件"


def collect_drafts(argv):
    """稿件列表：命令行给的优先；否则用默认三篇（存在于项目根时）。
    别名映射让表头短一些。"""
    if argv:
        return {os.path.basename(p): p for p in argv}
    out = {}
    for fn in DRAFTS:
        p = os.path.join(ROOT, "稿件", fn)
        if os.path.exists(p):
            out[fn] = p
    return out


def main():
    ms = []
    if os.path.exists(FEAT):
        with open(FEAT, encoding="utf-8") as f:
            rows = [r for r in json.load(f)
                    if r["verdict"] == "确证" and not r["dup_of"] and r["genre"] == "下水议论文"]
        ms = [metrics(r["text"]) for r in rows]

    drafts = {}
    missing = []
    for name, p in collect_drafts(sys.argv[1:]).items():
        if not os.path.exists(p):
            # 早前这里直接 open，路径不存在就抛 FileNotFoundError 崩掉。
            missing.append(p)
            continue
        with open(p, encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        drafts[name] = metrics("\n".join(lines[1:]))
    if missing:
        print("找不到稿件：" + "、".join(os.path.basename(m) for m in missing))
        if not drafts:
            sys.exit(2)

    def med(k):
        if PROFILE_BASE and k in PROFILE_BASE:
            return PROFILE_BASE[k]          # profile 优先：跨环境可复现
        if not ms:
            return 0.0                      # 既无 profile 又无语料：不崩，交白卷
        return statistics.median(m[k] for m in ms)

    def avg(k):
        if PROFILE_TRUTH.get(k):
            return PROFILE_TRUTH[k]["mean"]
        if not ms:
            return med(k)
        return statistics.mean(m[k] for m in ms)

    print(caliber_line(PROFILE, PROFILE_PATH))
    if ms:
        print(f"对照：下水议论文 {len(ms)} 篇")
    else:
        print("对照：本机无语料 → 只用 profile 基线（skill 独立运行模式）")
    print()
    print(f"{'指标':<22}{'子类中位':>10}{'子类均值':>10}" +
          "".join(f"{_short(fn):>12}" for fn in drafts))
    print("-" * (42 + 12 * len(drafts)))
    for k, name in [("red3", "复读度 3-gram"), ("red5", "复读度 5-gram"), ("red9", "复读度 9-gram"),
                    ("sent_med", "句长中位"), ("sent_mean", "句长均值"),
                    ("long_sent_pct", "长句(>60字)占比%"),
                    ("policy_hits", "政策/机构词（次）"), ("policy_pk", "政策/机构词/千字")]:
        row = f"{name:<22}{med(k):>10.3f}{avg(k):>10.3f}"
        for fn in drafts:
            v = drafts[fn][k]
            row += f"{v:>12.3f}"
        print(row)

    print("\n各篇篇末姿态（是否给结论／呼告）：")
    if ms:
        n_give = sum(1 for m in ms if m["closing"])
        print(f"  子类：{n_give}/{len(ms)} = {n_give / len(ms) * 100:.1f}% 的篇末含结论/呼告标记")
    else:
        print("  子类：本机无语料，跳过（该指标未进 profile）")
    for fn, m in drafts.items():
        print(f"  {fn}：{m['closing'] or '（无）'}")

    print("\n判定：")
    for fn, m in drafts.items():
        notes = []
        for k, name, hi in [("red5", "复读度", False), ("sent_mean", "句长均值", False),
                            ("policy_pk", "政策词密度", False)]:
            if hi:
                continue
            ratio = m[k] / med(k) if med(k) else 0
            if ratio < 0.75:
                notes.append(f"{name}仅为子类中位的 {ratio:.0%}")
        if not m["closing"]:
            notes.append("篇末无结论/呼告标记")
        print(f"  {fn}: " + ("；".join(notes) if notes else "无明显偏差"))


if __name__ == "__main__":
    main()
