"""数独格式校验、求解、难度估计以及分步骤教学提示。"""
from itertools import combinations

DIGITS = set(range(1, 10))


def normalize_grid(grid):
    """把外部输入规范成 9×9 的 0–9 整数矩阵。"""
    if not isinstance(grid, list) or len(grid) != 9:
        raise ValueError("必须包含 9 行")
    result = []
    for row in grid:
        if not isinstance(row, list) or len(row) != 9:
            raise ValueError("每行必须包含 9 格")
        parsed = []
        for value in row:
            try:
                number = int(value or 0)
            except (TypeError, ValueError):
                raise ValueError("格子只能是 0–9")
            if number not in range(10):
                raise ValueError("格子只能是 0–9")
            parsed.append(number)
        result.append(parsed)
    return result


def units():
    rows = [[(r, c) for c in range(9)] for r in range(9)]
    cols = [[(r, c) for r in range(9)] for c in range(9)]
    boxes = [[(r, c) for r in range(br, br + 3) for c in range(bc, bc + 3)]
             for br in range(0, 9, 3) for bc in range(0, 9, 3)]
    return rows + cols + boxes


UNITS = units()


def unit_name(index):
    if index < 9:
        return f"第 {index + 1} 行"
    if index < 18:
        return f"第 {index - 8} 列"
    box = index - 18
    return f"第 {box + 1} 宫"


def cell_name(cell):
    return f"R{cell[0] + 1}C{cell[1] + 1}"


