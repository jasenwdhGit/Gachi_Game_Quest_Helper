# 手游任务助手 Gacha Game Quest Helper — QFluentWidgets 重构版主程序
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

"""手游任务助手 Gacha Game Quest Helper — QFluentWidgets 重构版主程序。

数据层（database / models）与原有实现一致，默认使用程序同目录下 userdata
文件夹存放 game_tasks.db 与导入/导出 game_tasks.json（可用环境变量
GAME_TASK_DATA_DIR 自定义数据目录）。
本文件负责 Fluent 风格的视图与交互编排。
"""
import os
import sys
import json
from datetime import datetime
from enum import Enum

from PyQt5.QtCore import Qt, QTimer, QSettings, QRect, QPoint, QRectF, QPointF
from PyQt5.QtGui import QIcon, QColor, QPainter, QFont, QCursor, QPen, QTransform, QPainterPath
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFormLayout,
    QSplitter, QListWidget, QListWidgetItem, QMenu,
    QFrame, QFileDialog, QSystemTrayIcon, QAction,
    QDialog, QScrollArea
)

import qfluentwidgets as qf
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon, FluentIconBase,
    ToolButton, PushButton, PrimaryPushButton,
    TitleLabel, BodyLabel, CaptionLabel, CheckBox, IconWidget, ComboBox,
    SpinBox, HyperlinkButton,
    InfoBar, InfoBarPosition, setTheme, Theme, isDarkTheme, setThemeColor
)

import database
import models
import ui_dialogs
from ui_dialogs import (
    icon_for_path, themed_menu, AddGameDialog, GameManageDialog, AddTaskDialog,
    CloseChoiceDialog, confirm
)


# ----------------------------------------------------------------------------
# 自定义图标：铃铛提醒（QFluentWidgets 内置无铃铛图标，用 QPainter 绘制，随主题变色）
# ----------------------------------------------------------------------------
class AppIcon(FluentIconBase, Enum):
    ALARM = "alarm"

    def path(self, theme=Theme.AUTO):
        return self.value

    def render(self, painter, rect, theme=Theme.AUTO, **attrs):
        color = QColor(255, 255, 255) if isDarkTheme() else QColor(0, 0, 0)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(color, max(1.5, rect.width() * 0.07))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        cx = rect.x() + rect.width() / 2
        cy = rect.y() + rect.height() / 2 + rect.height() * 0.02
        w = min(rect.width(), rect.height()) * 0.58
        h = min(rect.width(), rect.height()) * 0.52
        r = w / 2

        path = QPainterPath()
        # 顶部弧线：从左到右向下弯曲
        path.moveTo(cx - r, cy - h * 0.35)
        path.arcTo(cx - r, cy - h * 0.35 - r, w, r * 2, 180, -180)
        # 右侧向下外扩弧线
        path.quadTo(cx + r * 1.15, cy + h * 0.15, cx + r * 1.30, cy + h * 0.42)
        # 底部水平边
        path.lineTo(cx - r * 1.30, cy + h * 0.42)
        # 左侧向上外扩弧线
        path.quadTo(cx - r * 1.15, cy + h * 0.15, cx - r, cy - h * 0.35)
        painter.drawPath(path)

        # 铃舌（底部小圆点）
        painter.drawEllipse(QPointF(cx, cy + h * 0.52), r * 0.20, r * 0.20)
        painter.restore()


# ----------------------------------------------------------------------------
# 左侧导航栏放大（官方未提供图标/字号公开 API，此处用补丁覆盖绘制）
# 注意：以下依赖 QFluentWidgets 私有内部实现（.common.* 与 NavigationPushButton
# 内部属性），库升级可能失效；若私有 API 不可用则自动降级为默认绘制，不抛异常。
# ----------------------------------------------------------------------------
try:
    from qfluentwidgets import NavigationPushButton
    from qfluentwidgets.common.icon import drawIcon
    from qfluentwidgets.common.color import autoFallbackThemeColor
    _NAV_PATCH_OK = True
except Exception:  # 私有 API 变动时降级，使用控件默认绘制
    _NAV_PATCH_OK = False

_NAV_ICON_SIZE = 24  # 默认 16，放大到 24
_NAV_FONT_SIZE = 12  # 导航文字字号（偏小而精致，不加粗）


def _nav_pushbutton_paint(self, e):
    """放大版 NavigationPushButton 绘制：图标 24px、文字字号由 item 字体控制。"""
    painter = QPainter(self)
    painter.setRenderHints(
        QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform
    )
    painter.setPen(Qt.NoPen)
    if self.isPressed:
        painter.setOpacity(0.7)
    if not self.isEnabled():
        painter.setOpacity(0.4)

    c = 255 if isDarkTheme() else 0
    m = self._margins()
    pl, pr = m.left(), m.right()
    global_rect = QRect(self.mapToGlobal(QPoint()), self.size())

    if self._canDrawIndicator():
        painter.setBrush(QColor(c, c, c, 6 if self.isEnter else 10))
        painter.drawRoundedRect(self.rect(), 5, 5)
        painter.setBrush(autoFallbackThemeColor(self.lightIndicatorColor, self.darkIndicatorColor))
        painter.drawRoundedRect(self.indicatorRect(), 1.5, 1.5)
    elif ((self.isEnter and global_rect.contains(QCursor.pos())) or self.isAboutSelected) and self.isEnabled():
        painter.setBrush(QColor(c, c, c, 6 if self.isAboutSelected else 10))
        painter.drawRoundedRect(self.rect(), 5, 5)

    drawIcon(self._icon, painter,
             QRectF(8 + pl, (self.height() - _NAV_ICON_SIZE) / 2, _NAV_ICON_SIZE, _NAV_ICON_SIZE))

    if getattr(self, "isCompacted", False):
        return

    painter.setFont(self.font())
    painter.setPen(self.textColor())
    left = (8 + _NAV_ICON_SIZE + 12 + pl) if not self.icon().isNull() else pl + 16
    painter.drawText(
        QRectF(left, 0, self.width() - 13 - left - pr, self.height()),
        Qt.AlignVCenter, self.text()
    )


if _NAV_PATCH_OK:
    NavigationPushButton.paintEvent = _nav_pushbutton_paint


CONFIG_PATH = os.path.join(database._base_dir(), "config.ini")
_settings = QSettings(CONFIG_PATH, QSettings.IniFormat)


def cfg_get(key, default, typ=None):
    if typ is not None:
        return _settings.value(key, default, type=typ)
    return _settings.value(key, default)


def cfg_set(key, val):
    _settings.setValue(key, val)
    _settings.sync()


# ----------------------------------------------------------------------------
# 主题配色（深色下：背景与深色导航一致、卡片转灰、文字背景透明）
# ----------------------------------------------------------------------------
def theme_palette():
    """根据当前主题返回配色字典。"""
    if isDarkTheme():
        return {
            "bg": "#202020",            # 与深色导航背景一致
            "card_bg": "#303030",       # 卡片转灰
            "card_bg_warn": "#3A2426",  # 标红任务的浅红背景（深色）
            "card_border": "1px solid rgba(255,255,255,0.08)",
            "hover_border": "rgba(255,255,255,0.22)",
            "icon_bg": "#3a3a3a",
            "title": "#E6E6E6",
            "name": "#F2F2F2",
            "kv_key": "#9A9A9A",
            "kv_val": "#CFCFCF",
            "count": "#9A9A9A",
            "scroll": "rgba(255,255,255,0.25)",
            "scroll_hover": "rgba(255,255,255,0.4)",
        }
    return {
        "bg": "#EEF0F3",
        "card_bg": "#FFFFFF",
        "card_bg_warn": "#FEF0F0",  # 标红任务的浅红背景（浅色）
        "card_border": "1px solid rgba(0,0,0,0.06)",
        "hover_border": "#c8c9cc",
        "icon_bg": "#F5F7FA",
        "title": "#303133",
        "name": "#303133",
        "kv_key": "#C0C4CC",
        "kv_val": "#606266",
        "count": "#909399",
        "scroll": "rgba(0,0,0,0.22)",
        "scroll_hover": "rgba(0,0,0,0.35)",
    }


