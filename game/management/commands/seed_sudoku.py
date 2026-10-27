"""初始化四级难度分组和一组可重复执行的示例题。"""

from django.core.management.base import BaseCommand

from game.models import Puzzle, PuzzleGroup
from game.sudoku import count_solutions, solve_grid


GROUPS = [
    ("easy", "入门练习", "简单", "熟悉宫、行、列，从唯一候选开始建立节奏。"),
    ("medium", "进阶推理", "中等", "需要观察隐藏唯一、裸对与宫线关系。"),
    ("hard", "深度训练", "困难", "更少的已知数，更长的逻辑链。"),
    ("expert", "专家挑战", "专家", "为熟练解题者准备的高阶结构与耐心考验。"),
]
PUZZLES = [
    ("easy", "清晨第一局", "530070000600195000098000060800060003400803001700020006060000280000419005000080079"),
    ("medium", "交叉路口", "000260701680070090190004500820100040004602900050003028009300074040050036703018000"),
    ("hard", "静默回廊", "000000907000420180000705026100904000050000040000507009920108000034059000507000000"),
    ("expert", "阿尔卑斯之眼", "100007090030020008009600500005300900010080002600004000300000010040000007007000300"),
]


def grid(text):
    return [[int(text[r * 9 + c]) for c in range(9)] for r in range(9)]


class Command(BaseCommand):
    help = "创建四个难度分组和经过唯一解校验的示例题"

    def handle(self, *args, **options):
        # update_or_create 让初始化命令可重复运行而不会生成重复数据。
        groups = {}
        for order, (slug, name, difficulty, description) in enumerate(GROUPS):
            groups[slug], _ = PuzzleGroup.objects.update_or_create(slug=slug, defaults={
                "name": name, "difficulty": slug, "description": description, "sort_order": order,
            })
        for slug, title, text in PUZZLES:
            puzzle = grid(text)
            solution = solve_grid(puzzle)
            if not solution or count_solutions(puzzle) != 1:
                self.stderr.write(self.style.ERROR(f"跳过 {title}：题目无唯一解"))
                continue
            Puzzle.objects.update_or_create(group=groups[slug], sequence=1, defaults={
                "title": title, "puzzle": puzzle, "solution": solution, "difficulty": slug, "is_active": True,
            })
            self.stdout.write(self.style.SUCCESS(f"已准备：{title}"))
