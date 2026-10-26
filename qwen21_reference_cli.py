"""Reference editing uses its own current mflux environment and complete encoder."""
import argparse
import json
import sys
from pathlib import Path
from workbench_paths import MODEL_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prompt', required=True)
    parser.add_argument('--reference', nargs='+', required=True)
    parser.add_argument('--width', type=int, required=True)
    parser.add_argument('--height', type=int, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--output-width', type=int)
    parser.add_argument('--output-height', type=int)
    parser.add_argument('--comic-spec', help='Validated local storyboard JSON; render shots with isolated references')
    args = parser.parse_args()
    model = MODEL_DIR / 'Qwen-Image-2.1-Turbo-Reference-MLX-8bit'
    if not (model/'.ready.json').is_file():
        parser.error('参考图组件尚未下载完成')
    limit = 2560 if args.comic_spec else 1536
    if (not 1 <= len(args.reference) <= 3 or any(not Path(p).is_file() for p in args.reference)
            or any(n < 256 or n > limit or n % 32
                                               for n in (args.width, args.height))):
        parser.error(f'参考图不存在，或尺寸不是 256–{limit} 内的 32 倍数')
    if (args.output_width is not None or args.output_height is not None) and (
            args.comic_spec or any(n is None or n < 256 or n > 2560 or n % 32
                                 for n in (args.output_width, args.output_height))):
        parser.error('输出画布需为 256–2560 内的 32 倍数')
    from mflux.models.qwen21.cli.qwen21_edit_generate import main as generate
    from mflux.models.qwen21.weights.qwen_image21_weight_definition import QwenImage21WeightDefinition
    # The installed 0.20 Turbo export already quantized these four linears.
    # Recreate them at their stored precision instead of letting the newer
    # loader create float linears and discard the saved scales/biases.
    original_predicate = QwenImage21WeightDefinition.quantization_predicate
    legacy_quantized = {'modulation.layers.1', 'norm_out.linear',
                        'time_text_embed.timestep_embedder.linear_1',
                        'time_text_embed.timestep_embedder.linear_2'}
    QwenImage21WeightDefinition.quantization_predicate = staticmethod(
        lambda path, module: original_predicate(path, module)
        or (path in legacy_quantized and hasattr(module, 'to_quantized')))
    if args.comic_spec:
        from comic_render import render
        request = json.loads(args.comic_spec)
        request.update(width=args.width, height=args.height, seed=args.seed)
        render(args, request, model)
        return
    sys.argv = ['mflux-generate-qwen-2.1-edit', '--model', str(model),
                '--base-model', 'qwen-image-2.1-turbo', '--image-paths', *args.reference,
                '--prompt', args.prompt, '--width', str(args.width), '--height', str(args.height),
                '--steps', '8', '--guidance', '1', '--seed', str(args.seed),
                '--output-resolution', '512', '--low-ram', '--metadata', '--output', args.output]
    generate()
    if args.output_width is not None:
        resize_output(args.output, args.output_width, args.output_height)
    meta = Path(args.output).with_suffix('.metadata.json')
    if meta.is_file():
        data = json.loads(meta.read_text())
        data.update(model_id='qwen21_turbo_ref', backend='mlx', reference_mode=True)
        meta.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def resize_output(path, width, height):
    """Explicit canvas enlargement without another denoising or model call."""
    from PIL import Image, ImageOps, PngImagePlugin
    path = Path(path)
    with Image.open(path) as original:
        image = ImageOps.fit(original.convert('RGB'), (width, height), method=Image.Resampling.LANCZOS)
        metadata = PngImagePlugin.PngInfo()
        for key, value in original.info.items():
            if isinstance(value, str):
                metadata.add_text(key, value)
        metadata.add_text('canvas_resize', json.dumps(dict(render_width=original.width,
            render_height=original.height, width=width, height=height, method='lanczos')))
        image.save(path, pnginfo=metadata)
    meta = path.with_suffix('.metadata.json')
    if meta.is_file():
        data = json.loads(meta.read_text())
        data.update(width=width, height=height, canvas_resize='lanczos')
        meta.write_text(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