def filter_list_qss(p):
    """筛选列表（#filterList）的 QSS，含 iPhone 风格滚动条。"""
    return f"""
        #filterList{{
            background:transparent;
            border:none;
            border-radius:10px;
            outline:none;
            color:{p['name']};
        }}
        #filterList::item{{
            border-radius:6px;
            background:transparent;
        }}
        #filterList::item:selected{{
            background:rgba(64,158,255,0.18);
            color:#409EFF;
        }}
        #filterList QScrollBar:vertical{{
            background:transparent;
            width:8px;
            margin:4px 2px 4px 0px;
        }}
        #filterList QScrollBar::handle:vertical{{
            background:{p['scroll']};
            border-radius:4px;
            min-height:40px;
        }}
        #filterList QScrollBar::handle:vertical:hover{{
            background:{p['scroll_hover']};
        }}
        #filterList QScrollBar::add-line:vertical, #filterList QScrollBar::sub-line:vertical{{
            height:0px;
            background:none;
        }}
        #filterList QScrollBar::add-page:vertical, #filterList QScrollBar::sub-page:vertical{{
            background:transparent;
        }}
        #filterList QScrollBar:horizontal{{
            background:transparent;
            height:8px;
            margin:0px 4px 2px 4px;
        }}
        #filterList QScrollBar::handle:horizontal{{
            background:{p['scroll']};
            border-radius:4px;
            min-width:40px;
        }}
        #filterList QScrollBar::handle:horizontal:hover{{
            background:{p['scroll_hover']};
        }}
        #filterList QScrollBar::add-line:horizontal, #filterList QScrollBar::sub-line:horizontal{{
            width:0px;
            background:none;
        }}
        #filterList QScrollBar::add-page:horizontal, #filterList QScrollBar::sub-page:horizontal{{
            background:transparent;
        }}
    """


# ----------------------------------------------------------------------------
# 任务卡片（纯白圆角条状 UI）
# ----------------------------------------------------------------------------
class TaskCard(QFrame):
    """单条任务卡片：纯白圆角矩形，含游戏图标、任务名、类型标签、截止、剩余、提醒、状态、操作。"""

    # 各任务类型的主题色：日常灰、周常蓝、双周常绿、月常橙、限时活动红
    TYPE_COLORS = {
        "日常": "#909399",
        "周常": "#409EFF",
        "双周常": "#67C23A",
        "月常": "#E6A23C",
        "限时活动": "#F56C6C",
    }

    def __init__(self, task, game, ui, parent=None):
        super().__init__(parent)
        self.task = task
        self.ui = ui
        self.setObjectName("taskCard")
        self.setAttribute(Qt.WA_StyledBackground, True)

        now = datetime.now()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)

        # 最左侧：游戏图标
        self.icon_w = IconWidget(icon_for_path(game.get("icon_path") if game else None))
        self.icon_w.setFixedSize(40, 40)
        self.icon_w.setObjectName("gameIcon")
        lay.addWidget(self.icon_w)

        # 任务名称（字体放大，背景透明避免色块；保证最小宽度，避免被截断）
        self.name_lbl = BodyLabel(task["task_name"])
        self.name_lbl.setMinimumWidth(140)
        lay.addWidget(self.name_lbl, 1)

        r_hour = cfg_get("refresh_hour", 4, int)
        r_min = cfg_get("refresh_min", 0, int)
        dl_str = models.to_game_time_str(task["deadline_dt"], r_hour, r_min)
        rem_str = models.remaining_str(task["deadline_dt"], now)

        # 右侧面板：类型 / 截止 / 剩余 / 状态。不固定宽度，随窗口压缩动态隐藏元素。
        right = QWidget()
        right.setObjectName("rightPanel")
        right.setStyleSheet("background:transparent;border:none;")
        rlay = QHBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(12)

        # 类型 / 截止 / 状态固定宽度靠右对齐：左起依次为类型、截止、剩余（动态）、状态。
        # 其中类型、截止、状态宽度固定，右侧面板整体靠右，保证这些元素到卡片右边缘的距离一致。

        # 类型标签（固定宽度 64、居中、按类型着色）—— 压缩优先级最低（最后才隐藏）
        self.type_tag = self._tag(task["task_type"])
        rlay.addWidget(self.type_tag)

        # 截止时间（固定宽度，文本格式稳定，靠右对齐时不跳动）
        self.kv_deadline = self._kv("截止", dl_str, fixed_width=96)
        rlay.addWidget(self.kv_deadline)

        # 剩余时间（固定宽度，容下常用剩余文本）
        self.kv_remain = self._kv("剩余", rem_str, fixed_width=86)
        rlay.addWidget(self.kv_remain)
        # 保存值标签引用，供 60 秒定时增量刷新剩余时间（避免全量重建卡片）
        self.remain_val_lbl = self.kv_remain.findChild(BodyLabel)

        # 状态标签（固定尺寸 54x22，灰=未完成，绿=已完成），单击切换
        self.status_lbl = QLabel("已完成" if task["completed"] else "未完成")
        self.status_lbl.setObjectName("statusTag")
        self.status_lbl.setFixedSize(54, 22)
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setCursor(Qt.PointingHandCursor)
        self._style_status(self.status_lbl, task["completed"])
        self.status_lbl.mousePressEvent = (
            lambda e, tid=task["id"], done=task["completed"]: self.ui.on_status(tid, not done)
        )
        rlay.addWidget(self.status_lbl)

        # 右侧面板整体靠右对齐：外层 lay 中 name_lbl 是 stretch 吸收空间，
        # 面板以 AlignRight 贴卡片右缘，保证各信息块到卡片右边缘的距离一致。
        lay.addWidget(right, alignment=Qt.AlignRight | Qt.AlignVCenter)

        # 右键菜单：编辑 / 删除
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._card_menu)

        self.apply_theme_style()

    # ----------------------------- 自适应压缩 -----------------------------
    def showEvent(self, e):
        super().showEvent(e)
        self._apply_compact()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_compact()

    def _apply_compact(self, w=None):
        """窗口变窄时按优先级依次隐藏元素：截止→剩余→图标→名称→状态→类型。

        w 为 None 时使用任务列表滚动区的实际可见宽度，避免被卡片 sizeHint 锁定
        导致空间判断错误。
        """
        if w is None:
            w = self.ui._compact_width() if hasattr(self.ui, "_compact_width") else self.width()
        # 各元素最小宽度（仅元素本身，不含间距），用于估算可用空间
        item_w = {
            "icon": 40,
            "name": 140,
            "type": 64,
            "deadline": 96,
            "remain": 86,
            "status": 54,
        }
        spacing = 14   # lay.setSpacing(14)，元素间的间距
        margins = 32   # 卡片左右内边距 16*2
        # 可用空间 = 卡片宽度 - 左右内边距
        avail = w - margins
        # 压缩（隐藏）顺序：越靠前越先被隐藏
        hide_order = ["deadline", "remain", "icon", "name", "status", "type"]
        shown = set(item_w.keys())

        def needed():
            """全部可见元素 + 它们之间的 spacing 之和。"""
            if not shown:
                return 0
            n = len(shown)
            # 元素自身宽度总和 + (n-1) 个元素间间距
            return sum(item_w[k] for k in shown) + spacing * (n - 1)

        while needed() > avail and hide_order:
            shown.discard(hide_order.pop(0))

        self.icon_w.setVisible("icon" in shown)
        self.name_lbl.setVisible("name" in shown)
        self.type_tag.setVisible("type" in shown)
        self.kv_deadline.setVisible("deadline" in shown)
        self.kv_remain.setVisible("remain" in shown)
        self.status_lbl.setVisible("status" in shown)

    def _tag(self, text):
        color = self.TYPE_COLORS.get(text, "#606266")
        lbl = QLabel(text)
        # 固定宽高，保证不同任务类型、不同压缩状态下类型标签大小恒定
        lbl.setFixedSize(64, 36)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"QLabel{{background:{color};color:#FFFFFF;border-radius:7px;"
            f"padding:0;font-size:13px;font-weight:600;}}"
        )
        return lbl

    def _style_status(self, lbl, completed):
        color = "#67C23A" if completed else "#C0C4CC"
        hover = "#85CE61" if completed else "#909399"
        lbl.setStyleSheet(
            f"#statusTag{{background:{color};color:#FFFFFF;border-radius:5px;"
            f"padding:1px 0;font-size:11px;font-weight:600;}}"
            f"#statusTag:hover{{background:{hover};}}"
        )

    def _kv(self, key, val, fixed_width=None):
        w = QWidget()
        w.setObjectName("kv")
        # 容器本身无背景，依赖外层卡片；标签全部透明避免色块
        w.setStyleSheet("background:transparent;border:none;")
        v = QVBoxLayout(w)
        v.setContentsMargins(2, 0, 2, 0)
        v.setSpacing(3)
        k = CaptionLabel(key)
        val_lbl = BodyLabel(val)
        v.addWidget(k)
        v.addWidget(val_lbl)
        # 可选固定宽度：让截止时间等信息块宽度稳定，便于靠右对齐
        if fixed_width:
            w.setFixedWidth(fixed_width)
        return w

    # ----------------------------- 增量刷新 -----------------------------
    def update_remaining(self, now=None):
        """60 秒定时调用：仅更新剩余时间文本与警告状态，避免全量重建卡片。

        完成状态由 refresh_table 全量重建时决定；这里只负责时间相关的即时刷新。
        """
        now = now or datetime.now()
        if self.task["completed"]:
            # 已完成：无需刷新时间/警告
            return
        rem = models.remaining_str(self.task["deadline_dt"], now)
        self.remain_val_lbl.setText(rem)
        # 警告状态变化时才重绘整卡（避免每次都全卡重绘）
        warn = models.is_red_warning(self.task["task_type"], self.task["deadline_dt"], now)
        if warn != getattr(self, "_last_warn", None):
            self._last_warn = warn
            self.apply_theme_style()

    # ----------------------------- 主题样式 -----------------------------
    def apply_theme_style(self):
        """根据当前主题重绘卡片配色（创建时与父界面切换主题时调用）。"""
        p = theme_palette()
        now = datetime.now()
        warn = models.is_red_warning(
            self.task["task_type"], self.task["deadline_dt"], now
        ) and not self.task["completed"]

        self.setStyleSheet(f"""
            #taskCard {{
                background:{p['card_bg_warn'] if warn else p['card_bg']};
                border-radius:12px;
                border:{p['card_border']};
                {'border-left:4px solid #F56C6C;' if warn else 'border-left:4px solid transparent;'}
            }}
            #taskCard:hover {{ border-color:{p['hover_border']}; }}
        """)
        self.icon_w.setStyleSheet(f"#gameIcon{{border-radius:8px;background:{p['icon_bg']};}}")
        self.name_lbl.setStyleSheet(
            f"font-weight:600;color:{p['name']};font-size:17px;background:transparent;"
        )
        for kv in (self.kv_deadline, self.kv_remain):
            if kv is None:
                continue
            kv.findChild(CaptionLabel).setStyleSheet(
                f"color:{p['kv_key']};font-size:11px;background:transparent;"
            )
            val_lbl = kv.findChild(BodyLabel)
            if kv is self.kv_remain and warn:
                val_lbl.setStyleSheet(
                    "color:#F56C6C;font-weight:600;font-size:13px;background:transparent;"
                )
            else:
                val_lbl.setStyleSheet(
                    f"color:{p['kv_val']};font-size:13px;background:transparent;"
                )

    def mouseDoubleClickEvent(self, e):
        self.ui.on_status(self.task["id"], not self.task["completed"])
        super().mouseDoubleClickEvent(e)

    def _card_menu(self, pos):
        menu = themed_menu(self)
        menu.addAction(qf.FluentIcon.EDIT.icon(), "编辑", lambda: self.ui.edit_task(self.task["id"]))
        menu.addAction(qf.FluentIcon.DELETE.icon(), "删除", lambda: self.ui.delete_task(self.task["id"]))
        menu.exec_(self.mapToGlobal(pos))


