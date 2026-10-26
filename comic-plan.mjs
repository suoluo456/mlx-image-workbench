import {aspectLabel,styleLabel} from './render-settings.mjs?v=0.1.0';
// This data is produced inside the normal reply. Validation and prompt binding
// are local string operations; neither function requests a planning completion.
import {protagonistBinding} from './protagonist-reference.mjs?v=0.1.0';
import {gazeInstruction, looksFor, bindLooks} from './gaze-plan.mjs?v=0.1.0';
export const SCENE_TYPES = ['default', 'interaction', 'dialogue_pov'];
const KINDS = ['establishing', 'action', 'face', 'detail', 'pov'];
export const EXPRESSION_GUIDE = Object.freeze({
    悲伤:'眉内侧微抬、眼睑低垂、嘴角下压；只有剧情确有哭泣时才加泪水',
    紧张:'眉间轻收、眼睑与下颌略绷紧、嘴唇抿住或呼吸性微张，强度按剧情',
    委屈:'眉内侧抬起、眼神受伤或欲言又止、嘴角下垂或轻咬下唇，泪水须有依据',
    快乐:'眉眼舒展、眼周自然收拢、嘴角明显上扬，剧情大笑时才张口大笑',
    微笑:'嘴角小幅上扬、眼神柔和，可闭唇浅笑，不固定露齿大笑',
    放松:'眉间、眼睑和下颌自然舒展、嘴唇轻合，可是平静中性神情',
    害羞:'眉眼柔和、嘴角含蓄收敛、唇轻抿，剧情有脸红时才微红，视线独立按本格方向',
    愤怒:'眉头向内压低、眼睑收紧、下颌绷紧、嘴唇紧抿或按斥责剧情张口',
    瞪眼:'上眼睑抬起、眼睛明显睁大、眉毛与嘴部依惊讶、警告或生气等实际语境变化',
    撒娇:'眼神柔软且带请求感、眉间放松、嘴唇轻嘟或含蓄笑意，按说话方式选择，不新增贴靠动作',
});

export const APPEARANCE_CHECK = `配饰与发型逐人逐格检核：输出分镜JSON前，先按当前正文、世界书及角色原有设定核对每个实际出场人物的外观基准，把姓名、发型与已知配饰写入现有prompt的共同场景描述中，不另加正文、不新增协议字段。每格description再次写清该角色在当前取景中可见的发型和配饰，前后采用同一组明确描述，不能只在首格写一次后让后续镜头自行发挥。
逐项检核耳环、项链、眼镜、丝巾、眼罩，以及实际设定中的发饰、戒指、手镯和腕表：有无、款式、颜色、材质、数量、佩戴部位和左右侧均保持一致。某物只属于指定人物，不能在多人间互换或复制；左右以人物自身为准，换摄像机不把左耳配饰换到右耳。眼罩遮哪只眼、眼镜框型、项链吊坠、丝巾系法等既有细节要一致，未说明的细节保持原设定，不凭空增加配饰。
发型明确保持一致：同一人的发色、长度、直卷、刘海、分缝方向、扎发或披发方式、发髻或辫子位置及发饰固定。风吹和动作可改变少量发丝位置，不能因此把长发变短发、披发变扎发、卷发变直发，不能为换机位或表情另换发型。
一致性覆盖本页所有镜头和后续生成图片；沿用角色当前已经确定的状态。只有正文明确发生摘下、戴上、拿掉眼罩、换配饰、解开发束等动作时才改变，按该动作实际发生的时刻更新，并让之后的镜头延续改变后的状态，不能下一格又无故恢复。当前剧情的明确变化优先于头像和旧的静态服饰描述，不能为了满足一致性编造这些动作。
检核可见范围：配饰在画外、背面或被头发/手部遮住时可不展示，不能把看不见写成没有佩戴，也不能为了展示配饰把人物转成正脸或扩大特写取景。眼罩和眼镜的真实遮挡保留，不为画眼睛而摘掉；表情、机位与动作仍按剧情变化。输出前逐格比对人物与其外观基准，如配饰遗漏、串人或发型变化无剧情依据，先修正该格描述再输出；只在现有隐藏prompt和description中完成，不污染正常对话。`;

