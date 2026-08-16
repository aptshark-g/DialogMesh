"""五子棋小游戏（Gomoku）

纯 Python 实现，无需第三方依赖即可运行：
  - Gomoku      核心棋盘逻辑：落子、胜负判断、局面查询
  - GomokuAI    简单攻防 AI（评分式启发），可作为对手
  - 命令行交互  支持人机对战与双人本地对战

运行示例：
    python gomoku.py                 # 默认人机对战
    python gomoku.py --two-players   # 双人本地对战
    python gomoku.py --ai-first      # AI 执黑先手
"""

import sys

# 棋盘尺寸（标准五子棋 15x15）
BOARD_SIZE = 15

# 棋子
EMPTY = 0
BLACK = 1  # 黑
WHITE = 2  # 白

# 方向：水平、垂直、两条对角线
DIRECTIONS = [(0, 1), (1, 0), (1, 1), (1, -1)]

# 显示符号
PIECE_SYMBOL = {EMPTY: '.', BLACK: '●', WHITE: '○'}


def _in_bounds(r, c):
    return 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE


class Gomoku:
    """五子棋核心逻辑。"""

    def __init__(self, size=BOARD_SIZE):
        self.size = size
        self.board = [[EMPTY] * size for _ in range(size)]
        self.current = BLACK  # 黑先
        self.history = []     # 记录落子 (r, c)
        self.winner = EMPTY

    def reset(self):
        """重置棋盘，回到初始状态。"""
        self.board = [[EMPTY] * self.size for _ in range(self.size)]
        self.current = BLACK
        self.history = []
        self.winner = EMPTY

    def is_full(self):
        """棋盘是否已下满（平局）。"""
        return len(self.history) == self.size * self.size

    def get(self, r, c):
        """获取 (r, c) 位置的棋子。"""
        return self.board[r][c]

    def place(self, r, c):
        """在 (r, c) 落子。

        返回 (ok, msg, winner)。
          ok     : 是否落子成功
          winner : BLACK / WHITE / EMPTY(未见分晓)
          msg    : 附加信息（"棋盘已满" 表示平局）
        """
        if not _in_bounds(r, c):
            return False, "位置超出棋盘边界", EMPTY
        if self.board[r][c] != EMPTY:
            return False, "该位置已有棋子", EMPTY
        if self.winner != EMPTY:
            return False, "对局已结束", self.winner

        piece = self.current
        self.board[r][c] = piece
        self.history.append((r, c))

        if self._check_win(r, c, piece):
            self.winner = piece
            return True, "", piece
        if self.is_full():
            # 平局，维持 winner=EMPTY
            return True, "棋盘已满，平局", EMPTY

        self.current = WHITE if self.current == BLACK else BLACK
        return True, "", EMPTY

    def _check_win(self, r, c, piece):
        """从 (r, c) 出发，检查四个方向是否有五连。"""
        for dr, dc in DIRECTIONS:
            count = 1
            # 正方向
            nr, nc = r + dr, c + dc
            while _in_bounds(nr, nc) and self.board[nr][nc] == piece:
                count += 1
                nr += dr
                nc += dc
            # 反方向
            nr, nc = r - dr, c - dc
            while _in_bounds(nr, nc) and self.board[nr][nc] == piece:
                count += 1
                nr -= dr
                nc -= dc
            if count >= 5:
                return True
        return False

    def undo(self):
        """悔棋一步（移除最近一枚棋子）。"""
        if not self.history:
            return False
        r, c = self.history.pop()
        self.board[r][c] = EMPTY
        # 回退当前执子方：若落子后没有调换，说明游戏刚结束/平局，需还原
        self.winner = EMPTY
        self.current = WHITE if self.current == BLACK else BLACK
        return True

    def legal_moves(self):
        """返回所有空位坐标 (r, c) 列表。"""
        moves = []
        for r in range(self.size):
            for c in range(self.size):
                if self.board[r][c] == EMPTY:
                    moves.append((r, c))
        return moves

    def is_game_over(self):
        """对局是否结束：分出胜负或平局。"""
        return self.winner != EMPTY or self.is_full()

    def winner_name(self):
        return {BLACK: '黑方', WHITE: '白方'}.get(self.winner, '平局')

    def render(self):
        """用文本绘制棋盘。"""
        # 列标
        header = "   " + "".join(f"{c % 10}" for c in range(self.size))
        lines = [header]
        for r in range(self.size):
            row = f"{r % 10:<3}" + "".join(
                PIECE_SYMBOL[self.board[r][c]] for c in range(self.size)
            )
            lines.append(row)
        return "\n".join(lines)

    def __repr__(self):
        return f"<Gomoku turn={self.current} winner={self.winner} moves={len(self.history)}>"


# ---------------------------------------------------------------------------
# 简单 AI：基于棋型评分的攻防启发式
# ---------------------------------------------------------------------------

# 连续同色棋子的方向分值权重（按 连子中出现的最长连续长度与潜能评估）
# 这里用一个简易评分：对每个落子点评估其四方向形成的威胁
_SCORE_LINE = {
    5: 100000,  # 五连，必胜
    4: 10000,   # 活四/冲四
    3: 1000,    # 活三
    2: 100,     # 活二
    1: 10,      # 活一
}


