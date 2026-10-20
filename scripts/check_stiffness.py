#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生硬检测：段首追问提示语（N6，硬规则）+ 一组只读数不判定的质地指标。

来源：2026-10-20 项目 owner 验收原话「感觉文字依然生硬，不像lf写的」。
量化（`tools/probe_stiffness.py`，118 篇真文 vs 第 08 轮试跑稿 vs 专家档2 旧稿）：

  | 指标                      | 真文 118 篇 | 试跑稿 | 旧稿   |
  |---------------------------|------------|--------|--------|
  | 段首追问提示语（N6）       | **0/118**  | 39.5% 段 | 8.8% 段 |
  | 段首功能过渡（回到/至于…） | 5.9% 篇    | —      | —      |
  | 短判断句（金句）/千字      | 4.34       | 7.61   | 5.93   |
  | 对偶句/千字                | 3.03       | 4.98   | 5.79   |
  | 句长中位                   | 29         | 20     | 22     |

**为什么 N6 能立硬规则**：追问提示语（先问一句／还要问／再往深处问／更沉的一层／
一层一问／一层一层）8 个词在全库 118 篇里**全文零出现**——
零命中型约束，写了就是本期新发明的写法，不存在误伤真文的问题。
**为什么其余指标只读数**：金句密度、对偶、句长都是**多数命中型**（真文自己就有
4.34/千字、3.03/千字、中位 29），拿来判违规会误伤真文——与第 07 轮"收束同构"同型，
只能作生成偏好（写进 SKILL 的倾向节），不进判定。

功能过渡（回到／再看／至于／说到底／放到／放大）是 **5.9% 篇目的稀疏手法**：
仿写全篇 ≤1 处；检测器报数并提示，**不判违规**。

用法：
  python tools/check_stiffness.py --files a.md b.md   # 查稿（N6 命中 → rc=1）
  python tools/check_stiffness.py --corpus            # 118 篇真文，N6 必须 0 命中
  python tools/check_stiffness.py --selftest          # 反向测试，必须全过
