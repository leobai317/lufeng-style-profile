# -*- coding: utf-8 -*-
"""
把两套自检器的**真实输出**填进 <篇>-归档版.md 的 `<!-- REPORT -->` 占位处。

报告必须由程序生成、不可手抄——否则归档就失去可审计性。

用法：python fill_archive_report.py [篇名前缀，默认"首篇"]
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_io import project_root   # noqa: E402

# 项目根：STYLE_PROJECT 优先，其次脚本的上一级（脚本被复制进 skill 后靠 STYLE_PROJECT）
ROOT = project_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable


def run(script, arg):
    r = subprocess.run([PY, os.path.join(ROOT, "tools", script), arg],
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    if r.returncode != 0 or not r.stdout.strip():
        print(f"{script} 无输出或出错，中止。\n{r.stderr[-500:]}")
        sys.exit(1)
    return r.stdout.strip()


def replace_report(h, report):
    """三种定位方式，兼容首次填充与后续刷新。"""
    # 1) 标记对
    if "<!-- REPORT:BEGIN -->" in h and "<!-- REPORT:END -->" in h:
        a = h.index("<!-- REPORT:BEGIN -->") + len("<!-- REPORT:BEGIN -->")
        b = h.index("<!-- REPORT:END -->")
        return h[:a] + "\n\n" + report + "\n\n" + h[b:]
    # 2) 单标记占位（首次填充）
    if "<!-- REPORT -->" in h:
        return h.replace("<!-- REPORT -->", report, 1)
    # 3) 按小节标题定位（已填充过的，刷新时走这条）
    key = "## 五、"
    if key in h:
        i = h.index(key)
        j = len(h)
        for stop in ["\n---\n", "\n# 正文（完整包装版）"]:
            k = h.find(stop, i)
            if k != -1:
                j = min(j, k)
        return h[:i] + "## 五、指纹自检报告\n\n" + report + "\n" + h[j:]
    return None


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "首篇"
    doc = os.path.join(ROOT, "稿件", f"{prefix}-归档版.md")
    if not os.path.exists(doc):
        print(f"找不到：{doc}")
        sys.exit(1)

    draft = run("check_draft.py", f"{prefix}-裸文版.md")
    flaws = run("check_flaws2.py", f"{prefix}-裸文版.md")
    report = f"```\n{draft}\n```\n\n```\n{flaws}\n```"

    with open(doc, encoding="utf-8") as f:
        h = f.read()
    new = replace_report(h, report)
    if new is None:
        print("归档版里找不到报告位置（既无标记也无「## 五、」小节），中止")
        sys.exit(1)
    with open(doc, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"已把自检报告写入 {prefix}-归档版.md（{len(report.splitlines())} 行）")


if __name__ == "__main__":
    main()