export function comicInstruction(settings = {}) {
    return `composition固定为comic，scene_type按本次实际剧情选择：interaction为剧情人物与主角正在共同动作（共同工作、下棋、拥抱、打斗等），即使同时说话也优先；dialogue_pov为只有对话；default为主角不在场或没有上述互动。单方面说话手势不算共同动作。protagonist_present明确主角本次是否实际在场，不能把群聊发言者当主角。
cast只列本聊天可用头像名单中实际在场的重点人物，最多两位，不按发言角色选人；只在回忆、计划、电话提及或状态栏出现不算在场，不要求已有MVU记录。世界书或正文中没有头像的人物仍可正常入镜：在prompt与description中写出姓名、外貌、服装及动作，但不放进cast，也不编造头像。没有头像参考时cast必须为[]，draw仍为true。主角不放入cast。主角有用户头像时本地会另传独立参考；没有头像时按世界书和正文文字描绘，不能套用其他人物的头像；不要另编与现有头像冲突的脸型、五官或发型，衣着、动作和环境采用剧情。
panels按剧情自动安排2至5格，不固定四格，不为凑格数重复近景。采用漫画的事件推进逻辑，先从本次可见正文提取实际发生的动作节点，再选择有信息的时刻，而不是把同一瞬间换几个角度。没有动作推进的对话场景可选择说话、倾听、反应等已有节点，不强行编造动作。每格只写单一连续镜头，最终由本地逐格绘制并拼版，不在description里再分小格。
sequence_mode固定为chronological。每格带beat和moment：beat是本次实际事件节点序号，从1开始，随事件推进逐次加1；同一事件的有意义细节或表情反应可以沿用beat，不倒叙、不跳回旧状态。moment简写该时刻发生了什么，不写计划、愿望或未来可能发生的事。
示例只说明漫画叙事方法，不能添进实际剧情：只有当正文确实依次发生“远处挥手、走近、拥抱”时，才可安排第1格中远景交代两人的远距离挥手（beat1），第2格action画走近、距离缩短（beat2），第3格action画两人拥抱的完整动作关系（beat3），第4格face画对方拥抱时已有的情绪反应（仍为beat3）。动作格可有多格，不用主角面部特写充数。正文只有挥手时，只画挥手和已有反应，不能自行补上走近或拥抱。
expression_mode固定为per_panel。每格格式为{"kind":"establishing|action|face|detail|pov","beat":1,"moment":"本时刻实际发生的事","description":"此格可见内容","subject":"头像人物ID，仅face/pov需要","framing":"仅pov需要：portrait为近距离人像，action为动作中景","gaze":"camera|scene|away|back","gaze_reason":"离开主角视线或背对时的剧情原句","expressions":[{"subject":"头像人物ID或protagonist","emotion":"剧情中此刻的情绪及强弱","features":"可见眉眼、面部肌肉、嘴部的具体状态"}]}。
面部特写硬限制：漫画中不安排主角的面部、头肩或单独肖像特写，主角只能在多人中远景、动作中景或动作细节中正常入镜，仍使用主角头像保持身份。每个人整页最多一张面部或近距离人像特写，改变表情、角度或把镜头改名为pov都不能再画同一人的第二张面部特写；禁止把脸部特写写进detail或establishing绕过限制。
表情与身份分开：头像只保留稳定的脸型、眼形、鼻形、唇形与辨识特征，头像原有的笑容、皱眉、嘴巴开合和眼睑状态都不固定。每格expressions按本次剧情逐人写，不把角色性格当成永远不变的表情，也不让所有人物共享同一种情绪。表情优先于头像原有表情，剧情要求可以变化眉毛位置、眼睑松紧、面部肌肉、嘴角、嘴唇开合以及有依据的泪水或面色。
常用表情参照（只是面部变化词汇，不是固定剧情或穷尽名单，可按剧情混合并区分强弱）：${Object.entries(EXPRESSION_GUIDE).map(([name, text])=>name+'＝'+text).join('；')}。
每个face/pov格必须为其可见面部写一条expressions，用subject对应人物，再写emotion和至少眉眼、嘴部两个方面的可见变化，features用20至80字。示例仅说明写法：克制的愤怒＝眉头向内压低、眼睑收紧、嘴唇紧抿且嘴角压低；悲伤＝眉内侧抬起、眼神低落、嘴角下垂。不能只写“生气/难过/微笑”而没有面部变化，不把这些示例添加为剧情。情绪、强度和变化先后必须有当前对话或动作依据，平静时使用自然放松的中性神情，不能为了换表情编造愤怒、哭泣或伤口。
每个face和portrait型pov还要写background与lighting两个字符串：background写当前剧情地点在这个机位后方可见的虚化环境与颜色，lighting写当前光源、冷暖和脸部受光方向，不写其他人物，也不沿用参考头像的背景或照明。description明确当前头部姿态、说话时嘴部状态及衣领等可见衣着。头像是身份样本，整幅特写应当重新构图并表演当前情绪；眉眼与嘴部必须执行expressions，不能把原头像换成漫画笔触就当作新镜头。环境和光源必须来自当前剧情；正文未给具体光源时使用该场景自然光，不编造天气、时段或新地点。
establishing格逐人描述可见面部的当前表情，主角用subject:protagonist；同一人在相邻格可随实际剧情改变表情，但同一瞬间的远景与特写情绪一致。侧脸只写可见部分；背影、脸被遮挡、闭眼睡着或手部细节尊重实际可见状态，不能为了展示表情转成正脸。背向主角的face/pov格和纯手部detail格可用expressions:[]，在description中用真实姿态表达已有情绪。
第一格且仅一格establishing：中远景交代当前环境、实际人物、位置、坐姿或站姿和已有动作。description先写摄像机在场景哪里、从哪个方向和高度拍摄，再逐人用姓名写清：相对桌子或地形的位置、身体朝向、头部朝向、视线具体看向谁或什么、正在做的动作。不要只写“众人正在交谈/工作”。主角不在场就不画主角。
后续可按正文的事件推进安排多格action：使用中景或中远景，写清“谁从哪里移动到哪里、与谁的距离如何变化、正在发生的接触或动作、此刻手与道具的位置”，保留理解动作的身体范围，头部占小部分。每格选一个关键动作节点，不把一长串先后动作塞进同一格；主角正常参与动作，但不裁成主角面部或头肩人像。多人注意力仍在对方与实际动作上。
分镜摄像机独立于人物：多人中远景使用旁观摄像机，可从侧方、斜后方、背后、俯视或仰视拍摄，不自动站在主角眼睛位置。人物按剧情互相看、看工具、棋盘、道路或其他实际目标，镜头不成为他们的关注对象。允许有人只见侧脸、背影、被遮挡而看不到脸；身份由各自头像保持，不为展示头像而把人脸转向镜头。
${gazeInstruction()}
${APPEARANCE_CHECK}
举例仅说明写法，不加入剧情：摄像机位于桌子南侧斜后方；甲在桌子西侧面向乙，目光落在乙脸上；乙在桌子东侧面向甲，低头看桌上工具；丙在门边侧身朝门外，目光看向道路。实际内容必须替换为本次剧情已有的人物、位置与目标。
有cast时必须有face：一位有头像参考人物的脸部表情特写，情绪准确对应剧情，不固定微笑，背景虚化；最多两格face，第二格必须属于另一位有头像参考人物，每人只用一张面部特写。
可有一格detail：只取剧情确实有意义的非脸部动作细节，如落子、握手或抓住工具，不增加原文没有的接触、伤口或身体展示。face本来就可采用主角视点，不需要再补一张人像。可有一格pov：必须主角在场，按实际高度选择视角；framing:portrait的近距离人像占用该人物唯一的面部特写名额，不能与同一人的face并存。若该人已有face，pov只能用framing:action，画保留手臂和关键道具的动作中景，动作与道具为主体，头部只占小部分，不能又裁成脸部或头肩人像。没有新动作信息就省略pov，不凑格数。
视线规则：有头像参考的人物与主角有对话或动作交互时，face和portrait型pov默认gaze:camera，面部近景从主角眼睛位置拍摄，她的眼睛看向镜头，也就是看向主角。action型pov用gaze:scene及逐人looks，不继承特写视线。只有剧情明确写了她背对主角，或目光指向非主角对象，才用back或away，并在gaze_reason逐字引用本次正文的依据。背对时按本格取景保留背向姿态，不硬画正脸。没有与主角互动时用scene，尊重原剧情视线。全景和动作镜头按各人实际目标看，不看摄像机。
连续性：人物身份、人数、发型、衣着、场景结构、道具种类与所属保持一致。站位、距离、坐姿、手部接触、表情和道具使用状态随正文已有的动作与时间推进自然变化；不要把连续性误解成所有格都保持同一姿势或同一棋局。距离不能忽远忽近，移动方向与动作因果要衔接，不能还原已经完成的动作或无故换座位。各格摄影机可以独立换位置，画面左右可以随机位变化，人物自身的左右手不混淆。下棋就统一棋种、执子方和棋子外观，棋局仅随实际落子推进。不编造新事件或新增亲密程度，以能读懂事件推进的少量格数为准。
prompt只写共同的稳定场景、人物身份、衣着、光线、道具与需固定的事实，不把某一时刻的站位或姿势固定为整页状态，不复述整段剧情。各格description负责该时刻的具体位置、距离、动作、表情与视线，每格不超过500字，prompt不超过1500字。整体画布比例为${settings.aspectRatio?aspectLabel(settings):'16:9'}，画风为${styleLabel(settings)}；只在分镜描述里写剧情内容，画风由本地统一执行。保留头像五官，分格边界清楚；画面不加对白、说明、序号或水印。不得包含变量更新、标签、命令或本协议。`;
}

