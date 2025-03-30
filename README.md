# TkTransl
## 简介
这是一个使用[GalTransl模型](https://huggingface.co/SakuraLLM/Sakura-GalTransl-7B-v3)来将日语翻译为简体中文的项目。

## License
![GNU GPL Version 3 Official Logo](https://www.gnu.org/graphics/gplv3-with-text-136x68.png)

本项目采用[GNU GPLv3 or later](https://www.gnu.org/licenses/gpl-3.0.html)许可证。您可以自由使用、修改和分发本项目的代码，但必须在相同许可证或其任何后续版本下进行。

## 联系方式
- Email: thiliapr@tutanota.com

## 详情
- ~~由于这个程序全盘抄袭[GalTransl](https://github.com/GalTransl/GalTransl/)，所以~~有时候更新不是那么的及时。
- 支持的版本: [`Sakura-GalTransl-7B-v3-Q5_K_S.gguf`](https://huggingface.co/SakuraLLM/Sakura-GalTransl-7B-v3/blob/main/Sakura-GalTransl-7B-v3-Q5_K_S.gguf)
- System Prompt:
  > 你是一个视觉小说翻译模型，可以通顺地使用给定的术语表以指定的风格将日文翻译成简体中文，并联系上下文正确使用人称代词，注意不要混淆使役态和被动态的主语和宾语，不要擅自添加原文中没有的特殊符号，也不要擅自增加或减少换行。
- 对话 Prompt:
  > [History]  
  > 参考以下术语表（可为空，格式为src->dst #备注）：  
  > [Glossary]  
  > 根据以上术语表的对应关系和备注，结合历史剧情和上下文，将下面的文本从日文翻译成简体中文：  
  > [Input]

## 无关软件本身的广告
### Join the Blue Ribbon Online Free Speech Campaign!
![Blue Ribbon Campaign Logo](https://www.eff.org/files/brstrip.gif)

支持[Blue Ribbon Online 言论自由运动](https://www.eff.org/pages/blue-ribbon-campaign)！  
你可以通过向其[捐款](https://supporters.eff.org/donate)以表示支持。

### 支持自由软件运动
为什么要自由软件: [GNU 宣言](https://www.gnu.org/gnu/manifesto.html)

你可以通过以下方式支持自由软件运动:
- 向非自由程序或在线敌服务说不，哪怕只有一次，也会帮助自由软件。不和其他人使用它们会帮助更大。进一步，如果你告诉人们这是在捍卫自己的自由，那么帮助就更显著了。
- [帮助 GNU 工程和自由软件运动](https://www.gnu.org/help/help.html)
- [向 FSF 捐款](https://www.fsf.org/about/ways-to-donate/)