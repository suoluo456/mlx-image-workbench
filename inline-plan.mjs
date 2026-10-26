// Side data travels in the existing reply, then leaves the text stream before
// SillyTavern renders, runs MVU, saves the reply, or builds future chat context.
import {comicInstruction, parseComic} from './comic-plan.mjs?v=0.1.0';
export const OPEN = '<mlx_image_plan>';
export const CLOSE = '</mlx_image_plan>';
export const WIDTH = 1536, HEIGHT = 864;

export function eligiblePeople(people, approved) {
    const allowed = new Set(approved || []);
    return people.filter(p => p.available && allowed.has(p.avatar));
}

export function instruction(people, nonce, protagonist = '', renderSettings = {}) {
    return `附属画面数据协议（不改变正文、角色扮演、MVU及其他既有输出规则）：
先完成本次正常回复及原有变量更新。最后另附且仅附一个下列标签，标签内是严格JSON，不使用代码块、不在正文解释此协议：
${OPEN}${JSON.stringify(people.length ? {nonce,draw:true,composition:"comic",scene_type:"dialogue_pov",protagonist_present:true,cast:[people[0].id],prompt:"当前剧情中的人物和场景",panels:[{kind:"establishing",description:"本次剧情已有的人物站位与环境"},{kind:"face",subject:people[0].id,description:"该人物此刻的表情"}]} : {nonce,draw:true,composition:"comic",scene_type:"default",protagonist_present:false,cast:[],prompt:"本次剧情中的人物与场景，人物外貌依据世界书和正文文字",panels:[{kind:"establishing",description:"本次剧情已有的人物站位与环境"},{kind:"action",description:"本次剧情已经发生的动作"}]})}${CLOSE}
本次主角是用户扮演的人物：${JSON.stringify(String(protagonist))}，不把群聊发言者当成主角。
${comicInstruction(renderSettings)}
有可视剧情就draw:true；仅在没有可绘制内容时draw:false、cast:[]、prompt:""、panels:[]。不为了配图改变正常正文。
可用头像参考人物（不限制性别，不要求已有MVU记录）：${JSON.stringify(people.map(({id,name})=>({id,name})))}。这是头像名单，不是剧情人物名单。世界书或正文中的其他人物可按文字描述入镜，但不放进cast，也不凭空补头像。`;
}

export function parseInline(payloads, people, nonce, protagonist = '', story = '') {
    if (payloads.length !== 1) throw Error('本次回复没有唯一有效的画面数据，已跳过生图');
    const value = JSON.parse(payloads[0]);
    if (value.nonce !== nonce || !Array.isArray(value.cast) || value.cast.length > 2 ||
        new Set(value.cast).size !== value.cast.length) throw Error('画面人物数据无效，已跳过生图');
    const composition = value.composition ?? 'default';
    if (!['default', 'interaction', 'dialogue_pov', 'comic'].includes(composition) ||
        (value.draw !== undefined && typeof value.draw !== 'boolean')) throw Error('构图数据无效，已跳过生图');
    if (value.draw === false || (value.cast.length === 0 && value.draw !== true))
        return {cast: [], prompt: '', skip: true, composition: 'default', protagonist: ''};
    if (['interaction', 'dialogue_pov'].includes(composition) && (value.cast.length !== 1 || !String(protagonist).trim()))
        throw Error('互动构图需要一位人物和明确的主角，已跳过生图');
    const cast = value.cast.map(id => people.find(p => p.id === id));
    if (cast.some(p => !p) || new Set(cast.map(p => p.avatar)).size !== cast.length)
        throw Error('人物不在本聊天的头像参考名单内，已跳过生图');
    if (typeof value.prompt !== 'string' || !value.prompt.trim() || value.prompt.length > 4000 ||
        /mlx_image_plan|MLX_PLAN:/.test(value.prompt)) throw Error('画面描述无效，已跳过生图');
    if (composition === 'comic') return {cast, prompt: value.prompt.trim(), skip: false, composition,
        ...parseComic(value, cast, protagonist, story)};
    return {cast, prompt: value.prompt.trim(), skip: false, composition,
        protagonist: composition === 'default' ? '' : String(protagonist).trim().slice(0, 100)};
}

