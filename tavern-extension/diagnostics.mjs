import {DEFAULT_URL,normalizeUrl} from './connection.mjs?v=0.1.0';
const PREFIX='mlxWorkbenchDiagnosticPending:';

export function createDiagnosticWriter(fetchLocal, storage, getBase = () => DEFAULT_URL) {
    if(storage===undefined){try{storage=globalThis.localStorage}catch{}}
    const endpoint=()=>normalizeUrl(getBase())+'/api/tavern/diagnostics';
    const documents=new Map();let latest=null;
    const cache=doc=>{try{storage?.setItem(PREFIX+doc.id,JSON.stringify(doc))}catch(error){console.warn('MLX 分镜诊断暂存失败',error)}};
    const persist=doc=>{
        const snapshot=JSON.stringify(doc);cache(doc);
        Promise.resolve().then(()=>fetchLocal(endpoint(),{method:'POST',headers:{'Content-Type':'application/json'},body:snapshot}))
            .then(response=>{if(!response.ok)throw Error('诊断落盘失败：HTTP '+response.status);return response.json()})
            .then(()=>{try{if(storage?.getItem(PREFIX+doc.id)===snapshot)storage.removeItem(PREFIX+doc.id)}catch{}})
            .catch(error=>console.warn('MLX 分镜诊断暂存浏览器，工作台恢复后会补存',error.message));
    };
    function save(document) {
        const old=documents.get(document.id);
        const doc={...document,revision:(old?.revision||0)+1,updated_at:new Date().toISOString()};
        documents.set(doc.id,doc);if(documents.size>32)documents.delete(documents.keys().next().value);
        latest=doc.id;persist(doc);return doc.id;
    }
    function update(id,fields) {const old=documents.get(id);if(old)save({...old,...fields})}
    function retryPending() {
        try{for(let i=0;i<(storage?.length||0);i++){
            const key=storage.key(i);if(!key?.startsWith(PREFIX))continue;
            const doc=JSON.parse(storage.getItem(key));documents.set(doc.id,doc);persist(doc);
        }}catch(error){console.warn('MLX 分镜诊断补存失败',error.message)}
    }
    return {save,update,retryPending,url:()=>latest?endpoint()+'?id='+encodeURIComponent(latest):endpoint()};
}
