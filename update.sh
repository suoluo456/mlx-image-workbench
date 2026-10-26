#!/bin/bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/scripts/common.sh"
echo '更新前请停止工作台；模型、图片和设置会保留。'
if [[ ! -d "$ROOT/.git" ]]; then
  echo '你使用的是 Release ZIP。请下载新版，先备份 data；将新版程序放回原目录后双击「安装.command」，选择暂不下载模型。'
  echo '也可以将新版解压到新目录，并把旧版的 data 和 models 文件夹复制过去。不要复制 .venv 或 .tools。'
  exit 0
fi
[[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ]] || fail '源码有本地修改，请先保存修改后再更新。'
git -C "$ROOT" pull --ff-only
exec "$ROOT/install.sh" --models none --yes
