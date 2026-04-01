"""主 CLI 入口。"""

import builtins
from datetime import datetime

from src.controllers.console_command import main as run_console_command


_ORIGINAL_PRINT = builtins.print


def _should_prefix_timestamp(line: str) -> bool:
    """只给运行日志加时间戳，尽量不污染菜单与装饰性输出。"""
    stripped = (line or "").strip()
    if not stripped:
        return False
    if stripped.startswith("["):
        return True
    if stripped.startswith(("✓", "✗", ">>>")):
        return True
    ui_prefixes = (
        "╔",
        "║",
        "╚",
        "=",
        "请选择",
        "当前简历:",
        "1. ",
        "2. ",
        "3. ",
        "4. ",
        "5. ",
        "6. ",
        "7. ",
        "0. ",
        "匹配分析结果",
        "生成的打招呼语",
        "批量分析结果",
        "重算结果",
        "投递结果",
        "闭环 Agent 结果",
        "闭环求职 Agent",
        "自动投递已入队岗位",
        "批量分析岗位库",
        "按新分数重算入队状态",
        "创建简历",
        "汇总",
        "状态:",
        "目标实际投递:",
        "累计实际投递:",
        "继续沟通/已沟通:",
        "剩余待投递队列:",
    )
    return not stripped.startswith(ui_prefixes)


def _install_timestamped_print() -> None:
    """为控制台日志统一追加毫秒级时间前缀，便于排查卡顿位置。"""

    def timestamped_print(*args, **kwargs):
        sep = kwargs.pop("sep", " ")
        end = kwargs.pop("end", "\n")
        file = kwargs.pop("file", None)
        flush = kwargs.pop("flush", False)

        message = sep.join(str(arg) for arg in args)
        timestamp = f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}]"

        # 多行输出时给每一行都补时间，避免 banner 和长文本只有首行带前缀。
        lines = message.splitlines(keepends=True)
        if not lines:
            _ORIGINAL_PRINT(timestamp, end=end, file=file, flush=flush, **kwargs)
            return

        formatted_parts: list[str] = []
        for line in lines:
            if _should_prefix_timestamp(line):
                formatted_parts.append(f"{timestamp} {line}")
            else:
                formatted_parts.append(line)

        formatted_message = "".join(formatted_parts)
        if message.endswith(("\n", "\r")):
            _ORIGINAL_PRINT(formatted_message, end="", file=file, flush=flush, **kwargs)
            if end:
                _ORIGINAL_PRINT("", end=end, file=file, flush=flush, **kwargs)
            return

        _ORIGINAL_PRINT(formatted_message, end=end, file=file, flush=flush, **kwargs)

    builtins.print = timestamped_print


def main() -> None:
    """启动交互式控制台控制器。"""
    _install_timestamped_print()
    run_console_command()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 程序已退出")
