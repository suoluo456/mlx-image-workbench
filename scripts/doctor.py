"""Small offline environment check. Never loads model weights."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    errors = []
    print('MLX 图像工作台 · 环境检查（不加载模型）')
    print(f'系统：{platform.system()} {platform.mac_ver()[0]} / {platform.machine()}')
    print(f'Python：{platform.python_version()}')
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        errors.append('需要 Apple Silicon Mac。')
    if sys.version_info[:2] != (3, 12):
        errors.append('需要安装器创建的 Python 3.12 环境。')
    for name, expected in [('mflux', '0.20.0'), ('mlx', '0.32.2'), ('mlx-metal', '0.32.2')]:
        try:
            version = importlib.metadata.version(name)
            print(f'{name}：{version}')
            if version != expected:
                errors.append(f'{name} 需要 {expected}。')
        except importlib.metadata.PackageNotFoundError:
            errors.append(f'缺少 {name}，请重新运行安装。')
    for name in ('psutil', 'PIL', 'requests'):
        try:
            __import__(name)
        except ImportError:
            errors.append(f'缺少 {name}。')
    from workbench_paths import DATA_DIR, MODEL_DIR
    for title, path in [('数据', DATA_DIR), ('模型', MODEL_DIR)]:
        existing = path
        while not existing.exists():
            existing = existing.parent
        print(f'{title}目录：{path}；所在磁盘可用 {shutil.disk_usage(existing).free / 1e9:.1f} GB')
    settings = DATA_DIR / 'settings.json'
    try:
        tavern = json.loads(settings.read_text()).get('tavern_enabled', False) if settings.exists() else False
        print('酒馆扩展：' + ('已启用' if tavern else '关闭'))
        if tavern and not (ROOT / '.venv-reference/bin/python').is_file():
            errors.append('酒馆参考环境缺失，请重新安装并选择酒馆支持。')
    except (ValueError, OSError):
        errors.append('settings.json 无法读取。')
    from model_registry import catalog
    for model in catalog():
        print(f"{model['name']}：" + ('文件完整' if model['ready'] else '未安装或不完整'))
    if os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy'):
        print('下载代理：已配置（地址隐藏）')
    for error in errors:
        print('问题：' + error)
    print('检查完成。未进行推理；完整文件哈希校验请使用模型管理。')
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
