# -*- coding: utf-8 -*-
"""
生成「专家档专测」材料包：2 篇伪稿 + 6 篇真文，打乱后编号，另出答案密钥与评分表。

与校准轮的四处不同（都来自校准轮的教训）：
  1. 不给风格画像——量化画像会让裁判把「很少见」读成「不可能」，成批误杀真文；
  2. 不给校准样本——专家本人就是「读过他文章的人」，避免 8 篇样本人为约束出假规律；
  3. 不告诉伪稿数量——避免裁判去「凑数量」；
  4. 规模放大到 8 篇——单篇伪稿藏不住，多篇混入才能压住「哪一篇有点隔」的直觉。

首篇不进本包：专家已看过同题初版，标题与素材不变，必被认出（同题污染）。

用法：python build_expert_test.py
"""
import json
import os
import sys
import random
import re
import statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import project_root   # noqa: E402

# 项目根：STYLE_PROJECT 优先，其次脚本的上一级（脚本被复制进 skill 后靠 STYLE_PROJECT）
ROOT = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FEAT = os.path.join(ROOT, "corpus_own", "_final.json")
OUT = os.path.join(ROOT, "评测", "专家档-专测")

# 伪稿：篇名前缀 -> 裸文版路径（首篇刻意排除，理由见模块 docstring）
FAKES = ["第二篇", "第三篇"]

N_CONTROLS = 6
N_REF = 10            # AI 预演用的参考真文篇数（比校准轮的 8 篇更大，压制"自造规律"）
CHARS_RANGE = (900, 1200)
# 首篇校准轮用过的对照篇，专家可能已见过
USED_BEFORE = {48, 77, 207}
EXCLUDE_KEYWORDS = ("前文后赏", "预习", "预告", "复刊", "休刊")


def paras(t):
    return [p.strip() for p in re.split(r"\n\s*\n|\n", t) if len(p.strip()) >= 25]


def tail_q_rate(t):
    ps = paras(t)
    if not ps:
        return 0.0
    return sum(1 for p in ps if p.rstrip().endswith(("不是吗？", "不是吗", "不是吗?"))) / len(ps) * 100


def read_bare(path):
    """裸文版：第一行是标题，其余是正文。"""
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    return lines[0].lstrip("# ").strip(), "\n\n".join(lines[1:]).strip()


def pick_controls(rows):
    pool = []
    for r in rows:
        if r["verdict"] != "确证" or r["dup_of"] or r["genre"] != "下水议论文":
            continue
        if r["n"] in USED_BEFORE:
            continue
        if not (CHARS_RANGE[0] <= r["chars"] <= CHARS_RANGE[1]):
            continue
        if any(k in (r["headline"] or "") for k in EXCLUDE_KEYWORDS):
            continue
        ps = paras(r["text"])
        if not ps or not ps[-1].rstrip().endswith(("？", "?")):
            continue                              # 篇末必须有反问（子类 78%）
        pool.append((r, tail_q_rate(r["text"])))

    # 挑选规则（写死在脚本里，避免事后挑肥拣瘦）：
    # 段末反问率最接近子类均值 40.7% 的优先；再按栏目分散，每个栏目最多 2 篇。
    pool.sort(key=lambda x: abs(x[1] - 40.7))
    picked, per_cat = [], {}
    for r, rate in pool:
        cat = r["category"]
        if per_cat.get(cat, 0) >= 2:
            continue
        picked.append(r)
        per_cat[cat] = per_cat.get(cat, 0) + 1
        if len(picked) >= N_CONTROLS:
            break
    if len(picked) < N_CONTROLS:                  # 栏目分散没凑够，就不限栏目补齐
        for r, rate in pool:
            if r not in picked:
                picked.append(r)
            if len(picked) >= N_CONTROLS:
                break
    return picked


