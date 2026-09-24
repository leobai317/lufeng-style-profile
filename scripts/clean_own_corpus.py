# -*- coding: utf-8 -*-
"""
lf本人语料库 · 清洗器

在 review_own_corpus.py 落盘的原始段落上，剥掉不属于他的文字。
**不删只标**：全文版保留在 raw/，纯净版另存到 clean/，剪了什么全部记录在案。

  corpus_own/raw/own_NNNN.txt     原始切分（含尾部垃圾与评点夹批）
  corpus_own/clean/own_NNNN.txt   纯净版
  corpus_own/_features.json       追加 cleaned 字段（剪掉了什么、多少字、哪条规则）

流水线（分四遍，每遍职责单一，便于定位误剪）
  A  R1 图片文件名行 / R2 「本期点评：X」署名行     —— 安全，无条件执行
  B  R4 尾部栏目标题行 / R5 尾部下一篇标题行          —— 结构性，带误剪回退
  C  R3 「总评：」起至段末（点评人的总评块）          —— 有意剥离
  D  R6 段末评点夹批（正文已收句，后面还挂完整成句的括号）—— 有意剥离

回退阀只作用于 B：诗歌整篇是无标点短句，最容易被 R5 吃光，
所以诗歌体直接跳过 B，且 B 剪掉超过 10% 就整体回退并记账。
"""
import os
import re
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "corpus_own")
CLEAN = os.path.join(OUT, "clean")
FEAT = os.path.join(OUT, "_features.json")

IMG_RE = re.compile(r"^\S*\.(jpg|jpeg|png|gif|webp)\s*$", re.I)
CREDIT_RE = re.compile(r"^本期点评\s*[：:].*$")
IMAGE_WORD_RE = re.compile(r"^\s*(图片|视频)\s*$")
SECTION_TAIL_RE = re.compile(
    r"^\s*(?:[（(][^）)]{1,8}[）)]\s*)?"
    r"(?:部分)?(?:学校|一线|骨干|新老|市县|市区)?(?:教师|师生|学生|教研员|校长)?"
    r"(?:下水文|下水作文|作文|作品|习作)(?:展示|选登|汇编|作品)?\s*$"
)
END_PUNCT = "，。！？：；、）】”』…—,.:;)"

COMMENT_KW = [
    "评分", "符合", "体现", "展示", "彰显", "紧扣", "开篇", "结构", "论证",
    "过渡段", "总结全文", "升华", "呼应", "设计", "技法", "妙在", "亮点",
    "考纲", "阅卷", "主旋律", "思辨", "谋篇", "文采", "立意",
]

# —— R7：正文中途出现这些 → 后面都不是他的，就地截断 ——
# 触发 R7 的实测案例：某段后面吞进了「某校　张　三」「某校  李 四」两位老师
# 的下水文，原因是**署名行姓名内部带空格**，原正则匹配不上。
# 这是个容易漏的坑：漏掉它不会报错，只会让某一段莫名变长。
MID_SECTION_RE = re.compile(
    r"^\s*\S{0,12}(?:教师|师生|学生|教研员|校长)"
    r"(?:下水文|下水作文|作文|作品|习作|诗歌)(?:展示|选登|汇编|作品)?\s*$"
)
BRACKET_MARK_RE = re.compile(r"^\s*【\s*(?:总评|思路概要|点评|赏析|后赏|评析)\s*】")
# R8：文末附他人文章的引导语 / 「文/某某」署名 / 单独成段的「点评：」
APPENDIX_RE = re.compile(r"^\s*\d+\s*[、.．)]\s*(?:后附|附|附上).{0,20}$")
WEN_SLASH_RE = re.compile(r"^\s*文\s*[/／]\s*[\u4e00-\u9fa5]{2,4}\s*$")
PLAIN_CREDIT_RE = re.compile(r"^\s*点\s*评\s*[：:].*$")
# 行尾的点评人括注
INLINE_CRITIC_RE = re.compile(r"[（(]\s*点评人\s*[：:][^）)]{1,12}[）)]\s*$")
# 他人署名行：单位（含中/学/校/院/室/局）+ 姓名（姓名内部可能有空格）
OTHER_BYLINE_RE = re.compile(
    r"^\s*[\u4e00-\u9fa5]{2,10}"
    r"(?:中|中学|学校|学院|大学|研究院|教研院|教研室|实验学校|高级中学|小学)"
    r"[\s　]{1,6}[\u4e00-\u9fa5](?:[\s　]?[\u4e00-\u9fa5]){1,3}\s*$"
)

