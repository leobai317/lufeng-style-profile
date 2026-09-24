# -*- coding: utf-8 -*-
"""政治类素材 · 核验清单器。

**这不是"禁写检查"，是"核验清单"。**

政策（2026-09-24 调整）：政治·党史·政策·楷模类素材**放开使用**——它们覆盖
示例语料 28.8% 的篇目，是高考下水作文的常态，一律回避等于白丢近三成相似度。
真正的风险不在"用了"，在**编造或记错**：第一次核验就抓到一处失实
（某书的字数，两个权威来源互相矛盾，而稿子里写了第三个数字）。

所以本脚本做三件事：
  1. 列出稿中全部政治类素材（分层）
  2. 标出**必须核验**的信号——引语与具体数字
  3. 与 `profile.politics.verified` 比对：命中即标"已核"，否则列为**待核验**

用法：
  python check_politics.py 首篇-裸文版.md [更多篇...]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import caliber_line, find_profile  # noqa: E402

TIER_ORDER = ["领袖", "党史", "政策", "楷模", "任一"]
MUST_VERIFY = {"领袖", "政策"}          # 这两层里的引用最需要核

# 数字：阿拉伯式 + 中文数词串
NUM_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?%?|[一二三四五六七八九十百千万零两]{2,}")
QUOTE_RE = re.compile(r"[“「]([^”」]{2,40})[”」]")


def load_politics():
    prof, path = find_profile()
    p = (prof or {}).get("politics")
    if p:
        return p, caliber_line(prof, path)
    return None, "profile：未找到 politics 段 → 无法判断哪些已核过 ⚠"


def scan(text, pol):
    """返回 (素材命中, 该核的引语, 该核的数字)

    ⚠ 引语与数字**只在"含政治素材的段落"里取**。
    第一版扫全文，结果把题面古语（「物来顺应…」）、他自己的行文引号（「一个废人」）
    和不是数据的数词（「万万」「十六个字」）全列成了"待核验"——
    过度报警会把清单变成噪音，真该核的那几条反而被淹掉。
    """
    words = pol.get("wordlists") or {}
    paras = [p for p in re.split(r"\n\s*\n|\n", text) if p.strip()]

    mats, quotes, nums = [], [], []
    for para in paras:
        hits = [(tier, w, para.count(w))
                for tier, ws in words.items() for w in ws if w in para]
        if not hits:
            continue
        mats += hits
        # 该段里有政治素材 → 段内的引语与数字才需要核
        for m in QUOTE_RE.finditer(para):
            if len(m.group(1)) >= 4:
                quotes.append(m.group(1))
        for m in NUM_RE.finditer(para):
            nums.append(m.group(0))

    mats.sort(key=lambda x: (TIER_ORDER.index(x[0]) if x[0] in TIER_ORDER else 9, -x[2]))
    # 去重保序
    quotes = list(dict.fromkeys(quotes))
    nums = list(dict.fromkeys(nums))
    return mats, quotes, nums


def norm(s):
    """比对前归一：去标点、去空白、把「两」写成「二」。

    不加这一步会误报：稿里写「两万五千」，已核清单里写「二万五千」（同指长征里程）；
    稿里引语带句号，清单里不带。第一版就是这样把已核的项又报成"待核验"。
    """
    s = re.sub(r"[。．.，,、；;：:！!？?“”「」『』（）()【】\s]", "", s or "")
    return s.replace("两", "二")


def is_verified(value, verified, non_claims):
    """已核 → 返回条目；行文引号 → 返回 'skip'；否则 None"""
    nv = norm(value)
    if nv and nv in [norm(x) for x in (non_claims or [])]:
        return "skip"
    for v in verified or []:
        if nv and nv in norm(v.get("claim")):
            return v
    return None


def run(path, pol):
    text = open(path, encoding="utf-8").read()
    body = "\n".join([l for l in text.splitlines() if l.strip()][1:])
    mats, quotes, nums = scan(body, pol)
    verified = pol.get("verified") or []
    non_claims = pol.get("non_claims") or []

    print(f"════ {os.path.basename(path)} ════")
    if not mats:
        print("  政治类素材：无")
    else:
        print("  政治类素材（分层）：")
        for tier, w, c in mats:
            flag = "  ← 引语/数据需核" if tier in MUST_VERIFY else ""
            print(f"    [{tier}] {w} ×{c}{flag}")

    todo = []
    if quotes:
        print("  引语（政治素材所在段落内）：")
        for q in quotes:
            v = is_verified(q, verified, non_claims)
            tag = "已核 ✓" if isinstance(v, dict) else ("行文引号，无需核" if v == "skip" else "待核验 ⚠")
            print(f"    “{q}”  {tag}")
            if v is None:
                todo.append(("引语", q))
    if nums:
        print("  具体数字（政治素材所在段落内）：")
        for n in nums:
            v = is_verified(n, verified, non_claims)
            tag = "已核 ✓" if isinstance(v, dict) else ("行文引号，无需核" if v == "skip" else "待核验 ⚠")
            print(f"    {n:<12}{tag}")
            if v is None:
                todo.append(("数字", n))
    print()
    return todo, len(mats)


def main():
    args = sys.argv[1:]
    if not args:
        print("用法：check_politics.py <稿件.md> [更多篇...]")
        return 2
    pol, cal = load_politics()
    if not pol:
        print(cal)
        return 2
    print(cal)
    print(f"政策：{pol.get('policy')}")
    print()
    print(f"{pol.get('why')}")
    print()

    all_todo = []
    total_mats = 0
    for a in args:
        if not os.path.exists(a):
            print(f"找不到：{a}")
            return 2
        todo, nm = run(a, pol)
        all_todo += [(os.path.basename(a),) + t for t in todo]
        total_mats += nm
        print()

    print("─" * 66)
    print("还有未核过的项（政治类素材里的引语与数据，一律不得凭记忆写）:" if all_todo
          else "全部政治类引语与数字都已在核实清单内 ✓")
    for f, kind, val in all_todo:
        print(f"   [{f}] {kind}：{val}")
    if all_todo:
        print()
        print("  核完把结论写进 profile 的 politics.verified（带来源与日期），下次即自动标『已核』。")
        return 1
    print(f"\n（本次共扫到 {total_mats} 处政治类素材）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
