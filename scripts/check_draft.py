# -*- coding: utf-8 -*-
"""
仿写自检器：把生成稿与"目标子类"的真值逐项比对。

目标子类：下水议论文 × 辩证哲思类 × 900–1100 字
真值来源：tools/strata_stats.py 的分目别类统计（确证去重 178 篇）

用法：python check_draft.py <稿件路径>
"""
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import find_profile, caliber_line, project_root   # noqa: E402

# 项目根：STYLE_PROJECT 优先，其次脚本的上一级（脚本被复制进 skill 后靠 STYLE_PROJECT / cwd）
ROOT = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── profile：阈值与词表的真源 ───────────────────────────────────────────────
# 由 `tools/make_profile.py` 从语料现算产出，随语料增长刷新。
# **找不到时回落到内置值**（内置值即 2026-09-23 的 profile），并在输出里写明——
# 静默回落会让人以为用的是现算值。
PROFILE, PROFILE_PATH = find_profile()

# 目标子类真值：(指标, 目标区间, 真值说明)
# 说明：在 ~1000 字量级上，每千字率会因整数计数而量化（2 次「可见」=1.75/千字、
# 3 次=2.62/千字，中间没有取值），所以「可见」「问号」两项改用**出现次数**设带宽，
# 其余项仍用率或占比。
TARGETS_BUILTIN = [
    ("chars",          "总字数",              (900, 1150),  "浓度峰值区 800–1099"),
    ("bushi_para",     "含「不是吗？」段落占比", (45, 55),   "议论文 45.1%／辩证类更浓"),
    ("tail_q",         "段末反问占比",         (33, 50),    "议论文 40.7%／辩证类 43.3%"),
    ("last_q",         "篇末是否含反问",       (1, 1),      "议论文 78.0%／辩证类 83.9%"),
    ("kejian",         "「可见」出现次数",      (2, 3),      "真值 2.12/千字 → 千字文约 2–3 次"),
    ("q",              "问号出现次数",         (5, 7),      "真值 5.72/千字 → 千字文约 5–7 个"),
    ("tan_pk",         "感叹号每千字",          (1.8, 4.0),  "议论文均值 3.03／中位 2.28 ⚠ 曾漏查"),
    ("ell_pk",         "省略号每千字",          (0.8, 1.7),  "议论文 1.3 ⚠ 勿用全体值 2.12"),
    ("ell_para",       "「……」独立成段",        (1, 1),      "37.6% 的篇目有"),
    ("shixiang",       "「试想」出现次数",       (1, 1),      "10.2% 的篇目有"),
    ("arch",           "文言规劝虚词（须/方可/方能/务必/势必）", (0, 3), "议论文 0.99/千字·中位 0 处·P75 2 处"),
    ("short_para_pct", "短段(<80字)占比",        (15, 30),   "议论文 23.3%"),
    ("para_med",       "段落长度中位",          (100, 160),  "议论文 128 字"),
]

MATERIALS_BUILTIN = ["毛泽东", "史铁生", "黄文秀", "鲁迅", "路遥", "张桂梅", "袁隆平"]


def _wl(profile, key):
    """词表/名单：profile 优先，回落内置"""
    if profile:
        return profile.get("wordlists", {}).get(key)
    return None


def load_targets(profile):
    """目标区间：profile 优先，回落内置"""
    if profile:
        rows = profile.get("targets", {}).get("draft")
        if rows:
            return [(r["key"], r["label"], (r["lo"], r["hi"]), r.get("basis", "")) for r in rows]
    return TARGETS_BUILTIN


MATERIALS_OK = _wl(PROFILE, "materials_ok") or MATERIALS_BUILTIN
OFFLIST = _wl(PROFILE, "offlist_suspect") or ["苏轼", "长征", "刀郎", "张雪峰", "全红婵", "钟南山"]
TOPIC_GIVEN = _wl(PROFILE, "topic_given") or ["长征"]


def measure(path):
    """读稿件文件 → 去掉标题行与署名行 → 交给 measure_body()"""
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    lines = lines[1:]
    if lines and re.match(r"^.{0,20}(研究院|教研院|教研室|中学|学校)\s*[\u4e00-\u9fa5]{2,4}$",
                          lines[0].strip()):
        lines = lines[1:]
    body = "\n".join(lines).strip()
    return measure_body(body), body


