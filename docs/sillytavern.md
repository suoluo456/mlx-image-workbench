# 可选 SillyTavern 扩展

工作台可单独使用。酒馆扩展独立安装，版本为 0.1.0；默认连接同一台 Mac 的 `http://127.0.0.1:7866`。

## 先准备工作台

双击工作台的 **安装.command**，在弹窗中选择 **安装酒馆支持**。完成后双击 **启动.command**。不需要输入命令。

如果你偏好终端，也可以运行：

```sh
bash install.sh --models qwen21_turbo --tavern
./启动.command
```

`--tavern` 会安装 Qwen Turbo、人物参考权重和对应运行环境，并启用可选酒馆接口。若不使用酒馆，安装时使用 `--no-tavern`；网页工作台仍可正常用。酒馆扩展目前调用 Qwen Turbo；Z-Image 仍可在独立工作台中使用。

浏览器扩展不能启动本机 Python。每次使用前需先启动工作台；电脑重启后也一样。仅关闭浏览器页面不会停止工作台服务。

## 安装扩展

推荐在酒馆直接安装，之后可通过酒馆管理更新：

1. 打开酒馆 **扩展 → 安装扩展**。
2. 仓库网址填写 `https://github.com/suoluo456/mlx-image-workbench`。
3. 在 **Branch or tag name (optional)**（分支或标签）填写 `sillytavern-extension`，再点击安装。

这里必须填写分支：主分支是完整工作台，`sillytavern-extension` 分支才是根目录直接包含 `manifest.json` 的独立扩展。不需要另建一个 GitHub 仓库，也不要使用 `tree/main/tavern-extension` 子目录网页 URL。

若酒馆旧版本没有分支输入框，可升级酒馆，或使用 ZIP 方式：将独立扩展 ZIP 解压成一个目录，放入 `data/<你的用户目录>/extensions/mlx-image-workbench/`。也可以复制本项目整个 `tavern-extension/` 目录到该位置。目录第一层必须直接有 `manifest.json` 和 `index.js`，不要多套一层文件夹。

刷新酒馆，启用内置“图像生成”扩展，然后在扩展面板找到 **MLX Image Workbench**。加载时会自动测试默认地址；此时不会改动已有生图来源。点击 **应用 MLX 生图配置** 后，扩展会保存自己的工作流并切换到 ComfyUI 来源。它使用工作台提供的兼容接口，不需要另外安装 ComfyUI。

应用前会保存原生图设置，可点击 **恢复上次生图设置** 恢复，再刷新酒馆。已存在且内容不同的同名工作流会保留，新工作流会另取名称。反复应用不会覆盖第一份原设置备份。

以后只要工作台已启动，就会使用保存的连接地址。若改变端口，在扩展面板输入新地址，先测试，再点击应用。同机默认使用 7866；服务与酒馆必须在同一台 Mac 上，当前不支持远程酒馆服务器或 Docker 中不同网络环境的自动连接。

扩展代码采用 MIT 许可，安装分支和独立 ZIP 都附带 `LICENSE`。模型授权仍分别适用，详见工作台的第三方说明。

## JSON 可以导入什么

`MLX_Workbench_0.1.0.json` 是一个兼容工作流。可在扩展面板下载，也可以在“导入兼容工作流 JSON”中选择该文件，再点应用。导入动作只暂存内容，不改酒馆设置。

只使用 JSON 时，可在酒馆图像生成设置选择 ComfyUI、填写工作台地址，新建工作流并粘贴文件内容。该工作流支持基础文字生图；它只包含单个 `MLXAvatarTurbo` 节点，不能运行普通 ComfyUI 节点图。

**JSON 不能安装完整扩展。** 随回复提取隐藏分镜、自动漫画、头像参考、用户代写识别、旧楼层补图和画风面板都由 JavaScript 扩展提供。完整功能需要安装整个扩展目录。

## 已有功能与开关

- 当前聊天的角色头像默认都可作为参考，不限制性别；也可在面板指定可用头像。世界书中没有头像的人物可按正文描述绘制。
- 正常回复可附带隐藏分镜；分镜从可见正文中移除。自动生图默认关闭，可在当前聊天单独开启，也可手动补图。
- 支持 2～5 格漫画、图片折叠、实际提示词查看、画幅/分辨率/画风设置，以及旧楼层画笔入口。
- 支持酒馆原生“代写用户消息”。手动输入的用户消息不会自动生图。第三方代写助手可填写明确的请求前缀；默认留空，不匹配私人固定口令。
- 生图使用酒馆自己的 ComfyUI 转发和图片保存流程。头像发送给本机工作台；连接检查与诊断记录使用本机接口。
- 服务未启动、连接到其他应用、未启用酒馆、Qwen 未下载完整、人物参考组件缺失，会分别提示。

分镜和出图记录会保存在用户自己的聊天元数据、浏览器暂存或工作台数据目录；分享聊天、诊断和生成记录前请按自己的需要移除私人内容。扩展不包含预设私人角色、头像或聊天文件。

## 兼容范围与验证

实现对照 SillyTavern 当前 `release` 分支的图像生成扩展、ComfyUI 转发接口和上下文 API。扩展接入的是 Chat Completion 的正常回复/原生代写流程；Text Completion 及会改写同一请求的第三方扩展尚未完成实机验证。没有为了测试去修改你的现有酒馆、设置或聊天。

本地自动检查：

```sh
node --test tavern-extension/test-connection.mjs
```

检查覆盖连接身份、缺失组件、配置保存与恢复、同名工作流保护、JSON 校验、原生代写、流式隐藏分镜和诊断地址。它不能代替在干净酒馆实例中的真实对话与出图验收。

官方参考：[UI 扩展结构与安装目录](https://docs.sillytavern.app/for-contributors/writing-extensions/)、[图像生成与 ComfyUI 工作流](https://docs.sillytavern.app/extensions/stable-diffusion/)、[ComfyUI 转发源码](https://github.com/SillyTavern/SillyTavern/blob/release/src/endpoints/stable-diffusion.js)、[图像生成前端源码](https://github.com/SillyTavern/SillyTavern/blob/release/public/scripts/extensions/stable-diffusion/index.js)。
