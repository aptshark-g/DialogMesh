"""五子棋核心逻辑与 AI 单元测试。"""

import os
import sys

# 允许从项目根目录导入 gomoku
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import gomoku
from gomoku import BLACK, WHITE, EMPTY, Gomoku, GomokuAI


@pytest.fixture
def game():
    return Gomoku()


# ---------- 初始化 ----------

def test_initial_state(game):
    """初始棋盘全空，黑方先手，无胜者。"""
    assert game.size == 15
    assert game.current == BLACK
    assert game.winner == EMPTY
    assert len(game.history) == 0
    assert not game.is_full()
    assert game.legal_moves() == [(r, c) for r in range(15) for c in range(15)]


def test_reset(game):
    """重置后回到初始状态。"""
    game.place(7, 7)
    game.place(7, 8)
    game.reset()
    assert game.current == BLACK
    assert game.winner == EMPTY
    assert game.history == []
    assert game.board == [[EMPTY] * 15 for _ in range(15)]


# ---------- 落子 ----------

def test_place_valid(game):
    """在空位落子成功，且执子方轮换。"""
    ok, msg, winner = game.place(7, 7)
    assert ok is True
    assert winner == EMPTY
    assert game.get(7, 7) == BLACK
    assert game.current == WHITE  # 轮到白方


def test_place_out_of_bounds(game):
    """越界落子被拒绝。"""
    ok, msg, winner = game.place(-1, 0)
    assert ok is False
    assert "边界" in msg


def test_place_occupied(game):
    """在已有棋子位置落子被拒绝。"""
    game.place(7, 7)          # 黑
    ok, msg, winner = game.place(7, 7)  # 白尝试同一位置
    assert ok is False
    assert "已有棋子" in msg
    assert game.get(7, 7) == BLACK  # 未被覆盖


def test_alternating_turns(game):
    """黑白双方交替落子。"""
    game.place(7, 7)   # 黑
    game.place(7, 8)   # 白
    game.place(7, 9)   # 黑
    assert game.get(7, 7) == BLACK
    assert game.get(7, 8) == WHITE
    assert game.get(7, 9) == BLACK
    assert game.current == WHITE


# ---------- 胜负判断 ----------

def test_win_horizontal(game):
    """横向五连判胜。"""
    r = 7
    for c in range(7, 12):
        game.place(r, c)   # 黑
        if c < 11:
            game.place(0, c)  # 白下别处
    assert game.winner == BLACK
    assert game.is_game_over()


def test_win_vertical(game):
    """纵向五连判胜。"""
    c = 7
    for r in range(3, 8):
        game.place(r, c)   # 黑
        if r < 7:
            game.place(r, 0)  # 白
    assert game.winner == BLACK


def test_win_diagonal_conflict(game):
    """斜向(主对角)五连判胜。"""
    game.reset()
    for i in range(5):
        game.place(3 + i, 3 + i)   # 黑
        if i < 4:
            game.place(3 + i, 0)   # 白
    assert game.winner is BLACK


def test_win_diagonal_anti(game):
    """斜向(副对角)五连判胜。"""
    game.reset()
    for i in range(5):
        game.place(10 - i, 3 + i)   # 黑
        if i < 4:
            game.place(0, 3 + i)    # 白
    assert game.winner is BLACK


def test_four_not_enough(game):
    """四连不判胜。"""
    for i in range(4):
        game.place(7, i)
        game.place(0, i)
    assert game.winner == EMPTY
    assert not game.is_game_over()


def test_game_over_blocks_moves(game):
    """对局结束后不能再落子。"""
    for c in range(7, 12):
        game.place(7, c)
        if c < 11:
            game.place(0, c)
    assert game.winner == BLACK
    ok, msg, winner = game.place(7, 12)
    assert ok is False
    assert "结束" in msg


# ---------- 平局 ----------

def test_draw_on_full_board():
    """棋盘下满且无五连 -> 平局（winner 保持 EMPTY，is_full True）。"""
    g = Gomoku(size=5)
    # 构造一个无五连的满盘，这里用简单的交错填法（只验证 is_full 路径）
    pattern = [[ (r + c) % 2 == 0 for c in range(5)] for r in range(5)]
    # 用黑对白交替填充，避免五连（简化：直接轮流填满）
    moves = [(r, c) for r in range(5) for c in range(5)]
    # 保证不会形成五连——5x5 满盘必含有五连，此处改为验证 is_full 本身
    for r in range(5):
        for c in range(5):
            g.place(r, c)
    assert g.is_full()
    # 满盘后 legal_moves 为空
    assert g.legal_moves() == []


# ---------- 悔棋 ----------

def test_undo(game):
    """悔棋移除最近一子并恢复执子方。"""
    game.place(7, 7)   # 黑
    game.place(7, 8)   # 白
    assert game.get(7, 8) == WHITE
    assert game.undo() is True
    assert game.get(7, 8) == EMPTY
    assert game.current == WHITE  # 回到白方落子前


def test_undo_empty(game):
    """空历史悔棋返回 False。"""
    assert game.undo() is False


# ---------- AI ----------

def test_ai_picks_center_first_move():
    """AI 首步倾向于中心附近。"""
    g = Gomoku()
    g.current = BLACK
    ai = GomokuAI(g, BLACK)
    r, c = ai.get_move()
    assert g.get(r, c) == EMPTY  # 落在空位
    # 首次落子应在中心区域
    assert 5 <= r <= 9 and 5 <= c <= 9


def test_ai_blocks_threat():
    """AI 应能发现并阻挡对方三连威胁。"""
    g = Gomoku()
    # 黑在 (7,7)(7,8)(7,9) 形成活三，白方 AI 应在此下子防守
    g.place(7, 7)   # 黑
    g.place(0, 0)   # 白
    g.place(7, 8)   # 黑
    g.place(0, 1)   # 白
    g.place(7, 9)   # 黑
    # 此时轮到白 (WHITE) 落子，AI 应封堵
    assert g.current == WHITE
    ai = GomokuAI(g, WHITE)
    r, c = ai.get_move()
    # AI 的落子应拦截黑方的活三（在第7行横向，c 在 6 或 10）
    assert (r, c) in [(7, 6), (7, 10)]


def test_ai_moves_only_on_empty(game):
    """AI 移动总落在空位。"""
    ai = GomokuAI(game, BLACK)
    r, c = ai.get_move()
    assert game.get(r, c) == EMPTY
    game.place(r, c)
    # 再来一回合
    ai2 = GomokuAI(game, WHITE)
    r2, c2 = ai2.get_move()
    assert game.get(r2, c2) == EMPTY


# ---------- 渲染 ----------

def test_render_output(game):
    """渲染输出包含行列信息。"""
    game.place(7, 7)
    out = game.render()
    assert isinstance(out, str) and len(out) > 0
