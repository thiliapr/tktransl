"闲散的工具集。"
# 本文件是 tktransl 的一部分
# SPDX-FileCopyrightText: 2025 thiliapr <thiliapr@tutanota.com>
# SPDX-FileContributor: thiliapr <thiliapr@tutanota.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

import orjson
import random
import pathlib
from typing import Any, Iterator


def read_translation_dict(files: list[pathlib.Path]) -> list[dict[str, str]]:
    """
    从指定的文件列表中读取译前/译后处理词典。  
    每个文件应包含多行，每行格式为: `源文本->目标文本`。  
    支持单行注释和空行，注释以 `//` 开头。  
    注意: 不支持行内注释（比如说，`fubuki->吹雪  // this is en_to_zh`是不合法的）。  
    格式示例: `Hello->你好`（`->`前后没有空格）。
    
    Args:
        files: 包含术语表文件路径的列表，每个文件应为文本格式。
    
    Returns:
        包含译前/译后处理词典的列表，每个词典项为字典，包含以下键:
            - "source": 源文本
            - "target": 目标文本
    
    Examples:
        >>> files = [pathlib.Path("pre_dict.txt")]
        >>> pre_dict = read_translation(files)
        >>> print(pre_dict)
        [{'source': 'Hello', 'target': '你好'}, {'source': 'World', 'target': '世界'}]
    """
    # 初始化译前/译后处理词典列表
    translation = []

    # 遍历每个文件
    for file in files:
        with open(file, encoding="utf-8") as f:
            # 逐行读取文件内容
            for line in f:
                # 清理行内容，去除首尾空格
                line = line.strip()

                # 跳过空行和注释行、无效行
                if not line or line.startswith("//") or "->" not in line:
                    continue

                # 分割源文本和目标文本
                source, target = [part.strip() for part in line.split("->", 1)]

                # 添加到词典
                translation.append({"source": source, "target": target})

    return translation


def read_gpt_dict(files: list[pathlib.Path]) -> list[dict[str, str]]:
    """
    从指定的文件列表中读取GPT专用词典。  
    每个文件应包含多行，每行格式为: `源文本->目标文本 #描述`。  
    支持单行注释和空行，注释以 `//` 开头。  
    注意: 不支持行内注释（比如说，`fubuki->吹雪  // this is en_to_zh`是不合法的）。  
    格式示例: `shirakami fubuki->白上吹雪 #虚拟主播，Hololive成员`（`->`前后没有空格；` #`前有空格，后面没有）。

    Args:
        files: 包含GPT词典文件路径的列表，每个文件应为文本格式。
    
    Returns:
        包含GPT词典的列表，每个词典项为字典，包含以下键:
            - "source": 源文本
            - "target": 目标文本
            - "description": 描述文本（可选）
    
    Examples:
        >>> files = [pathlib.Path("gpt_dict.txt")]
        >>> gpt_dict = read_gpt_dict(files)
        >>> print(gpt_dict)
        [{'source': 'Hello', 'target': '你好', 'description': '问候语'}, {'source': 'World', 'target': '世界'}]
    """
    # 初始化 GPT 词典列表
    gpt_dict = []

    # 遍历每个文件
    for file in files:
        with open(file, encoding="utf-8") as f:
            # 逐行读取文件内容
            for line in f:
                # 清理行内容，去除首尾空格
                line = line.strip()

                # 跳过空行和注释行、无效行
                if not line or line.startswith("//") or "->" not in line:
                    continue

                # 分割源文本和目标文本
                source, target = [part.strip() for part in line.split("->", 1)]
                entry = {"source": source, "target": target}

                # 处理描述字段
                if " #" in target:
                    target, description = target.split(" #", 1)
                    entry.update({
                        "target": target.strip(),
                        "description": description.strip()
                    })

                gpt_dict.append(entry)

    return gpt_dict


def read_texts_to_translate(project_path: str) -> Iterator[tuple[pathlib.Path, list[dict[str, Any]]]]:
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
        with open(json_file, "rb") as file:
            file_content = orjson.loads(file.read())

        # 筛选需要翻译的有效条目（source.strip() 非空且 target 字段不存在或为空）
        valid_entries = [
            {"index": idx, **entry}
            for idx, entry in enumerate(file_content)
            if entry.get("source", "").strip() and not entry.get("target")
        ]

        # 只添加有需要翻译内容的文件
        if valid_entries:
            yield json_file, valid_entries


def generate_placeholder_token(base_name: str, text: str, max_attempts: int = 10) -> str:
    """
    生成一个在给定文本中不存在的唯一标记。
    标记格式为：<base_name-random_number>，其中random_number是0到65535(2^16)之间的随机数。

    Args:
        base_name: 标记的基础名称，将作为生成标记的前缀
        text: 要检查的文本内容，确保生成的标记不在其中
        max_attempts: 最大尝试次数

    Returns:
        生成的唯一标记

    Examples:
        >>> text = "This is a sample text containing <test-123>"
        >>> token = generate_unique_token("test", text)
        >>> print(token)
        <test-456>  # 随机生成的数字，保证不在原文本中
    """
    max_attempts = 10
    for _ in range(max_attempts):
        token = f"<{base_name}-{random.randint(0, 2**16)}>"
        if token not in text:
            return token
    raise RuntimeError(f"无法为`{base_name}`生成唯一标记")