def peers(cell):
    r, c = cell
    result = {(r, x) for x in range(9)} | {(x, c) for x in range(9)}
    result |= {(x, y) for x in range(r // 3 * 3, r // 3 * 3 + 3)
               for y in range(c // 3 * 3, c // 3 * 3 + 3)}
    result.discard(cell)
    return result


def duplicate_errors(grid):
    errors = []
    for index, unit in enumerate(UNITS):
        values = [grid[r][c] for r, c in unit if grid[r][c]]
        duplicates = sorted({v for v in values if values.count(v) > 1})
        if duplicates:
            errors.append(f"{unit_name(index)}重复出现数字 {'、'.join(map(str, duplicates))}")
    return errors


def validate_complete_solution(solution):
    try:
        solution = normalize_grid(solution)
    except ValueError as exc:
        return [f"答案格式错误：{exc}"]
    if any(0 in row for row in solution):
        return ["答案必须填写完整"]
    return duplicate_errors(solution)


def validate_puzzle(puzzle, solution=None):
    try:
        puzzle = normalize_grid(puzzle)
    except ValueError as exc:
        return [f"题面格式错误：{exc}"]
    errors = duplicate_errors(puzzle)
    if solution:
        try:
            solution = normalize_grid(solution)
            for r in range(9):
                for c in range(9):
                    if puzzle[r][c] and puzzle[r][c] != solution[r][c]:
                        errors.append(f"题面 {cell_name((r, c))} 与答案不一致")
        except ValueError as exc:
            errors.append(f"答案格式错误：{exc}")
    return errors


def candidates(board):
    """为每个空格计算未被同行、同列和同宫占用的合法数字集合。"""
    board = normalize_grid(board)
    result = {}
    for r in range(9):
        for c in range(9):
            if board[r][c] == 0:
                used = {board[x][y] for x, y in peers((r, c))}
                result[(r, c)] = DIGITS - used
    return result


def _solve(board, limit=2):
    """采用最少候选优先的回溯搜索；limit 用于快速判断是否唯一解。"""
    board = [row[:] for row in normalize_grid(board)]
    solutions = []

    def walk():
        if len(solutions) >= limit:
            return
        cands = candidates(board)
        if not cands:
            if not duplicate_errors(board) and all(all(row) for row in board):
                solutions.append([row[:] for row in board])
            return
        # 优先尝试候选数最少的格子，显著缩小搜索树。
        cell, options = min(cands.items(), key=lambda item: len(item[1]))
        if not options:
            return
        r, c = cell
        for value in sorted(options):
            board[r][c] = value
            walk()
            board[r][c] = 0

    if not duplicate_errors(board):
        walk()
    return solutions


def solve_grid(board):
    found = _solve(board, 1)
    return found[0] if found else None


def count_solutions(board, limit=2):
    return len(_solve(board, limit))


def assess_difficulty(board):
    """按空格数量做稳定的基础难度估计，供投稿自动分组使用。"""
    blanks = sum(value == 0 for row in board for value in row)
    if blanks <= 44:
        return "easy"
    if blanks <= 51:
        return "medium"
    if blanks <= 56:
        return "hard"
    return "expert"


def _hint(technique, level, title, explanation, cells, eliminations=None, placement=None):
    """统一提示返回结构，前端无需了解各推理技巧的内部实现。"""
    return {
        "technique": technique,
        "level": level,
        "title": title,
        "explanation": explanation,
        "cells": [cell_name(x) for x in cells],
        "eliminations": eliminations or [],
        "placement": placement,
    }


def find_hint(board, requested_level="auto"):
    """返回一个可解释的逻辑步骤，不替玩家静默填入答案。"""
    board = normalize_grid(board)
    cands = candidates(board)
    if any(not values for values in cands.values()):
        return _hint("矛盾检查", "初级", "当前盘面存在矛盾",
                     "至少有一个空格已经没有合法候选数，请撤销最近的填写或检查笔记。", [], [])

    # Naked single.
    for cell, values in cands.items():
        if len(values) == 1:
            value = next(iter(values))
            return _hint("唯一候选数", "初级", f"{cell_name(cell)} 只能填 {value}",
                         f"同一行、列和宫已经排除了其他 8 个数字，因此 {cell_name(cell)} 的唯一候选数是 {value}。",
                         [cell], placement={"cell": cell_name(cell), "value": value})

    # Hidden single.
    for idx, unit in enumerate(UNITS):
        for digit in range(1, 10):
            positions = [cell for cell in unit if digit in cands.get(cell, set())]
            if len(positions) == 1:
                cell = positions[0]
                return _hint("隐性唯一", "初级", f"{unit_name(idx)} 的 {digit} 只有一个位置",
                             f"检查{unit_name(idx)}：数字 {digit} 在其他空格都已被同行、同列或同宫排除，只能放在 {cell_name(cell)}。",
                             [cell], placement={"cell": cell_name(cell), "value": digit})

    # Naked pair / triple.
    for size, label in ((2, "裸对"), (3, "裸三")):
        for idx, unit in enumerate(UNITS):
            open_cells = [x for x in unit if x in cands and 1 < len(cands[x]) <= size]
            for combo in combinations(open_cells, size):
                union = set().union(*(cands[x] for x in combo))
                if len(union) != size:
                    continue
                removed = []
                for cell in unit:
                    if cell not in combo and cell in cands:
                        for digit in sorted(cands[cell] & union):
                            removed.append(f"从 {cell_name(cell)} 删除候选数 {digit}")
                if removed:
                    names = "、".join(cell_name(x) for x in combo)
                    nums = "、".join(map(str, sorted(union)))
                    return _hint(label, "中级", f"{unit_name(idx)} 出现{label}",
                                 f"{names} 的候选数合计恰好是 {nums}，这些数字必须占据这 {size} 格，所以{unit_name(idx)}的其他格不能再包含它们。",
                                 combo, removed)

    # Hidden pair / triple.
    for size, label in ((2, "隐性对"), (3, "隐性三")):
        for idx, unit in enumerate(UNITS):
            digit_cells = {d: {x for x in unit if d in cands.get(x, set())} for d in DIGITS}
            useful = [d for d, cells in digit_cells.items() if 1 <= len(cells) <= size]
            for nums in combinations(useful, size):
                cells = set().union(*(digit_cells[d] for d in nums))
                if len(cells) != size:
                    continue
                removed = []
                for cell in cells:
                    for digit in sorted(cands[cell] - set(nums)):
                        removed.append(f"从 {cell_name(cell)} 删除候选数 {digit}")
                if removed:
                    return _hint(label, "中级", f"{unit_name(idx)} 出现{label}",
                                 f"数字 {'、'.join(map(str, nums))} 在{unit_name(idx)}中只可能出现在 {'、'.join(cell_name(x) for x in cells)}，因此这些格可删除其他候选数。",
                                 sorted(cells), removed)

    # Pointing pair/triple: candidates inside one box lie on one line.
    for box_idx, box in enumerate(UNITS[18:]):
        for digit in DIGITS:
            cells = [x for x in box if digit in cands.get(x, set())]
            if len(cells) not in (2, 3):
                continue
            rows, cols = {x[0] for x in cells}, {x[1] for x in cells}
            targets = []
            direction = ""
            if len(rows) == 1:
                row = next(iter(rows)); direction = f"第 {row + 1} 行"
                targets = [(row, c) for c in range(9) if (row, c) not in box and digit in cands.get((row, c), set())]
            elif len(cols) == 1:
                col = next(iter(cols)); direction = f"第 {col + 1} 列"
                targets = [(r, col) for r in range(9) if (r, col) not in box and digit in cands.get((r, col), set())]
            if targets:
                label = "指向对" if len(cells) == 2 else "指向三"
                removed = [f"从 {cell_name(x)} 删除候选数 {digit}" for x in targets]
                return _hint(label, "中级", f"第 {box_idx + 1} 宫形成{label}",
                             f"第 {box_idx + 1} 宫里的数字 {digit} 只能出现在{direction}上的 {'、'.join(cell_name(x) for x in cells)}，所以该行/列在宫外的位置不能再填 {digit}。",
                             cells, removed)

    # Claiming (box-line reduction / 宫线声明).
    for idx, unit in enumerate(UNITS[:18]):
        for digit in DIGITS:
            cells = [x for x in unit if digit in cands.get(x, set())]
            boxes = {(r // 3, c // 3) for r, c in cells}
            if len(cells) >= 2 and len(boxes) == 1:
                br, bc = next(iter(boxes))
                box = [(r, c) for r in range(br * 3, br * 3 + 3) for c in range(bc * 3, bc * 3 + 3)]
                targets = [x for x in box if x not in unit and digit in cands.get(x, set())]
                if targets:
                    return _hint("宫线声明", "中级", f"{unit_name(idx)} 将数字 {digit} 锁定在一个宫内",
                                 f"{unit_name(idx)}中的数字 {digit} 只能位于 {'、'.join(cell_name(x) for x in cells)}，它们同属第 {br * 3 + bc + 1} 宫，因此该宫其余格可排除 {digit}。",
                                 cells, [f"从 {cell_name(x)} 删除候选数 {digit}" for x in targets])

    wing = _find_fish(cands, 2)
    if wing:
        digit, bases, covers, targets, orientation = wing
        return _hint("X-Wing", "高级", f"数字 {digit} 形成 X-Wing",
                     f"在{orientation} {bases} 中，数字 {digit} 都只出现在交叉的 {covers}；它必须占据两条对角位置之一，因此这些交叉线上的其他格可以排除 {digit}。",
                     wing_cells(bases, covers, orientation), [f"从 {cell_name(x)} 删除候选数 {digit}" for x in targets])

    xy = _find_xy_wing(cands)
    if xy:
        pivot, a, b, x, y, z, targets = xy
        return _hint("XY-Wing", "高级", f"以 {cell_name(pivot)} 为轴形成 XY-Wing",
                     f"轴格 {cell_name(pivot)} 为 {{{x},{y}}}，翼格 {cell_name(a)} 为 {{{x},{z}}}、{cell_name(b)} 为 {{{y},{z}}}。无论轴格取 {x} 还是 {y}，两翼之一必为 {z}，所以同时看见两翼的格可排除 {z}。",
                     [pivot, a, b], [f"从 {cell_name(t)} 删除候选数 {z}" for t in targets])

    fish = _find_fish(cands, 3)
    if fish:
        digit, bases, covers, targets, orientation = fish
        return _hint("剑鱼", "高级", f"数字 {digit} 形成剑鱼",
                     f"在{orientation} {bases} 中，数字 {digit} 的位置被限制在 {covers} 三条交叉线上；三枚 {digit} 必定占据这些交叉线，因此其他位置可以排除 {digit}。",
                     wing_cells(bases, covers, orientation), [f"从 {cell_name(x)} 删除候选数 {digit}" for x in targets])

    solved = solve_grid(board)
    if solved:
        cell = next(iter(cands))
        value = solved[cell[0]][cell[1]]
        return _hint("试探与矛盾", "高级", "常规技巧暂未发现直接突破口",
                     f"可对 {cell_name(cell)} 的候选数逐一作假设，并沿同行、同列和同宫传播；会造成某格无候选数的分支应排除。完成这一验证后，该格可确定为 {value}。",
                     [cell], placement={"cell": cell_name(cell), "value": value})
    return _hint("盘面检查", "初级", "当前盘面无解", "请检查已有填写，当前状态不能完成为合法数独。", [])


def _find_fish(cands, size):
    for digit in DIGITS:
        row_positions = {r: {c for c in range(9) if digit in cands.get((r, c), set())} for r in range(9)}
        eligible = [r for r, cols in row_positions.items() if 2 <= len(cols) <= size]
        for bases in combinations(eligible, size):
            covers = set().union(*(row_positions[r] for r in bases))
            if len(covers) == size:
                targets = [(r, c) for r in range(9) if r not in bases for c in covers if digit in cands.get((r, c), set())]
                if targets:
                    return digit, tuple(x + 1 for x in bases), tuple(x + 1 for x in sorted(covers)), targets, "行"
        col_positions = {c: {r for r in range(9) if digit in cands.get((r, c), set())} for c in range(9)}
        eligible = [c for c, rows in col_positions.items() if 2 <= len(rows) <= size]
        for bases in combinations(eligible, size):
            covers = set().union(*(col_positions[c] for c in bases))
            if len(covers) == size:
                targets = [(r, c) for c in range(9) if c not in bases for r in covers if digit in cands.get((r, c), set())]
                if targets:
                    return digit, tuple(x + 1 for x in bases), tuple(x + 1 for x in sorted(covers)), targets, "列"
    return None


def wing_cells(bases, covers, orientation):
    if orientation == "行":
        return [(r - 1, c - 1) for r in bases for c in covers]
    return [(r - 1, c - 1) for c in bases for r in covers]


def _find_xy_wing(cands):
    bivalue = {cell: values for cell, values in cands.items() if len(values) == 2}
    for pivot, pv in bivalue.items():
        visible = [x for x in peers(pivot) if x in bivalue]
        for a, b in combinations(visible, 2):
            av, bv = bivalue[a], bivalue[b]
            shared_a, shared_b = pv & av, pv & bv
            if len(shared_a) != 1 or len(shared_b) != 1 or shared_a == shared_b:
                continue
            zset = (av - pv) & (bv - pv)
            if len(zset) != 1:
                continue
            x, y, z = next(iter(shared_a)), next(iter(shared_b)), next(iter(zset))
            targets = sorted((peers(a) & peers(b)) - {pivot, a, b})
            targets = [t for t in targets if z in cands.get(t, set())]
            if targets:
                return pivot, a, b, x, y, z, targets
    return None
