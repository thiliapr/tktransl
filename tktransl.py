"TkTransl 程序主入口模块。"
# 本文件是 tktransl 的一部分
# SPDX-FileCopyrightText: 2025 thiliapr <thiliapr@tutanota.com>
# SPDX-FileContributor: thiliapr <thiliapr@tutanota.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

import argparse
import threading
import time
import warnings
import pathlib
from typing import Any, Union

import orjson
from tqdm import tqdm
from utils import read_translation_dict, read_gpt_dict, read_texts_to_translate
from sakurallm import TranslateError, TranslationCountError, batch_translate

DEFAULT_BATCH_SIZE = 7
DEFAULT_HISTORY_SIZE = 2
DEFAULT_TIMEOUT = 30
DEFAULT_TOP_P = 0.8
DEFAULT_TEMPRATURE = 0.3


def thread_wrapper(
    lock: threading.Lock,
    result_container: list[Union[list[dict[str, Any]], TranslateError]],
    *args,
    **kwargs
) -> None:
    """
    线程安全的翻译函数，将翻译结果存入共享变量。

    该函数设计用于多线程环境，确保对共享变量的安全访问。它会先清空结果指针，
    然后执行实际翻译，最后将结果存入共享变量。

    Args:
        lock: 线程锁对象，用于同步对共享变量的访问
        result_container: 共享的结果列表指针，用于存储翻译结果的列表。结果为TranslateError时，代表翻译错误
        *args: 传递给batch_translate函数的位置参数
        **kwargs: 传递给batch_translate函数的关键字参数
    """
    # 执行实际翻译
    try:
        result = batch_translate(*args, **kwargs)
    except TranslateError as e:
        result = e

    # 存储翻译结果
    with lock:
        result_container.append(result)


