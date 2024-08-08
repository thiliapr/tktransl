# Copyright (C) 2024  thiliapr
# 本文件是 TkTransl 的一部分。
# TkTransl 是自由软件：你可以再分发之和/或依照由自由软件基金会发布的 GNU 通用公共许可证修改之，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 TkTransl 是希望它能有用，但是并无保障;甚至连可销售和符合某个特定的目的都不保证。请参看 GNU 通用公共许可证，了解详情。
# 你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/>。

from sys import stdout, stderr
from datetime import datetime
from enum import Enum


class LogLevel(Enum):
    Debug = "DEBUG"
    Info = "INFO"
    Warning = "WARN"
    Error = "ERROR"
    Fatal = "FATAL"


LogLevelsAllowed = {level for level in LogLevel}


def escape(msg: str) -> str:
    """
    返回一个单行的字符串。
    """

    return msg.replace("\\", "\\\\").replace("\n", "\\n")


def unescape(msg: str) -> str:
    """
    返回一个反转义的文本。
    """

    src = ""

    escape = False
    for char in msg:
        if escape:
            if char == "n":
                src += "\n"
            else:
                src += char
            escape = False
        elif char == "\\":
            escape = True
        else:
            src += char
    
    return src


def log(by: str, msg: str, level: LogLevel = LogLevel.Info):
    """
    日志。
    """

    if level in LogLevelsAllowed:
        print(
            " ".join([datetime.strftime(datetime.now(), "[%H:%M:%S]"), f"[{level.value}]", f"[{by}]:", escape(msg)]),
            file=stderr if (level == LogLevel.Error) or (level == LogLevel.Fatal) else stdout
        )