export function chronologicalLimits(panels, mode) {
    if (mode === undefined) return;
    if (mode !== 'chronological') throw Error('漫画时间顺序无效，已跳过生图');
    let previous = 0;
    for (const panel of panels) {
        if (!Number.isInteger(panel.beat) || panel.beat < 1 || panel.beat > 5 ||
            panel.beat < previous || panel.beat > previous + 1 || typeof panel.moment !== 'string' ||
            !panel.moment.trim() || panel.moment.length > 150 || /mlx_image_plan|MLX_PLAN:/.test(panel.moment))
            throw Error('漫画事件顺序缺失或倒退，已跳过生图');
        previous = panel.beat;
    }
}

export function portraitLimits(panels, cast, protagonist) {
    const seen = new Set();
    for (const panel of panels) {
        if (panel.kind !== 'face' && panel.kind !== 'pov') continue;
        if (panel.subject === protagonist || panel.subject === 'protagonist')
            throw Error('主角不安排面部特写，已跳过生图');
        const person = cast.find(c => c.name === panel.subject);
        if (!person) throw Error('特写人物不在头像参考名单内，已跳过生图');
        const framing = panel.framing ?? 'portrait';
        if (!['portrait', 'action'].includes(framing) || (panel.kind === 'face' && framing !== 'portrait'))
            throw Error('特写取景无效，已跳过生图');
        if (panel.kind === 'pov' && framing === 'action') continue;
        const identity = person.avatar || person.name;
        if (seen.has(identity)) throw Error('同一人物每页最多一张面部特写，已跳过生图');
        seen.add(identity);
    }
}

