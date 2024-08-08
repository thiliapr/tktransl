# Copyright (C) 2024  thiliapr
# 本文件是 TkTransl 的一部分。
# TkTransl 是自由软件：你可以再分发之和/或依照由自由软件基金会发布的 GNU 通用公共许可证修改之，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 TkTransl 是希望它能有用，但是并无保障;甚至连可销售和符合某个特定的目的都不保证。请参看 GNU 通用公共许可证，了解详情。
# 你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/>。 

import json
from pathlib import Path
from typing import Optional
from utils.translate import Message


def load_dicts(paths: tuple[list[Path], list[Path], list[Path]]) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str, Optional[str]]]]:
    """
    加载字典。

    Args:
        paths(tuple):
            list[Path]: 译前词典。
            list[Path]: 译后词典。
            list[Path]: GPT词典。
    
    Returns:
        list[tuple[原文, 译文]]: 译前词典。
        list[tuple[原文, 译文]]: 译后词典。
        list[tuple[原文, 译文, Optional[额外信息]]]: GPT词典。
    """
    
    # 读取词典
    dicts: tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str, Optional[str]]]] = [], [], []
    for index, dict_paths in enumerate(paths):
        for dict_path in dict_paths:
            with open(dict_path, encoding="utf-8") as f:
                for entry_str in f.readlines():
                    # 忽略注释
                    entry_str = entry_str.split("//", 1)[0].strip()

                    # 跳过空行
                    if not entry_str:
                        continue
                    elif "->" not in entry_str:
                        raise Exception(f"Entry missing \"->\": {entry_str}")

                    # 分割原文、译文等
                    src, other = entry_str.split("->", 1)
                    src = src.replace("\\->", "->")

                    if index == 2:
                        other = other.split(" #", 1)
                        dest, info = other[0], other[1] if len(other) > 1 else None
                    else:
                        dest = other
                    
                    # 添加词条至词典
                    if index == 2:
                        dicts[index].append((src, dest, info))
                    else:
                        dicts[index].append((src, dest)) #type: ignore
    
    return dicts


def load_messages(input_path: Path, output_path: Path) -> dict[str, list[Message]]:
    """
    加载要翻译的文本（不包括已翻译的文本）。

    Returns:
        dict[文件的相对路径, list[要翻译的文本]]
    """

    messages: dict[str, list[Message]] = {}
    for message_abspath in sorted(input_path.glob("**/*.json")):
        message_path = message_abspath.relative_to(input_path)

        # 读取翻译的文本
        if (output_path / message_path).exists():
            with open(output_path / message_path, encoding="utf-8") as f:
                messages_translated: list[int] = [message_output["index"] for message_output in json.load(f)]
        else:
            messages_translated: list[int] = []

        # 读取待翻译的文本
        with open(message_abspath, encoding="utf-8") as f:
            messages[str(message_path)] = [
                Message.from_input(message, index)
                for index, message in enumerate(json.load(f))
                if index not in messages_translated
            ]
    
    return messages