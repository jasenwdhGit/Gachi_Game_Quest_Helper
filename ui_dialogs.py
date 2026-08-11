# 手游任务助手 Gacha Game Quest Helper — 对话框层
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

"""QFluentWidgets 风格对话框层：游戏 / 任务 / 设置 / 提醒。

所有对话框均为 QDialog 子类，内部使用 Fluent 控件，保持统一的视觉风格。
数据访问通过 database / models 完成，本文件不持有业务逻辑。
"""
import os
from datetime import datetime, date

from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget,
    QFileDialog, QListWidget, QListWidgetItem, QMenu, QFrame
)

import qfluentwidgets as qf
from qfluentwidgets import (
    FluentIcon, LineEdit, ComboBox, CheckBox, SpinBox,
    PushButton, PrimaryPushButton, DateEdit, BodyLabel,
    TitleLabel, CaptionLabel, IconWidget, InfoBar, InfoBarPosition, HyperlinkButton,
    isDarkTheme
)

import models
import database


# ----------------------------------------------------------------------------
# 图标辅助
# ----------------------------------------------------------------------------
import functools
import tempfile


@functools.lru_cache(maxsize=256)
def _icon_for_path_cached(path: str) -> QIcon:
    """根据路径返回图标：.exe 提取程序图标，图片直接加载，其余回退默认图标。"""
    if not path:
        return qf.FluentIcon.GAME.icon()
    p = path.lower()
    if p.endswith(".exe") and os.path.exists(path):
        try:
            import win32ui, win32gui
            large, _ = win32gui.ExtractIconEx(path, 0)
            if large:
                hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
                hbmp = win32ui.CreateBitmap()
                hbmp.CreateCompatibleBitmap(hdc, 32, 32)
                memdc = hdc.CreateCompatibleDC()
                memdc.SelectObject(hbmp)
                memdc.DrawIcon((0, 0), large[0])
                bmpinfo = hbmp.GetInfo()
                bmpstr = hbmp.GetBitmapBits(True)
                from PIL import Image
                img = Image.frombuffer(
                    "RGBA", (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                    bmpstr, "raw", "BGRA"
                )
                # 写入系统临时目录，避免占用当前工作目录且无写权限时报错
                fd, tmp_path = tempfile.mkstemp(suffix=".png")
                try:
                    img.save(tmp_path)
                    return QIcon(tmp_path)
                finally:
                    os.close(fd)
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
        except Exception:
            return qf.FluentIcon.GAME.icon()
    if os.path.exists(path):
        return QIcon(path)
    return qf.FluentIcon.GAME.icon()


def icon_for_path(path: str) -> QIcon:
    """根据路径返回图标（带缓存）。exe 图标按路径缓存，避免每次刷新重复提取。"""
    return _icon_for_path_cached(path)


# ----------------------------------------------------------------------------
# 对话框基类
# ----------------------------------------------------------------------------
class _BaseDialog(QDialog):
    def __init__(self, parent=None, title="", width=420, height=0):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        if height:
            self.setFixedHeight(height)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(24, 20, 24, 16)
        self.body.setSpacing(14)

    def _add_buttons(self, accept_text="确定", reject_text="取消"):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        # 分隔线颜色随主题自适应：深色用白色半透明，浅色用黑色半透明
        divider = "rgba(255,255,255,0.10)" if isDarkTheme() else "rgba(0,0,0,0.08)"
        line.setStyleSheet(f"color: {divider};")
        self.body.addWidget(line)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = PushButton(reject_text)
        cancel.clicked.connect(self.reject)
        ok = PrimaryPushButton(accept_text)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        self.body.addLayout(row)
        self._ok = ok


# ----------------------------------------------------------------------------
# 添加 / 编辑游戏
# ----------------------------------------------------------------------------
class AddGameDialog(_BaseDialog):
    def __init__(self, parent=None, game=None):
        super().__init__(parent, "添加游戏" if game is None else "编辑游戏", width=460)
        self.game = game

        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("游戏名称")
        self.body.addWidget(BodyLabel("游戏名称"))
        self.body.addWidget(self.name_edit)

        # EXE / 图标
        self.exe_path = ""
        self.icon_path = game["icon_path"] if game else ""

        exe_row = QHBoxLayout()
        self.exe_label = BodyLabel("未选择程序" if not self.icon_path else os.path.basename(self.icon_path))
        self.exe_btn = PushButton("选择程序 / 图标")
        self.exe_btn.clicked.connect(self._pick)
        exe_row.addWidget(self.exe_label, 1)
        exe_row.addWidget(self.exe_btn)
        self.body.addLayout(exe_row)

        self.preview = IconWidget()
        self.preview.setFixedSize(48, 48)
        self.preview.setIcon(icon_for_path(self.icon_path))
        self.body.addWidget(self.preview, alignment=Qt.AlignCenter)

        self._add_buttons()

        if game:
            self.name_edit.setText(game["name"])

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择游戏程序或图标", "",
            "程序或图标 (*.exe *.ico *.png *.jpg);;所有文件 (*.*)"
        )
        if not path:
            return
        self.icon_path = path
        self.exe_label.setText(os.path.basename(path))
        self.preview.setIcon(icon_for_path(path))

    def accept(self):
        name = self.name_edit.text().strip()
        if not name:
            InfoBar.warning("请填写游戏名称", "", parent=self)
            return
        if self.game is None and database.game_name_exists(name):
            InfoBar.warning("该游戏名称已存在", "请更换名称", parent=self)
            return
        if self.game is not None and database.game_name_exists(name, exclude_id=self.game["id"]):
            InfoBar.warning("该游戏名称已存在", "请更换名称", parent=self)
            return
        self.result_name = name
        self.result_icon = self.icon_path
        super().accept()


