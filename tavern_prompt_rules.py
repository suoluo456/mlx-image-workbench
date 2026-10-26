"""Literal local-only additions to Tavern image prompts; no model/API calls."""
import comic_storyboard
import tavern_render_options
import comic_gaze
import json
from workbench_paths import DATA_DIR

REFERENCE_IDENTITY_RULE = ('参考身份与动态表情分开：保留头像稳定的脸型、眼形、鼻形、唇形和可辨识特征；'
    '眉毛位置、眼睑开合、面部肌肉、嘴角高低、嘴唇开合按照当前剧情文字重绘，'
    '表情优先执行本次描述，头像原有表情不是固定要求。各人各格的情绪与强弱分别依据剧情。'
    '有明确情绪时重绘该表情，未指定时使用符合场景的自然中性状态；泪水与伤痕须有剧情依据。'
    '侧脸、闭眼、背影与遮挡自然保留。')

APPEARANCE_RULE = ('逐人外观一致性最终要求：以共同场景和本镜头描述中各角色已经确定的发型、配饰为准。'
    '耳环、项链、眼镜、丝巾、眼罩以及已设定的发饰、戒指、手镯、腕表，在本页各格及后续图片中保持各自的有无、款式、颜色、材质、数量、佩戴位置和左右侧；'
    '左右以人物自身为准，不因机位变化交换佩戴侧，不把甲的配饰复制或移给乙，不凭空增添配饰。'
    '同一人的发色、长度、直卷、刘海、分缝、扎发或披发方式、发髻和辫子位置明确保持一致，风和动作只改变自然发丝走势，不另换发型。'
    '只有本次剧情明确描写摘下、戴上、换配饰或改变发束时才按发生的时刻变化，后续镜头延续该状态；该明确变化优先于参考头像和旧的静态人物描述。'
    '配饰在画外、被遮挡或位于背面时保持实际遮挡，不把不可见当成未佩戴，不扩大取景或转正人脸来展示配饰；眼罩遮住的眼睛保持遮住，眼镜按原款佩戴。'
    '只约束本镜头实际出现的人物，不向无人场景补入人物或配饰，表情与动作仍依照本格剧情。')

def character_prompts():
    """User-owned optional rules, never bundled in a release."""
    path = DATA_DIR / 'character-prompts.json'
    try:
        if path.stat().st_size > 256_000:
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            return {}
        return {name: prompt for name, prompt in value.items()
                if isinstance(name, str) and 0 < len(name) <= 100
                and isinstance(prompt, str) and 0 < len(prompt) <= 4000}
    except (OSError, ValueError):
        return {}


def append(prompt, request):
    if request.get('source') != 'sillytavern':
        return prompt
    prompt = tavern_render_options.clean_legacy_style(prompt, request.get('render_style', 'default'))
    additions = [comic_gaze.SPATIAL_RULE]
    characters = character_prompts()
    seen = set()
    # Use exact text lookup on the actual reference-image cast, not names merely
    # mentioned in the scene. Order stays aligned with reference images 1 and 2.
    all_names = request.get('reference_characters', [])
    roles = request.get('reference_roles', ['character'] * len(all_names))
    names = [name for name, role in zip(all_names, roles) if role == 'character']
    for name in names:
        name = name.strip()
        if name in characters and name not in seen:
            additions.append(characters[name])
            seen.add(name)
    composition = request.get('composition', 'default')
    protagonist = request.get('protagonist', '')
    if composition == 'comic':
        additions.append(comic_storyboard.constraints(request))
    elif composition == 'interaction' and len(names) == 1 and protagonist:
        additions.append(f'构图要求：以{names[0]}与主角{protagonist}两人为主体，参考人物在左、主角在右，'
                         '近距离双人动作特写。按照剧情实际发生的交互安排动作，保留两人的表情、关键手部、'
                         '接触关系及必要工具或棋盘，不能裁掉理解动作所需的部位。人物占画面主体，'
                         '背景浅景深虚化。不得新增亲密动作，不增加其他人物，不把参考人物的脸复制给主角。')
    elif composition == 'dialogue_pov' and len(names) == 1 and protagonist:
        additions.append(f'构图要求：固定相机位于对话者双眼的位置，正前方直接面对{names[0]}，视线与镜头相交。'
                         f'画面只有{names[0]}一位人物，是近距离正面单人肖像，面容完整清晰，面部及上半身占据主要画面，'
                         '动作和表情准确对应对话情绪。前景由这位人物自己的面部和上半身组成，背景浅景深虚化。'
                         '单人特写取景优先于展示完整服饰和全身；参考头像只提供面容，场景和姿态采用当前画面描述。')
    if request.get('protagonist_reference_index'):
        additions.append(f'主角身份最终要求：参考图{request["protagonist_reference_index"]}只对应主角{protagonist}，'
                         '保留该头像稳定的脸型、五官结构、发型和可辨识特征。主角入镜的每一格都保持同一主角身份，'
                         '各人分别使用自己的头像，不能把其他人物的面容复制给主角，不能把主角面容复制给其他人物。'
                         '衣着、动作和环境按本次剧情，稳定五官结构与发型以各自头像为准，表情、眉眼肌肉和嘴部状态按每格剧情变化。'
                         '头像只确定身份，不固定头部朝向或视线；在中远景中主角可以侧身或背对摄像机，'
                         '视线看向本格剧情中的人或物，保持自然动作，不为展示头像而转向镜头。')
    if composition == 'comic':
        expressions = []
        for i, panel in enumerate(request.get('panels', []), 1):
            for entry in panel.get('expressions', []):
                expressions.append(f'仅第{i}格{entry["subject"]}此刻{entry["emotion"]}：{entry["features"]}。')
        if expressions:
            additions.append('逐格表情最终执行：' + ''.join(expressions) +
                             '保留每人的稳定身份特征，优先重绘上述眉眼、面部肌肉和嘴部动态，所有人物无需共用同一表情。'
                             '背影和被遮挡的面部保持原朝向与遮挡。')
        additions.append('漫画特写最终限制：主角只在多人中远景或动作镜头中入镜，主角头像仅保持身份，'
                         '不生成主角的面部、头肩或单独肖像特写；每个人整页最多一张面部特写，'
                         '近距离人像pov同样计入，不能通过换表情、换角度或额外格子重复同一人的脸部特写。')
    if request.get('render_style', 'default') != 'default':
        additions.append('本次最终画风：' + tavern_render_options.style_text(request) +
                         '全部镜头统一使用此画风；分镜只控制镜头组织，不改变所选画风。')
    additions.append(APPEARANCE_RULE)
    return '\n\n'.join([prompt, *additions])