export function createTextFilter() {
    let buffer = '', hidden = false, payload = '', overflow = false, finished = false;
    const payloads = [], blocks = [];
    let raw = '', rawLength = 0;
    function capture(text) {
        rawLength += text.length;
        raw += text.slice(0, Math.max(0, 256000 - raw.length));
        if (payload.length + text.length > 16000) overflow = true;
        if (!overflow) payload += text;
    }
    function captured(closed) {
        blocks.push({text:raw, closed, length:rawLength, truncated:raw.length < rawLength, parse_overflow:overflow});
        raw = '';rawLength = 0;
    }
    return {
        payloads,
        diagnostics: () => blocks.map(block => ({...block})),
        push(text) {
            if (finished) return '';
            buffer += text; let output = '';
            while (buffer) {
                if (hidden) {
                    const end = buffer.indexOf(CLOSE);
                    if (end < 0) {
                        const count = Math.max(0, buffer.length - CLOSE.length + 1);
                        capture(buffer.slice(0, count)); buffer = buffer.slice(count); break;
                    }
                    capture(buffer.slice(0, end));
                    payloads.push(overflow ? '' : payload);
                    captured(true);
                    buffer = buffer.slice(end + CLOSE.length); hidden = false; payload = ''; overflow = false;
                } else {
                    const start = buffer.indexOf(OPEN);
                    if (start >= 0) {
                        output += buffer.slice(0, start); buffer = buffer.slice(start + OPEN.length); hidden = true;
                    } else {
                        let keep = Math.min(OPEN.length - 1, buffer.length);
                        while (keep && !OPEN.startsWith(buffer.slice(-keep))) keep--;
                        output += buffer.slice(0, buffer.length - keep); buffer = keep ? buffer.slice(-keep) : ''; break;
                    }
                }
            }
            return output;
        },
        finish() {
            if (finished) return ''; finished = true;
            if (hidden) {capture(buffer);captured(false)}
            // An unfinished tag/JSON is hidden too; it never becomes story text.
            const tail = hidden || OPEN.startsWith(buffer) ? '' : buffer;
            buffer = ''; return tail;
        },
    };
}

export function stripInline(text) {
    const filter = createTextFilter();
    return filter.push(String(text || '')) + filter.finish();
}

export async function filterChatResponse(response, streaming, onComplete) {
    if (!response.ok || !response.body) return response;
    const filters = new Map(); let committed = false, story = '', finishReason = null;
    const getFilter = id => {
        if (!filters.has(id)) filters.set(id, createTextFilter());
        return filters.get(id);
    };
    function clean(data) {
        for (const choice of data.choices || []) {
            const index = choice.index || 0;
            const container = choice.delta || choice.message || choice;
            const field = choice.delta || choice.message ? 'content' : 'text';
            if (typeof container[field] === 'string') {
                container[field] = getFilter(index).push(container[field]);
                if (index === 0) story = (story + container[field]).slice(-32000);
            }
            // Some providers echo formatting into reasoning. Keep it hidden there
            // too, but never accept a plan extracted from reasoning as a result.
            for (const name of ['reasoning_content', 'reasoning']) {
                if (typeof container[name] === 'string') container[name] = getFilter(index + ':' + name).push(container[name]);
            }
        }
        return data;
    }
    function commit(complete) {
        if (committed) return; committed = true;
        const diagnostics = [...filters].filter(([id])=>id===0||String(id).startsWith('0:')).flatMap(([id,filter])=>
            filter.diagnostics().map(block=>({channel:id===0?'content':String(id).slice(2),...block})));
        onComplete({payloads: getFilter(0).payloads, complete, story, finishReason, diagnostics});
    }
    const headers = new Headers(response.headers);
    headers.delete('content-length'); headers.delete('content-encoding');
    if (!streaming) {
        const data = clean(await response.json());
        for (const filter of filters.values()) filter.finish();
        const reason = data.choices?.[0]?.finish_reason;
        finishReason = reason || null;
        commit(!data.error && !['length', 'content_filter', 'tool_calls'].includes(reason));
        return new Response(JSON.stringify(data), {status: response.status, statusText: response.statusText, headers});
    }
    const decoder = new TextDecoder(), encoder = new TextEncoder(); let buffer = '';
    const transform = new TransformStream({
        transform(chunk, controller) {
            buffer += decoder.decode(chunk, {stream: true});
            let match;
            while ((match = /\r?\n\r?\n/.exec(buffer))) {
                const event = buffer.slice(0, match.index); buffer = buffer.slice(match.index + match[0].length);
                const lines = event.split(/\r?\n/), data = lines.filter(l => l.startsWith('data:')).map(l => l.slice(5).trimStart()).join('\n');
                if (!data || data === '[DONE]') {
                    if (data === '[DONE]') {finishReason ||= 'done';for (const filter of filters.values()) filter.finish(); commit(true)}
                    controller.enqueue(encoder.encode(event + '\n\n')); continue;
                }
                let parsed; try {parsed = JSON.parse(data)} catch {controller.enqueue(encoder.encode(event + '\n\n')); continue}
                clean(parsed);
                const reason = parsed.choices?.find(c => (c.index || 0) === 0)?.finish_reason;
                if (reason) {finishReason=reason;for (const filter of filters.values()) filter.finish(); commit(reason === 'stop')}
                const prefix = lines.filter(l => !l.startsWith('data:')).join('\n');
                controller.enqueue(encoder.encode((prefix ? prefix + '\n' : '') + 'data: ' + JSON.stringify(parsed) + '\n\n'));
            }
        },
        flush() {for (const filter of filters.values()) filter.finish(); commit(false)},
    });
    const reader=response.body.pipeThrough(transform).getReader();
    const observed=new ReadableStream({
        async pull(controller) {
            try{const result=await reader.read();if(result.done)controller.close();else controller.enqueue(result.value)}
            catch(error){finishReason ||= 'stream_error: '+error.message;for(const filter of filters.values())filter.finish();commit(false);controller.error(error)}
        },
        cancel(reason){finishReason ||= 'cancelled';for(const filter of filters.values())filter.finish();commit(false);return reader.cancel(reason)},
    });
    return new Response(observed, {status: response.status, statusText: response.statusText, headers});
}
