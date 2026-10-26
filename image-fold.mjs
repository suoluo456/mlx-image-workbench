// Presentation-only folding for message image attachments. Tavern continues to
// own the media nodes, gallery controls, files, and chat data.
export const IMAGE_FOLD_KEY = 'mlx_plot_fold_images_v1';

export function installImageFold({toggle, doc=document, storage=localStorage,
    Observer=MutationObserver} = {}) {
    const style=doc.createElement('style');
    style.id='mlxPlotImageFoldStyle';
    style.textContent=`
body.mlx-fold-images .mes:not([data-mlx-image-open="true"]) .mes_media_wrapper > .mes_img_container{display:none!important}
.mlx-image-fold-toggle{display:none;align-items:center;gap:.4em;margin:.35em 0;padding:.28em .65em;border:1px solid var(--SmartThemeBorderColor,#777);border-radius:6px;background:var(--SmartThemeBlurTintColor,#303039);color:var(--SmartThemeBodyColor,#eee);font:inherit;cursor:pointer}
body.mlx-fold-images .mlx-image-fold-toggle{display:inline-flex}
.mlx-image-fold-toggle:focus-visible{outline:2px solid currentColor;outline-offset:2px}`;
    doc.head.append(style);
    let enabled=false;
    try { enabled=storage.getItem(IMAGE_FOLD_KEY)==='true'; } catch {}
    const updateButton=(message,button)=>{
        const open=message.dataset.mlxImageOpen==='true';
        const label=open?'收起图片':'显示图片';
        if(button.textContent!==label)button.textContent=label;
        button.setAttribute('aria-expanded',String(open));
    };
    const scan=()=>{
        for(const message of doc.querySelectorAll('.mes')){
            const media=message.querySelector('.mes_media_wrapper');
            if(!media)continue;
            let button=message.querySelector('.mlx-image-fold-toggle');
            if(!media.querySelector('.mes_img_container')){
                if(button)button.remove();
                continue;
            }
            if(!button){
                button=doc.createElement('button');button.type='button';
                button.className='mlx-image-fold-toggle';
                button.addEventListener('click',()=>{
                    message.dataset.mlxImageOpen=message.dataset.mlxImageOpen==='true'?'false':'true';
                    updateButton(message,button);
                });
                media.parentNode.insertBefore(button,media);
            }
            updateButton(message,button);
        }
    };
    const apply=()=>{
        doc.body.classList.toggle('mlx-fold-images',enabled);
        if(toggle)toggle.checked=enabled;
        scan();
    };
    if(toggle)toggle.addEventListener('change',()=>{
        enabled=toggle.checked;
        try { storage.setItem(IMAGE_FOLD_KEY,String(enabled)); } catch {}
        apply();
    });
    apply();
    let scheduled=false;
    const observer=new Observer(records=>{
        const mediaChanged=records.some(record=>
            record.target?.classList?.contains('mes_media_wrapper') ||
            [...record.addedNodes].some(node=>node.nodeType===1 &&
                (node.matches?.('.mes, .mes_media_wrapper, .mes_img_container') ||
                    node.querySelector?.('.mes_media_wrapper, .mes_img_container'))));
        if(!mediaChanged)return;
        if(scheduled)return;
        scheduled=true;
        queueMicrotask(()=>{scheduled=false;scan()});
    });
    observer.observe(doc.querySelector('#chat')||doc.body,{childList:true,subtree:true});
    return {scan,disconnect:()=>observer.disconnect()};
}
