"""Render isolated shots with only their own references, then assemble locally.

There is no dialogue/planning call here. One child process shares the loaded
Turbo weights across shots; the final page layout is deterministic.
"""
import json
import re
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

import comic_storyboard
import comic_gaze
import tavern_prompt_rules
import portrait_reference
import tavern_render_options


STYLE = ('彩色写实漫画的一个独立镜头，细致手绘墨线、轻排线、自然彩色上色、真实比例。'
         '只绘制一个连续画面，画面铺满，内部没有分格、插图、画中画、文字、对白或水印。')


def page_boxes(width, height, count):
    if count not in range(2, 6):
        raise ValueError('漫画需2至5格')
    gap = max(4, round(min(width, height) / 144))
    rows = [2] if count == 2 else [1, count - 1] if count < 5 else [2, 3]
    boxes = []
    for row, columns in enumerate(rows):
        top = round(row * height / len(rows)) + gap
        bottom = round((row + 1) * height / len(rows)) - gap
        for column in range(columns):
            left = round(column * width / columns) + gap
            right = round((column + 1) * width / columns) - gap
            boxes.append((left, top, right, bottom))
    return boxes


def scene_context(request):
    context = request.get('scene_context')
    if isinstance(context, str) and context.strip():
        return context.strip()
    # Older saved floors contain the same scene between these binding markers.
    prompt = request.get('prompt', '')
    match = re.search(r'共同场景与连续性事实：(.*?)(?:\n第1格|\Z)', prompt, re.S)
    return match.group(1).strip() if match else prompt


def portrait_setting(request, panel):
    # Old floors lack dedicated background fields. Recover only setting clauses,
    # keeping the other cast's names/actions out of this single-person shot.
    names = request.get('reference_characters', []) + [request.get('protagonist', ''), '主角']
    def environment(text):
        return '，'.join(part.strip() for part in re.split(r'[，,。；;\n]', text)
                        if part.strip() and not any(name and name in part for name in names))
    background = environment(panel.get('background', '')) or environment(scene_context(request))
    lighting = environment(panel.get('lighting', ''))
    return (f'当前剧情环境（虚化背景）：{background}。' if background else '') + (
        f'本镜头光线与面部受光：{lighting}。' if lighting else '')


def prepare_shot_references(jobs):
    for job in jobs:
        if job.get('reference_mode') != 'identity_sample':
            continue
        job['original_references'] = job['references'][:]
        prepared = [portrait_reference.prepare_identity(path) for path in job['references']]
        job['references'] = [path for path, _ in prepared]
        job['identity_crop_applied'] = all(applied for _, applied in prepared)
    return jobs


