# -*- coding: utf-8 -*-
"""
生成/刷新**作者画像文件（profile）**：把"仿写这个作者要靠哪些判据"变成一个可读、可审计、
可随语料增长刷新的 JSON。

为什么需要它：
  1. 自检器的阈值原本硬编码在 `check_draft.py` 的 TARGETS 里，只有作者本人能用，
     而且**改了语料不会自动跟着变**——这与"阈值必须现算"的约定相冲突。
  2. 换会话/换目录时，只要带上 profile + 脚本，就能复现同一套判据（skill 自包含）。
  3. 阈值来自哪个口径、什么时候算的，必须能被查——否则"可审计"是空话。

设计要点：
  · **真值（truth）由脚本现算**，不许手填；
  · **目标区间（targets）可以人工收放**——因为带宽是产品判断，不是统计量。
    凡人工设定的区间一律标 `source: "manual"` 并写明理由；未人工设定的按 RULES 自动派生并标 `"rule"`。
    刷新 profile 时**保留 manual**，只更新 truth。这样既不会把验证过的带宽冲掉，也能追责。
  · profile 里带 **语料口径标识**（筛选条件 / 篇数 / 字数 / 生成日期 / 生成脚本），
    因为同一个名字下的数字在不同口径下不可比。

用法：
  python make_profile.py                      # 写入 <项目>/profile/lf.json
  python make_profile.py --out-dir <目录>      # 写到别处（如 skill 的 profile/ 目录）
  python make_profile.py --md                 # 顺便打印人读画像表
"""
import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter

ROOT = None  # 见下方 project_root()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profile_io import project_root   # noqa: E402
from check_draft import measure_body                      # noqa: E402
from check_flaws2 import metrics as flaws2_metrics        # noqa: E402
from check_verbosity import metrics as verbosity_metrics  # noqa: E402
from check_flaws import metrics as flaws_metrics, COLLOQ  # noqa: E402

# 项目根：STYLE_PROJECT 优先，其次脚本的上一级（脚本被复制进 skill 后靠 STYLE_PROJECT / cwd）。
# **必须在 import 之前定好**——被 import 的那几个模块会读各自的 ROOT/FEAT 路径。
ROOT = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FEAT = os.path.join(ROOT, "corpus_own", "_final.json")
GEN = "tools/make_profile.py"
GENERATED_AT = "2026-09-28"

GENRE = "下水议论文"          # 目标文体（子类的第一维）
NAME_RE = "lf"

# ── 人工设定的目标区间（已验证，勿轻易改；改了要说清为什么）────────────────
# source=manual 的项在刷新 profile 时**保持不动**，只更新它旁边的 truth。
MANUAL_BANDS = {
    # key: (lo, hi, 理由)
    "chars":          (900, 1150, "浓度峰值档为 800–1099；下限上浮 100 避开'偏短端'，上限取 1099×1.05≈1150"),
    "bushi_para":     (45, 55,    "子类 45.1%，目标对准子类均值 ±5 个点（产品选择：宁可浓不可淡）"),
    "tail_q":         (33, 50,    "子类 40.7%；下限≈0.8×、上限≈1.23×"),
    "last_q":         (1, 1,      "硬签名：多数篇目以反问收尾（覆盖率见下表「覆盖面」，随语料现算）"),
    "kejian":         (2, 3,      "子类 2.17/千字；千字量级上改用次数带，避免整数量化"),
    "q":              (5, 7,      "子类 5.83/千字；同上，改次数带"),
    "tan_pk":         (1.8, 4.0,  "子类中位 2.39——**最显眼的口头习惯，曾整篇漏查**"),
    "ell_pk":         (0.8, 1.7,  "议论文 1.32；勿用全体值 2.12（那是被散文拉高的）"),
    "ell_para":       (1, 1,      "概率性手法，1 处即可（覆盖率见「覆盖面」）"),
    "shixiang":       (1, 1,      "概率性手法，1 次即可（覆盖率见「覆盖面」）"),
    "arch":           (0, 3,      "逐篇中位 0、P75 2；**勿用旧线 3–4 处**（那个数把「当…时」算成了文言虚词）"),
    "short_para_pct": (15, 30,    "子类 23.3%；节奏需要两成左右的短段"),
    "para_med":       (100, 160,  "子类 128 字；段落不许写长"),
}

# ── 自动派生规则（无人工设定时使用）────────────────────────────────────────
RULES_NOTE = {
    "rate": "每千字率类：[0.5×中位, 2.0×中位]（与 check_flaws2 的 band 判据同源）",
    "pct":  "占比类：±15% 相对",
    "count": "次数类：[floor(中位×0.7), max(ceil(中位×1.4), 中位+1)]",
    "binary": "0/1 类：子类覆盖率 ≥60% → (1,1)，否则 (0,1)",
}

