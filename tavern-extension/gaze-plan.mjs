const VIEWS = ['profile','three_quarter','down','back','occluded'];
const CAMERA_TARGET = /镜头|摄像|摄影|屏幕|观众|观看者|camera|viewer|lens/i;
export const sceneFrame = p => ['establishing','action'].includes(p.kind) || (p.kind==='pov' && p.framing==='action');

export function gazeInstruction() {
    return `gaze_mode固定为per_person。每个establishing、action及动作型pov格都单独带camera和looks；不把这些字段用在face或人像型pov。camera写摄像机在场景哪里、朝哪个方向及高度拍摄；动作格采用侧方、斜后方或俯视的独立旁观机位，不站在对话者眼睛位置。
looks逐人记录本格实际入镜人物，格式为[{"subject":"头像人物ID或protagonist","position":"本人物在场景中的位置、在当前画面中的前后左右、与对象的距离和遮挡关系","kind":"person|object|scene","target":"person用目标人物头像ID或protagonist；object/scene用具体物品或环境目标及位置","body":"身体朝向","head":"头部朝向，鼻尖具体朝哪里","view":"profile|three_quarter|down|back|occluded"}]。subject不能重复，实际入镜的每个人各写一条；没有名单人物的环境格可用[]。
每一张图、每一格都先确定站位再确定视线：用固定的桌子、门、路口等作场景锚点，逐人写position，不只写含混的“左侧/右侧”，而要说明是谁的左侧或当前画面的左侧。target为另一人物时，依据对方本格的position写身体、鼻尖和瞳孔朝向；目标在画面右侧就朝右看，目标在左侧就朝左看，不能写成互相交谈却都看画外同一侧。对视须分别写出甲看乙和乙看甲；单方面注视须按剧情保留另一人的实际目标，不强迫双方对视。目标在近处下方就低头看向该点，远处或高处则采用对应视角。摄像机在人物连线的哪一侧必须说清，换机位后重新判断画面左右，场景中的相对位置、距离和遮挡须连续。
交互时看对方：讲话、挥手、靠近、拥抱时，把target绑定为剧情正在交互的人，头部与瞳孔朝向该人；侧方机位用profile或three_quarter，允许一人只见后脑和背部。做事时看操作点：下棋看正在落子的棋点，穿绳看手中绳头与轮槽，递工具看工具或接物的手，用object与view:down，头部俯下、瞳孔下移。根据本格实际动作逐人选择，不能让所有人机械地看同一个方向。
动作格的target不能是摄像机、镜头、屏幕或画外观看者，view不使用正面肖像。头像只保持身份，不要求露出完整正脸，主角可以背对镜头，其他人物也可以侧脸或被遮挡。只有人物face和人像型pov按原有规则从主角视点看向镜头；明确背对主角或看向其他对象时继续使用有正文依据的例外。动作型pov不继承面部特写的看镜头要求，优先使用独立机位的action格。没有头像的人物仍在画面与文字描述中出现，但不为其编造looks中的头像ID。`;
}

export function looksFor(panel, cast, protagonist, present, required) {
    if (!sceneFrame(panel)) return {};
    if (panel.looks === undefined) {
        if (required) throw Error('缺少动作格逐人视线，已跳过生图');
        return {};
    }
    const nameFor = id => id==='protagonist' && present ? protagonist : cast.find(c=>c.id===id)?.name;
    if (typeof panel.camera!=='string' || !panel.camera.trim() || panel.camera.length>300 || !Array.isArray(panel.looks) ||
        panel.looks.length>cast.length+Number(present) || (required && (cast.length||present) && !panel.looks.length))
        throw Error('动作格机位或人物视线无效，已跳过生图');
    const seen = new Set();
    const looks = panel.looks.map(e=>{
        const subject=nameFor(e?.subject), requestedKind=e?.kind;
        // A worldbook-only person has no avatar ID. Keep the written target
        // instead of discarding the entire page of art.
        const knownTarget=requestedKind==='person'?nameFor(e?.target):null;
        const kind=requestedKind==='person'&&!knownTarget?'scene':requestedKind;
        const target=knownTarget||e?.target;
        if (!subject || seen.has(subject) || !['person','object','scene'].includes(kind) || typeof target!=='string' ||
            !target.trim() || target.length>150 || CAMERA_TARGET.test(target) || (kind==='person' && target===subject) ||
            !VIEWS.includes(e?.view) || [e?.body,e?.head].some(v=>typeof v!=='string'||!v.trim()||v.length>250) ||
            /mlx_image_plan|MLX_PLAN:/.test(target+e.body+e.head))
            throw Error('动作格人物朝向或视线目标无效，已跳过生图');
        const position=e.position;
        if(position!==undefined&&(typeof position!=='string'||!position.trim()||position.length>250||/mlx_image_plan|MLX_PLAN:/.test(position)))
            throw Error('动作格人物位置无效，已跳过生图');
        seen.add(subject);
        return {subject,kind,target:target.trim(),body:e.body.trim(),head:e.head.trim(),view:e.view,...(position?{position:position.trim()}:{})};
    });
    if (required && (panel.expressions||[]).some(e=>!seen.has(nameFor(e.subject))))
        throw Error('动作格缺少可见人物的视线目标，已跳过生图');
    return {camera:panel.camera.trim(),looks};
}

export function bindLooks(panel) {
    if (!sceneFrame(panel)) return '';
    if (Array.isArray(panel.looks) && !panel.looks.length) return '本格按已有场景取景，摄影机位置：'+panel.camera+'。';
    return '本格为独立旁观机位，' + (panel.camera ? '摄影机位置：'+panel.camera+'。' : '') +
        (panel.looks||[]).map(e=>{
            const target=(panel.looks||[]).find(person=>person.subject===e.target);
            return `${e.subject}`+(e.position?`位于${e.position}；`:'')+`身体${e.body}，头部${e.head}，采用${e.view}朝向，视线落点为${e.target}。`+
                (e.kind==='person'&&target?.position?`${e.subject}看向的${e.target}位于${target.position}，鼻尖与瞳孔必须沿两人位置的连线指向对方。`:'');
        }).join('') +
        '交互看对方，做事看操作点，人物保持侧面、低头或背向的实际朝向，面部特写的看镜头要求不适用于本格。';
}
