"""对话框集合：添加/管理游戏、添加/编辑任务、全局设置、提醒设置、关闭确认。"""
from datetime import datetime, date, timedelta

from PyQt5.QtCore import QDate, QFileInfo, Qt, QTime
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QGroupBox, QTimeEdit, QWidget,
)

import database as db
import models

ICON_SIZE = 96  # 添加/编辑游戏时图标预览尺寸


def icon_for_path(path: str) -> QIcon:
    """根据路径生成图标：exe 用系统文件图标，图片直接用 QPixmap。"""
    if not path:
        return QIcon()
    if path.lower().endswith(".exe"):
        from PyQt5.QtWidgets import QFileIconProvider
        return QFileIconProvider().icon(QFileInfo(path))
    pm = QPixmap(path)
    if not pm.isNull():
        return QIcon(pm)
    return QIcon()


def scaled_icon(path: str) -> QIcon:
    ic = icon_for_path(path)
    return ic


# --------------------------------------------------------------------------
# 添加游戏
# --------------------------------------------------------------------------
class AddGameDialog(QDialog):
    def __init__(self, parent=None, game: dict = None):
        super().__init__(parent)
        self.setWindowTitle("添加游戏" if not game else "编辑游戏")
        self.resize(420, 300)
        self.icon_path = game["icon_path"] if game else ""

        layout = QVBoxLayout(self)
        fl = QFormLayout()
        self.name_edit = QLineEdit(game["name"] if game else "")
        fl.addRow("游戏名称:", self.name_edit)
        layout.addLayout(fl)

        hl = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("border:1px solid #ccc;background:#fff;")
        self.update_icon_preview()
        hl.addWidget(self.icon_label)
        up_btn = QPushButton("上传图片")
        up_btn.clicked.connect(self.upload_image)
        exe_btn = QPushButton("选择 EXE")
        exe_btn.clicked.connect(self.select_exe)
        hl.addWidget(up_btn)
        hl.addWidget(exe_btn)
        hl.addStretch(1)
        layout.addLayout(hl)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def update_icon_preview(self):
        ic = icon_for_path(self.icon_path)
        if not ic.isNull():
            # 先取大尺寸图标再按比例缩放到预览框，保证显示完整、清晰
            pm = ic.pixmap(ICON_SIZE * 4, ICON_SIZE * 4)
            if not pm.isNull():
                pm = pm.scaled(ICON_SIZE, ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.icon_label.setPixmap(pm)
                self.icon_label.setText("")
                return
        self.icon_label.setPixmap(QPixmap())
        self.icon_label.setText("无")

    def upload_image(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.ico)")
        if p:
            self.icon_path = p
            self.update_icon_preview()

    def select_exe(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择 EXE", "", "可执行文件 (*.exe)")
        if p:
            self.icon_path = p
            # 从文件名猜测游戏名（若未填）
            if not self.name_edit.text().strip():
                base = QFileInfo(p).baseName()
                self.name_edit.setText(base)
            self.update_icon_preview()

    def accept(self):
        self.name = self.name_edit.text().strip()
        if not self.name:
            QMessageBox.warning(self, "提示", "请填写游戏名称")
            return
        super().accept()


# --------------------------------------------------------------------------
# 游戏管理
# --------------------------------------------------------------------------
class GameManageDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("游戏管理")
        self.resize(420, 360)
        layout = QVBoxLayout(self)

        self.list = QListWidget()
        self.list.itemClicked.connect(self.on_select)
        layout.addWidget(self.list)

        btn_row = QHBoxLayout()
        self.name_edit = QLineEdit()
        btn_row.addWidget(QLabel("名称:"))
        btn_row.addWidget(self.name_edit, 1)
        layout.addLayout(btn_row)

        op = QHBoxLayout()
        self.rename_btn = QPushButton("修改名称")
        self.rename_btn.clicked.connect(self.rename_game)
        self.icon_btn = QPushButton("更换图标/EXE")
        self.icon_btn.clicked.connect(self.change_icon)
        self.del_btn = QPushButton("删除游戏")
        self.del_btn.setObjectName("danger")
        self.del_btn.clicked.connect(self.delete_game)
        op.addWidget(self.rename_btn)
        op.addWidget(self.icon_btn)
        op.addWidget(self.del_btn)
        op.addStretch(1)
        layout.addLayout(op)

        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        layout.addWidget(bb)

        self.current = None
        self.refresh()

    def refresh(self):
        sel_id = self.current["id"] if self.current else None
        self.list.clear()
        for g in db.get_games():
            item = QListWidgetItem(g["name"])
            item.setIcon(icon_for_path(g["icon_path"]))
            item.setData(Qt.UserRole, g["id"])
            self.list.addItem(item)
        # 刷新后恢复选中项，避免更换图标/改名后丢失选择
        if sel_id is not None:
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.UserRole) == sel_id:
                    self.list.setCurrentRow(i)
                    self.current = db.get_game(sel_id)
                    self.name_edit.setText(self.current["name"])
                    break

    def on_select(self, item):
        self.current = db.get_game(item.data(Qt.UserRole))
        if self.current:
            self.name_edit.setText(self.current["name"])

    def rename_game(self):
        if not self.current:
            QMessageBox.information(self, "提示", "请先选择一款游戏")
            return
        new_name = self.name_edit.text().strip()
        if not new_name:
            QMessageBox.information(self, "提示", "名称不能为空")
            return
        if new_name == self.current["name"]:
            return
        exist = db.find_game_by_name(new_name)
        if exist and exist["id"] != self.current["id"]:
            QMessageBox.information(self, "提示", "已存在同名游戏")
            return
        db.update_game(self.current["id"], new_name, self.current["icon_path"])
        self.refresh()
        QMessageBox.information(self, "提示", "名称已修改")

    def change_icon(self):
        if not self.current:
            QMessageBox.information(self, "提示", "请先选择一款游戏")
            return
        p, _ = QFileDialog.getOpenFileName(
            self, "选择图标图片或 EXE", "", "图片/程序 (*.png *.jpg *.jpeg *.ico *.exe)"
        )
        if p:
            db.update_game(self.current["id"], self.current["name"], p)
            self.current = db.get_game(self.current["id"])
            self.refresh()
            QMessageBox.information(self, "提示", "图标已更新")

    def delete_game(self):
        if not self.current:
            QMessageBox.information(self, "提示", "请先选择一款游戏")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除游戏「{self.current['name']}」吗？\n该游戏下的任务也会一并删除。",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for t in db.get_tasks(game_ids={self.current["id"]}):
            db.delete_task(t["id"])
        db.delete_game(self.current["id"])
        self.current = None
        self.name_edit.clear()
        self.refresh()
        QMessageBox.information(self, "提示", "游戏已删除")

    def accept(self):
        if self.current and self.name_edit.text().strip():
            new_name = self.name_edit.text().strip()
            db.update_game(self.current["id"], new_name, self.current["icon_path"])
        super().accept()


# --------------------------------------------------------------------------
# 添加 / 编辑任务
# --------------------------------------------------------------------------
class AddTaskDialog(QDialog):
    def __init__(self, parent=None, task: dict = None, r_hour: int = 4, r_min: int = 0):
        super().__init__(parent)
        self.setWindowTitle("添加任务" if not task else "编辑任务")
        self.resize(460, 420)
        self.task = task
        self.r_hour = r_hour
        self.r_min = r_min

        layout = QVBoxLayout(self)

        # 游戏选择
        gl = QHBoxLayout()
        gl.addWidget(QLabel("游戏:"))
        self.game_combo = QComboBox()
        self.fill_games()
        self.add_game_btn = QPushButton("添加游戏")
        self.add_game_btn.clicked.connect(self.on_add_game)
        gl.addWidget(self.game_combo, 1)
        gl.addWidget(self.add_game_btn)
        layout.addLayout(gl)

        # 名称
        nl = QHBoxLayout()
        nl.addWidget(QLabel("任务名称:"))
        self.name_edit = QLineEdit()
        nl.addWidget(self.name_edit, 1)
        layout.addLayout(nl)

        # 类型
        tl = QHBoxLayout()
        tl.addWidget(QLabel("类型:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(models.TASK_TYPES)
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        tl.addWidget(self.type_combo, 1)
        layout.addLayout(tl)

        # 周期规则区（仅周期任务）—— 控件只创建一次，靠可见性切换，避免重复 addRow 删除控件
        self.period_box = QGroupBox("周期规则")
        self.p_layout = QFormLayout(self.period_box)
        self.days_spin = QSpinBox(); self.days_spin.setRange(1, 365); self.days_spin.setValue(1)
        self.week_combo = QComboBox(); self.week_combo.addItems(models.WEEKDAY_CN)
        self.start_edit = QDateEdit(QDate.currentDate()); self.start_edit.setCalendarPopup(True)
        self.month_spin = QSpinBox(); self.month_spin.setRange(1, 31); self.month_spin.setValue(1)
        self.time_edit = QTimeEdit(QTime(4, 0)); self.time_edit.setDisplayFormat("HH:mm")
        self.preset_row = QHBoxLayout()
        for label, fn in [
            ("每天 4:00", lambda: self.apply_preset("daily")),
            ("每周一 4:00", lambda: self.apply_preset("weekly")),
            ("每月1日 4:00", lambda: self.apply_preset("monthly")),
        ]:
            b = QPushButton(label); b.clicked.connect(fn); self.preset_row.addWidget(b)

        self.period_inner = QWidget()
        il = QFormLayout(self.period_inner)
        il.addRow("每 X 天:", self.days_spin)
        il.addRow("星期几:", self.week_combo)
        il.addRow("起始日期:", self.start_edit)
        il.addRow("每月几号:", self.month_spin)
        il.addRow("刷新时间:", self.time_edit)
        il.addRow("快捷:", self.preset_row)
        self.p_layout.addRow(self.period_inner)

        layout.addWidget(self.period_box)

        # 限时活动截止时间（0~28 小时制）—— 紧凑排布：日期+时+分 紧挨在一起
        self.limit_box = QGroupBox("截止时间（游戏时间）")
        ll = QHBoxLayout(self.limit_box)
        ll.setSpacing(4)
        ll.setContentsMargins(8, 8, 8, 8)
        self.date_edit = QDateEdit(QDate.currentDate()); self.date_edit.setCalendarPopup(True)
        self.hour_combo = QComboBox()
        self.hour_combo.setFixedWidth(56)
        self.hour_combo.addItems([str(h) for h in range(0, 29)])  # 0~28
        self.min_combo = QComboBox()
        self.min_combo.setFixedWidth(56)
        self.min_combo.addItems([f"{m:02d}" for m in range(0, 60)])
        ll.addWidget(QLabel("日期"))
        ll.addWidget(self.date_edit)
        ll.addSpacing(4)
        ll.addWidget(QLabel("时"))
        ll.addWidget(self.hour_combo)
        ll.addSpacing(4)
        ll.addWidget(QLabel("分"))
        ll.addWidget(self.min_combo)
        ll.addStretch(1)
        layout.addWidget(self.limit_box)

        # 提醒
        self.remind_chk = QCheckBox("开启提醒")
        self.remind_chk.setChecked(True)
        layout.addWidget(self.remind_chk)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

        self.on_type_changed()
        if task:
            self.prefill(task)

    # ---- 周期规则控件动态显示 ----
    def on_type_changed(self):
        t = self.type_combo.currentText()
        show_limit = t == "限时活动"
        self.limit_box.setVisible(show_limit)
        self.period_box.setVisible(not show_limit)
        if show_limit:
            return
        # 仅切换各控件（含其标签）可见性，绝不 removeRow，避免删除已复用控件
        mapping = [
            (self.days_spin, t in ("日常", "双周常")),
            (self.week_combo, t == "周常"),
            (self.start_edit, t == "双周常"),
            (self.month_spin, t == "月常"),
            (self.time_edit, True),
        ]
        for w, vis in mapping:
            w.setVisible(vis)
            lbl = self.period_inner.layout().labelForField(w)
            if lbl is not None:
                lbl.setVisible(vis)

    def apply_preset(self, kind):
        self.time_edit.setTime(QTime(4, 0))
        if kind == "daily":
            self.type_combo.setCurrentText("日常")
            self.days_spin.setValue(1)
        elif kind == "weekly":
            self.type_combo.setCurrentText("周常")
            self.week_combo.setCurrentIndex(0)
        elif kind == "monthly":
            self.type_combo.setCurrentText("月常")
            self.month_spin.setValue(1)

    def fill_games(self):
        self.game_combo.clear()
        for g in db.get_games():
            self.game_combo.addItem(g["name"], g["id"])

    def on_add_game(self):
        d = AddGameDialog(self)
        if d.exec_() == QDialog.Accepted:
            if db.find_game_by_name(d.name):
                QMessageBox.information(self, "提示", "该游戏已存在")
            else:
                db.add_game(d.name, d.icon_path)
            self.fill_games()
            idx = self.game_combo.findText(d.name)
            if idx >= 0:
                self.game_combo.setCurrentIndex(idx)

    def prefill(self, task):
        idx = self.game_combo.findData(task["game_id"])
        if idx >= 0:
            self.game_combo.setCurrentIndex(idx)
        self.name_edit.setText(task["task_name"])
        self.type_combo.setCurrentText(task["task_type"])
        self.remind_chk.setChecked(task["need_remind"])
        if task["task_type"] == "限时活动":
            dt = task["deadline_dt"]
            # 反向转换真实时间 -> 游戏时间(0~28)，再填到控件
            gdate, ghour, gmin = self.real_to_game_input(dt)
            self.date_edit.setDate(QDate(gdate.year, gdate.month, gdate.day))
            self.hour_combo.setCurrentText(str(ghour))
            self.min_combo.setCurrentText(f"{gmin:02d}")
        else:
            p = models.parse_period_rule(task["period_rule"])
            self.time_edit.setTime(QTime(p["hh"], p["mm"]))
            if task["task_type"] == "日常":
                self.days_spin.setValue(p["days"] or 1)
            elif task["task_type"] == "周常":
                self.week_combo.setCurrentIndex(p["weekday"] or 0)
            elif task["task_type"] == "双周常":
                self.days_spin.setValue(p["days"] or 14)
                if p["start"]:
                    y, m, d = (int(x) for x in p["start"].split("-"))
                    self.start_edit.setDate(QDate(y, m, d))
            elif task["task_type"] == "月常":
                self.month_spin.setValue(p["day"] or 1)

    def real_to_game_input(self, dt: datetime):
        """真实时间 -> (日期, 小时0~28, 分钟)，遵循 28 小时制反向规则（基于全局刷新点）。"""
        R = self.r_hour
        if dt.hour < R:
            return dt.date() - timedelta(days=1), dt.hour + 24, dt.minute
        if dt.hour == R:
            return dt.date() - timedelta(days=1), R + 24, dt.minute
        return dt.date(), dt.hour, dt.minute

    def accept(self):
        self.name = self.name_edit.text().strip()
        if not self.name:
            QMessageBox.warning(self, "提示", "请填写任务名称")
            return
        if self.game_combo.count() == 0:
            QMessageBox.warning(self, "提示", "请先添加一款游戏")
            return
        self.game_id = self.game_combo.currentData()
        self.task_type = self.type_combo.currentText()
        self.need_remind = self.remind_chk.isChecked()
        self.period_rule = ""
        self.deadline = None

        hh = self.time_edit.time().hour()
        mm = self.time_edit.time().minute()
        if self.task_type == "日常":
            self.period_rule = models.build_rule("日常", self.days_spin.value(), 0, "", 1, hh, mm)
            self.deadline = models.compute_initial_deadline("日常", self.period_rule, datetime.now())
        elif self.task_type == "周常":
            self.period_rule = models.build_rule("周常", 7, self.week_combo.currentIndex(), "", 1, hh, mm)
            self.deadline = models.compute_initial_deadline("周常", self.period_rule, datetime.now())
        elif self.task_type == "双周常":
            start = self.start_edit.date().toString("yyyy-MM-dd")
            self.period_rule = models.build_rule("双周常", self.days_spin.value(), 0, start, 1, hh, mm)
            self.deadline = models.compute_initial_deadline("双周常", self.period_rule, datetime.now())
        elif self.task_type == "月常":
            self.period_rule = models.build_rule("月常", 1, 0, "", self.month_spin.value(), hh, mm)
            self.deadline = models.compute_initial_deadline("月常", self.period_rule, datetime.now())
        elif self.task_type == "限时活动":
            gd = self.date_edit.date().toPyDate()
            gh = int(self.hour_combo.currentText())
            gm = int(self.min_combo.currentText())
            self.deadline = models.from_game_time_to_real(gd, gh, gm)
        super().accept()


# --------------------------------------------------------------------------
# 全局设置（刷新点）
# --------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, r_hour, r_min, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全局设置 - 刷新点")
        self.resize(280, 160)
        layout = QVBoxLayout(self)
        fl = QFormLayout()
        self.hour_spin = QSpinBox(); self.hour_spin.setRange(0, 23); self.hour_spin.setValue(r_hour)
        self.min_spin = QSpinBox(); self.min_spin.setRange(0, 59); self.min_spin.setValue(r_min)
        fl.addRow("刷新点（时）:", self.hour_spin)
        fl.addRow("刷新点（分）:", self.min_spin)
        layout.addLayout(fl)
        note = QLabel("修改后将按新刷新点重新计算所有周期性任务截止时间。")
        note.setWordWrap(True)
        layout.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def accept(self):
        self.r_hour = self.hour_spin.value()
        self.r_min = self.min_spin.value()
        super().accept()


# --------------------------------------------------------------------------
# 提醒设置
# --------------------------------------------------------------------------
class RemindSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("通知提醒设置")
        self.resize(460, 360)
        layout = QVBoxLayout(self)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["类型", "时间", "启用", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, __import__("PyQt5.QtWidgets", fromlist=["QHeaderView"]).QHeaderView.Stretch)
        layout.addWidget(self.table)
        self.add_btn = QPushButton("添加规则（最多 10 条）")
        self.add_btn.clicked.connect(self.add_rule)
        layout.addWidget(self.add_btn)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(self.accept)
        layout.addWidget(bb)
        self.refresh()

    def refresh(self):
        rules = db.get_remind_rules()
        self.table.setRowCount(len(rules))
        for r, rule in enumerate(rules):
            self.table.setItem(r, 0, QTableWidgetItem("每日提醒" if rule["rule_type"] == "daily" else "每周提醒"))
            self.table.setItem(r, 1, QTableWidgetItem(rule["time"]))
            self.table.setItem(r, 2, QTableWidgetItem("是" if rule["enabled"] else "否"))
            op = QPushButton("删除")
            op.setObjectName("danger")
            op.clicked.connect(lambda _, rid=rule["id"]: self.del_rule(rid))
            self.table.setCellWidget(r, 3, op)

    def add_rule(self):
        if db.count_remind_rules() >= 10:
            QMessageBox.warning(self, "提示", "最多只能添加 10 条提醒规则")
            return
        # 简易添加：默认每日 08:00，启用
        db.add_remind_rule("daily", "08:00", True)
        self.refresh()

    def del_rule(self, rid):
        db.delete_remind_rule(rid)
        self.refresh()

    def accept(self):
        super().accept()


# --------------------------------------------------------------------------
# 关闭确认
# --------------------------------------------------------------------------
class CloseConfirmDialog(QDialog):
    def __init__(self, remember: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关闭确认")
        self.resize(300, 150)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("你希望如何关闭程序？"))
        self.min_btn = QPushButton("最小化到托盘")
        self.exit_btn = QPushButton("退出程序")
        self.min_btn.clicked.connect(lambda: self.done(1))
        self.exit_btn.clicked.connect(lambda: self.done(2))
        row = QHBoxLayout()
        row.addWidget(self.min_btn)
        row.addWidget(self.exit_btn)
        layout.addLayout(row)
        self.remember_chk = QCheckBox("记住我的选择")
        self.remember_chk.setChecked(remember)
        layout.addWidget(self.remember_chk)