DEFAULT_RATES = ["semicolon", "pause", "dash", "quote", "paren",
                 "tan_pk", "ell_pk", "kejian_pk", "q_pk"]

# ── 题材维度（多标签）────────────────────────────────────────────────────
# 用途：外部题目进来后，先判它落在哪个题材，再取**该题材的阈值**。
# 为什么不能只用 targets.draft（全子类汇总值）：题材间方差很大——
#   辩证·哲思类   段末反问 43.3% / 篇末反问 83.9%
#   青年·成长类   段末反问 27.2% / 篇末反问 60.7%
# 拿全子类均值去写青年类题目，会写得比他浓近一倍。这与"混合平均会骗人"同一个病根。
TOPICS = [
    ("科技·数据·AI", r"人工智能|AI|数据|科技|算法|数字|网络|信息|机器学习"),
    ("文化·传统·课本", r"文化|传统|古诗|经典|课本|戏曲|文言|先贤|国学"),
    ("青年·成长·人生", r"青年|青春|成长|人生|奋斗|少年|学生|选择"),
    ("家国·时代·使命", r"国家|民族|时代|现代化|复兴|强国|家国|使命|长征"),
    ("辩证·哲思", r"辩证|一概而论|矛盾|对立|统一|取舍|进退|尺度|边界"),
]

# 题材 → 什么素材：分析器据共现频次给建议（不写死"某题必用某人"）
TOPIC_MATS = ["毛泽东", "史铁生", "黄文秀", "鲁迅", "路遥", "张桂梅", "袁隆平",
              "陶行知", "钱学森", "屠呦呦", "樊锦诗", "钟南山",
              "习主席", "红军", "长征"]


def rows():
    with open(FEAT, encoding="utf-8") as f:
        allrows = json.load(f)
    return [r for r in allrows
            if r["verdict"] == "确证" and not r["dup_of"] and r["genre"] == GENRE]


