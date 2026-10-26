"""Local validation and literal constraints for a single comic-page render."""
import comic_gaze
import tavern_render_options


def _expressions(panel, names, required):
    if 'expressions' not in panel:
        if required:
            raise ValueError('缺少本格人物表情')
        return None
    value = panel['expressions']
    if not isinstance(value, list) or len(value) > len(names):
        raise ValueError('人物表情数据无效')
    result, seen = [], set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError('人物表情数据无效')
        name, emotion, features = entry.get('subject'), entry.get('emotion'), entry.get('features')
        if (name not in names or name in seen or not isinstance(emotion, str) or not emotion.strip()
                or len(emotion) > 100 or not isinstance(features, str) or not features.strip()
                or len(features) > 400 or 'mlx_image_plan' in emotion + features or 'MLX_PLAN:' in emotion + features):
            raise ValueError('人物表情与身份对应无效')
        seen.add(name)
        result.append(dict(subject=name, emotion=emotion.strip(), features=features.strip()))
    return result


def portrait_limits(panels, names, protagonist):
    seen = set()
    for panel in panels:
        if panel.get('kind') not in ('face', 'pov'):
            continue
        subject, framing = panel.get('subject'), panel.get('framing', 'portrait')
        if subject == protagonist or subject == 'protagonist':
            raise ValueError('主角不安排面部特写')
        if (subject not in names or framing not in ('portrait', 'action')
                or (panel['kind'] == 'face' and framing != 'portrait')):
            raise ValueError('特写人物或取景无效')
        if panel['kind'] == 'pov' and framing == 'action':
            continue
        if subject in seen:
            raise ValueError('同一人物每页最多一张面部特写')
        seen.add(subject)


def chronological_limits(panels, mode):
    if mode is None:
        return
    if mode != 'chronological':
        raise ValueError('漫画时间顺序无效')
    previous = 0
    for panel in panels:
        beat, moment = panel.get('beat'), panel.get('moment')
        if (isinstance(beat, bool) or not isinstance(beat, int) or not 1 <= beat <= 5
                or beat < previous or beat > previous + 1 or not isinstance(moment, str)
                or not moment.strip() or len(moment) > 150 or 'mlx_image_plan' in moment or 'MLX_PLAN:' in moment):
            raise ValueError('漫画事件顺序缺失或倒退')
        previous = beat


def validate(values, names, protagonist):
    scene = values.get('scene_type')
    present = values.get('protagonist_present')
    panels = values.get('panels')
    expression_mode = values.get('expression_mode')
    sequence_mode = values.get('sequence_mode')
    gaze_mode = values.get('gaze_mode')
    if gaze_mode not in (None, 'per_person'):
        raise ValueError('动作格视线方式无效')
    if expression_mode not in (None, 'per_panel'):
        raise ValueError('表情方式无效')
    if (scene not in ('default', 'interaction', 'dialogue_pov') or not isinstance(present, bool)
            or (present and not protagonist.strip())
            or (scene != 'default' and not present)):
        raise ValueError('漫画人物在场数据无效')
    if not isinstance(panels, list) or not 2 <= len(panels) <= 5:
        raise ValueError('漫画分镜需2至5格')
    result, descriptions, counts = [], set(), {}
    for i, panel in enumerate(panels):
        if not isinstance(panel, dict):
            raise ValueError('漫画镜头无效')
        kind, text = panel.get('kind'), panel.get('description')
        if (kind not in ('establishing', 'action', 'face', 'detail', 'pov') or not isinstance(text, str)
                or not text.strip() or len(text) > 1000 or 'mlx_image_plan' in text or 'MLX_PLAN:' in text):
            raise ValueError('漫画镜头无效')
        fingerprint = ''.join(text.split())
        if fingerprint in descriptions or ((i == 0) != (kind == 'establishing')):
            raise ValueError('漫画镜头重复或缺少开场站位')
        descriptions.add(fingerprint)
        counts[kind] = counts.get(kind, 0) + 1
        item = dict(kind=kind, description=text.strip())
        if sequence_mode is not None:
            item.update(beat=panel.get('beat'), moment=panel.get('moment'))
        expressions = _expressions(panel, names + ([protagonist] if present else []), expression_mode == 'per_panel')
        if expressions is not None:
            item['expressions'] = expressions
        item.update(comic_gaze.validate(panel, names + ([protagonist] if present else []), gaze_mode == 'per_person'))
        if kind in ('face', 'pov'):
            subject, gaze, reason = panel.get('subject'), panel.get('gaze'), panel.get('gaze_reason', '')
            if (subject not in names or gaze not in ('camera', 'scene', 'away', 'back')
                    or not isinstance(reason, str) or len(reason) > 300
                    or (gaze in ('away', 'back') and not reason.strip())
                    or (scene != 'default' and gaze == 'scene' and panel.get('framing') != 'action')
                    or (kind == 'pov' and not present)):
                raise ValueError('漫画特写人物或视线无效')
            framing = panel.get('framing', 'portrait')
            if framing not in ('portrait', 'action') or (kind == 'face' and framing != 'portrait'):
                raise ValueError('特写取景无效')
            item.update(subject=subject, gaze=gaze, gaze_reason=reason)
            for key in ('background', 'lighting'):
                if key in panel:
                    value = panel[key]
                    if (not isinstance(value, str) or not value.strip() or len(value) > 300
                            or 'mlx_image_plan' in value or 'MLX_PLAN:' in value):
                        raise ValueError('特写环境或光线无效')
                    item[key] = value.strip()
            if kind == 'pov':
                item['framing'] = framing
                if framing == 'action' and gaze == 'camera':
                    item['gaze'] = 'scene'
            if expression_mode == 'per_panel' and gaze != 'back' and not any(e['subject'] == subject for e in expressions):
                raise ValueError('面部特写缺少对应表情')
        result.append(item)
    if ((names and not counts.get('face')) or counts.get('detail', 0) > 1 or counts.get('pov', 0) > 1):
        raise ValueError('漫画镜头安排无效')
    portrait_limits(result, names, protagonist)
    chronological_limits(result, sequence_mode)
    result = dict(scene_type=scene, protagonist_present=present, panels=result)
    if expression_mode:
        result['expression_mode'] = expression_mode
    if sequence_mode:
        result['sequence_mode'] = sequence_mode
    if gaze_mode:
        result['gaze_mode'] = gaze_mode
    return result


