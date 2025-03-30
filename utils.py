"闲散的工具集。"
# Copyright (C) 2025  thiliapr
# 本文件是 TkTransl 的一部分。
# TkTransl 是自由软件：你可以再分发之和/或依照由自由软件基金会发布的 GNU 通用公共许可证修改之，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 TkTransl 是希望它能有用，但是并无保障; 甚至连可销售和符合某个特定的目的都不保证。请参看 GNU 通用公共许可证，了解详情。
# 你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/>。

import json
import pathlib
from typing import Any, Iterator


def read_work_info() -> dict[str, Any]:
    """
    读取工作配置信息，优先从内存中获取，其次从work.json文件加载。

    该函数实现了以下功能：
    1. 首先检查全局变量中是否已存在 WORK_INFO
    2. 如果存在，直接返回该变量（避免重复读取文件）
    3. 如果不存在，从 work.json 文件读取配置

    Returns:
        包含工作配置信息的字典
    """
    if "WORK_INFO" in globals():  # 如果已经定义`WORK_INFO`，使用其作为工作信息
        return globals()["WORK_INFO"]  # 为了避免检查，从`globals()`读取工作信息
    else:
        with open("work.json", encoding="utf-8") as f:
            return json.load(f)


def read_glossary(config: dict[str, any]) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """
    从配置文件读取并解析三种类型的术语表词典。

    Args:
        config: 包含术语表配置的字典，应包含以下可选键:
            - "pre": 译前词典配置
            - "post": 译后词典配置
            - "gpt": GPT词典配置
            每个配置应包含以下可选键:
                - "file" (list[str]): 术语表文件路径列表
                - "list" (list[dict]): 直接指定的术语项列表

    Returns:
        包含三个元素的元组，按顺序为:
            1. 译前词典
            2. 译后词典
            3. GPT词典

        每个词典项为包含以下键的字典:
            - "source": 源文本 (必选)
            - "target": 目标文本 (必选)
            - "description": 描述文本 (仅GPT词典可选)

    文件格式说明:
        - 每行一个术语项，格式为: 源文本->目标文本
        - 支持行内注释: 使用 // 符号
        - 空行会被忽略
        - GPT词典专用: 可使用 #符号添加描述
          示例: 源文本->目标文本 #这是描述

    配置示例:
        {
            "pre": {
                "file": ["pre_dict.txt"],
                "list": [{"source": "A", "target": "B"}]
            },
            "gpt": {
                "file": ["gpt_dict.txt"]
            }
        }
    """
    pre_dict = []  # 译前词典
    post_dict = []  # 译后词典
    gpt_dict = []  # GPT词典

    # 处理每种词典类型
    for dict_type, glossary in [("pre", pre_dict), ("post", post_dict), ("gpt", gpt_dict)]:
        if dict_type not in config:
            continue  # 如果配置中没有该类型，跳过

        # 处理文件中的术语
        for dict_file in config[dict_type].get("file", []):
            with open(dict_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("//"):
                        continue  # 跳过空行和注释

                    # 移除行内注释
                    line = line.split("//")[0].strip()
                    if "->" not in line:
                        continue  # 跳过无效行

                    # 分割源文本和目标文本
                    source, target = [part.strip() for part in line.split("->", 1)]
                    entry = {"source": source, "target": target}

                    # 处理GPT词典的特殊描述字段
                    if dict_type == "gpt" and " #" in target:
                        target, description = target.split(" #", 1)
                        entry.update({
                            "target": target.strip(),
                            "description": description.strip()
                        })

                    glossary.append(entry)

        # 添加直接配置的术语项
        glossary.extend(
            item for item in config[dict_type].get("list", [])
            if "source" in item and "target" in item
        )

    return pre_dict, post_dict, gpt_dict


def read_text_to_translate(project_path: str) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """
    递归查找项目目录中所有需要翻译的文本内容，以迭代器形式返回。

    该迭代器会:
    1. 递归扫描项目目录下所有.json文件
    2. 解析每个JSON文件内容
    3. 筛选出需要翻译的条目(不含target字段且source字段不为空)
    4. 为每个条目添加原始位置信息
    5. 以迭代器形式逐个返回条目

    Args:
        project_path: 项目根目录路径，字符串类型

    Yields:
        元组，其中:
        - 第一个元素: JSON文件路径
        - 第二个元素: 需要翻译的条目字典，包含:
            * source_index: 条目在原文件中的位置索引
            * source: 原文(必选)
            * speaker: 说话人(可选)
            * 其他原始字段
    """
    # 递归查找所有JSON文件
    for json_file in pathlib.Path(project_path).glob("**/*.json"):
        with open(json_file, "r", encoding="utf-8") as file:
            file_content = json.load(file)

        # 筛选需要翻译的有效条目
        valid_entries = [
            {"index": idx, **entry}
            for idx, entry in enumerate(file_content)
            if entry.get("source") and not entry.get("target")
        ]

        # 只添加有需要翻译内容的文件
        if valid_entries:
            yield json_file, valid_entries
