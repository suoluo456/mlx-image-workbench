import {parseInline} from './inline-plan.mjs?v=0.1.0';
import {withProtagonistReference} from './protagonist-reference.mjs?v=0.1.0';

// Native impersonation is explicit. A user may opt in a separate helper prefix;
// ordinary typed messages and unrelated MVU/quiet calls remain excluded.
export function isUserStoryRequest(body, helperPrefix = '') {
    if (body.type === 'impersonate') return true;
    if (!String(helperPrefix).trim()) return false;
    if (!Array.isArray(body.messages)) return false;
    const last=body.messages.findLast(message=>message.role==='user');
    return typeof last?.content==='string' && last.content.trimStart().startsWith(String(helperPrefix).trim());
}

function storyFallback(story, nonce, protagonist) {
    const visible=String(story||'').replace(/<updatevariable\b[^>]*>[\s\S]*?<\/updatevariable>/gi,'')
        .replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim().slice(0,1800);
    if (visible.length<12) return null;
    const present=!!protagonist&&(visible.includes(protagonist)||visible.includes('你'));
    return {nonce,draw:true,composition:'comic',scene_type:'default',protagonist_present:present,
        cast:[],prompt:visible,panels:[
            {kind:'establishing',description:'交代本次剧情中的人物、环境和已有位置：'+visible.slice(0,450)},
            {kind:'action',description:'呈现本次剧情已经发生的动作或反应，不新增事件：'+visible.slice(-450)}]};
}

export function capturePlan(capture, {people, nonce, protagonist, persona, role='assistant', type='normal', chatKey='', model=''}) {
    const {payloads=[],complete=false,story='',finishReason=null,diagnostics=[]}=capture;
    const diagnostic={schema_version:1,id:nonce,nonce,created_at:new Date().toISOString(),
        chat_key:chatKey,source_role:role,generation_type:type,model,complete,finish_reason:finishReason,
        eligible_people:people.map(({id,name,avatar})=>({id,name,avatar})),protagonist,persona_avatar:persona?.avatar||'',
        story_length:story.length,payload_count:payloads.length,raw_blocks:diagnostics,status:'captured',revision:0};
    let stage='transport';
    try {
        if (!complete) throw Error('回复未正常完成（finish_reason='+String(finishReason||'流提前结束')+'）');
        stage='extraction';
        if (diagnostics.some(block=>block.channel==='content'&&block.parse_overflow))
            throw Error('分镜JSON超过16000字符的解析上限，原文已另存');
        if (payloads.length!==1 && !(payloads.length===0 && diagnostics.length===0 && storyFallback(story,nonce,protagonist)))
            throw Error('正文分镜块数量应为1，实际为'+payloads.length+
                (diagnostics.some(block=>!block.closed)?'；存在未闭合的分镜标签':''));
        const fallback=payloads.length===0?storyFallback(story,nonce,protagonist):null;
        stage='json_parse';if (!fallback) JSON.parse(payloads[0]);
        stage='validation';const parsed=parseInline([fallback?JSON.stringify(fallback):payloads[0]],people,nonce,protagonist,story);
        stage='avatar_binding';const plan=withProtagonistReference(parsed,persona);
        const record={...plan,version:plan.composition==='comic'?3:2,nonce,
            cast:plan.cast.map(({name,avatar})=>({name,avatar})),source_role:role,diagnostic_id:nonce};
        diagnostic.status=plan.skip?'model_skipped':fallback?'story_fallback':'validated';diagnostic.stage=stage;
        diagnostic.cast=record.cast;diagnostic.panel_count=record.panels?.length||0;
        return {record,diagnostic};
    } catch(error) {
        diagnostic.status='rejected';diagnostic.stage=stage;
        diagnostic.error={name:error.name||'Error',message:String(error.message||error),stack:String(error.stack||'').slice(0,10000)};
        return {record:{version:2,nonce,skip:true,cast:[],prompt:'',source_role:role,diagnostic_id:nonce,
            reason:diagnostic.error.message+'；已跳过生图，不追加对话API'},diagnostic};
    }
}
