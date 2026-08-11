# 手游任务助手 Gacha Game Quest Helper — 业务规则
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

"""周期规则、截止时间计算、28 小时制游戏时间换算、红色警告逻辑。

任务类型（与数据库 task_type 字段保持一致，使用中文）：
    '日常', '周常', '双周常', '月常', '限时活动'

period_rule 格式规范：
    日常   : '<天数>d@<时:分>'            例 '1d@04:00'
    周常   : '<天数>d@<周几(0=周一)>@<时:分>'  例 '7d@0@04:00'
    双周常 : '<天数>d@<起始日期>@<时:分>'      例 '14d@2026-08-08@04:00'
    月常   : '1m@<每月几号>@<时:分>'          例 '1m@01@04:00'
限时活动 : 无 period_rule（deadline 由用户直接指定）
"""
from datetime import datetime, timedelta, date
import calendar

# 任务类型（与数据库存储一致）
TASK_TYPES = ["日常", "周常", "双周常", "月常", "限时活动"]
PERIODIC_TYPES = ["日常", "周常", "双周常", "月常"]

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# --------------------------------------------------------------------------
# period_rule 解析
# --------------------------------------------------------------------------
def parse_period_rule(rule: str) -> dict:
    """将 period_rule 字符串解析为结构化字典。

    返回示例（周常）: {'kind':'daily','days':7,'weekday':0,'start':None,'day':None,'hh':4,'mm':0}
    """
    if not rule:
        return {}
    try:
        parts = rule.split("@")
        first = parts[0]
        res = {"kind": None, "days": None, "weekday": None, "start": None, "day": None, "hh": 0, "mm": 0}
        if first.endswith("m"):
            res["kind"] = "monthly"
            res["day"] = int(parts[1])
            hh, mm = parts[2].split(":")
            res["hh"], res["mm"] = int(hh), int(mm)
        else:  # 以 'd' 结尾
            res["days"] = int(first[:-1])
            if len(parts) == 2:  # 每日: '<天数>d@<时:分>'
                res["kind"] = "daily"
                time = parts[1]
            else:  # 周常/双周常: '<天数>d@<周几|起始日期>@<时:分>'
                mid, time = parts[1], parts[2]
                if "-" in mid:  # 双周常起始日期
                    res["kind"] = "biweekly"
                    res["start"] = mid
                else:  # 周几
                    res["kind"] = "weekly"
                    res["weekday"] = int(mid)
            hh, mm = time.split(":")
            res["hh"], res["mm"] = int(hh), int(mm)
        return res
    except (ValueError, IndexError):
        # 非法 period_rule 格式：返回空字典，由调用方兜底处理，避免崩溃
        return {}


def _weekday_occurrence(now: datetime, target_wd: int, hh: int, mm: int) -> datetime:
    """返回 >= now 的下一个 周target_wd(0=周一) hh:mm。"""
    # datetime.weekday(): 周一=0 ... 周日=6
    days_ahead = (target_wd - now.weekday()) % 7
    cand = (now + timedelta(days=days_ahead)).replace(hour=hh, minute=mm, second=0, microsecond=0)
    if cand < now:
        cand += timedelta(days=7)
    return cand


