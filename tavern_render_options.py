"""Literal style controls and bounded render sizes; never calls a model/API."""
STYLES = {
    'default': '彩色写实漫画，细致手绘墨线、轻排线、自然彩色上色、真实比例。',
    'iphone': ('高清真实iPhone摄影，真实照片质感、自然曝光与色彩、清晰而自然的皮肤细节，'
               '采用手机镜头的透视、现场光与真实景深，人物面容保持参考身份。'),
    'japanese': ('日式人像写真摄影，柔和自然光、通透细腻的色调、克制的胶片颗粒，'
                 '真实皮肤和自然的人物比例，清新生活感，人物面容保持参考身份。'),
    'manhwa': ('彩色韩漫画风，精致清晰的线稿、细腻赛璐璐上色、柔和渐变光影，'
               '现代韩漫人物比例与表现力，保留参考人物可辨认的脸型和五官特征。'),
}


def checked_style(value='default'):
    if not isinstance(value, str) or value not in STYLES:
        raise ValueError('画风选项无效，请重新选择')
    return value


def style_text(request):
    return STYLES[checked_style(request.get('render_style', 'default'))]


def clean_legacy_style(text, style):
    """Old saved plans can contain the former mandatory comic-style sentence."""
    if style == 'default':
        return text
    for hint in ('细致手绘墨线、轻排线、自然彩色上色', '手绘墨线与彩色上色',
                 '明确手绘墨线、统一彩色上色和自然比例', '细致手绘墨线', '轻排线', '手绘墨线'):
        text = text.replace(hint, '')
    return text.replace('彩色写实漫画', '分镜画面')


def reference_size(width, height):
    """Keep each reference denoising pass within the existing 1536 budget."""
    scale = min(1, 1536 / max(width, height))
    return tuple(max(256, round(n * scale / 32) * 32) for n in (width, height))
