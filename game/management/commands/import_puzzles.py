"""从统一 JSON 格式校验并批量导入数独题目。"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from game.models import Puzzle, PuzzleGroup
from game.sudoku import count_solutions, normalize_grid, validate_complete_solution, validate_puzzle


class Command(BaseCommand):
    help = "从后台导出的 JSON 文件导入题目"

    def add_arguments(self, parser):
        parser.add_argument("file", type=Path)

    def handle(self, *args, **options):
        try:
            records = json.loads(options["file"].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"无法读取 JSON：{exc}")
        if not isinstance(records, list):
            raise CommandError("JSON 顶层必须是数组")
        imported = 0
        for index, item in enumerate(records, 1):
            try:
                # 只有格式合法且唯一解的题目才能进入正式题库。
                puzzle, solution = normalize_grid(item["puzzle"]), normalize_grid(item["solution"])
                difficulty = item.get("difficulty", "easy")
                if difficulty not in {"easy", "medium", "hard", "expert"}:
                    raise ValueError("未知难度")
                errors = validate_puzzle(puzzle, solution) + validate_complete_solution(solution)
                if errors or count_solutions(puzzle) != 1:
                    raise ValueError("；".join(errors) or "题目没有唯一解")
                slug = item.get("group", difficulty)
                group, _ = PuzzleGroup.objects.get_or_create(slug=slug, defaults={
                    "name": slug, "difficulty": difficulty,
                })
                sequence = int(item.get("sequence") or group.puzzles.count() + 1)
                Puzzle.objects.update_or_create(group=group, sequence=sequence, defaults={
                    "title": item.get("title") or f"导入题目 {index}", "puzzle": puzzle,
                    "solution": solution, "difficulty": difficulty, "is_active": True,
                })
                imported += 1
            except (KeyError, TypeError, ValueError) as exc:
                self.stderr.write(self.style.WARNING(f"跳过第 {index} 条：{exc}"))
        self.stdout.write(self.style.SUCCESS(f"成功导入 {imported} 道题"))
