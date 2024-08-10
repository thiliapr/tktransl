# Copyright (C) 2024  thiliapr
# 本文件是 TkTransl 的一部分。
# TkTransl 是自由软件：你可以再分发之和/或依照由自由软件基金会发布的 GNU 通用公共许可证修改之，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。
# 发布 TkTransl 是希望它能有用，但是并无保障;甚至连可销售和符合某个特定的目的都不保证。请参看 GNU 通用公共许可证，了解详情。
# 你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看 <https://www.gnu.org/licenses/>。

from abc import abstractmethod
from asyncio import Lock, create_task, sleep
from dataclasses import dataclass
from typing import Optional, Any
from utils.extra import LogLevel, log


@dataclass
class Message:
    """
    储存翻译文本的对象。

    - index(int): 该文本在输入中的索引。
    - source(str): 原文。
    - translation(str): 译文。
    - translate_by(str): 由哪个翻译器翻译（即翻译这个文本的翻译器的`name`值）。
    - original_speaker(Optional[str]): 说话这句话的人的名字。
    - speaker_translation(Optional[str]): 说话这句话的人的名字的翻译。
    - additional_info(Optional[Any]): 任意类型的附加信息。
    """

    index: int
    source: str
    translation: str | None
    translate_by: str | None
    original_speaker: Optional[str]
    speaker_translation: Optional[str]
    additional_info: Optional[Any]

    # 翻译时用
    translating: bool = False

    def jsonify(self) -> dict[str, Any]:
        """
        将文本对象JSON序列化。
        """

        return {k: v for k, v in {
            "index": self.index,
            "source": self.source,
            "translation": self.translation,
            "translate_by": self.translate_by,
            "original_speaker": self.original_speaker,
            "speaker_translation": self.speaker_translation,
            "additional_info": self.additional_info,
        }.items() if v is not None}

    @staticmethod
    def from_input(data: dict[str, Any], index: int):
        """
        从输入中加载文本。
        """

        return Message(index, data["message"], None, None, data.get("speaker"), None, data.get("additional_info"))


class BaseTranslator:
    """
    文本翻译器。
    """

    def __init__(self, name: str, previous_lines: int, next_lines: int, **kwargs):
        self.name = name
        self.previous_lines = previous_lines
        self.next_lines = next_lines

        if kwargs:
            log(self.name, f"初始化翻译器时发现未知参数: {kwargs.keys()}", level=LogLevel.Warning)

    @abstractmethod
    async def batch_translate(
        self,
        messages: list[Message],
        messages_lock: Lock,
        dicts: tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str, Optional[str]]]],
        cache: dict[tuple[str, Optional[str]], tuple[str, Optional[str]]],
        cache_lock: Lock
    ):
        """
        启动一个翻译协程。
        """

        raise NotImplementedError


async def progress_bar(
    filepath: str,
    messages: list[Message],
    messages_lock: Lock,
    running_translators: set[BaseTranslator]
):
    # 循环显示进度条
    while True:
        if len(running_translators) == 0:
            break

        async with messages_lock:
            messages_finished = [msg for msg in messages if msg.translation is not None]

            chars_total = [char for msg in messages for char in msg.source]
            chars_finished = [char for msg in messages_finished for char in msg.source]

            log("Progress", f"{len(chars_finished)}/{len(chars_total)} Character(s) {len(chars_finished) * 100 / len(chars_total):.2f}%; {len(messages_finished)}/{len(messages)} Message(s) {len(messages_finished) * 100 / len(messages):.2f}%; {filepath}")
        await sleep(4)


async def translate_async(
    filepath: str,
    messages: list[Message],
    translators: list[BaseTranslator],
    dicts: tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str, Optional[str]]]]
):
    """
    使用多个翻译器协程翻译。

    Args:
    - filepath(str): 翻译的文件的路径。
    - messages(list[Message]): 需要翻译的文本的列表，会对其进行操作。
    - translators(list[BaseTranslator])：要使用的翻译器的列表。
    - dicts(tuple[..., ..., ...]): 译前、译后、GPT词典。
    """

    messages_lock = Lock()

    # 创建一个储存运行中的翻译器的列表，用于决定进度条是否停止。
    running_translators = set()

    # 创建一个翻译的缓存，用于储存已翻译的文本
    cache, cache_lock = {}, Lock()

    # 运行翻译器和进度条的协程
    translators_tasks = [create_task(translator.batch_translate(messages, messages_lock, dicts, cache, cache_lock), name=translator.name) for translator in translators]
    for task in translators_tasks:
        running_translators.add(task)
        task.add_done_callback(running_translators.discard)

    await progress_bar(filepath, messages, messages_lock, running_translators)


# 翻译器用
async def get_messages(
    messages: list[Message],
    messages_lock: Lock,
    n: int,
    exclude: set[int],
    cache: dict[tuple[str, Optional[str]], tuple[str, Optional[str], str]],
    cache_lock: Lock
) -> list[Message]:
    """
    从文本中取出`n`个文本, 并将它们的`translating`值设置为`True`。
    """

    while True:
        async with messages_lock:
            messages_to_translate: list[Message] = []

            # 获取要翻译的文本
            for msg in messages:
                # 数量是否已经足够
                if len(messages_to_translate) >= n:
                    break
                # 是否已经翻译或正在被翻译
                elif (msg.translation is not None) or msg.translating:
                    continue
                # 队列中是否存在完全相同的翻译
                elif (msg.source, msg.original_speaker) in {(msg.source, msg.original_speaker) for msg in messages if msg.translating}:
                    continue
                # 是否为空
                elif msg.source == "":
                    msg.translation = ""

                    # 查找相同说话的人的文本
                    if msg.original_speaker:
                        for translated_message in messages:
                            if translated_message.original_speaker == msg.original_speaker:
                                msg.speaker_translation = translated_message.speaker_translation
                                msg.translate_by = translated_message.translate_by
                                continue
                    else:
                        msg.speaker_translation = msg.original_speaker
                        msg.translate_by = None
                        continue

                # 是否不支持该文本
                elif msg.index in exclude:
                    continue
                # 是否已有缓存
                async with cache_lock:
                    if (msg.source, msg.original_speaker) in cache:
                        msg.translation, msg.speaker_translation, msg.translate_by = cache[msg.source, msg.original_speaker]
                        continue

                # 添加至目前任务列表
                msg.translating = True
                messages_to_translate.append(msg)

            # 判断是否退出循环
            if not messages_to_translate:
                # 如果既没有文本要翻译，并且没有翻译任务未完成，就返回空列表，否则一秒后继续检测
                if [msg for msg in messages if msg.translating]:
                    await sleep(1)
                    continue
                else:
                    return []
            else:
                return messages_to_translate