def constraints(request):
    panels = request['panels']
    portrait_limits(panels, request.get('reference_characters', []), request.get('protagonist', ''))
    chronological_limits(panels, request.get('sequence_mode'))
    text = (f'漫画最终要求：整页共{len(panels)}格，按上述分镜组织大小与排版。'
            + ('彩色写实漫画，明确手绘墨线、统一彩色上色和自然比例。' if request.get('render_style', 'default') == 'default'
               else tavern_render_options.style_text(request)) + '每格提供不同信息，'
            '人物身份、发型、服装、场景结构及道具种类保持一致，身体左右手不混淆。'
            '各格按正文已有的事件先后推进，距离、站位、动作、表情和道具状态随实际事件自然变化。'
            '一格只表现一个时刻，不补造未发生的动作，不倒退到已完成动作之前。'
            '各格摄影机独立取景，人物在画面中的左右可随机位变化，场景内真实位置保持连续。'
            '每位人物仅取自己参考图的稳定脸型与五官结构，主角保持独立身份，当前表情按本格剧情变化。'
            '主角只在多人中远景或动作镜头里入镜，不安排主角的面部、头肩或单独肖像特写。'
            '整页每人最多一张面部或近距离人像特写，face与人像pov合并计数，禁止额外重复人像。'
            '分格有清晰边界；不添加对白、文字、序号或水印。近景背景虚化。')
    for i, panel in enumerate(panels, 1):
        if request.get('reference_characters') or panel.get('looks'):
            text += comic_gaze.constraints(panel)
        if panel.get('beat'):
            text += f'第{i}格为剧情第{panel["beat"]}个时刻：{panel["moment"]}。'
        if panel.get('kind') == 'pov' and panel.get('framing') == 'action':
            text += f'第{i}格是{panel["subject"]}的动作中景，保留上半身、手臂和关键道具，动作占主体、头部占小部分，保持中景范围，不能裁成面部或头肩人像。'
            if panel.get('gaze') in ('away', 'back'):
                text += f'本格视线依据“{panel["gaze_reason"]}”，保留该方向与朝向。'
        elif panel.get('kind') in ('face', 'pov') and panel.get('gaze') == 'camera':
            text += f'仅第{i}格{panel["subject"]}的面部特写：摄影机在主角双眼位置，前景由她自己的脸部组成，双眼看向镜头，与主角目光相交；剧情明确闭眼或眼部被遮挡时保留该状态。'
        elif panel.get('kind') in ('face', 'pov') and panel.get('gaze') in ('away', 'back'):
            text += f'第{i}格视线例外依据“{panel["gaze_reason"]}”，保留该方向与朝向。'
    text += ('多人中远景采用独立旁观摄像机。逐人按该格描述的站位、身体朝向、头部朝向和实际目标安排视线，'
             '交谈时看对方，做事时看手边动作与物品，其他人物看各自剧情目标；侧脸、背影和遮挡自然保留。'
             '头像只确定身份，不要求为了露出脸而面向镜头。看向镜头的要求仅限上面指定的脸部特写格。')
    return text
