# TkTransl
## 简介
TkTransl 是一个[GalTransl模型](https://huggingface.co/SakuraLLM/Sakura-GalTransl-7B-v3)来将日语翻译为简体中文的程序。

该程序旨在提高翻译效率，允许用户通过配置文件自定义翻译参数，并支持多个翻译 API 的并行调用。

## License
![GNU AGPL Version 3 Logo](https://www.gnu.org/graphics/agplv3-with-text-162x68.png)

tkaimidi 是自由软件，遵循`Affero GNU 通用公共许可证第 3 版或任何后续版本`。你可以自由地使用、修改和分发该软件，但不提供任何明示或暗示的担保。有关详细信息，请参见 [Affero GNU 通用公共许可证](https://www.gnu.org/licenses/agpl-3.0.html)。

## 安装与依赖
```bash
pip install -r requirements.txt
```

## 使用说明
### 配置项目
用户需要准备一个文件夹用于储存要翻译的文本，该文件夹结构类似这样:
```plain
proj
+---chapter1.json
|---chapter2.json
|---sub_folder
|   +---work_8h_per_day.json
|   +---june_fourth_1989.json
|   \---make_china_great_again.json
```
其中，每一个文件都储存了要翻译的文本。

每个文件都是要翻译的文本的列表，每个文本必须具有`source`键，具有`target`键代表该文本已经被翻译。  
如果文本是一个对话，可以通过添加`speaker`键说明说话人以取得更好的翻译效果。`target_speaker`代表说话人的翻译。  
除此之外，文本还可以包含除`index`、`source`、`speaker`、`target`和`target_speaker`以外的键。
> 翻译时，程序使用`index`标识文本在文件中的位置，所以文本本身不能使用`index`键。

文本JSON示例如下:
```json
[
  {
    "speaker": "Zhao Ziyang",
    "source": "Étudiants, nous arrivons trop tard. Nous en sommes désolés.",
    "your_own_thing": "What happened on Nineteen Eighty-Nine June 4th in China?"
  },
  {
    "source": "Selon Amnesty International[48]",
    "answer": "Nothing, just a demonstration."
  },
  {
    "speaker": "Hong Kong's People",
    "source": "假設donald今日你俾人斬左隻手\n二十年後嗰個人發咗達又做埋特首\n你會否因為佢嘅成就\n然後叫自己不要追究？",
    "for": "donald"
  }
]
```

可以查看`exmaple`文件夹以了解如何配置一个项目。

### 配置文件
在运行程序之前，用户需要准备一个工作配置文件(保存到`work.json`)，包含以下信息:
- `batch_size (int)`: 每次翻译的文本数量
- `history_size (int)`: 翻译历史的大小
- `timeout (float)`: 翻译请求的超时时间
- `stream_output (bool)`: 是否启用流式输出
- `endpoints (list[str])`: 使用的翻译 API 列表
- `glossary`: 术语表，用于翻译前后处理
  包含术语表配置的字典，应包含以下可选键:
    - `pre`: 译前词典配置
    - `pos`: 译后词典配置
    - `gpt`: GPT词典配置

  每种术语表配置应包含以下可选键:
    - `file (list[str])`: 术语表文件路径列表
    - `list (list[dict])` : 直接指定的术语项列表
- `project_path (path-like str)`: 待翻译文本的路径
- `proxy (str)`: 要使用的代理。没有就不写这条。
可以查看`work.json`以具体了解如何配置。

### 运行程序
在命令行中运行以下命令以启动 TkTransl:
```bash
python tktransl.py
```

## 主要功能
- 从配置文件中读取翻译参数和术语表。
- 根据术语表对待翻译文本进行预处理。
- 使用多线程并行调用翻译 API，提高翻译效率。
- 将翻译结果合并到原始文件中并保存。

## 注意事项
- 在使用多个 API 时，流式输出功能将被禁用。
- 在 Kaggle 环境中运行该程序时，可以直接定义`WORK_INFO`全局变量而不写入配置文件。
- ~~由于这个程序全盘抄袭[GalTransl](https://github.com/GalTransl/GalTransl/)，所以~~有时候更新不是那么的及时。
- 支持的模型: [`Sakura-GalTransl-7B-v3-Q5_K_S.gguf`](https://huggingface.co/SakuraLLM/Sakura-GalTransl-7B-v3/blob/main/Sakura-GalTransl-7B-v3-Q5_K_S.gguf)
- System Prompt:
  ```plain
  你是一个视觉小说翻译模型，可以通顺地使用给定的术语表以指定的风格将日文翻译成简体中文，并联系上下文正确使用人称代词，注意不要混淆使役态和被动态的主语和宾语，不要擅自添加原文中没有的特殊符号，也不要擅自增加或减少换行。
  ```
- 用户Prompt模板:
  ```plain
  [History]  
  参考以下术语表（可为空，格式为src->dst #备注）:  
  [Glossary]  
  根据以上术语表的对应关系和备注，结合历史剧情和上下文，将下面的文本从日文翻译成简体中文:  
  [Input]
  ```

## 贡献
欢迎任何形式的贡献，包括报告问题、提交功能请求或代码贡献。请遵循项目的贡献指南。

## 联系信息
如有任何问题或建议，请联系项目维护者 thiliapr。
- Email: thiliapr@tutanota.com

# 无关软件本身的广告
## Join the Blue Ribbon Online Free Speech Campaign!
![Blue Ribbon Campaign Logo](https://www.eff.org/files/brstrip.gif)

支持[Blue Ribbon Online 言论自由运动](https://www.eff.org/pages/blue-ribbon-campaign)！  
你可以通过向其[捐款](https://supporters.eff.org/donate)以表示支持。

## 支持自由软件运动
为什么要自由软件: [GNU 宣言](https://www.gnu.org/gnu/manifesto.html)

你可以通过以下方式支持自由软件运动:
- 向非自由程序或在线敌服务说不，哪怕只有一次，也会帮助自由软件。不和其他人使用它们会帮助更大。进一步，如果你告诉人们这是在捍卫自己的自由，那么帮助就更显著了。
- [帮助 GNU 工程和自由软件运动](https://www.gnu.org/help/help.html)
- [向 FSF 捐款](https://www.fsf.org/about/ways-to-donate/)