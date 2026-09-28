# -*- coding: utf-8 -*-
"""
从 wxfetch/ 的公众号抓取文本中，按署名行切分出"lf本人"的段落。

依据（已人工核对 310_3.13号外、278_5.9号外 两个样本）：
    格式：先是文章标题行，再是署名行「<单位> <姓名>」，再是正文。
    单位变体：示例市教研院 / 示例市教研院 / 示例市教研院 /
              示例市教研院 / 示例市教研室 …
    分隔符：单位与姓名之间 1~4 个空格，或完全无空格。

切分规则：
    1) 按标题去重（文件名 `序号_标题.txt`，序号为抓取顺序，会重复）
    2) 定位所有"署名行"（本人 + 他人），以署名行为界切段
    3) 只保留本人署名的那一段

输出：不写盘，只统计到 stdout（另可选 --emit 目录导出）
"""
import os
import re
import sys
import json
from collections import Counter

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_raw-存档", "wxfetch")

NAME = "lf"

# 署名行：单位关键词 + 2~4 字姓名，整行长度受限
AFFIL = (
    r"(?:教研院|教研室|基础教育研究院|基础教研院|基础研究院|研究院|"
    r"教育局|教育学院|师范学院|中学|学校|高中|学院|大学|"
    r"一中|二中|三中|四中|五中|六中|七中|八中|十中|十一中|十七中|十八中)"
)
BYLINE_RE = re.compile(
    r"^[\s　]*(?:[\u4e00-\u9fa5、\u00b7]{0,20}" + AFFIL + r")?[\s　]*"
    r"([\u4e00-\u9fa5\u00b7]{2,4})[\s　]*$"
)
# 纯姓名行（无单位），用于兜底
BARE_NAME_RE = re.compile(r"^[\s　]*([\u4e00-\u9fa5]{2,4})[\s　]*$")

MAX_BYLINE_LEN = 34  # 超过此长度不可能是署名行


def looks_like_byline(line: str):
    s = line.strip()
    if not s or len(s) > MAX_BYLINE_LEN:
        return None
    # 排除以标点结尾的（标题/正文句）
    if s[-1] in "，。！？：；、）】”』…—,.:;)>\"'":
        return None
    m = BYLINE_RE.match(line)
    if m:
        return m.group(1)
    return None


def load_dedup():
    """按标题去重，同名保留字数最多的那一份"""
    best = {}
    for fn in os.listdir(SRC):
        if not fn.endswith(".txt") or fn.startswith("probe"):
            continue
        # 去掉前导 `数字_`
        title = re.sub(r"^\d+_", "", fn)[:-4]
        path = os.path.join(SRC, fn)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
        except OSError:
            continue
        if title not in best or len(txt) > len(best[title][1]):
            best[title] = (fn, txt)
    return best


def main():
    emit_dir = None
    if "--emit" in sys.argv:
        emit_dir = sys.argv[sys.argv.index("--emit") + 1]
        os.makedirs(emit_dir, exist_ok=True)

    docs = load_dedup()
    total_files = len(docs)

    own_segments = []          # (title, seg_text)
    files_with_byline = 0      # 含本人署名行的文件数
    no_byline_hits = []        # 提到他名字但没有规范署名的文件

    for title, (fn, txt) in docs.items():
        lines = txt.splitlines()
        marks = []  # (line_idx, name)
        for i, ln in enumerate(lines):
            nm = looks_like_byline(ln)
            if nm:
                marks.append((i, nm))

        own_here = False
        for j, (i, nm) in enumerate(marks):
            if nm != NAME:
                continue
            end = marks[j + 1][0] if j + 1 < len(marks) else len(lines)
            seg = "\n".join(lines[i + 1:end]).strip()
            # 去掉图片占位行、空行
            seg = re.sub(r"^\s*(图片|视频)\s*$", "", seg, flags=re.M)
            seg = re.sub(r"\n{3,}", "\n\n", seg).strip()
            if len(seg) >= 120:
                own_segments.append((fn, seg))
                own_here = True
        if own_here:
            files_with_byline += 1
        elif NAME in txt:
            no_byline_hits.append(fn)

    n = len(own_segments)
    chars = sum(len(s) for _, s in own_segments)

    print(f"去重后文件数        : {total_files}")
    print(f"命中本人署名段的文件: {files_with_byline}")
    print(f"切出的本人段落数    : {n}")
    print(f"本人语料总字数      : {chars}")
    if n:
        print(f"平均每段字数        : {chars // n}")
        lens = sorted((len(s) for _, s in own_segments), reverse=True)
        print(f"最长 / 中位 / 最短  : {lens[0]} / {lens[n // 2]} / {lens[-1]}")
        buckets = Counter(
            "≥2000" if len(s) >= 2000 else
            "1200-1999" if len(s) >= 1200 else
            "800-1199" if len(s) >= 800 else
            "400-799" if len(s) >= 400 else "<400"
            for _, s in own_segments
        )
        print("字数分层            : " + " / ".join(f"{k}:{v}" for k, v in buckets.items()))

    # 他名出现但没切出（说明署名格式不规范，需人工看）
    print(f"\n提到但未切出的文件  : {len(no_byline_hits)}")
    for fn in no_byline_hits[:15]:
        print("   -", fn)

    # 反向抽查：切出的段落前 60 字
    print("\n抽样（前 6 条切出的段落开头）：")
    for fn, seg in own_segments[:6]:
        print(f"   [{fn}] {seg[:60]}".replace("\n", " "))

    # 诊断：最长几段的"尾巴"，用于人眼判断有没有把下一篇吞进来
    if "--tails" in sys.argv or emit_dir:
        top = sorted(own_segments, key=lambda t: -len(t[1]))[:5]
        print("\n最长 5 段的尾巴（查切分是否漏界）：")
        for fn, seg in top:
            print(f"\n── [{len(seg)}字] {fn}")
            print("   尾：" + seg[-160:].replace("\n", " ⏎ "))

    if emit_dir:
        index = []
        for k, (fn, seg) in enumerate(own_segments, 1):
            out = os.path.join(emit_dir, f"own_{k:04d}.txt")
            with open(out, "w", encoding="utf-8") as f:
                f.write(seg)
            index.append({"n": k, "src": fn, "chars": len(seg), "file": out})
        with open(os.path.join(emit_dir, "_index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=1)
        print(f"\n已导出 {n} 段 → {emit_dir}")


if __name__ == "__main__":
    main()
