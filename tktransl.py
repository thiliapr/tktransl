#!/usr/bin/env python3

# Copyright (C) 2024  thiliapr
# 本文件是 TkTransl 的一部分。
# TkTransl 是自由软件：你可以再分发之和/或依照由自由软件基金会发布的 GNU 通用公共许可证修改之，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 TkTransl 是希望它能有用，但是并无保障; 甚至连可销售和符合某个特定的目的都不保证。请参看 GNU 通用公共许可证，了解详情。
# 你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/>。

"""
TkTransl的程序入口。
"""

import json
import os
from asyncio import run
from pathlib import Path
from argparse import ArgumentParser
from utils.extra import LogLevel, LogLevelsAllowed, log
from utils.load import load_dicts, load_messages
from utils.translate import BaseTranslator, translate_async
from utils.translators import get_translator


def main():
    """
    程序的主入口。
    """

    # 显示程序信息
    print(
        "TkTransl  Copyright (C) 2024  thiliapr\n"
        "This program comes with ABSOLUTELY NO WARRANTY.\n"
        "This is free software, and you are welcome to redistribute it under certain conditions.\n"
        "Source Code: https://github.com/thiliapr/tktransl\n"
    )

    # 获取资源库路径
    library_path = Path(__file__).absolute().parent / "library"

    # 解析参数
    parser = ArgumentParser(description="由thiliapr开发的翻译工具。")
    parser.add_argument("-i", "--input", type=Path, required=True, dest="input_path", help="要翻译的文件")
    parser.add_argument("-o", "--output", type=Path, required=True, dest="output_path", help="翻译的输出路径")
    parser.add_argument("-c", "--config", type=Path, required=True, help="配置文件")
    parser.add_argument("--pre-dict", type=Path, action="append", default=[], help="译前词典")
    parser.add_argument("--post-dict", type=Path, action="append", default=[], help="译后词典")
    parser.add_argument("--gpt-dict", type=Path, action="append", default=[], help="GPT词典")
    parser.add_argument("--not-allowed-logging-level", action="append", dest="not_allowed_logging_levels", default=[], help="不允许某个等级的日志输出。等级: [Debug, Info, Warning, Error, Fatal]")
    parser.add_argument("--builtin-pre-dict", action="append_const", const=(library_path / "preDict.txt"), dest="pre_dict", help="使用内置的译前词典。")
    parser.add_argument("--builtin-post-dict", action="append_const", const=(library_path / "postDict.txt"), dest="post_dict", help="使用内置的译后词典。")
    parser.add_argument("--builtin-gpt-dict", action="append_const", const=(library_path / "gptDict.txt"), dest="gpt_dict", help="使用内置的GPT词典。")
    args = parser.parse_args()

    # 创建输出目录
    os.makedirs(args.output_path, exist_ok=True)

    # 日志输出设置
    for level in LogLevelsAllowed.copy():
        if level.name in args.not_allowed_logging_levels:
            LogLevelsAllowed.discard(level)

    # 读取词典
    dicts = load_dicts((args.pre_dict, args.post_dict, args.gpt_dict))

    # 读取配置
    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    # 加载文本
    all_messages = load_messages(args.input_path, args.output_path)
    log("Main", f"未翻译的文本有{len(all_messages)}个文件，{len([msg for file_msgs in all_messages.values() for msg in file_msgs])}条文本，{len([char for file_msgs in all_messages.values() for msg in file_msgs for char in msg.source])}个字符。")

    # 从配置中加载翻译器
    translators: list[BaseTranslator] = []

    for translator_id, translators_config in config["translators"].items():
        for translator_config in translators_config:
            translators.append(get_translator(translator_id)(**(config.get(translator_id, {}) | translator_config)))

    if not translators:
        log("Main", "没有翻译器以供翻译。", level=LogLevel.Fatal)
        return

    # 开始翻译
    for filepath, file_messages in all_messages.items():
        if not file_messages:
            continue

        # 初始化变量
        interrupted = False

        # 等待翻译完成
        try:
            run(translate_async(filepath, file_messages, translators, dicts))
        except KeyboardInterrupt:
            interrupted = True

        # 保存翻译结果
        if (args.output_path / filepath).exists():
            with open(args.output_path / filepath, encoding="utf-8") as f:
                output = json.load(f)
        else:
            output = []

        output = sorted(output + [msg.jsonify() for msg in file_messages if msg.translation], key=lambda x: x["index"])

        with open(args.output_path / filepath, mode="w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent="\t")

        # 如果被打断就退出翻译
        if interrupted:
            log("Main", "翻译被打断，正在退出...")
            break


if __name__ == "__main__":
    main()