def dist(vals):
    """分布摘要。**精度取 6 位**——4 位会让 0.06645 变成 0.0665，
    打印成 3 位时进位到 0.067，与"现场直算"的 0.066 差一个末位，
    又成了"同一指标两个数"。"""
    v = sorted(vals)
    n = len(v)
    return {
        "n": n,
        "median": round(statistics.median(v), 6),
        "mean": round(statistics.mean(v), 6),
        "p25": round(v[n // 4], 6),
        "p75": round(v[3 * n // 4], 6),
        "min": round(v[0], 6),
        "max": round(v[-1], 6),
    }


# 标点／空白：用来把「标点序列」排除出重复片段（见 repeated_frag 的反向测试教训）。
_PUNCT = re.compile(r"[，。！？、；：「」『』“”‘’\"'（）()《》〈〉—…·\s]")


def repeated_frag(p):
    """段内重复 ≥3 次的 2–5 字片段（第 06 轮 #4「毛边」的可靠判据）。

    为什么用这个判据：第 05 轮评委说远程稿"排比太工整、判断句自我复制"，
    而真文是**笨凿的重复**（"再愚拙的走一次亲戚……再愚拙的发一下"同形容词硬凿三次）。
    "硬凿"在文本上就是同一个词/句式在一段里反复——这是**能从语料里真提取出来**的。
    排除「不是吗」「可见」，避免与 kouxu_burst / kejian_link 两类重叠。

    放在模块级而不是嵌在 build_samples 里：嵌套函数拿不到，没法单独做反向测试
    （第一版就是嵌着的，测试直接 KeyError——这本身就是个提醒）。
    """
    for L in (2, 3, 4, 5):
        cnt = {}
        for i in range(len(p) - L + 1):
            f = p[i:i + L]
            # 双向排除：口癖与「可见」已各有专类（kouxu_burst / kejian_link），
            # 这里再收一遍就是重复计。注意要**双向**——f="不是" 不含"不是吗"，
            # 但它是"不是吗"的一部分，单向判会漏（口癖密集段会被误收进毛边类）。
            if ("不是吗" in f or f in "不是吗"
                    or "可见" in f or f in "可见"):
                continue
            # 含标点的片段一律不要：否则「吗？」×4、「见，」×3 这种**标点序列**
            # 会被当成硬凿重复（反向测试抓到的假阳性）。要找的是**词**的反复。
            if _PUNCT.search(f):
                continue
            cnt[f] = cnt.get(f, 0) + 1
        for f, c in sorted(cnt.items(), key=lambda kv: -kv[1]):
            if c >= 3:
                return f, c
    return None


def build_samples(rs):
    """风格样本层（第 01 轮盲测主修，2026-09-24）。

    为什么需要：第 01 轮远程盲测 0/12——画像只有数值时，生成必然是"平均的他"
    （四评委 4/4 识破）。且量化复核证明：喷发数/盖章模式/段长 CV/间距 CV 四个
    标量指标**全部不构成判别**——"太工整"活在句子级序列质感里，标量永远抓不住。
    所以把"他怎么写字"的样子本身放进画像：每类样本带 learn（学什么），生成前必读。

    提取口径：段落按单换行切（_final.json 无空行）；每类每篇至多取 1 条，保多样性。
    """
    paras_of = lambda t: [p.strip() for p in re.split(r"\n+", t) if p.strip()]
    out = {}

    def cap(items, limit, tmax):
        seen, kept = set(), []
        for it in items:
            if it["n"] in seen:
                continue
            body = it.get("text") or (it.get("short", "") + it.get("long", ""))
            if len(body) > tmax:
                continue
            seen.add(it["n"])
            kept.append(it)
            if len(kept) >= limit:
                break
        return kept

    burst, kejian, shix, opening, ending, stance, ragged, roughen = (
        [], [], [], [], [], [], [], [])
    for r in rs:
        t, n = r["text"], r["n"]
        ps = paras_of(t)
        for p in ps:
            if p.count("不是吗") >= 2:
                burst.append({"n": n, "text": p}); break
        m = re.search(r"([^。\n]{15,80}。[^。\n]{0,60}可见，[^。]{8,60}。)", t)
        if m: kejian.append({"n": n, "text": m.group(1)})
        for m in re.finditer(r"([^。\n]{10,70}。[^。\n]{0,50}(?:试想|如此这般)[^。]{10,70}。)", t):
            shix.append({"n": n, "text": m.group(1)}); break
        if ps:
            p0 = re.sub(r"\s", "", ps[0])
            if 30 <= len(p0) <= 120: opening.append({"n": n, "text": ps[0]})
            if len(ps) >= 2 and "？" in ps[-1] and len(re.sub(r"\s", "", ps[-1])) <= 220:
                ending.append({"n": n, "text": ps[-1]})
        if len(ps) >= 4:
            ls = [len(re.sub(r"\s", "", p)) for p in ps]
            if min(ls) >= 8 and max(ls) / max(1, min(ls)) >= 5:
                i_s, i_l = ls.index(min(ls)), ls.index(max(ls))
                if i_s != i_l and len(ps[i_l]) <= 320:
                    ragged.append({"n": n, "short": ps[i_s], "long": ps[i_l]})
        m = re.search(r"[^。！？\n]{0,15}(我是[^。！？\n]{1,18}|我相信[^。！？\n]{1,30}"
                      r"|我对此[^。！？\n]{1,18}|我看[^。！？\n]{1,25})[！？。]", t)
        if m: stance.append({"n": n, "text": m.group(0).strip()})
        for p in ps:
            flat = re.sub(r"\s", "", p)
            rp = repeated_frag(flat)
            if rp and 40 <= len(flat) <= 320:
                roughen.append({"n": n, "text": p, "frag": rp[0], "times": rp[1]})
                break

    out["usage"] = ("生文前必读——这是「他怎么写字」的样子。学手法、学气息、学毛边，"
                    "禁止整句照抄进稿（样本会随语料刷新）。"
                    "无语料 few-shot 时，本层就是唯一的「手感」来源。")
    out["kouxu_burst"] = {
        "learn": ("「不是吗」是情绪喷发：同一段里连用两三次（全库单段最多 4 个），"
                  "且位置跟着情绪走——绝不是每段末尾打卡。含「不是吗」的段通常只占三到五成，"
                  "其余段一个都没有，疏密是乱的。"
                  "**语法位置（第 03 轮全量核验，425 处）**：① 后接标点**必须是「？」**——"
                  "「不是吗。」句号版全库 **0 处**，写一次露一次；"
                  "② 84% 作段末结论，16% 嵌在段中（**是真的有，不是错**——"
                  "评委说「句中嵌是破绽」，核验不成立，别见一个改一个）；"
                  "③ 前一句是问句的仅 7 处（1.6%），属稀疏用法，仿写慎用。"),
        "items": cap(burst, 8, 400)}
    out["kejian_link"] = {
        "learn": ("「可见」必须紧跟具体例证、由例推出结论；收在抽象判断上是空转（自检器会抓）。"
                  "**不得借「可见」引入新例证**——那是「用结论词带新料」，"
                  "全库 262 个「可见」句里只有 1 句这么用（0.4%）。"),
        "items": cap(kejian, 8, 220)}
    out["shixiang"] = {
        "learn": "「试想／如此这般」的推进式说理：假设下去，把后果说出来。",
        "items": cap(shix, 6, 220)}
    out["opening"] = {
        "learn": "开头直入话题，不摆骨架、不解释结构（评委抓过「首段解释得过于明白」）。",
        "items": cap(opening, 8, 160)}
    out["ending"] = {
        "learn": ("结尾常以反问收、直接呼告读者（你呢？不是吗？），但不是每篇都反问。"
                  "**收束是程式，不是抒情（第 03 轮全量核验，118 篇）**："
                  "63.6% 以「不是吗？」收尾，46.6% 的末段带总结词（总之／可见／说到底）；"
                  "抒情问句收尾只有 4 篇（3.4%）。"
                  "仿写**禁用文艺腔**收尾（「今夜，你打算把灯留到几点呢？」这类）——"
                  "写法是：总结判断 + 段末反问。"),
        "items": cap(ending, 8, 240)}
    out["stance"] = {
        "learn": ("第一人称立场句：约三分之一篇章出现，可短到「我是赞成的。」——"
                  "出现时就是亮态度，不出现也不算错（勿当硬指标）。"),
        "items": cap(stance, 6, 80)}
    out["ragged"] = {
        "learn": ("段落长短故意不平整：短段一句一行，长段两三百字——「文似看山不喜平」。"
                  "每条含同一篇里的最短段与最长段对照。"),
        "items": cap(ragged, 6, 340)}
    out["roughen"] = {
        "learn": ("**毛边是特征，不是清单（第 06 轮 #4 → 第 07 轮 #3 修正）**。"
                  "第 05 轮评委说远程稿「排比太工整、判断句自我复制、素材精确贴题零损耗」，"
                  "而真文是**笨凿的重复、堆砌而不裁剪**。"
                  "**但第 06 轮把这一类当成了「照单补毛边」，反被评委识破**——"
                  "「这些毛边像是按清单补进去的」。清单化的特征一旦被刻意复制，本身就是新破绽："
                  "**按清单补破绽也是破绽**（与「写得太好是破绽」是同一枚硬币的两面）。"
                  "⚠ **所以下面这些例子只是「他长什么样」的证据，不是待办清单，不许逐条复制。** "
                  "本类**能从语料提取**的只有一种：同一个词或同一句式在一段里硬凿三次以上。"
                  "另五类**不可程序化提取**：错字／脱字、引语记串（把「独立之精神，自由之思想」"
                  "写成「独立之人格」）、成语误用（「不为人齿」）、「啊」当句号、"
                  "素材一口气压五六个名字不解释。"
                  "它们的**真实来源是赶稿过程**——不回头的崩句、念顺了反复说、随手写错，"
                  "**不可提取，只能靠通篇气息**，不是往稿子里插几条。"
                  "凡自己觉得「这句写得漂亮」「这个排比很齐」「这条毛边我补上了」，就再检查一遍。"),
        "items": cap(roughen, 6, 340)}
    return out


def build():
    rs = rows()
    texts = [r["text"] for r in rs]
    total_chars = sum(len(re.sub(r"\s", "", t)) for t in texts)

    # 逐篇三套指标
    mb = [m for m in (measure_body(t) for t in texts) if m]   # 空正文的篇目返回 None，跳过
    f2 = [m for m in (flaws2_metrics(t) for t in texts) if m]
    vb = [verbosity_metrics(t) for t in texts]
    fl = [flaws_metrics(t, "") for t in texts]

    def d(ms, key):
        return dist([m[key] for m in ms])

    # ── 覆盖面（用于 0/1 类与"是否常用"的判断）──
    coverage = {
        "last_q": sum(1 for m in mb if m["last_q"] == 1) / len(mb),
        "ell_para": sum(1 for m in mb if m["ell_para"] >= 1) / len(mb),
        "shixiang": sum(1 for m in mb if m["shixiang"] >= 1) / len(mb),
        "arch": sum(1 for m in mb if m["arch"] >= 1) / len(mb),
        "kejian": sum(1 for m in mb if m["kejian"] >= 1) / len(mb),
        "bushi": sum(1 for m in mb if m["bushi_para"] > 0) / len(mb),
    }

    # ── targets（稿件级 13 项）：manual 优先，其余按规则派生 ──
    targets = []
    for key, label, ms in [
        ("chars", "总字数", mb), ("bushi_para", "含「不是吗？」段落占比", mb),
        ("tail_q", "段末反问占比", mb), ("last_q", "篇末是否含反问", mb),
        ("kejian", "「可见」出现次数", mb), ("q", "问号出现次数", mb),
        ("tan_pk", "感叹号每千字", mb), ("ell_pk", "省略号每千字", mb),
        ("ell_para", "「……」独立成段", mb), ("shixiang", "「试想」出现次数", mb),
        ("arch", "规劝虚词（须/方可/方能/务必/势必）", mb),
        ("short_para_pct", "短段(<80字)占比", mb), ("para_med", "段落长度中位", mb),
    ]:
        t = d(ms, key)
        if key in MANUAL_BANDS:
            lo, hi, why = MANUAL_BANDS[key]
            src = "manual"
        else:
            med = t["median"]
            if key in ("last_q", "ell_para", "shixiang"):
                cov = coverage.get(key, 0)
                lo, hi = (1, 1) if cov >= 0.6 else (0, 1)
                src = "rule"
                why = f"{RULES_NOTE['binary']}；实测覆盖率 {cov:.1%}"
            else:
                lo, hi = round(med * 0.85, 1), round(med * 1.15, 1)
                src, why = "rule", RULES_NOTE["pct"]
        targets.append({
            "key": key, "label": label, "lo": lo, "hi": hi,
            "source": src, "basis": why,
            "truth": {"median": t["median"], "mean": t["mean"],
                      "p25": t["p25"], "p75": t["p75"], "max": t["max"]},
        })

    # ── baselines（供 check_flaws2 / check_verbosity / check_flaws 的 band 判据用）──
    baselines = {
        "flaws2": {k: d(f2, k)["median"] for k in
                   ["cv", "ratio", "labels", "semicolon", "pause", "dash", "quote", "paren"]},
        "verbosity": {k: d(vb, k)["median"] for k in
                      ["red3", "red5", "red9", "sent_med", "sent_mean", "long_sent_pct",
                       "policy_hits", "policy_pk"]},
        "flaws": {k: d(fl, k)["median"] for k in
                  ["tan_pk", "q_pk", "rep_ratio", "aa_pk", "collq_pk"]},
    }
    baselines["flaws2"]["ev_rate"] = round(
        statistics.median([m["ev_rate"] for m in f2 if m["ev_rate"] is not None]), 2)

    # ── 词表 ──
    wordlists = {
        "materials_ok": ["毛泽东", "史铁生", "黄文秀", "鲁迅", "路遥", "张桂梅", "袁隆平"],
        "offlist_suspect": ["苏轼", "长征", "刀郎", "张雪峰", "全红婵", "钟南山"],
        "topic_given": ["长征"],
        # 题材分类器（多标签）：analyze_topic.py 用它给**外部题目**归类。
        # 放在这里而不是脚本里，是为了让"改题材定义"＝改画像，不用改代码。
        "topics": {name: pat for name, pat in TOPICS},
        "colloquial": COLLOQ,
        "policy_words": ["习主席", "习近平", "五年规划", "十四五", "一带一路", "长江禁渔",
                         "生态文明", "脱贫攻坚", "脱贫", "乡村振兴", "改革开放", "高考改革",
                         "抗疫", "中国梦", "中华民族伟大复兴", "两个一百年", "绿水青山",
                         "金山银山", "国家队", "党"],
        "fingerprints": {
            "不是吗": "2.60/千字（全体）/ 3.51（议论文）——最强的签名",
            "可见": "1.60/千字（全体）/ 2.17（议论文）",
            "试想": "0.18/千字",
            "须": "0.45/千字，只覆盖 30.5% 的篇目",
        },
    }

    # ── 标题画像（2026-09-24 补：此前完全漏掉的一块）────────────────────
    # 为什么值得单列：标题是全文最显眼的部分，而**类型分布本身就是签名**。
    # 三篇稿子若全用同一个类型，比正文用词偏差更容易被认出来——
    # 实测过：三篇仿稿的标题全落进 18.8% 的「逗号双分句」，而他 41% 的冒号式一次没用。
    titles = [re.sub(r"\s", "", (r.get("headline") or "")) for r in rs]
    titles = [t for t in titles if t]
    nt = len(titles)

    def has_any(t, *cs):
        return any(c in t for c in cs)

    def trate(pred):
        return round(sum(1 for t in titles if pred(t)) / nt * 100, 1)

    title_truth = {
        "chars": dist([len(t) for t in titles]),
        "colon_pct": trate(lambda t: has_any(t, "：", ":")),
        "comma_only_pct": trate(lambda t: has_any(t, "，") and not has_any(t, "：", ":")),
        "plain_pct": trate(lambda t: not has_any(t, "：", ":", "，", "；", "、", "·", "•")),
        "three_item_pct": trate(lambda t: len(re.split(r"[、·•，,]", t)) >= 3),
        "mid_dot_pct": trate(lambda t: has_any(t, "·", "•")),
        "quote_pct": trate(lambda t: has_any(t, "“", "”")),
        "first_person_pct": trate(lambda t: has_any(t, "我")),
        "question_pct": trate(lambda t: has_any(t, "？", "?")),
        "dunhao_pct": trate(lambda t: has_any(t, "、")),
    }

    # 题面词复现率：从源文件名里抽出带引号的题面，看标题有没有回扣它的词。
    # ⚠ 分母必须与上面一致——只用**有 headline 的篇目**。
    # （第一版写成遍历全部 rs，把 headline 为空的那篇也算进了分母，于是 57.4% 变 56.4%，
    #   又成了"同一指标两个数"。）
    echo_hit = echo_tot = 0
    for r in rs:
        title = re.sub(r"\s", "", r.get("headline") or "")
        if not title:
            continue
        m = re.search(r"[“「]([^”」]{2,20})[”」]", r.get("src") or "")
        if not m:
            continue
        echo_tot += 1
        words = [w for w in re.split(r"[与和，,、：:\s]+", m.group(1)) if len(w) >= 2]
        if any(w in title for w in words):
            echo_hit += 1
    title_truth["topic_echo_pct"] = round(echo_hit / echo_tot * 100, 1) if echo_tot else None
    title_truth["topic_echo_n"] = echo_tot

    tc = title_truth["chars"]
    targets_title = {
        "chars_band": [int(tc["p25"]), int(tc["p75"])],
        "chars_why": f"P25–P75；中位 {tc['median']:.0f} 字"
                     f"（最短 {tc['min']:.0f} / 最长 {tc['max']:.0f}）",
        "structure_mix": {
            "冒号式（话题词：判断）": title_truth["colon_pct"],
            "单句无标记": title_truth["plain_pct"],
            "逗号双分句": title_truth["comma_only_pct"],
            "三项以上并列": title_truth["three_item_pct"],
        },
        "topic_echo_pct": title_truth["topic_echo_pct"],
        "hard_rules": [
            f"顿号「、」{title_truth['dunhao_pct']}% —— 标题里基本不用顿号，出现即为破绽",
            f"问号 {title_truth['question_pct']}% —— 标题几乎不用问号"
            "（与正文篇末 78% 用反问形成反差，这本身是签名）",
            f"三项并列时用中点「·／•」（{title_truth['mid_dot_pct']}%），不用顿号/逗号",
            f"多篇之间**结构类型必须分散**——不要三篇全用同一种",
        ],
        "truth": title_truth,
    }

    # ── 题材带：题目分析器按题材取阈值（不是全子类均值）────────────────────
    # 每个题材给：篇数 + 段末/篇末反问 + 「可见」与问号密度 + 段落中位 + 该题材的高频素材。
    # analyze_topic.py 读它，决定"这道题该按哪一列的浓度写"。
    topic_bands = {}
    for _tname, _tpat in TOPICS:
        sub_texts = [r["text"] for r in rs if re.search(_tpat, r["text"])]
        if len(sub_texts) < 5:          # 样本太少不给带——免得拿 3 篇当"真值"
            continue
        sm = [m for m in (measure_body(t) for t in sub_texts) if m]
        if not sm:
            continue

        def _med(key):
            v = sorted(x[key] for x in sm)
            return v[len(v) // 2]

        mat_c = Counter()
        for _r in rs:
            if re.search(_tpat, _r["text"]):
                for _m in TOPIC_MATS:
                    if _m in _r["text"]:
                        mat_c[_m] += 1
        topic_bands[_tname] = {
            "n": len(sm),
            "share": round(len(sm) / len(rs), 4),
            "tail_q": round(_med("tail_q"), 1),
            "last_q": round(sum(1 for x in sm if x["last_q"] == 1) / len(sm) * 100, 1),
            "bushi_para": round(_med("bushi_para"), 1),
            "kejian_pk": round(_med("kejian_pk"), 2),
            "q_pk": round(_med("q_pk"), 2),
            "para_med": int(_med("para_med")),
            "materials": [m for m, _ in mat_c.most_common(8)],
        }

    # ── 政治类素材：**放开使用 + 引语数据必须可核**（2026-09-24 政策调整）──
    # 原先是「一律不仿」，实测代价是丢掉 28.8% 篇目的例证重心，换来的是一个说不清数
    # 的"先天欠账"。改为放开后发现：真正的风险不在"用了政治素材"（那是高考下水作文的
    # 常态），而在**编造或记错**——第一次核验就抓到一处失实（某书的字数，两个权威
    # 来源互相矛盾，稿子里写了第三个数字）。所以规则从"禁写"改成"用 + 核验"。
    POL_WORDS = {
        "领袖": ["习近平", "习主席", "总书记", "毛泽东", "周恩来", "邓小平", "朱德",
                 "刘少奇", "陈云"],
        "党史": ["党的二十大", "党中央", "党史", "井冈山", "延安", "遵义会议", "革命先烈",
                 "共产党人", "红军", "长征", "抗战", "先烈", "苏区", "革命根据"],
        "政策": ["十四五", "五年规划", "一带一路", "脱贫攻坚", "乡村振兴", "生态文明",
                 "社会主义核心价值观", "全面小康", "共同富裕", "中国式现代化", "双减", "新课标"],
        "楷模": ["黄文秀", "张桂梅", "钟南山", "袁隆平", "屠呦呦", "钱学森", "邓稼先", "樊锦诗"],
    }
    pol_cov = {t: round(sum(1 for r in rs if any(w in r["text"] for w in ws)) / len(rs), 4)
               for t, ws in POL_WORDS.items()}
    BANNED_TIERS = ("领袖", "党史", "政策")   # 原先被"铁律4"禁掉的那三层（楷模层本来就没禁）
    pol_banned = round(sum(1 for r in rs if any(
        any(w in r["text"] for w in POL_WORDS[t]) for t in BANNED_TIERS)) / len(rs), 4)
    pol_banned_n = round(pol_banned * len(rs))
    pol_any = round(sum(1 for r in rs
                        if any(w in r["text"] for ws in POL_WORDS.values() for w in ws))
                    / len(rs), 4)
    pol_n = round(pol_any * len(rs))

    politics = {
        "policy": "放开使用；但**引语与具体数据必须可核**——不得编造，不得凭记忆写数",
        "why": (f"原先被禁的三层（领袖／党史／政策）就覆盖 **{pol_banned:.1%}** 的篇目"
                f"（{pol_banned_n}/{len(rs)}）；再加上一直在白名单里的楷模层，"
                f"政治相关素材共覆盖 **{pol_any:.1%}**（{pol_n}/{len(rs)}）。"
                "一律回避等于丢掉这块相似度，换来的却只是一个说不清数的『先天欠账』。"
                "实测风险不在『用了』，在『编造或记错』——故规则从禁写改为用+核验。"),
        "coverage": dict(pol_cov, 被禁三层并集=pol_banned, 全部政治相关并集=pol_any),
        "tiers": {
            "可正常用": ["党史与革命史（长征、抗战、红军）", "时代楷模与英模（黄文秀、张桂梅）",
                        "科学家（屠呦呦、袁隆平、钱学森）", "国家成就（脱贫攻坚、航天）"],
            "用前必须核实": ["领袖与领导人的原话引用", "一切具体数字（百分比／次数／年数／字数）",
                          "政策专名与官方表述"],
            "仍不写": ["编造领袖言论或官方文件表述", "对政策的评价性议论（超出范文常规）",
                     "涉敏感议题的表述"],
        },
        # 已核实的事实：稿子里凡出现这些断言，直接标"已核"，不必重复查。
        # 没查过的 → check_politics.py 会列为待核验。
        "verified": [
            {"claim": "毛泽东读《伦理学原理》批注一万二千余字", "status": "核",
             "src": "央广网／人民网党史／中国军网 一致", "checked": "2026-09-24"},
            {"claim": "该书全书字数（12万 / 8万多 两种说法）", "status": "⚠ 来源矛盾，不得写",
             "src": "人民网党史『12万字』 vs 人民网『8万多字』", "checked": "2026-09-24"},
            {"claim": "批注用语「此说终觉不完满」「此节不当」", "status": "核",
             "src": "人民网党史学习教育官网（毛泽东读书笔记三类及其批注实例）",
             "checked": "2026-09-24"},
            {"claim": "黄文秀任百坭村第一书记，贫困发生率 22.88%→2.71%（稿中可写作『百分之二十二』『百分之二点七』）",
             "status": "核", "src": "新华社／央视／中央党史和文献研究院 一致",
             "checked": "2026-09-24"},
            {"claim": "黄文秀带领村民发展砂糖橘、硬化道路", "status": "核",
             "src": "同上", "checked": "2026-09-24"},
            {"claim": "红军长征二万五千里", "status": "核",
             "src": "人民网党史（1935 年毛泽东语『最多的走了二万五千里』，指红一方面军走得最远的部队）",
             "checked": "2026-09-24"},
            {"claim": "「有气则有势，有识则有度，有情则有韵，有趣则有味」", "status": "核",
             "src": "曾国藩，同治四年六月初一日《谕纪泽纪鸿》家书；"
                    "贵州政协／湖南图书馆／人民日报 一致",
             "checked": "2026-09-24"},
        ],
        # 行文引号（强调用法），不是引文——检查器不该把这类列为"待核验"。
        # 第一版没这一层，结果把「一个废人」「贫困本该如此」「雪山草地」
        # 这类自造引号全报成待核，清单变噪音，真该核的几条反被淹掉。
        "non_claims": ["一个废人", "贫困本该如此", "雪山草地", "为什么走",
                       "当时不杂", "未来不迎", "横眉冷对", "眼力"],
        "wordlists": POL_WORDS,
    }

    truth_all = {
        "draft": {t["key"]: t["truth"] for t in targets},
        "title": title_truth,
        "flaws2": {k: d(f2, k) for k in
                   ["cv", "ratio", "labels", "semicolon", "pause", "dash", "quote", "paren"]},
        "verbosity": {k: d(vb, k) for k in
                      ["red3", "red5", "red9", "sent_med", "sent_mean", "long_sent_pct",
                       "policy_hits", "policy_pk"]},
        "flaws": {k: d(fl, k) for k in ["tan_pk", "q_pk", "rep_ratio", "aa_pk", "collq_pk"]},
    }

    # 零中位指标要额外记**覆盖率**：这类指标的"中位=0"会让比率判据失效
    # （任何非零值都 > 0×3），判定只能靠"他本人的上界 + 有多少篇目用"。
    # 见 check_flaws2.py 的 lower 分支。
    _lab = [m["labels"] for m in f2]
    if _lab:
        truth_all["flaws2"]["labels"]["_coverage"] = round(
            sum(1 for x in _lab if x >= 1) / len(_lab), 4)

    return {
        "profile_id": "lf",
        "author": NAME_RE,
        "generated_at": GENERATED_AT,
        "generator": GEN,
        "caliber": {
            "source": "corpus_own/_final.json",
            "filter": f"verdict=确证 AND dup_of=空 AND genre={GENRE}",
            "n": len(rs),
            "chars": total_chars,
            "note": "字数=剥离空白；指标=先逐篇算再取中位/均值。"
                    "改语料后必须重跑本脚本刷新 truth；手动设定的区间（source=manual）会保留。",
        },
        "subclass": f"{GENRE} · 古语辩证类 · 约 {MANUAL_BANDS['chars'][0]}–{MANUAL_BANDS['chars'][1]} 字",
        "targets": {"draft": targets, "title": targets_title, "topic_bands": topic_bands,
                    "topic_bands_note":
                        "口径 = **先逐篇算再取中位**（与 targets.draft 同源）。"
                        "strata_stats.py 的 D3b 表用的是 pooled（合并全部文本后算），"
                        "两者会有可见差异——实测辩证类段末反问 33.3%（本表）vs 43.3%（pooled）。"
                        "引用时必须写明是哪一种，不可混用。"},
        "baselines": baselines,
        "wordlists": wordlists,
        "samples": build_samples(rs),
        "politics": politics,
        "coverage": {k: round(v, 4) for k, v in coverage.items()},
        "truth": truth_all,
        "rules": RULES_NOTE,
    }


def to_md(p):
    L = [f"# 画像 · {p['author']}（{p['profile_id']}）", ""]
    c = p["caliber"]
    L += [f"> 口径：{c['filter']}　→　**{c['n']} 篇 / {c['chars']:,} 字**",
          f"> 生成：{p['generator']}　于 {p['generated_at']}", ""]
    L += ["## 稿件级目标区间（自检器用）", "",
          "| 指标 | 目标 | 来源 | 真值中位 | 均值 | P25 | P75 | 依据 |",
          "|---|---|---|---|---|---|---|---|"]
    for t in p["targets"]["draft"]:
        tr = t["truth"]
        L.append(f"| {t['label']} | **{t['lo']}–{t['hi']}** | {t['source']} | "
                 f"{tr['median']} | {tr['mean']} | {tr['p25']} | {tr['p75']} | {t['basis']} |")
    L += ["", "## 基线（判据带用）", ""]
    for grp, kv in p["baselines"].items():
        L.append(f"- **{grp}**：" + "；".join(f"{k} {v}" for k, v in kv.items()))
    L += ["", "## 覆盖面", ""]
    L.append("；".join(f"{k} {v:.1%}" for k, v in p["coverage"].items()))
    s = p.get("samples")
    if s:
        L += ["", "## 风格样本层（生文前必读）", "", f"> {s['usage']}", ""]
        for key in ["kouxu_burst", "kejian_link", "shixiang", "opening",
                    "ending", "stance", "ragged", "roughen"]:
            blk = s.get(key)
            if not blk:
                continue
            L += [f"### {key}（{len(blk['items'])} 例）", "", blk["learn"], ""]
            for it in blk["items"]:
                if "short" in it:
                    L += [f"- （#{it['n']}）短段：{it['short']}", f"  - 同篇最长段：{it['long']}"]
                elif "frag" in it:
                    L.append(f"- （#{it['n']}）重复「{it['frag']}」×{it['times']}：{it['text']}")
                else:
                    L.append(f"- （#{it['n']}）{it['text']}")
            L.append("")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "profile"))
    ap.add_argument("--md", action="store_true")
    args = ap.parse_args()

    p = build()
    os.makedirs(args.out_dir, exist_ok=True)
    jp = os.path.join(args.out_dir, "lf.json")
    mp = os.path.join(args.out_dir, "lf.md")

    # 保留已有的人工区间（若存在），只更新真值
    if os.path.exists(jp):
        with open(jp, encoding="utf-8") as f:
            old = json.load(f)
        old_map = {t["key"]: t for t in old.get("targets", {}).get("draft", [])
                   if t.get("source") == "manual"}
        for t in p["targets"]["draft"]:
            if t["key"] in old_map:
                t["lo"], t["hi"] = old_map[t["key"]]["lo"], old_map[t["key"]]["hi"]
                t["source"] = "manual"
                t["basis"] = old_map[t["key"]].get("basis", t["basis"])

    with open(jp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)
    with open(mp, "w", encoding="utf-8") as f:
        f.write(to_md(p))
    print(f"已写入 {jp}")
    print(f"已写入 {mp}")
    print(f"口径：{p['caliber']['n']} 篇 / {p['caliber']['chars']:,} 字")

    if args.md:
        print()
        print(to_md(p))


if __name__ == "__main__":
    main()
