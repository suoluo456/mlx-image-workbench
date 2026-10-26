import {bindPrompt} from './planner.mjs?v=0.1.0';
import {eligiblePeople,instruction,parseInline,stripInline,filterChatResponse} from './inline-plan.mjs?v=0.1.0';
import {withProtagonistReference} from './protagonist-reference.mjs?v=0.1.0';
import {installPromptHover} from './prompt-hover.mjs?v=0.1.0';
import {capturePlan,isUserStoryRequest} from './plan-capture.mjs?v=0.1.0';
import {createDiagnosticWriter} from './diagnostics.mjs?v=0.1.0';
import {installImageFold} from './image-fold.mjs?v=0.1.0';
import {SETTINGS_KEY,LEVELS,RATIOS,STYLES,settingsFor,normalizeSettings,withRenderSettings,styleLabel} from './render-settings.mjs?v=0.1.0';
import {DEFAULT_URL,EXTENSION_KEY,DEFAULT_WORKFLOW,connectionSettings,normalizeUrl,ownsWorkflow,isWorkbenchTarget,validateWorkflow,readHealth,requireReady,testConnection,applyConfiguration,restoreConfiguration} from './connection.mjs?v=0.1.0';
import {appendMediaToMessage} from '../../../../script.js';
import {MEDIA_DISPLAY,MEDIA_SOURCE,MEDIA_TYPE,SCROLL_BEHAVIOR} from '../../../constants.js';
import {user_avatar,getUserAvatar} from '../../../personas.js';

const ctx=()=>SillyTavern.getContext(),baseFetch=window.fetch.bind(window);
let busy=false,nativeBusy=false,manual=[],autoQueue=[],autoRunning=false,controller=null,generationFrame=null,nativeAnchor=null;
const plans=new Map(),completed=[],avatarCache=new Map(),seenAuto=new Set();
let freshPlans=new WeakMap(),boundFrames=new WeakMap();const diagnostics=createDiagnosticWriter(baseFetch, undefined, ()=>connectionSettings(ctx().extensionSettings).url);
const key=()=>String(ctx().groupId||ctx().characterId)+':'+ctx().getCurrentChatId();
const status=text=>{const node=document.getElementById('mlxPlotStatus');if(node)node.textContent=text};
function catalog(){
 const c=ctx(),members=c.groupId?c.groups.find(g=>String(g.id)===String(c.groupId))?.members:[c.characters[c.characterId]?.avatar];
 return [...new Set(members||[])].map((avatar,i)=>{const char=c.characters.find(x=>x.avatar===avatar);return {id:'c'+i,name:char?.name||avatar||'缺少头像',avatar,available:!!char&&!!avatar&&avatar!=='none'}});
}
// A reference is optional: worldbook-only characters can be drawn from text.
// Every available character is eligible by default.
const approved=()=>Array.isArray(ctx().chatMetadata.mlx_plot_characters)?ctx().chatMetadata.mlx_plot_characters:
 catalog().filter(p=>p.available).map(p=>p.avatar);