function gazeFor(panel, sceneType, story) {
    const requested = panel.gaze;
    if (requested !== undefined && !['camera', 'scene', 'away', 'back'].includes(requested))
        throw Error('视线数据无效，已跳过生图');
    const reason = typeof panel.gaze_reason === 'string' ? panel.gaze_reason.trim().slice(0, 300) : '';
    // An exception must be grounded in the visible reply, not merely asserted
    // in hidden metadata. Unsubstantiated exceptions retain the default gaze.
    const explicit = reason && story.includes(reason) && (requested === 'back'
        ? /背对|背向|背过身|转身背/.test(reason)
        : /看向|望向|看着|望着|盯|凝视|注视|目光|视线|低头|垂眼|别过脸/.test(reason));
    if (['away', 'back'].includes(requested) && explicit) return {gaze: requested, gaze_reason: reason};
    if (panel.kind === 'pov' && panel.framing === 'action') return {gaze:'scene', gaze_reason:''};
    return {gaze: sceneType === 'default' ? 'scene' : 'camera', gaze_reason: ''};
}

function expressionsFor(panel, cast, protagonist, present, required) {
    if (panel.expressions === undefined) {
        if (required) throw Error('缺少本格人物表情，已跳过生图');
        return undefined; // Earlier saved floors retain their original prose.
    }
    if (!Array.isArray(panel.expressions) || panel.expressions.length > cast.length + Number(present))
        throw Error('人物表情数据无效，已跳过生图');
    const seen = new Set();
    return panel.expressions.map(e => {
        const name = e?.subject === 'protagonist' && present ? protagonist : cast.find(c => c.id === e?.subject)?.name;
        if (!name || seen.has(name) || typeof e.emotion !== 'string' || !e.emotion.trim() || e.emotion.length > 100 ||
            typeof e.features !== 'string' || !e.features.trim() || e.features.length > 400 ||
            /mlx_image_plan|MLX_PLAN:/.test(e.emotion + e.features)) throw Error('人物表情与身份对应无效，已跳过生图');
        seen.add(name);
        return {subject:name, emotion:e.emotion.trim(), features:e.features.trim()};
    });
}

