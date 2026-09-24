# -*- coding: utf-8 -*-
"""
风格分目别类：把"一个平均指纹"拆成若干子画像。

混合口径的平均值会掩盖方差——他写下水议论文和写叙事散文不是一个语体，
写在「同题共写」里和写在「前文后赏」里也不是一个写法。
仿写要用的是**目标子类的画像**，不是全体平均。

切分维度
  D1 文体（genre）
  D2 栏目（category）
  D3 题材（按内容关键词，多标签）
  D4 篇幅档（按字数）
  D5 开篇方式
  D6 段落长度节奏

口径：确证去重 178 篇（corpus_own/_final.json 中 verdict=确证 且 dup_of 为空）。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import project_root   # noqa: E402
import json
from collections import Counter, defaultdict

# 项目根：STYLE_PROJECT 优先，其次脚本的上一级（脚本被复制进 skill 后靠 STYLE_PROJECT / cwd）
ROOT = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FEAT = os.path.join(ROOT, "corpus_own", "_final.json")

MATERIALS = ["毛泽东", "史铁生", "黄文秀", "鲁迅", "路遥", "张桂梅", "袁隆平",
             "陶行知", "钱学森", "习近平"]

TOPICS = [
    ("科技·数据·AI", r"人工智能|AI|数据|科技|算法|数字|网络|信息|机器学习"),
    ("文化·传统·课本", r"文化|传统|古诗|经典|课本|戏曲|文言|先贤|国学"),
    ("青年·成长·人生", r"青年|青春|成长|人生|奋斗|少年|学生|选择"),
    ("家国·时代·使命", r"国家|民族|时代|现代化|复兴|强国|家国|使命|长征"),
    ("辩证·哲思", r"辩证|一概而论|矛盾|对立|统一|取舍|进退|尺度|边界"),
]


def paras(t):
    return [p.strip() for p in re.split(r"\n\s*\n|\n", t) if len(p.strip()) >= 25]


def metrics(rows):
    """一组文章的画像指标

    字数口径：**剥离空白**（与 check_flaws2.py / check_verbosity.py / check_draft.py 一致）。
    早期版本用未剥空白的 len(text)，同一批数据会比剥离口径低约 2%，
    导致同一份文档里出现「问号 5.72」与「问号 5.86」两个数。已统一。
    """
    text = "".join(r["text"] for r in rows)
    nc = len(re.sub(r"\s", "", text)) or 1
    ps = [p for r in rows for p in paras(r["text"])]
    np_ = len(ps) or 1
    tail_q = sum(1 for p in ps if p.rstrip().endswith(("不是吗？", "不是吗", "不是吗?")))
    last_q = sum(1 for r in rows if paras(r["text"]) and "？" in paras(r["text"])[-1])
    mat = Counter()
    for r in rows:
        for m in MATERIALS:
            if m in r["text"]:
                mat[m] += 1
    pat_sx = re.compile(r"试想[，,].{0,40}?(怎|哪|岂|何)")
    return {
        "n": len(rows),
        "chars": nc,
        "para_med": sorted(len(p) for p in ps)[np_ // 2] if ps else 0,
        "bushi_pk": round(text.count("不是吗") / nc * 1000, 2),
        "bushi_para_pct": round(sum(1 for p in ps if "不是吗" in p) / np_ * 100, 1),
        "tail_q_pct": round(tail_q / np_ * 100, 1),
        "last_q_pct": round(last_q / len(rows) * 100, 1) if rows else 0,
        "kejian_pk": round(text.count("可见") / nc * 1000, 2),
        "q_pk": round((text.count("？") + text.count("?")) / nc * 1000, 2),
        "ell_pk": round(text.count("……") / nc * 1000, 2),
        "shixiang_pct": round(sum(1 for r in rows if pat_sx.search(r["text"])) / len(rows) * 100, 1),
        # 规劝虚词：**只计无歧义的**。「当」必须剔除——它 284 次里几乎全是「当…时」时间从句
        # （"当技术把肉体解放出来之后"），不是文言虚词。早期把它算进去得 3.82/千字，
        # 三篇仿稿据此齐刷刷堆文言。含「当」的旧口径保留为 arch_amb_pk，仅供对照。
        "arch_pk": round(sum(text.count(w) for w in ["须", "方可", "方能", "务必", "势必"]) / nc * 1000, 2),
        "arch_amb_pk": round(sum(text.count(w) for w in ["须", "当", "方可", "方能"]) / nc * 1000, 2),
        "top_mat": ", ".join(f"{m}{c}" for m, c in mat.most_common(4)),
    }


HEADERS = ["组", "篇数", "字数", "段中位", "不是吗/千字", "含句段%", "**段末反问%**",
           "**篇末反问%**", "可见/千字", "问号/千字", "省略号/千字", "试想篇%", "规劝虚词/千字"]


def table(title, groups, showsize=None):
    print(f"\n### {title}\n")
    print("| " + " | ".join(HEADERS) + " |")
    print("|" + "---|" * len(HEADERS))
    for label, rows in groups:
        if not rows:
            continue
        m = metrics(rows)
        print(f"| {label} | {m['n']} | {m['chars']:,} | {m['para_med']} | {m['bushi_pk']} | "
              f"{m['bushi_para_pct']} | **{m['tail_q_pct']}** | **{m['last_q_pct']}** | "
              f"{m['kejian_pk']} | {m['q_pk']} | {m['ell_pk']} | {m['shixiang_pct']} | {m['arch_pk']} |")


def main():
    with open(FEAT, encoding="utf-8") as f:
        rows = [r for r in json.load(f) if r["verdict"] == "确证" and not r["dup_of"]]
    print(f"口径：确证去重 {len(rows)} 篇 / {sum(r['chars'] for r in rows):,} 字")

    table("D1 按文体", [(g, [r for r in rows if r["genre"] == g])
                        for g, _ in Counter(r["genre"] for r in rows).most_common()])
    table("D2 按栏目", [(g, [r for r in rows if r["category"] == g])
                        for g, _ in Counter(r["category"] for r in rows).most_common()])
    table("D3 按篇幅档",
          [(f"{lo}–{hi} 字", [r for r in rows if lo <= r["chars"] <= hi])
           for lo, hi in [(0, 799), (800, 1099), (1100, 1499), (1500, 9999)]])

    print("\n### D3b 按题材（多标签，一篇可归多类）\n")
    print("| 题材 | 篇数 | 占比 | 段末反问% | 篇末反问% | 可见/千字 | 问号/千字 |")
    print("|---|---|---|---|---|---|---|")
    for name, pat in TOPICS:
        sub = [r for r in rows if re.search(pat, r["text"])]
        if not sub:
            continue
        m = metrics(sub)
        print(f"| {name} | {m['n']} | {m['n'] / len(rows) * 100:.1f}% | {m['tail_q_pct']} | "
              f"{m['last_q_pct']} | {m['kejian_pk']} | {m['q_pk']} |")

    # D5 开篇方式
    print("\n### D5 开篇方式\n")
    d5 = Counter()
    examples = defaultdict(list)
    for r in rows:
        ps = paras(r["text"])
        if not ps:
            continue
        f = ps[0]
        head = f[:80]
        if "？" in f[:70] or re.match(r"^.{0,40}(吗|呢|呢？)", head):
            k = "设问开篇"
        elif re.match(r"^\s*[“「]", f) or re.search(r"^(古人|有人说|俗话说|常言|材料|习主席|毛主席)", f):
            k = "引语/材料开篇"
        elif re.search(r"(我以为|我认为|我的观点|我的回答|我是这样理解|对此，我)", f[:150]):
            k = "直陈判断开篇"
        elif re.search(r"(时代|当下|如今|而今|时下|最近|这些天)", f[:60]):
            k = "时代/现象开篇"
        else:
            k = "其他"
        d5[k] += 1
        if len(examples[k]) < 3:
            examples[k].append((r["n"], head.replace("\n", " ")[:56]))
    for k, v in d5.most_common():
        print(f"- **{k}**　{v} 篇　{v / len(rows) * 100:.1f}%")
        for n, ex in examples[k]:
            print(f"    - `#{n:04d}` {ex}…")

    # D6 段落节奏
    print("\n### D6 段落长度节奏\n")
    for gname in ["下水议论文", "叙事散文"]:
        sub = [r for r in rows if r["genre"] == gname]
        if not sub:
            continue
        lens = [len(p) for r in sub for p in paras(r["text"])]
        if not lens:
            continue
        lens.sort()
        n = len(lens)
        print(f"- **{gname}**：段数 {n}，中位 {lens[n // 2]} 字，"
              f"P25 {lens[n // 4]}，P75 {lens[3 * n // 4]}，"
              f"长段(>250字) {sum(1 for x in lens if x > 250) / n * 100:.1f}%，"
              f"短段(<80字) {sum(1 for x in lens if x < 80) / n * 100:.1f}%")
    # 省略号独立成段（要查原始行，不能查过滤后的段落表——「……」只有 2 字会被长度阈值滤掉）
    ell_para = 0
    for r in rows:
        if any(re.fullmatch(r"[….\s]+", ln.strip()) and len(ln.strip()) >= 2
               for ln in r["text"].splitlines()):
            ell_para += 1
    print(f"- 用「……」独立成段做过渡：{ell_para}/{len(rows)} 篇 = {ell_para / len(rows) * 100:.1f}%")


if __name__ == "__main__":
    main()
