# 第三方组件与引用声明

卿音本身只做「编排层」：参数方案、素材管理、任务调度、界面和提示。
真正干活的模型与运行时都来自开源社区，版权归各自作者，本项目不打包、不转售、不内置它们的权重。

## 一、运行时与依赖

| 组件 | 用途 | 许可 | 来源 |
|---|---|---|---|
| RVC（Retrieval-based-Voice-Conversion-WebUI） | 音色转换 | MIT | https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI |
| UVR5 / audio-separator | 人声分离 | MIT | https://github.com/nomadkaraoke/python-audio-separator |
| Demucs | 人声分离（可选后端） | MIT | https://github.com/facebookresearch/demucs |
| FFmpeg | 转码与拼接 | LGPL/GPL（按其构建） | https://ffmpeg.org |
| yt-dlp | 链接下载 | Unlicense | https://github.com/yt-dlp/yt-dlp |
| PyTorch | 推理运行时 | BSD-3-Clause | https://pytorch.org |
| Pretrained 权重（hubert / rmvpe / 预训练底模） | 转换与训练基础 | 见上游 RVC 仓库说明 | RVC 官方发布渠道 |

模型权重由使用者自行准备（自己的声音、自己训练、自己承担授权责任）。本项目**不附带任何第三方音色模型**。

## 二、素材来源

- 本地曲库：读取用户本机已有文件（网易云 / QQ 音乐的明文或已解密文件），仅限个人欣赏。
- 在线搜索：B 站、iTunes、网易云、QQ 音乐的公开接口做元数据检索；下载能力受平台规则限制。
- 本项目**不提供任何解密实现**，只保留插件接口（`plugins/`）；是否接入、如何接入由使用者自行决定并承担全部责任。

## 三、界面与设计参考

- 图标：自绘 SVG（线性风格参考 Lucide / Tabler 的通用做法）。
- 设计令牌组织方式参考 Radix Colors、Open Props。
- 排版与组件克制感参考 Arco Design、Semi Design、TDesign。
- 「新中式」调性（宣纸 / 朱砂 / 宋体标题）为本项目自定，非照搬任何现有设计系统。

## 四、致谢

感谢 RVC、UVR、Demucs、FFmpeg、yt-dlp 以及所有把模型和工具开源出来的作者。
没有这些基础，这个项目只能是一堆 YAML。

## 五、如果我是权利人的话

如果你是本项目引用的某个组件/素材的权利人，认为使用方式不妥，
请在仓库开 Issue 说明，我会在 48 小时内调整或移除相关内容。
