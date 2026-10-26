#!/usr/bin/env python3
"""Generate with the verified Turbo Q8 checkpoint using the existing native MLX pipeline."""
import json
import sys
from pathlib import Path

from mflux.callbacks.callback_manager import CallbackManager
from mflux.models.common.resolution.config_resolution import ConfigResolution
from mflux.models.qwen21.cli.qwen21_generate import DEFAULT_MODEL, build_parser
from mflux.models.qwen21.latent_creator.qwen21_latent_creator import Qwen21LatentCreator
from mflux.models.qwen21.variants.txt2img.qwen_image_21 import QwenImage21 as BaseQwenImage21
from mflux.utils.generated_image import GeneratedImage
from mflux.utils.prompt_util import PromptUtil

from qwen21_turbo_scheduler import SIGMAS
from model_registry import TURBO_MAX_DIMENSION
from workbench_paths import MODEL_DIR

MODEL_PATH = MODEL_DIR / 'Qwen-Image-2.1-Turbo-MLX-8bit'
SCHEDULER = 'qwen21_turbo_scheduler.Qwen21TurboScheduler'


class TurboGeneratedImage(GeneratedImage):
    def _get_metadata(self):
        return super()._get_metadata() | dict(model='Qwen/Qwen-Image-2.1-Turbo',
            model_id='qwen21_turbo', backend='mlx', sampler='euler',
            scheduler=SCHEDULER, sigmas=list(SIGMAS), uncensored=False)


class QwenImage21(BaseQwenImage21):
    def __init__(self, *args, **kwargs):
        path = Path(kwargs.get('model_path') or MODEL_PATH).resolve()
        if path != MODEL_PATH.resolve():
            raise ValueError('Turbo 必须使用已校验的 MLX Turbo 模型目录')
        manifest = json.loads((path / '.ready.json').read_text())
        if manifest.get('model') != 'Qwen/Qwen-Image-2.1-Turbo' or manifest.get('backend') != 'mlx':
            raise ValueError('Turbo 模型安装记录不匹配')
        # The installer verifies the pinned checkpoint hash. Validate the local
        # index and tensor header here without requiring the original Qwen model.
        from model_integrity import validate_transformer_index
        validate_transformer_index(path)
        kwargs['model_path'] = str(path)
        super().__init__(*args, **kwargs)

    def generate_image(self, **kwargs):
        if kwargs.get('num_inference_steps', 8) != 8:
            raise ValueError('Qwen Turbo 固定使用 8 步')
        if kwargs.get('guidance', 1.0) != 1.0 or kwargs.get('negative_prompt'):
            raise ValueError('Qwen Turbo 使用 CFG 1，不发送负向提示词')
        kwargs.update(num_inference_steps=8, guidance=1.0, negative_prompt=None, scheduler=SCHEDULER)
        image = super().generate_image(**kwargs)
        image.__class__ = TurboGeneratedImage
        image.model_path = str(MODEL_PATH)
        return image


def main():
    parser = build_parser()
    parser.set_defaults(steps=8, width=1024, height=1024)
    if any(value.startswith('--') and 'lora' in value.lower() for value in sys.argv[1:]):
        parser.error('本公开版不支持 LoRA 参数')
    args = parser.parse_args()
    if args.steps != 8:
        parser.error('Qwen Turbo 固定使用 8 步')
    if args.image_path or args.guidance not in (None, 1.0) or PromptUtil.read_negative_prompt(args):
        parser.error('此入口使用 Turbo 文字生图、CFG 1，不支持负向提示词')
    if not (256 <= args.width <= TURBO_MAX_DIMENSION and 256 <= args.height <= TURBO_MAX_DIMENSION
            and args.width % 16 == 0 and args.height % 16 == 0):
        parser.error(f'宽高需为 256–{TURBO_MAX_DIMENSION}，且是 16 的倍数')
    model_config = ConfigResolution.resolve_restricted(
        args.model, DEFAULT_MODEL, model_path=args.model_path, base_model=args.base_model)
    qwen = QwenImage21(quantize=args.quantize, model_path=args.model_path, model_config=model_config)
    memory_saver = CallbackManager.register_callbacks(args=args, model=qwen,
                                                       latent_creator=Qwen21LatentCreator)
    try:
        for seed in args.seed:
            image = qwen.generate_image(seed=seed, prompt=PromptUtil.read_prompt(args),
                                       width=args.width, height=args.height, num_inference_steps=8)
            image.save(path=args.output.format(seed=seed), export_json_metadata=args.metadata)
    finally:
        if memory_saver:
            print(memory_saver.memory_stats())


if __name__ == '__main__':
    main()
