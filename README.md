# MLX Image Workbench

在 M 系列 Mac 上运行的本地生图工作台。支持 **Qwen-Image-2.1 Turbo MLX 8bit** 与 **Z-Image-Turbo MLX Q8**，提供批量生成、历史查询、收藏、参数重用和可选的 SillyTavern 配图扩展。此版本不支持 LoRA。

## 双击安装

支持 **Apple Silicon、macOS 26 或更新系统**。不要求提前安装 Python、Homebrew 或 Git。安装器会为本项目准备 Python 3.12 和独立环境。

1. 下载 Release 附件 `MLX-Image-Workbench-版本号-macOS.zip`，在 Finder 中解压。
2. 把整个文件夹移到准备长期使用的位置，双击 **安装.command**。
3. 在弹窗里选择模型，并选择是否安装酒馆支持。终端只用于显示进度，无需输入命令。
4. 安装完成后双击 **启动.command**，浏览器自动打开工作台。默认地址为 `http://127.0.0.1:7866`。

安装中断后，重新运行安装器可以继续。也可以先选择“只装工作台”，稍后双击 **模型管理.command** 下载、修复、完整校验或移除模型。没有模型时可以打开网页，但不能生成图片。

Release ZIP 会保留 `.command` 的执行权限。**本发布包尚未经过 Apple Developer ID 签名和公证**，下载后可能需要在“系统设置 → 隐私与安全性”对该文件选择“仍要打开”。无需关闭系统安全保护。详见 [Apple 的官方说明](https://support.apple.com/102445) 和包内 `先读我.txt`。通过其他工具重新打包或中转可能丢失权限；优先使用 Release ZIP 和 macOS 自带解压工具。

## 模型与磁盘

| 模型 | 已安装权重约占用 | 说明 |
| --- | ---: | --- |
| Qwen-Image-2.1 Turbo MLX 8bit | 24 GB | 包含文字编码器、处理器和 VAE；固定 8 步 |
| Z-Image-Turbo MLX Q8 | 11 GB | 默认 9 步 |

两套基础模型约 35 GB；安装时有临时下载和转换文件，峰值超过 43 GB，另外还需要运行环境和图片空间。建议基础双模型安装预留至少 60 GB。可选酒馆人物参考还需额外组件，安装器会计算并提示。

模型体积不是运行内存需求。较大尺寸、多张不同提示词和人物参考会增加内存使用；先从小尺寸单张开始。最低可用内存尚未在多台设备上验收，不承诺所有 M 系列配置具有相同性能。

模型在安装时联网下载；生成过程使用本机模型。下载来源、固定版本、文件大小和校验信息见 `model-manifest.json`。支持 Hugging Face 的常规代理环境变量。首次安装还需访问 Python 包和工具下载源。

**模型许可与代码许可分别适用。** 本项目代码采用 MIT；Qwen-Image-2.1 Turbo 及其配套 Qwen 模型采用 Qwen Research License，仅授权研究/评估等许可内用途，商业使用需要另获授权。Z-Image-Turbo 的模型页标注 Apache 2.0。详见 [第三方说明](THIRD_PARTY_NOTICES.md)。模型权重不包含在 GitHub 源码或 Release ZIP 中。

## 使用与数据

在网页选择已安装的模型，输入描述并开始生成。支持随机提示词、连续多张、停止、历史筛选、收藏和重跑设置；重跑设置只回填参数，点击生成后才运行。停止服务可以在服务终端按 Control+C，关闭浏览器不会自动停止服务。

| 目录 | 内容 |
| --- | --- |
| `models/` | 模型和安装清单 |
| `data/output/` | 生成图片、参数、组图和历史数据库 |
| `data/references/` | 用户上传的参考图 |
| `data/logs/` | 本机运行与可选酒馆诊断日志 |
| `data/settings.json` | 本机可选功能配置 |
| `.venv/`、`.venv-reference/` | 独立 Python 环境 |
| `.tools/` | 本项目的安装工具、受管 Python 和缓存 |

这些运行目录都不进入源码提交或发布包。公开包不含开发者的历史记录、参考图、日志、提示词和个人角色配置。提示词会随生成结果保存在本机；分享图片或诊断文件前请自行检查其内容。

如需换磁盘，可以在启动和安装时设置同一个 `MLX_WORKBENCH_MODEL_DIR`；`MLX_WORKBENCH_DATA_DIR` 可指定数据目录。默认设置适合直接双击使用。

## 可选：SillyTavern

基础工作台不依赖酒馆。安装时选择酒馆支持，会准备人物参考环境和模型；**不会修改已安装的 SillyTavern**。

工作流 JSON 可以导入酒馆的 ComfyUI 工作流编辑器。自动剧情配图、人物头像和渲染设置需要独立扩展，不能只靠一个工作流 JSON 安装。扩展提供服务地址设置、连接检查及主动应用配置按钮，同机默认地址为 `http://127.0.0.1:7866`。

安装步骤与限制见 [SillyTavern 使用说明](docs/sillytavern.md)。浏览器扩展不能代替用户启动本机 Python 服务；使用前先双击工作台的启动入口。

## 命令行入口（可选）

```sh
./install.sh
./install.sh --models qwen21_turbo,zimage --no-tavern --yes
./install.sh --models qwen21_turbo --tavern --yes
./start.sh
./models.sh list
./models.sh verify qwen21_turbo
./doctor.sh
```

启动端口通过 `MLX_WEB_PORT` 修改；修改后也要更新酒馆扩展的连接地址。服务只监听本机回环地址，不提供公网托管或多用户服务。

## 更新与排错

双击 **环境检查.command** 查看诊断结果。下载失败时先确认网络和可用磁盘空间，再重新运行安装器。模型损坏时可用模型检查/安装入口重新校验和修复。不要删除 `data/` 来修复运行环境，否则会丢失自己的历史和图片。

ZIP 安装用户更新时，将新版本解压到新文件夹，再迁移自己的 `data/` 与 `models/`，重新安装运行环境。不要复制旧 `.venv`；其中包含路径关联。保留旧目录作为回退，确认新版本运行正常后再自行清理。

## 开发与发布

发布采用 `release-files.json` 中明确列出的源文件；不会递归打包工作目录。发布检查拒绝用户数据目录、符号链接、未审查二进制、大文件和明显凭据。

```sh
python3 scripts/audit_release.py
python3 scripts/build_release.py
```

生成的 `dist/` 包含工作台 ZIP、独立酒馆扩展 ZIP 和 SHA256 清单。打包器明确写入脚本的 `755` 权限。源码检查与无模型测试不能代替真机生成验收；发布验证范围见 [验证记录](docs/validation.md)。
