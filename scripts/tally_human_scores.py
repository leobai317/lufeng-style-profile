# -*- coding: utf-8 -*-
"""
人类志愿者评分统计（校准轮）。

两种读法都算，并各自给出结论——因为"分数方向"这个歧义会让结论整个反过来。

读法 1（his）：分数 = 「出自他本人之手的可能性」（评分表原本的定义，100＝确定是他）
读法 2（fake）：分数 = 「是仿作的可能性」（100＝确定是假的）

关键指标不是"判别力 ≤ 20"这种单侧线，而是双向的两件事：
  · 识破率：该裁判给伪稿的分数是否显著低于他给真文的均分（低 20 分以上 = 识破）
  · 假阳性率：真文被判为伪（低于 50 分）的篇数
"""
import sys

# 稿件真伪：A 真 / B 真 / C 伪 / D 真
TRUTH = ["真", "真", "伪", "真"]
LABELS = ["A", "B", "C", "D"]

# 志愿者 × 四篇（第一至第四篇）
RATERS = [
    ("第1位（熟悉他）", [10, 100, 30, 90]),
    ("第2位",           [85, 40, 80, 10]),
    ("第3位",           [40, 85, 80, 45]),
    ("第4位",           [70, 65, 70, 100]),
]


def analyse(direction):
    """direction: 'his' 或 'fake'"""
    print(f"\n{'='*74}")
    print(f"读法：分数＝{'「是他本人写的」可能性' if direction == 'his' else '「是仿作」的可能性'}")
    print(f"{'='*74}")
    print(f"{'裁判':<16}{'真文均分':>9}{'伪稿分':>8}{'伪−真':>8}{'结论':>14}{'假阳性(真文<50)':>16}")
    print("-" * 74)
    n_fooled = 0
    for name, s in RATERS:
        if direction == "his":
            his = s
        else:
            his = [100 - x for x in s]      # 换算成"他的可能性"
        real = [his[i] for i in range(4) if TRUTH[i] == "真"]
        fake = his[TRUTH.index("伪")]
        rm = sum(real) / len(real)
        delta = fake - rm                   # 负 = 伪稿被压低 = 识破
        fooled = delta > -20                # 没被压低到 20 分以下 = 没识破
        n_fooled += fooled
        fp = sum(1 for i in range(4) if TRUTH[i] == "真" and his[i] < 50)
        print(f"{name:<16}{rm:>9.1f}{fake:>8.0f}{delta:>+8.1f}"
              f"{'未识破' if fooled else '识破':>14}{fp:>16}")
    print("-" * 74)
    print(f"未识破 {n_fooled}/{len(RATERS)} 位　→ "
          f"{'满足「多数裁判判伪稿为真」' if n_fooled >= 2 else '不满足'}")
    return n_fooled


def extremes():
    print(f"\n{'='*74}")
    print("各篇在 4 位裁判之间的分歧（原始分）")
    print(f"{'='*74}")
    print(f"{'稿件':<6}{'真伪':<6}{'分数':<24}{'极差':>6}{'均值':>8}")
    print("-" * 74)
    for i, lab in enumerate(LABELS):
        vals = [s[i] for _, s in RATERS]
        print(f"{lab:<6}{TRUTH[i]:<6}{str(vals):<24}{max(vals) - min(vals):>6}"
              f"{sum(vals) / len(vals):>8.1f}")
    print("\n第 1 位（熟悉他）的分数两极分化最大；其余三位集中在中段。")


if __name__ == "__main__":
    extremes()
    analyse("his")
    analyse("fake")