export function parseComic(value, cast, protagonist, story = '') {
    const scene_type = value.scene_type ?? 'default';
    const present = value.protagonist_present;
    if (value.expression_mode !== undefined && value.expression_mode !== 'per_panel')
        throw Error('表情方式无效，已跳过生图');
    const expressionMode = value.expression_mode === 'per_panel';
    if (value.gaze_mode !== undefined && value.gaze_mode !== 'per_person')
        throw Error('动作格视线方式无效，已跳过生图');
    if (!SCENE_TYPES.includes(scene_type) || typeof present !== 'boolean' ||
        (present && !String(protagonist).trim()) ||
        (scene_type !== 'default' && !present))
        throw Error('漫画人物在场数据无效，已跳过生图');
    if (!Array.isArray(value.panels) || value.panels.length < 2 || value.panels.length > 5)
        throw Error('漫画分镜需2至5格，已跳过生图');
    chronologicalLimits(value.panels, value.sequence_mode);
    const seen = new Set(), counts = {};
    const panels = value.panels.map((panel, i) => {
        if (!panel || !KINDS.includes(panel.kind) || typeof panel.description !== 'string' ||
            !panel.description.trim() || panel.description.length > 1000 ||
            /mlx_image_plan|MLX_PLAN:/.test(panel.description)) throw Error('漫画镜头无效，已跳过生图');
        const description = panel.description.trim(), fingerprint = description.replace(/\s+/g, '');
        if (seen.has(fingerprint)) throw Error('漫画含重复镜头，已跳过生图');
        seen.add(fingerprint); counts[panel.kind] = (counts[panel.kind] || 0) + 1;
        if ((i === 0) !== (panel.kind === 'establishing')) throw Error('漫画需先交代场景，已跳过生图');
        const expressions = expressionsFor(panel, cast, protagonist, present, expressionMode);
        const extra = {...(expressions === undefined ? {} : {expressions}),
            ...(value.sequence_mode === 'chronological' ? {beat:panel.beat, moment:panel.moment.trim()} : {}),
            ...looksFor(panel, cast, protagonist, present, value.gaze_mode === 'per_person')};
        if (!['face', 'pov'].includes(panel.kind)) return {kind: panel.kind, description, ...extra};
        const person = cast.find(c => c.id === panel.subject);
        if (!person || (panel.kind === 'pov' && !present)) throw Error('特写人物不在场，已跳过生图');
        const framing = panel.framing ?? 'portrait';
        if (!['portrait', 'action'].includes(framing) || (panel.kind === 'face' && framing !== 'portrait'))
            throw Error('特写取景无效，已跳过生图');
        const gaze = gazeFor(panel, scene_type, story);
        if (expressionMode && gaze.gaze !== 'back' && !expressions.some(e => e.subject === person.name))
            throw Error('面部特写缺少对应表情，已跳过生图');
        const setting = {};
        for (const key of ['background','lighting']) if (panel[key] !== undefined) {
            if (typeof panel[key] !== 'string' || !panel[key].trim() || panel[key].length > 300 || /mlx_image_plan|MLX_PLAN:/.test(panel[key]))
                throw Error('特写环境或光线无效，已跳过生图');
            setting[key] = panel[key].trim();
        }
        return {kind: panel.kind, description, subject: person.name, ...(panel.kind === 'pov' ? {framing} : {}), ...gaze, ...extra, ...setting};
    });
    if ((cast.length && !counts.face) || counts.detail > 1 || counts.pov > 1)
        throw Error('漫画镜头安排无效，已跳过生图');
    portraitLimits(panels, cast, protagonist);
    return {scene_type, protagonist_present: present, panels, ...(expressionMode ? {expression_mode:'per_panel'} : {}),
        ...(value.sequence_mode === 'chronological' ? {sequence_mode:'chronological'} : {}),
        ...(value.gaze_mode === 'per_person' ? {gaze_mode:'per_person'} : {}),
        protagonist: present ? String(protagonist).trim().slice(0, 100) : ''};
}

