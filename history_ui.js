/* History management uses the same generation controls and server-side records. */
const HistoryUI=(()=>{
 const batchSize=500;
 let serial=0,view='records',loaded=[],total=0,allTotal=0,nextOffset=0,hasMore=false,lastParams=null,loadingMore=null,refreshing=false,loadFailed=false,viewerIndex=-1,viewerPhoto=null,viewerMode='gallery',groupPhotos=[],navigating=false;
 const box=$('photoViewer'),root=$('groups'),actionBox=$('historyActionDialog');let pendingAction=null;
 function askDialog({title,message,value,destructive=false}){return new Promise(resolve=>{pendingAction={resolve,hasInput:value!==undefined};$('actionTitle').textContent=title;$('actionMessage').textContent=message;$('actionName').hidden=value===undefined;$('actionName').value=value||'';$('actionConfirm').textContent=destructive?'永久删除':value!==undefined?'保存':'确认';$('actionConfirm').className=destructive?'danger-button':'';actionBox.showModal();if(value!==undefined){$('actionName').focus();$('actionName').select()}else $('actionCancel').focus()})}
 function finishAction(confirmed){if(!pendingAction)return;const {resolve,hasInput}=pendingAction;pendingAction=null;const result=confirmed?(hasInput?$('actionName').value:true):null;actionBox.close();resolve(result)}
 $('actionConfirm').onclick=()=>finishAction(true);$('actionCancel').onclick=()=>finishAction(false);actionBox.addEventListener('close',()=>finishAction(false));$('actionName').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();finishAction(true)}};
 const node=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e};
 function button(text,handler,cls='secondary'){const b=node('button',cls,text);b.type='button';b.onclick=async e=>{e.stopPropagation();try{await handler(b)}catch(err){notify(err.message)}};return b}
 function notify(text){$('historyNotice').textContent=text;if(box.open){let notice=$('viewerNotice');if(!notice){notice=node('p','hint');notice.id='viewerNotice';notice.setAttribute('role','status');$('viewerTools').after(notice)}notice.textContent=text}}
 function datesToday(){const d=new Date(),date=[d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');$('historyStart').value=date+'T00:00';$('historyEnd').value=date+'T23:59:59'}
 function parameters(){const p=new URLSearchParams({offset:0,limit:batchSize,view,q:$('historyQuery').value.trim()});for(const [key,id]of[['start','historyStart'],['end','historyEnd']])if($(id).value)p.set(key,Math.floor(new Date($(id).value).getTime()/1000));p.set('record_like',$('recordLikeOnly').checked?1:0);p.set('photo_like',$('photoLikeOnly').checked?1:0);return p}
 async function action(body){return api('/api/history/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
 function likeButton(liked,label,handler){const b=button((liked?'♥ ':'♡ ')+label,async()=>{await handler(!liked)},'secondary like-button'+(liked?' is-liked':''));b.setAttribute('aria-pressed',String(!!liked));b.setAttribute('aria-label',label+(liked?'：已收藏':'：未收藏'));return b}
 async function setPhotoLike(groupId,item,liked){await action({action:'like_photo',id:groupId,filename:item.image||item.filename,liked});item.liked=liked;if(viewerPhoto?.filename===(item.image||item.filename)){viewerPhoto.liked=liked;renderViewerTools()}await refresh();if(currentId===groupId)await poll()}
 async function remove(groupId,filename){
  const message=filename?'永久删除这张照片、元数据和生成日志？此操作不能恢复。':'永久删除这条记录，以及本组全部照片、元数据和生成日志？此操作不能恢复。';
  if(!await askDialog({title:'确认永久删除',message,destructive:true}))return;
  await action({action:filename?'delete_photo':'delete_record',id:groupId,filename,confirm:true});
  if(box.open)box.close();notify('已永久删除');
  if(currentId===groupId){const g=await api('/api/history/group?'+new URLSearchParams({id:groupId})).catch(()=>null);drawResults(g);if(!g)currentId=null;lastSignature=''}
  await refresh();
 }
 async function replay(groupId){
  const detail=await api('/api/history/group?'+new URLSearchParams({id:groupId})),opt=detail.replay;
  if(!opt?.models?.length){notify('这条旧记录未保存可识别的模型，无法自动填入');return}
  const missing=[];if(opt.mode!=='reference'){const lookup=new Map(opt.models.map(m=>[m.id,m]));
  models=models.sort((a,b)=>{const ids=opt.models.map(m=>m.id);return (ids.indexOf(a.id)<0?99:ids.indexOf(a.id))-(ids.indexOf(b.id)<0?99:ids.indexOf(b.id))});
  models.forEach(m=>{const old=lookup.get(m.id);m.selected=!!old&&m.ready;if(old){m.steps=old.steps;if(!m.ready)missing.push(m.name)}});
  opt.models.forEach(m=>{if(!models.some(x=>x.id===m.id))missing.push(m.id)});
  }
  $('prompt').value=opt.mode==='reference'&&opt.composition==='comic'?(opt.scene_context||opt.prompt||''):opt.prompt||'';$('negativePrompt').value=opt.negative_prompt||'';$('negativeGuidance').value=opt.negative_guidance||2;
  if(Number.isFinite(Number(opt.width))&&Number.isFinite(Number(opt.height))){$('width').value=opt.width;$('height').value=opt.height;restoreSize()}
  $('count').value=opt.count||1;$('seed').value=opt.seed_input!==undefined?opt.seed_input:opt.seed??'';
  referenceUI.restore(opt,{replayId:groupId});drawModels();save();if(box.open)box.close();
  selectPrimaryTab('create');$('prompt').focus();$('prompt').scrollIntoView({behavior:'smooth',block:'center'});
  const message='已填入历史设置，点击“开始生成”重跑'+(opt.inferred?'；旧记录部分设置由现有参数推断':'')+(missing.length?'；未就绪：'+missing.join('、'):'');
  notify(message);$('status').textContent=message;
 }
 function photoTools(item,groupId){const bar=node('div','photo-tools');if(item.image){bar.append(likeButton(item.liked,'照片 Like',v=>setPhotoLike(groupId,item,v)),button('删除',()=>remove(groupId,item.image),'danger-link'))}return bar}
 async function rename(group){const title=await askDialog({title:'记录命名',message:'最多 100 字，留空清除名称；名称也可以用于搜索。',value:group.title||''});if(title===null)return;await action({action:'rename',id:group.id,title});notify('名称已保存');await refresh()}
 function groupTools(group){const bar=node('div','record-tools');bar.append(likeButton(group.liked,'记录 Like',async liked=>{await action({action:'like_record',id:group.id,liked});await refresh()}),button('重跑',()=>replay(group.id)),button('命名',()=>rename(group)),button('删除记录',()=>remove(group.id),'danger-link'));return bar}
 function itemKey(item){return view==='gallery'?item.filename:item.id}
 function displayLoading(){
  $('historyCount').textContent=view==='gallery'?`已显示 ${loaded.length} / ${total} 张照片`:`已显示 ${loaded.length} / ${total} 条 · 全部 ${allTotal} 条`;
  const more=$('historyLoadMore');more.hidden=!hasMore;more.disabled=!!loadingMore||refreshing;
  more.textContent=loadingMore?'正在加载…':loadFailed?'加载失败，点击重试':'向下滚动自动加载更多 · 点击也可加载';
  observer.unobserve(more);if(hasMore&&!loadingMore&&!refreshing&&!loadFailed)observer.observe(more);
 }
 function append(items,expanded=new Set()){
  for(const entry of items){
   if(view==='gallery'){
    const photo=entry,card=node('article','gallery-photo'),open=button('',()=>{viewerMode='gallery';return showPhoto(loaded.findIndex(p=>p.filename===photo.filename))},'gallery-open');open.setAttribute('aria-label','查看照片 '+(photo.group_title||photo.model||photo.filename));
    const img=node('img');img.src='/images/'+encodeURIComponent(photo.filename);img.alt=photo.group_title||photo.model||'生成照片';img.loading='lazy';open.append(img);
    const info=node('div','gallery-info');info.append(node('span','',photo.group_title||photo.model||'照片'),likeButton(photo.liked,'照片 Like',v=>setPhotoLike(photo.group_id,{image:photo.filename,liked:photo.liked},v)),button('删除',()=>remove(photo.group_id,photo.filename),'danger-link'));
    card.append(open,info);root.append(card);
   }else{
    const group=entry,row=node('article','history-row'),section=node('details','history-entry'),summary=node('summary','group-title');section.dataset.group=group.id;
    summary.append(node('span','history-name',group.title||'未命名记录'),node('span','history-date',new Date(group.created_at*1000).toLocaleString('zh-CN',{hour12:false})+` · ${group.done}/${group.count} 张 · ${group.width} × ${group.height} · ${group.models.join(' / ')} · ${labels[group.state]||({partial:'部分失败',interrupted:'已中断'}[group.state])||group.state}`));summary.append(node('span','history-excerpt',group.prompt_excerpt||'未保存提示词'));
    const content=node('div');section.append(summary,content);let detailsLoaded=false,detailsLoading=false;
    section.addEventListener('toggle',async()=>{if(!section.open||detailsLoaded||detailsLoading)return;detailsLoading=true;content.textContent='加载中…';try{
      const detail=await api('/api/history/group?'+new URLSearchParams({id:group.id}));content.replaceChildren();const promptText=node('p','group-prompt',detail.prompt||'未保存提示词');const grid=node('div','grid');
      detail.items.filter(i=>!i.deleted&&(!$('photoLikeOnly').checked||i.liked&&i.image)).forEach(i=>grid.append(tile(i,group.id,detail)));content.append(promptText,grid);detailsLoaded=true;
    }catch(e){content.textContent=e.message}finally{detailsLoading=false}});
    row.append(section,groupTools(group));root.append(row);section.open=expanded.has(group.id);
   }
  }
 }
 async function refresh({reset=false}={}){
  const request=++serial,p=parameters(),target=reset?batchSize:Math.max(batchSize,loaded.length);lastParams=new URLSearchParams(p);loadingMore=null;refreshing=true;loadFailed=false;observer.disconnect();
  try{
   let h=await api('/api/history?'+p);if(request!==serial)return;
   const rows=h.groups.length?h.groups:h.photos;let received=rows.slice();
   while(h.has_more&&received.length<target){p.set('offset',h.next_offset);h=await api('/api/history?'+p);if(request!==serial)return;received.push(...(view==='gallery'?h.photos:h.groups))}
   if(!currentId&&view==='records'&&received.length){const latest=await api('/api/history/group?'+new URLSearchParams({id:received[0].id}));if(request!==serial)return;drawResults(latest);currentId=latest.id}
   loaded=received;total=h.total;allTotal=h.all_total;nextOffset=h.next_offset;hasMore=h.has_more;
   $('recordView').setAttribute('aria-pressed',String(view==='records'));$('galleryView').setAttribute('aria-pressed',String(view==='gallery'));
   const expanded=reset?new Set():new Set(Array.from(root.querySelectorAll('details[open]')).map(e=>e.dataset.group));root.replaceChildren();root.className=view==='gallery'?'gallery-grid':'';
   if(!loaded.length)root.append(node('p','hint','没有匹配的历史内容'));else append(loaded,expanded);
  }catch(e){if(request===serial)notify(e.message)}finally{if(request===serial){refreshing=false;displayLoading()}}
 }
 async function loadMore(){
  if(refreshing||!hasMore)return false;if(loadingMore)return loadingMore;
  const request=serial,p=new URLSearchParams(lastParams);p.set('offset',nextOffset);loadFailed=false;
  loadingMore=(async()=>{try{
   const h=await api('/api/history?'+p);if(request!==serial)return false;
   const known=new Set(loaded.map(itemKey)),rows=(view==='gallery'?h.photos:h.groups).filter(i=>!known.has(itemKey(i)));
   loaded.push(...rows);total=h.total;allTotal=h.all_total;nextOffset=h.next_offset;hasMore=h.has_more;append(rows);return !!rows.length;
  }catch(e){if(request===serial){loadFailed=true;notify(e.message)}return false}finally{if(request===serial){loadingMore=null;displayLoading()}}})();
  displayLoading();return loadingMore;
 }
 const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))loadMore()},{rootMargin:'500px'});
 $('historyLoadMore').onclick=()=>loadMore();
 function renderViewerTools(){
  const tools=$('viewerTools');
  // Replacing a focused Like button otherwise sends keyboard focus to <body>.
  const focusIndex=Array.from(tools.children).indexOf(document.activeElement);
  tools.replaceChildren();if(!viewerPhoto)return;
  tools.append(likeButton(viewerPhoto.liked,'照片 Like',v=>setPhotoLike(viewerPhoto.group_id,{image:viewerPhoto.filename},v)),button('重跑',()=>replay(viewerPhoto.group_id)),button('删除照片',()=>remove(viewerPhoto.group_id,viewerPhoto.filename),'danger-link'));
  if(focusIndex>=0)tools.children[focusIndex]?.focus({preventScroll:true});
 }
 // Coordinates are CSS pixels; 100% displays one image pixel per CSS pixel.
 const zoomWrap=box.querySelector('.viewer-image-wrap'),zoomImage=$('viewerImage');
 let zoom=1,fitZoom=1,panX=0,panY=0,drag=null,skipClick=false;
 function paintZoom(){
  const w=zoomWrap.clientWidth,h=zoomWrap.clientHeight,iw=zoomImage.naturalWidth*zoom,ih=zoomImage.naturalHeight*zoom;
  panX=iw<=w?(w-iw)/2:Math.max(w-iw,Math.min(0,panX));
  panY=ih<=h?(h-ih)/2:Math.max(h-ih,Math.min(0,panY));
  zoomImage.style.width=zoomImage.naturalWidth+'px';zoomImage.style.height=zoomImage.naturalHeight+'px';
  zoomImage.style.transform=`translate(${panX}px,${panY}px) scale(${zoom})`;
  $('viewerZoomLevel').textContent=Math.round(zoom*100)+'%';
  zoomWrap.classList.toggle('is-zoomed',iw>w+1||ih>h+1);
 }
 function zoomAt(value,x=zoomWrap.clientWidth/2,y=zoomWrap.clientHeight/2){
  if(!zoomImage.naturalWidth)return;
  const next=Math.max(Math.min(fitZoom,.1),Math.min(8,value)),ratio=next/zoom;
  panX=x-(x-panX)*ratio;panY=y-(y-panY)*ratio;zoom=next;paintZoom();
 }
 function resetZoom(){
  drag=null;zoomWrap.classList.remove('is-dragging');
  if(!box.open||!zoomImage.naturalWidth)return;
  fitZoom=Math.min(1,zoomWrap.clientWidth/zoomImage.naturalWidth,zoomWrap.clientHeight/zoomImage.naturalHeight);
  zoom=fitZoom;panX=panY=0;paintZoom();
 }
 function setExpanded(expanded){
  endDrag();
  box.classList.toggle('is-expanded',expanded);
  if(!box.open||!zoomImage.naturalWidth)return;
  if(expanded){
   fitZoom=Math.min(1,zoomWrap.clientWidth/zoomImage.naturalWidth,zoomWrap.clientHeight/zoomImage.naturalHeight);
   zoom=1;panX=(zoomWrap.clientWidth-zoomImage.naturalWidth)/2;panY=(zoomWrap.clientHeight-zoomImage.naturalHeight)/2;paintZoom();
  }else resetZoom();
  $('viewerActual').setAttribute('aria-pressed',String(expanded));
 }
 zoomImage.addEventListener('load',()=>{if(box.classList.contains('is-expanded'))setExpanded(true);else resetZoom()});
 zoomWrap.addEventListener('click',e=>{
  if(skipClick){skipClick=false;return}
  const rect=zoomImage.getBoundingClientRect();
  if(e.clientX>=rect.left&&e.clientX<=rect.right&&e.clientY>=rect.top&&e.clientY<=rect.bottom)setExpanded(!box.classList.contains('is-expanded'));
 });
 zoomWrap.addEventListener('wheel',e=>{
  if(!box.open||actionBox.open)return;e.preventDefault();
  const rect=zoomWrap.getBoundingClientRect(),delta=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?zoomWrap.clientHeight:1);
  zoomAt(zoom*Math.exp(-Math.max(-150,Math.min(150,delta))*.002),e.clientX-rect.left,e.clientY-rect.top);
 },{passive:false});
 zoomWrap.addEventListener('pointerdown',e=>{if(e.button!==0||!zoomWrap.classList.contains('is-zoomed'))return;e.preventDefault();skipClick=false;drag={id:e.pointerId,x:e.clientX,y:e.clientY,px:panX,py:panY,moved:false};zoomWrap.setPointerCapture(e.pointerId);zoomWrap.classList.add('is-dragging')});
 zoomWrap.addEventListener('pointermove',e=>{if(!drag||drag.id!==e.pointerId)return;if(Math.hypot(e.clientX-drag.x,e.clientY-drag.y)>4)drag.moved=true;panX=drag.px+e.clientX-drag.x;panY=drag.py+e.clientY-drag.y;paintZoom()});
 function endDrag(){if(drag?.moved)skipClick=true;drag=null;zoomWrap.classList.remove('is-dragging')}
 ['pointerup','pointercancel','lostpointercapture'].forEach(name=>zoomWrap.addEventListener(name,endDrag));
 zoomWrap.addEventListener('dblclick',()=>setExpanded(false));
 $('viewerZoomIn').onclick=()=>zoomAt(zoom*1.25);$('viewerZoomOut').onclick=()=>zoomAt(zoom/1.25);
 $('viewerFit').onclick=()=>setExpanded(false);$('viewerActual').onclick=()=>setExpanded(true);
 window.addEventListener('resize',()=>{if(box.open){if(box.classList.contains('is-expanded'))setExpanded(true);else resetZoom()}});box.addEventListener('close',()=>{endDrag();skipClick=false;box.classList.remove('is-expanded');$('viewerActual').setAttribute('aria-pressed','false')});
 async function showPhoto(index){const gallery=viewerMode==='gallery',length=gallery?total:groupPhotos.length;if(navigating||index<0||index>=length)return;navigating=true;try{
  if(gallery){const request=serial;while(index>=loaded.length&&hasMore){if(!await loadMore())break;if(request!==serial)return}if(request!==serial)return}
  viewerPhoto=(gallery?loaded:groupPhotos)[index];if(!viewerPhoto)return;viewerIndex=index;
  $('viewerImage').dataset.generationPrompt=viewerPhoto.effective_prompt||'';$('viewerImage').src='/images/'+encodeURIComponent(viewerPhoto.filename);$('viewerImage').alt=viewerPhoto.group_title||'生成照片';
  $('viewerCaption').textContent=(viewerPhoto.group_title||viewerPhoto.model||'照片')+` · ${viewerPhoto.width} × ${viewerPhoto.height} · ${index+1}/${length}`;
  $('viewerPrev').disabled=index<=0;$('viewerNext').disabled=index>=length-1;renderViewerTools();if(!box.open)box.showModal();if(box.classList.contains('is-expanded'))setExpanded(true);else resetZoom();
 }catch(e){notify(e.message)}finally{navigating=false}}
 async function openSingle(groupId,item){
  // Result viewing follows its own record even outside the current history filter.
  const detail=await api('/api/history/group?'+new URLSearchParams({id:groupId}));
  groupPhotos=detail.items.filter(i=>i.image&&!i.deleted).map(i=>({group_id:groupId,group_title:detail.title,filename:i.image,liked:i.liked,model:i.name,effective_prompt:i.effective_prompt,width:detail.width,height:detail.height}));
  viewerMode='group';await showPhoto(groupPhotos.findIndex(i=>i.filename===item.image));
 }
 $('historySearch').onclick=()=>{refresh({reset:true})};$('historyQuery').onkeydown=e=>{if(e.key==='Enter')$('historySearch').click()};
 $('historyReset').onclick=()=>{['historyStart','historyEnd','historyQuery'].forEach(id=>$(id).value='');$('recordLikeOnly').checked=$('photoLikeOnly').checked=false;refresh({reset:true})};
 $('historyToday').onclick=()=>{datesToday();refresh({reset:true})};
 ['recordLikeOnly','photoLikeOnly'].forEach(id=>$(id).onchange=()=>{refresh({reset:true})});
 $('recordView').onclick=()=>{view='records';refresh({reset:true})};$('galleryView').onclick=()=>{view='gallery';refresh({reset:true})};
 $('viewerClose').onclick=()=>box.close();$('viewerPrev').onclick=()=>showPhoto(viewerIndex-1);$('viewerNext').onclick=()=>showPhoto(viewerIndex+1);
 box.addEventListener('click',e=>{if(e.target===box)box.close()});document.addEventListener('keydown',e=>{
  if(!box.open||actionBox.open||viewerIndex<0||e.defaultPrevented||e.isComposing||e.ctrlKey||e.metaKey||e.altKey||['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName))return;
  if(e.key==='ArrowLeft'){e.preventDefault();showPhoto(viewerIndex-1)}
  if(e.key==='ArrowRight'){e.preventDefault();showPhoto(viewerIndex+1)}
 });
 $('imageSize').value=localStorage.getItem('mlx-public-image-size')||'medium';$('imageSize').onchange=()=>{document.body.dataset.imageSize=$('imageSize').value;localStorage.setItem('mlx-public-image-size',$('imageSize').value)};$('imageSize').onchange();
 datesToday();return {refresh,replay,photoTools,openSingle};
})();