# ----------------------------------------------------------------------------
# 游戏管理
# ----------------------------------------------------------------------------
class GameManageDialog(_BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent, "游戏管理", width=460, height=520)
        self.parent_ui = parent

        self.list = QListWidget()
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.body.addWidget(self.list, 1)

        add_btn = PrimaryPushButton("添加游戏")
        add_btn.clicked.connect(self._add)
        self.body.addWidget(add_btn)

        self.refresh()

    def refresh(self):
        self.list.clear()
        for g in database.get_games():
            it = QListWidgetItem(icon_for_path(g["icon_path"]), g["name"])
            it.setData(Qt.UserRole, g["id"])
            self.list.addItem(it)

    def _menu(self, pos):
        it = self.list.itemAt(pos)
        if not it:
            return
        gid = it.data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction(qf.FluentIcon.EDIT.icon(), "重命名 / 修改图标", lambda: self._edit(gid))
        menu.addAction(qf.FluentIcon.DELETE.icon(), "删除", lambda: self._delete(gid))
        menu.exec_(self.list.mapToGlobal(pos))

    def _add(self):
        dlg = AddGameDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            if database.add_game(dlg.result_name, dlg.result_icon) is None:
                InfoBar.warning("该游戏名称已存在", "请更换名称", parent=self)
                return
            self.refresh()
            if self.parent_ui:
                self.parent_ui.refresh_all()

    def _edit(self, gid):
        g = database.get_game(gid)
        if not g:
            return
        dlg = AddGameDialog(self, g)
        if dlg.exec_() == QDialog.Accepted:
            if not database.update_game(gid, dlg.result_name, dlg.result_icon):
                InfoBar.warning("该游戏名称已存在", "请更换名称", parent=self)
                return
            self.refresh()
            if self.parent_ui:
                self.parent_ui.refresh_all()

    def _delete(self, gid):
        if confirm(self, "删除游戏", "删除游戏将同时删除其下所有任务，确定？"):
            database.delete_game(gid)
            self.refresh()
            if self.parent_ui:
                self.parent_ui.refresh_all()