"""
import argparse
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import find_profile  # noqa: E402

# ── N6：段首追问提示语（硬规则，0/118）────────────────────────────────────
# 只查**段首 14 字内**——全文扫描会把段中的正当用法算进来。
# ⚠ 只收**纯程序提示词**（8 个，全部 0/118 全文零出现）。
#   「反过来／转过来」**故意不收**：它们是内容反转词，不是程序提示——
#   真文 #184 段中正当用过（"其实，有时候反过来，家庭也是很和谐的"）。
#   收它们就是拿稀有当排除依据（项目纪律：稀有 ≠ 非他），段首误报真文形态。
#   反向测试第 3 条守住的就是这个决定。
N6_PATTERNS = ["先问", "还要问", "再问", "再往", "往下再", "更沉的",
               "一层一问", "一层一层"]

# ── 功能过渡（稀疏手法 5.9% 篇目；只报数）────────────────────────────────
F_PATTERNS = ["回到", "再看", "至于", "说到底", "放到", "放大", "把话", "另一头", "回过头"]

# 判断词口径与 probe_stiffness.py **逐字相同**（不能一个工具一个定义——
# 那正是本项目"两处逻辑漂移"的老毛病）。真文段首判断 5.9%。
JUDGE_RE = re.compile("不是|才是|就是|难|要紧|偏|便")
SENT_END = "。！？；"          # 项目口径：只用中文句末标点断句，不加 ASCII !?;

# 真文读数（probe_stiffness.py 2026-10-20 实测；语料不在时用这组冻结值并打印说明）
# ⚠ 口径：短判断句＝≤20 字且含判断词（不是/才是/就是/难/要紧/偏/便）——与 probe 同口径。
#   曾用宽口径（含裸"是"）算出 5.62，已废弃；对齐后真值 4.34。
TRUTH_FROZEN = {"aph_per_k": 4.34, "dual_per_k": 3.03, "sent_med": 29, "first_judge_pct": 5.9}


def paras_of(text):
    return [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]


def first_sentence(para):
    out, buf = [], []
    for ch in para:
        buf.append(ch)
        if ch in SENT_END:
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out[0] if out else ""


def sents_of(text):
    out, buf = [], []
    for ch in text:
        buf.append(ch)
        if ch in SENT_END:
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def n6_hits(text):
    """段首追问提示语命中清单 [(段号, 段首片段)]。"""
    ps = paras_of(text)
    hits = []
    for i, p in enumerate(ps[1:], start=2):      # 跳过标题行
        fs = first_sentence(p)[:14]
        for pat in N6_PATTERNS:
            if pat in fs:
                hits.append((i, fs, pat))
                break
    return hits


def f_count(text):
    ps = paras_of(text)
    return sum(1 for p in ps[1:] if any(x in first_sentence(p)[:14] for x in F_PATTERNS))


def readings(text):
    ps = paras_of(text)
    body = "\n".join(ps[1:]) if len(ps) > 1 else ""
    chars = len(re.sub(r"\s", "", body))
    sents = sents_of(body)
    if not chars or not sents:
        return None
    aph = sum(1 for s in sents if len(s) <= 20 and JUDGE_RE.search(s))
    dual = 0
    for s in sents:
        for m in re.finditer(r"[，]", s):
            a, b = s[:m.start()], s[m.start() + 1:]
            if 6 <= len(a) <= 30 and abs(len(a) - len(b)) <= 1 and 6 <= len(b) <= 30:
                dual += 1
                break
    fj = sum(1 for p in ps[1:]
             if JUDGE_RE.search(first_sentence(p)) and len(first_sentence(p)) <= 30)
    slens = sorted(len(s) for s in sents)
    return {
        "aph_per_k": aph / chars * 1000,
        "dual_per_k": dual / chars * 1000,
        "sent_med": slens[len(slens) // 2],
        "first_judge_pct": fj / max(len(ps) - 1, 1) * 100,
    }


def check_file(path, truth):
    text = open(path, encoding="utf-8").read()
    hits = n6_hits(text)
    fc = f_count(text)
    rd = readings(text) or {}
    print(f"\n══ {os.path.basename(path)} ══")
    if hits:
        print(f"  ❌ N6 段首追问提示语 {len(hits)} 处（真值 0/118，零命中红线）：")
        for i, fs, pat in hits:
            print(f"     段{i}「{fs}」（命中「{pat}」）")
    else:
        print("  ✓ N6 段首追问提示语：0 处")
    print(f"  · 功能过渡（段首）：{fc} 处（真文稀疏手法 5.9% 篇目；偏好全篇 ≤1，不判违规）")
    if rd:
        print(f"  · 短判断句 {rd['aph_per_k']:.1f}/千字（真文 {truth['aph_per_k']:.1f}，偏好参考）｜"
              f"对偶 {rd['dual_per_k']:.2f}/千字（真文 {truth['dual_per_k']:.2f}）｜"
              f"句长中位 {rd['sent_med']:.0f}（真文 {truth['sent_med']:.0f}）｜"
              f"段首判断 {rd['first_judge_pct']:.0f}%（真文 {truth['first_judge_pct']:.0f}%）")
        print("    （这四项是多数命中型，只读数——写进 SKILL 的是倾向，不是红线）")
    return len(hits)


def corpus_mode():
    rows = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "corpus_own", "_final.json"), encoding="utf-8"))
    rows = [r for r in rows if r.get("verdict") == "确证" and not r.get("dup_of")
            and r.get("genre") == "下水议论文"]
    bad = [(r["n"], h) for r in rows for h in n6_hits(r["text"])]
    print(f"118 篇真文：N6 命中 {len(bad)} 处")
    for n, h in bad[:10]:
        print(f"  #{n:03d} 段{h[0]}「{h[1]}」")
    aph = [readings(r["text"])["aph_per_k"] for r in rows if readings(r["text"])]
    print(f"短判断句篇均 {sum(aph)/len(aph):.2f}/千字（冻结值 {TRUTH_FROZEN['aph_per_k']}）")
    return 1 if bad else 0


def selftest():
    """反向测试：每条都必须按预期红/绿，否则检测器是摆设。"""
    results = []

    def rep(name, ok):
        results.append((name, ok))
        print(f"  {'✓' if ok else '✗'} {name}")

    # 1. 构造追问提示语 → 必须红
    bad = "标题：x\n\n还要问：期待错了么？\n\n怕是怪不到他们头上的。\n"
    rep("构造「还要问」段首 → N6 报红", len(n6_hits(bad)) == 1)
    bad2 = "标题：x\n\n先问一句：这是什么？\n\n正文一句。\n"
    rep("构造「先问一句」段首 → N6 报红", len(n6_hits(bad2)) == 1)
    # 2. 功能过渡 → 必须不红（稀疏手法，不判违规）
    ok = "标题：x\n\n说到底，人是要害。\n\n正文一句，说得明白。\n"
    rep("构造「说到底」段首 → N6 不误报", len(n6_hits(ok)) == 0)
    # 3. 段中的"反过来" → 必须不红（#184 形态；且该词已故意不进红线词表）
    mid = "标题：x\n\n其实，有时候反过来，家庭也很和谐。\n\n再说一句正文，收尾。\n"
    rep("构造段中「反过来」→ N6 不误报", len(n6_hits(mid)) == 0)
    # 4. 干净稿 → 全绿
    clean = "标题：x\n\n人是要有一点精神的。\n\n古往今来，语言的河流一直都是这样流着，从诗经离骚到白话文运动，脉脉相承，不曾断绝，这就是最好的证明。\n"
    rep("构造干净稿 → N6 0 命中", len(n6_hits(clean)) == 0)
    # 5. 语料在时，真文必须 0 命中
    try:
        rc = corpus_mode()
        rep("118 篇真文 N6 0 命中", rc == 0)
    except FileNotFoundError:
        rep("118 篇真文 N6 0 命中（语料不在，跳过）", True)
    # 6. 试跑题2（已知最差稿）必须报红——证明对真数据有效
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "远程生文", "第08轮", "工序试跑", "包", "task", "output", "题目2-裸文.md")
    if os.path.isfile(p):
        rep("试跑题2（5 处追问提示）→ N6 报红", len(n6_hits(open(p, encoding='utf-8').read())) >= 3)
    else:
        rep("试跑题2 → N6 报红（文件不在，跳过）", True)
    ok = all(x[1] for x in results)
    print(f"\n合计 {sum(1 for _, x in results if x)}/{len(results)} 通过" + ("" if ok else "　← 有失败"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--corpus", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if args.corpus:
        return corpus_mode()

    if not args.files:
        ap.error("要给 --files / --corpus / --selftest 之一")

    prof = find_profile()
    truth = TRUTH_FROZEN
    print(f"profile：{prof or '（未找到，用冻结真值）'}")
    if not prof:
        print(f"  ⚠ 语料/profile 不在 → 用 2026-10-20 冻结真值：{TRUTH_FROZEN}")
    total = 0
    for f in args.files:
        if not os.path.isfile(f):
            print(f"⚠ 找不到稿件：{f}")
            continue
        total += check_file(f, truth)
    print(f"\nN6 命中合计：{total} 处" + ("（0 = 过硬规则）" if total == 0 else "（>0 = 越界）"))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
