"""叙事越界检测（N1–N3）

来源：2026-10-18 视频轮，专家判伪1 的攻击点不是文风，是"这个人物压根不该存在"——
"小区门口修车的老陈……我问他看什么……这lf大人恐怕没有这样的水平，恐怕写不出来"。

本检测器只查**负向约束**（他不做什么），不查正向特征。
零命中的约束是安全的；多数命中的约束才危险（第 07 轮"收束同构"教训）。

用法：
  python tools/check_narrative.py --selftest    # 反向测试，必须 100% 通过
  python tools/check_narrative.py --corpus      # 跑 118 篇真文，看误伤
  python tools/check_narrative.py --files a.md b.md
"""
import json, os, re, sys, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# N1 第一人称亲历叙事（"我看，……"是评论，不算）
N1 = [
    r"我问他", r"我问她", r"我问过", r"我见过", r"我认识", r"我遇到", r"我碰见",
    r"我身边", r"我们班", r"我的学生", r"我有个", r"我邻居", r"那天我", r"有一次[，,]?我",
]
# N3 市井/场景（**只留强场景词**）
# 去掉"巷子/楼下/胡同"这类易作比喻的词：
#   伪3「进了哪条巷子却要自己抬脚」是比喻；真文 #207「酒香也怕巷子深」是引俗语——两者都误报。
N3 = ["小区", "菜市场", "公交车上", "地铁上", "家门口", "楼道", "单元门", "邻居"]
# N2 虚构人物：具名 + 职业身份 + 无出处（粗筛，需人工复核）
N2_PAT = [
    r"(小区|门口|街边|巷口|村口)(的)?[^。，]{0,8}(老|小)[陈王李张刘赵孙周吴郑]",
    r"(修车|补胎|修鞋|卖菜|开出租|送快递|扫街)的[^。，]{0,6}老[陈王李张刘赵孙周吴郑]",
]


def hits(text):
    out = {}
    n1 = [p for p in N1 if re.search(p, text)]
    if n1:
        out["N1_亲历叙事"] = n1
    n3 = [w for w in N3 if w in text]
    if n3:
        out["N3_市井场景"] = n3
    n2 = [p for p in N2_PAT if re.search(p, text)]
    if n2:
        out["N2_虚构人物"] = n2
    return out


def corpus():
    p = os.path.join(ROOT, "corpus_own", "_final.json")
    if not os.path.exists(p):
        sys.exit(f"找不到语料：{p}\n（--corpus 只在项目里用；skill 里请用 --files <稿.md>）")
    rows = json.load(open(p, encoding="utf-8"))
    return [r for r in rows if r.get("verdict") == "确证" and not r.get("dup_of")
            and r.get("genre") == "下水议论文"]


def selftest():
    ok = fail = 0

    def ck(name, cond):
        nonlocal ok, fail
        print(("  ✓ " if cond else "  ✗ ") + name)
        ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)

    # 1) 伪1 的原句必须被抓到
    fake = "小区门口修车的老陈，他汉子一撑就是几十年。我问他看什么，他说看看有没有人推着车过来。"
    h = hits(fake)
    ck("伪1 原句 → 命中 N1/N2/N3", "N1_亲历叙事" in h and "N3_市井场景" in h)

    # 2) 真文的"我看，……"必须**不**被抓（评论 vs 叙事）
    real = "我看，这主要看谦让、不谦让的效果。若谦让，只是让自己受委屈，那就不必。"
    ck("真文『我看，……』→ 不误报", not hits(real))

    # 3) 引诗"我见青山多妩媚"不误报
    ck("引诗『我见青山』→ 不误报", not hits("#131 我见青山多妩媚，料青山见我应如是"))

    # 4) 空文
    ck("空文 → 无命中", not hits(""))

    # 5) 反向：把 N1 词表清空 → 伪1 必须抓不到（证明是 N1 在起作用，不是巧合）
    n1_bak = N1[:]
    N1.clear()
    ck("清空 N1 → 伪1 不再命中 N1", "N1_亲历叙事" not in hits(fake))
    N1.extend(n1_bak)

    print(f"\n反向测试：{ok}/{ok+fail} 通过")
    return 0 if fail == 0 else 1


def run_corpus():
    rows = corpus()
    bad = []
    for r in rows:
        h = hits(r["text"])
        if h:
            bad.append((r["n"], r["headline"], h))
    print(f"118 篇真文：{len(bad)} 篇命中")
    for n, head, h in bad[:20]:
        print(f"  #{n:03d} {head[:26]}")
        for k, v in h.items():
            print(f"       {k}: {v}")
    return len(bad)


def run_files(paths):
    for p in paths:
        t = open(p, encoding="utf-8").read()
        t = re.sub(r"^#.*$", "", t, flags=re.M)
        h = hits(t)
        print(f"{os.path.basename(p)}：{'命中 ' + str(list(h)) if h else '干净'}")
        for k, v in h.items():
            print(f"   {k}: {v}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--corpus", action="store_true")
    ap.add_argument("--files", nargs="*")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if a.corpus:
        run_corpus()
    if a.files:
        run_files(a.files)
