"""手游日常助手 Gachi Game Quest Helper —— 主窗口、系统托盘、定时提醒、导入/导出。

界面布局（符合要求）：
    左侧：游戏筛选（多选）+ 类型筛选（多选）
    右侧：任务列表（QTableWidget）
        列：游戏图标(30px) | 游戏名称 | 任务名称 | 类型 | 截止时间(游戏时间) | 状态 | 操作
    排序：未完成在前（按剩余时间升序），已完成在末尾。
"""
import json
import os
import sys
from datetime import datetime

from PyQt5.QtCore import Qt, QSettings, QTimer, QSize
from PyQt5.QtGui import QIcon, QPixmap, QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QAction, QApplication, QCheckBox, QComboBox,
    QDialog, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSystemTrayIcon, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QInputDialog, QSplitter,
)

import database as db
import models
from dialogs import (
    AddGameDialog, AddTaskDialog, GameManageDialog, SettingsDialog,
    RemindSettingsDialog, CloseConfirmDialog, icon_for_path,
)

ICON_SIZE = 48  # 任务表图标列图标边长（px），已渲染缩放并填满单元格
SETTINGS_ORG = "GachiGameQuestHelper"
SETTINGS_APP = "手游日常助手 Gachi Game Quest Helper"
CONFIG_INI = os.path.join(
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__)),
    "config.ini",
)


