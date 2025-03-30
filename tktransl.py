"TkTransl 程序主入口模块。"

# Copyright (C) 2025  thiliapr
# 本文件是 TkTransl 的一部分。
# TkTransl 是自由软件：你可以再分发之和/或依照由自由软件基金会发布的 GNU 通用公共许可证修改之，
# 无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 TkTransl 是希望它能有用，但是并无保障; 甚至连可销售和符合某个特定的目的都不保证。
# 请参看 GNU 通用公共许可证，了解详情。
# 你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/>。

import json
import threading
import time
import warnings
from functools import partial
from typing import Any

DEFAULT_BATCH_SIZE = 7
DEFAULT_HISTORY_SIZE = 2
DEFAULT_TIMEOUT = 30

# 在非Jupyter环境下导入模型和工具库
if "get_ipython" not in globals():
    from utils import read_work_info, read_glossary, read_text_to_translate
    from sakurallm import batch_translate


def thread_translate(
    lock: threading.Lock,
    result_ptr: list[list[dict[str, Any]]],
    *args,
    **kwargs
) -> None:
    """
    线程安全的翻译函数，将翻译结果存入共享变量

    该函数设计用于多线程环境，确保对共享变量的安全访问。它会先清空结果指针，
    然后执行实际翻译，最后将结果存入共享变量。

    Args:
        lock: 线程锁对象，用于同步对共享变量的访问
        result_ptr: 共享的结果列表指针，
            用于存储翻译结果的结构为列表的列表
        *args: 传递给batch_translate函数的位置参数
        **kwargs: 传递给batch_translate函数的关键字参数
    """
    # 清空结果指针
    with lock:
        result_ptr.clear()

    # 执行实际翻译
    result = batch_translate(*args, **kwargs)

    # 存储翻译结果
    with lock:
        result_ptr.append(result)


def main():
    """
    主函数，协调整个翻译流程

    主要流程:
    1. 读取工作配置和术语表
    2. 预处理待翻译文本
    3. 并行调用翻译API
    4. 保存翻译结果
    """
    # 读取工作配置
    work_info = read_work_info()
    batch_size = work_info.get("batch_size", DEFAULT_BATCH_SIZE)
    history_size = work_info.get("history_size", DEFAULT_HISTORY_SIZE)
    timeout = work_info.get("timeout", DEFAULT_TIMEOUT)
    stream = work_info.get("stream", False)

    # 多API时不能流式输出
    if stream and len(work_info["api"]) > 1:
        warnings.warn(f"多API时不能流式输出。现在有{len(work_info['api'])}。")

    # 读取术语表（译前处理、译后处理、GPT专用）
    pre_dict, post_dict, gpt_dict = read_glossary(work_info.get("glossary", {}))

    # 处理每个待翻译文件
    for file, sources in read_text_to_translate(work_info["project_path"]):
        if not sources:
            continue  # 跳过空文件

        # 储存要翻译的文本的数量
        number_sources = len(sources)

        # 应用译前翻译术语替换
        for source in sources:
            for entry in pre_dict:
                source["source"] = source["source"].replace(entry["source"], entry["target"])

        targets = []
        # 准备API线程池 (API, 线程锁, 结果指针)
        api_pool = [(api, threading.Lock(), [None]) for api in work_info["api"]]

        # 分批处理所有待翻译文本
        while len(targets) < number_sources:
            for api, lock, result_ptr in api_pool:
                with lock:
                    if not result_ptr:
                        continue

                    # 准备下一批翻译
                    translate_func = partial(
                        threading.Thread,
                        target=thread_translate,
                        args=(lock, result_ptr, sources[:batch_size], targets[-history_size:], gpt_dict, api),
                        kwargs={
                            "stream": stream,
                            "timeout": timeout
                        }
                    )

                    # 该API线程空闲
                    if not result_ptr[0]:
                        # 启动翻译线程
                        translate_func().start()
                        sources = sources[batch_size:]
                    else:  # 该API线程已完成
                        # 应用译后翻译术语替换
                        for result in result_ptr[0]:
                            for entry in post_dict:
                                result["target"] = result["target"].replace(entry["source"], entry["target"])

                        # 收集结果并排序
                        targets.extend(result_ptr[0])
                        targets.sort(key=lambda x: x["index"])

                        if sources:
                            # 启动新翻译线程
                            translate_func().start()
                            sources = sources[batch_size:]
            time.sleep(1)

        # 读取原始文件并更新翻译结果
        with open(file, encoding="utf-8") as f:
            data = json.load(f)

        # 合并翻译结果到原始数据
        for entry in targets:
            data[entry["index"]].update(
                {k: v for k, v in entry.items() if k != "index"}
            )

        # 写回文件
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent="\t")


if __name__ == "__main__":
    main()
