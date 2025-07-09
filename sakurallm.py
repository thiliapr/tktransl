"SakuraLLM的翻译部分"
# 本文件是 tktransl 的一部分
# SPDX-FileCopyrightText: 2025 thiliapr <thiliapr@tutanota.com>
# SPDX-FileContributor: thiliapr <thiliapr@tutanota.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

import orjson
from typing import Any, Optional, Iterator
import httpx
from utils import generate_placeholder_token


SYSTEM_PROMPT = "你是一个视觉小说翻译模型，可以通顺地使用给定的术语表以指定的风格将日文翻译成简体中文，并联系上下文正确使用人称代词，注意不要混淆使役态和被动态的主语和宾语，不要擅自添加原文中没有的特殊符号，也不要擅自增加或减少换行。"
TRANSLATION_PROMPT_TEMPLATE = """历史翻译：[History]
参考以下术语表（可为空，格式为src->dst #备注）：
[Glossary]
根据以上术语表的对应关系和备注，结合历史剧情和上下文，将下面的文本从日文翻译成简体中文：
[Input]"""


class TranslateError(RuntimeError):
    "翻译相关异常的基类"


class TranslationCountError(TranslateError):
    """
    原文与译文数量不匹配时抛出的异常。
    当源文本列表和翻译结果列表的长度不一致时，表明翻译过程可能出现将两个连续的文本翻译为一个文本的情况。

    Args:
        sources_count: 源文数量
        targets_count: 译文数量
    """

    def __init__(self, sources_count: int, targets_count: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sources_count = sources_count
        self.targets_count = targets_count

    def __str__(self):
        return f"原文与译文数量不匹配。原文有 {self.sources_count} 条文本，而译文却有 {self.targets_count} 条。"


def ask_stream(
    api: str,
    prompt: str,
    temperature: float,
    top_p: float,
    presence_penalty: float,
    frequency_penalty: float,
    timeout: float,
    proxy: Optional[str] = None,
) -> Iterator[str]:
    """
    向支持流式响应的API发送请求，并以流式方式获取生成的文本内容。

    Args:
        api: API基础URL
        prompt: 用户输入的完整提示词
        temperature: 控制生成随机性的参数
        top_p: 核采样参数
        presence_penalty: 避免重复话题的参数
        frequency_penalty: 避免重复用词的参数
        timeout: 请求超时时间(单位: 秒)
        proxy: 可选代理设置

    Returns:
        生成器，逐块产生API返回的文本内容

    Exceptions:
        RuntimeError: 当API返回非200状态码时抛出
    """
    with httpx.stream(
        "POST",
        f"{api}/v1/chat/completions",
        proxy=proxy,
        timeout=timeout,
        json={
            "model": "sakura",
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

            # 删除`data: `
            line = line[6:]

            # 解析响应行
            data = orjson.loads(line)
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
    source_texts: list[dict[str, Any]],
    translation_history: list[dict[str, Any]],
    glossary_terms: list[dict[str, Any]],
    endpoint: str,
    stream_output: bool,
    temperature: float,
    top_p: float,
    presence_penalty: float,
    frequency_penalty: float,
    timeout: float,
    proxy: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    批量翻译视觉小说文本，支持术语表和历史上下文

    处理流程:
        1. 预处理文本中的特殊符号（如引号、换行符）
        2. 构建包含历史翻译和术语表的完整提示词
        3. 调用翻译API获取结果
        4. 后处理结果（恢复特殊符号、验证数量一致性）
        5. 返回结构化翻译结果
    Args:
        source_texts: 待翻译文本列表，每个元素应包含:
            - source: 原文内容（必需）
            - speaker: 说话人标识（可选）
        translation_history: 历史翻译记录，用于保持上下文一致性，每个元素应包含:
            - source: 原文内容（必需）
            - target: 已有译文（必需）
            - speaker: 说话人原文（如有）
            - target_speaker: 说话人译文（如有）
        glossary_terms: 术语对照表，每个元素应包含:
            - source: 原文术语（必需）
            - target: 译文术语（必需）
            - description: 术语说明（可选）
        endpoint: 翻译API服务地址
        stream_output: 是否实时输出翻译进度

        temperature: 控制生成随机性的温度，值越高结果越多样
        top_p: 核采样参数，控制词汇选择范围
        presence_penalty: 避免重复话题的，避免重复话题
        frequency_penalty: 避免重复用词的，避免重复用词

        timeout: API请求超时时间（秒）
        proxy: 代理服务器地址

    Returns:
        翻译结果列表，保留原始字段并新增:
            - target: 翻译内容
            - target_speaker: 说话人译名（如果原文有speaker字段）

    Exceptions:
        TranslationCountError: 当返回结果数量与输入不一致时抛出
        RuntimeError: 当API请求失败时抛出
    """
    # ========== 预处理阶段 ==========
    # 获取原文样版
    original_text_sample = "\n".join(entry["source"] for entry in source_texts)

    # 生成防冲突的特殊标记
    newline_token = generate_placeholder_token("NL", original_text_sample)
    quote_start_token = generate_placeholder_token("QS", original_text_sample)
    quote_end_token = generate_placeholder_token("QE", original_text_sample)

    # 处理历史记录
    processed_history = []
    for history_entry in translation_history:
        # 标准化文本格式
        processed_text = history_entry["target"].replace("\r\n", "\n").replace("\n", newline_token)

        # 处理说话人标记
        if "speaker" in history_entry:
            speaker_name = history_entry.get("target_speaker", history_entry["speaker"])
            processed_text = f"{speaker_name}「{processed_text.replace('「', quote_start_token).replace('」', quote_end_token)}」"
        processed_history.append(processed_text)

    # 构建历史上下文字符串
    history_context = "<SEP>".join(processed_history)

    # 处理术语表
    glossary_context = "\n".join(
        f"{term['source']}->{term['target']}"
        + (f" #{term['description']}" if term.get("description") else "")
        for term in glossary_terms
        if term["source"] in original_text_sample
    )

    # 处理待翻译文本
    processed_sources = []
    for text_entry in source_texts:
        # 标准化文本格式
        processed_text = text_entry["source"].replace("\r\n", "\n").replace("\n", newline_token)

        # 处理说话人标记
        if "speaker" in text_entry:
            processed_text = f"{text_entry['speaker']}「{processed_text.replace('「', quote_start_token).replace('」', quote_end_token)}」"
        processed_sources.append(processed_text)

    # ========== API调用阶段 ==========
    # 构建完整提示词
    final_prompt = (
        TRANSLATION_PROMPT_TEMPLATE
        .replace("[History]", history_context)
        .replace("[Glossary]", glossary_context)
        .replace("[Input]", "\n".join(processed_sources))
    )

    # 获取翻译结果
    api_response = ""
    for response_chunk in ask_stream(endpoint, final_prompt, temperature, top_p, presence_penalty, frequency_penalty, proxy, timeout):
        api_response += response_chunk
        if stream_output:
            print(response_chunk, end="", flush=True)

    if stream_output:
        print()  # 流式输出结束换行

    # ========== 译后处理阶段 ==========
    # 验证结果数量
    response_lines = api_response.splitlines()
    if len(source_texts) != len(response_lines):
        if len(source_texts) == 1:  # 单条输入特殊处理
            api_response = api_response.replace("\n", "")
            response_lines = [api_response]
        else:
            raise TranslationCountError(len(source_texts), len(response_lines))

    # 结构化处理结果
    final_results = []
    for source_entry, translated_text in zip(source_texts, response_lines):
        # 恢复原始格式
        restored_text = translated_text.replace(newline_token, "\n")
        result_entry = {**source_entry, "target": restored_text}

        # 处理说话人信息
        if "speaker" in source_entry and "「" in restored_text:
            speaker_part, dialog_part = restored_text.split("「", 1)
            dialog_content = dialog_part[:dialog_part.rfind("」")] if "」" in dialog_part else dialog_part

            # 恢复特殊符号
            dialog_content = (
                dialog_content
                .replace(quote_start_token, "「")
                .replace(quote_end_token, "」")
            )

            result_entry.update({
                "target": dialog_content,
                "target_speaker": speaker_part
            })

        final_results.append(result_entry)

    return final_results
