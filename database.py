# 手游任务助手 Gacha Game Quest Helper — 数据访问层
# Copyright (C) 2026 Yamazaki_Kaoru
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""数据访问层（DAO）：SQLite 持久化 + 自动更新 + 导入/导出。

表结构见需求 spec：
    games(id, name UNIQUE, icon_path)
    tasks(id, game_id, task_name, task_type, deadline, completed, period_rule, need_remind)
    remind_rules(id, rule_type, time, enabled)   最多 10 条
"""
import json
import os
import sys
import sqlite3
from contextlib import contextmanager
from datetime import datetime
import models


def _base_dir():
    """数据目录解析（优先级从高到低）：
    1. 环境变量 GAME_TASK_DATA_DIR（便于自定义或迁移数据）
    2. 程序同目录下的 userdata 文件夹（默认）

    无论哪种情况，最终目录都会被自动创建（不存在时），以保证 SQLite 可写入。
    """
    env = os.environ.get("GAME_TASK_DATA_DIR")
    if env:
        base = env
    elif getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    base = os.path.join(base, "userdata")
    os.makedirs(base, exist_ok=True)
    return base


DB_PATH = os.path.join(_base_dir(), "game_tasks.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _dt(s: str) -> datetime:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)  # Python 3.11+ 兼容空格分隔 "2026-08-09 04:00:00"
    except ValueError:
        try:
            # 兼容 Python < 3.11（fromisoformat 不接受空格分隔）及其它格式
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat(sep=" ") if dt else None


def init_db() -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS games (
                   id        INTEGER PRIMARY KEY AUTOINCREMENT,
                   name      TEXT NOT NULL UNIQUE,
                   icon_path TEXT DEFAULT ''
               )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS tasks (
                   id          INTEGER PRIMARY KEY AUTOINCREMENT,
                   game_id     INTEGER NOT NULL,
                   task_name   TEXT NOT NULL,
                   task_type   TEXT NOT NULL,
                   deadline    TEXT NOT NULL,
                   completed   INTEGER NOT NULL DEFAULT 0,
                   period_rule TEXT DEFAULT '',
                   need_remind INTEGER NOT NULL DEFAULT 1,
                   FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
               )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS remind_rules (
                   id        INTEGER PRIMARY KEY AUTOINCREMENT,
                   rule_type TEXT NOT NULL,
                   time      TEXT NOT NULL,
                   enabled   INTEGER NOT NULL DEFAULT 1,
                   game_id   INTEGER NOT NULL DEFAULT -1,
                   task_type TEXT NOT NULL DEFAULT ''
               )"""
        )

        # 迁移：为历史数据库补充可能缺失的列（CREATE TABLE IF NOT EXISTS 不会修改旧表）
        cols = {row[1] for row in cur.execute("PRAGMA table_info(games)").fetchall()}
        if "icon_path" not in cols:
            cur.execute("ALTER TABLE games ADD COLUMN icon_path TEXT DEFAULT ''")

        # 迁移：为提醒规则补充 game_id / task_type 列（旧库兼容）
        rcols = {row[1] for row in cur.execute("PRAGMA table_info(remind_rules)").fetchall()}
        if "game_id" not in rcols:
            cur.execute("ALTER TABLE remind_rules ADD COLUMN game_id INTEGER NOT NULL DEFAULT -1")
        if "task_type" not in rcols:
            cur.execute("ALTER TABLE remind_rules ADD COLUMN task_type TEXT NOT NULL DEFAULT ''")


# ------------------------- 游戏 -------------------------
def game_name_exists(name: str, exclude_id: int = None) -> bool:
    """判断游戏名是否已被占用（编辑时可排除自身 id）。"""
    with get_conn() as conn:
        cur = conn.cursor()
        if exclude_id is not None:
            cur.execute("SELECT id FROM games WHERE name=? AND id!=?", (name, exclude_id))
        else:
            cur.execute("SELECT id FROM games WHERE name=?", (name,))
        return cur.fetchone() is not None


def add_game(name: str, icon_path: str = "") -> int:
    """新增游戏。若名称重复返回 None（调用方据此给出友好提示）。"""
    if game_name_exists(name):
        return None
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO games(name, icon_path) VALUES(?,?)", (name, icon_path))
        return cur.lastrowid


def update_game(gid: int, name: str, icon_path: str = "") -> bool:
    """更新游戏。若新名称与其他游戏重复返回 False，更新成功返回 True。"""
    if game_name_exists(name, exclude_id=gid):
        return False
    with get_conn() as conn:
        conn.execute(
            "UPDATE games SET name=?, icon_path=? WHERE id=?", (name, icon_path, gid)
        )
    return True


