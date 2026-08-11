# 手游任务助手 Gacha Game Quest Helper — 无控制台入口
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

# 无控制台入口：用 pythonw 运行本文件可避免托盘常驻程序闪现控制台窗口。
# 打包 (.exe) 时同样建议使用 pythonw / 隐藏控制台。
import sys

from main import main

if __name__ == "__main__":
    main()
