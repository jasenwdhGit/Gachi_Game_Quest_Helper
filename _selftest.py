# -*- coding: utf-8 -*-
import sqlite3
import models
import database as db
from datetime import datetime, date, timedelta

db.init_db()
c = sqlite3.connect("game_tasks.db")
c.executescript("DELETE FROM tasks; DELETE FROM games; DELETE FROM remind_rules;")
c.commit()
c.close()

now = datetime(2026, 8, 17, 10, 0, 0)

print("parse daily   :", models.parse_period_rule("1d@04:00"))
print("parse weekly  :", models.parse_period_rule("7d@0@04:00"))
print("parse biweekly:", models.parse_period_rule("14d@2026-08-08@04:00"))
print("parse monthly :", models.parse_period_rule("1m@01@04:00"))

print("game_time 4:00:", models.to_game_time_str(datetime(2026, 8, 18, 4, 0), 4, 0))
print("game_time 0:00:", models.to_game_time_str(datetime(2026, 8, 18, 4, 0), 0, 0))
print("reverse 28->  :", models.from_game_time_to_real(date(2026, 8, 17), 28, 0))

print("daily init    :", models.compute_initial_deadline("日常", "1d@04:00", now))
print("weekly init   :", models.compute_initial_deadline("周常", "7d@0@04:00", now))
print("biweekly init :", models.compute_initial_deadline("双周常", "14d@2026-08-08@04:00", now))
print("monthly init  :", models.compute_initial_deadline("月常", "1m@01@04:00", now))

dl, comp = models.auto_update_deadline(datetime(2026, 8, 17, 4, 0), True, "日常", "1d@04:00", now)
print("autoreset daily:", dl, comp)
dl, comp = models.auto_update_deadline(datetime(2026, 8, 10, 4, 0), True, "周常", "7d@0@04:00", now)
print("autoreset weekly:", dl, comp)

future = now + timedelta(days=5)
print("red month     :", models.is_red_warning("月常", future, now))
print("red daily     :", models.is_red_warning("日常", future, now))

g = db.add_game("原神", "")
t = db.add_task(g, "每日委托", "日常",
                models.compute_initial_deadline("日常", "1d@04:00", datetime.now()),
                "1d@04:00", True)
db.auto_update_task(t)
print("incomplete daily:", db.count_incomplete_daily())
print("LOGIC_OK")