def main():
    # ==================== 初始化阶段 ====================
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="TkTransl 翻译工具")
    parser.add_argument("project_path", type=str, help="待翻译项目的路径")
    parser.add_argument("endpoints", type=str, nargs="+", help="API端点列表，至少一个，示例：`http://127.0.0.1:8000`")
    parser.add_argument("-b", "--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="每次翻译的文本数量，默认为 %(default)s")
    parser.add_argument("-i", "--history-size", type=int, default=DEFAULT_HISTORY_SIZE, help="翻译时提供给模型的历史翻译记录的数量，默认为 %(default)s")
    parser.add_argument("-s", "--stream-output", action="store_true", help="启用流式输出模式，逐条显示翻译结果")
    parser.add_argument("-p", "--pre-dict", type=str, action="append", default=[], help="译前处理术语表文件路径，可以多次指定")
    parser.add_argument("-o", "--post-dict", type=str, action="append", default=[], help="译后处理术语表文件路径，可以多次指定")
    parser.add_argument("-g", "--gpt-dict", type=str, action="append", default=[], help="GPT专用术语表文件路径，可以多次指定")
    parser.add_argument("-t", "--timeout", type=float, default=DEFAULT_TIMEOUT, help="API请求超时时间（秒），默认为 %(default)s")
    parser.add_argument("--top-p", type=float, default=DEFAULT_TOP_P, help="设置生成模型的 top_p 参数，默认为 %(default)s")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPRATURE, help="设置生成模型的 temperature 参数，默认为 %(default)s")
    parser.add_argument("--presence-penalty", type=float, default=0.0, help="设置生成模型的 presence_penalty 参数，默认为 %(default)s")
    parser.add_argument("--frequency-penalty", type=float, default=0.0, help="设置生成模型的 frequency_penalty 参数，默认为 %(default)s")
    parser.add_argument("--no-builtin-pre-dict", action="store_true", help="禁用内置的译前处理术语表")
    parser.add_argument("--no-builtin-post-dict", action="store_true", help="禁用内置的译后处理术语表")
    parser.add_argument("--no-builtin-gpt-dict", action="store_true", help="禁用内置的GPT专用术语表")
    parser.add_argument("--proxy", type=str, default=None, help="代理服务器地址，默认无代理")
    args = parser.parse_args()

    # 如果启用了流式输出，但有多个API端点，则禁用流式输出模式，因为多API并行时不支持流式显示
    if (stream_output := args.stream_output) and len(args.endpoints) > 1:
        stream_output = False
        warnings.warn(f"已禁用流式输出模式（多API并行时不支持流式显示）。当前配置API数量: {len(args.endpoints)}。")

    # 添加内置的术语表文件路径
    pre_dict = args.pre_dict
    post_dict = args.post_dict
    gpt_dict = args.gpt_dict
    if not args.no_builtin_pre_dict:
        pre_dict.append(pathlib.Path(__file__).parent / "library/preDict.txt")
    if not args.no_builtin_post_dict:
        post_dict.append(pathlib.Path(__file__).parent / "library/postDict.txt")
    if not args.no_builtin_gpt_dict:
        gpt_dict.append(pathlib.Path(__file__).parent / "library/gptDict.txt")

    # 读取术语表（译前处理、译后处理、GPT专用）
    pre_dict = read_translation_dict(pre_dict)
    post_dict = read_translation_dict(post_dict)
    gpt_dict = read_gpt_dict(gpt_dict)

    # ==================== 文件处理循环 ====================
    # 处理每个待翻译文件
    for file, untranslated_texts in read_texts_to_translate(args.project_path):
        if not untranslated_texts:
            continue  # 跳过空文件

        # 初始化进度跟踪
        total_texts = len(untranslated_texts)
        progress_bar = tqdm(desc=file.name, total=total_texts)

        # 应用译前翻译术语替换
        for source in untranslated_texts:
            for entry in pre_dict:
                source["source"] = source["source"].replace(entry["source"], entry["target"])

        # ============== 并行翻译核心逻辑 ==============
        # 初始化API工作池 (endpoint, 状态锁, 结果引用, 处理中批次)
        api_workers = [
            (endpoint, threading.Lock(), [None], [])
            for endpoint in args.endpoints
        ]

        translated_results = []  # 最终翻译结果存储
        dynamic_batch_size = args.batch_size  # 动态调整的批次大小

        while len(translated_results) < total_texts:
            for endpoint, lock, result_container, processing_texts in api_workers:
                with lock:
                    # 跳过忙碌的工作线程
                    if not result_container:
                        continue

                    # 处理完成结果
                    batch_result = result_container[0]

                    # 成功处理批次
                    if isinstance(batch_result, list):
                        # 应用译后翻译术语替换
                        for target in batch_result:
                            for entry in post_dict:
                                target["target"] = target["target"].replace(entry["source"], entry["target"])

                        # 合并并排序结果
                        translated_results.extend(batch_result)
                        translated_results.sort(key=lambda x: x["index"])

                        # 重置动态批次大小为初始值
                        dynamic_batch_size = args.batch_size

                        # 更新进度
                        progress_bar.update(len(batch_result))
                    # 翻译过程中发生错误
                    elif isinstance(batch_result, TranslateError):
                        # 仅在流式输出模式时，显示发生了什么错误
                        if stream_output:
                            print(f"发生翻译错误: {batch_result}")

                        # 释放原文并重新排序
                        untranslated_texts.extend(processing_texts)
                        untranslated_texts.sort(key=lambda x: x["index"])

                        # 翻译结果数量与原文数量不一致
                        if isinstance(batch_result, TranslationCountError):
                            # 减少一半文本重试
                            dynamic_batch_size //= 2

                    # 清空处理中文本列表和结果容器
                    processing_texts.clear()
                    result_container.clear()

                    # 翻译下一批文本
                    if untranslated_texts:
                        # 获取要翻译的文本，并将其添加至处理列表
                        text_to_translate = untranslated_texts[:dynamic_batch_size]
                        processing_texts.extend(text_to_translate)

                        # 启动翻译线程
                        threading.Thread(
                            target=thread_wrapper,
                            args=(lock, result_container, text_to_translate, translated_results[-args.history_size:], gpt_dict, endpoint),
                            kwargs={
                                "stream_output": stream_output,
                                "timeout": args.timeout,
                                "proxy": args.proxy,
                                "top_p": args.top_p,
                                "temperature": args.temperature,
                                "presence_penalty": args.presence_penalty,
                                "frequency_penalty": args.frequency_penalty
                            },
                            daemon=True
                        ).start()

                        # 从待翻译文本列表删除处理中的文本
                        untranslated_texts = untranslated_texts[dynamic_batch_size:]

            # 避免CPU空转
            time.sleep(1)

        # 结束进度条
        progress_bar.close()

        # ============== 结果写入阶段 ==============
        # 读取原始文件并更新翻译结果
        with open(file, "rb") as f:
            data = orjson.loads(f.read())

        # 合并翻译结果到原始数据
        for entry in translated_results:
            data[entry["index"]].update(
                {k: v for k, v in entry.items() if k != "index"}
            )

        # 写回文件
        with open(file, "wb") as f:
            f.write(orjson.dumps(data))


if __name__ == "__main__":
    main()
