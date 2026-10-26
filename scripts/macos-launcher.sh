#!/bin/bash
# Finder entry points: all choices use native dialogs; Terminal shows progress.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

dialog() {
  /usr/bin/osascript - "$@" <<'APPLESCRIPT'
on run argv
  display dialog (item 1 of argv) with title "MLX Image Workbench" buttons {"好"} default button "好"
end run
APPLESCRIPT
}

fail() {
  local code="$?"
  trap - ERR
  dialog "操作没有完成。请查看这个终端窗口最后的错误说明，也可以双击『环境检查.command』。窗口会保留，方便查看。" || true
  exit "$code"
}
trap fail ERR

case "${1:-start}" in
  install)
    selection=$(/usr/bin/osascript <<'APPLESCRIPT'
set choices to {"Qwen Turbo + Z-Image（约35 GB）", "仅 Qwen-Image-2.1 Turbo（约24 GB）", "仅 Z-Image-Turbo（约11 GB）", "只装工作台，稍后下载模型"}
set result to choose from list choices with title "安装 MLX Image Workbench" with prompt "适用于 M 系列 Mac，macOS 26 或更新。自动准备 Python，无需提前安装。\n\nQwen 模型仅限研究/评估；商业使用需向模型作者另获许可。Z-Image 模型使用 Apache 2.0。\n\n请选择要安装的模型：" default items {item 3 of choices} OK button name "继续" cancel button name "取消"
if result is false then return "cancel"
repeat with i from 1 to count choices
  if item 1 of result is item i of choices then return i as text
end repeat
APPLESCRIPT
)
    case "$selection" in
      1) models="qwen21_turbo,zimage" ;;
      2) models="qwen21_turbo" ;;
      3) models="zimage" ;;
      4) models="none" ;;
      *) exit 0 ;;
    esac
    tavern=$(/usr/bin/osascript <<'APPLESCRIPT'
set result to display dialog "是否安装可选的酒馆配图支持？\n\n它会额外准备人物参考环境与 Qwen Turbo 配套组件，需要更多下载和磁盘空间。Qwen 模型仅限研究/评估。\n\n这一步不会修改你的酒馆；扩展由你自行安装。" with title "可选：SillyTavern" buttons {"取消", "暂不安装", "安装酒馆支持"} default button "暂不安装" cancel button "取消"
return button returned of result
APPLESCRIPT
) || exit 0
    option="--no-tavern"
    [[ "$tavern" == "安装酒馆支持" ]] && option="--tavern"
    bash "$ROOT/install.sh" --models "$models" "$option" --yes
    result=$(/usr/bin/osascript <<'APPLESCRIPT'
set result to display dialog "安装完成。现在打开网页工作台？" with title "MLX Image Workbench" buttons {"稍后", "打开工作台"} default button "打开工作台"
return button returned of result
APPLESCRIPT
)
    if [[ "$result" == "打开工作台" ]]; then
      bash "$ROOT/start.sh"
    fi
    ;;
  start)
    if [[ ! -x "$ROOT/.venv/bin/python" || ! -f "$ROOT/.tools/install-complete.json" ]]; then
      result=$(/usr/bin/osascript <<'APPLESCRIPT'
set result to display dialog "这个工作台还没有安装运行环境。现在安装？" with title "MLX Image Workbench" buttons {"取消", "开始安装"} default button "开始安装" cancel button "取消"
return button returned of result
APPLESCRIPT
) || exit 0
      exec bash "$ROOT/scripts/macos-launcher.sh" install
    fi
    bash "$ROOT/start.sh"
    ;;
  doctor)
    # A failing diagnostic is displayed in this terminal, not hidden by a dialog.
    if bash "$ROOT/doctor.sh"; then code=0; else code="$?"; fi
    dialog "检查完成。结果显示在终端窗口中。分享结果前请确认其中的本机路径可以公开。" || true
    exit "$code"
    ;;
  models)
    if [[ ! -x "$ROOT/.venv/bin/python" || ! -f "$ROOT/.tools/install-complete.json" ]]; then
      dialog '请先双击「安装.command」准备运行环境。'
      exit 0
    fi
    action=$(/usr/bin/osascript <<'APPLESCRIPT'
set answer to choose from list {"下载或修复模型", "完整校验模型", "移除模型（保留图片和历史）"} with title "模型管理" with prompt "请选择操作：" OK button name "继续" cancel button name "取消"
if answer is false then return "cancel"
return item 1 of answer
APPLESCRIPT
) || exit 0
    [[ "$action" != cancel ]] || exit 0
    selected=$(/usr/bin/osascript <<'APPLESCRIPT'
set answer to choose from list {"Qwen-Image-2.1 Turbo", "Z-Image-Turbo", "Qwen Turbo 人物参考（酒馆组件）"} with title "模型管理" with prompt "请选择模型：" OK button name "继续" cancel button name "取消"
if answer is false then return "cancel"
return item 1 of answer
APPLESCRIPT
) || exit 0
    case "$selected" in
      'Qwen-Image-2.1 Turbo') model=qwen21_turbo ;;
      'Z-Image-Turbo') model=zimage ;;
      'Qwen Turbo 人物参考（酒馆组件）') model=qwen21_turbo_ref ;;
      *) exit 0 ;;
    esac
    case "$action" in
      '下载或修复模型')
        if [[ "$model" != zimage ]]; then
          /usr/bin/osascript <<'APPLESCRIPT' >/dev/null || exit 0
display dialog "Qwen 模型仅限研究/评估用途，商业使用需另获许可。将联网下载并校验所选组件。" with title "模型下载" buttons {"取消", "继续下载"} default button "继续下载" cancel button "取消"
APPLESCRIPT
        fi
        if [[ "$model" == qwen21_turbo_ref ]]; then
          bash "$ROOT/install.sh" --models none --tavern --yes
        else
          bash "$ROOT/models.sh" install "$model"
        fi
        ;;
      '完整校验模型') bash "$ROOT/models.sh" verify "$model" ;;
      '移除模型（保留图片和历史）')
        /usr/bin/osascript - "$selected" <<'APPLESCRIPT' >/dev/null || exit 0
on run argv
  display dialog ("确定移除模型「" & item 1 of argv & "」？\n\n只删除本安装器管理的模型文件，保留图片、历史和设置。以后使用需重新下载。请先停止工作台。") with title "移除模型" buttons {"取消", "移除模型"} default button "取消" cancel button "取消"
end run
APPLESCRIPT
        bash "$ROOT/models.sh" remove "$model" --yes
        ;;
      *) exit 0 ;;
    esac
    dialog '操作完成，详情见终端窗口。'
    ;;
  *) printf '未知操作。\n' >&2; exit 2 ;;
esac
