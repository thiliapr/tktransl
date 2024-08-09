# Copyright (C) 2024  thiliapr
# 本文件是 TkTransl 的一部分。
# TkTransl 是自由软件：你可以再分发之和/或依照由自由软件基金会发布的 GNU 通用公共许可证修改之，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 TkTransl 是希望它能有用，但是并无保障;甚至连可销售和符合某个特定的目的都不保证。请参看 GNU 通用公共许可证，了解详情。
# 你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/>。

from asyncio import Lock, sleep
import json
from typing import Optional
from httpx import AsyncClient, HTTPError
from utils.extra import LogLevel, log, escape, unescape
from utils.translate import BaseTranslator, Message, get_messages


class SakuraLLMTranslator(BaseTranslator):
    Sakura10SystemPrompt = "你是一个轻小说翻译模型，可以流畅通顺地使用给定的术语表以日本轻小说的风格将日文翻译成简体中文，并联系上下文正确使用人称代词，注意不要混淆使役态和被动态的主语和宾语，不要擅自添加原文中没有的代词，也不要擅自增加或减少换行。"
    Sakura10TranslatePrompt = "根据以下术语表（可以为空）：\n{glossary}\n将下面的日文文本根据上述术语表的对应关系和备注翻译成中文：{input}"
    GalTranslSystemPrompt = "你是一个视觉小说翻译模型，可以通顺地使用给定的术语表以指定的风格将日文翻译成简体中文，并联系上下文正确使用人称代词，注意不要混淆使役态和被动态的主语和宾语，不要擅自添加原文中没有的代词，也不要擅自增加或减少换行。"
    GalTranslTranslatePrompt = "根据以下术语表（可以为空，格式为src->dst #备注）：\n{glossary}\n联系历史剧情和上下文，根据上述术语表的对应关系和备注，以{style}的风格从日文到简体中文翻译下面的文本：\n{input}\n*EOF*\n{style}风格简体中文翻译结果："

    def __init__(
        self,
        number_per_request_translate: int,
        model: str,
        api: str,
        timeout: int | float,
        style: str = "文艺",
        **kwargs
    ):
        super().__init__(**kwargs)

        self.style = style
        self.number_per_request_translate = number_per_request_translate
        self.api = api.removesuffix("/")
        self.model = model

        # 构造prompt
        if model == "sakura-10":
            self.system_prompt = SakuraLLMTranslator.Sakura10SystemPrompt
            self.translate_prompt = SakuraLLMTranslator.Sakura10TranslatePrompt
        elif model == "galtransl-v1.5":
            self.system_prompt = SakuraLLMTranslator.GalTranslSystemPrompt
            self.translate_prompt = SakuraLLMTranslator.GalTranslTranslatePrompt
        else:
            log(self.name, f"提供了不支持的模型: {model}。将会当作galtransl-v1.5处理。", LogLevel.Warning)
            self.system_prompt = SakuraLLMTranslator.GalTranslSystemPrompt
            self.translate_prompt = SakuraLLMTranslator.GalTranslTranslatePrompt

        # 初始化客户端
        self.client = AsyncClient(timeout=timeout)

    async def batch_translate(
        self,
        messages: list[Message],
        messages_lock: Lock,
        dicts: tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str, Optional[str]]]],
        cache: dict[tuple[str, Optional[str]], tuple[str, Optional[str], str]],
        cache_lock: Lock
    ):
        # 初始化变量
        excluded_messages: set[int] = set()

        # 循环翻译
        while True:
            # 获取要翻译的文本
            messages_to_translate = await get_messages(messages, messages_lock, self.number_per_request_translate, excluded_messages, cache, cache_lock)
            if not messages_to_translate:
                break

            # 初始化frequency_penalty
            frequency_penalty = 0

            # 一直翻译直到成功
            while True:
                # 构造批量翻译文本
                sources = []
                for index, msg in enumerate(messages_to_translate):
                    source = msg.source

                    # 译前词典操作
                    for entry in dicts[0]:
                        source = source.replace(entry[0], entry[1])

                    # 对说话的人进行处理
                    if msg.original_speaker:
                        source = f"{msg.original_speaker}「{source}」"

                    sources.append(f"{escape(source)}<MSG{index}End>")
                sources = "\n".join(sources)

                # 连接上下文
                previous = escape("\n".join("\n".join([f"{msg.original_speaker}「{msg.source}」" if msg.original_speaker else msg.source for msg in messages[:messages.index(messages_to_translate[0])]]).splitlines()[-self.previous_lines:]))
                next = escape("\n".join("\n".join([f"{msg.original_speaker}「{msg.source}」" if msg.original_speaker else msg.source for msg in messages[messages.index(messages_to_translate[-1]) + 1:]]).splitlines()[:self.next_lines]))
                sources = "\n".join([
                    f"{previous}<PreviousEnd>",
                    sources,
                    f"<NextBegin>{next}"
                ])

                # 获取最大允许重复次数
                max_repetition_cnt = max(len(sources), 30)

                # 转化GPT词典为字符串
                gpt_dict: str = "\n".join(f"{src}->{dst} #{info}" if info else f"{src}->{dst}" for src, dst, info in dicts[2] if src in sources)

                # 构造data
                data = {
                    "messages": [
                        {
                            "role": "system",
                            "content": self.system_prompt
                        },
                        {
                            "role": "user",
                            "content": self.translate_prompt.format(glossary=gpt_dict, input=sources, style=self.style)
                        }
                    ],
                    "stream": True,
                    "temperature": 0.1618,
                    "top_p": 0.8,
                    "presence_penalty": 0,
                    "frequency_penalty": frequency_penalty
                }

                # 初始化变量: 接受的译文、错误标志（0代表无错误, 1代表可以通过重新翻译解决, 2代表需要跳过这些文本，3代表提前结束翻译）
                resp = ""
                error = 0

                # 发送请求
                try:
                    async with self.client.stream("POST", f"{self.api}/v1/chat/completions", json=data) as response:
                        if response.status_code != 200:
                            log(self.name, f"不正常的响应({response.status_code}): {await response.aread()}")
                            await sleep(1)
                            continue

                        async for line in response.aiter_lines():
                            if not line:
                                continue

                            # 解析数据
                            answer = json.loads(line.removeprefix("data: "))
                            if answer["choices"][0]["finish_reason"]:
                                break

                            resp += answer["choices"][0]["delta"]["content"]

                            # 删除上文
                            if "<PreviousEnd>" in resp:
                                resp = resp[resp.find("<PreviousEnd>") + len("<PreviousEnd>"):].removeprefix("\n")

                            # 提前结束翻译（不翻译下文）
                            if "<NextBegin>" in resp:
                                resp = resp[:resp.find("<NextBegin>")]
                                error = 3

                            # 检测是否退化
                            if SakuraLLMTranslator.check_degen(resp, max_repetition_cnt) or (len(resp) / len(sources) > 1.5):
                                if frequency_penalty < 0.8:
                                    log(self.name, f"检测到退化发生(重复或译文过长), 增加frequency_penalty重试。目前的frequency_penalty: {frequency_penalty}")
                                    frequency_penalty += 0.1
                                    error = 1
                                elif len(messages_to_translate) >= 2:
                                    log(self.name, f"检测到退化发生(重复或译文过长), 对半拆分重试。")
                                    frequency_penalty = 0
                                    async with messages_lock:
                                        for msg in messages_to_translate[:len(messages_to_translate) // 2]:
                                            msg.translating = False
                                            messages_to_translate.remove(msg)

                                    error = 1
                                else:
                                    # 没法拆分了
                                    log(self.name, f"翻译`{sources}`时失败。", level=LogLevel.Error)
                                    async with messages_lock:
                                        excluded_messages.add(messages_to_translate[0].index)
                                        messages_to_translate[0].translating = False

                                    error = 2

                            # 检测是否缺失文本结束标志
                            loss = []
                            for i in range(len(messages_to_translate) + 1):
                                if f"<MSG{i}End>" not in resp:
                                    loss.append(i)

                            if len(loss) > 1:
                                for i in range(len(loss) - 1):
                                    if loss[i + 1] - loss[i] != 1:
                                        log(self.name, f"检测到缺少文本结束标志。删减翻译至第{loss[0] - 1}条文本。")
                                        split_at = loss[0]

                                        # 删除文本
                                        async with messages_lock:
                                            for msg in messages_to_translate[split_at:]:
                                                messages_to_translate.remove(msg)
                                                msg.translating = False

                                        # 删除响应
                                        resp = resp[:resp.find(f"<MSG{split_at - 1}End>") + len(f"<MSG{split_at - 1}End>")]

                                        # 结束翻译
                                        error = 3
                                        break

                            # 是否翻译了多出了文本
                            elif len(loss) == 0:
                                log(self.name, f"检测到翻译了太多的文本, 对半拆分重试。")
                                async with messages_lock:
                                    for msg in messages_to_translate[:len(messages_to_translate) // 2]:
                                        msg.translating = False
                                        messages_to_translate.remove(msg)
                                error = 1

                            # 是否发生错误
                            if error:
                                break
                except (HTTPError, RuntimeError) as e:
                    log(self.name, f"请求翻译时发生了错误: {repr(e)}", level=LogLevel.Warning)
                    await sleep(3)
                    continue

                # 无法翻译、提前结束翻译
                if error != 1:
                    break

            # 无法翻译
            if error == 2:
                continue

            # 还原
            next = resp
            async with messages_lock:
                for index, msg in enumerate(messages_to_translate):
                    content = next[:next.find(f"<MSG{index}End>")]
                    next = next[next.find(f"<MSG{index}End>") + len(f"<MSG{index}End>"):].removeprefix("\n")

                    # 还原说话的人
                    if msg.original_speaker:
                        if "「" in content:
                            speaker, content = content.split("「", 1)
                        else:
                            speaker = msg.original_speaker
                        content = content.removesuffix("」")
                    else:
                        speaker = None

                    # 删除多余的行
                    content = "\n".join(unescape(content).splitlines()[:len(msg.source.splitlines())])

                    # 译后词典操作
                    for entry in dicts[1]:
                        content = content.replace(entry[0], entry[1])

                    # 提交翻译
                    msg.translation = content
                    msg.speaker_translation = speaker
                    msg.translate_by = self.name
                    msg.translating = False

                    # 保存至缓存中
                    async with cache_lock:
                        if (msg.source, msg.original_speaker) not in cache:
                            cache[msg.source, msg.original_speaker] = msg.translation, msg.speaker_translation, msg.translate_by

                    # 显示翻译
                    if msg.original_speaker:
                        log(self.name, f"Source: {msg.original_speaker} says {msg.source}", level=LogLevel.Debug)
                        log(self.name, f"  Dest: {msg.speaker_translation} says {msg.translation}", level=LogLevel.Debug)
                    else:
                        log(self.name, f"Source: {msg.source}", level=LogLevel.Debug)
                        log(self.name, f"  Dest: {msg.translation}", level=LogLevel.Debug)

    @staticmethod
    def check_degen(resp: str, max_repetition_cnt: int) -> bool:
        for length in range(1, len(resp) // max_repetition_cnt):
            txt = resp[-length:]
            start = repetition_cnt = 0

            while start < len(resp):
                if resp[start:].startswith(txt):
                    repetition_cnt += 1
                    start += len(txt)
                else:
                    repetition_cnt = 0
                    start += 1

                if repetition_cnt >= max_repetition_cnt:
                    return True

        return False
