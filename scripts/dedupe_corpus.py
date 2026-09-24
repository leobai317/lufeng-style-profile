# -*- coding: utf-8 -*-
"""
确证集内部查重：同一篇文章可能被收录多次（号外合集 + 前文后赏 + 独立发布），
会把它的语言特征重复计权，也会污染"跨段重复短句"这类套路化指标。

用 5-gram 集合的 Jaccard 相似度判定近重复（阈值 0.55）。
"""
import os
import re
import json
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, "corpus_own", "confirmed")
OUT = os.path.join(ROOT, "corpus_own", "_duplicates.json")


def shingles(text, k=5):
    s = re.sub(r"[\s“”「」《》（）()\"'，。！？；：、…—]", "", text)
    return {s[i:i + k] for i in range(max(0, len(s) - k + 1))}


def main():
    docs = []
    for fn in sorted(os.listdir(CONF)):
        if fn.endswith(".txt"):
            with open(os.path.join(CONF, fn), encoding="utf-8") as f:
                docs.append((fn[:-4], f.read()))

    sets = {n: shingles(t) for n, t in docs}
    names = [n for n, _ in docs]
    pairs = []
    for i in range(len(names)):
        a = names[i]
        if not sets[a]:
            continue
        for j in range(i + 1, len(names)):
            b = names[j]
            if not sets[b]:
                continue
            inter = len(sets[a] & sets[b])
            if inter < 30:
                continue
            jac = inter / len(sets[a] | sets[b])
            if jac >= 0.55:
                pairs.append((round(jac, 3), a, b))

    pairs.sort(reverse=True)
    print(f"确证集 {len(docs)} 段，检出近重复对 {len(pairs)} 组\n")

    # 连通分量 → 重复簇
    parent = {n: n for n in names}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry
    for _, a, b in pairs:
        union(a, b)

    clusters = defaultdict(list)
    for n in names:
        clusters[find(n)].append(n)
    dup_clusters = {k: sorted(v) for k, v in clusters.items() if len(v) > 1}

    print("重复簇（同一文章被收录多次）：")
    char_of = dict(docs)
    saved = 0
    for k, members in sorted(dup_clusters.items(), key=lambda x: -len(x[1])):
        chars = [len(char_of[m]) for m in members]
        saved += sum(chars) - max(chars)
        print(f"  · {len(members)} 份：{members}　各 {chars} 字")
    print(f"\n去重可省字数（保守估计）：{saved:,}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"pairs": pairs, "clusters": [sorted(v) for v in dup_clusters.values()]},
                  f, ensure_ascii=False, indent=1)
    print(f"明细写入 {OUT}")


if __name__ == "__main__":
    main()
