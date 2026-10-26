"""Start or reuse this exact installation, waiting for health before opening Safari."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workbench_paths import DATA_DIR, MODEL_DIR


def main():
    parser = argparse.ArgumentParser(description='启动 MLX 图像工作台')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        port = int(os.environ.get('MLX_WEB_PORT', '7866'))
        if not 1024 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit('错误：MLX_WEB_PORT 必须是 1024–65535 的端口。')
    url = f'http://127.0.0.1:{port}'
    local_http = build_opener(ProxyHandler({}))

    def health():
        try:
            with local_http.open(url + '/api/health', timeout=1) as response:
                value = json.load(response)
            return (value.get('service') == 'mlx-image-workbench' and
                    value.get('root') == str(ROOT) and value.get('data_dir') == str(DATA_DIR)
                    and value.get('model_dir') == str(MODEL_DIR))
        except (OSError, ValueError):
            return False

    if health():
        print('工作台已启动：' + url, flush=True)
        if not args.no_browser:
            subprocess.run(['open', url], check=True)
        return
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', port))
        except OSError:
            raise SystemExit(f'错误：端口 {port} 已被其他程序占用。请先关闭该程序，或设置 MLX_WEB_PORT。')
    process = subprocess.Popen([str(ROOT / '.venv/bin/python'), str(ROOT / 'web_ui.py')], cwd=ROOT)

    def stop(_signal=None, _frame=None):
        if process.poll() is None:
            process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        print('正在启动，等待网页准备完成……', flush=True)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise SystemExit(f'启动失败，服务已退出（代码 {process.returncode}），请查看上方错误。')
            if health():
                print('工作台已准备好：' + url + '；关闭此终端或按 Control+C 可停止。', flush=True)
                if not args.no_browser:
                    subprocess.run(['open', url], check=True)
                return process.wait()
            time.sleep(.25)
        raise SystemExit('启动超时，请双击「环境检查.command」查看问题。')
    finally:
        stop()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == '__main__':
    sys.exit(main())