REQ_BUSHI = "【要求】" in ""


def pass_a(text):
    """R1 图片名 / R2 点评署名"""
    kept, dropped = [], []
    for l in text.splitlines():
        s = l.strip()
        if not s or IMAGE_WORD_RE.match(s):
            continue
        if IMG_RE.match(s):
            dropped.append(["R1图片名", s]); continue
        if CREDIT_RE.match(s):
            dropped.append(["R2点评署名", s]); continue
        kept.append(l)
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept).strip(), dropped


def pass_b(text, allow):
    """R4 尾部栏目标题 / R5 尾部下一篇标题（带 10% 误剪回退）"""
    if not allow:
        return text, [], False
    lines = text.splitlines()
    kept, dropped = list(lines), []
    for _ in range(3):
        if kept and SECTION_TAIL_RE.match(kept[-1].strip()):
            dropped.append(["R4栏目标题", kept[-1].strip()])
            kept.pop()
            while kept and not kept[-1].strip():
                kept.pop()
        else:
            break
    if len(kept) >= 2:
        last, prev = kept[-1].strip(), kept[-2].strip()
        if (last and len(last) <= 22 and last[-1] not in END_PUNCT
                and not last.startswith("“") and "：" not in last
                and prev and prev[-1] in "。！？…”』）"):
            dropped.append(["R5尾部标题", last])
            kept.pop()
    out = "\n".join(kept).strip()
    if len(dropped) and len(out) < len(text) * 0.9:
        return text, [["回退B", f"B 剪掉过多，回退（{len(text)}→{len(out)}）"]], True
    return out, dropped, False


def pass_c(text):
    """R3 总评块"""
    lines = text.splitlines()
    idx = None
    for i, l in enumerate(lines):
        if re.match(r"^\s*总\s*评\s*[：:]", l):
            idx = i
    if idx is None:
        return text, []
    return "\n".join(lines[:idx]).strip(), [["R3总评块", "\n".join(lines[idx:])[:160]]]


def pass_d(text):
    """R6 段末评点夹批 + R8 行尾「（点评人：X）」"""
    dropped, out = [], []
    for line in text.splitlines():
        s = line.rstrip()
        m = INLINE_CRITIC_RE.search(s)
        if m:
            dropped.append(["R8点评人括注", m.group(0)])
            s = s[:m.start()].rstrip()
        m = re.search(r"[（(]([^（）()]{6,})[）)]\s*$", s)
        if m:
            inner, before = m.group(1), s[:m.start()].rstrip()
            if before and before[-1] in "。！？…”』）":
                if any(k in inner for k in COMMENT_KW) or inner[-1] in "。！？":
                    dropped.append(["R6评点夹批", inner[:60] + ("…" if len(inner) > 60 else "")])
                    s = before
        out.append(s)
    return "\n".join(out).strip(), dropped