def shot_jobs(request, reference_paths):
    panels = request['panels']
    names = request.get('reference_characters', [])
    roles = request.get('reference_roles', ['character'] * len(names))
    if len(reference_paths) != len(names) or len(roles) != len(names):
        raise ValueError('分镜头像与人物未逐一对应')
    comic_storyboard.portrait_limits(panels, names, request.get('protagonist', ''))
    comic_storyboard.chronological_limits(panels, request.get('sequence_mode'))
    context = scene_context(request)
    result = []
    boxes = page_boxes(request['width'], request['height'], len(panels))
    for index, (panel, box) in enumerate(zip(panels, boxes)):
        kind, subject = panel['kind'], panel.get('subject')
        portrait = comic_gaze.is_portrait(panel)
        gaze_data = comic_gaze.validate(panel, names, request.get('gaze_mode') == 'per_person')
        panel = dict(panel, **gaze_data)
        if portrait or (kind == 'pov' and 'looks' not in panel):
            selected = [i for i, name in enumerate(names) if name == subject and roles[i] == 'character']
            if len(selected) != 1:
                raise ValueError('人物近景缺少独立人物头像')
        elif kind == 'detail':
            # A hand/prop detail does not need any face reference.
            selected = []
        elif 'looks' in panel:
            visible = {entry['subject'] for entry in panel['looks']}
            selected = [i for i, name in enumerate(names) if name in visible]
        else:
            mentioned = {e['subject'] for e in panel.get('expressions', [])}
            selected = [i for i, name in enumerate(names) if name in panel['description'] or name in mentioned
                        or (roles[i] == 'protagonist' and '主角' in panel['description'])]
            if not selected:
                selected = list(range(len(names)))  # Legacy prose such as "三人围桌".
        selected_names = [names[i] for i in selected]
        selected_roles = [roles[i] for i in selected]
        text = STYLE if request.get('render_style', 'default') == 'default' else (
            tavern_render_options.style_text(request) +
            '这是分镜页中的一个独立镜头，只绘制一个连续画面，画面铺满，内部没有分格、插图、画中画、文字、对白或水印。')
        if comic_gaze.scene_frame(panel):
            text += ('这是交代场景的中远景，保留地面、环境与人物完整坐姿或站姿；人物头部占小部分。'
                     '每人按本镜头的朝向做事或看向剧情目标。共同场景：' + context)
        elif portrait:
            text += (f'重新绘制{subject}在当前剧情里的一个全新脸部特写，仅该人物的一张脸。'
                     '身份样本只提供同一个人的五官比例和辨识特征，整幅构图、背景、光照与表情重新按本镜头绘制。')
            text += portrait_setting(request, panel)
        else:
            text += '本镜头只拍手部动作或道具细节，取景范围内没有人脸，周围背景虚化。'
        text += '本镜头可见内容：' + panel['description']
        if panel.get('beat'):
            text += (f'当前是剧情第{panel["beat"]}个实际发生的时刻：{panel["moment"]}。'
                     '仅表现本时刻的人物距离、位置、接触关系和道具状态，不把前后时刻的动作画在一起。')
        for local_index, name in enumerate(selected_names, 1):
            text += f'参考图{local_index}仅提供{name}稳定的脸型、五官结构与发型，动作和表情按本镜头。'
        if portrait:
            if panel.get('gaze') == 'camera':
                text += f'{subject}的眼睛看向镜头，视线与画外对话者相交；闭眼或遮挡按剧情保留。'
            elif panel.get('gaze') in ('away', 'back'):
                text += f'视线与朝向遵循原文“{panel["gaze_reason"]}”，保持该方向。'
            text += '对话者位于画面外，当前取景只显示上述人物与本镜头实际动作。'
        hidden_faces = {e['subject'] for e in panel.get('looks', []) if e['view'] in ('back', 'occluded')}
        for expression in panel.get('expressions', []):
            if expression['subject'] in selected_names and expression['subject'] not in hidden_faces:
                text += f'{expression["subject"]}此刻{expression["emotion"]}：{expression["features"]}。'
        # Keep the user's literal additions, filtered to the people in this shot.
        local_request = dict(source=request.get('source'), reference_characters=selected_names,
                             reference_roles=selected_roles, render_style=request.get('render_style', 'default'))
        text = tavern_prompt_rules.append(text, local_request)
        if selected:
            text += '\n' + (tavern_prompt_rules.REFERENCE_IDENTITY_RULE if portrait else
                '参考头像只用于识别各自身份；脸型与发型保持各自特征，身体姿势、头部方向、瞳孔落点和可见面部范围完全采用当前动作镜头，保留侧脸、低头、后脑与自然遮挡。')
        if portrait:
            performance = '；'.join(f'{e["emotion"]}，{e["features"]}' for e in panel.get('expressions', [])
                                   if e['subject'] == subject)
            if performance:
                text += f'本次面部表演必须清晰可见：{performance}。重新绘制眉毛、眼睑、面颊肌肉和嘴部开合来表现这个瞬间。'
            text += portrait_setting(request, panel)
            text += f'最终取景：只有{subject}一张脸，单一连续人像画面。'
        elif kind == 'detail':
            text += ('最终取景：摄影机垂直俯拍桌面或当前道具表面，极近距离放大手指与正在接触的物品，'
                     '画面的四周全部由桌面或道具表面铺满，手指从画面边缘伸入，手腕之外的身体都在画面外。')
        else:
            text += '最终取景：一个连续动作场景，完整保留上述构图范围。'
            text += comic_gaze.constraints(panel)
        width, height = box[2] - box[0], box[3] - box[1]
        render_width, render_height = tavern_render_options.reference_size(
            max(256, round(width / 32) * 32), max(256, round(height / 32) * 32))
        result.append(dict(index=index, kind=kind, subject=subject, box=box,
            **gaze_data,
            **({key:panel[key] for key in ('beat', 'moment')} if panel.get('beat') else {}),
            width=render_width, height=render_height,
            prompt=text, references=[str(reference_paths[i]) for i in selected],
            reference_characters=selected_names,
            **(dict(reference_mode='identity_sample', reference_resolution=288) if portrait else {}),
            seed=(request['seed'] + index * 104729) % 1_000_000_000))
    return result