def measure_body(body):
    """正文 → 指标。

    **稿件与语料走同一套定义**：`tools/make_profile.py` 直接 import 本函数来给语料逐篇算指标，
    因此自检器的目标区间与它实测稿件的口径天然一致。
    本项目吃过"两个脚本同一指标两个数"的亏，所以这里不再各写一份。
    """
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", body) if p.strip()]
    if not paras:
        # 空正文（只有标题行／内容全被剥掉）。早前这里直接往下走，
        # 在 `sum(...) / len(paras)` 处抛 ZeroDivisionError。
        # 契约：调用方必须判 None。
        return None
    long_paras = [p for p in paras if len(p) >= 25]
    plens = [len(p) for p in paras]

    nc = len(re.sub(r"\s", "", body)) or 1
    tail_q = sum(1 for p in paras if p.rstrip().endswith(("不是吗？", "不是吗", "不是吗?")))
    kouxu_counts = [p.count("不是吗") for p in paras]
    has_k = [c for c in kouxu_counts if c > 0]
    m = {
        "chars": nc,
        "bushi_para": sum(1 for p in paras if "不是吗" in p) / len(paras) * 100,
        "tail_q": tail_q / len(paras) * 100,
        "last_q": 1 if "？" in paras[-1] else 0,
        "kejian": body.count("可见"),
        "kejian_pk": body.count("可见") / nc * 1000,
        "q": body.count("？") + body.count("?"),
        "q_pk": (body.count("？") + body.count("?")) / nc * 1000,
        "tan_pk": (body.count("！") + body.count("!")) / nc * 1000,
        "ell_pk": body.count("……") / nc * 1000,
        "ell_para": sum(1 for p in paras if re.fullmatch(r"[….\s]+", p) and len(p) >= 2),
        "shixiang": len(re.findall(r"试想", body)),
        "arch": sum(body.count(w) for w in ["须", "方可", "方能", "务必", "势必"]),
        "dang": body.count("当"),
        "short_para_pct": sum(1 for p in paras if len(p) < 80) / len(paras) * 100,
        "para_med": sorted(len(p) for p in long_paras)[len(long_paras) // 2] if long_paras else 0,
        # ── 第 01 轮盲测回流（2026-09-24）────────────────────────────
        # 评委 4/4 指认"口癖像打卡一样每段末尾准时报到"。本人 118 篇里 92 篇
        # 存在单段≥2 的喷发（全库单段最大 10 个），三篇远程稿全是单段最大 1、
        # 恰好 5/11 段各挂 1 个——"装饰性等距"是他的反签名。
        "burst_max": max(kouxu_counts),
        # 盖章模式：含「不是吗」的段≥4 且每段恰好 1 个 → 判为装饰性等距（他不用这种）
        "kouxu_stamped": 1 if (has_k and len(has_k) >= 4 and max(has_k) == 1) else 0,
        # 段落长度变异系数：评委"段落长短几乎等宽，人不会这么写"
        "para_cv": (statistics.stdev(plens) / statistics.mean(plens)) if len(plens) >= 2 else 0,
        "_paras": len(paras),
        "_plist": paras,
    }
    return m


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "首篇-裸文版.md")
    if not os.path.exists(path):
        print(f"找不到稿件：{path}")
        sys.exit(2)
    m, body = measure(path)
    if m is None:
        print(f"稿件 {os.path.basename(path)} 没有可分析的段落（只有标题行／正文为空），无法计算指标。")
        sys.exit(2)
    targets = load_targets(PROFILE)

    print(f"稿件：{os.path.basename(path)}")
    print(f"段落 {m['_paras']} 段 / {m['chars']} 字")
    print(caliber_line(PROFILE, PROFILE_PATH))
    print()
    print(f"{'指标':<24}{'实测':>10}{'目标区间':>14}   判定")
    print("-" * 68)
    fails = []
    for key, label, (lo, hi), note in targets:
        v = m[key]
        ok = lo <= v <= hi
        vs = f"{v:.2f}" if isinstance(v, float) else str(v)
        print(f"{label:<24}{vs:>10}{f'{lo}–{hi}':>14}   {'通过' if ok else '✗ 未达'}")
        if not ok:
            fails.append((label, v, (lo, hi), note))

    print("\n素材使用：")
    used = [x for x in MATERIALS_OK if x in body]
    # 名单外素材（按确证集实证频率判定为"被收录件话题"、非其本人骨干的）
    # 例外：题面直接指定的意象不算违规——如竞猜之十的题面就是
    #      "长征、鲁迅与人工智能"三词，长征是题目给定的，必须写。
    outside = [x for x in OFFLIST if x in body and x not in TOPIC_GIVEN]
    print(f"  骨干名单内：{used or '（无）'}")
    print(f"  名单外（应为空）：{outside or '（无）'}")
    given = [x for x in TOPIC_GIVEN if x in body]
    if given:
        print(f"  题面指定（豁免）：{given}")

    print("\n复现的缺陷是否就位（路线 A 要求这些毛病必须在）：")
    flaws = [
        ("反事实断言替代因果证明（试想…怎/哪/岂/何…）",
         bool(re.search(r"试想[，,][^。！？]{0,60}(怎|哪|岂|何)", body))),
        ("「可见」空转（收在抽象判断而非由例证推出）",
         bool(re.search(r"可见，[^。！？]{0,50}"
                        r"(事|事实|问题|选择|担当|放弃|边界|本身|功夫|价值|贵在|在于|才是|就是)",
                        body))),
        ("结论恒定（结尾落到固定出口：主体性／担当／精神）",
         bool(re.search(r"(主体性|主体|向善|有温度|家国|担当|精神|人的事|自己的事|人自己)",
                        m["_plist"][-1]))),
        ("训导腔（须／切莫／万万／务必 的规劝句）",
         bool(re.search(r"(须|切莫|万万|务必)", body))),
    ]
    for name, ok in flaws:
        print(f"  {'✓' if ok else '✗'} {name}")
    print("  · 单例归纳的跳跃、素材贴标签——程序难判，须人工确认")
    print(f"\n  参考（不判定）：「当」共 {m['dang']} 次——"
          f"其中「当…时」从句与「当年/当下」无法自动区分，故不纳入指标")

    print("\n" + "=" * 68)
    if fails:
        print(f"未达标 {len(fails)} 项：")
        for label, v, (lo, hi), note in fails:
            print(f"  · {label}：实测 {v:.2f}，目标 {lo}–{hi}（真值依据：{note}）")
    else:
        print("全部指标通过。")


if __name__ == "__main__":
    main()