class GomokuAI:
    """攻防参考：对空位打分，分数越高越该下。"""

    def __init__(self, piece=WHITE):
        self.piece = piece
        self.opponent = BLACK if piece == WHITE else WHITE

    def best_move(self, gomoku):
        """返回 AI 认为的最佳落点 (r, c)。"""
        gomoku = gomoku  # 复用同一实例评估，需临时落子再撤销

        best_score = -1
        best = None

        # 先手第一步落在中心，快速开局
        if not gomoku.history:
            mid = gomoku.size // 2
            return (mid, mid)

        for r, c in gomoku.legal_moves():
            score = self._evaluate_move(gomoku, r, c)
            if score > best_score:
                best_score = score
                best = (r, c)
        return best

    def _evaluate_move(self, gomoku, r, c):
        """评估在 (r, c) 落子对 AI 与对手的综合价值（攻 + 防）。"""
        # 进攻：假设自己落子
        attack = self._line_score(gomoku, r, c, self.piece)
        # 防守：评估对手若在此落子的价值
        defense = self._line_score(gomoku, r, c, self.opponent)
        # 防守权重略高于进攻，采用"有急先守"的策略
        return attack * 1.1 + defense * 1.2

    def _line_score(self, gomoku, r, c, piece):
        """假设 piece 落在 (r, c)，返回四个方向的威胁评分总和。"""
        total = 0
        for dr, dc in DIRECTIONS:
            count = 1  # 当前虚拟落子
            # 正方向
            nr, nc = r + dr, c + dc
            while _in_bounds(nr, nc) and gomoku.board[nr][nc] == piece:
                count += 1
                nr += dr
                nc += dc
            # 反方向
            nr, nc = r - dr, c - dc
            while _in_bounds(nr, nc) and gomoku.board[nr][nc] == piece:
                count += 1
                nr -= dr
                nc -= dc
            total += _SCORE_LINE.get(count, 0)
        return total


# ---------------------------------------------------------------------------
# 命令行交互
# ---------------------------------------------------------------------------

NAME = {BLACK: "黑方", WHITE: "白方"}
SYM = {BLACK: PIECE_SYMBOL[BLACK], WHITE: PIECE_SYMBOL[WHITE]}


def _parse_input(text):
    """解析用户输入坐标，支持 '7,9' 或 '7 9'。"""
    text = text.strip().replace('，', ',').replace(' ', ',')
    parts = text.split(',')
    if len(parts) != 2:
        return None
    try:
        r, c = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return r, c


def play_two_players(gomoku):
    """双人本地对战。"""
    gomoku.reset()
    print("双人对战开始，输入坐标如 7,9，输入 undo 悔棋，q 退出。\n")
    while True:
        print(gomoku.render())
        print(f"\n轮到 {NAME[gomoku.current]}（{SYM[gomoku.current]}）")
        cmd = input("> ").strip().lower()
        if cmd in ('q', 'quit', 'exit'):
            print("再见！")
            return
        if cmd == 'undo':
            if gomoku.undo():
                print("已悔棋。")
            else:
                print("无棋可悔。")
            continue
        move = _parse_input(cmd)
        if move is None:
            print("格式错误，例：7,9")
            continue
        ok, msg, _ = gomoku.place(move[0], move[1])
        if not ok:
            print(f"落子失败：{msg}")
            continue
        if msg == "棋盘已满，平局":
            print(gomoku.render())
            print("平局！")
            return
        if gomoku.winner != EMPTY:
            print(gomoku.render())
            print(f"{gomoku.winner_name()}获胜！")
            return


def play_vs_ai(gomoku, ai_piece=WHITE, ai_first=False):
    """人机对战，玩家执黑（默认），AI 执白。"""
    gomoku.reset()
    if ai_first:
        used = gomoku.current  # 当前是黑
        ai = GomokuAI(piece=BLACK)
        human = WHITE
    else:
        ai = GomokuAI(piece=WHITE)
        human = BLACK

    print("人机对战开始。你执黑（●），AI 执白（○）。输入 7,9 落子，undo 悔棋，q 退出。\n")
    while True:
        if gomoku.current == ai.piece:
            r, c = ai.best_move(gomoku)
            ok, msg, _ = gomoku.place(r, c)
            print(gomoku.render())
            print(f"\nAI 落子于 {r},{c}")
            if gomoku.winner != EMPTY:
                print(f"{gomoku.winner_name()}获胜！")
                return
            if msg == "棋盘已满，平局":
                print("平局！")
                return
            continue

        print(gomoku.render())
        print(f"\n你（{SYM[human]}）的回合")
        cmd = input("> ").strip().lower()
        if cmd in ('q', 'quit', 'exit'):
            print("再见！")
            return
        if cmd == 'undo':
            if gomoku.undo():
                print("已悔棋。")
            else:
                print("无棋可悔。")
            continue
        move = _parse_input(cmd)
        if move is None:
            print("格式错误，例：7,9")
            continue
        ok, msg, _ = gomoku.place(move[0], move[1])
        if not ok:
            print(f"落子失败：{msg}")
            continue
        if gomoku.winner != EMPTY:
            print(gomoku.render())
            print(f"{gomoku.winner_name()}获胜！")
            return
        if msg == "棋盘已满，平局":
            print(gomoku.render())
            print("平局！")
            return


def main():
    if '--two-players' in sys.argv:
        play_two_players(Gomoku())
    elif '--ai-first' in sys.argv:
        play_vs_ai(Gomoku(), ai_first=True)
    else:
        play_vs_ai(Gomoku())


if __name__ == '__main__':
    main()
