"SakuraLLM的翻译部分"
# Copyright (C) 2025  thiliapr
# 本文件是 TkTransl 的一部分。
# TkTransl 是自由软件：你可以再分发之和/或依照由自由软件基金会发布的 GNU 通用公共许可证修改之，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 TkTransl 是希望它能有用，但是并无保障; 甚至连可销售和符合某个特定的目的都不保证。请参看 GNU 通用公共许可证，了解详情。
# 你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/>。

import json
import httpx
import datetime
from typing import Any, Optional, Iterator


SYSTEM_PROMPT = "你是一个视觉小说翻译模型，可以通顺地使用给定的术语表以指定的风格将日文翻译成简体中文，并联系上下文正确使用人称代词，注意不要混淆使役态和被动态的主语和宾语，不要擅自添加原文中没有的特殊符号，也不要擅自增加或减少换行。"
USER_PROMPT_TEMPLATE = """[History]
参考以下术语表（可为空，格式为src->dst #备注）：
[Glossary]
根据以上术语表的对应关系和备注，结合历史剧情和上下文，将下面的文本从日文翻译成简体中文：
[Input]"""


def ask_stream(
    api: str,
    prompt: str,
    temperature: float,
    top_p: float,
    presence_penalty: float,
    frequency_penalty: float,
    proxy: Optional[str] = None,
    timeout: float = 4.0,
) -> Iterator[str]:
    """
    向翻译API发送流式请求并获取翻译结果

    Args:
        api: API基础URL
        prompt: 完整的提示词
        temperature: 控制生成随机性的参数
        top_p: 核采样参数
        presence_penalty: 避免重复话题的参数
        frequency_penalty: 避免重复用词的参数
        proxy: 可选代理设置
        timeout: 请求超时时间(单位: 秒)

    Returns:
        异步生成器，逐块产生翻译结果

    Exceptions:
        RuntimeError: 当API返回非200状态码时抛出
    """
    with httpx.stream(
        "POST",
        f"{api}/v1/chat/completions",
        proxy=proxy,
        timeout=timeout,
        json={
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "stream": True,
            "temperature": temperature,
            "top_p": top_p,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty,
            "n": 1,
            "user": "user"
        }
    ) as response:
        # 检查响应状态
        if response.status_code != 200:
            response.read()
            raise RuntimeError(
                f"API请求失败: 状态码 {response.status_code} - {response.reason_phrase}\n"
                f"响应内容: {response.text}"
            )

        # 处理流式响应
        for line in response.iter_lines():
            if not line:
                continue

            # 解析响应行
            line = line.removeprefix("data: ")
            data = json.loads(line)
            choice = data["choices"][0]

            # 检查是否结束
            if choice.get("finish_reason"):
                response.close()
                break

            # 获取内容增量
            delta = choice["delta"]
            if delta.get("content"):
                yield delta["content"]


def batch_translate(
    sources: list[dict[str, Any]],
    history: list[dict[str, Any]],
    glossary: list[dict[str, Any]],
    api: str,
    stream: bool = False,
    temperature: float = 1.0,
    top_p: float = 1.0,
    presence_penalty: float = 0.0,
    frequency_penalty: float = 0.0,
    proxy: Optional[str] = None,
    timeout: float = 4.0,
) -> list[dict[str, Any]]:
    """
    批量翻译视觉小说文本

    Args:
        sources: 待翻译文本列表，每个字典应包含:
            - source: 原文内容
            - speaker: 说话人名称 (可选)
        history: 历史翻译记录，格式同sources，每个字典还应包含:
            - target: 已翻译内容
            - speaker_target: 说话人译名 (如有speaker)
        glossary: 术语表，每个字典应包含:
            - source: 原文术语
            - target: 译文术语
            - description: 术语说明 (可选)
        api: 翻译API的基础URL
        stream: 是否启用流式输出
        temperature: 控制生成随机性的温度，值越高越随机
        top_p: 核采样参数，控制生成多样性
        presence_penalty: 避免重复话题的，避免重复话题
        frequency_penalty: 避免重复用词的，避免重复用词
        proxy: 代理服务器地址
        timeout: API请求超时时间(秒)

    Returns:
        翻译结果列表，包含原始字段和新增的:
            - target: 翻译内容
            - target_speaker: 说话人译名 (如有speaker)

    Exceptions:
        RuntimeError: 当API请求失败时抛出
    """
    # 准备历史文本
    history_entries = []
    for entry in history:
        # 标准化换行符并添加特殊标记
        text = entry["target"].replace("\r\n", "\n").replace("\n", "<TRNewLine>")

        # 处理带说话人的历史记录
        if entry.get("speaker"):
            text = f"{entry['speaker_target']}「{text.replace('「', '<TRQuoteStart>').replace('」', '<TRQuoteEnd>')}」"

        history_entries.append(text)
    history_text = "历史翻译：" + "<TRNewSeq>".join(history_entries)

    # 准备术语表文本: 格式化为"原文->译文 #说明"的格式
    glossary_text = "\n".join(
        f"{g['source']}->{g['target']}" + (f" #{g['description']}" if g.get("description") else "")
        for g in glossary
    )

    # 准备源文本
    source_entries = []
    for entry in sources:
        # 标准化换行符并添加特殊标记
        text = entry["source"].replace("\r\n", "\n").replace("\n", "<TRNewLine>")

        # 处理带说话人的文本
        if "speaker" in entry:
            text = f"{entry['speaker']}「{text.replace('「', '<TRQuoteStart>').replace('」', '<TRQuoteEnd>')}」"

        source_entries.append(text)
    source_text = "\n".join(source_entries)

    # 构建完整提示词
    prompt = USER_PROMPT_TEMPLATE.replace("[History]", history_text).replace("[Glossary]", glossary_text).replace("[Input]", source_text)

    # 获取翻译结果
    if stream:
        print(datetime.datetime.now().strftime("%H:%M:%S"))

    response_text = ""
    for chunk in ask_stream(api, prompt, temperature, top_p, presence_penalty, frequency_penalty, proxy, timeout):
        response_text += chunk
        if stream:
            print(chunk, end="", flush=True)

    if stream:
        print()

    # 处理翻译结果
    translated_entries = []
    for source, target in zip(sources, response_text.splitlines()):
        # 还原换行
        target = target.replace("<TRNewLine>", "\n")

        # 创建结果条目
        entry = {**source, "target": target}

        # 处理带说话人的文本
        if source.get("speaker") and "「" in target:
            # 分割说话人和对话内容
            target_speaker, target_content = target.split("「", 1)

            # 查找对话结束位置
            quote_end_pos = target_content.rfind("」")
            if quote_end_pos != -1:
                target_content = target_content[:quote_end_pos]

            # 恢复特殊标记
            target_content = target_content.replace("<TRQuoteStart>", "「").replace("<TRQuoteEnd>", "」")

            entry.update({
                "target": target_content,
                "target_speaker": target_speaker
            })

        translated_entries.append(entry)

    return translated_entries