# ----------------------------------------------------------------------------
# 任务主界面
# ----------------------------------------------------------------------------
class TaskInterface(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.setObjectName("TaskInterface")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.game_checked = {}
        self._last_remind = set()
        # 去重集合清理锚点：记录当前周键，跨周后清空旧 key，防止长期运行内存增长
        self._remind_week_key = datetime.now().strftime("%Y-W%W")

        self._build_ui()
        self.apply_theme_style()
        self.refresh_all()

    # ----------------------------- 窗口大小监听 -----------------------------
    def resizeEvent(self, e):
        """任务列表大小变化时，强制刷新所有卡片的紧凑布局。

        TaskCard 自身的 resizeEvent 只在卡片宽度变化时触发；当父容器尺寸变化
        导致滚动区宽度变化而卡片宽度未变时，这里兜底重新调用 _apply_compact。
        """
        super().resizeEvent(e)
        if not hasattr(self, "task_layout"):
            return
        # 用 available 宽度（滚动区可见宽）作为卡片的目标宽度
        avail_w = self._compact_width()
        for i in range(self.task_layout.count()):
            item = self.task_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, TaskCard):
                w._apply_compact(avail_w)

    # ----------------------------- UI 构建 -----------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 16, 16, 16)
        root.setSpacing(12)

        # 顶部工具栏
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(TitleLabel("任务清单"))
        bar.addSpacing(8)
        self.count_label = CaptionLabel("")
        self.count_label.setStyleSheet("color:#909399;")
        bar.addWidget(self.count_label)
        bar.addStretch(1)

        for icon, text, slot in (
            (FluentIcon.ADD, "添加任务", self.open_add_task),
            (FluentIcon.PEOPLE, "游戏管理", self.open_game_manage),
            (FluentIcon.SYNC, "刷新", self.refresh_all),
        ):
            btn = PushButton(icon, text)
            btn.setFixedHeight(34)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        root.addLayout(bar)

        # 主分割：左筛选 | 右任务表
        self.main_split = QSplitter(Qt.Horizontal)
        self.main_split.setHandleWidth(16)

        # 左侧纵向分割：游戏筛选 + 任务类型
        self.left_split = QSplitter(Qt.Vertical)
        self.left_split.setHandleWidth(14)
        self.left_split.addWidget(self._make_card("游戏筛选", self._build_game_list()))
        self.left_split.addWidget(self._make_card("任务类型", self._build_type_list()))

        self.main_split.addWidget(self.left_split)
        self.main_split.addWidget(self._build_table_area())

        # 折叠/展开栏：常驻左侧、紧贴导航栏，单击收起/展开筛选面板
        self._filter_collapsed = False
        self._saved_split_sizes = None
        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.collapse_bar = self._make_collapse_bar()
        outer.addWidget(self.collapse_bar)
        outer.addWidget(self.main_split, 1)
        root.addLayout(outer, 1)

    def _make_card(self, title, widget):
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        t = BodyLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setObjectName("cardTitle")
        lay.addWidget(t)
        lay.addWidget(widget, 1)
        return card

    def _build_game_list(self):
        self.game_list = QListWidget()
        self.game_list.setObjectName("filterList")
        self.game_list.setStyleSheet(filter_list_qss(theme_palette()))
        self.game_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.game_list.customContextMenuRequested.connect(self._game_menu)
        self.game_list.itemClicked.connect(self._on_game_clicked)
        return self.game_list

    def _build_type_list(self):
        self.type_list = QListWidget()
        self.type_list.setObjectName("filterList")
        self.type_list.setStyleSheet(filter_list_qss(theme_palette()))
        self.type_list.itemClicked.connect(self._on_type_clicked)
        for t in models.TASK_TYPES:
            it = QListWidgetItem(t)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            self.type_list.addItem(it)
        return self.type_list

    def _build_table_area(self):
        area = QWidget()
        area.setObjectName("tableArea")
        v = QVBoxLayout(area)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.task_container = QWidget()
        self.task_container.setObjectName("taskContainer")
        self.task_layout = QVBoxLayout(self.task_container)
        self.task_layout.setContentsMargins(4, 4, 4, 4)
        self.task_layout.setSpacing(10)
        self.task_layout.addStretch(1)
        self.scroll.setWidget(self.task_container)
        v.addWidget(self.scroll, 1)

        self.hint = CaptionLabel("暂无任务，点击「添加任务」开始")
        self.hint.setStyleSheet("color:#C0C4CC;font-size:14px;")
        self.hint.setAlignment(Qt.AlignCenter)
        v.addWidget(self.hint)
        return area

    # ----------------------------- 主题样式 -----------------------------
    def apply_theme_style(self):
        """根据当前主题刷新背景、卡片、筛选列表与滚动条配色。"""
        p = theme_palette()
        # 主界面背景与深色导航一致（深色 #202020 / 浅色 #EEF0F3）
        self.setStyleSheet(f"background:{p['bg']};")
        # 滚动区透明，滚动条用主题色
        self.scroll.setStyleSheet(f"""
            QScrollArea{{background:transparent;border:none;}}
            QScrollBar:vertical{{
                background:transparent;
                width:8px;
                margin:4px 2px 4px 0px;
            }}
            QScrollBar::handle:vertical{{
                background:{p['scroll']};
                border-radius:4px;
                min-height:40px;
            }}
            QScrollBar::handle:vertical:hover{{
                background:{p['scroll_hover']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical{{
                height:0px;
                background:none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical{{
                background:transparent;
            }}
        """)
        self.task_container.setStyleSheet("background:transparent;")
        # 已存在的任务卡片立即跟随主题重绘（避免切主题后白色卡片滞留到下次刷新）
        for i in range(self.task_layout.count()):
            item = self.task_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, TaskCard):
                w.apply_theme_style()
        # 左侧筛选卡片 + 标题
        for i in range(self.left_split.count()):
            card = self.left_split.widget(i)
            card.setStyleSheet(
                f"#card{{background:{p['card_bg']};border-radius:8px;"
                f"border:{p['card_border']};}}"
            )
            title = card.findChild(QLabel, "cardTitle")
            if title:
                title.setStyleSheet(
                    f"font-weight:600;color:{p['title']};font-size:15px;"
                    f"background:transparent;padding:2px 0;"
                )
        # 筛选列表（文本背景透明，滚动条主题色）
        self.game_list.setStyleSheet(filter_list_qss(p))
        self.type_list.setStyleSheet(filter_list_qss(p))
        self.count_label.setStyleSheet(f"color:{p['count']};")
        # 游戏筛选 / 任务类型 之间的分隔与主 UI 背景同色（横线融入背景不可见）
        self.left_split.setStyleSheet(
            f"QSplitter::handle:vertical{{background:{p['bg']};border-radius:6px;margin:4px 22px;}}"
        )
        # 折叠栏外观
        self.collapse_bar.setStyleSheet(
            f"#collapseBar{{background:{p['card_bg']};border:{p['card_border']};"
            f"border-top-right-radius:8px;border-bottom-right-radius:8px;}}"
        )
        self.collapse_btn.setStyleSheet(
            f"#collapseBtn{{background:transparent;border:none;}}"
            f"#collapseBtn:hover{{background:{p['icon_bg']};border-radius:6px;}}"
        )

    # ----------------------------- 折叠栏 -----------------------------
    def _chevron(self, left=False):
        """右侧箭头图标；left=True 时水平翻转成指向左。"""
        ic = FluentIcon.CHEVRON_RIGHT.icon()
        if not left:
            return ic
        pm = ic.pixmap(16, 16)
        pm = pm.transformed(QTransform().scale(-1, 1))
        return QIcon(pm)

    def _make_collapse_bar(self):
        bar = QFrame()
        bar.setObjectName("collapseBar")
        bar.setFixedWidth(14)
        v = QVBoxLayout(bar)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addStretch(1)
        btn = ToolButton(FluentIcon.CHEVRON_RIGHT)
        btn.setObjectName("collapseBtn")
        btn.setFixedSize(14, 40)
        # 让整条 bar 可点击：按钮不拦截鼠标事件，由 bar 统一处理
        btn.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        v.addWidget(btn, alignment=Qt.AlignCenter)
        v.addStretch(1)
        self.collapse_btn = btn
        bar.mousePressEvent = lambda e: self._toggle_filter_panel()
        bar.setCursor(Qt.PointingHandCursor)
        self.collapse_bar = bar
        self._update_collapse_btn()
        return bar

    def _toggle_filter_panel(self):
        self._filter_collapsed = not self._filter_collapsed
        if self._filter_collapsed:
            self._saved_split_sizes = self.main_split.sizes()
            self.left_split.setVisible(False)
            self.main_split.handle(1).setVisible(False)
        else:
            self.left_split.setVisible(True)
            self.main_split.handle(1).setVisible(True)
            if self._saved_split_sizes:
                self.main_split.setSizes(self._saved_split_sizes)
        self._update_collapse_btn()
        # 筛选栏折叠/展开导致右侧任务区宽度变化，重新压缩所有任务卡片
        QTimer.singleShot(0, self._refresh_cards_compact)

    def _update_collapse_btn(self):
        if self._filter_collapsed:
            # 收起状态：箭头指向右，提示“点击展开”
            self.collapse_btn.setIcon(self._chevron(left=False))
            self.collapse_bar.setToolTip("展开筛选")
        else:
            # 展开状态：箭头指向左，提示“点击收起”
            self.collapse_btn.setIcon(self._chevron(left=True))
            self.collapse_bar.setToolTip("收起筛选")

    # ----------------------------- 筛选状态 -----------------------------
    def _on_game_clicked(self, item):
        # 单个游戏勾选切换：取消勾选即隐藏该游戏任务
        self.game_checked[item.text()] = item.checkState() == Qt.Checked
        self.refresh_table()

    def _on_type_clicked(self, item):
        self.refresh_table()

    def _active_game_ids(self):
        games = database.get_games()
        if not games:
            return None
        ids = [g["id"] for g in games if self.game_checked.get(g["name"], True)]
        # 全部勾选（或均未记录）则视为显示全部
        if len(ids) == len(games):
            return None
        return ids

    def _active_types(self):
        checked = []
        for i in range(self.type_list.count()):
            it = self.type_list.item(i)
            if it.checkState() == Qt.Checked:
                checked.append(it.text())
        if len(checked) == self.type_list.count():
            return None
        return checked

    # ----------------------------- 刷新 -----------------------------
    def refresh_all(self):
        self.refresh_game_filter()
        self.refresh_table()

    def refresh_game_filter(self):
        self.game_list.clear()
        for g in database.get_games():
            # 补全 game_checked，保证筛选状态完整一致
            on = self.game_checked.get(g["name"], True)
            self.game_checked[g["name"]] = on
            it = QListWidgetItem(icon_for_path(g["icon_path"]), g["name"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if on else Qt.Unchecked)
            self.game_list.addItem(it)

    def refresh_table(self):
        database.auto_update_all()
        now = datetime.now()

        types = self._active_types()
        gids = self._active_game_ids()
        tasks = database.get_tasks(None if gids is None else set(gids),
                                   None if types is None else set(types))

        games_by_id = {g["id"]: g for g in database.get_games()}

        def sort_key(t):
            # 三级排序：① 标红(红警)未完成任务置顶 ② 其余未完成按剩余时间升序
            #          ③ 已完成沉底。标红内部同样按剩余时间升序（最紧急在最上）。
            rem = (t["deadline_dt"] - now).total_seconds()
            if t["completed"]:
                return (2, 1e18)
            if models.is_red_warning(t["task_type"], t["deadline_dt"], now):
                return (0, rem)
            return (1, rem)
        tasks.sort(key=sort_key)

        # 清空旧卡片后重建（末尾保留 stretch）
        while self.task_layout.count():
            item = self.task_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for t in tasks:
            g = games_by_id.get(t["game_id"])
            self.task_layout.addWidget(TaskCard(t, g, self))
        self.task_layout.addStretch(1)

        self.hint.setVisible(len(tasks) == 0)
        incomplete = sum(1 for t in tasks if not t["completed"])
        self.count_label.setText(f"未完成 {incomplete} / 共 {len(tasks)}")
        self.main.update_title(incomplete)

    def refresh_remaining(self):
        """60 秒定时增量刷新：只更新现有卡片的剩余时间与警告状态，不重建卡片。

        任务完成状态变更仍需全量重建（由 on_status 触发），这里不处理。
        """
        now = datetime.now()
        for i in range(self.task_layout.count()):
            item = self.task_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, TaskCard):
                w.update_remaining(now)

    def _compact_width(self):
        """任务卡片可用的实际宽度：滚动区可见宽度（而非卡片 sizeHint 宽度）。"""
        if hasattr(self, "scroll"):
            return self.scroll.viewport().width()
        return self.width()

    def _refresh_cards_compact(self):
        """让所有任务卡片按当前可见宽度重新压缩。

        在启动（窗口显示后）与筛选栏折叠/展开（右侧任务区宽度变化）时调用，
        确保卡片的隐藏状态始终与当前宽度匹配。
        """
        avail_w = self._compact_width()
        for i in range(self.task_layout.count()):
            item = self.task_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, TaskCard):
                w._apply_compact(avail_w)

    # ----------------------------- 交互 -----------------------------
    def on_status(self, tid, completed):
        database.set_completed(tid, completed)
        # 限时活动：标记为完成后若已过期，自动删除
        t = database.get_task(tid)
        if t and t["task_type"] == "限时活动" and completed and t["deadline_dt"] <= datetime.now():
            database.delete_task(tid)
            InfoBar.success(
                "限时任务已过期并完成", f"已自动删除「{t['task_name']}」",
                parent=self, position=InfoBarPosition.TOP_RIGHT, duration=3000,
            )
        self.refresh_table()

    def edit_task(self, tid):
        t = database.get_task(tid)
        if not t:
            return
        dlg = AddTaskDialog(self, t)
        if dlg.exec_() == QDialog.Accepted:
            database.update_task(
                tid, dlg.result_game_id, dlg.result_name, dlg.result_type,
                dlg.result_deadline, dlg.result_rule
            )
            database.auto_update_task(tid)
            self.refresh_all()

    def delete_task(self, tid):
        if confirm(self, "删除任务", "确定删除该任务？"):
            database.delete_task(tid)
            self.refresh_all()

    def _game_menu(self, pos):
        it = self.game_list.itemAt(pos)
        if not it:
            return
        name = it.text()
        g = next((x for x in database.get_games() if x["name"] == name), None)
        if not g:
            return
        menu = themed_menu(self)
        menu.addAction(qf.FluentIcon.EDIT.icon(), "重命名 / 修改图标",
                      lambda: self._edit_game(g))
        menu.addAction(qf.FluentIcon.SYNC.icon(), "重新加载程序图标",
                      lambda: self.refresh_all())
        menu.addAction(qf.FluentIcon.ADD.icon(), "添加任务(自定义)",
                      lambda: self.open_add_task(g["id"], None))
        menu.addAction(qf.FluentIcon.ADD.icon(), "一键添加日常",
                      lambda: self.open_add_task(g["id"], "日常"))
        menu.addAction(qf.FluentIcon.ADD.icon(), "一键添加周常",
                      lambda: self.open_add_task(g["id"], "周常"))
        menu.addAction(qf.FluentIcon.DELETE.icon(), "删除游戏",
                      lambda: self._delete_game(g))
        menu.exec_(self.game_list.mapToGlobal(pos))

    def _edit_game(self, g):
        dlg = AddGameDialog(self, g)
        if dlg.exec_() == QDialog.Accepted:
            if not database.update_game(g["id"], dlg.result_name, dlg.result_icon):
                InfoBar.warning("该游戏名称已存在", "请更换名称", parent=self)
                return
            self.refresh_all()

    def _delete_game(self, g):
        if confirm(self, "删除游戏", f"删除「{g['name']}」将同时删除其下所有任务，确定？"):
            database.delete_game(g["id"])
            self.refresh_all()

    # ----------------------------- 动作 -----------------------------
    def open_add_task(self, game_id=None, preset_type=None):
        dlg = AddTaskDialog(self, None, preset_game_id=game_id, preset_type=preset_type)
        if dlg.exec_() == QDialog.Accepted:
            database.add_task(
                dlg.result_game_id, dlg.result_name, dlg.result_type,
                dlg.result_deadline, dlg.result_rule
            )
            self.refresh_all()

    def open_game_manage(self):
        dlg = GameManageDialog(self)
        dlg.exec_()


