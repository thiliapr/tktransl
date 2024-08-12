# Copyright (C) 2024  thiliapr
# 本文件是 TkTransl 的一部分。
# TkTransl 是自由软件：你可以再分发之和/或依照由自由软件基金会发布的 GNU 通用公共许可证修改之，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 TkTransl 是希望它能有用，但是并无保障; 甚至连可销售和符合某个特定的目的都不保证。请参看 GNU 通用公共许可证，了解详情。
# 你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/>。

"""
定义了一些对翻译器的操作。
"""

from utils.translate import BaseTranslator
from utils.extra import LogLevel, log
from utils.translators.sakurallm import SakuraLLMTranslator


def get_translator(translator_id: str) -> type[BaseTranslator]:
    """
    根据标识符返回相应的翻译器。
    """

    if translator_id == "sakurallm":
        return SakuraLLMTranslator

    log("get_translator()", f"创建翻译器时发现了未知的翻译器: {translator_id}", level=LogLevel.Error)
    return None
