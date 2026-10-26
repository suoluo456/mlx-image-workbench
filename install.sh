#!/bin/bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/scripts/common.sh"
MODELS='' TAVERN='' YES=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --models) [[ $# -ge 2 ]] || fail '--models 缺少选项'; MODELS="$2"; shift 2 ;;
    --tavern) TAVERN=yes; shift ;;
    --no-tavern) TAVERN=no; shift ;;
    --yes) YES=1; shift ;;
    --help|-h) echo 'install.sh [--models qwen21_turbo,zimage|none] [--tavern|--no-tavern] [--yes]'; exit 0 ;;
    *) fail "未知参数：$1" ;;
  esac
done
check_platform
if [[ -z "$MODELS" ]]; then
  if [[ "$YES" == 1 ]]; then MODELS=none
  else
    echo '选择模型：1 Qwen Turbo；2 Z-Image；3 两者；4 暂不下载'
    read -r -p '请选择 [4]：' choice
    case "${choice:-4}" in 1) MODELS=qwen21_turbo ;; 2) MODELS=zimage ;; 3) MODELS=qwen21_turbo,zimage ;; 4) MODELS=none ;; *) fail '请选择 1–4。' ;; esac
  fi
fi
case "$MODELS" in none|qwen21_turbo|zimage|qwen21_turbo,zimage|zimage,qwen21_turbo) ;; *) fail '模型选项无效。' ;; esac
if [[ -z "$TAVERN" ]]; then
  TAVERN=keep
  if [[ "$YES" != 1 ]]; then
    TAVERN=no
    read -r -p '安装酒馆人物参考支持和额外模型？[y/N]：' choice
    [[ "${choice:-n}" != y && "${choice:-n}" != Y ]] || TAVERN=yes
  fi
fi
unset HF_HUB_OFFLINE TRANSFORMERS_OFFLINE UV_OFFLINE
step '1/4 检查运行环境……'
mkdir -p "$ROOT/.tools"
INSTALL_LOCK="$ROOT/.tools/install.lock"
if ! mkdir "$INSTALL_LOCK" 2>/dev/null; then
  [[ ! -L "$INSTALL_LOCK" && -f "$INSTALL_LOCK/pid" ]] || fail '另一个安装正在启动，请稍后再试。'
  old_pid="$(cat "$INSTALL_LOCK/pid")"
  [[ "$old_pid" =~ ^[0-9]+$ ]] || fail '安装锁文件无效，请先关闭其他安装窗口。'
  if kill -0 "$old_pid" 2>/dev/null; then fail '另一个安装正在进行，请等待它完成。'; fi
  rm "$INSTALL_LOCK/pid"
  rmdir "$INSTALL_LOCK" || fail '安装锁目录包含额外文件，请先检查。'
  mkdir "$INSTALL_LOCK"
fi
printf '%s\n' "$$" > "$INSTALL_LOCK/pid"
release_install_lock() { rm -f "$INSTALL_LOCK/pid"; rmdir "$INSTALL_LOCK" 2>/dev/null || true; }
trap release_install_lock EXIT
trap 'printf "\n安装未完成，请查看上方错误后重新双击「安装.command」；已下载的缓存会复用。\n" >&2' ERR
trap 'exit 130' INT
trap 'exit 143' TERM
rm -f "$ROOT/.tools/install-complete.json"
free_kb="$(df -Pk "$ROOT" | awk 'END {print $4}')"
[[ "$free_kb" -ge 6291456 ]] || fail '安装环境至少需要约 6 GB 可用空间（模型另计）。'
choose_python
bootstrap_uv
step "使用 Python：$PYTHON_BIN"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then "$PYTHON_BIN" -m venv "$ROOT/.venv"; fi
"$ROOT/.venv/bin/python" -c 'import platform,sys; assert sys.version_info[:2]==(3,12) and platform.machine()=="arm64", "现有环境版本不兼容"'
step '2/4 安装固定版本的网页和 MLX 依赖……'
"$ROOT/.tools/bin/uv" pip sync --python "$ROOT/.venv/bin/python" "$ROOT/requirements.lock.txt"
"$ROOT/.tools/bin/uv" pip check --python "$ROOT/.venv/bin/python"
if [[ "$TAVERN" == yes ]]; then
  step '安装可选人物参考环境（独立于基础文生图环境）……'
  if [[ ! -x "$ROOT/.venv-reference/bin/python" ]]; then "$PYTHON_BIN" -m venv "$ROOT/.venv-reference"; fi
  "$ROOT/.tools/bin/uv" pip sync --python "$ROOT/.venv-reference/bin/python" "$ROOT/requirements-reference.lock.txt"
  "$ROOT/.tools/bin/uv" pip check --python "$ROOT/.venv-reference/bin/python"
  if /usr/bin/xcode-select -p >/dev/null 2>&1; then
    mkdir -p "$ROOT/bin"
    if /usr/bin/xcrun swiftc -module-cache-path "$ROOT/.tools/swift-module-cache" "$ROOT/face_box.swift" -o "$ROOT/bin/face-box"; then
      echo '可选人脸裁剪工具已编译。'
    else
      echo '可选人脸裁剪工具编译失败，将保留原参考图继续使用。'
    fi
  else
    echo '未安装 Apple 开发工具，跳过自动人脸裁剪；人物参考功能仍可使用。'
  fi
fi
step '3/4 下载所选模型；只有校验通过后才标记可用……'
echo '模型遵循各自许可证；Qwen 模型适用 Qwen Research License，详见 THIRD_PARTY_NOTICES.md。'
if [[ "$MODELS" != none ]]; then
  IFS=',' read -r -a chosen_models <<< "$MODELS"
  "$ROOT/.venv/bin/python" "$ROOT/scripts/manage_models.py" install "${chosen_models[@]}"
fi
if [[ "$TAVERN" == yes ]]; then
  echo '酒馆参考功能需要额外视觉组件，并依赖 Qwen Turbo；将自动补齐。'
  "$ROOT/.venv/bin/python" "$ROOT/scripts/manage_models.py" install qwen21_turbo_ref
fi
if [[ "$TAVERN" != keep ]]; then
  MLX_TAVERN_INSTALL="$TAVERN" "$ROOT/.venv/bin/python" "$ROOT/scripts/save_settings.py"
fi
step '4/4 检查安装……'
"$ROOT/.venv/bin/python" "$ROOT/scripts/doctor.py"
"$ROOT/.venv/bin/python" -c 'import json,pathlib,sys;pathlib.Path(sys.argv[1]).write_text(json.dumps({"app":"mlx-image-workbench","schema":1,"mflux":"0.20.0","mlx":"0.32.2"})+"\n")' "$ROOT/.tools/install-complete.json"
step '安装完成！双击「启动.command」打开网页工作台。首次启动不会自动下载模型或生成图片。'