class StatusButton(QPushButton):
    """状态按钮：已完成(绿色圆角) / 未完成(灰色)。"""

    def __init__(self, completed: bool, on_toggle):
        super().__init__()
        self.setFixedWidth(70)
        self._completed = completed
        self._on_toggle = on_toggle
        self.clicked.connect(lambda: self._on_toggle())
        self.refresh()

    def set_completed(self, c: bool):
        self._completed = c
        self.refresh()

    def refresh(self):
        if self._completed:
            self.setText("已完成")
            self.setStyleSheet(
                "background:#67C23A; color:#fff; border:none; border-radius:10px; padding:4px;"
            )
        else:
            self.setText("未完成")
            self.setStyleSheet(
                "background:#e0e0e0; color:#555; border:none; border-radius:10px; padding:4px;"
            )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        db.init_db()
        self.settings = QSettings(CONFIG_INI, QSettings.IniFormat)
        # 全局刷新点
        self.r_hour = int(self.settings.value("refresh_hour", 4))
        self.r_min = int(self.settings.value("refresh_min", 0))
        # 关闭行为记忆
        self.remember_close = self.settings.value("remember_close", "false") == "true"
        self.close_action = self.settings.value("close_action", "exit")  # 'min' / 'exit'

        self.setWindowTitle("手游日常助手 Gachi Game Quest Helper")
        self.resize(1050, 680)
        self.task_row_map = {}  # row -> task_id

        db.auto_update_all()  # 启动时过期自动重置
        self.init_ui()
        self.build_filters()
        self.refresh_table()

        self.setup_tray()
        self.setup_timer()
        self.restore_state()

    # ---------------------- 状态持久化（窗口大小 + 分割条位置） ----------------------
    def restore_state(self):
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1050, 680)
        st = self.settings.value("main_splitter")
        if st is not None:
            self.main_splitter.restoreState(st)
        st = self.settings.value("left_splitter")
        if st is not None:
            self.left_splitter.restoreState(st)

    def save_state(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("main_splitter", self.main_splitter.saveState())
        self.settings.setValue("left_splitter", self.left_splitter.saveState())

    # ---------------------- UI ----------------------
    def init_ui(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件")
        for text, slot in [("导出数据", self.export_data), ("导入数据", self.import_data)]:
            act = QAction(text, self); act.triggered.connect(slot); file_menu.addAction(act)
        tool_menu = menubar.addMenu("工具")
        for text, slot in [
            ("游戏管理", self.manage_games),
            ("通知设置", self.open_remind_settings),
            ("全局设置（刷新点）", self.open_settings),
        ]:
            act = QAction(text, self); act.triggered.connect(slot); tool_menu.addAction(act)
        help_menu = menubar.addMenu("帮助")
        about_act = QAction("关于", self); about_act.triggered.connect(self.show_about)
        help_menu.addAction(about_act)

        # 工具栏
        tb = self.addToolBar("工具栏")
        for text, slot in [
            ("➕ 添加游戏", self.add_game),
            ("➕ 添加任务", self.add_task),
            ("🔄 刷新", self.refresh_table),
        ]:
            act = QAction(text, self); act.triggered.connect(slot); tb.addAction(act)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # 左侧：垂直分割（游戏筛选 / 类型筛选）—— 两块可拖动调整高度
        game_panel = QWidget()
        gl = QVBoxLayout(game_panel)
        gl.addWidget(QLabel("游戏筛选（多选）"))
        self.game_filter = QListWidget()
        self.game_filter.setIconSize(QSize(22, 22))
        self.game_filter.itemChanged.connect(self.on_game_filter_changed)
        self.game_filter.setContextMenuPolicy(Qt.CustomContextMenu)
        self.game_filter.customContextMenuRequested.connect(self.on_game_filter_menu)
        gl.addWidget(self.game_filter)

        type_panel = QWidget()
        tl = QVBoxLayout(type_panel)
        tl.addWidget(QLabel("类型筛选（多选）"))
        self.type_filter = QListWidget()
        self.type_filter.itemChanged.connect(self.refresh_table)
        tl.addWidget(self.type_filter)

        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.addWidget(game_panel)
        self.left_splitter.addWidget(type_panel)
        self.left_splitter.setStretchFactor(0, 1)
        self.left_splitter.setStretchFactor(1, 1)
        self.left_splitter.setHandleWidth(3)
        self.left_splitter.setStyleSheet(
            "QSplitter::handle:vertical {"
            "  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "    stop:0 #8a8a8a, stop:0.5 #5f5f5f, stop:1 #8a8a8a);"
            "  height: 3px; border-radius: 2px;"
            "}"
            "QSplitter::handle:vertical:hover { background: #4A90D9; }"
        )

        # 右侧表格
        right = QWidget()
        rl = QVBoxLayout(right)
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["图标", "游戏名称", "任务名称", "类型", "剩余时间", "截止时间", "状态", "操作"]
        )
        self.table.setColumnWidth(0, ICON_SIZE + 8)
        self.table.verticalHeader().setDefaultSectionSize(ICON_SIZE + 8)
        self.table.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.on_table_menu)
        self.table.cellDoubleClicked.connect(self.on_table_double_clicked)
        rl.addWidget(self.table)

        # 主分割：左侧面板 | 右侧任务表 —— 可拖动调整宽度
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self.left_splitter)
        self.main_splitter.addWidget(right)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([220, 800])
        self.main_splitter.setHandleWidth(3)
        self.main_splitter.setStyleSheet(
            "QSplitter::handle:horizontal {"
            "  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "    stop:0 #8a8a8a, stop:0.5 #5f5f5f, stop:1 #8a8a8a);"
            "  width: 3px; border-radius: 2px;"
            "}"
            "QSplitter::handle:horizontal:hover { background: #4A90D9; }"
        )

        root.addWidget(self.main_splitter)

    def build_filters(self):
        self.game_filter.blockSignals(True)
        self.game_filter.clear()
        all_item = QListWidgetItem("全部游戏")
        all_item.setFlags(all_item.flags() | Qt.ItemIsUserCheckable)
        all_item.setCheckState(Qt.Checked)
        self.game_filter.addItem(all_item)
        for g in db.get_games():
            it = QListWidgetItem(g["name"])
            it.setIcon(icon_for_path(g["icon_path"]))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            it.setData(Qt.UserRole, g["id"])
            self.game_filter.addItem(it)
        self.game_filter.blockSignals(False)

        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        for t in models.TASK_TYPES:
            it = QListWidgetItem(t)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            it.setData(Qt.UserRole, t)
            self.type_filter.addItem(it)
        self.type_filter.blockSignals(False)

    def on_game_filter_changed(self, item):
        """游戏筛选联动：全部游戏 ⇄ 各游戏勾选状态。"""
        if item is self.game_filter.item(0):
            # “全部游戏”被切换：同步勾选/取消所有游戏
            state = item.checkState()
            self.game_filter.blockSignals(True)
            for i in range(1, self.game_filter.count()):
                self.game_filter.item(i).setCheckState(state)
            self.game_filter.blockSignals(False)
        else:
            # 单个游戏切换：更新“全部游戏”的勾选状态（全勾/无勾/部分勾）
            all_item = self.game_filter.item(0)
            states = [self.game_filter.item(i).checkState()
                      for i in range(1, self.game_filter.count())]
            checked = sum(1 for s in states if s == Qt.Checked)
            self.game_filter.blockSignals(True)
            if checked == 0:
                all_item.setCheckState(Qt.Unchecked)
            elif checked == len(states):
                all_item.setCheckState(Qt.Checked)
            else:
                all_item.setCheckState(Qt.PartiallyChecked)
            self.game_filter.blockSignals(False)
        self.refresh_table()

    def on_game_filter_menu(self, pos):
        """游戏筛选右键菜单：修改名称 / 修改图标 / 重新加载 EXE / 删除。"""
        item = self.game_filter.itemAt(pos)
        if item is None or item is self.game_filter.item(0):
            return  # 忽略“全部游戏”与空白处
        gid = item.data(Qt.UserRole)
        game = db.get_game(gid)
        if not game:
            return
        menu = QMenu(self)
        act_q_daily = menu.addAction("一键添加日常")
        act_q_weekly = menu.addAction("一键添加周常")
        menu.addSeparator()
        act_rename = menu.addAction("修改名称")
        act_icon = menu.addAction("修改图标")
        act_exe = menu.addAction("重新加载 EXE")
        act_add = QMenu("添加任务(自定义)", self)
        for t in models.TASK_TYPES:
            a = QAction(t, self)
            a.triggered.connect(lambda _, tt=t: self.add_task_for_game(gid, tt))
            act_add.addAction(a)
        menu.addMenu(act_add)
        menu.addSeparator()
        act_del = menu.addAction("删除游戏")
        action = menu.exec_(self.game_filter.viewport().mapToGlobal(pos))
        if action == act_q_daily:
            self.quick_add_task(gid, game, "日常")
        elif action == act_q_weekly:
            self.quick_add_task(gid, game, "周常")
        elif action == act_rename:
            self.rename_game_from_filter(item, gid, game)
        elif action == act_icon:
            self.change_icon_from_filter(item, gid)
        elif action == act_exe:
            self.reload_exe_from_filter(item, gid)
        elif action == act_del:
            self.delete_game_from_filter(gid, game)

    def rename_game_from_filter(self, item, gid, game):
        name, ok = QInputDialog.getText(self, "修改名称", "游戏名称:", text=game["name"])
        if not ok or not name.strip():
            return
        name = name.strip()
        if name == game["name"]:
            return
        exist = db.find_game_by_name(name)
        if exist and exist["id"] != gid:
            QMessageBox.information(self, "提示", "已存在同名游戏")
            return
        db.update_game(gid, name, game["icon_path"])
        item.setText(name)  # 就地更新，保留筛选勾选状态
        self.refresh_table()

    def change_icon_from_filter(self, item, gid):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择图标图片或 EXE", "", "图片/程序 (*.png *.jpg *.jpeg *.ico *.exe)"
        )
        if p:
            db.update_game(gid, db.get_game(gid)["name"], p)
            item.setIcon(icon_for_path(p))
            self.refresh_table()

    def reload_exe_from_filter(self, item, gid):
        p, _ = QFileDialog.getOpenFileName(self, "重新加载 EXE", "", "可执行文件 (*.exe)")
        if p:
            db.update_game(gid, db.get_game(gid)["name"], p)
            item.setIcon(icon_for_path(p))
            self.refresh_table()

    def delete_game_from_filter(self, gid, game):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除游戏「{game['name']}」吗？\n该游戏下的任务也会一并删除。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for t in db.get_tasks(game_ids={gid}):
            db.delete_task(t["id"])
        db.delete_game(gid)
        self.build_filters()  # 删除是结构性变化，重建筛选列表
        self.refresh_table()

    def add_task_for_game(self, gid, task_type):
        """从筛选栏右键直接进入添加任务，并预选游戏与类型。"""
        d = AddTaskDialog(self, r_hour=self.r_hour, r_min=self.r_min)
        d.fill_games()
        idx = d.game_combo.findData(gid)
        if idx >= 0:
            d.game_combo.setCurrentIndex(idx)
        if task_type in models.TASK_TYPES:
            d.type_combo.setCurrentText(task_type)
        if d.exec_() == QDialog.Accepted:
            tid = db.add_task(d.game_id, d.name, d.task_type, d.deadline, d.period_rule, d.need_remind)
            db.auto_update_task(tid)
            self.refresh_table()

    def quick_add_task(self, gid, game, task_type):
        """右键一键添加：以[游戏名]为任务名、按类型默认值直接入库（不弹窗）。"""
        now = datetime.now()
        if task_type == "日常":
            rule = models.build_rule("日常", days=1, weekday=0, start="", month_day=1, hh=4, mm=0)
        else:  # 周常
            rule = models.build_rule("周常", days=7, weekday=0, start="", month_day=1, hh=4, mm=0)
        deadline = models.compute_initial_deadline(task_type, rule, now)
        name = f"{game['name']}{task_type}"
        tid = db.add_task(gid, name, task_type, deadline, rule, False)
        db.auto_update_task(tid)
        self.refresh_table()

    def active_game_ids(self):
        items = [self.game_filter.item(i) for i in range(1, self.game_filter.count())]
        checked = [it.data(Qt.UserRole) for it in items if it.checkState() == Qt.Checked]
        # 若“全部游戏”未勾选且没有任何单独勾选，返回空
        all_item = self.game_filter.item(0)
        if all_item.checkState() == Qt.Checked:
            return None  # None 表示全部
        return set(checked) if checked else set()

    def active_types(self):
        items = [self.type_filter.item(i) for i in range(self.type_filter.count())]
        checked = [it.data(Qt.UserRole) for it in items if it.checkState() == Qt.Checked]
        return set(checked) if checked else set()

    # ---------------------- 表格 ----------------------
    def refresh_table(self):
        now = datetime.now()
        gid_set = self.active_game_ids()
        type_set = self.active_types()
        tasks = db.get_tasks(game_ids=gid_set, types=type_set)

        incomplete = [t for t in tasks if not t["completed"]]
        complete = [t for t in tasks if t["completed"]]
        incomplete.sort(key=lambda t: t["deadline_dt"])
        ordered = incomplete + complete

        self.table.setRowCount(len(ordered))
        self.task_row_map.clear()
        for r, t in enumerate(ordered):
            self.task_row_map[r] = t["id"]
            g = db.get_game(t["game_id"])

            # 图标 —— 强制缩放至单元格大小（ICON_SIZE x ICON_SIZE），Qt 平滑缩放填满
            icon_item = QTableWidgetItem()
            ic = icon_for_path(g["icon_path"]) if g else QIcon()
            if not ic.isNull():
                pm = ic.pixmap(ICON_SIZE, ICON_SIZE)
                if not pm.isNull():
                    ic = QIcon(pm)
            icon_item.setIcon(ic)
            self.table.setItem(r, 0, icon_item)

            self.table.setItem(r, 1, QTableWidgetItem(g["name"] if g else "-"))
            self.table.setItem(r, 2, QTableWidgetItem(t["task_name"]))

            type_item = QTableWidgetItem(t["task_type"])
            self.table.setItem(r, 3, type_item)

            # 剩余时间
            rem_item = QTableWidgetItem(models.remaining_str(t["deadline_dt"], now))
            warn = models.is_red_warning(t["task_type"], t["deadline_dt"], now)
            if warn:
                rem_item.setForeground(QColor("#e53935"))
                rem_item.setToolTip("剩余时间不足，请注意")
            self.table.setItem(r, 4, rem_item)

            # 截止时间（游戏时间 + 红警）
            dl_str = models.to_game_time_str(t["deadline_dt"], self.r_hour, self.r_min)
            dl_item = QTableWidgetItem(dl_str)
            if warn:
                dl_item.setForeground(QColor("#e53935"))
                dl_item.setToolTip("剩余时间不足，请注意")
            self.table.setItem(r, 5, dl_item)

            # 状态按钮
            status_btn = StatusButton(t["completed"], lambda tid=t["id"]: self.toggle_complete(tid))
            cell = QWidget()
            hl = QHBoxLayout(cell); hl.addWidget(status_btn); hl.setContentsMargins(2, 0, 2, 0)
            self.table.setCellWidget(r, 6, cell)

            # 操作
            op = QWidget()
            ol = QHBoxLayout(op)
            edit_btn = QPushButton("编辑"); edit_btn.setFixedWidth(46)
            del_btn = QPushButton("删除"); del_btn.setFixedWidth(46); del_btn.setObjectName("danger")
            edit_btn.clicked.connect(lambda _, tid=t["id"]: self.edit_task(tid))
            del_btn.clicked.connect(lambda _, tid=t["id"]: self.delete_task(tid))
            ol.addWidget(edit_btn); ol.addWidget(del_btn)
            ol.setContentsMargins(2, 0, 2, 0)
            self.table.setCellWidget(r, 7, op)

            # 行底色：已完成灰；警告（未完成的周常<3天/其他<7天/限时活动<7天）整行浅红
            if t["completed"]:
                for c in range(self.table.columnCount()):
                    it = self.table.item(r, c)
                    if it:
                        it.setBackground(QColor("#f2f2f2"))
            elif warn:
                for c in range(self.table.columnCount()):
                    it = self.table.item(r, c)
                    if it:
                        it.setBackground(QColor("#ffd9d9"))
                cell.setStyleSheet("background:#ffd9d9;")
                op.setStyleSheet("background:#ffd9d9;")

        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, ICON_SIZE + 8)

    def toggle_complete(self, tid):
        t = db.get_task(tid)
        if not t:
            return
        db.set_completed(tid, not t["completed"])
        self.refresh_table()

    def on_table_double_clicked(self, row, col):
        """双击任务行直接切换完成状态（状态/操作列由按钮处理，忽略）。"""
        if col in (6, 7):
            return
        tid = self.task_row_map.get(row)
        if tid is None:
            return
        self.toggle_complete(tid)

    def on_table_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        tid = self.task_row_map.get(row)
        if tid is None:
            return
        menu = QMenu(self)
        act_toggle = menu.addAction("切换完成状态")
        act_edit = menu.addAction("编辑")
        act_del = menu.addAction("删除")
        action = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if action == act_toggle:
            self.toggle_complete(tid)
        elif action == act_edit:
            self.edit_task(tid)
        elif action == act_del:
            self.delete_task(tid)

    # ---------------------- 操作 ----------------------
    def add_game(self):
        d = AddGameDialog(self)
        if d.exec_() == QDialog.Accepted:
            if db.find_game_by_name(d.name):
                QMessageBox.information(self, "提示", "该游戏已存在")
            else:
                db.add_game(d.name, d.icon_path)
            self.build_filters()
            self.refresh_table()

    def add_task(self):
        if not db.get_games():
            QMessageBox.information(self, "提示", "请先添加一款游戏，再添加任务。")
            return
        d = AddTaskDialog(self, r_hour=self.r_hour, r_min=self.r_min)
        if d.exec_() == QDialog.Accepted:
            tid = db.add_task(d.game_id, d.name, d.task_type, d.deadline, d.period_rule, d.need_remind)
            db.auto_update_task(tid)
            self.refresh_table()

    def edit_task(self, tid):
        task = db.get_task(tid)
        if not task:
            return
        d = AddTaskDialog(self, task=task, r_hour=self.r_hour, r_min=self.r_min)
        if d.exec_() == QDialog.Accepted:
            db.update_task(tid, d.game_id, d.name, d.task_type, d.deadline, d.period_rule, d.need_remind)
            db.auto_update_task(tid)
            self.refresh_table()

    def delete_task(self, tid):
        reply = QMessageBox.question(self, "确认删除", "确定删除该任务吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            db.delete_task(tid)
            self.refresh_table()

    def manage_games(self):
        d = GameManageDialog(self)
        if d.exec_() == QDialog.Accepted:
            self.build_filters()
            self.refresh_table()

    def open_settings(self):
        d = SettingsDialog(self.r_hour, self.r_min, self)
        if d.exec_() == QDialog.Accepted:
            self.r_hour, self.r_min = d.r_hour, d.r_min
            self.settings.setValue("refresh_hour", self.r_hour)
            self.settings.setValue("refresh_min", self.r_min)
            db.auto_update_all()  # 重新计算所有周期性任务截止时间
            self.refresh_table()

    def open_remind_settings(self):
        d = RemindSettingsDialog(self)
        d.exec_()

    # ---------------------- 导入 / 导出 ----------------------
    def export_data(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出数据", "game_tasks.json", "JSON (*.json)")
        if not path:
            return
        data = db.export_json()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, "导出成功", f"数据已导出至：\n{path}")

    def import_data(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入数据", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"文件解析错误：{e}")
            return
        reply = QMessageBox.question(
            self, "确认导入",
            "导入将覆盖当前所有数据（已自动备份当前数据）。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        backup = os.path.join(os.path.dirname(path) or ".", "game_tasks.backup.json")
        with open(backup, "w", encoding="utf-8") as f:
            json.dump(db.export_json(), f, ensure_ascii=False, indent=2)
        db.import_json(data)
        db.auto_update_all()
        self.build_filters()
        self.refresh_table()
        QMessageBox.information(self, "导入成功", f"数据已导入，原数据备份于：\n{backup}")

    # ---------------------- 托盘 / 通知 ----------------------
    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.app_icon())
        self.tray.setToolTip("手游日常助手 Gachi Game Quest Helper")
        menu = QMenu(self)
        show_act = QAction("显示主窗口", self); show_act.triggered.connect(self.show_normal)
        forget_act = QAction("取消记住退出选择", self); forget_act.triggered.connect(self.forget_close_choice)
        exit_act = QAction("退出", self); exit_act.triggered.connect(self.app_exit)
        menu.addAction(show_act)
        menu.addAction(forget_act)
        menu.addSeparator()
        menu.addAction(exit_act)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_normal() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def forget_close_choice(self):
        """清除“记住退出选择”，下次关闭窗口会重新询问。"""
        self.remember_close = False
        self.close_action = "min"
        self.settings.setValue("remember_close", False)
        self.settings.setValue("close_action", "min")
        QMessageBox.information(self, "提示", "已取消记住退出选择，下次关闭窗口将重新询问。")

    def app_icon(self):
        pm = QPixmap(32, 32)
        pm.fill(QColor("#4A90D9"))
        return QIcon(pm)

    def setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_reminders)
        self.timer.start(60 * 1000)  # 每分钟检查
        self._notify_marks = set()  # 记录本分钟已发送的 (rid, minute_key)

    def check_reminders(self):
        now = datetime.now()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        # 清理旧的发送标记
        self._notify_marks = {m for m in self._notify_marks if m[1] == minute_key}
        for r in db.get_remind_rules():
            if not r["enabled"]:
                continue
            if r["time"] != now.strftime("%H:%M"):
                continue
            mark = (r["id"], minute_key)
            if mark in self._notify_marks:
                continue
            self._notify_marks.add(mark)
            if r["rule_type"] == "daily":
                x = db.count_incomplete_daily()
                msg = f"今天你还有 {x} 个日常任务未完成。"
            else:
                x = db.count_incomplete_all()
                msg = f"本周你还有 {x} 个任务未完成。"
            self.tray.showMessage("手游日常助手提醒", msg, QSystemTrayIcon.Information, 5000)

    # ---------------------- 显示 / 关闭 ----------------------
    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        self.save_state()
        if self.remember_close and self.close_action == "min":
            event.ignore()
            self.hide()
            self.tray.showMessage("手游日常助手", "已最小化到系统托盘", QSystemTrayIcon.Information, 2000)
            return
        if self.remember_close and self.close_action == "exit":
            event.accept()
            self.app_exit(real=False)
            return

        d = CloseConfirmDialog(self.remember_close, self)
        res = d.exec_()
        if res == 1:  # 最小化
            action = "min"
        elif res == 2:  # 退出
            action = "exit"
        else:
            event.ignore()
            return

        if d.remember_chk.isChecked():
            self.settings.setValue("remember_close", "true")
            self.settings.setValue("close_action", action)
            self.remember_close = True
            self.close_action = action

        if action == "min":
            event.ignore()
            self.hide()
        else:
            event.accept()
            self.app_exit(real=False)

    def app_exit(self, real=True):
        self.tray.hide()
        QApplication.quit()

    def show_about(self):
        QMessageBox.about(
            self, "关于",
            "手游日常助手 Gachi Game Quest Helper v3.0\n\n"
            "记录与管理多款手游的 日常/周常/双周常/月常/限时活动 任务。\n"
            "数据保存在本地 game_tasks.db（SQLite）。",
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(SETTINGS_APP)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
