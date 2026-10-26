// Read the prompt stored in this particular image, never regenerate a plan.
const decoder = new TextDecoder();
const latin = new TextDecoder('latin1');
const MAX_TEXT = 2 * 1024 * 1024;

async function inflate(bytes) {
    const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate')).getReader();
    const chunks=[];let length=0;
    try {
        while (true) {
            const {done,value}=await reader.read();if(done)break;
            length+=value.length;if(length>MAX_TEXT)throw Error('图片提示词过大');
            chunks.push(value);
        }
    } finally { await reader.cancel().catch(()=>{}); }
    const result=new Uint8Array(length);let offset=0;
    for(const chunk of chunks){result.set(chunk,offset);offset+=chunk.length;}
    return result;
}

export async function pngPrompt(buffer) {
    const bytes=new Uint8Array(buffer);
    if(bytes.length<8 || ![137,80,78,71,13,10,26,10].every((v,i)=>bytes[i]===v))return '';
    const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
    let plain='';
    for(let offset=8;offset+12<=bytes.length;){
        const length=view.getUint32(offset),type=latin.decode(bytes.subarray(offset+4,offset+8));
        if(length>bytes.length-offset-12)break;
        const data=bytes.subarray(offset+8,offset+8+length);offset+=12+length;
        if(type==='IEND')break;
        if(!['iTXt','tEXt','zTXt'].includes(type)||length>MAX_TEXT)continue;
        const end=data.indexOf(0);if(end<0)continue;
        const key=latin.decode(data.subarray(0,end));let text;
        try {
            if(type==='iTXt'){
                if(end+3>data.length)continue;
                const compressed=data[end+1],method=data[end+2];
                const language=data.indexOf(0,end+3),translated=language<0?-1:data.indexOf(0,language+1);
                if(translated<0||compressed>1||(compressed&&method!==0))continue;
                const payload=data.subarray(translated+1);
                text=decoder.decode(compressed?await inflate(payload):payload);
            }else if(type==='zTXt'){
                if(data[end+1]!==0)continue;
                text=decoder.decode(await inflate(data.subarray(end+2)));
            }else text=decoder.decode(data.subarray(end+1));
            // MFLUX's full prompt is in XMP; its IPTC caption can be truncated.
            if(key==='XML:com.adobe.xmp'){
                const xml=new DOMParser().parseFromString(text,'application/xml');
                const description=xml.getElementsByTagNameNS('http://purl.org/dc/elements/1.1/','description')[0];
                const prompt=description?.textContent?.trim();if(prompt)return prompt;
            }
            try {const value=JSON.parse(text);if(typeof value?.prompt==='string'&&value.prompt)return value.prompt;} catch {}
            if(['parameters','prompt','Description'].includes(key)&&text.trim())plain=text.trim();
        } catch { /* A broken optional metadata chunk must not break image viewing. */ }
    }
    return plain;
}

export function promptLoader(fetchImage=fetch) {
    const cache=new Map();
    return async image=>{
        if(image.dataset.generationPrompt)return image.dataset.generationPrompt;
        const url=new URL(image.currentSrc||image.src,location.href);
        if(url.origin!==location.origin && !url.href.startsWith('data:image/png'))return '';
        const key=url.href;
        if(!cache.has(key)){
            if(cache.size>=48)cache.delete(cache.keys().next().value);
            cache.set(key,(async()=>{
                const response=await fetchImage(key,{credentials:'same-origin'});
                if(!response.ok)throw Error('无法读取这张图片的提示词');
                if(Number(response.headers.get('Content-Length'))>50*1024*1024)throw Error('图片过大，无法读取提示词');
                return pngPrompt(await response.arrayBuffer());
            })().catch(error=>{cache.delete(key);throw error;}));
        }
        return cache.get(key);
    };
}

