"""运行库检测脚本：检查 Python 版本与项目依赖是否就绪。"""
import importlib
import importlib.util
import sys

required = [
    ("PyQt5", "PyQt5 GUI 库（必需）"),
    ("PySide6", "PySide6 GUI 库（可选，PyQt5 缺失时的备选）"),
    ("sqlite3", "Python 内置 SQLite 支持（必需）"),
]


def main():
    print("=" * 50)
    print("手游日常助手 Gachi Game Quest Helper - 运行库检测")
    print("=" * 50)
    print(f"Python 版本：{sys.version.split()[0]}  ({sys.executable})")
    print("-" * 50)

    all_ok = True
    for mod, desc in required:
        spec = importlib.util.find_spec(mod)
        if spec is None:
            status = "[缺失]"
            all_ok = False if mod != "PySide6" else all_ok
        else:
            ver = "(内置)"
            try:
                md = importlib.import_module(mod)
                if hasattr(md, "__version__"):
                    ver = f"v{md.__version__}"
            except Exception:
                pass
            status = f"[就绪] {ver}"
        print(f"  {mod:<10} {status}")
        print(f"             {desc}")

    print("-" * 50)
    has_qt = (
        importlib.util.find_spec("PyQt5") is not None
        or importlib.util.find_spec("PySide6") is not None
    )
    if has_qt and importlib.util.find_spec("sqlite3") is not None:
        print("结论：运行环境满足要求，可直接运行 python main.pyw")
    else:
        print("结论：缺少必需依赖，请执行 pip install -r requirements.txt")
    print("=" * 50)


if __name__ == "__main__":
    main()
