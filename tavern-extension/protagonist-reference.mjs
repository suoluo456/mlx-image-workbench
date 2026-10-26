// User personas are a separate avatar collection from group character cards.
export function needsProtagonist(plan) {
    return plan.protagonist_present === true || plan.composition === 'interaction';
}

export function withProtagonistReference(plan, current) {
    if (!needsProtagonist(plan)) return plan;
    const saved = plan.protagonist_reference;
    const person = saved || (current?.name === plan.protagonist ? current : null);
    if (!person || person.name !== plan.protagonist)
        throw Error('主角人设已变化，请切回该楼层的主角');
    if (typeof person.avatar !== 'string' || !person.avatar ||
        ['none', 'undefined'].includes(person.avatar)) return plan;
    if (/[/\\]/.test(person.avatar)) throw Error('主角头像路径无效');
    return {...plan, protagonist_reference: {name: person.name, avatar: person.avatar, kind: 'user', available: true}};
}

export function protagonistBinding(plan) {
    if (!plan.protagonist_reference) return '';
    return `参考图${plan.cast.length + 1}只对应主角${plan.protagonist}，使用这张独立用户头像保留主角稳定的脸型、五官结构、发型和可辨识特征。主角与其他角色各自使用自己的参考面容，彼此不混用。头像只确定身份，主角的表情、眉眼松紧、嘴角、嘴唇开合、头部朝向、视线和姿势采用本格剧情，侧面或背面也保持该朝向。`;
}
