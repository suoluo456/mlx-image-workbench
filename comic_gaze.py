"""Per-person attention for scene/action frames; portraits keep their own gaze."""
import re

VIEWS = ('profile', 'three_quarter', 'down', 'back', 'occluded')
CAMERA_TARGET = re.compile(r'镜头|摄像|摄影|屏幕|观众|观看者|camera|viewer|lens', re.I)
SPATIAL_RULE = ('只针对本镜头实际出现的人物安排站位，不向无人镜头补入人物，画外注视对象保持在画外。人物位置与视线须形成同一空间关系：先按本镜头描述放置人物及目标，身体姿势保留剧情要求，头部转向、鼻尖与瞳孔朝向该目标实际所在的位置。'
                '区分场景内的真实方位与当前画面的左右；摄影机独立于人物，换机位时重新判断画面左右，人物在场景中的相对距离和位置保持连贯。'
                '对视时分别把两人的目光连向对方；只有一人注视时保留另一人的实际注意对象，做事时看手与物品的接触点。'
                '视线目标必须明确属于对应人物，不交换目标，不因头像为正面就把所有人转向镜头；侧面、背影和遮挡符合当前机位。'
                '面部特写仍按该格既定的主角视点、视线例外和表情要求，不把动作格的旁观机位套用到面部特写。')


def is_portrait(panel):
    return panel.get('kind') == 'face' or (panel.get('kind') == 'pov' and panel.get('framing', 'portrait') == 'portrait')


def scene_frame(panel):
    return panel.get('kind') in ('establishing', 'action') or (panel.get('kind') == 'pov' and not is_portrait(panel))


def validate(panel, names, required=False):
    if not scene_frame(panel):
        return {}
    if 'looks' not in panel:
        if required:
            raise ValueError('缺少动作格逐人视线')
        return {}  # Saved floors retain their original written directions.
    camera, looks = panel.get('camera'), panel['looks']
    if (not isinstance(camera, str) or not camera.strip() or len(camera) > 300
            or 'mlx_image_plan' in camera or 'MLX_PLAN:' in camera
            or not isinstance(looks, list) or len(looks) > len(names)
            or (required and names and not looks)):
        raise ValueError('动作格机位或人物视线无效')
    result, seen = [], set()
    for entry in looks:
        if not isinstance(entry, dict):
            raise ValueError('动作格人物视线无效')
        subject, kind, target = entry.get('subject'), entry.get('kind'), entry.get('target')
        if kind == 'person' and target not in names:
            # Text-only worldbook people have no reference ID; preserve the
            # prose target while keeping reference identities separate.
            kind = 'scene'
        body, head, view = entry.get('body'), entry.get('head'), entry.get('view')
        if (subject not in names or subject in seen or kind not in ('person', 'object', 'scene')
                or not isinstance(target, str) or not target.strip() or len(target) > 150
                or CAMERA_TARGET.search(target) or (kind == 'person' and target == subject)
                or view not in VIEWS or any(not isinstance(v, str) or not v.strip() or len(v) > 250 for v in (body, head))
                or any('mlx_image_plan' in v or 'MLX_PLAN:' in v for v in (target, body, head))):
            raise ValueError('动作格人物朝向或视线目标无效')
        seen.add(subject)
        position = entry.get('position')
        if 'position' in entry and (not isinstance(position, str) or not position.strip() or len(position)>250
                                     or 'mlx_image_plan' in position or 'MLX_PLAN:' in position):
            raise ValueError('动作格人物位置无效')
        result.append(dict(subject=subject, kind=kind, target=target.strip(), body=body.strip(), head=head.strip(), view=view,
                           **({'position':position.strip()} if position else {})))
    if required and any(e.get('subject') not in seen for e in panel.get('expressions', [])):
        raise ValueError('动作格缺少可见人物的视线目标')
    return dict(camera=camera.strip(), looks=result)


def constraints(panel):
    if not scene_frame(panel):
        return ''
    if panel.get('looks') == []:
        return '本格按既有场景取景，不补入人物或人像。摄影机位置：' + panel['camera'] + '。'
    text = ('动作格最终机位与视线：这是从场景侧方观察实际动作的摄像机。'
            '人物注意力落在场景内的对象，不向画外观看者摆拍；头像原有正脸朝向让位于本格身体、头部和瞳孔方向。')
    if panel.get('camera'):
        text += '摄影机位置：' + panel['camera'] + '。'
    view_words = {
        'profile': '清楚的侧脸轮廓，只见一侧眼睛，鼻尖沿侧向指向视线目标',
        'three_quarter': '斜侧脸，鼻尖与瞳孔一起转向该目标',
        'down': '下巴下收、头部俯下，上眼睑自然低垂，瞳孔落在下方的这个具体目标上',
        'back': '后脑与背部朝向摄像机，脸转向剧情目标，正面双眼不在镜头中',
        'occluded': '面部按当前遮挡保留，用身体姿态与头部朝向表达注意力',
    }
    for entry in panel.get('looks', []):
        text += (f'{entry["subject"]}：' + (f'位于{entry["position"]}；' if entry.get('position') else '') +
                 f'身体{entry["body"]}；头部{entry["head"]}；'
                 f'视线只落在{entry["target"]}，{view_words[entry["view"]]}。')
        target = next((person for person in panel.get('looks', []) if person['subject']==entry['target']), None)
        if entry['kind']=='person' and target and target.get('position'):
            text += (f'{entry["subject"]}的注视对象{entry["target"]}在{target["position"]}，'
                     '头部转向、鼻尖与瞳孔落点均沿两人站位的连线指向对方，不能朝画面的相反方向。')
    if not panel.get('looks'):
        # Repeat only the old floor's actual directions, never invent a target.
        clauses = re.findall(r'[^。；]*(?:看|望|视线|目光|朝向|面向|低头|背对|侧背)[^。；]*', panel['description'])
        if clauses:
            text += '本镜头已有的具体朝向：' + '；'.join(clauses) + '。'
        text += ('交互时双方身体和鼻尖朝向对方，双眼关注彼此；操作时头部俯下、瞳孔落向手中或桌上的操作点。'
                 '侧脸、后脑、背部和自然遮挡保留，不转正展示头像。')
    text += '本动作格的朝向与视线优先于头像原姿态；面部特写的看镜头规则不适用于本格。'
    return text
