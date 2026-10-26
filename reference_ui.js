/* One-reference trial mode. Reference images remain on this computer. */
const referenceUI=(()=>{
 const el=id=>document.getElementById(id),key='mlx-public-reference-v1';
 let reference=null,ready=false,uploading=false,replay=null;
 const prefix='以参考图中的人物为同一位主角，保留其面部轮廓、五官比例、眼睛、鼻子、嘴和可辨识特征，不要更换人物身份。根据以下要求改变画面：';
 const active=()=>el('generationMode').value==='reference';
 function remember(){localStorage.setItem(key,JSON.stringify({mode:el('generationMode').value,reference,replay,preserve:el('preserveIdentity').checked}))}
 function preview(){
  el('referencePreview').hidden=!reference;
  if(reference)el('referencePreview').src='/references/'+reference;
  else el('referencePreview').removeAttribute('src');
  el('clearReference').hidden=!reference;
  const extra=el('referenceReplayPreviews'),info=el('referenceReplayInfo');extra.replaceChildren();
  if(replay){
   replay.references.slice(1).forEach((id,index)=>{const image=document.createElement('img');image.src='/references/'+id;image.alt='参考图 '+(index+2)+(replay.names[index+1]?' · '+replay.names[index+1]:'');image.style.cssText='max-width:96px;max-height:110px;border-radius:6px;object-fit:contain';extra.append(image)});
   info.textContent=`历史重跑：${replay.references.length} 张参考图`+(replay.names.length?' · '+replay.names.join('、'):'')+'。保留原来的人物对应、分镜和画风；可修改共同场景、尺寸和种子。';
  }
  info.hidden=!replay;extra.hidden=!replay||replay.references.length<2;

 }
 function sync({align=false}={}){
  const on=active();el('referenceControls').hidden=!on;
  el('models').hidden=on;el('models').previousElementSibling.hidden=on;
  el('negativePrompt').disabled=el('negativeGuidance').disabled=true;
  el('count').disabled=on;if(on)el('count').value=1;
  for(const id of ['width','height']){
   el(id).step=on?'32':'16';
   if(on&&align)el(id).value=Math.max(256,Math.min(1536,Math.round(Number(el(id).value)/32)*32));
  }
  el('referenceAvailability').textContent=ready?'Qwen Turbo MLX · 固定 8 步 · 每次一张':'参考图组件尚未就绪';
  preview();
 }
 function setReady(info){ready=!!info?.ready;sync()}
 function initialize(info){
  try{const old=JSON.parse(localStorage.getItem(key)||'{}');reference=old.reference||null;replay=old.replay&&typeof old.replay.id==='string'&&Array.isArray(old.replay.references)?old.replay:null;el('generationMode').value=old.mode==='reference'?'reference':'text';el('preserveIdentity').checked=old.preserve!==false}catch{}
  setReady(info);
 }
 function restore(options,{replayId}={}){
  el('generationMode').value=options.mode==='reference'?'reference':'text';
  const references=options.references?.length?options.references:[options.reference].filter(Boolean);
  replay=options.mode==='reference'&&replayId?{id:replayId,references,names:options.reference_characters||[],tavern:options.source==='sillytavern'}:null;
  reference=references[0]||null;el('preserveIdentity').checked=options.preserve_identity!==false;
  sync();remember();
 }
 el('generationMode').onchange=()=>{replay=null;sync({align:true});restoreSize();updateSummary();save();remember()};
 el('preserveIdentity').onchange=()=>{updateSummary();remember()};
 el('clearReference').onclick=()=>{reference=null;replay=null;el('referenceFile').value='';preview();updateSummary();remember()};
 el('referenceFile').onchange=async()=>{
  const file=el('referenceFile').files[0];if(!file)return;
  if(file.size>10*1024*1024){el('referenceMessage').textContent='参考图最多 10 MB';return}
  uploading=true;el('referenceMessage').textContent='正在保存参考图…';updateSummary();
  try{
   const image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file)});
   const result=await api('/api/reference/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image})});
   reference=result.id;replay=null;preview();remember();el('referenceMessage').textContent=`已保存 · ${result.width} × ${result.height} · 仅保存在本机`;
  }catch(error){el('referenceMessage').textContent=error.message||'上传失败，请重新选择'}
  finally{uploading=false;el('referenceFile').value='';updateSummary()}
 };
 function summary(){
  if(!active())return;
  let error=uploading?'参考图上传中':!ready?'参考图组件尚未就绪':!reference?'请上传一张参考图':'';
  const w=Number(el('width').value),h=Number(el('height').value);
  if(w%32||h%32)error='参考图模式的宽高需为 32 的倍数';
  const limit=replay?.tavern?2560:1536;
  if(Math.max(w,h)>limit)error='参考图宽高最多 '+limit+'，请调小尺寸';
  el('queueHint').textContent=error||(replay?'已恢复历史参考图与人物对应；点击“开始生成”重跑。':'Qwen Turbo · 人物参考 · 8 步 · 一张 · 参考图读取预算 512');
  el('generate').disabled=el('generateTop').disabled=running||!!error;
 }
 function augment(body){
  if(active())Object.assign(body,{mode:'reference',reference,preserve_identity:el('preserveIdentity').checked,
     count:1,negative_prompt:'',models:[{id:'qwen21_turbo_ref',steps:8}],...(replay?{history_replay_id:replay.id}:{})});
  return body;
 }
 function drawPreview(root){
  if(!active())return false;
  const item=document.createElement('div'),title=document.createElement('strong'),note=document.createElement('small'),text=document.createElement('pre');
  item.className='preview-item';title.textContent='Qwen Turbo · 人物参考';
  note.textContent=replay?'历史重跑保留每位人物的独立头像、分镜和画风':el('preserveIdentity').checked?'自动加入保留面部轮廓与五官要求；效果以实际结果为准':'按原始描述编辑参考图';
  text.textContent=(!replay&&el('preserveIdentity').checked?prefix:'')+el('prompt').value.trim();
  item.append(title,note,text);root.append(item);return true;
 }
 function drawReference(root,group){
  const ids=group?.options?.references||[group?.options?.reference];if(group?.options?.mode!=='reference')return;
  ids.filter(Boolean).forEach((id,index)=>{
  const card=document.createElement('div'),area=document.createElement('div'),image=document.createElement('img'),info=document.createElement('div');
  card.className='tile';area.className='image-area';area.dataset.aspect='true';area.style.setProperty('--image-aspect','1 / 1');
  image.src='/references/'+id;image.alt='输入参考图';
  image.onload=()=>area.style.setProperty('--image-aspect',`${image.naturalWidth} / ${image.naturalHeight}`);
  info.className='tile-info';info.textContent='参考图 '+(index+1)+(group.options.reference_characters?.[index]?' · '+group.options.reference_characters[index]:' · 用于比较人物外貌');area.append(image);card.append(area,info);root.append(card);
  });
 }
 return {active,initialize,setReady,restore,summary,augment,drawPreview,drawReference};
})();