const eligible=()=>eligiblePeople(catalog(),approved());
function storyText(message,limit=8000){
 const doc=new DOMParser().parseFromString(stripInline(message),'text/html');
 doc.querySelectorAll('script,style,details,updatevariable,jsonpatch,analysis,think,thinking,simple_thinking,dream_think,statusplaceholderimpl').forEach(n=>n.remove());
 const text=(doc.body.textContent||'').replace(/\s+/g,' ');return limit?text.slice(-limit):text;
}
function latestId(){return ctx().chat.findLastIndex(m=>!m.is_system&&(!m.is_user||m.extra?.mlx_plot_plan?.source_role==='user')&&(!m.extra?.media?.length||m.extra?.mlx_plot_plan))}
function rememberDiagnostic(document){
 diagnostics.save(document);
 const link=documentNode('mlxPlotDiagnosticLink');if(link)link.href=diagnostics.url();
}
const documentNode=id=>document.getElementById(id);
function keepCompleted(entry){completed.push(entry);if(completed.length>8)completed.shift()}
function newFrame(type,role='assistant'){
 return {key:key(),length:ctx().chat.length,last:ctx().chat.at(-1)?.mes,type,role,requested:false};
}
function matchesUserStory(entry,message){
 const normalize=text=>storyText(text,0).replace(/[^\p{L}\p{N}]/gu,'');
 const a=normalize(entry.story),b=normalize(message.mes);
 return !!a&&a===b;
}
function render(){
 const select=document.getElementById('mlxPlotCast'),women=document.getElementById('mlxPlotWomen');if(!select||!women)return;
 select.replaceChildren();women.replaceChildren();const people=catalog(),allowed=eligible();
 for(const person of people){const o=document.createElement('option');o.value=person.avatar;o.textContent=person.name;o.selected=approved().includes(person.avatar);women.append(o)}
 for(const person of allowed){const o=document.createElement('option');o.value=person.avatar;o.textContent=person.name;o.selected=manual.includes(person.avatar);select.append(o)}
 document.getElementById('mlxPlotAuto').checked=ctx().chatMetadata.mlx_plot_auto===true;
 renderSettings();
 const missing=people.filter(p=>approved().includes(p.avatar)&&!allowed.some(a=>a.avatar===p.avatar));
 document.getElementById('mlxPlotEligibility').textContent='当前可触发：'+(allowed.map(p=>p.name).join('、')||'无')+(missing.length?'；头像不可用：'+missing.map(p=>p.name).join('、'):'');
}
function renderSettings(){
 const selected=settingsFor(ctx().chatMetadata);
 document.getElementById('mlxPlotRatio').value=selected.aspectRatio;
 document.getElementById('mlxPlotResolution').replaceChildren(...LEVELS.map((level,i)=>{
  const size=normalizeSettings({...selected,level:i}),option=document.createElement('option');
  option.value=String(i);option.textContent=level.name+(selected.aspectRatio==='custom'?'':` · ${size.width}×${size.height}`);return option;
 }));
 document.getElementById('mlxPlotResolution').value=String(selected.level);
 document.getElementById('mlxPlotResolution').disabled=selected.aspectRatio==='custom';
 document.getElementById('mlxPlotStyle').value=selected.style;
 document.getElementById('mlxPlotCustomSize').hidden=selected.aspectRatio!=='custom';
 document.getElementById('mlxPlotWidth').value=selected.width;document.getElementById('mlxPlotHeight').value=selected.height;
 document.getElementById('mlxPlotRenderHint').textContent=`本聊天：${selected.width}×${selected.height} · ${styleLabel(selected)}。自动生图与手动补图均按当前选择执行。`+
  (Math.max(selected.width,selected.height)>1536?' 高清画布：漫画按格绘制并拼版；参考图单镜头最多1536，超出的部分用本地缩放适配画布，不额外生图。':'宽高按参考图模式32像素对齐。');
}
function initializeRenderSettings(){
 for(const [id,options] of [['mlxPlotRatio',RATIOS],['mlxPlotStyle',STYLES]]){
  document.getElementById(id).replaceChildren(...options.map(([value,label])=>{const option=document.createElement('option');option.value=value;option.textContent=label;return option}));
 }
 const change=patch=>{
  const selected=normalizeSettings({...settingsFor(ctx().chatMetadata),...patch});
  ctx().chatMetadata[SETTINGS_KEY]=selected;ctx().saveMetadataDebounced();renderSettings();
  status(`之后生图使用 ${selected.width}×${selected.height} · ${styleLabel(selected)}；已在本聊天保存`);
 };
 document.getElementById('mlxPlotRatio').onchange=e=>change({aspectRatio:e.target.value});
 document.getElementById('mlxPlotResolution').onchange=e=>change({level:Number(e.target.value)});
 document.getElementById('mlxPlotStyle').onchange=e=>change({style:e.target.value});
 for(const [id,key] of [['mlxPlotWidth','width'],['mlxPlotHeight','height']])document.getElementById(id).onchange=e=>change({[key]:Number(e.target.value)});
}
function savedPlan(messageId,request='',allowManual=true){
 const message=ctx().chat[messageId];if(!message)throw Error('没有可用的剧情楼层');
 const allowed=eligible(messageId),record=message.extra?.mlx_plot_plan;
 const selected=allowed.filter(p=>manual.includes(p.avatar));
 if(allowManual&&selected.length){
  if(selected.length>2)throw Error('最多选择两位人物');
  if([2,3].includes(record?.version)&&!record.skip&&record.cast.length===selected.length&&record.cast.every((p,i)=>p.avatar===selected[i].avatar))
   return {...record,cast:selected,prompt:record.prompt+(request?'。额外画面要求：'+request:'')};
  const story=storyText(message.mes);
  if(selected.some(p=>!story.includes(p.name)))throw Error('旧楼层需明确出现所选人物，不能用最新剧情替代');
  return {cast:selected,prompt:'仅描绘以下剧情中所选人物的一个瞬间：'+story+(request?'。额外画面要求：'+request:'')};
 }
 if(!record||![2,3].includes(record.version))throw Error('这层尚无随对话生成的画面数据；可等待下一条正常回复，旧楼层可手动选人后点画笔');
 if(record.skip)throw Error(record.reason||'这层没有可绘制内容，已跳过生图');
 const cast=record.cast.map(p=>allowed.find(a=>a.avatar===p.avatar&&a.name===p.name));
 if(cast.some(p=>!p)||cast.length>2||new Set(cast.map(p=>p.avatar)).size!==cast.length)
  throw Error('该楼层头像已不可用，已停止生图');
 return {...record,cast,prompt:record.prompt+(request?'。额外画面要求：'+request:'')};
}
async function avatar(person){
 if(!person.available||!person.avatar||person.avatar.includes('/')||person.avatar.includes('\\'))throw Error(person.name+' 缺少有效头像');
 const path=person.kind==='user'?getUserAvatar(encodeURIComponent(person.avatar)):'/characters/'+encodeURIComponent(person.avatar);
 const old=avatarCache.get(path);if(old&&Date.now()-old.time<60000)return old.data;
 const r=await baseFetch(path);if(!r.ok)throw Error('无法读取 '+person.name+' 的头像');
 const blob=await r.blob();if(blob.size>10*1024*1024)throw Error(person.name+' 的头像超过 10 MB');
 const data=await new Promise((resolve,reject)=>{const f=new FileReader();f.onload=()=>resolve(f.result);f.onerror=reject;f.readAsDataURL(blob)});
 if(avatarCache.size>=8)avatarCache.delete(avatarCache.keys().next().value);
 avatarCache.set(path,{data,time:Date.now()});return data;
}
function ownWorkflow(){return ownsWorkflow(ctx().extensionSettings.sd,connectionSettings(ctx().extensionSettings).url)}
async function chatRequest(input,init,body){
 // Request type is supplied by Tavern itself, including for hidden MVU/quiet
 // jobs. Never add our protocol to those jobs or initiate another chat call.
 if(!ownWorkflow()||!Array.isArray(body.messages)||!['normal','group_chat','swipe','regenerate','impersonate'].includes(body.type))return baseFetch(input,init);
 const userStory=isUserStoryRequest(body,connectionSettings(ctx().extensionSettings).helperPrefix);
 if(userStory&&(!generationFrame||generationFrame.key!==key()||generationFrame.requested))
  generationFrame=newFrame('helper_user_story','user');
 if(!generationFrame||generationFrame.key!==key()||generationFrame.requested)
  return baseFetch(input,init);
 const people=eligible(),frame=generationFrame,startedKey=key();frame.requested=true;
 const protagonist=String(ctx().name1||'').trim().slice(0,100);
 const persona={name:protagonist,avatar:user_avatar};
 const renderSettings=settingsFor(ctx().chatMetadata);
 const nonce=crypto.randomUUID(),capture={frame,key:startedKey,nonce};
 for(const message of body.messages){if(typeof message.content==='string')message.content=stripInline(message.content)}
 body.messages.push({role:'system',content:instruction(people,nonce,protagonist,renderSettings)});
 let response;
 try{response=await baseFetch(input,{...init,body:JSON.stringify(body)})}
 catch(error){
  const parsed=capturePlan({complete:false,finishReason:'request_error'},{people,nonce,protagonist,persona,role:frame.role,type:frame.type,chatKey:startedKey,model:String(body.model||'')});
  parsed.diagnostic.stage='request';parsed.diagnostic.error={name:error.name||'Error',message:String(error.message||error),stack:String(error.stack||'').slice(0,10000)};
  parsed.record.reason=parsed.diagnostic.error.message+'；已跳过生图，不追加对话API';rememberDiagnostic(parsed.diagnostic);
  keepCompleted({...capture,record:parsed.record,story:''});throw error;
 }
 if(!response.ok){
  const parsed=capturePlan({complete:false,finishReason:'HTTP '+response.status},{people,nonce,protagonist,persona,role:frame.role,type:frame.type,chatKey:startedKey,model:String(body.model||'')});
  parsed.diagnostic.stage='request';rememberDiagnostic(parsed.diagnostic);keepCompleted({...capture,record:parsed.record,story:''});return response;
 }
 return filterChatResponse(response,body.stream===true,result=>{
  const parsed=capturePlan(result,{people,nonce,protagonist,persona,role:frame.role,type:frame.type,chatKey:startedKey,model:String(body.model||'')});
  rememberDiagnostic(parsed.diagnostic);
  if(key()!==startedKey||(frame.role!=='user'&&generationFrame!==frame)){
   diagnostics.update(nonce,{status:'discarded',stage:'correlation',error:{name:'GenerationChanged',message:'聊天或当前生成已变化，分镜保留用于诊断，本次不配图',stack:''}});return;
  }
  const record=withRenderSettings(parsed.record,renderSettings);
  keepCompleted({...capture,record,story:result.story});
 });
}
// Existing reply/authoring requests and our loopback workflow are intercepted.
// Native Tavern authentication, provider choice and image saving stay intact.
window.fetch=async(input,init)=>{
 const path=new URL(typeof input==='string'?input:input.url,location.href);
 if(path.origin!==location.origin||typeof init?.body!=='string')return baseFetch(input,init);
 if(path.pathname==='/api/backends/chat-completions/generate')return chatRequest(input,init,JSON.parse(init.body));
 if(path.pathname!=='/api/sd/comfy/generate')return baseFetch(input,init);
 const body=JSON.parse(init.body);let target;try{target=new URL(body.url)}catch{return baseFetch(input,init)}
 if(!ownWorkflow()||!isWorkbenchTarget(target.href,connectionSettings(ctx().extensionSettings).url))return baseFetch(input,init);
 const graph=JSON.parse(body.prompt),nodes=Object.values(graph.prompt||{});
 if(nodes.length!==1||nodes[0]?.class_type!=='MLXAvatarTurbo')return baseFetch(input,init);
 const startedKey=key(),values=nodes[0].inputs;
 const marker=String(values.prompt||'').match(/\[\[MLX_PLAN:([a-f0-9-]+)\]\]/);
 let chosen=marker?plans.get(marker[1]):null;
 if(marker&&!chosen)throw Error('本次生图会话已失效，请重试');
 if(nativeBusy||(busy&&!chosen))throw Error('上一张还在生成，请稍候');
 nativeBusy=true;
 try{
  if(!chosen){
   const anchor=nativeAnchor?.key===key()&&Date.now()-nativeAnchor.time<10000?nativeAnchor:null;nativeAnchor=null;
   chosen=withRenderSettings(savedPlan(anchor?.id??latestId(),anchor?'':String(values.prompt||'')),settingsFor(ctx().chatMetadata));
  }
  chosen=withProtagonistReference(chosen,{name:String(ctx().name1||'').trim(),avatar:user_avatar});
  const references=[...chosen.cast,...(chosen.protagonist_reference?[chosen.protagonist_reference]:[])];
  requireReady(await readHealth(baseFetch,connectionSettings(ctx().extensionSettings).url),references.length>0);
  const images=await Promise.all(references.map(avatar));
  if(key()!==startedKey)throw Error('聊天已切换，本次生图已取消');
  values.avatars=images;values.characters=references.map(c=>c.name);values.reference_roles=references.map(c=>c.kind==='user'?'protagonist':'character');values.prompt=bindPrompt(chosen);
  values.render_mode=references.length?'reference':'text';values.composition=chosen.composition||'default';values.protagonist=chosen.protagonist||'';
  values.scene_type=chosen.scene_type;values.protagonist_present=chosen.protagonist_present;values.panels=chosen.panels;
  values.expression_mode=chosen.expression_mode;
  values.sequence_mode=chosen.sequence_mode;
  values.gaze_mode=chosen.gaze_mode;
  if(chosen.composition==='comic')values.scene_context=chosen.prompt;
  values.width=chosen.width;values.height=chosen.height;values.render_style=chosen.render_settings.style;body.prompt=JSON.stringify(graph);
  status((references.map((c,i)=>`参考图${i+1}：${c.name}`).join('；')||'普通场景，无人物头像')+(chosen.panels?' · '+chosen.panels.length+'格漫画':'')+' · 正在本地生图…');
  const abort=new AbortController();controller=abort;
  const signal=init.signal?AbortSignal.any([init.signal,abort.signal]):abort.signal;
  try{const response=await baseFetch(input,{...init,signal,body:JSON.stringify(body)});if(key()!==startedKey)throw Error('聊天已切换，已忽略本次图片');status(response.ok?'图片已生成 · '+(chosen.cast.map(c=>c.name).join('、')||'普通场景'):'生图失败，请查看工作台日志');return response}
  finally{if(controller===abort)controller=null}
 }catch(e){status(e.message);throw e}finally{nativeBusy=false}
};
async function run(args={},request='',messageId=latestId()){
 if(busy||nativeBusy)throw Error('上一张还在生成，请稍候');
 if(!ownWorkflow())throw Error('请在 MLX Image Workbench 扩展面板点击“应用 MLX 生图配置”');
 const initialKey=key(),started=performance.now(),token=crypto.randomUUID(),source=ctx().chat[messageId],originalText=source?.mes,originalNonce=source?.extra?.mlx_plot_plan?.nonce;busy=true;
 try{
  nativeAnchor=null;
  const plan=withRenderSettings(savedPlan(messageId,request,args.automatic!==true),settingsFor(ctx().chatMetadata));
  const command=ctx().SlashCommandParser.commands.sd;if(!command)throw Error('酒馆图像生成扩展未就绪');
  if(key()!==initialKey)throw Error('聊天已切换，本次生图已取消');plans.set(token,plan);
  // Keep native image-file saving, but attach the image to the source floor
  // ourselves. Native sendMessage would put its full prompt into chat text.
  const url=await command.callback({quiet:'true',extend:'false',edit:'false'},`[[MLX_PLAN:${token}]]`+plan.prompt);
  if(!url)throw Error('生图失败，请查看本地工作台日志');
  if(key()!==initialKey||ctx().chat[messageId]!==source||source.mes!==originalText||source.extra?.mlx_plot_plan?.nonce!==originalNonce)throw Error('剧情楼层已变化，图片保留在图库，本次不插入对话');
  if(String(args.quiet||'false')!=='true'){
   source.extra||={};source.extra.media||=[];
   source.extra.media.push({url,type:MEDIA_TYPE.IMAGE,source:MEDIA_SOURCE.GENERATED,title:(plan.composition==='comic'?'剧情漫画 · ':'剧情配图 · ')+(plan.cast.map(p=>p.name).join('、')||'普通场景'),generation_type:6,width:plan.width,height:plan.height,render_style:plan.render_settings.style});
   source.extra.media_index=source.extra.media.length-1;source.extra.media_display=MEDIA_DISPLAY.GALLERY;source.extra.inline_image=true;
   source.extra.mlx_plot_image_nonce=originalNonce;
   appendMediaToMessage(source,jQuery(`.mes[mesid="${messageId}"]`),SCROLL_BEHAVIOR.KEEP);
   await ctx().saveChat();
  }
  status('完成 · '+(plan.cast.map(c=>c.name).join('、')||'普通场景')+' · '+plan.width+'×'+plan.height+' · '+styleLabel(plan.render_settings)+' · '+Math.round((performance.now()-started)/1000)+' 秒 · 无额外对话API');
  return url;
 }catch(e){status(e.message);throw e}finally{plans.delete(token);busy=false}
}
async function drainAuto(){
 if(autoRunning)return;autoRunning=true;
 try{while(autoQueue.length){if(busy||nativeBusy){setTimeout(()=>drainAuto(),500);break}const entry=autoQueue.shift();
  if(entry.key!==key()||ctx().chatMetadata.mlx_plot_auto!==true||ctx().chat[entry.id]!==entry.message||entry.message.extra?.mlx_plot_plan?.nonce!==entry.nonce||entry.message.extra?.mlx_plot_image_nonce===entry.nonce)continue;
  try{await run({automatic:true},'',entry.id)}catch(e){toastr.warning(e.message,'MLX 剧情配图')}
 }}finally{autoRunning=false}
}
function queueAuto(id){
 const current=ctx(),m=current.chat[id],record=m?.extra?.mlx_plot_plan;
 if(current.chatMetadata.mlx_plot_auto!==true||!m||m.is_system||m.extra?.media?.length||record?.skip!==false||freshPlans.get(m)!==record.nonce)return;
 const identity=key()+':'+id+':'+record.nonce;if(seenAuto.has(identity))return;seenAuto.add(identity);
 if(seenAuto.size>256)seenAuto.delete(seenAuto.values().next().value);
 autoQueue.push({key:key(),id,message:m,nonce:record.nonce});setTimeout(()=>drainAuto(),250);
}
function storePlan(id,record,frame=generationFrame){
 const m=ctx().chat[id];if(!m)return;
 if(m.is_user)record={...record,source_role:'user'};
 m.extra||={};m.extra.mlx_plot_plan=record;
 boundFrames.set(m,frame);
 if(m.swipe_info?.[m.swipe_id]){m.swipe_info[m.swipe_id].extra||={};m.swipe_info[m.swipe_id].extra.mlx_plot_plan=record}
 diagnostics.update(record.diagnostic_id,{message_id:id,message_name:m.name||'',source_role:record.source_role||'assistant'});
 freshPlans.set(m,ctx().chatMetadata.mlx_plot_auto===true?record.nonce:null);
 render();status(record.skip?(record.reason||'本次没有可绘制内容，已跳过生图'):'画面数据已随对话保存 · '+(record.cast.map(p=>p.name).join('、')||'普通场景')+' · '+record.width+'×'+record.height);
 queueAuto(id);
}
async function receiveUser(id){
 const m=ctx().chat[id];if(!m?.is_user||m.is_system)return;
 const at=completed.findLastIndex(entry=>entry.key===key()&&
  (id>=entry.frame.length||(id===entry.frame.length-1&&m.mes!==entry.frame.last))&&matchesUserStory(entry,m));
 if(at<0)return; // Typed text and historical floors have no captured AI reply.
 const entry=completed.splice(at,1)[0];storePlan(id,entry.record,entry.frame);await ctx().saveChat();
}
function initializeConnection(holder){
 const panel=document.createElement('div');panel.innerHTML=`
 <label>本机工作台地址<input id="mlxWorkbenchUrl" class="text_pole" type="url" spellcheck="false"></label>
 <p><button id="mlxWorkbenchTest" class="menu_button">测试连接</button>
 <button id="mlxWorkbenchApply" class="menu_button">应用 MLX 生图配置</button>
 <button id="mlxWorkbenchRestore" class="menu_button">恢复上次生图设置</button></p>
 <p id="mlxWorkbenchConnection" role="status">连接检查中…</p>
 <details><summary>工作流 JSON 与代写兼容</summary>
 <p><a id="mlxWorkbenchWorkflow" download="MLX_Workbench_0.1.0.json">下载工作流 JSON</a></p>
 <label>导入兼容工作流 JSON<input id="mlxWorkbenchImport" type="file" accept=".json,application/json"></label>
 <p id="mlxWorkbenchImportStatus">默认使用扩展自带工作流。导入只暂存；点击“应用”后写入酒馆。</p>
 <label>可选：第三方代写助手的明确请求前缀<input id="mlxWorkbenchHelper" class="text_pole" type="text" maxlength="100" placeholder="留空，仅支持酒馆原生代写"></label>
 <p>原生“代写用户消息”直接支持。手动发送的用户消息不会触发配图。JSON 只定义生图工作流，完整剧情配图需要本扩展。</p></details>
 <p>首次使用需点击“应用”来选择生图来源；已有设置会保存一份供恢复。之后自动使用保存的地址。浏览器不能启动本机 Python，请先双击 启动.command。</p>`;
 holder.insertBefore(panel,holder.children[1]);
 let workflow=structuredClone(DEFAULT_WORKFLOW);
 const url=document.getElementById('mlxWorkbenchUrl'),note=document.getElementById('mlxWorkbenchConnection');
 const settings=connectionSettings(ctx().extensionSettings);url.value=settings.url;
 document.getElementById('mlxWorkbenchHelper').value=settings.helperPrefix;
 document.getElementById('mlxWorkbenchWorkflow').href=new URL('./MLX_Workbench_0.1.0.json',import.meta.url).href;
 const headers=()=>ctx().getRequestHeaders();
 const report=async()=>{note.textContent='正在检查连接…';try{
  const health=await testConnection(baseFetch,headers,url.value);
  note.textContent='已连接 v'+health.version+(health.reference_ready?' · 人物参考已就绪':' · 文字生图已就绪；人物参考组件未安装')+(ownsWorkflow(ctx().extensionSettings.sd,normalizeUrl(url.value))?' · MLX 工作流已启用':' · 点击“应用”后启用 MLX 工作流');
 }catch(e){note.textContent=e.message}};
 document.getElementById('mlxWorkbenchTest').onclick=report;
 document.getElementById('mlxWorkbenchImport').onchange=async e=>{try{
  const file=e.target.files?.[0];if(!file)return;if(file.size>65536)throw Error('工作流 JSON 不能超过 64 KB');
  workflow=validateWorkflow(await file.text());document.getElementById('mlxWorkbenchImportStatus').textContent='已暂存 '+file.name+'；点击“应用”后生效';
 }catch(error){document.getElementById('mlxWorkbenchImportStatus').textContent=error.message;e.target.value=''}};
 document.getElementById('mlxWorkbenchApply').onclick=async e=>{
  e.target.disabled=true;note.textContent='检查连接并保存工作流…';try{
   const result=await applyConfiguration({fetcher:baseFetch,headers,context:ctx(),base:url.value,workflow});
   ctx().extensionSettings[EXTENSION_KEY].helperPrefix=document.getElementById('mlxWorkbenchHelper').value.trim();
   ctx().saveSettingsDebounced();url.value=normalizeUrl(url.value);
   // Use Tavern's own source-change handler to refresh its controls/options.
   jQuery('#sd_comfy_url').val(url.value);jQuery('#sd_comfy_type').val('standard');
   jQuery('#sd_source').val('comfy').trigger('change');
   note.textContent='已应用 '+result.name+'；之前的生图设置已保留，可恢复'+(result.health.reference_ready?'':'。人物参考还需安装额外组件');
  }catch(error){note.textContent=error.message}finally{e.target.disabled=false}
 };
 document.getElementById('mlxWorkbenchRestore').onclick=()=>{try{
  restoreConfiguration(ctx());jQuery('#sd_comfy_url').val(ctx().extensionSettings.sd.comfy_url||'');
  jQuery('#sd_comfy_type').val(ctx().extensionSettings.sd.comfy_type||'standard');
  jQuery('#sd_source').val(ctx().extensionSettings.sd.source);
  note.textContent='已恢复之前的生图设置；刷新酒馆后生效';
 }catch(error){note.textContent=error.message}};
 void report();
}
async function init(){
 const holder=document.createElement('details');holder.id='mlxPlotPanel';holder.className='extension_container';
 holder.innerHTML='<summary><b>MLX Image Workbench · 剧情漫画</b></summary><p>正常对话会同时保存隐藏分镜，不额外调用对话API。按剧情自动安排2～5格；默认16:9、1536×864、彩色写实漫画。分辨率与画风在本聊天保存，之后生图按当前选择执行。</p><label>画面比例<select id="mlxPlotRatio" class="text_pole"></select></label><label>分辨率<select id="mlxPlotResolution" class="text_pole"></select></label><div id="mlxPlotCustomSize" hidden><label>宽度<input id="mlxPlotWidth" class="text_pole" type="number" min="256" max="2560" step="32"></label><label>高度<input id="mlxPlotHeight" class="text_pole" type="number" min="256" max="2560" step="32"></label></div><label>画风<select id="mlxPlotStyle" class="text_pole"></select></label><p id="mlxPlotRenderHint"></p><label>可用头像参考（默认包含当前聊天所有人物；不限制性别）<select id="mlxPlotWomen" multiple size="6" style="width:100%"></select></label><p id="mlxPlotEligibility"></p><label class="checkbox_label"><input id="mlxPlotFoldImages" type="checkbox">折叠聊天中的图片（点每层的“显示图片”可单独展开）</label><label class="checkbox_label"><input id="mlxPlotAuto" type="checkbox">本聊天每次 AI 回复后自动生图</label><p><button id="mlxPlotGenerate" class="menu_button" style="width:100%;white-space:normal">使用最新楼层画面数据生图</button></p><details><summary>旧楼层手动选人</summary><label>手动入镜人物（不选则读取该层画面数据）<select id="mlxPlotCast" multiple size="4" style="width:100%"></select></label><button id="mlxPlotAutoCast" class="menu_button" style="width:100%;white-space:normal">使用楼层人物名单</button></details><p>每页最多两位人物使用头像参考；世界书中没有头像的人物仍可依据正文和世界书描述绘制。头像只约束身份，表情与服装由剧情决定。没有头像时使用文字生图，不能保证与某张未提供的脸一致。主角有用户头像时单独参考。缺失或无效分镜会跳过，不补发对话API。</p><p id="mlxPlotStatus" role="status">就绪 · 同次对话附带分镜 · 16:9</p>';
 document.getElementById('extensions_settings').append(holder);
 const explanation=document.createElement('p');explanation.textContent='支持 AI 代写的用户剧情，图片挂在对应楼层。手动输入不会自动配图。原始分镜与具体错误保存在本地诊断文件。';holder.append(explanation);
 const diagnosticLink=document.createElement('a');diagnosticLink.id='mlxPlotDiagnosticLink';diagnosticLink.textContent='查看分镜诊断记录（原始 JSON）';diagnosticLink.href=diagnostics.url();diagnosticLink.target='_blank';diagnosticLink.rel='noopener';holder.append(diagnosticLink);
 initializeConnection(holder);
 initializeRenderSettings();
 document.getElementById('mlxPlotWomen').onchange=e=>{ctx().chatMetadata.mlx_plot_characters=[...e.target.selectedOptions].map(o=>o.value);ctx().saveMetadataDebounced();manual=[];render()};
 document.getElementById('mlxPlotCast').onchange=e=>{const picked=[...e.target.selectedOptions];if(picked.length>2){toastr.warning('最多选择两位人物');render();return}manual=picked.map(o=>o.value)};
 document.getElementById('mlxPlotAutoCast').onclick=()=>{manual=[];render();status('已恢复使用该楼层的重点人物名单')};
 document.getElementById('mlxPlotAuto').onchange=e=>{ctx().chatMetadata.mlx_plot_auto=e.target.checked;ctx().saveMetadataDebounced();status(e.target.checked?'已启用：下一条符合条件的AI回复后生图':'自动生图已关闭；正常回复仍附带隐藏画面数据，可稍后手动生图')};
 document.getElementById('mlxPlotGenerate').onclick=()=>run().catch(e=>toastr.error(e.message,'MLX 生图'));
 // Capture the actual historic floor before the native delegated paintbrush
 // handler runs. Never substitute the latest story for that floor.
 document.addEventListener('click',e=>{
  const button=e.target.closest?.('.sd_message_gen');if(!button)return;
  const id=Number(button.closest('.mes')?.getAttribute('mesid'));
  if(Number.isInteger(id)&&ctx().chat[id])nativeAnchor={key:key(),id,time:Date.now()};
 },true);
 const c=ctx();c.SlashCommandParser.addCommandObject(c.SlashCommand.fromProps({name:'mlx-image',
  callback:(args,value)=>run(args,String(value||'')),helpString:'读取最新剧情楼层随正常回复保存的画面数据，可参考聊天人物头像或按世界书文字本地生图；不额外调用对话API。',
  namedArgumentList:[c.SlashCommandNamedArgument.fromProps({name:'quiet',description:'不把图片插入聊天',typeList:[c.ARGUMENT_TYPE.BOOLEAN]})]}));
 c.eventSource.on(c.eventTypes.CHAT_CHANGED,()=>{controller?.abort();generationFrame=null;completed.length=0;autoQueue=[];manual=[];nativeAnchor=null;freshPlans=new WeakMap();boundFrames=new WeakMap();render()});
 c.eventSource.on(c.eventTypes.GENERATION_STARTED,(type,_options,dryRun)=>{
  if(dryRun||['quiet','continue'].includes(type))return;
  generationFrame=newFrame(type,type==='impersonate'?'user':'assistant');
 });
 c.eventSource.on('js_generation_requested',(_id,_type,config)=>{
  if(isUserStoryRequest({messages:[{role:'user',content:config?.user_input}]},connectionSettings(ctx().extensionSettings).helperPrefix))generationFrame=newFrame('helper_user_story','user');
 });
 const receive=(id,origin)=>{
  const m=ctx().chat[id];if(m?.is_user){void receiveUser(id);return}
  if(!m||m.is_system||['extension','first_message','quiet','impersonate','continue'].includes(origin)||!generationFrame||generationFrame.key!==key())return;
  if(id<generationFrame.length&&!(id===generationFrame.length-1&&m.mes!==generationFrame.last))return;
  const at=completed.findIndex(r=>r.key===key()&&r.frame===generationFrame);
  if(at<0&&boundFrames.get(m)===generationFrame)return;
  let record;
  if(at>=0)record=completed.splice(at,1)[0].record;
  else{
   const nonce=crypto.randomUUID(),parsed=capturePlan({complete:false,story:m.mes,finishReason:'未收到该楼层的分镜捕获结果'},
    {people:[],nonce,protagonist:ctx().name1||'',persona:{},chatKey:key(),type:generationFrame.type});
   rememberDiagnostic(parsed.diagnostic);record=parsed.record;
  }
  storePlan(id,record);
 };
 (c.eventSource.makeFirst||c.eventSource.on).call(c.eventSource,c.eventTypes.MESSAGE_RECEIVED,receive);
 c.eventSource.on(c.eventTypes.CHARACTER_MESSAGE_RENDERED,(id,origin)=>{if(!['extension','first_message','quiet','continue'].includes(origin))queueAuto(id)});
 for(const event of [c.eventTypes.MESSAGE_SENT,c.eventTypes.USER_MESSAGE_RENDERED,c.eventTypes.MESSAGE_UPDATED].filter(Boolean))
  c.eventSource.on(event,id=>receiveUser(id));
 if(ownWorkflow())diagnostics.retryPending();
 render();
}
await init();
installImageFold({toggle:document.getElementById('mlxPlotFoldImages')});
installPromptHover({selector:'.mes_img, .zoomed_avatar img, .popup img'});
