# TkTransl

一个翻译文本的程序。

## 版权

TkTransl 是自由软件：你可以再分发之和/或依照由[自由软件基金会](https://www.fsf.org/)发布的[GNU 通用公共许可证](https://www.gnu.org/licenses/gpl-3.0.html)修改它，无论是版本 3 许可证，还是（按你的决定）任何以后版都可以。  
你应该随程序获得一份 GNU 通用公共许可证的复本。如果没有，请看[这个链接](https://www.gnu.org/licenses/)。

## 用法

```shell
# 安装依赖
pip install -r requirements.txt

# 翻译
python tktransl.py --input proj/input/ --output proj/output/ --config proj/config.json --pre-dict proj/preDict.txt --post-dict proj/postDict.txt --gpt-dict proj/gptDict.txt --not-allowed-log-level Log
```

### 参数说明

`--input`: 必选。要翻译的文件。
`--output`: 必选。翻译的输出路径。
`--config`: 必选。配置文件。
`--pre-dict`: 多选。译前（预处理）词典文件。
`--post-dict`: 多选。译后词典文件。
`--not-allowed-logging-level`: 多选。不允许某个等级的日志输出。等级: [Debug, Info, Warning, Error, Fatal]。
`--builtin-pre-dict`: 建议。使用内置的译前词典。
`--builtin-post-dict`: 建议。使用内置的译后词典。
`--builtin-gpt-dict`: 建议。使用内置的GPT词典。

## 文本

### 输入

```json
[
    {
        "message": "原文",
        "speaker": "说话的人，如果有的话。可以不写。",
        "additional_info": "附加信息，翻译时不会用到，输出时会带有这个。类型可以是字符串、数值、列表、字典等等都行。"
    },
    {
        "message": "另一则原文",
    }
]
```

### 输出

```json
[
    {
        // 该文本对象在原文的索引。
        "index": 0,

        "source": "原文",
        "translation": "译文",
        "translate_by": "哪个翻译器翻译的",

        // 以下键值对都只有相应的值不为空（或假）时才会包含在输出内
        "original_speaker": "说话的人的名字原文",
        "speaker_translation": "说话的人的名字译文",
        "additional_info": "原封不动的附加信息"
    }
]
```

## 词典

### 译前、译后词典

译前词典: 翻译前对原文处理。  
译后词典: 翻译后对译文处理。

格式如下:

```text
原文1->译文1

// 注释
原文2->译文2
```

### GPT词典

用于[SakuraLLM](https://github.com/SakuraLLM/SakuraLLM)、[ChatGPT](https://chat.openai.com/)等大语言模型，以提高AI翻译的质量。

格式如下:

```text
// 即使翻译与原文相同也要写
白上->白上 #白上フブキ的姓，少女
フブキ->吹雪 #白上フブキ的名，少女
```

## 配置

### 示例

配置顶层的设置是各个翻译器的通用设置，`translators`内的设置是个性化设置。

```json
{
    "sakurallm": {
        // 翻译时上文、下文分别的行数。此例中上文2行，下文1行。
        "previous_lines": 2,
        "next_lines": 1,

        // galtransl-v1.5专有。翻译风格，可以是“文艺”或者“流畅”。
        "style": "文艺",

        // SakuraLLM专有。一次翻译多少行
        "number_per_request_translate": 7,

        // SakuraLLM专有。支持的模型有`galtransl-v1.5`, `sakura-010`
        "model": "galtransl-v1.5"
    },
    "translators": {
        "sakurallm": [
            {
                // 翻译器的名称。记录日志时会显示此名称。
                "name": "SakuraLLM-1",

                // 以下皆为SakuraLLM专有。
                // OpenAI格式的API、时间限制（单位：秒）。
                "api": "http://127.0.0.1:10086", 
                "timeout": 5,
            }
        ]
    }
}
```