def _biweekly_occurrence(now: datetime, start: str, hh: int, mm: int) -> datetime:
    """返回 >= now 的最近一个 (date-start) % 14 == 0 的 hh:mm。"""
    sy, sm, sd = (int(x) for x in start.split("-"))
    start_d = date(sy, sm, sd)
    cand_d = now.date()
    # 向前对齐到最近的 14 天倍数日
    diff = (cand_d - start_d).days
    if diff < 0:
        cand_d = start_d
    else:
        cand_d = start_d + timedelta(days=(diff // 14) * 14)
    while True:
        cand = datetime(cand_d.year, cand_d.month, cand_d.day, hh, mm)
        if cand >= now:
            return cand
        cand_d += timedelta(days=14)


def _monthday_occurrence(now: datetime, day: int, hh: int, mm: int) -> datetime:
    """返回 >= now 的下一个月 day 号 hh:mm（day 超出当月长度则取月末）。"""
    y, m = now.year, now.month
    for _ in range(48):  # 最多向前找 4 年
        last = calendar.monthrange(y, m)[1]
        d = min(day, last)
        cand = datetime(y, m, d, hh, mm)
        if cand >= now:
            return cand
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    # 兜底
    return datetime(y, m, 1, hh, mm)


# --------------------------------------------------------------------------
# 初始截止时间 / 周期推进
# --------------------------------------------------------------------------
def compute_initial_deadline(task_type: str, rule: str, now: datetime) -> datetime:
    """根据任务类型与规则，计算 >= now 的首次截止时间。"""
    p = parse_period_rule(rule)
    # 空/非法规则兜底：给一个安全默认值，避免调用方 KeyError 崩溃
    if not p:
        return now
    if task_type == "日常":
        cand = now.replace(hour=p.get("hh", 0), minute=p.get("mm", 0), second=0, microsecond=0)
        while cand < now:
            cand += timedelta(days=p.get("days", 1))
        return cand
    if task_type == "周常":
        return _weekday_occurrence(now, p.get("weekday", 0), p.get("hh", 0), p.get("mm", 0))
    if task_type == "双周常":
        return _biweekly_occurrence(now, p.get("start") or now.strftime("%Y-%m-%d"),
                                    p.get("hh", 0), p.get("mm", 0))
    if task_type == "月常":
        return _monthday_occurrence(now, p.get("day", 1), p.get("hh", 0), p.get("mm", 0))
    return now  # 限时活动：deadline 由用户直接给定


def _add_one_month(dt: datetime, day: int, hh: int, mm: int) -> datetime:
    y, m = dt.year, dt.month
    nm = m + 1
    ny = y + (nm - 1) // 12
    nm = (nm - 1) % 12 + 1
    last = calendar.monthrange(ny, nm)[1]
    d = min(day, last)
    return datetime(ny, nm, d, hh, mm)


def advance_deadline(dt: datetime, task_type: str, rule: str) -> datetime:
    """将 deadline 推进一个周期（用于过期自动重置）。"""
    p = parse_period_rule(rule)
    if not p:
        # 空/非法规则：无法计算推进，直接返回原时间（由上层视为不可用）
        return dt
    if task_type == "月常":
        return _add_one_month(dt, p.get("day", 1), p.get("hh", 0), p.get("mm", 0))
    # 日常 / 周常 / 双周常：按 days 推进（周常 days=7，双周常 days=14）
    return dt + timedelta(days=p.get("days", 1))


def auto_update_deadline(deadline: datetime, completed: bool, task_type: str, rule: str,
                         now: datetime):
    """过期自动重置：返回更新后的 (deadline, completed)。

    只要周期性任务过期（deadline <= now），无论是否已完成都重置：
        completed -> False，deadline 反复推进到 > now。
    限时活动不推进。
    """
    if task_type not in PERIODIC_TYPES:
        return deadline, completed
    d = deadline
    comp = completed
    while d <= now:
        comp = False
        nd = advance_deadline(d, task_type, rule)
        # 规则损坏/为空导致无法推进：跳出循环，避免死循环
        if nd <= d:
            break
        d = nd
    return d, comp


# --------------------------------------------------------------------------
# 28 小时制游戏时间
# --------------------------------------------------------------------------
def to_game_time_str(real_dt: datetime, r_hour: int, r_min: int) -> str:
    """将真实时间转换为「游戏时间」字符串（M月D日 HH:MM，HH 可为 24~28）。

    规则（R 为全局刷新点的小时数）：
        hour <  R : 游戏日期 = 真实日期-1，游戏小时 = hour + 24
        hour == R : 游戏日期 = 真实日期-1，游戏小时 = R + 24
        hour >  R : 游戏日期 = 真实日期，  游戏小时 = hour
    """
    if real_dt.hour < r_hour:
        gd = real_dt.date() - timedelta(days=1)
        gh = real_dt.hour + 24
    elif real_dt.hour == r_hour:
        gd = real_dt.date() - timedelta(days=1)
        gh = r_hour + 24
    else:
        gd = real_dt.date()
        gh = real_dt.hour
    return f"{gd.month}月{gd.day}日 {gh:02d}:{real_dt.minute:02d}"


def from_game_time_to_real(gdate: date, ghour: int, gmin: int) -> datetime:
    """游戏时间(日期+0~28小时)反转为真实 datetime。

    ghour <= 23 : 真实 = 当日 ghour:gmin
    ghour >= 24 : 真实 = 次日 (ghour-24):gmin
    """
    if ghour <= 23:
        return datetime(gdate.year, gdate.month, gdate.day, ghour, gmin)
    nd = gdate + timedelta(days=1)
    return datetime(nd.year, nd.month, nd.day, ghour - 24, gmin)


# --------------------------------------------------------------------------
# 红色警告
# --------------------------------------------------------------------------
def remaining_str(deadline: datetime, now: datetime) -> str:
    """人类可读的剩余时间：X天Y小时 / 今天 / 已过期。"""
    delta = deadline - now
    total_min = int(delta.total_seconds() // 60)
    if total_min < 0:
        return "已过期"
    days = total_min // (24 * 60)
    hours = (total_min % (24 * 60)) // 60
    if days > 0:
        return f"{days}天{hours}小时" if hours else f"{days}天"
    if hours > 0:
        mins = total_min % 60
        return f"{hours}小时{mins}分" if mins else f"{hours}小时"
    return f"{total_min}分"


def is_red_warning(task_type: str, deadline: datetime, now: datetime) -> bool:
    """根据任务类型决定剩余多久进入警告：

    日常  : 不警告
    周常  : 仅最后 3 天（或已过期）
    其他  : 最后 7 天（或已过期）
    """
    if task_type == "日常":
        return False
    if task_type == "周常":
        return (deadline - now) < timedelta(days=3)
    return (deadline - now) < timedelta(days=7)


# --------------------------------------------------------------------------
# 周期规则构建辅助
# --------------------------------------------------------------------------
def build_rule(task_type: str, days: int, weekday: int, start: str, month_day: int,
               hh: int, mm: int) -> str:
    """根据对话框输入构建 period_rule 字符串。"""
    t = f"{hh:02d}:{mm:02d}"
    if task_type == "日常":
        return f"{days}d@{t}"
    if task_type == "周常":
        return f"{days}d@{weekday}@{t}"
    if task_type == "双周常":
        return f"{days}d@{start}@{t}"
    if task_type == "月常":
        return f"1m@{month_day:02d}@{t}"
    return ""
