# -*- coding: utf-8 -*-
"""
profile 读取：让自检器在**没有语料**的环境里也能跑（skill 自包含的关键）。

查找顺序：
  1. 显式传入的路径
  2. 环境变量 `STYLE_PROFILE`
  3. `<脚本目录>/profile/lf.json`        ← skill 布局
  4. `<脚本目录>/../profile/lf.json`     ← 项目布局（tools/ 的上一级）
  5. 环境变量 `STYLE_PROJECT` 下的 `profile/`

找不到时返回 (None, None)，调用方应回落到内置快照并**在输出里写明**——
静默回落会让人以为用的是现算值，那是这个项目反复踩的坑。
"""
import json
import os

FILENAME = "lf.json"


def find_profile(explicit=None):
    cands = []
    if explicit:
        cands.append(explicit)
    if os.environ.get("STYLE_PROFILE"):
        cands.append(os.environ["STYLE_PROFILE"])
    here = os.path.dirname(os.path.abspath(__file__))
    cands.append(os.path.join(here, "profile", FILENAME))
    cands.append(os.path.join(here, "..", "profile", FILENAME))
    if os.environ.get("STYLE_PROJECT"):
        cands.append(os.path.join(os.environ["STYLE_PROJECT"], "profile", FILENAME))
    for p in cands:
        if p and os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f), os.path.abspath(p)
    return None, None


def baseline(profile, group):
    """取某个自检器组的基线（中位）。无 profile 时返回 None"""
    if not profile:
        return None
    return (profile.get("baselines") or {}).get(group)


def truth(profile, group):
    """取某个自检器组的完整分布（median/mean/p25/p75）。无 profile 时返回 {}"""
    if not profile:
        return {}
    return (profile.get("truth") or {}).get(group) or {}


def project_root(default=None):
    """定位"项目根目录"（放语料与稿件的地方）。

    脚本被复制进 skill 后，`脚本目录的上一级` 就不再是项目根了。所以按序判定：
      1. 环境变量 `STYLE_PROJECT`
      2. 传入的 default（通常＝脚本目录的上一级）
      3. 当前工作目录
    判据是"该目录下有没有 corpus_own/ 或 稿件文件"，避免误判到 skill 目录。
    """
    cands = []
    if os.environ.get("STYLE_PROJECT"):
        return os.path.abspath(os.environ["STYLE_PROJECT"])
    if default:
        cands.append(default)
    cands.append(os.getcwd())
    for c in cands:
        if not c:
            continue
        if (os.path.isdir(os.path.join(c, "corpus_own"))
                or os.path.isdir(os.path.join(c, "稿件"))):
            return os.path.abspath(c)
    return os.path.abspath(default or os.getcwd())


def caliber_line(profile, path):
    """一行口径说明，供各脚本打印"""
    if not profile:
        return "profile：未找到 → 使用内置阈值（2026-09-23 快照）⚠ 不是现算值"
    c = profile.get("caliber", {})
    when = c.get("generated_at") or profile.get("generated_at") or "未知"
    return (f"profile：{path}\n"
            f"         口径 {c.get('n')} 篇 / {c.get('chars'):,} 字（{c.get('filter')}）"
            f"　生成于 {when}")