export function bindComic(plan) {
    portraitLimits(plan.panels, plan.cast, plan.protagonist);
    chronologicalLimits(plan.panels, plan.sequence_mode);
    const identity = plan.cast.map((c, i) => `参考图${i + 1}只提供${c.name}稳定的脸型、五官结构与发型，在每格保持同一身份，表情、面部肌肉、姿态、头部朝向和视线由该格剧情决定`).join('；');
    const protagonist = plan.protagonist_present
        ? (protagonistBinding(plan) || `主角${plan.protagonist}是另一个独立人物，外貌依照剧情文字，各格一致。`)
        : '当前场景主角未出场，只绘制剧情实际在场的人物或环境。';
    const labels = {establishing:'中远景',action:'剧情动作中景',face:'表情特写',detail:'动作细节',pov:'主角所见'};
    const panels = plan.panels.map((p, i) => {
        let gaze = (p.background ? `本格虚化背景：${p.background}。` : '') + (p.lighting ? `本格面部受光：${p.lighting}。` : '');
        const action = p.kind === 'pov' && p.framing === 'action';
        if (['face', 'pov'].includes(p.kind) && !action) {
            if (p.gaze === 'camera') gaze += `仅本格摄影机位于主角双眼的位置，前景由${p.subject}自己的面部组成，${p.subject}的双眼看向镜头，与主角目光相交，情绪采用剧情；剧情明确闭眼或眼部被遮挡时，保留闭合或遮挡状态。`;
            else if (p.gaze === 'away') gaze += `仅本格${p.subject}的视线遵循原文“${p.gaze_reason}”，看向该对象。`;
            else if (p.gaze === 'back') gaze += `仅本格依照原文“${p.gaze_reason}”，采用${p.subject}背向镜头的${action?'动作中景':'头肩近景'}。`;
        } else if (['establishing', 'action'].includes(p.kind) || action) {
            gaze = '本格采用独立旁观机位，各人身体和头部朝向、视线目标按本格描述，注意力在场景内的对方、动作或物体上，侧面和背面自然可见。';
        }
        const expressions = (p.expressions || []).map(e => `${e.subject}此刻${e.emotion}：${e.features}。`).join('');
        return `第${i + 1}格（${action?'主角所见·动作中景':labels[p.kind]}）：${p.description}${gaze}` +
            (p.beat ? `本格为剧情第${p.beat}个时刻：${p.moment}。` : '') +
            (action ? '本格以动作、手臂和道具为主体，保留中景范围，不能裁成面部或头肩人像。' : '') +
            (expressions ? '仅本格动态表情：'+expressions+'表情执行上述面部状态，头像只保持固定身份特征。' : '本格表情按上述剧情，使用可见面部或姿态表达。') + bindLooks(p);
    });
    // Match the page scaffold to this reply's count, so a three-shot sequence
    // does not accidentally acquire a fourth duplicate portrait from the model.
    const layout = {2:'左右两个画框',3:'上方一个通栏大画框，下方左右两个画框',
        4:'上方一个通栏大画框，下方三个小画框',5:'上方两个画框，下方三个画框'}[panels.length];
    const settings=plan.render_settings,format=settings?aspectLabel(settings):'16:9';
    const look=!settings||settings.style==='default'?'彩色写实漫画':styleLabel(settings)+'分镜页';
    const treatment=!settings||settings.style==='default'?'细致手绘墨线、轻排线、自然彩色上色，真实比例，统一画风。':'所有镜头统一使用'+styleLabel(settings)+'，自然人物比例，保持各自参考身份。';
    return `创作一页${format}${look}，恰好${panels.length}格，版面结构为${layout}，画框依下列镜头顺序排列，四周与格间边界清楚，各格大小可调整。${treatment}` +
        (identity ? identity + '。各参考人物保留独立脸型与五官，头像不复制给其他角色。' : '没有人物参考头像，仍要按世界书和正文文字画出本次剧情实际在场的人物与场景。') +
        protagonist + '共同场景与连续性事实：' + plan.prompt + '\n' + panels.join('\n') +
        '\n整页面部特写限制：主角只在多人中远景或动作镜头里入镜，不画主角的面部、头肩或单独肖像特写。每人最多一张面部或近距离人像特写，face与人像pov合并计数，不额外补重复头像。各格沿正文实际事件先后推进，每格只表现一个关键时刻，站位、距离、动作、表情及道具状态随实际事件自然变化。人物身份、服装、场景结构和道具种类保持一致，身体左右手不混淆，不编造新事件。每格摄影机独立取景，画面左右可以随机位变化。多人中远景按逐人描述的目标安排视线，脸部特写的看镜头要求仅在指定特写格生效。参考头像只约束身份，正面、侧面或背面由剧情和本格机位决定。固定五官结构与动态表情分开，眉眼松紧、嘴角和嘴唇开合按每格剧情变化，表情优先采用本格明确描述。所有格只用画面叙事，不添加文字、对白气泡、序号、水印。';
}