# ----------------------------------------------------------------------------
# 添加 / 编辑任务
# ----------------------------------------------------------------------------
class AddTaskDialog(_BaseDialog):
    def __init__(self, parent=None, task=None, preset_game_id=None, preset_type=None):
        super().__init__(parent, "添加任务" if task is None else "编辑任务", width=520)
        self.task = task
        self.games = database.get_games()
        if not self.games:
            InfoBar.warning("请先添加游戏", "", parent=self.parent())
            # 仍继续，但下拉为空

        # 游戏
        self.game_combo = ComboBox()
        for g in self.games:
            self.game_combo.addItem(g["name"])
        self.body.addWidget(BodyLabel("游戏"))
        self.body.addWidget(self.game_combo)

        # 任务名
        self.name_edit = LineEdit()
        self.name_edit.setPlaceholderText("任务名称")
        self.body.addWidget(BodyLabel("任务名称"))
        self.body.addWidget(self.name_edit)

        # 类型
        self.type_combo = ComboBox()
        self.type_combo.addItems(models.TASK_TYPES)
        self.type_combo.currentTextChanged.connect(self._on_type)
        self.body.addWidget(BodyLabel("任务类型"))
        self.body.addWidget(self.type_combo)

        # 条件输入区（根据类型动态显隐）
        self.cond = QWidget()
        cond_layout = QFormLayout(self.cond)
        cond_layout.setContentsMargins(0, 0, 0, 0)
        cond_layout.setSpacing(10)

        self.days_spin = SpinBox()
        self.days_spin.setRange(1, 365)
        self.days_spin.setValue(1)

        self.weekday_combo = ComboBox()
        self.weekday_combo.addItems(models.WEEKDAY_CN)

        self.start_date = DateEdit()
        self.start_date.setDate(QDate.currentDate())

        self.month_day_spin = SpinBox()
        self.month_day_spin.setRange(1, 31)
        self.month_day_spin.setValue(1)

        self.hour_spin = SpinBox()
        self.hour_spin.setRange(0, 28)
        self.hour_spin.setValue(4)
        self.minute_spin = SpinBox()
        self.minute_spin.setRange(0, 59)
        self.minute_spin.setValue(0)

        self.deadline_date = DateEdit()
        self.deadline_date.setDate(QDate.currentDate())
        self.deadline_hour = SpinBox()
        self.deadline_hour.setRange(0, 28)
        self.deadline_hour.setValue(4)
        self.deadline_minute = SpinBox()
        self.deadline_minute.setRange(0, 59)
        self.deadline_minute.setValue(0)

        cond_layout.addRow("周期天数", self.days_spin)
        cond_layout.addRow("星期", self.weekday_combo)
        cond_layout.addRow("起始日期", self.start_date)
        cond_layout.addRow("每月几号", self.month_day_spin)
        cond_layout.addRow("刷新时刻(时)", self.hour_spin)
        cond_layout.addRow("刷新时刻(分)", self.minute_spin)
        cond_layout.addRow("截止日期", self.deadline_date)
        cond_layout.addRow("截止(时)", self.deadline_hour)
        cond_layout.addRow("截止(分)", self.deadline_minute)
        self.body.addWidget(self.cond)

        # 提醒
        self.remind_cb = CheckBox("需要提醒")
        self.remind_cb.setChecked(True)
        self.body.addWidget(self.remind_cb)

        # 预览
        self.preview_label = CaptionLabel("")
        self.preview_label.setStyleSheet("color: #909399;")
        self.body.addWidget(self.preview_label)
        for w in (self.days_spin, self.weekday_combo, self.month_day_spin,
                  self.hour_spin, self.minute_spin, self.deadline_hour, self.deadline_minute):
            if hasattr(w, "valueChanged"):
                w.valueChanged.connect(self._update_preview)
            else:
                w.currentIndexChanged.connect(self._update_preview)
        self.start_date.dateChanged.connect(self._update_preview)
        self.deadline_date.dateChanged.connect(self._update_preview)

        self._add_buttons()

        # 预填
        if task:
            self._fill(task)
        elif preset_game_id is not None:
            for i, g in enumerate(self.games):
                if g["id"] == preset_game_id:
                    self.game_combo.setCurrentIndex(i)
                    break
        if preset_type:
            idx = self.type_combo.findText(preset_type)
            if idx >= 0:
                self.type_combo.setCurrentIndex(idx)
        self._on_type(self.type_combo.currentText())
        self._update_preview()

    def _on_type(self, t):
        periodic = t in models.PERIODIC_TYPES
        self.days_spin.setVisible(t == "日常")
        self.weekday_combo.setVisible(t == "周常")
        self.start_date.setVisible(t == "双周常")
        self.month_day_spin.setVisible(t == "月常")
        self.hour_spin.setVisible(periodic)
        self.minute_spin.setVisible(periodic)
        self.deadline_date.setVisible(t == "限时活动")
        self.deadline_hour.setVisible(t == "限时活动")
        self.deadline_minute.setVisible(t == "限时活动")

    def _build_rule(self):
        t = self.type_combo.currentText()
        hh = self.hour_spin.value()
        mm = self.minute_spin.value()
        if t == "日常":
            return models.build_rule(t, self.days_spin.value(), 0, "", 1, hh, mm)
        if t == "周常":
            return models.build_rule(t, 7, self.weekday_combo.currentIndex(), "", 1, hh, mm)
        if t == "双周常":
            return models.build_rule(t, 14, 0, self.start_date.date().toString("yyyy-MM-dd"), 1, hh, mm)
        if t == "月常":
            return models.build_rule(t, 1, 0, "", self.month_day_spin.value(), hh, mm)
        return ""

    def _update_preview(self):
        try:
            t = self.type_combo.currentText()
            if t == "限时活动":
                d = self.deadline_date.date().toPyDate()
                dl = models.from_game_time_to_real(d, self.deadline_hour.value(), self.deadline_minute.value())
            else:
                rule = self._build_rule()
                dl = models.compute_initial_deadline(t, rule, datetime.now())
            self.preview_label.setText("首次 / 当前截止：" + dl.strftime("%Y-%m-%d %H:%M"))
        except Exception as e:
            self.preview_label.setText("预览失败：" + str(e))

    def _fill(self, task):
        self.name_edit.setText(task["task_name"])
        for i, g in enumerate(self.games):
            if g["id"] == task["game_id"]:
                self.game_combo.setCurrentIndex(i)
                break
        tidx = self.type_combo.findText(task["task_type"])
        if tidx >= 0:
            self.type_combo.setCurrentIndex(tidx)
        self.remind_cb.setChecked(bool(task["need_remind"]))
        p = models.parse_period_rule(task["period_rule"])
        if p:
            if p.get("days"):
                self.days_spin.setValue(p["days"])
            if p.get("weekday") is not None:
                self.weekday_combo.setCurrentIndex(p["weekday"])
            if p.get("start"):
                try:
                    y, m, d = (int(x) for x in p["start"].split("-"))
                    self.start_date.setDate(date(y, m, d))
                except Exception:
                    pass
            if p.get("day"):
                self.month_day_spin.setValue(p["day"])
            self.hour_spin.setValue(p["hh"])
            self.minute_spin.setValue(p["mm"])
        else:
            # 限时活动
            dl = task["deadline_dt"]
            if dl:
                self.deadline_date.setDate(dl.date())
                self.deadline_hour.setValue(dl.hour)
                self.deadline_minute.setValue(dl.minute)

    def accept(self):
        name = self.name_edit.text().strip()
        if not name:
            InfoBar.warning("请填写任务名称", "", parent=self)
            return
        if self.game_combo.count() == 0:
            InfoBar.warning("请先添加游戏", "", parent=self)
            return
        self.result_game_id = self.games[self.game_combo.currentIndex()]["id"]
        self.result_name = name
        self.result_type = self.type_combo.currentText()
        self.result_remind = self.remind_cb.isChecked()
        if self.result_type == "限时活动":
            d = self.deadline_date.date().toPyDate()
            self.result_deadline = models.from_game_time_to_real(
                d, self.deadline_hour.value(), self.deadline_minute.value()
            )
            self.result_rule = ""
        else:
            self.result_rule = self._build_rule()
            self.result_deadline = models.compute_initial_deadline(
                self.result_type, self.result_rule, datetime.now()
            )
        super().accept()