def pass_e(text):
    """R7 截断外来内容：正文中途遇到他人署名 / 栏目标题 / 本期点评 / 【总评】

    只在第 2 行之后开始扫（第 1 行是正文开头），命中即截断，保留前面部分。
    命中项全部记账，便于审计截断了什么。
    """
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if i == 0:
            continue
        s = l.strip()
        if not s:
            continue
        hit = None
        if MID_SECTION_RE.match(s):
            hit = "R7栏目标题"
        elif CREDIT_RE.match(s) or PLAIN_CREDIT_RE.match(s):
            hit = "R7点评署名"
        elif BRACKET_MARK_RE.match(s):
            hit = "R7方括号评点块"
        elif APPENDIX_RE.match(s):
            hit = "R8附录引导语"
        elif WEN_SLASH_RE.match(s) or (OTHER_BYLINE_RE.match(s) and "lf" not in s):
            hit = "R8他人署名行"
        if hit:
            kept = "\n".join(lines[:i]).strip()
            return kept, [[hit, f"第{i + 1}行起截断：{s[:40]}"]]
    return text, []


def main():
    if not os.path.exists(FEAT):
        print("先跑 review_own_corpus.py")
        return
    os.makedirs(CLEAN, exist_ok=True)
    with open(FEAT, encoding="utf-8") as f:
        records = json.load(f)

    stat, rollbacks = {}, []
    for r in records:
        with open(os.path.join(OUT, r["file"]), encoding="utf-8") as f:
            raw = f.read()

        verse = r["category"] in ("课本诗", "诗歌组诗") or "诗歌体" in r["flags"]
        dropped = []
        t, d = pass_a(raw);                     dropped += d
        t, d, rb = pass_b(t, allow=not verse);  dropped += d
        if rb:
            rollbacks.append(r["n"])
        t, d = pass_e(t);                       dropped += d
        t, d = pass_c(t);                       dropped += d
        t, d = pass_d(t);                       dropped += d

        # 底线：剪完不足 100 字（诗歌 40 字）→ 回退全文
        floor = 40 if verse else 100
        if len(t) < floor:
            dropped.append(["回退最终", f"仅剩 {len(t)} 字，回退全文"])
            t = raw
            if r["n"] not in rollbacks:
                rollbacks.append(r["n"])

        with open(os.path.join(CLEAN, f"own_{r['n']:04d}.txt"), "w", encoding="utf-8") as f:
            f.write(t)

        rc, cc = len(raw), len(t)
        r["cleaned"] = {
            "file": f"clean/own_{r['n']:04d}.txt",
            "chars": cc, "removed_chars": rc - cc,
            "removed_pct": round((rc - cc) / rc * 100, 1),
            "rules": dropped,
        }
        r["fp_clean"] = {
            "chars": cc,
            "bushi": t.count("不是吗"),
            "bushi_per_k": round(t.count("不是吗") / cc * 1000, 3) if cc else 0,
            "kejian": t.count("可见"),
            "kejian_per_k": round(t.count("可见") / cc * 1000, 3) if cc else 0,
            "q": t.count("？") + t.count("?"),
            "q_per_k": round((t.count("？") + t.count("?")) / cc * 1000, 3) if cc else 0,
            "ellipsis": t.count("……"),
        }
        for name, _ in dropped:
            stat[name] = stat.get(name, 0) + 1

    with open(FEAT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)

    raw_total = sum(r["chars"] for r in records)
    clean_total = sum(r["cleaned"]["chars"] for r in records)
    print(f"清洗完成：{len(records)} 段")
    print(f"  原始总字数 : {raw_total:,}")
    print(f"  纯净总字数 : {clean_total:,}")
    print(f"  剪掉字数   : {raw_total - clean_total:,}  ({(raw_total - clean_total) / raw_total * 100:.1f}%)")
    print("\n规则命中（按次）：")
    for k, v in sorted(stat.items(), key=lambda x: -x[1]):
        print(f"   {k:<10}{v} 次")
    if rollbacks:
        print(f"\n触发回退：{sorted(rollbacks)}")
    print("\n剪掉比例最高的 10 段：")
    for r in sorted(records, key=lambda x: -x["cleaned"]["removed_pct"])[:10]:
        print(f"   #{r['n']:<4} {r['chars']:>5}→{r['cleaned']['chars']:<5} "
              f"-{r['cleaned']['removed_pct']:>5}%  {os.path.basename(r['src'])[:48]}")


if __name__ == "__main__":
    main()
