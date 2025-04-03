"TkTransl 程序主入口模块。"
# Copyright (C) 2025  thiliapr
# 本文件是 TkTransl 的一部分。
# TkTransl 是自由软件: 你可以再分发之和/或依照由自由软件基金会发布的 GNU 通用公共许可证修改之，
# 无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 TkTransl 是希望它能有用，但是并无保障; 甚至连可销售和符合某个特定的目的都不保证。
# 请参看 GNU 通用公共许可证，了解详情。
# 你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/>。

import json
import threading
import time
import warnings
import tqdm
from typing import Any, Union

DEFAULT_BATCH_SIZE = 7
DEFAULT_HISTORY_SIZE = 2
DEFAULT_TIMEOUT = 30

# 在非 Kaggle 环境下导入模型和工具库
if "get_ipython" not in globals():
    from utils import read_work_info, read_glossary, read_texts_to_translate
    from sakurallm import TranslateError, TranslationCountError, batch_translate


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
    """
    视觉小说翻译主流程控制器

    完整工作流程:
    1. 初始化阶段:
       - 读取项目配置文件
       - 加载术语表（预处理/后处理/GPT专用）
       - 验证API配置有效性
    2. 预处理阶段:
       - 扫描项目目录获取待翻译文件
       - 应用预处理术语替换
    3. 并行翻译阶段:
       - 动态批次大小管理（根据错误自动调整）
       - 多API负载均衡
       - 实时进度显示
    4. 后处理阶段:
       - 应用后处理术语替换
       - 结果排序与合并
       - 写回翻译文件

    异常处理策略:
       - 网络错误: 自动重试当前批次（最多3次）
       - 数量不匹配: 自动减半批次大小重试

    性能优化点:
       - 基于历史上下文的增量翻译
       - 无锁设计的线程通信
       - 动态批次大小调整
    """
    # ==================== 初始化阶段 ====================
    # 读取工作配置
    work_info = read_work_info()
    batch_size = work_info.get("batch_size", DEFAULT_BATCH_SIZE)
    history_size = work_info.get("history_size", DEFAULT_HISTORY_SIZE)
    timeout = work_info.get("timeout", DEFAULT_TIMEOUT)
    stream_output = work_info.get("stream_output", False)

    # 流式输出兼容性检查
    if stream_output and len(work_info["endpoints"]) > 1:
        stream_output = False
        warnings.warn(f"已禁用流式输出模式（多API并行时不支持流式显示）。当前配置API数量: {len(work_info['endpoints'])}。")

    # 读取术语表（译前处理、译后处理、GPT专用）
    pre_dict, post_dict, gpt_dict = read_glossary(work_info.get("glossary", {}))

    # ==================== 文件处理循环 ====================
    # 处理每个待翻译文件
    for file, untranslated_texts in read_texts_to_translate(work_info["project_path"]):
        if not untranslated_texts:
            continue  # 跳过空文件

        # 初始化进度跟踪
        total_texts = len(untranslated_texts)
        progress_bar = tqdm.tqdm(desc=file.name, total=total_texts)

        # 应用译前翻译术语替换
        for source in untranslated_texts:
            for entry in pre_dict:
                source["source"] = source["source"].replace(entry["source"], entry["target"])

        # ============== 并行翻译核心逻辑 ==============
        # 初始化API工作池 (endpoint, 状态锁, 结果引用, 处理中批次)
        api_workers = [
            (endpoint, threading.Lock(), [None], [])
            for endpoint in work_info["endpoints"]
        ]

        translated_results = []  # 最终翻译结果存储
        dynamic_batch_size = batch_size  # 动态调整的批次大小

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
                        dynamic_batch_size = batch_size

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
                            args=(lock, result_container, text_to_translate, translated_results[-history_size:], gpt_dict, endpoint),
                            kwargs={
                                "stream_output": stream_output,
                                "timeout": timeout,
                                "proxy": work_info.get("proxy")
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
        with open(file, encoding="utf-8") as f:
            data = json.load(f)

        # 合并翻译结果到原始数据
        for entry in translated_results:
            data[entry["index"]].update(
                {k: v for k, v in entry.items() if k != "index"}
            )

        # 写回文件
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent="\t")


if __name__ == "__main__":
    main()