def confirm(parent, title, text) -> bool:
    """通用确认对话框，返回是否点击「确定」。"""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
    dlg.setFixedSize(360, 150)
    v = QVBoxLayout(dlg)
    v.setContentsMargins(24, 20, 24, 16)
    v.addWidget(BodyLabel(text))
    row = QHBoxLayout()
    row.addStretch(1)
    no = PushButton("取消")
    no.clicked.connect(dlg.reject)
    yes = PrimaryPushButton("确定")
    yes.clicked.connect(dlg.accept)
    row.addWidget(no)
    row.addWidget(yes)
    v.addLayout(row)
    return dlg.exec_() == QDialog.Accepted


class CloseChoiceDialog(QDialog):
    """关闭窗口时询问：最小化到托盘 / 直接退出 / 取消。"""

    def __init__(self, parent=None, remember_default=False):
        super().__init__(parent)
        self._choice = "cancel"
        self.setWindowTitle("关闭窗口")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(380, 200)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 16)
        v.addWidget(BodyLabel("要如何关闭 手游任务助手 Gacha Game Quest Helper？"))

        self.remember_cb = CheckBox("记住我的选择")
        self.remember_cb.setChecked(bool(remember_default))
        v.addWidget(self.remember_cb)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = PushButton("取消")
        cancel.clicked.connect(self.reject)
        exit_btn = PushButton("直接退出")
        exit_btn.setObjectName("exitBtn")
        exit_btn.setStyleSheet("""
            #exitBtn{
                background-color:#F56C6C;
                color:#FFFFFF;
                border:none;
                border-radius:6px;
                padding:5px 16px;
            }
            #exitBtn:hover{background-color:#F89898;}
            #exitBtn:pressed{background-color:#C45656;}
        """)
        exit_btn.clicked.connect(self._exit)
        mini = PrimaryPushButton("最小化到托盘")
        mini.clicked.connect(self._minimize)
        row.addWidget(cancel)
        row.addWidget(exit_btn)
        row.addWidget(mini)
        v.addLayout(row)

    def _minimize(self):
        self._choice = "minimize"
        self.accept()

    def _exit(self):
        self._choice = "exit"
        self.accept()

    def choice(self):
        return self._choice

    def remember(self):
        return self.remember_cb.isChecked()
