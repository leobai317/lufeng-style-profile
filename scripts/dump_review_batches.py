# -*- coding: utf-8 -*-
"""
把 216 段按批次打包成自包含的复核任务书（corpus_own/_batch_N.md）。

每批含：序号、源文件、类别、长度、旗标、原标题、以及**纯净版全文**。
复核者只需读一个文件，不必逐段 Read。
"""
import os
import json
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "corpus_own")
BATCH = 6


def main():
    with open(os.path.join(OUT, "_features.json"), encoding="utf-8") as f:
        records = json.load(f)
    n_total = len(records)
    size = (n_total + BATCH - 1) // BATCH

    for b in range(BATCH):
        chunk = records[b * size:(b + 1) * size]
        if not chunk:
            continue
        p = os.path.join(OUT, f"_batch_{b + 1}.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# 复核批次 {b + 1}/{BATCH}　段 {chunk[0]['n']}–{chunk[-1]['n']}"
                    f"（共 {len(chunk)} 段）\n\n")
            f.write("> 每段都是「按署名行从公众号抓取文本中切出的、署名lf的段落」的纯净版。\n"
                    "> 任务：判定每段是否确为lf本人所写，并打上文体与完整度标签。\n\n---\n\n")
            for r in chunk:
                with open(os.path.join(OUT, r["cleaned"]["file"]), encoding="utf-8") as g:
                    text = g.read()
                f.write(f"## #{r['n']:04d}\n\n")
                f.write(f"- 源文件：`{r['src']}`\n")
                f.write(f"- 自动类别：{r['category']}　长度：{r['chars']}→{r['cleaned']['chars']} 字"
                        f"　风险档：{r['risk']}\n")
                f.write(f"- 原标题：{r['headline'] or '（未取到）'}\n")
                if r["flags"]:
                    f.write(f"- 自动旗标：{'；'.join(r['flags'])}\n")
                f.write(f"- 自动指纹：不是吗×{r['fp_clean']['bushi']}"
                        f"　可见×{r['fp_clean']['kejian']}"
                        f"　问号×{r['fp_clean']['q']}"
                        f"　省略号×{r['fp_clean']['ellipsis']}\n\n")
                f.write("```text\n" + text + "\n```\n\n---\n\n")
        print(f"{p}  ({len(chunk)} 段)")


if __name__ == "__main__":
    main()
