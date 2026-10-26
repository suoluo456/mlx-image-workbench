"""Official Qwen-Image-2.1-Turbo Euler schedule; no resolution-dependent shift."""
import mlx.core as mx
from mflux.models.common.schedulers.linear_scheduler import LinearScheduler

SIGMAS = (1.0, 0.978453, 0.95418, 0.926626, 0.89508, 0.845148, 0.704534, 0.414568, 0.0)


class Qwen21TurboScheduler(LinearScheduler):
    def _get_sigmas(self):
        if self.config.num_inference_steps != 8:
            raise ValueError('Qwen Turbo 固定使用 8 步')
        return mx.array(SIGMAS, dtype=mx.float32)
