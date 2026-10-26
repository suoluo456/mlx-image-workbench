# Third-party notices

The MIT license at the root applies to this workbench's source code. It does not relicense model weights or third-party packages. Runtime dependencies are installed separately into local virtual environments; they retain their respective licenses.

## MFLUX and MLX

The workbench uses [MFLUX](https://github.com/mflux-community/mflux) and [Apple MLX](https://github.com/ml-explore/mlx), both distributed under MIT licenses. The Turbo scheduler and runtime adapters integrate with MFLUX APIs. The installed MFLUX 0.20.0 package includes the following notice, preserved here for adapted integration code:

> MIT License
>
> Copyright (c) 2026 Filip Strand
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

## Downloaded models

| Component | Source | License |
| --- | --- | --- |
| Qwen Turbo transformer | [abenzerps/Qwen-Image-2.1-Turbo-Quantized](https://huggingface.co/abenzerps/Qwen-Image-2.1-Turbo-Quantized) | Qwen Research License |
| Qwen text encoder, processor and VAE | [JoyFusionAI/Qwen-Image-2.1-MLX-8bit](https://huggingface.co/JoyFusionAI/Qwen-Image-2.1-MLX-8bit) | Qwen Research License |
| Optional Qwen reference components | [JoyFusionAI/Qwen-Image-2.1-Edit-MLX-8bit](https://huggingface.co/JoyFusionAI/Qwen-Image-2.1-Edit-MLX-8bit) | See the source model's Qwen Research License |
| Z-Image-Turbo Q8 | [mflux-community/z-image-turbo-mflux-q8](https://huggingface.co/mflux-community/z-image-turbo-mflux-q8) | Apache 2.0 |

These are community MLX conversions, not a claim of affiliation with the model authors. Exact repository revisions, file sizes and SHA256 hashes are recorded in `model-manifest.json`. The Turbo installer changes tensor names and serialization metadata for compatibility with MFLUX, retaining tensor payload bytes. It records the resulting file hash and installation details locally.

Qwen is licensed under the Qwen RESEARCH LICENSE AGREEMENT, Copyright (c) 2026 Hangzhou Tongyi Laboratory Technology Co., Ltd. All Rights Reserved.

The [official Qwen Turbo license](https://huggingface.co/Qwen/Qwen-Image-2.1-Turbo/blob/main/LICENSE) limits the granted use to research/evaluation and requires a separate license for commercial use. Review the complete source-model terms before downloading or using models. The workbench's MIT license does not remove those conditions. Model weights are downloaded by the user and are not included in this repository or its release archives.

## SillyTavern

[SillyTavern](https://github.com/SillyTavern/SillyTavern) is a separate project under AGPL-3.0. This repository ships its own optional browser extension and an API-compatible workflow description, not SillyTavern itself. Install and operate SillyTavern separately under its own terms.

## Installer tools

[uv](https://github.com/astral-sh/uv) and managed CPython are downloaded separately when needed. uv is distributed under MIT or Apache-2.0; CPython uses the Python Software Foundation license. Downloaded binaries and their environments are excluded from source and release archives.
