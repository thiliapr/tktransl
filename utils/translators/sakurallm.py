# Copyright (C) 2024  thiliapr
# 本文件是 TkTransl 的一部分。
# TkTransl 是自由软件：你可以再分发之和/或依照由自由软件基金会发布的 GNU 通用公共许可证修改之，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 TkTransl 是希望它能有用，但是并无保障; 甚至连可销售和符合某个特定的目的都不保证。请参看 GNU 通用公共许可证，了解详情。
# 你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/>。

"""
SakuraLLM翻译器。
"""

from asyncio import Lock, sleep
import json
from typing import Optional
from httpx import AsyncClient, HTTPError
from utils.extra import LogLevel, log, escape, unescape
from utils.translate import BaseTranslator, Message, get_messages


class SakuraLLMTranslator(BaseTranslator):
    """
    使用SakuraLLM作为引擎的翻译器类。
    """

    GalTranslSystemPrompt = "你是一个视觉小说翻译模型，可以通顺地使用给定的术语表以指定的风格将日文翻译成简体中文，并联系上下文正确使用人称代词，注意不要混淆使役态和被动态的主语和宾语，不要擅自添加原文中没有的特殊符号，也不要擅自增加或减少换行。"
    GalTranslTranslatePrompt = "参考以下术语表（可为空，格式为src->dst #备注）：\n{glossary}\n根据上述术语表的对应关系和备注，结合历史剧情和上下文，以{style}的风格将下面的文本从日文翻译成简体中文：\n{input}"

    def __init__(
        self,
        number_per_request_translate: int,
        model: str,
        api: str,
        timeout: int | float,
        style: str,
        restart_api: Optional[str] = None,
        restart_timeout: int | float = 60,
        **kwargs
    ):
        super().__init__(**kwargs)

        self.style = style
        self.number_per_request_translate = number_per_request_translate
        self.api = api.removesuffix("/")
        self.model = model
        self.restart_api = restart_api
        self.restart_timeout = restart_timeout

        # 构造prompt
        if model == "galtransl-v2":
            self.system_prompt = SakuraLLMTranslator.GalTranslSystemPrompt
            self.translate_prompt = SakuraLLMTranslator.GalTranslTranslatePrompt
        else:
            log(self.name, f"提供了不支持的模型: {model}。将会当作galtransl-v2处理。", LogLevel.Warning)
            self.system_prompt = SakuraLLMTranslator.GalTranslSystemPrompt
            self.translate_prompt = SakuraLLMTranslator.GalTranslTranslatePrompt

        # 初始化客户端
        self.client = AsyncClient(timeout=timeout)

    async def _half_messages(self, error_message: str, messages_to_translate: list[Message], messages_lock: Lock, excluded_messages: set[int]) -> bool:
        """
        如果要翻译的文本的数量大于1, 就从要翻译的文本的列表中删除一半, 并返回True; 否则, 就释放当前唯一的文本, 并返回False。
        """

        async with messages_lock:
            if len(messages_to_translate) > 1:
                log(self.name, f"{error_message}, 对半拆分重试。")
                for msg in messages_to_translate[:len(messages_to_translate) // 2]:
                    msg.translating = False
                    messages_to_translate.remove(msg)
                return True
            else:
                log(self.name, f"{error_message}, 翻译器将不会翻译该文本。", level=LogLevel.Warning)
                excluded_messages.add(messages_to_translate[0].index)
                messages_to_translate[0].translating = False
                return False

    @staticmethod
    def check_degen(resp: str, max_repetition_cnt: int) -> bool:
        """
        检查文本内是否存在超过`max_repetition_cnt`个重复文本。
        """

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

    async def batch_translate(
        self,
        messages: list[Message],
        messages_lock: Lock,
        dicts: tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str, Optional[str]]]],
        cache: dict[tuple[str, Optional[str]], tuple[str, Optional[str], str]],
        cache_lock: Lock
    ):
        """
        启动一个翻译协程。
        """
        excluded_messages: set[int] = set()  # 初始化变量

        # 循环翻译
        while True:
            # 获取要翻译的文本
            messages_to_translate = await get_messages(messages, messages_lock, self.number_per_request_translate, excluded_messages, cache, cache_lock)
            if not messages_to_translate:
                break

            frequency_penalty = 0  # 初始化frequency_penalty
            # 一直翻译直到成功
            while True:
                # 构造批量翻译文本
                sources = []
                for index, msg in enumerate(messages_to_translate):
                    source = msg.source

                    # 对说话的人进行处理
                    if msg.original_speaker:
                        source = source.replace("「", "“").replace("」", "”")
                        source = f"{msg.original_speaker}「{source}」"

                    sources.append(escape(source))

                # 连接上下文
                previous_content = escape("\n".join("\n".join([f"{msg.original_speaker}「{msg.source}」" if msg.original_speaker else msg.source for msg in messages[:messages.index(messages_to_translate[0])]]).splitlines()[-self.previous_lines:]))
                next_content = escape("\n".join("\n".join([f"{msg.original_speaker}「{msg.source}」" if msg.original_speaker else msg.source for msg in messages[messages.index(messages_to_translate[-1]) + 1:]]).splitlines()[:self.next_lines]))
                sources = "\n".join([
                    previous_content if previous_content else "没有上文",
                    *sources,
                    next_content if next_content else "没有下文"
                ])

                # 译前词典操作
                for entry in dicts[0]:
                    sources = sources.replace(entry[0], entry[1])

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
                    "temperature": 0.3,
                    "top_p": 0.8,
                    "presence_penalty": 0,
                    "frequency_penalty": frequency_penalty
                }

                # 初始化变量: 接受的译文、错误标志（0代表无错误, 1代表可以通过重新翻译解决, 2代表需要跳过这些文本，3代表致命错误）
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

                            # 检测是否退化
                            if SakuraLLMTranslator.check_degen(resp, max_repetition_cnt) or (len(resp) / len(sources) > 1.5):
                                if frequency_penalty < 0.8:
                                    log(self.name, "检测到退化发生(重复或译文过长), 增加frequency_penalty重试。")
                                    frequency_penalty += 0.1
                                    error = 1
                                else:
                                    frequency_penalty = 0
                                    error = 1 if await self._half_messages("检测到退化发生(重复或译文过长)", messages_to_translate, messages_lock, excluded_messages) else 2
                            # 检测行数是否超过了原文
                            elif len(resp.splitlines()) > len(sources.splitlines()):
                                error = 1 if await self._half_messages("翻译行数大于原文行数", messages_to_translate, messages_lock, excluded_messages) else 2

                            # 检测是否存在空行
                            if not error:
                                for index, line in enumerate(resp.removesuffix("\n").splitlines()):
                                    if not line:
                                        error = 1 if await self._half_messages(f"第{index + 1}行为空", messages_to_translate, messages_lock, excluded_messages) else 2
                                        break

                            # 是否发生错误
                            if error:
                                break
                except (HTTPError, RuntimeError) as e:
                    if self.restart_api:
                        log(self.name, f"请求翻译时发生了错误, 正在尝试重启服务器: {repr(e)}")
                        try:
                            response = await self.client.post(self.restart_api)
                            if response.content != b"ok":
                                log(self.name, f"重启服务器时返回了不正常的响应({response.status_code}): {response.content}", level=LogLevel.Error)
                                error = 3
                            else:
                                error = 1
                        except (HTTPError, RuntimeError) as ex:
                            log(self.name, f"重启服务器时发生了错误: {repr(ex)}", level=LogLevel.Error)
                            error = 3
                    else:
                        log(self.name, f"请求翻译时发生了错误, 等待3秒后重试: {repr(e)}")
                        await sleep(3)
                        error = 1

                # 结束时再检测一次是否存在空行
                if not error:
                    for index, line in enumerate(resp.splitlines()):
                        if not line:
                            error = 1 if await self._half_messages(f"第{index + 1}行为空", messages_to_translate, messages_lock, excluded_messages) else 2
                            break

                # 检测是否翻译行数是否小于或大于原文行数
                if not error and len(resp.splitlines()) != len(sources.splitlines()):
                    cmp_result = len(resp.splitlines()) < len(sources.splitlines())
                    error = 1 if await self._half_messages("翻译行数{}于原文行数".format("小" if cmp_result else "大"), messages_to_translate, messages_lock, excluded_messages) else 2

                # 无法翻译、致命错误
                if error != 1:
                    break
            if error == 2:  # 无法翻译
                continue
            if error == 3:  # 致命错误
                break

            log(self.name, resp, level=LogLevel.Debug)
            resp = "\n".join(resp.splitlines()[1:-1])  # 删除上、下文

            # 还原
            destinations = resp.splitlines()
            async with messages_lock:
                for index, msg in enumerate(messages_to_translate):
                    content = destinations[index]

                    # 还原说话的人
                    if msg.original_speaker:
                        if "「" in content:
                            speaker, content = content.split("「", 1)
                            content = content.replace("“", "「").replace("”", "」")
                        else:
                            speaker = msg.original_speaker
                        content = content.removesuffix("」")
                    else:
                        speaker = msg.original_speaker
                    content = "\n".join(unescape(content).splitlines()[:len(msg.source.splitlines())])  # 删除多余的行

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
                        log(self.name, f"Source: {msg.original_speaker} says {msg.source}", level=LogLevel.Info)
                        log(self.name, f"  Dest: {msg.speaker_translation} says {msg.translation}", level=LogLevel.Info)
                    else:
                        log(self.name, f"Source: {msg.source}", level=LogLevel.Info)
                        log(self.name, f"  Dest: {msg.translation}", level=LogLevel.Info)
