# -*- coding: utf-8 -*-
"""
题目分析器：拿到**一道外部题目**，产出"按他的习惯该怎么做"的施工单。

为什么需要它
------------
写稿流程的第 1 步原来只写着"定题 → 交人确认"四个字——那是假设题目从他的
题面库里挑。用户给的题不在这套假设里，于是拿到题只能凭感觉写。而这道题该按
哪一列阈值写、他写过多少接近的题、用哪种结构，全都没判，全靠事后自检去补。

施工单回答四件事：
  ① **题材归属** → 决定用哪套阈值（题材间方差大：辩证类段末反问 33.3%，
     青年·成长类 28.6%；拿错列会写得过浓或过淡）
  ② **可比篇目** → 决定 few-shot 用哪几篇，也决定相似度天花板
  ③ **结构类型** → 三种已验证结构里选一种（正反例对举／主题并列／分点列举）
  ④ **素材与标题** → 本题材的实测高频素材；标题结构按他的类型分布挑

用法
----
    python analyze_topic.py <题面文件.md>
    python analyze_topic.py --text "题面正文……"
    python analyze_topic.py --text "…" --json      # 机器读

⚠ 输出是**施工单，不是作文**。按流程，施工单要经确认才落笔。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import find_profile, project_root   # noqa: E402

ROOT = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FEAT = os.path.join(ROOT, "corpus_own", "_final.json")
GENRE = "下水议论文"

# 辩证题的语面标记。他偏好的题面形式就是"古语／名句 + 也有人持不同看法"，
# 见到这些标记基本可以判定该用「正反例对举」。
DIALECTIC_RE = re.compile(
    r"也有人|不同看法|另一种看法|未必|不可一概|辩证|岂能一概|"
    r"固然|然而|但也要|是否|争议|又何必")

# 三种已验证结构。写成规则而不是统计量——这是产品判断（来自实测三篇的成败）。
STRUCTURES = [
    {
        "name": "正反例对举",
        "how": "正面例证二段 → 转折承认对方有理 → 反面例证二段 → 落到主体性",
        "when": "题面自带对立（也有／未必／辩证），或有明确正反两面",
        "anchor": "守界·破界·越界（#85 一系）",
    },
    {
        "name": "主题并列式多层",
        "how": "几个并列的名词各领一段（如 脱贫之山 → 生态之山 → 制造之山）",
        "when": "题面给出多个并列概念／三个关键词，且互不构成对立",
        "anchor": "「再也没有作文题了」一系（#131）",
    },
    {
        "name": "分点列举式",
        "how": "先说清一层理，再补一层，逐层加深（不用序次词，用「还有」衔接）",
        "when": "治学／方法／读书类题面，无强对立也无并列名词",
        "anchor": "「我的观点：笔记适当做」（#43／#58 一系）",
    },
]

# 题面里出现这些词，说明是"多概念并列"型
PARALLEL_HINT = ["与", "和", "、", "三者", "两者", "三个"]
# 治学／方法类
METHOD_HINT = ["读书", "治学", "学问", "笔记", "札记", "积累", "方法", "素养", "经典"]

STOP = set("的了是在有和与就都而及等这那你我他她它其之为对从把被于并且或但很更最"
           "一个一种一些什么怎样如何为什么材料阅读下面的根据要求作文题目")

# 题干套话：几乎每道题都有，对"找可比篇目"毫无信息量。
# 第一版没滤，结果六篇"可比篇目"全是共用「对此／思考」——纯噪音。
BOILER = [
    "对此", "你有怎样的", "有怎样的", "思考", "写作", "写一篇", "一篇", "不少于",
    "自拟标题", "自选角度", "文体不限", "诗歌除外", "不得抄袭", "材料",
    "引发", "启示", "谈谈", "看法", "你的", "请", "要求", "据此", "依据",
    "阅读下面", "理解", "体验", "结合自己", "根据要求",
]
# 引语引导词：它们是"引出题面"的，不是题面内容
QUOTE_LEAD = ["古人云", "有人说", "俗话说", "常言道", "有言", "云", "曰", "诗云"]
# 指代词开头的片段多半是句子碎片（"这十六个字讲…"），不是话题词
PRONOUN_HEAD = "这那其该此每某一"
# 话题词长度上限：超过这个长度的片段基本是整句（"这三个词串起了中国"）
WORD_MAX = 8


def load_profile():
    p, src = find_profile()
    return p, src


def load_rows():
    """语料里的目标子类篇目；语料不在本机时返回 None（skill 独立运行模式）。"""
    if not os.path.exists(FEAT):
        return None
    with open(FEAT, encoding="utf-8") as f:
        allrows = json.load(f)
    return [r for r in allrows
            if r["verdict"] == "确证" and not r["dup_of"] and r["genre"] == GENRE]


def topic_words(text):
    """从题面抽实词片段（2–8 字、非套话），用于找可比篇目与拟标题。

    **引号内容优先级最高**：题面的核心话题词几乎总在引号里。
    实测「谈谈对'输与赢'的理解」——真正的题眼是「输与赢」，
    而第一版把引号当标点洗掉了，剩下的全是「理解」这类套话，
    于是召回的"可比篇目"共用词是「理解」，等于没召。
    """
    raw = []
    # 中文引号与 ASCII 单引号都认——外部题面常把题眼写成 '输与赢' 这种形式
    for m in re.finditer(r"[“「『]([^”」』]{2,20})[”」』]|'([^']{2,20})'", text):
        body = m.group(1) or m.group(2) or ""
        for p in re.split(r"[，,、；;]", body):
            p = p.strip()
            if 2 <= len(p) <= 10:
                raw.append(p)

    clean = re.sub(r"[“”「」『』【】《》（）()\[\]{}']", " ", text)
    clean = re.sub(r"[\s，。！？、；：,.!?;:]+", "|", clean)
    for seg in clean.split("|"):
        seg = seg.strip()
        if len(seg) < 2 or seg in STOP or seg in QUOTE_LEAD:
            continue
        for part in re.split(r"[与和的以及]", seg):
            part = part.strip()
            if not part:
                continue
            if len(part) <= WORD_MAX:
                raw.append(part)
            else:
                # 长片段（多半是整句）用更宽的虚词再切一遍——
                # 实测「读书札记是前人治学的常用方式」一刀下去只剩「常用方式」，
                # 把真正的话题词「读书札记」丢了。
                for p2 in re.split(r"[是为即可能会要应，,、]", part):
                    p2 = p2.strip()
                    if len(p2) >= 2:
                        raw.append(p2)

    seen, res = set(), []
    for w in raw:
        if len(w) < 2 or len(w) > WORD_MAX:
            continue
        if w in STOP or w in QUOTE_LEAD:
            continue
        if w[0] in PRONOUN_HEAD:              # 指代词开头的句子碎片
            continue
        if any(b in w for b in BOILER):       # 题干套话一律丢
            continue
        if w in seen:
            continue
        seen.add(w)
        res.append(w)
    return res


def classify(text, topics):
    """题材多标签。返回 [(题材, 命中词数, [命中词…]), …]，按命中数降序。"""
    hits = []
    for name, pat in topics.items():
        found = sorted(set(re.findall(pat, text)))
        if found:
            hits.append((name, len(found), found))
    hits.sort(key=lambda x: -x[1])
    return hits


def peers(words, rows, topic_pat=None, topn=12):
    """可比篇目：**两路召回**。

    路 A 题面词重叠（字面）；
    路 B 主题材同类（语义）。

    为什么必须两路：古语类题面的关键词往往在他语料里**根本不存在**
    （实测竞猜八的「物来顺应」全库零命中），纯字面召回只剩 1 篇，
    而他的辩证类实际有 29 篇可参照——那 1 篇把天花板判成了"生僻"，是错的。
    """
    if not rows:
        return []
    scored = []
    for r in rows:
        hay = (r.get("headline") or "") + " " + (r.get("text") or "")
        hit = [w for w in words if w in hay]
        title_hit = [w for w in words if w in (r.get("headline") or "")]
        s = len(hit) + 2 * len(title_hit)
        in_topic = bool(topic_pat and re.search(topic_pat, hay))
        if s == 0 and not in_topic:
            continue
        if in_topic:
            s += 1.5
        # 字数越接近他的浓度峰值档（800–1099）越优先——同题材里挑更像的
        scored.append((s, r, hit if hit else ["（题材同类，无字面重叠）"]))
    scored.sort(key=lambda x: (-x[0], abs((x[1].get("chars") or 0) - 1000)))
    return scored[:topn]


# 天花板档次，由低到高——取两路判据里**较低**的一档
LEVEL_ORDER = ["无先例", "生僻", "边缘", "常见", "熟域"]


def _topic_level(n_topic):
    """题材体量判档：**只作封顶**，不单独决定天花板。

    题材有 40 篇只能说明"这类题他写过很多"，说明不了"这道题有得参照"。
    """
    if n_topic >= 40:
        return 4, f"该题材在他语料里有 {n_topic} 篇"
    if n_topic >= 10:
        return 3, f"该题材有 {n_topic} 篇"
    if n_topic >= 3:
        return 2, f"该题材只有 {n_topic} 篇"
    if n_topic >= 1:
        return 1, f"该题材只有 {n_topic} 篇"
    return 0, "这一题材在他语料里查不到"


def _recall_level(n_peers):
    """实际召回判档：**主判据**。召回数 = 字面重叠 + 同题材两路相加的去重篇数。"""
    if n_peers >= 8:
        return 4, f"实际召回 {n_peers} 篇可比篇目"
    if n_peers >= 4:
        return 3, f"实际召回 {n_peers} 篇"
    return 2, f"实际只召回 {n_peers} 篇"


def ceiling(n_topic, n_peers):
    """相似度天花板：**主判据是实际召回篇数**，题材体量只作封顶。

    为什么改（第 03 轮 §4.5）：旧版只看题材篇数——题材有 40 篇就报「熟域」，
    哪怕这道题的关键词在库里一篇都没召回。那是假信心：组包预演与第 01 轮
    远程 agent 各独立踩过一次（召回 0 篇仍判「熟域」）。
    「这类题他写过很多」≠「这道题有得参照」，两者取较低的一档。

    ⚠ 召回 0 篇时**直接判「边缘」**，不再与题材档取低值——此时题材判定本身
    是推断来的（第三级反推），题材体量这个数也不可靠，拿它封顶只会更假。
    """
    if n_peers == 0:
        extra = "；题材体量同样查不到（双零）" if n_topic <= 0 else f"（题材体量 {n_topic} 篇，但题材判定为推断级，不作信心依据）"
        return ("边缘", f"实际召回 0 篇：题面词在他语料里零重叠{extra}。"
                        "可比篇目不可得时**不得按熟域的浓度写**——"
                        "结构取通用型（正反例对举），自检阈值取题材带下限。")

    r_lvl, r_note = _recall_level(n_peers)
    t_lvl, t_note = _topic_level(n_topic)
    lvl_i = min(r_lvl, t_lvl)
    lvl = LEVEL_ORDER[lvl_i]

    why = {
        "熟域": "可比篇目充足。按题材带正常写，目标是他本人的平均水准。",
        "常见": "结构与素材都有现成参照，按题材带写即可；few-shot 优先取同题材的。",
        "边缘": "**不要指望达到他最熟那类题的浓度**——自检阈值取题材带下限即可，别硬冲上界。",
        "生僻": "题材不熟时他能调用的只有通用结构（正反例对举）与骨干素材，产出更像"
                "「他写陌生题目」，不像「他写熟题」。",
        "无先例": "建议改题，或明确接受「这只是风格摹写，不是他的熟路」。",
    }[lvl]

    cap = "" if t_lvl >= r_lvl else f"{t_note}，题材体量把天花板封到「{LEVEL_ORDER[t_lvl]}」；"
    return lvl, f"{r_note}。{cap}{why}"


def pick_structure(text, hits):
    """结构建议：规则来自三种已验证结构的成败，不是统计量。"""
    names = [n for n, _, _ in hits]
    if DIALECTIC_RE.search(text):
        return STRUCTURES[0], "题面自带对立标记（" + DIALECTIC_RE.search(text).group(0) + "）"
    if any(h in text for h in METHOD_HINT):
        return STRUCTURES[2], "题面是治学／方法类"
    if sum(text.count(h) for h in PARALLEL_HINT) >= 2 and "辩证·哲思" not in names:
        return STRUCTURES[1], "题面出现多个并列概念"
    return STRUCTURES[0], "无强标记，取最通用的一种"


def resolve_topic(text, hits, prs, topics, st):
    """主题材判定——**三级降级**，返回 (题材, 判定依据)。

    为什么不能只靠题面词：题面通常很短，而古语类题面里一个题材词都没有
    （实测竞猜八的题面直接命中 0 个题材）。但阈值必须取某一列，不能空着。
    三级：① 题面词命中 → ② 题型推断 → ③ 可比篇目反推。
    **依据必须打印出来**，否则会让人以为都是题面直接命中的。
    """
    if hits:
        top, n, ws = hits[0]
        # 只命中 1 个词时可信度低：题面词表宽（「青年·成长·人生」含
        # 青年|青春|成长|人生|奋斗|少年|学生|选择），一道谈"输赢"的题
        # 会只因"人生"二字被判成该类。如实标注强度，别假装精确。
        conf = "强" if n >= 2 else "弱——题面线索只有一词，建议人工核一遍"
        return top, f"题面词直接命中「{'、'.join(ws[:3])}」（{n} 词，置信{conf}）"
    if DIALECTIC_RE.search(text):
        return "辩证·哲思", "由题型推断（题面含对立标记，「辩证·哲思」即对应此类）"
    if st["name"] == "分点列举式":
        return "文化·传统·课本", "由题型推断（治学／方法类）"
    if prs:
        c = Counter()
        for _, r, _ in prs:
            hay = (r.get("headline") or "") + " " + (r.get("text") or "")
            for name, pat in topics.items():
                if re.search(pat, hay):
                    c[name] += 1
        if c:
            top, n = c.most_common(1)[0]
            # ⚠ 这一级有系统性偏斜：「青年·成长·人生」词表最宽
            # （青年|青春|成长|人生|奋斗|少年|学生|选择），最容易赢。
            # 故只作参考，并在输出里如实标明来源。
            return top, f"由可比篇目反推（{n}/{len(prs)} 篇命中；此级有偏斜，仅供参考）"
    return None, None


def build(text, prof, rows):
    topics = (prof.get("wordlists") or {}).get("topics") or {}
    bands = (prof.get("targets") or {}).get("topic_bands") or {}
    title_truth = ((prof.get("targets") or {}).get("title") or {}).get("truth") or {}

    words = topic_words(text)
    hits = classify(text, topics)
    order = [n for n, _, _ in hits]
    st, why = pick_structure(text, hits)

    # 第三级判定用**纯字面召回**，避免与题材召回互相依赖（否则成环）
    prs_raw = peers(words, rows, None)
    primary, how = resolve_topic(text, hits, prs_raw, topics, st)
    topic_pat = topics.get(primary) if primary else None
    prs = peers(words, rows, topic_pat, topn=12)
    band = bands.get(primary) if primary else None
    n_topic = (band or {}).get("n", 0)
    lvl, note = ceiling(n_topic, len(prs))

    # 素材池：**题材高频 + 骨干名单补充**，两者都要。
    # 只按题材频率会漏：史铁生、黄文秀在「辩证·哲思」类里各只出现 1 次，
    # 但它俩才是"困境超越者"这条线的骨干——频率低是题材窄，不是不可用。
    mats = []
    for n in ([primary] + order if primary else order)[:2]:
        for m in (bands.get(n) or {}).get("materials", []):
            if m not in mats:
                mats.append(m)
    ok_list = (prof.get("wordlists") or {}).get("materials_ok") or []
    mats_general = [m for m in ok_list if m not in mats]

    return {
        "chars": len(re.sub(r"\s", "", text)),
        "topic_words": words,
        "topics": [{"name": n, "n_hit": k, "hits": h} for n, k, h in hits],
        "primary": primary,
        "primary_how": how,
        "band": band,
        "n_topic": n_topic,
        "peers": [{"n": r["n"], "headline": r.get("headline") or "",
                   "chars": r.get("chars"), "shared": h} for _, r, h in prs],
        "ceiling": {"level": lvl, "note": note},
        "structure": {"name": st["name"], "how": st["how"], "why": why,
                      "anchor": st["anchor"]},
        "materials": mats[:8],
        "materials_general": mats_general,
        "title": {
            "structure_mix": (prof.get("targets") or {}).get("title", {}).get("structure_mix"),
            "chars_band": (prof.get("targets") or {}).get("title", {}).get("chars_band"),
            "topic_echo_pct": title_truth.get("topic_echo_pct"),
            "dunhao_pct": title_truth.get("dunhao_pct"),
            "question_pct": title_truth.get("question_pct"),
            "candidates": title_candidates(text, words, prof),
        },
        "has_corpus": rows is not None,
    }


def title_candidates(text, words, prof):
    """按他的结构分布给标题候选：冒号式前件取题面词，单句式给判断。

    只取 **2–5 字**的词——超过 5 字的片段多是句子（「赛场上有胜负」），
    拿它当"话题词"会写出很荒谬的候选。
    """
    short = [w for w in words if 2 <= len(w) <= 5]
    cands = []
    if short:
        cands.append(("冒号式", f"{short[0]}：〈后件写你的判断〉"))
    cands.append(("单句无标记", "〈一句判断，不作分解〉"))
    if len(short) >= 3:
        cands.append(("三项并列", "·".join(short[:3])))
    return cands


def render(a):
    L = []
    L.append("═" * 62)
    L.append("题目施工单")
    L.append("═" * 62)
    L.append(f"题面 {a['chars']} 字｜§ 语料：{'在本机' if a['has_corpus'] else '不在本机（只用画像）'}")

    L.append("")
    L.append("【① 题材归属】决定用哪一列的阈值")
    if a["topics"]:
        for t in a["topics"]:
            mark = "★题面命中" if t["name"] == a["primary"] else "  附带　　"
            L.append(f"  {mark} {t['name']:<12} 命中 {t['n_hit']} 词：{'、'.join(t['hits'][:6])}")
    else:
        L.append("  （题面本身没有命中任何题材词）")
    if a["primary"] and a["primary_how"]:
        L.append(f"  → 主题材：**{a['primary']}**（{a['primary_how']}）")
    if not a["primary"]:
        L.append("  ⚠ 判定不出主题材——阈值只能取全子类汇总值，浓度会有偏差。见 ②。")

    if a["band"]:
        b = a["band"]
        L.append("")
        L.append(f"  → 阈值取「{a['primary']}」列（该题材 {b['n']} 篇 / 占子类 {b['share']*100:.1f}%）：")
        L.append(f"      段末反问 ≥ {b['tail_q']}%　　篇末反问 必须有（该题材 {b['last_q']}%）")
        L.append(f"      「可见」{b['kejian_pk']}/千字　　问号 {b['q_pk']}/千字　　段落中位 {b['para_med']} 字")
        L.append("      （口径：先逐篇算再取中位。与全子类汇总值不同——别混用。）")

    L.append("")
    L.append(f"【② 可比篇目】{len(a['peers'])} 篇｜相似度天花板：{a['ceiling']['level']}")
    L.append(f"  {a['ceiling']['note']}")
    if a["peers"]:
        L.append("  few-shot 候选（题面词 + 同题材两路召回）：")
        for p in a["peers"][:6]:
            L.append(f"    #{p['n']:<4} {p['chars']:>5}字  {p['headline'][:34]:<36} "
                     f"共用：{'、'.join(p['shared'][:4])}")
    elif not a["has_corpus"]:
        L.append("  （语料不在本机，无法找可比篇目——只用画像基线）")
    else:
        L.append("  ⚠ 找不到可比篇目。")

    L.append("")
    L.append("【③ 结构类型】")
    L.append(f"  → {a['structure']['name']}（{a['structure']['why']}）")
    L.append(f"    {a['structure']['how']}")
    L.append(f"    锚点：{a['structure']['anchor']}")

    L.append("")
    L.append("【④ 素材池】")
    L.append("  本题材高频（按覆盖篇数）：" + ("　".join(a["materials"]) if a["materials"] else "（无）"))
    if a.get("materials_general"):
        L.append("  骨干名单补充：" + "　".join(a["materials_general"]))
    L.append("  ⚠ 题材频率低 ≠ 不可用——史铁生／黄文秀在辩证类只各 1 次，")
    L.append("    但「困境超越」这条线非他们不可。选素材看**功能**，不只看频次。")
    L.append("  ⚠ 政治／党史／政策类放开使用，但引语与数字必须可核（跑 check_politics.py）")

    L.append("")
    L.append("【⑤ 标题】他的结构分布：冒号式 41.0%／单句 37.6%／逗号双分句 18.8%／三项 5.1%")
    if a["title"]["topic_echo_pct"] is not None:
        L.append(f"  题面词复现率 {a['title']['topic_echo_pct']}%——过半标题回扣题面关键词")
    L.append(f"  硬约束：顿号 {a['title']['dunhao_pct']}%（基本不用）·"
             f" 问号 {a['title']['question_pct']}%（标题几乎不用问号）")
    for kind, s in a["title"]["candidates"]:
        L.append(f"    {kind}：{s}")

    L.append("")
    L.append("─" * 62)
    L.append("下一步：把 ①③④ 交人确认（尤其是结构与素材），确认后才落笔。")
    L.append("落笔后跑 check_draft / check_flaws2 / check_verbosity / check_title / check_politics。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="题面文件（md/txt）")
    ap.add_argument("--text", help="直接给题面字符串")
    ap.add_argument("--json", action="store_true", help="输出 JSON（供流程调用）")
    args = ap.parse_args()

    if args.text is not None:
        text = args.text
    elif args.path:
        if not os.path.exists(args.path):
            print(f"找不到题面文件：{args.path}")
            return 2
        with open(args.path, encoding="utf-8") as f:
            text = f.read()
    else:
        print("需要题面：给文件路径，或用 --text")
        return 2

    if not text.strip():
        print("题面为空——没法分析。")
        return 2

    prof, src = load_profile()
    rows = load_rows()
    a = build(text, prof, rows)
    a["profile_source"] = src
    if args.json:
        print(json.dumps(a, ensure_ascii=False, indent=2))
    else:
        print(render(a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
