import {aspectLabel} from './render-settings.mjs?v=0.1.0';
import {bindComic} from './comic-plan.mjs?v=0.1.0';
import {protagonistBinding} from './protagonist-reference.mjs?v=0.1.0';
export function bindPrompt(plan) {
    if (plan.composition === 'comic') return bindComic(plan);
    const prompt=protagonistBinding(plan)+legacyPrompt(plan);
    return plan.render_settings?prompt.replaceAll('横屏16:9单幅构图',aspectLabel(plan.render_settings)+'单幅构图'):prompt;
}
function legacyPrompt(plan) {
    if (!plan.cast.length) return '按以下剧情正常绘制人物或场景，不新增未出场的人物。横屏16:9单幅构图。'+plan.prompt;
    if (plan.composition === 'interaction') return `参考图1只对应${plan.cast[0].name}，该人物在画面左侧；主角${plan.protagonist}在右侧，两位不同人物。${plan.protagonist_reference?'两人各自使用对应头像，保留独立的面容。':'头像仅用于该人物，不复制到主角脸上。'}画面只以这两人的动作交互为主体。横屏16:9单幅构图。`+plan.prompt;
    if (plan.composition === 'dialogue_pov') return `参考图1只对应${plan.cast[0].name}。固定相机位于对话者的双眼位置，正前方面对${plan.cast[0].name}。仅该人物的正面单人近景特写，视线直接看向镜头。横屏16:9单幅构图。`+plan.prompt;
    return plan.cast.map((c,i)=>`参考图${i+1}只对应${c.name}`+(plan.cast.length===2?(i===0?'，人物在画面左侧':'，人物在画面右侧'):'')).join('；')+'。只画以上人物，各自保留独立的脸型和五官，不交换、不融合、不复制脸。横屏16:9单幅构图。'+plan.prompt;
}