def assemble(images, boxes, width, height):
    if len(images) != len(boxes):
        raise ValueError('漫画分镜未完成，不能拼版')
    page = Image.new('RGB', (width, height), '#f6f2e9')
    draw = ImageDraw.Draw(page)
    for image, box in zip(images, boxes):
        size = (box[2] - box[0], box[3] - box[1])
        page.paste(ImageOps.fit(image.convert('RGB'), size, method=Image.Resampling.LANCZOS), box[:2])
        draw.rectangle(box, outline='#202020', width=2)
    return page


def render(args, request, model_path):
    # Imported only in the isolated reference environment, after the existing
    # Turbo quantization compatibility patch has been installed by its CLI.
    from mflux.callbacks.callback_manager import CallbackManager
    from mflux.models.common.resolution.config_resolution import ConfigResolution
    from mflux.models.qwen21.cli.qwen21_edit_generate import build_parser
    from mflux.models.qwen21.latent_creator.qwen_image21_latent_creator import QwenImage21LatentCreator
    from mflux.models.qwen21.variants.edit.qwen_image_21_edit import QwenImage21Edit
    from mflux.utils.exif_orientation import open_oriented
    import mlx.core as mx

    class ShotModel(QwenImage21Edit):
        def _encode_prompt(self, prompt, images):
            cached = self.__dict__.get('_comic_encodings', {})
            return cached[prompt] if prompt in cached else super()._encode_prompt(prompt, images)

    jobs = prepare_shot_references(shot_jobs(request, args.reference))
    previous_argv = sys.argv
    try:
        sys.argv = ['mlx-comic', '--model', str(model_path), '--base-model', 'qwen-image-2.1-turbo',
            '--prompt', args.prompt, '--steps', '8', '--guidance', '1', '--low-ram', '--output', args.output]
        runtime = build_parser().parse_args()
    finally:
        sys.argv = previous_argv
    config = ConfigResolution.resolve_restricted(runtime.model, 'qwen-image-2.1',
        model_path=runtime.model_path, extra_keys=('qwen-image-2.1-turbo',), base_model=runtime.base_model)
    model = ShotModel(quantize=runtime.quantize, model_path=runtime.model_path, model_config=config)
    saver = CallbackManager.register_callbacks(runtime, model, QwenImage21LatentCreator)
    images, evidence, generated = [], [], None
    folder = Path(args.output).with_suffix('.panels')
    folder.mkdir(exist_ok=False)
    try:
        # Encode each shot once before denoising, then allow low-RAM callbacks to
        # release the encoder. A portrait cache contains only its own references.
        encodings = {}
        for job in jobs:
            references = []
            for path in job['references']:
                with open_oriented(path) as original:
                    image = original.convert('RGBA')
                size = QwenImage21LatentCreator.dimensions(job.get('reference_resolution', 512), image.width / image.height)
                references.append(image.resize(size, Image.Resampling.LANCZOS))
            encoded = model._encode_prompt(job['prompt'], references)
            mx.eval(encoded)
            encodings[job['prompt']] = encoded
        model.__dict__['_comic_encodings'] = encodings
        for index, job in enumerate(jobs):
            # Release text/transformer only after their final use in this process.
            if saver:
                saver.keep_text_encoder = False
                saver.keep_transformer = index < len(jobs) - 1
            print(f'Comic shot {index + 1}/{len(jobs)}', flush=True)
            started = time.monotonic()
            generated = model.generate_image(seed=job['seed'], prompt=job['prompt'],
                num_inference_steps=8, width=job['width'], height=job['height'], guidance=1,
                image_paths=job['references'], output_resolution=job.get('reference_resolution', 512), use_kv_cache=True)
            filename = folder / f'{index + 1:02d}-{job["kind"]}.png'
            generated.save(filename, export_json_metadata=True)
            images.append(generated.image)
            evidence.append(dict(job, filename=str(filename), elapsed=round(time.monotonic() - started, 1)))
        generated.image = assemble(images, [job['box'] for job in jobs], args.width, args.height)
        generated.width, generated.height = args.width, args.height
        generated.prompt, generated.seed = args.prompt, args.seed
        generated.generation_time = sum(entry['elapsed'] for entry in evidence)
        generated.image_paths = args.reference
        generated.generation_parameters.update(comic_render='isolated_panels', panels=len(jobs))
        generated.save(args.output, export_json_metadata=True)
        Path(args.output).with_suffix('.comic.json').write_text(json.dumps(dict(
            render_mode='isolated_panels', model_loads=1, dialogue_api_calls=0,
            sequence_mode=request.get('sequence_mode'),
            width=args.width, height=args.height, panels=evidence), ensure_ascii=False, indent=2))
    finally:
        if saver:
            print(saver.memory_stats(), flush=True)
