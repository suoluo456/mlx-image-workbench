"""Reuse the installed CLI's model and callbacks for one model's image batch.

Runs in an isolated child process. Nothing remains resident after the batch exits.
"""
import importlib
import json
import sys
import time
from collections import OrderedDict
from pathlib import Path

EVENT_PREFIX = 'MLX_BATCH_EVENT '


class BatchComplete(BaseException):
    """Exit the CLI after our loop has saved all images."""


def emit(event, **values):
    print(EVENT_PREFIX + json.dumps(dict(event=event, **values)), flush=True)


def main():
    spec = json.loads(Path(sys.argv[1]).read_text())
    model_id = spec['model']
    modules = {
        'qwen21_turbo': ('qwen21_turbo_cli', 'QwenImage21'),
        'zimage': ('mflux.models.z_image.cli.z_image_generate', 'ZImage'),
    }
    module_name, class_name = modules[model_id]
    cli = importlib.import_module(module_name)
    model_class = getattr(cli, class_name)
    original_generate = model_class.generate_image
    from mflux.callbacks.instances.memory_saver import MemorySaver
    # A later random prompt may need the encoder again. Retain it only in this
    # batch process; still use low-RAM VAE tiling and Metal cache cleanup.
    varied_prompts = len({(i["effective_prompt"], i.get("negative_prompt", ""), i["guidance"])
                         for i in spec["items"]}) > 1
    if varied_prompts:
        MemorySaver._delete_text_encoders = lambda self: None
    original_init = MemorySaver.__init__

    def init_memory(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.keep_transformer = True
    MemorySaver.__init__ = init_memory

    if model_id == 'zimage':
        original_encode = model_class._encode_prompts
        def encode(self, **kwargs):
            cache = getattr(self, '_batch_prompt_cache', None)
            if cache is None:
                cache = self._batch_prompt_cache = OrderedDict()
            key = (kwargs['prompt'], kwargs.get('negative_prompt'), kwargs['guidance'])
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
            value = original_encode(self, **kwargs)
            cache[key] = value
            if len(cache) > 8:
                cache.popitem(last=False)
            return value
        model_class._encode_prompts = encode

    def generate_batch(self, **initial):
        for index, item in enumerate(spec['items']):
            started = time.monotonic()
            emit('start', index=index)
            kwargs = dict(initial, seed=item['seed'], prompt=item['effective_prompt'],
                          num_inference_steps=item['steps'])
            if 'negative_prompt' in initial:
                kwargs['negative_prompt'] = item.get('negative_prompt', '')
            if 'guidance' in initial:
                kwargs['guidance'] = item['guidance']
            try:
                image = original_generate(self, **kwargs)
                image.save(path=item['output'], export_json_metadata=True)
                import mlx.core as mx
                emit('done', index=index, elapsed=round(time.monotonic()-started, 1),
                     peak_gb=mx.get_peak_memory()/10**9)
            except Exception as exc:
                # Model errors may leave callbacks or tensors in an invalid state.
                emit('error', index=index, error=str(exc))
                raise
            cache = getattr(self, 'prompt_cache', None)
            if cache and len(cache) > 8:
                for key in list(cache)[:-8]:
                    del cache[key]
        raise BatchComplete()

    model_class.generate_image = generate_batch
    command = spec['command']
    # The existing CLI remains authoritative for model loading and settings.
    if command[1].endswith('qwen21_turbo_cli.py'):
        sys.argv = command[1:]
        launch = cli.main
    else:
        sys.argv = command
        launch = cli.main
    try:
        launch()
    except BatchComplete:
        pass


if __name__ == '__main__':
    main()