# ----------------------------------------------------------------------------
# 提醒子界面（tag 页面）
# ----------------------------------------------------------------------------
class RemindInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RemindInterface")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background:{theme_palette()['bg']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        root.addWidget(TitleLabel("提醒设置"))

        top = QHBoxLayout()
        self.type_combo = ComboBox()
        self.type_combo.addItems(["每日", "每周", "每月"])
        self.game_combo = ComboBox()
        self.game_combo.addItem("全部游戏")
        for g in database.get_games():
            self.game_combo.addItem(g["name"])
        self.kind_combo = ComboBox()
        self.kind_combo.addItems(["全部类型"] + models.TASK_TYPES)
        top.addWidget(BodyLabel("类型"))
        top.addWidget(self.type_combo)
        top.addWidget(BodyLabel("游戏"))
        top.addWidget(self.game_combo)
        top.addWidget(BodyLabel("任务类型"))
        top.addWidget(self.kind_combo)
        top.addStretch(1)
        root.addLayout(top)

        bottom = QHBoxLayout()
        self.hour_spin = SpinBox()
        self.hour_spin.setRange(0, 23)
        self.hour_spin.setValue(8)
        self.min_spin = SpinBox()
        self.min_spin.setRange(0, 59)
        self.min_spin.setValue(0)
        add_btn = PrimaryPushButton("添加规则")
        add_btn.clicked.connect(self._add_rule)
        bottom.addWidget(BodyLabel("时间"))
        bottom.addWidget(self.hour_spin)
        bottom.addWidget(BodyLabel("时"))
        bottom.addWidget(self.min_spin)
        bottom.addWidget(BodyLabel("分"))
        bottom.addWidget(add_btn)
        bottom.addStretch(1)
        root.addLayout(bottom)

        self.list = QListWidget()
        self.list.setObjectName("filterList")
        self.list.setStyleSheet(self._list_qss(theme_palette()))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemDoubleClicked.connect(self._toggle)
        root.addWidget(self.list, 1)

        self.refresh()

    def _refresh_game_combo(self):
        """在保持当前选择（若存在）的前提下刷新游戏下拉项。"""
        cur = self.game_combo.currentText()
        self.game_combo.clear()
        self.game_combo.addItem("全部游戏")
        for g in database.get_games():
            self.game_combo.addItem(g["name"])
        idx = self.game_combo.findText(cur)
        if idx >= 0:
            self.game_combo.setCurrentIndex(idx)

    def _sel_game_id(self):
        name = self.game_combo.currentText()
        if name == "全部游戏" or not name:
            return -1
        g = database.find_game_by_name(name)
        return g["id"] if g else -1

    @staticmethod
    def _rule_game_name(rule):
        gid = rule.get("game_id", -1)
        if gid is None or gid == -1:
            return ""
        g = database.get_game(gid)
        return g["name"] if g else ""

    def showEvent(self, e):
        """每次切换到提醒页时兜底同步游戏下拉框与规则列表。

        游戏在「游戏管理」中新增/重命名/删除后不会主动通知提醒页，
        这里在页面显示时刷新，保证下拉框与规则列表始终与数据库一致。
        """
        super().showEvent(e)
        if hasattr(self, "game_combo"):
            self.refresh()

    def refresh(self):
        self._refresh_game_combo()
        self.list.clear()
        for r in database.get_remind_rules():
            enabled = bool(r["enabled"])
            gid = r.get("game_id", -1)
            gname = "全部游戏"
            if gid not in (None, -1):
                g = database.get_game(gid)
                if g:
                    gname = g["name"]
            ttype = r.get("task_type", "") or "全部类型"
            label = (
                f"{r['rule_type']} {r['time']} {gname} {ttype}"
                f"  [{'已启用' if enabled else '已停用'}]"
            )
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, r["id"])
            if not enabled:
                it.setForeground(Qt.gray)
            self.list.addItem(it)

    def _add_rule(self):
        rtype = self.type_combo.currentText()
        t = f"{self.hour_spin.value():02d}:{self.min_spin.value():02d}"
        if database.count_remind_rules() >= 10:
            InfoBar.warning("最多 10 条提醒规则", "", parent=self)
            return
        game_id = self._sel_game_id()
        ttype = self.kind_combo.currentText()
        ttype = "" if ttype == "全部类型" else ttype
        database.add_remind_rule(rtype, t, True, game_id, ttype)
        self.refresh()

    def _menu(self, pos):
        it = self.list.itemAt(pos)
        if not it:
            return
        rid = it.data(Qt.UserRole)
        menu = themed_menu(self)
        menu.addAction("启用 / 停用", lambda: self._toggle(it))
        menu.addAction(qf.FluentIcon.DELETE.icon(), "删除", lambda: self._delete(rid))
        menu.exec_(self.list.mapToGlobal(pos))

    def _toggle(self, it):
        rid = it.data(Qt.UserRole)
        r = next((x for x in database.get_remind_rules() if x["id"] == rid), None)
        if not r:
            return
        database.update_remind_rule(
            rid, r["rule_type"], r["time"], not bool(r["enabled"]),
            r.get("game_id", -1), r.get("task_type", ""),
        )
        self.refresh()

    def _delete(self, rid):
        database.delete_remind_rule(rid)
        self.refresh()

    # ----------------------------- 主题样式 -----------------------------
    @staticmethod
    def _list_qss(p):
        return f"""
            #filterList{{
                background:{p['card_bg']};border:none;border-radius:10px;outline:none;
                padding:4px;
            }}
            #filterList::item{{border-radius:6px;background:transparent;}}
            #filterList::item:selected{{background:rgba(64,158,255,0.10);color:#409EFF;}}
        """

    def apply_theme_style(self):
        p = theme_palette()
        self.setStyleSheet(f"background:{p['bg']};")
        self.list.setStyleSheet(self._list_qss(p))


