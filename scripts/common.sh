#!/bin/bash
# Shared by the macOS command wrappers. No shell profile or system Python changes.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
export MLX_WORKBENCH_ROOT="$ROOT"
export UV_CACHE_DIR="$ROOT/.tools/uv-cache"
export UV_PYTHON_INSTALL_DIR="$ROOT/.tools/python"
export UV_TOOL_DIR="$ROOT/.tools/uv-tools"
export UV_TOOL_BIN_DIR="$ROOT/.tools/bin"
export UV_HTTP_TIMEOUT="${UV_HTTP_TIMEOUT:-180}"
export UV_CONCURRENT_DOWNLOADS="${UV_CONCURRENT_DOWNLOADS:-4}"
export PIP_CACHE_DIR="$ROOT/.tools/pip-cache"
export HF_HOME="$ROOT/.tools/huggingface"
export XDG_CACHE_HOME="$ROOT/.tools/cache"
export PYTHONPYCACHEPREFIX="$ROOT/.tools/pycache"
export MPLCONFIGDIR="$ROOT/.tools/matplotlib"
export TORCH_HOME="$ROOT/.tools/torch"
export PYTHONNOUSERSITE=1
unset PYTHONPATH PYTHONHOME

fail() { printf '\n错误：%s\n' "$*" >&2; exit 1; }
step() { printf '\n%s\n' "$*"; }
check_platform() {
  [[ "$(uname -s)" == Darwin ]] || fail '目前仅支持 macOS。'
  [[ "$(uname -m)" == arm64 ]] || fail '需要 Apple Silicon Mac，并使用原生终端；Intel/Rosetta 暂不支持。'
  local version
  version="$(sw_vers -productVersion)"
  [[ "${version%%.*}" -ge 26 ]] || fail '当前锁定的 MLX 需要 macOS 26 或更新版本。'
}
require_environment() {
  [[ -x "$ROOT/.venv/bin/python" ]] || fail '尚未安装运行环境，请先双击「安装.command」。'
  [[ -f "$ROOT/.tools/install-complete.json" ]] || fail '上次安装尚未完成，请重新双击「安装.command」继续安装。'
  "$ROOT/.venv/bin/python" -c 'import importlib.metadata as m; import PIL,psutil,requests; assert m.version("mflux")=="0.20.0" and m.version("mlx")=="0.32.2" and m.version("mlx-metal")=="0.32.2"' 2>/dev/null || fail '运行环境缺失或版本不匹配，请重新双击「安装.command」修复。'
}
bootstrap_uv() {
  local version='0.11.8' archive='uv-aarch64-apple-darwin.tar.gz' base
  mkdir -p "$ROOT/.tools/bin" "$ROOT/.tools/downloads"
  if [[ -x "$ROOT/.tools/bin/uv" ]] && [[ "$("$ROOT/.tools/bin/uv" --version)" == "uv $version"* ]]; then return; fi
  local cached_wheel="$ROOT/.tools/downloads/uv-0.11.8-py3-none-macosx_11_0_arm64.whl"
  if [[ -f "$cached_wheel" ]] && [[ "$(shasum -a 256 "$cached_wheel" | awk '{print $1}')" == f0d402e182ab581e934c159cc9edf25ec6e08d32f29aa797980e949afefc87cd ]]; then
    step '复用已通过 SHA256 校验的官方 uv 安装包……'
    mkdir -p "$ROOT/.tools/downloads/uv-wheel"
    /usr/bin/ditto -xk "$cached_wheel" "$ROOT/.tools/downloads/uv-wheel"
    cp "$ROOT/.tools/downloads/uv-wheel/uv-0.11.8.data/scripts/uv" "$ROOT/.tools/bin/uv"
    chmod +x "$ROOT/.tools/bin/uv"
    [[ "$("$ROOT/.tools/bin/uv" --version)" == "uv $version"* ]] || fail 'uv 版本校验失败。'
    return
  fi
  step "下载项目私有安装工具 uv ${version}（支持 HTTPS_PROXY）……"
  base="https://github.com/astral-sh/uv/releases/download/$version"
  if curl --fail --location --retry 1 --connect-timeout 15 --max-time 90 "$base/$archive" -o "$ROOT/.tools/downloads/$archive" &&
     curl --fail --location --retry 1 --connect-timeout 15 --max-time 30 "$base/$archive.sha256" -o "$ROOT/.tools/downloads/$archive.sha256" &&
     (cd "$ROOT/.tools/downloads" && shasum -a 256 -c "$archive.sha256"); then
    tar -xzf "$ROOT/.tools/downloads/$archive" -C "$ROOT/.tools/downloads"
    cp "$ROOT/.tools/downloads/uv-aarch64-apple-darwin/uv" "$ROOT/.tools/bin/uv"
  else
    step 'GitHub 下载未成功，改用官方 PyPI 的固定版本安装包……'
    local wheel='uv-0.11.8-py3-none-macosx_11_0_arm64.whl'
    local checksum='f0d402e182ab581e934c159cc9edf25ec6e08d32f29aa797980e949afefc87cd'
    local wheel_url='https://files.pythonhosted.org/packages/d5/62/82953018801a250e16b091ef4b5e95e939b2f01224363d6fc80f600b7eff/uv-0.11.8-py3-none-macosx_11_0_arm64.whl'
    curl --fail --location --retry 3 --connect-timeout 30 "$wheel_url" -o "$ROOT/.tools/downloads/$wheel" || fail '安装工具下载失败，请检查网络或 HTTPS_PROXY 后重新运行。'
    [[ "$(shasum -a 256 "$ROOT/.tools/downloads/$wheel" | awk '{print $1}')" == "$checksum" ]] || fail 'uv 安装包 SHA256 不匹配。'
    mkdir -p "$ROOT/.tools/downloads/uv-wheel"
    /usr/bin/ditto -xk "$ROOT/.tools/downloads/$wheel" "$ROOT/.tools/downloads/uv-wheel"
    if [[ -f "$ROOT/.tools/downloads/uv-wheel/uv-0.11.8.data/scripts/uv" ]]; then
      cp "$ROOT/.tools/downloads/uv-wheel/uv-0.11.8.data/scripts/uv" "$ROOT/.tools/bin/uv"
    elif [[ -f "$ROOT/.tools/downloads/uv-wheel/uv/uv" ]]; then
      cp "$ROOT/.tools/downloads/uv-wheel/uv/uv" "$ROOT/.tools/bin/uv"
    else
      fail '官方 uv 安装包目录结构发生变化，请报告此错误。'
    fi
  fi
  chmod +x "$ROOT/.tools/bin/uv"
  [[ "$("$ROOT/.tools/bin/uv" --version)" == "uv $version"* ]] || fail 'uv 版本校验失败。'
}
choose_python() {
  local candidate
  for candidate in "${MLX_PYTHON:-}" "$(command -v python3.12 || true)" "$(command -v python3 || true)"; do
    [[ -n "$candidate" && -x "$candidate" ]] || continue
    if [[ "$candidate" == /usr/bin/python3 ]] && ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
      continue  # Apple's placeholder may otherwise prompt to install developer tools.
    fi
    if "$candidate" -c 'import platform,sys;sys.exit(not(sys.version_info[:2]==(3,12) and platform.machine()=="arm64" and sys.prefix==sys.base_prefix))' 2>/dev/null; then
      PYTHON_BIN="$candidate"; return
    fi
  done
  bootstrap_uv
  step '安装项目私有 Python 3.12（存放于 .tools/python）……'
  "$ROOT/.tools/bin/uv" python install 3.12.13 --no-bin
  PYTHON_BIN="$("$ROOT/.tools/bin/uv" python find --managed-python 3.12.13)"
}