export function installPromptHover({selector,load=promptLoader(),delay=400}={}) {
    if(!selector||document.getElementById('mlxPromptHoverStyle'))return;
    const style=document.createElement('style');style.id='mlxPromptHoverStyle';
    style.textContent=`.mlx-prompt-hover{display:flex;flex-direction:column;position:fixed;inset:auto;margin:0;width:min(660px,calc(100vw - 24px));max-height:min(72vh,680px);box-sizing:border-box;padding:14px;border:1px solid #737286;border-radius:12px;background:#202129;color:#eee;box-shadow:0 12px 46px #0009;z-index:2147483647;font:14px/1.55 system-ui,sans-serif;text-align:left;overflow:hidden}.mlx-prompt-hover[hidden]{display:none!important}.mlx-prompt-hover .mlx-prompt-head{flex-shrink:0;display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:8px}.mlx-prompt-hover button{cursor:pointer;border:1px solid #737286;border-radius:7px;padding:5px 12px;background:#353543;color:#eee;font:inherit;flex-shrink:0}.mlx-prompt-hover pre{flex:1;min-height:0;margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;user-select:text;overflow:auto;overscroll-behavior:contain;padding-right:8px}.mlx-prompt-hover small{flex-shrink:0;display:block;color:#bbb8c9;font-size:12px;margin-top:8px}`;
    document.head.append(style);
    const panel=document.createElement('div');panel.id='mlxPromptHover';panel.className='mlx-prompt-hover';panel.hidden=true;
    panel.setAttribute('role','region');panel.setAttribute('aria-label','完整生图提示词');panel.setAttribute('popover','manual');
    const head=document.createElement('div');head.className='mlx-prompt-head';
    const title=document.createElement('strong');title.textContent='完整生图提示词';
    const copy=document.createElement('button');copy.type='button';copy.textContent='复制全部';copy.disabled=true;
    const text=document.createElement('pre'),hint=document.createElement('small');text.tabIndex=0;hint.textContent='可滚动查看全部文字 · 移入浮层可选中复制 · Esc 关闭';
    head.append(title,copy);panel.append(head,text,hint);document.body.append(panel);
    let active=null,showTimer,hideTimer,serial=0,savedTitle=null;
    function hide(){
        clearTimeout(showTimer);clearTimeout(hideTimer);serial++;
        if(active){active.removeAttribute('aria-describedby');if(savedTitle!==null)active.setAttribute('title',savedTitle);}
        active=null;savedTitle=null;
        try{if(panel.matches(':popover-open'))panel.hidePopover();}catch{}
        panel.hidden=true;
    }
    function position(image){
        const rect=image.getBoundingClientRect(),right=innerWidth-rect.right-22,leftSpace=rect.left-22;
        const side=Math.max(right,leftSpace),fullWidth=Math.min(660,innerWidth-24);
        panel.style.width=(side>=320?Math.min(fullWidth,side):fullWidth)+'px';
        const width=panel.offsetWidth,height=panel.offsetHeight;
        let left=right>=leftSpace?rect.right+10:rect.left-width-10;
        panel.style.left=Math.max(12,Math.min(innerWidth-width-12,left))+'px';
        panel.style.top=Math.max(12,Math.min(innerHeight-height-12,rect.top))+'px';
    }
    function schedule(image){
        clearTimeout(hideTimer);if(active===image)return;
        hide();active=image;const source=image.currentSrc||image.src,request=serial;
        savedTitle=image.getAttribute('title');image.removeAttribute('title');
        showTimer=setTimeout(async()=>{
            if(active!==image||request!==serial)return;
            text.textContent='正在读取这张图片保存的提示词…';copy.disabled=true;copy.textContent='复制全部';panel.hidden=false;
            // Popovers remain visible above both Tavern and workbench image dialogs.
            try{panel.showPopover();}catch{(image.closest('dialog[open]')||document.body).append(panel);}
            image.setAttribute('aria-describedby',panel.id);position(image);
            try{
                const value=await load(image);
                if(active!==image||request!==serial||(image.currentSrc||image.src)!==source)return;
                text.textContent=value||'这张图片没有保存可读取的完整提示词。';copy.disabled=!value;
            }catch(error){if(active===image&&request===serial)text.textContent=error.message;}
            if(active===image&&request===serial){text.scrollTop=0;position(image);}
        },delay);
    }
    function imageAt(target){return target?.closest?.(selector)||target?.closest?.('a,button')?.querySelector(selector);}
    document.addEventListener('pointerover',event=>{
        if(panel.contains(event.target)){clearTimeout(hideTimer);return;}
        const image=imageAt(event.target);if(image)schedule(image);
    });
    document.addEventListener('pointerout',event=>{
        if((active===event.target||panel.contains(event.target))&&!panel.contains(event.relatedTarget)&&event.relatedTarget!==active)
            hideTimer=setTimeout(hide,240);
    });
    document.addEventListener('focusin',event=>{if(panel.contains(event.target)){clearTimeout(hideTimer);return;}const image=imageAt(event.target);if(image)schedule(image);});
    document.addEventListener('focusout',event=>{if(active===event.target&&!panel.contains(event.relatedTarget))hideTimer=setTimeout(hide,240);});
    document.addEventListener('keydown',event=>{if(event.key==='Escape')hide();});
    document.addEventListener('pointerdown',event=>{if(!panel.contains(event.target))hide();});
    // Focusing an image can scroll it into view before the delayed popup opens.
    document.addEventListener('scroll',event=>{if(active&&!panel.hidden&&!panel.contains(event.target))hide();},true);
    window.addEventListener('resize',hide);
    const annotate=root=>{if(root.matches?.(selector))root.tabIndex=0;root.querySelectorAll?.(selector).forEach(image=>image.tabIndex=0);};
    annotate(document);new MutationObserver(changes=>{for(const change of changes){for(const node of change.addedNodes)annotate(node);if(change.type==='attributes'&&active===change.target)hide();}})
        .observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['src']});
    copy.onclick=async()=>{
        try{await navigator.clipboard.writeText(text.textContent);copy.textContent='已复制';}
        catch{copy.textContent='请选中文字复制';}
    };
    return {hide};
}