# ----------------------------------------------------------------------------
# 设置子界面（tag 页面）
# ----------------------------------------------------------------------------
class SettingsInterface(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsInterface")
        self.main = main_window
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background:{theme_palette()['bg']};")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        root.addWidget(TitleLabel("设置"))

        form = QFormLayout()
        form.setSpacing(12)
        self.rh = SpinBox(); self.rh.setRange(0, 28); self.rh.setValue(cfg_get("refresh_hour", 4, int))
        self.rm = SpinBox(); self.rm.setRange(0, 59); self.rm.setValue(cfg_get("refresh_min", 0, int))
        rh_row = QHBoxLayout()
        rh_row.addWidget(self.rh); rh_row.addWidget(BodyLabel("时"))
        rh_row.addWidget(self.rm); rh_row.addWidget(BodyLabel("分"))
        form.addRow("全局刷新时刻", rh_row)

        self.close_combo = ComboBox()
        self.close_combo.addItems(["最小化到托盘", "直接退出"])
        self.close_combo.setCurrentIndex(0 if cfg_get("close_action", "minimize") == "minimize" else 1)
        form.addRow("关闭窗口时", self.close_combo)

        self.remember_cb = CheckBox("记住我的选择")
        self.remember_cb.setChecked(bool(cfg_get("remember_close", False)))
        form.addRow("", self.remember_cb)

        self.theme_combo = ComboBox()
        self.theme_combo.addItems(["浅色", "深色"])
        self.theme_combo.setCurrentIndex(0 if cfg_get("theme", "light") == "light" else 1)
        form.addRow("主题", self.theme_combo)
        root.addLayout(form)

        from PyQt5.QtWidgets import QSizePolicy
        expanding = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        open_dir = PushButton("打开数据目录")
        open_dir.clicked.connect(self._open_dir)
        open_dir.setSizePolicy(expanding)
        root.addWidget(open_dir)

        io_row = QHBoxLayout()
        export_btn = PushButton("导出 JSON")
        export_btn.clicked.connect(self._export)
        import_btn = PushButton("导入 JSON")
        import_btn.clicked.connect(self._import)
        export_btn.setSizePolicy(expanding)
        import_btn.setSizePolicy(expanding)
        io_row.addWidget(export_btn, 1)
        io_row.addWidget(import_btn, 1)
        root.addLayout(io_row)

        save_btn = PrimaryPushButton("保存设置")
        save_btn.clicked.connect(self._save)
        save_btn.setSizePolicy(expanding)
        root.addWidget(save_btn)
        root.addStretch(1)

        self.apply_theme_style()

        # 任意控件变动即自动保存并生效（初始化在 connect 之前完成，故不会误触发）
        self.rh.editingFinished.connect(lambda: self.auto_save())
        self.rm.editingFinished.connect(lambda: self.auto_save())
        self.close_combo.currentIndexChanged.connect(lambda: self.auto_save())
        self.remember_cb.stateChanged.connect(lambda: self.auto_save())
        self.theme_combo.currentIndexChanged.connect(lambda: self.auto_save())

    # ----------------------------- 主题样式 -----------------------------
    def apply_theme_style(self):
        """深色模式下将所有文字改为白色，浅色模式恢复默认。"""
        from PyQt5.QtWidgets import QComboBox, QSpinBox
        p = theme_palette()
        self.setStyleSheet(f"background:{p['bg']};")
        # 遍历所有标签：标题用 title 色并放大，其余用 name（深色=白）色
        for w in self.findChildren(QLabel):
            # 跳过位于 ComboBox / SpinBox 内部的文本标签（由其自身管理）
            if isinstance(w.parent(), (qf.ComboBox, qf.SpinBox, QComboBox, QSpinBox)):
                continue
            if isinstance(w, TitleLabel):
                w.setStyleSheet(
                    f"color:{p['title']};font-size:23px;font-weight:600;background:transparent;"
                )
            else:
                w.setStyleSheet(f"color:{p['name']};background:transparent;")
        # 勾选框文字
        for cb in self.findChildren(CheckBox):
            cb.setStyleSheet(f"color:{p['name']};background:transparent;")

    def _open_dir(self):
        import subprocess
        subprocess.Popen(["explorer", database._base_dir()])

    def _export(self):
        from PyQt5.QtWidgets import QFileDialog
        import json as _json
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 JSON", os.path.join(database._base_dir(), "game_tasks.json"),
            "JSON 文件 (*.json)"
        )
        if not path:
            return
        data = database.export_json()
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
        InfoBar.success("已导出", os.path.basename(path), parent=self,
                       position=InfoBarPosition.TOP_RIGHT, duration=3000)

    def _import(self):
        from PyQt5.QtWidgets import QFileDialog
        import json as _json
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 JSON", database._base_dir(), "JSON 文件 (*.json)"
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        backup = os.path.join(database._base_dir(), "game_tasks.backup.json")
        with open(backup, "w", encoding="utf-8") as f:
            _json.dump(database.export_json(), f, ensure_ascii=False, indent=2)
        database.import_json(data)
        if self.main is not None and hasattr(self.main, "task_ui"):
            self.main.task_ui.refresh_all()
        InfoBar.success("已导入", f"已自动备份至 {os.path.basename(backup)}",
                       parent=self, position=InfoBarPosition.TOP_RIGHT, duration=4000)

    def auto_save(self, show_tip=False):
        """保存并立即生效（任何控件变动都会调用，show_tip 控制是否弹提示）。"""
        theme = "light" if self.theme_combo.currentIndex() == 0 else "dark"
        cfg_set("refresh_hour", self.rh.value())
        cfg_set("refresh_min", self.rm.value())
        cfg_set("close_action", "minimize" if self.close_combo.currentIndex() == 0 else "exit")
        cfg_set("remember_close", self.remember_cb.isChecked())
        cfg_set("theme", theme)
        setTheme(Theme.LIGHT if theme == "light" else Theme.DARK)
        self.main._style_nav()
        if show_tip:
            InfoBar.success("已保存", "设置已生效", parent=self,
                           position=InfoBarPosition.TOP_RIGHT, duration=2500)

    def _save(self):
        self.auto_save(show_tip=True)


