# -*- coding: utf-8 -*-
"""标题自检。

**为什么单独一个检查器**：标题是全文最显眼的部分，却一直到 2026-09-24 才被纳入判据——
此前三篇仿稿的标题全落进同一个「逗号双分句」类型（占真值 18.8%），
而他 41.0% 的冒号式一次都没用。**类型分布本身就是签名。**

判据从 `profile` 的 `targets.title` 读（现算，不写死）。

用法：
  python check_title.py 首篇-裸文版.md        # 从稿件取第一行的标题
  python check_title.py "物来顺应：亦有不可顺者"   # 直接给标题字符串
  python check_title.py 首篇-裸文版.md 第二篇-裸文版.md 第三篇-裸文版.md
      # 多篇时额外检查"结构类型是否分散"
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import caliber_line, find_profile  # noqa: E402

SEP_RE = re.compile(r"[、·•，,；]")

# 无 profile 时的回落快照——**必须打印出来，静默回落会让人以为用的是现算值**
FALLBACK = {
    "chars_band": [11, 17],
    "structure_mix": {"冒号式（话题词：判断）": 41.0, "单句无标记": 37.6,
                      "逗号双分句": 18.8, "三项以上并列": 5.1},
    "topic_echo_pct": 57.4,
    "hard_rules": ["顿号「、」0.0%", "问号 0.9%", "三项并列用中点「·／•」"],
    "truth": {"chars": {"median": 14, "p25": 11, "p75": 17, "min": 3, "max": 27},
              "colon_pct": 41.0, "plain_pct": 37.6, "comma_only_pct": 18.8,
              "three_item_pct": 5.1, "mid_dot_pct": 4.3, "quote_pct": 19.7,
              "first_person_pct": 11.1, "question_pct": 0.9, "dunhao_pct": 0.0,
              "topic_echo_pct": 57.4, "topic_echo_n": 54},
}


def load_targets():
    prof, path = find_profile()
    t = ((prof or {}).get("targets") or {}).get("title")
    if t:
        return t, caliber_line(prof, path)
    return FALLBACK, "profile：未找到标题段 → 用内置快照 ⚠ 不是现算值"


def get_title(arg):
    """文件 → 取第一处非空行；否则当作标题串"""
    if os.path.isfile(arg):
        lines = [l for l in open(arg, encoding="utf-8").read().splitlines() if l.strip()]
        for l in lines:
            return re.sub(r"\s", "", re.sub(r"^#+\s*", "", l))
        return ""
    return re.sub(r"\s", "", arg)


def classify(t):
    # 中点优先：真值里有「平视（拍）•仰视（拍）•俯视（拍）：我更愿意平视与平拍」这类
    # 「三项 + 冒号」的复合式，区分度最高的是中点，所以先判它。
    if ("·" in t or "•" in t) and len(SEP_RE.split(t)) >= 3:
        return "三项以上并列"
    if "：" in t or ":" in t:
        return "冒号式（话题词：判断）"
    if SEP_RE.search(t) and len(SEP_RE.split(t)) >= 3:
        return "三项以上并列"
    if "，" in t or "；" in t:
        return "逗号双分句"
    if t.endswith("。") or not any(c in t for c in "：:，,；、·•"):
        return "单句无标记"
    return "其他"


def check_one(title, tg):
    """返回 (问题列表, 类型)"""
    truth = tg["truth"]
    band = tg["chars_band"]
    n = len(title)
    typ = classify(title)
    probs = []

    lo, hi = band
    if n < lo:
        probs.append(f"❌ 偏短：{n} 字（带内 {lo}–{hi}，真值中位 {truth['chars']['median']:.0f}）")
    elif n > hi:
        probs.append(f"⚠ 偏长：{n} 字（带内 {lo}–{hi}）")

    if "、" in title:
        probs.append(f"❌ 出现顿号「、」——真值 {truth['dunhao_pct']}%（117 条里一次没用），"
                     "这是他标题的硬签名")
    if "？" in title or "?" in title:
        probs.append(f"⚠ 标题用了问号——真值仅 {truth['question_pct']}%。"
                     "注意他与正文的反差：篇末 78% 用反问，标题几乎不用")
    if typ == "三项以上并列" and ("·" not in title and "•" not in title):
        probs.append(f"⚠ 三项并列却没用中点——真值 {truth['mid_dot_pct']}% 用「·／•」分隔，"
                     "他不用顿号也不用逗号切三项")
    if typ == "冒号式（话题词：判断）" and title.index("：" if "：" in title else ":") > n * 0.65:
        probs.append("⚠ 冒号位置偏后——他的冒号式是「**话题词**：判断」，前件短而后件是判断")
    return probs, typ


def main():
    args = sys.argv[1:]
    if not args:
        print("用法：check_title.py <稿件.md 或 标题串> [更多篇...]")
        return 2

    tg, cal = load_targets()
    print(cal)
    print()

    items = []
    for a in args:
        t = get_title(a)
        if not t:
            print(f"❌ 取不到标题：{a}")
            return 2
        items.append((os.path.basename(a) if os.path.isfile(a) else "（标题串）", t))

    bad = 0
    for label, t in items:
        probs, typ = check_one(t, tg)
        mark = "✓" if not probs else ("❌" if any(p.startswith("❌") for p in probs) else "⚠")
        print(f"{mark} {t}")
        print(f"    [{len(t)} 字] 类型：{typ}")
        for p in probs:
            print(f"    {p}")
            bad += 1
        print()

    # 多篇：类型分散性
    if len(items) >= 2:
        kinds = [classify(t) for _, t in items]
        from collections import Counter
        c = Counter(kinds)
        print("结构类型分散性：")
        for k, v in c.items():
            print(f"   {k}  ×{v}")
        dup = [k for k, v in c.items() if v >= 2]
        if dup:
            print(f"   ❌ 有 {len(dup)} 个类型被重复使用：{dup}")
            print("      真值分布里最大的类型也只有 41%，三篇全同型会被当成一个可识别的规律。")
            bad += 1
        else:
            print("   ✓ 各篇类型互不相同")
        print()

    if bad:
        print(f"共 {bad} 项未达——标题是全文最显眼处，改到全绿再交付。")
        return 1
    print("✓ 标题全项通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