def delete_game(gid: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM games WHERE id=?", (gid,))
        # 同步清理指向该游戏的提醒规则，避免 game_id 悬挂引用
        conn.execute("DELETE FROM remind_rules WHERE game_id=?", (gid,))


def get_games() -> list:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM games ORDER BY id")
        return [dict(r) for r in cur.fetchall()]


def get_game(gid: int) -> dict:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM games WHERE id=?", (gid,))
        row = cur.fetchone()
        return dict(row) if row else None


def find_game_by_name(name: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM games WHERE name=?", (name,))
        row = cur.fetchone()
        return dict(row) if row else None


# ------------------------- 任务 -------------------------
def add_task(game_id, task_name, task_type, deadline: datetime,
             period_rule="", need_remind=True) -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO tasks(game_id, task_name, task_type, deadline, completed, period_rule, need_remind)
               VALUES(?,?,?,?,0,?,?)""",
            (game_id, task_name, task_type, _dt_to_str(deadline), period_rule,
             1 if need_remind else 0),
        )
        return cur.lastrowid


def update_task(tid, game_id, task_name, task_type, deadline: datetime,
                period_rule="", need_remind=True, completed=None) -> None:
    with get_conn() as conn:
        if completed is None:
            conn.execute(
                """UPDATE tasks SET game_id=?, task_name=?, task_type=?, deadline=?, period_rule=?, need_remind=?
                   WHERE id=?""",
                (game_id, task_name, task_type, _dt_to_str(deadline), period_rule,
                 1 if need_remind else 0, tid),
            )
        else:
            conn.execute(
                """UPDATE tasks SET game_id=?, task_name=?, task_type=?, deadline=?, completed=?,
                       period_rule=?, need_remind=? WHERE id=?""",
                (game_id, task_name, task_type, _dt_to_str(deadline),
                 1 if completed else 0, period_rule, 1 if need_remind else 0, tid),
            )


def delete_task(tid: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM tasks WHERE id=?", (tid,))


def get_tasks(game_ids=None, types=None) -> list:
    """返回所有任务（含解析后的 deadline datetime），可按游戏/类型筛选。"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks ORDER BY id")
        rows = [dict(r) for r in cur.fetchall()]
    out = []
    for t in rows:
        t["deadline_dt"] = _dt(t["deadline"])
        # 非法 deadline 视为数据损坏：跳过，避免后续排序/计算崩溃
        if t["deadline_dt"] is None:
            continue
        t["completed"] = bool(t["completed"])
        t["need_remind"] = bool(t["need_remind"])
        if game_ids is not None and t["game_id"] not in game_ids:
            continue
        if types is not None and t["task_type"] not in types:
            continue
        out.append(t)
    return out


def get_task(tid: int) -> dict:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE id=?", (tid,))
        row = cur.fetchone()
        if not row:
            return None
        t = dict(row)
        t["deadline_dt"] = _dt(t["deadline"])
        # 非法 deadline 视为数据不可用，返回 None 由调用方安全跳过
        if t["deadline_dt"] is None:
            return None
        t["completed"] = bool(t["completed"])
        t["need_remind"] = bool(t["need_remind"])
        return t


def set_completed(tid: int, completed: bool) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET completed=? WHERE id=?", (1 if completed else 0, tid))


def set_deadline(tid: int, deadline: datetime) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE tasks SET deadline=? WHERE id=?", (_dt_to_str(deadline), tid))


def save_task_state(tid: int, deadline: datetime, completed: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE tasks SET deadline=?, completed=? WHERE id=?",
            (_dt_to_str(deadline), 1 if completed else 0, tid),
        )


# ------------------------- 自动更新（过期重置） -------------------------
def auto_update_all(now: datetime = None) -> bool:
    """启动时/全局刷新点变更后：对所有周期性任务执行过期自动重置。

    返回是否发生任何重置（调用方据此决定是否需要全量重建界面）。
    """
    changed = False
    now = now or datetime.now()
    for t in get_tasks():
        if t["task_type"] in models.PERIODIC_TYPES:
            new_dl, new_comp = models.auto_update_deadline(
                t["deadline_dt"], t["completed"], t["task_type"], t["period_rule"], now
            )
            if new_dl != t["deadline_dt"] or new_comp != t["completed"]:
                save_task_state(t["id"], new_dl, new_comp)
                changed = True
    return changed


def auto_update_task(task_id: int, now: datetime = None) -> None:
    """修改某任务截止时间/周期规则后，立即对该任务执行过期重置。"""
    now = now or datetime.now()
    t = get_task(task_id)
    if not t or t["task_type"] not in models.PERIODIC_TYPES:
        return
    new_dl, new_comp = models.auto_update_deadline(
        t["deadline_dt"], t["completed"], t["task_type"], t["period_rule"], now
    )
    save_task_state(task_id, new_dl, new_comp)


# ------------------------- 提醒规则 -------------------------
def get_remind_rules() -> list:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM remind_rules ORDER BY id")
        return [dict(r) for r in cur.fetchall()]


def add_remind_rule(rule_type: str, time: str, enabled: bool = True,
                    game_id: int = -1, task_type: str = "") -> int:
    """新增一条提醒规则，返回新行 id。

    game_id: 目标游戏 id，-1 表示全部游戏。
    task_type: 任务类型（"日常"等），空字符串表示全部类型。
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO remind_rules(rule_type, time, enabled, game_id, task_type) "
            "VALUES(?,?,?,?,?)",
            (rule_type, time, 1 if enabled else 0, game_id, task_type),
        )
        return cur.lastrowid


def update_remind_rule(rid: int, rule_type, time, enabled,
                       game_id: int = -1, task_type: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE remind_rules SET rule_type=?, time=?, enabled=?, game_id=?, task_type=? "
            "WHERE id=?",
            (rule_type, time, 1 if enabled else 0, game_id, task_type, rid),
        )


def delete_remind_rule(rid: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM remind_rules WHERE id=?", (rid,))


def count_remind_rules() -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM remind_rules")
        return cur.fetchone()[0]


def count_incomplete_grouped(game_id=None, task_type=None) -> dict:
    """返回在筛选范围内、按任务类型（models.TASK_TYPES 顺序）分组的未完成数量。

    game_id 为 None 或 -1 表示全部游戏；task_type 为 None/'' 表示全部类型。
    """
    tasks = get_tasks(
        None if (game_id is None or game_id == -1) else {game_id},
        None if not task_type else {task_type},
    )
    res = {t: 0 for t in models.TASK_TYPES}
    for t in tasks:
        if t["completed"]:
            continue
        res[t["task_type"]] = res.get(t["task_type"], 0) + 1
    return res


# ------------------------- 统计（供通知使用） -------------------------
def count_incomplete_daily() -> int:
    return sum(
        1 for t in get_tasks() if t["task_type"] == "日常" and not t["completed"]
    )


def count_incomplete_all() -> int:
    return sum(1 for t in get_tasks() if not t["completed"])


# ------------------------- 导入 / 导出 -------------------------
def export_json() -> dict:
    return {
        "games": [
            {"id": g["id"], "name": g["name"], "icon_path": g["icon_path"]} for g in get_games()
        ],
        "tasks": [
            {
                "game": db_game_name(t["game_id"]),
                "task_name": t["task_name"],
                "task_type": t["task_type"],
                "deadline": t["deadline"],
                "completed": t["completed"],
                "period_rule": t["period_rule"],
                "need_remind": t["need_remind"],
            }
            for t in get_tasks()
        ],
        "remind_rules": [
            {
                "rule_type": r["rule_type"],
                "time": r["time"],
                "enabled": r["enabled"],
                "game_id": r.get("game_id", -1),
                # 同时导出游戏名，便于导入时稳定映射到新 id（避免旧整数 id 失效）
                "game_name": db_game_name(r.get("game_id", -1)),
                "task_type": r.get("task_type", ""),
            }
            for r in get_remind_rules()
        ],
    }


def db_game_name(gid: int) -> str:
    g = get_game(gid)
    return g["name"] if g else ""


def import_json(data: dict) -> None:
    """覆盖式导入：清空现有数据后按 JSON 重建（调用方负责先备份）。"""
    with get_conn() as conn:
        conn.execute("DELETE FROM remind_rules")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM games")
    # 重建游戏
    game_id_map = {}      # 游戏名 -> 新 id
    old_to_new = {}       # 旧 id -> 新 id
    for g in data.get("games", []):
        gid = add_game(g["name"], g.get("icon_path", ""))
        if gid is None:
            continue  # 理论上不会发生（已清空），防御处理
        game_id_map[g["name"]] = gid
        old_to_new[g.get("id")] = gid
    # 重建任务
    for t in data.get("tasks", []):
        gid = game_id_map.get(t.get("game"))
        if gid is None:
            gid = add_game(t.get("game", "未命名游戏"))
            game_id_map[t.get("game")] = gid
        add_task(
            gid, t["task_name"], t["task_type"],
            _dt(t["deadline"]), t.get("period_rule", ""),
            bool(t.get("need_remind", True)),
        )
    # 重建提醒规则：优先按游戏名映射，其次按旧 id 映射，找不到则重置为 -1（全部游戏）
    for r in data.get("remind_rules", []):
        target_gid = -1
        gname = r.get("game_name")
        if gname:
            target_gid = game_id_map.get(gname, -1)
        elif r.get("game_id") is not None:
            target_gid = old_to_new.get(r["game_id"], -1)
        add_remind_rule(
            r["rule_type"], r["time"], bool(r.get("enabled", True)),
            target_gid, r.get("task_type", ""),
        )