# ----------------------------------------------------------------------------
# 关于页面（tag 页面，替代原弹窗）
# ----------------------------------------------------------------------------
class AboutInterface(QWidget):
    GITHUB_URL = "https://github.com/jasenwdhGit/Gacha_Game_Quest_Helper"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AboutInterface")
        v = QVBoxLayout(self)
        v.setContentsMargins(40, 40, 40, 40)
        v.setAlignment(Qt.AlignTop)

        icon = IconWidget(FluentIcon.GAME.icon())
        icon.setFixedSize(64, 64)
        v.addWidget(icon, alignment=Qt.AlignCenter)

        v.addWidget(TitleLabel("手游任务助手 Gacha Game Quest Helper"),
                    alignment=Qt.AlignCenter)
        v.addWidget(BodyLabel("v2.0.0"), alignment=Qt.AlignCenter)
        v.addWidget(BodyLabel("QFluentWidgets 重构版 · 本地 SQLite 存储"),
                    alignment=Qt.AlignCenter)
        v.addWidget(CaptionLabel("支持 db / json 兼容 · 28 小时制游戏时间 · 周期自动重置"),
                    alignment=Qt.AlignCenter)

        v.addSpacing(14)
        # 28 小时制游戏时间说明
        v.addWidget(BodyLabel("关于 28 小时制游戏时间"), alignment=Qt.AlignCenter)
        game_time_note = (
            "以「全局刷新点 R」（默认 4:00）为界，将真实时间换算为游戏时间显示：\n"
            "· 真实小时 < R：游戏日期减 1 天，游戏小时 = 真实小时 + 24（如 3:00 → 前一日 27:00）\n"
            "· 真实小时 = R：游戏日期减 1 天，游戏小时 = R + 24（如 4:00 → 前一日 28:00）\n"
            "· 真实小时 > R：游戏日期不变，游戏小时 = 真实小时（如 8:00 → 当日 8:00）\n"
            "限时活动截止可输入 0~28 小时，≥24 表示次日对应时刻。"
        )
        note_lbl = CaptionLabel(game_time_note)
        note_lbl.setWordWrap(True)
        note_lbl.setStyleSheet(
            "color:#909399;font-size:13px;background:transparent;line-height:1.6;"
        )
        note_lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(note_lbl)
        v.addSpacing(14)

        v.addWidget(BodyLabel("开源项目地址："), alignment=Qt.AlignCenter)
        link = HyperlinkButton(self.GITHUB_URL, self.GITHUB_URL, self)
        link.setFixedWidth(440)
        v.addWidget(link, alignment=Qt.AlignCenter)

        v.addStretch(1)

        self.apply_theme_style()

    # ----------------------------- 主题样式 -----------------------------
    def apply_theme_style(self):
        p = theme_palette()
        self.setStyleSheet(f"background:{p['bg']};")
        for w in self.findChildren(QLabel):
            if isinstance(w, TitleLabel):
                w.setStyleSheet(
                    f"color:{p['title']};font-size:23px;font-weight:600;background:transparent;"
                )
            else:
                w.setStyleSheet(f"color:{p['name']};background:transparent;")


