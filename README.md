# MLX Image Workbench — SillyTavern 扩展

独立可选扩展，版本 0.1.0，默认连接同机 `http://127.0.0.1:7866`。

1. 双击工作台的 `安装.command`，在弹窗中选择“安装酒馆支持”；完成后双击 `启动.command`。
2. 酒馆打开 **扩展 → 安装扩展**：仓库网址填写 `https://github.com/suoluo456/mlx-image-workbench`，**Branch or tag name (optional)**（分支或标签）填写 `sillytavern-extension`，点击安装。
3. 刷新酒馆，并启用内置图像生成扩展。打开 **MLX Image Workbench** 面板，点 **测试连接**，再点 **应用 MLX 生图配置**。之后使用保存的地址；原生图设置会保留一份，恢复后请刷新酒馆。
4. 按需开启当前聊天的自动配图，或点击手动生图。头像参考、2～5 格漫画、原生代写用户消息和画风设置均包含在扩展中。

务必填写 `sillytavern-extension` 分支：该分支根目录直接包含扩展文件，主分支是完整工作台。不要填写 GitHub 子目录网页 URL。

旧版酒馆没有分支输入框时，可升级酒馆或解压独立扩展 ZIP，把目录放到 `data/<用户目录>/extensions/mlx-image-workbench/`；`manifest.json` 必须直接在该目录下。
启动检查不会覆盖现有生图设置；点击应用才会切换来源。改变工作台端口后需重新设置地址。浏览器不能替你启动 Python 服务。

`MLX_Workbench_0.1.0.json` 可单独导入为基础文字生图工作流。JSON 只定义工作流，不能安装完整扩展；完整自动配图需要本目录的 JavaScript 文件。面板也支持下载和导入兼容 JSON。

主项目与扩展共用一个仓库，扩展通过独立分支安装和更新。扩展代码采用 MIT 许可，见本目录 `LICENSE`；模型授权分别适用。

本地自动测试：`node --test test-connection.mjs`（源码包含测试文件，独立安装 ZIP 可不包含）。当前接入 Chat Completion 的正常回复和原生代写；Text Completion 与其他拦截请求的插件尚未完成实机验证。

完整使用说明：[酒馆接入文档](https://github.com/suoluo456/mlx-image-workbench/blob/main/docs/sillytavern.md)。官方说明：[UI 扩展](https://docs.sillytavern.app/for-contributors/writing-extensions/)、[图像生成](https://docs.sillytavern.app/extensions/stable-diffusion/)。