def main():
    with open(FEAT, encoding="utf-8") as f:
        rows = json.load(f)
    os.makedirs(OUT, exist_ok=True)

    items = []
    for prefix in FAKES:
        title, body = read_bare(os.path.join(ROOT, "稿件", f"{prefix}-裸文版.md"))
        items.append({"is_fake": True, "prefix": prefix, "title": title, "body": body,
                      "chars": len(re.sub(r"\s", "", body))})

    controls = pick_controls(rows)
    for r in controls:
        items.append({"is_fake": False, "n": r["n"], "title": r["headline"] or f"（无题 #{r['n']}）",
                      "body": r["text"], "chars": r["chars"], "category": r["category"],
                      "tail_q": tail_q_rate(r["text"])})

    random.seed(20260923)                          # 固定种子，便于复现与审计
    random.shuffle(items)
    for i, it in enumerate(items, 1):
        it["label"] = i

    # —— 稿件 ——
    lines = ["# 稿件（共 8 篇）", "",
             "> 请逐篇给出一个 0–100 的整数分，含义是「你认为这一篇出自你熟悉的那位作者之手的可能性」。",
             "> 不要凑比例，不必假定一定有几篇不是他写的。允许给极端分，也允许给中间分。", ""]
    for it in items:
        lines += ["---", "", f"## 第 {it['label']} 篇", "", it["title"], "", it["body"], ""]
    with open(os.path.join(OUT, "稿件.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # —— 评分表 ——
    tb = ["# 评分表", "",
          "| 篇号 | 分数（0–100） | 判断（本人／不是本人／不确定） | 触发了什么（可选） |",
          "|---|---|---|---|"]
    for it in items:
        tb.append(f"| 第 {it['label']} 篇 |  |  |  |")
    tb += ["", "**最后请单独回答**：如果只能挑出一篇你认为最不像他写的，你挑哪一篇？为什么？", ""]
    with open(os.path.join(OUT, "评分表.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(tb))

    # —— 给专家的一页说明 ——
    brief = f"""# 说明

这是一次**作者鉴别**。

某位作者（某市级教研院的语文教研员）写下水作文、课本诗、教研随笔，
主持一个日更的教研公众号。下面 8 篇稿子里，**有一部分不是他本人写的**——有人仿写了他的文风。

请你**逐篇给一个 0–100 的整数分**，含义是「你认为这一篇出自他本人之手的可能性」。
然后填进 `评分表.md`。

几点说明：

- **不要凑比例**，不必假定「一定有几篇是假的」。按你的真实判断给分就好。
- 允许给极端分（比如 5 分或 95 分），也允许给中间分。
- 这 8 篇字数在 {min(it['chars'] for it in items)}–{max(it['chars'] for it in items)} 字之间，
  题材与文体相近，都是他的公众号常发的那类下水议论文。
- 这些稿子的署名和日期都已剥掉，因为要判的是**文章本身**。
- **不必去猜题目**，也不必判断文章好坏——只判断「像不像他写的」。

如果有哪一篇让你犹豫，可以在评分表里写一句为什么。谢谢。
"""
    with open(os.path.join(OUT, "说明.md"), "w", encoding="utf-8") as f:
        f.write(brief)

    # —— 答案密钥（**刻意放在材料包目录之外**，避免误发给裁判）——
    key = ["# 答案密钥（**不要给裁判看**）", "", f"随机种子 20260923　｜　{len(FAKES)} 伪 + {len(controls)} 真", "",
           "材料包目录 `专家档-专测/` 里只有「稿件.md」「说明.md」「评分表.md」三个文件，可整目录发给裁判。", "",
           "| 篇号 | 真伪 | 来源 | 标题 | 字数 |", "|---|---|---|---|---|"]
    for it in items:
        if it["is_fake"]:
            key.append(f"| 第 {it['label']} 篇 | **伪** | {it['prefix']} | {it['title']} | {it['chars']} |")
        else:
            key.append(f"| 第 {it['label']} 篇 | 真 | #{it['n']}（{it['category']}） | {it['title']} | {it['chars']} |")
    key_path = os.path.join(ROOT, "评测", "专家档-专测-答案密钥.md")
    with open(key_path, "w", encoding="utf-8") as f:
        f.write("\n".join(key) + "\n")

    print(f"材料包已生成 → {OUT}")
    for it in items:
        tag = "伪" if it["is_fake"] else "真"
        src = it["prefix"] if it["is_fake"] else f"#{it['n']}"
        print(f"  第 {it['label']} 篇  [{tag}] {src:<6} {it['chars']:>5} 字  {it['title'][:34]}")

    # —— AI 预演目录：另攒 N_REF 篇参考真文（与待判稿不重叠），模拟「读过他文章的人」 ——
    # 参考集刻意比校准轮的 8 篇更大：样本越少，评委越容易从样本里自造硬规律误杀真文。
    import shutil
    reh = os.path.join(ROOT, "评测", "专家档-专测-AI预演")
    os.makedirs(reh, exist_ok=True)
    shutil.copy2(os.path.join(OUT, "稿件.md"), os.path.join(reh, "待判稿.md"))

    used = {r["n"] for r in controls} | USED_BEFORE
    pool = [r for r in rows
            if r["verdict"] == "确证" and not r["dup_of"] and r["genre"] == "下水议论文"
            and r["n"] not in used and CHARS_RANGE[0] <= r["chars"] <= CHARS_RANGE[1]]
    pool.sort(key=lambda r: abs(tail_q_rate(r["text"]) - 40.7))
    ref = pool[:N_REF]
    ref_lines = ["# 你读过他的文章", "",
                 f"> 下面 {len(ref)} 篇确认出自他本人之手。先读完，建立对他的直觉。", ""]
    for r in ref:
        ref_lines += ["---", "", f"## {r['headline'] or '（无题）'}", "", r["text"], ""]
    with open(os.path.join(reh, "你读过他的文章.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(ref_lines))
    print(f"\nAI 预演材料已生成 → {reh}（参考真文 {len(ref)} 篇）")
    for r in ref:
        print(f"  参考 #{r['n']:<5}{r['chars']:>5} 字  {(r['headline'] or '')[:36]}")


if __name__ == "__main__":
    main()