# ----------------------------------------------------------------------------
# 主窗口
# ----------------------------------------------------------------------------
class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("手游任务助手 Gacha Game Quest Helper")
        self.resize(1120, 720)
        # 最小尺寸：保证右侧任务列表与左侧筛选栏可用，避免卡片元素全部被压缩隐藏
        self.setMinimumSize(720, 480)
        database.init_db()
        database.auto_update_all()

        theme = cfg_get("theme", "light")
        setTheme(Theme.DARK if theme == "dark" else Theme.LIGHT)
        setThemeColor("#2F7DCD")

        self.task_ui = TaskInterface(self)
        self.addSubInterface(self.task_ui, FluentIcon.GAME, "任务", NavigationItemPosition.TOP)

        # “提醒”放置在“任务”下方的导航栏区域（tag 页面切换）
        self.remind_ui = RemindInterface(self)
        self.addSubInterface(self.remind_ui, AppIcon.ALARM, "提醒", NavigationItemPosition.TOP)

        # “设置”切换为 tag 页面
        self.settings_ui = SettingsInterface(self, self)
        self.addSubInterface(self.settings_ui, FluentIcon.SETTING, "设置", NavigationItemPosition.BOTTOM)

        # “关于”也切换为 tag 页面
        self.about_ui = AboutInterface(self)
        self.addSubInterface(self.about_ui, FluentIcon.INFO, "关于", NavigationItemPosition.BOTTOM)

        self._init_tray()
        self._init_timer()

        # 恢复布局 / 折叠状态 / 窗口尺寸
        self._restore_splitters()
        self._restore_filter_state()
        self._restore_window()

        # 导航栏：展开宽度减半 + 放大图标与文字
        self.navigationInterface.setExpandWidth(160)
        self._style_nav()

    # ----------------------------- 导航栏样式 -----------------------------
    def _style_nav(self):
        nav_font = QFont("Microsoft YaHei UI", _NAV_FONT_SIZE)
        nav_font.setBold(False)
        nav_font.setWeight(QFont.Normal)
        for item in self.navigationInterface.panel.items.values():
            item.widget.setFont(nav_font)
        # 主题切换后刷新任务界面配色
        if hasattr(self, "task_ui"):
            self.task_ui.apply_theme_style()
        # 设置界面文字需随主题变色（深色=白）
        if hasattr(self, "settings_ui"):
            self.settings_ui.apply_theme_style()
        if hasattr(self, "about_ui"):
            self.about_ui.apply_theme_style()
        if hasattr(self, "remind_ui"):
            self.remind_ui.apply_theme_style()

    # ----------------------------- 托盘 / 定时器 -----------------------------
    def _init_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(FluentIcon.GAME.icon())
        self.tray.setToolTip("手游任务助手 Gacha Game Quest Helper")
        menu = QMenu(self)
        show_act = QAction("显示窗口", self)
        show_act.triggered.connect(self.showNormal)
        refresh_act = QAction("刷新", self)
        refresh_act.triggered.connect(self.task_ui.refresh_all)
        quit_act = QAction("退出", self)
        quit_act.triggered.connect(self.quit_app)
        menu.addAction(show_act)
        menu.addAction(refresh_act)
        menu.addSeparator()
        menu.addAction(quit_act)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.showNormal() if reason == QSystemTrayIcon.DoubleClick else None
        )
        self.tray.show()

    def _init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start(60000)

    def on_tick(self):
        # 有过期重置时需全量重建；否则仅增量刷新剩余时间，避免每 60 秒全量重建造成闪烁
        if database.auto_update_all():
            self.task_ui.refresh_table()
        else:
            self.task_ui.refresh_remaining()
        self.check_reminders()

    def check_reminders(self):
        now = datetime.now()
        # 跨周时清空去重集合，避免长期运行导致 key 无限累积（内存泄漏）
        wk = now.strftime("%Y-W%W")
        if wk != self.task_ui._remind_week_key:
            self.task_ui._last_remind.clear()
            self.task_ui._remind_week_key = wk
        for r in database.get_remind_rules():
            if not r["enabled"]:
                continue
            try:
                rh, rm = (int(x) for x in r["time"].split(":"))
            except Exception:
                continue
            if now.hour != rh or now.minute != rm:
                continue
            if r["rule_type"] == "每周" and now.weekday() != 0:
                continue
            if r["rule_type"] == "每月" and now.day != 1:
                continue
            occ = {"每日": now.strftime("%Y-%m-%d"),
                   "每周": now.strftime("%Y-W%W"),
                   "每月": now.strftime("%Y-%m")}[r["rule_type"]]
            key = f"{r['id']}:{occ}"
            if key in self.task_ui._last_remind:
                continue
            self.task_ui._last_remind.add(key)
            grouped = database.count_incomplete_grouped(
                r.get("game_id", -1), r.get("task_type", "")
            )
            total = sum(grouped.values())
            if total == 0:
                continue
            title, body = self._build_remind_text(r, grouped, total)
            self.tray.showMessage(title, body, QSystemTrayIcon.Information, 6000)

    def _build_remind_text(self, rule, grouped, total):
        """根据提醒规则的筛选生成细化文案。

        全部类型  -> 逐个类型说明各有多少未完成（日常 X、周常 Y...）。
        全部游戏  -> 不按游戏分别说明。
        特定类型/游戏 -> 直接说明该范围的数量。
        """
        ttype = rule.get("task_type", "")
        gname = RemindInterface._rule_game_name(rule)
        if not ttype:
            # 全部类型：仅列出有未完成的类型
            detail = "、".join(f"{k} {v}" for k, v in grouped.items() if v > 0)
            scope = f"【{gname}】" if gname else ""
            return "任务提醒", f"{scope}未完成共 {total} 个：{detail}"
        # 特定类型：仅说明该类型
        scope = f"【{gname}·{ttype}】" if gname else f"【{ttype}】"
        return "任务提醒", f"{scope}还有 {total} 个未完成"

    # ----------------------------- 布局持久化 -----------------------------
    def _restore_splitters(self):
        try:
            self.task_ui.main_split.restoreState(
                bytes(cfg_get("main_splitter", b""))
            )
            self.task_ui.left_split.restoreState(
                bytes(cfg_get("left_splitter", b""))
            )
        except Exception:
            pass

    def _restore_filter_state(self):
        """恢复隔断（折叠栏）的隐藏/展开状态。"""
        try:
            if cfg_get("filter_collapsed", False, bool):
                # 初始化时 _filter_collapsed=False，置为 False 后 toggle 翻转成折叠
                self.task_ui._filter_collapsed = False
                self.task_ui._toggle_filter_panel()
        except Exception:
            pass

    def _restore_window(self):
        """恢复上次退出时的窗口位置与尺寸。"""
        try:
            geo = cfg_get("window_geometry", b"")
            if geo:
                self.restoreGeometry(bytes(geo))
        except Exception:
            pass

    def showEvent(self, e):
        """窗口显示、几何恢复完成后，按实际可见宽度刷新所有任务卡片的压缩状态。

        此时滚动区可见宽度已确定，比启动时立即触发更准确。
        """
        super().showEvent(e)
        if hasattr(self, "task_ui"):
            QTimer.singleShot(0, self.task_ui._refresh_cards_compact)

    def closeEvent(self, event):
        remember = cfg_get("remember_close", False, bool)
        if remember:
            action = cfg_get("close_action", "minimize")
            if action == "minimize":
                event.ignore()
                self.hide()
                return
            event.accept()
            self.quit_app()
            return
        dlg = CloseChoiceDialog(self, bool(cfg_get("remember_close", False)))
        if dlg.exec_() == QDialog.Accepted:
            choice = dlg.choice()
            if dlg.remember():
                cfg_set("remember_close", True)
                cfg_set("close_action", choice)
            else:
                cfg_set("remember_close", False)
            if choice == "minimize":
                event.ignore()
                self.hide()
            else:
                event.accept()
                self.quit_app()
        else:
            event.ignore()

    def quit_app(self):
        cfg_set("main_splitter", self.task_ui.main_split.saveState())
        cfg_set("left_splitter", self.task_ui.left_split.saveState())
        cfg_set("filter_collapsed", self.task_ui._filter_collapsed)
        cfg_set("window_geometry", self.saveGeometry())
        QApplication.quit()

    # ----------------------------- 子界面动作 -----------------------------
    def update_title(self, incomplete=None):
        if incomplete is not None:
            self.setWindowTitle(
                f"手游任务助手 Gacha Game Quest Helper v2.0.0 — 未完成 {incomplete}"
            )
        else:
            self.setWindowTitle("手游任务助手 Gacha Game Quest Helper v2.0.0")
        if incomplete is not None and hasattr(self, "tray"):
            self.tray.setToolTip(
                f"手游任务助手 Gacha Game Quest Helper — 未完成 {incomplete}"
            )


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setQuitOnLastWindowClosed(False)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
