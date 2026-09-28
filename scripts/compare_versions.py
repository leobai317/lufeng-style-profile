# -*- coding: utf-8 -*-
"""
核对同一篇的「裸文版 / 完整包装版 / 归档版」三者正文是否逐字一致。

正文的唯一真源是裸文版；包装版与归档版由 sync_draft_versions.py 注入。
本脚本用于验证注入没有走样。

用法：python compare_versions.py [篇名前缀，默认"首篇"]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import project_root   # noqa: E402

# 项目根：STYLE_PROJECT 优先，其次脚本的上一级（脚本被复制进 skill 后靠 STYLE_PROJECT）
ROOT = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BYLINE_RE = re.compile(r"^.{0,20}(研究院|教研院|教研室|中学|学校)\s*[\u4e00-\u9fa5]{2,4}$")
MARKER = "# 正文（完整包装版）"


def body(path, marker=None):
    with open(path, encoding="utf-8") as f:
        h = f.read()
    if marker and marker in h:
        h = h.split(marker, 1)[1]
    lines = [ln for ln in h.splitlines() if ln.strip()]
    lines = lines[1:]                                   # 去标题行
    if lines and BYLINE_RE.match(lines[0].strip()):
        lines = lines[1:]                               # 去署名行
    return re.sub(r"\s", "", "\n".join(lines))


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "首篇"
    paths = {
        "裸文版": (os.path.join(ROOT, "稿件", f"{prefix}-裸文版.md"), None),
        "完整包装版": (os.path.join(ROOT, "稿件", f"{prefix}-完整包装版.md"), None),
        "归档版": (os.path.join(ROOT, "稿件", f"{prefix}-归档版.md"), MARKER),
    }
    bodies = {}
    for name, (p, marker) in paths.items():
        if not os.path.exists(p):
            print(f"{name}：文件不存在 —— {p}")
            return 1
        bodies[name] = body(p, marker)
        print(f"{name}：{len(bodies[name])} 字")

    vals = list(bodies.values())
    same = all(v == vals[0] for v in vals)
    print(f"\n三版正文逐字一致：{'是 ✓' if same else '否 ✗'}")
    if not same:
        base = vals[0]
        for name, v in list(bodies.items())[1:]:
            if v != base:
                for i, (x, y) in enumerate(zip(base, v)):
                    if x != y:
                        print(f"  首处差异 @{i}：{name} 是「{y}」，裸文版是「{x}」")
                        print(f"    上下文：…{base[max(0, i - 20):i + 20]}…")
                        break
                else:
                    print(f"  {name} 长度不同：{len(v)} vs {len(base)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
