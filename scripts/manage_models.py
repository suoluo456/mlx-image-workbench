"""Pinned model downloads with resume, SHA256 verification and guarded removal."""
import argparse
from contextlib import contextmanager
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import sys
import time
from urllib.parse import quote, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workbench_paths import MODEL_DIR

MANIFEST = json.loads((ROOT / 'model-manifest.json').read_text())['models']
APP = 'mlx-image-workbench'
RESERVE_BYTES = 2 * 10**9


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def valid(path, spec, full=True):
    return (path.is_file() and path.stat().st_size == spec['size'] and
            (not full or digest(path) == spec['sha256']))


def safe_target(directory, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('模型清单包含非法路径。')
    result = directory.joinpath(*path.parts)
    for parent in [result, *result.parents]:
        if parent == MODEL_DIR:
            break
        if parent.is_symlink():
            raise ValueError('下载目标存在符号链接，请检查模型目录。')
    return result


def write_json(path, value):
    temp = path.with_name(path.name + '.tmp')
    if temp.is_symlink():
        raise ValueError('写入目标不应为符号链接。')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


@contextmanager
def model_lock():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / '.model-operation.lock'
    if path.is_symlink():
        raise ValueError('模型锁文件不应为符号链接。')
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('另一个安装/校验/移除操作正在进行，请稍后重试。')
        yield


def download(directory, spec):
    target = safe_target(directory, spec['path'])
    target.parent.mkdir(parents=True, exist_ok=True)
    if valid(target, spec):
        print('已校验，跳过：' + spec['path'], flush=True)
        return target
    endpoint = os.environ.get('HF_ENDPOINT', 'https://huggingface.co').rstrip('/')
    parsed = urlparse(endpoint)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('HF_ENDPOINT 必须是没有用户名密码的 HTTPS 地址。')
    url = endpoint + '/' + spec['repo'] + '/resolve/' + spec['revision'] + '/' + quote(spec['remote_path'], safe='/')
    partial = target.with_name(target.name + '.part')
    if partial.is_symlink():
        raise ValueError('下载临时文件不应为符号链接。')
    for attempt in range(4):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > spec['size']:
                partial.unlink()
                offset = 0
            if offset != spec['size']:
                headers = {'Range': f'bytes={offset}-', 'Accept-Encoding': 'identity'} if offset else {'Accept-Encoding': 'identity'}
                token = os.environ.get('HF_TOKEN')
                if token and parsed.hostname == 'huggingface.co':
                    headers['Authorization'] = 'Bearer ' + token
                print(f"下载 {spec['path']}：{offset / 1e9:.2f}/{spec['size'] / 1e9:.2f} GB", flush=True)
                with requests.get(url, headers=headers, stream=True, timeout=(30, 90)) as response:
                    response.raise_for_status()
                    if response.status_code == 206:
                        expected = f"bytes {offset}-{spec['size'] - 1}/{spec['size']}"
                        if response.headers.get('Content-Range') != expected:
                            raise ValueError('服务器返回了错误的续传范围。')
                    elif response.status_code == 200:
                        offset = 0  # A mirror may not support Range; restart this file safely.
                    else:
                        raise ValueError('下载服务器返回了不支持的状态。')
                    last = time.monotonic()
                    with partial.open('ab' if offset else 'wb') as stream:
                        for block in response.iter_content(8 * 1024 * 1024):
                            stream.write(block)
                            offset += len(block)
                            if offset > spec['size']:
                                raise ValueError('下载内容超过清单长度。')
                            if time.monotonic() - last > 3:
                                print(f"  {100 * offset / spec['size']:.1f}%", flush=True)
                                last = time.monotonic()
            print('校验 SHA256：' + spec['path'], flush=True)
            if not valid(partial, spec):
                partial.unlink(missing_ok=True)
                raise ValueError('文件长度或 SHA256 不匹配，已清理该临时文件。')
            partial.replace(target)
            return target
        except (requests.RequestException, OSError, ValueError) as exc:
            # Do not print proxy addresses, authentication headers or tokens.
            status = getattr(getattr(exc, 'response', None), 'status_code', None)
            reason = f'HTTP {status}' if status else type(exc).__name__
            if isinstance(exc, ValueError):
                reason = str(exc)
            elif isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
                raise ValueError('磁盘空间已用尽。请释放空间后重试，下载进度已保留。') from None
            print(f'下载失败（{reason}），第 {attempt + 1}/4 次；可设置 HTTPS_PROXY 后重试。', flush=True)
            if attempt == 3:
                raise ValueError('下载未完成，已保留可续传文件：' + spec['path']) from None
            time.sleep(2 * (attempt + 1))


def transformer_index(path):
    with path.open('rb') as stream:
        length = struct.unpack('<Q', stream.read(8))[0]
        if length > 16 * 1024 * 1024:
            raise ValueError('模型头部长度不合法。')
        header = json.loads(stream.read(length))
    return dict(metadata=header.get('__metadata__', {}),
                weight_map={key: path.name for key in header if key != '__metadata__'})


def repack_transformer(directory, spec):
    target = safe_target(directory, spec['transformer']['path'])
    target.parent.mkdir(parents=True, exist_ok=True)
    if not valid(target, spec['transformer']):
        source = download(directory, spec['transformer_source'])
        print('转换 Turbo 文件格式（保持全部权重字节不变）……', flush=True)
        with source.open('rb') as stream:
            length = struct.unpack('<Q', stream.read(8))[0]
            if length > 16 * 1024 * 1024:
                raise ValueError('模型头部长度不合法。')
            header = json.loads(stream.read(length))
            mapped = {key.replace('modulation.1.', 'modulation.layers.1.', 1)
                      if key.startswith('modulation.1.') else key: value
                      for key, value in header.items() if key != '__metadata__'}
            if len(mapped) != len(header):
                raise ValueError('Turbo 源文件结构与固定版本不符。')
            source_spec = spec['transformer_source']
            mapped['__metadata__'] = dict(quantization_level='8', mflux_version='0.20.0',
                                          source_repo=source_spec['repo'], source_revision=source_spec['revision'])
            body = json.dumps(mapped, separators=(',', ':')).encode()
            body += b' ' * (-len(body) % 8)
            temp = safe_target(directory, spec['transformer']['path'] + '.part')
            with temp.open('wb') as output:
                output.write(struct.pack('<Q', len(body)) + body)
                shutil.copyfileobj(stream, output, length=8 * 1024 * 1024)
        if not valid(temp, spec['transformer']):
            temp.unlink(missing_ok=True)
            raise ValueError('转换结果 SHA256 不匹配。')
        temp.replace(target)
        source.unlink()
        if not any(source.parent.iterdir()):
            source.parent.rmdir()
    index = transformer_index(target)
    write_json(target.parent / 'model.safetensors.index.json', index)


def check_space(spec, directory):
    def remaining(entry):
        target = directory / entry['path']
        if target.is_file():
            print('检查已有文件：' + entry['path'], flush=True)
        if valid(target, entry):
            return 0
        partial = target.with_name(target.name + '.part')
        resumed = partial.stat().st_size if partial.is_file() and not partial.is_symlink() else 0
        return entry['size'] - resumed if 0 <= resumed <= entry['size'] else entry['size']
    needed = sum(remaining(entry) for entry in spec['files'])
    if 'transformer' in spec and not valid(directory / spec['transformer']['path'], spec['transformer']):
        # An old same-sized transformer may need replacement after a version update.
        # Keep the old target until its replacement is verified, so reserve both source and output.
        needed += spec['transformer']['size'] + remaining(spec['transformer_source'])
    free = shutil.disk_usage(MODEL_DIR).free
    print(f'预计还需磁盘空间约 {needed / 1e9:.2f} GB，另保留 2 GB；当前可用 {free / 1e9:.2f} GB。', flush=True)
    if free < needed + RESERVE_BYTES:
        raise ValueError('磁盘空间不足。请释放空间，或设置 MLX_WORKBENCH_MODEL_DIR 到其他磁盘。')


def install(model_id, completed):
    if model_id in completed:
        return
    spec = MANIFEST[model_id]
    for required in spec.get('requires', []):
        install(required, completed)
    directory = MODEL_DIR / spec['folder']
    if directory.is_symlink():
        raise ValueError('模型目录不能是符号链接，请使用 MLX_WORKBENCH_MODEL_DIR 指定位置。')
    if directory.is_dir() and any(directory.iterdir()) and not (directory / '.workbench-model.json').is_file():
        raise ValueError('目标目录已有不属于此安装器的文件，请使用新的模型目录；原文件保持不变。')
    directory.mkdir(parents=True, exist_ok=True)
    owner = directory / '.workbench-model.json'
    if owner.exists() and json.loads(owner.read_text()) != dict(app=APP, model_id=model_id):
        raise ValueError('模型目录归属不匹配。')
    write_json(owner, dict(app=APP, model_id=model_id))
    (directory / '.ready.json').unlink(missing_ok=True)
    print('\n安装：' + spec['name'], flush=True)
    check_space(spec, directory)
    for entry in spec['files']:
        download(directory, entry)
    if 'transformer' in spec:
        repack_transformer(directory, spec)
    if model_id == 'qwen21_turbo_ref':
        source = MODEL_DIR / MANIFEST['qwen21_turbo']['folder'] / 'transformer'
        for filename in ('0.safetensors', 'model.safetensors.index.json'):
            link = directory / 'transformer' / filename
            if link.is_symlink():
                if link.resolve() != (source / filename).resolve():
                    raise ValueError('人物参考模型的共享权重链接不匹配。')
            elif link.exists():
                raise ValueError('人物参考共享权重位置被其他文件占用。')
            else:
                link.symlink_to(os.path.relpath(source / filename, link.parent))
        write_json(directory / 'model_index.json', dict(_class_name='QwenImage21Pipeline',
                   sample_sigmas=[1.0, .978453, .95418, .926626, .89508, .845148, .704534, .414568]))
    names = [entry['path'] for entry in spec['files']]
    if model_id in ('qwen21_turbo', 'qwen21_turbo_ref'):
        names += ['transformer/0.safetensors', 'transformer/model.safetensors.index.json']
    if model_id == 'qwen21_turbo_ref':
        names += ['model_index.json']
    files = {name: (directory / name).stat().st_size for name in names}
    hashes = {entry['path']: entry['sha256'] for entry in spec['files']}
    for name in names:
        if name not in hashes:
            hashes[name] = (MANIFEST['qwen21_turbo']['transformer']['sha256']
                            if name == 'transformer/0.safetensors' else digest(directory / name))
    write_json(directory / '.ready.json', dict(app=APP, model_id=model_id, backend='mlx',
               model='Qwen/Qwen-Image-2.1-Turbo' if model_id.startswith('qwen') else 'z-image-turbo',
               files=files, sha256=hashes))
    completed.add(model_id)
    print('模型已安装并校验：' + spec['name'], flush=True)


def verify(model_id):
    spec = MANIFEST[model_id]
    directory = MODEL_DIR / spec['folder']
    marker = directory / '.ready.json'
    if not marker.is_file():
        raise ValueError(spec['name'] + ' 尚未完整安装。')
    verified_hashes = {}
    for entry in spec['files']:
        print('校验：' + entry['path'], flush=True)
        if not valid(directory / entry['path'], entry):
            raise ValueError('校验失败，请重新安装修复：' + entry['path'])
        verified_hashes[entry['path']] = entry['sha256']
    if model_id in ('qwen21_turbo', 'qwen21_turbo_ref'):
        target = directory / 'transformer/0.safetensors'
        if not valid(target, MANIFEST['qwen21_turbo']['transformer']):
            raise ValueError('Turbo 绘图权重校验失败。')
        actual = json.loads((directory / 'transformer/model.safetensors.index.json').read_text())
        if actual != transformer_index(target):
            raise ValueError('Turbo 权重索引不匹配，请重新安装修复。')
        verified_hashes['transformer/0.safetensors'] = MANIFEST['qwen21_turbo']['transformer']['sha256']
    if model_id == 'qwen21_turbo_ref':
        expected_index = dict(_class_name='QwenImage21Pipeline',
                              sample_sigmas=[1.0, .978453, .95418, .926626, .89508, .845148, .704534, .414568])
        if json.loads((directory / 'model_index.json').read_text()) != expected_index:
            raise ValueError('人物参考模型时间表不匹配，请重新安装修复。')
    ready = json.loads(marker.read_text())
    if not ready.get('files') or not ready.get('sha256'):
        raise ValueError('安装记录缺少文件校验信息。')
    expected_names = set(entry['path'] for entry in spec['files'])
    if model_id in ('qwen21_turbo', 'qwen21_turbo_ref'):
        expected_names.update(('transformer/0.safetensors', 'transformer/model.safetensors.index.json'))
    if model_id == 'qwen21_turbo_ref':
        expected_names.add('model_index.json')
    if set(ready['files']) != expected_names or set(ready['sha256']) != expected_names:
        raise ValueError('安装记录的文件清单不完整或存在额外路径。')
    for name, size in ready['files'].items():
        path = directory / name
        if not path.is_file() or path.stat().st_size != size:
            raise ValueError('安装记录与实际文件不符：' + name)
        actual_hash = verified_hashes.get(name) or digest(path)
        if ready['sha256'][name] != actual_hash:
            raise ValueError('安装记录与实际文件 SHA256 不符：' + name)
    print('完整校验通过：' + spec['name'], flush=True)


def remove(model_id, yes):
    directory = MODEL_DIR / MANIFEST[model_id]['folder']
    if not directory.exists():
        print('模型尚未安装。')
        return
    if directory.is_symlink() or directory.resolve().parent != MODEL_DIR.resolve():
        raise ValueError('拒绝删除：模型目录不在指定的精确位置。')
    marker = directory / '.workbench-model.json'
    if not marker.is_file() or json.loads(marker.read_text()) != dict(app=APP, model_id=model_id):
        raise ValueError('拒绝删除：目录不是本安装器创建的模型目录。')
    for other, spec in MANIFEST.items():
        if model_id in spec.get('requires', []) and (MODEL_DIR / spec['folder']).exists():
            raise ValueError('请先移除依赖它的模型：' + other)
    if not yes:
        answer = input(f'仅删除模型目录 {directory}\n图片和历史会保留。输入 {model_id} 确认：')
        if answer != model_id:
            print('已取消。')
            return
    shutil.rmtree(directory)
    print('已移除模型：' + model_id)


def main():
    parser = argparse.ArgumentParser(description='模型管理：固定版本下载、续传和 SHA256 校验')
    parser.add_argument('action', choices=['list', 'install', 'verify', 'remove'])
    parser.add_argument('models', nargs='*', choices=list(MANIFEST))
    parser.add_argument('--yes', action='store_true', help='调用方已完成删除确认')
    args = parser.parse_args()
    if args.action == 'list':
        for model_id, spec in MANIFEST.items():
            size = sum(entry['size'] for entry in spec['files']) + spec.get('transformer', {}).get('size', 0)
            state = '已安装' if (MODEL_DIR / spec['folder'] / '.ready.json').is_file() else '未安装'
            print(f'{model_id}: {spec["name"]} · {size / 1e9:.2f} GB · {state}')
        return
    if not args.models:
        parser.error('请选择至少一个模型。')
    with model_lock():
        completed = set()
        for model_id in args.models:
            if args.action == 'install':
                install(model_id, completed)
            elif args.action == 'verify':
                verify(model_id)
            else:
                remove(model_id, args.yes)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        print('错误：' + str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\n已停止。重新安装同一模型可继续下载。', file=sys.stderr)
        sys.exit(130)
