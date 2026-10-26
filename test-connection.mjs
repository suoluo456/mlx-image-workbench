import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import {DEFAULT_URL,DEFAULT_WORKFLOW,EXTENSION_KEY,WORKFLOW_NAME,normalizeUrl,connectionSettings,
    ownsWorkflow,validateWorkflow,readHealth,requireReady,testConnection,applyConfiguration,restoreConfiguration} from './connection.mjs';
import {bindPrompt} from './planner.mjs';
import {isUserStoryRequest} from './plan-capture.mjs';
import {createTextFilter} from './inline-plan.mjs';
import {createDiagnosticWriter} from './diagnostics.mjs';
const ready={app:'mlx-image-workbench',version:'0.1.0',tavern_enabled:true,models:[{id:'qwen21_turbo',ready:true}],reference_ready:true};
const response=value=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
function harness({health=ready,names=[],stored='',saveFails=false}={}){
 const calls=[],before={source:'auto',url:'http://localhost:9000',steps:23,model:'my-model'};
 const context={extensionSettings:{sd:structuredClone(before)},saves:0,saveSettingsDebounced(){this.saves++}};
 const fetcher=async(url,init)=>{
  calls.push({url,init});
  if(url.endsWith('/api/health'))return response(health);
  if(url.endsWith('/ping'))return new Response('OK');
  if(url.endsWith('/workflows'))return response(names);
  if(url.endsWith('/workflow'))return response(stored);
  if(url.endsWith('/save-workflow'))return saveFails?new Response('',{status:500}):response([...names,JSON.parse(init.body).file_name]);
  throw Error('Unexpected network request '+url);
 };
 return {calls,before,context,fetcher,headers:()=>({'Content-Type':'application/json','X-CSRF-Token':'test-only'})};
}
test('default URL is isolated from the private workbench',()=>{
 assert.equal(connectionSettings({}).url,'http://127.0.0.1:7866');
 assert.equal(normalizeUrl('http://localhost:9001/'),'http://localhost:9001');
 for(const input of ['https://example.com','http://127.0.0.1:7866/path','http://u:p@localhost','file:///tmp/a','http://localhost/?token=x'])
  assert.throws(()=>normalizeUrl(input));
});
test('only this configured MLX workflow is intercepted',()=>{
 const sd={source:'comfy',comfy_url:DEFAULT_URL,comfy_workflow:WORKFLOW_NAME};
 assert.equal(ownsWorkflow(sd,DEFAULT_URL),true);
 for(const altered of [{comfy_url:'http://127.0.0.1:8188'},{comfy_workflow:'Other.json'},{source:'auto'},{comfy_type:'runpod_serverless'}])
  assert.equal(ownsWorkflow({...sd,...altered},DEFAULT_URL),false);
});
test('bundled workflow is neutral and matches its module',async()=>{
 const file=JSON.parse(await readFile(new URL('./MLX_Workbench_0.1.0.json',import.meta.url),'utf8'));
 assert.deepEqual(validateWorkflow(file),validateWorkflow(DEFAULT_WORKFLOW));
 assert.equal(file['1'].inputs.render_mode,'text');
});
test('workflow import rejects arbitrary nodes and embedded references',()=>{
 assert.throws(()=>validateWorkflow({'1':{class_type:'KSampler',inputs:{}}}));
 const bad=structuredClone(DEFAULT_WORKFLOW);bad['1'].inputs.avatars=['private-avatar'];
 assert.throws(()=>validateWorkflow(bad));
 assert.throws(()=>validateWorkflow({...DEFAULT_WORKFLOW,'2':DEFAULT_WORKFLOW['1']}));
});
test('health identifies the correct app and reports missing components',async()=>{
 await assert.rejects(()=>readHealth(async()=>response({app:'other'}),DEFAULT_URL),/不是/);
 assert.throws(()=>requireReady({...ready,tavern_enabled:false}),/启用酒馆/);
 assert.throws(()=>requireReady({...ready,models:[]}),/下载完整/);
 assert.throws(()=>requireReady({...ready,reference_ready:false},true),/人物参考/);
 assert.equal(requireReady({...ready,reference_ready:false},false).reference_ready,false);
});
test('testing connection never changes generation settings',async()=>{
 const h=harness();await testConnection(h.fetcher,h.headers,DEFAULT_URL);
 assert.deepEqual(h.context.extensionSettings.sd,h.before);assert.equal(h.context.saves,0);
 assert.deepEqual(h.calls.map(x=>x.url),[DEFAULT_URL+'/api/health','/api/sd/comfy/ping']);
});
test('apply uses native workflow proxy and preserves original settings',async()=>{
 const h=harness();const applied=await applyConfiguration({...h,base:DEFAULT_URL});
 assert.equal(applied.name,WORKFLOW_NAME);assert.equal(h.context.extensionSettings.sd.source,'comfy');
 assert.deepEqual(h.context.extensionSettings[EXTENSION_KEY].previousSd,h.before);
 const save=h.calls.find(x=>x.url.endsWith('/save-workflow'));assert.equal(JSON.parse(save.init.body).file_name,WORKFLOW_NAME);
 assert.equal(save.init.headers['X-CSRF-Token'],'test-only');
 restoreConfiguration(h.context);assert.deepEqual(h.context.extensionSettings.sd,h.before);
});
test('reapplying a new port keeps the first settings backup',async()=>{
 const h=harness();await applyConfiguration({...h,base:DEFAULT_URL});
 await applyConfiguration({...h,base:'http://127.0.0.1:9001'});
 assert.deepEqual(h.context.extensionSettings[EXTENSION_KEY].previousSd,h.before);
 restoreConfiguration(h.context);assert.deepEqual(h.context.extensionSettings.sd,h.before);
});
test('changed existing workflow is preserved under a fresh name',async()=>{
 const h=harness({names:[WORKFLOW_NAME],stored:JSON.stringify({'1':{class_type:'Other'}})});
 const applied=await applyConfiguration({...h,base:DEFAULT_URL});
 assert.equal(applied.name,'MLX_Workbench_0.1.0_2.json');
});
test('same workflow is reused without an unnecessary write',async()=>{
 const h=harness({names:[WORKFLOW_NAME],stored:JSON.stringify(DEFAULT_WORKFLOW)});
 await applyConfiguration({...h,base:DEFAULT_URL});
 assert.equal(h.calls.some(x=>x.url.endsWith('/save-workflow')),false);
});
test('failed connection or workflow write leaves settings intact',async()=>{
 for(const options of [{health:{...ready,tavern_enabled:false}},{saveFails:true}]){
  const h=harness(options);await assert.rejects(()=>applyConfiguration({...h,base:DEFAULT_URL}));
  assert.deepEqual(h.context.extensionSettings.sd,h.before);assert.equal(h.context.saves,0);
 }
});
test('native impersonation is recognized without a private phrase',()=>{
 assert.equal(isUserStoryRequest({type:'impersonate'}),true);
 assert.equal(isUserStoryRequest({messages:[{role:'user',content:'ordinary input'}]}),false);
 assert.equal(isUserStoryRequest({messages:[{role:'user',content:'WRITE_AS_USER: continue'}]},'WRITE_AS_USER:'),true);
 assert.equal(isUserStoryRequest({messages:[{role:'user',content:'unrelated'}]},'WRITE_AS_USER:'),false);
});
test('hidden plan stays outside visible chat even across streamed chunks',()=>{
 const filter=createTextFilter();let visible='';
 for(const chunk of ['Story <mlx_','image_plan>{"nonce":"x"}</mlx_image_','plan> end'])visible+=filter.push(chunk);
 visible+=filter.finish();assert.equal(visible,'Story  end');assert.deepEqual(filter.payloads,['{"nonce":"x"}']);
});
test('diagnostics uses configured endpoint and its own cache namespace',async()=>{
 const calls=[],cache=new Map();let base='http://localhost:9001';
 const storage={setItem:(k,v)=>cache.set(k,v),getItem:k=>cache.get(k),removeItem:k=>cache.delete(k),get length(){return cache.size},key:i=>[...cache.keys()][i]};
 const writer=createDiagnosticWriter(async(url)=>{calls.push(url);return response({ok:true})},storage,()=>base);
 writer.save({id:'case-1'});assert.ok([...cache.keys()][0].startsWith('mlxWorkbenchDiagnosticPending:'));
 await new Promise(resolve=>setImmediate(resolve));assert.equal(calls[0],base+'/api/tavern/diagnostics');
 base='http://localhost:9002';assert.equal(writer.url(),base+'/api/tavern/diagnostics?id=case-1');
});

test('character prompts do not force a gender',()=>{
 const prompt=bindPrompt({composition:'interaction',cast:[{name:'Alex'}],protagonist:'Player',prompt:'They exchange a book.'});
 assert.ok(prompt.includes('Alex'));assert.ok(!/女性|女人|女方/.test(prompt));
});
