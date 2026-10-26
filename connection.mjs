export const DEFAULT_URL = 'http://127.0.0.1:7866';
export const EXTENSION_KEY = 'mlx_image_workbench';
export const WORKFLOW_NAME = 'MLX_Workbench_0.1.0.json';
export const DEFAULT_WORKFLOW = Object.freeze({'1': {class_type: 'MLXAvatarTurbo', inputs: {
    prompt: '%prompt%', render_mode: 'text', avatars: [], characters: [], width: '%width%', height: '%height%', seed: '%seed%',
}}});

export function normalizeUrl(value = DEFAULT_URL) {
    let url;
    try { url = new URL(String(value).trim()); } catch { throw Error('请输入完整地址，例如 '+DEFAULT_URL); }
    if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname)
        || url.username || url.password || !['', '/'].includes(url.pathname) || url.search || url.hash)
        throw Error('当前仅支持同一台 Mac 的 http://127.0.0.1:端口 或 http://localhost:端口');
    return url.origin;
}
export function connectionSettings(settings) {
    const saved = settings?.[EXTENSION_KEY] || {};
    return {url: normalizeUrl(saved.url || DEFAULT_URL), helperPrefix: String(saved.helperPrefix || '').trim().slice(0, 100)};
}
export function isWorkbenchTarget(candidate, expected) {
    try { return normalizeUrl(candidate) === normalizeUrl(expected); } catch { return false; }
}
export function ownsWorkflow(sd, expected) {
    return sd?.source === 'comfy' && (!sd.comfy_type || sd.comfy_type === 'standard')
        && /^MLX_Workbench_[\w.-]+\.json$/.test(String(sd.comfy_workflow || ''))
        && isWorkbenchTarget(sd.comfy_url, expected);
}
export function validateWorkflow(input) {
    const value = typeof input === 'string' ? JSON.parse(input) : input;
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('工作流必须是 JSON 对象');
    const nodes = Object.values(value);
    if (nodes.length !== 1 || nodes[0]?.class_type !== 'MLXAvatarTurbo')
        throw Error('请选择本扩展的单节点 MLXAvatarTurbo 工作流；普通 ComfyUI 节点图不能在此运行');
    const data = nodes[0].inputs;
    if (!data || typeof data !== 'object' || Array.isArray(data) || data.prompt !== '%prompt%'
        || data.width !== '%width%' || data.height !== '%height%' || data.seed !== '%seed%'
        || !Array.isArray(data.avatars) || data.avatars.length || !Array.isArray(data.characters) || data.characters.length)
        throw Error('请保留 prompt/width/height/seed 占位符，并清空 avatars 与 characters');
    const graph=structuredClone(value);
    Object.values(graph)[0].inputs.render_mode='text';
    return graph;
}
export async function readHealth(fetcher, base) {
    let response;
    try { response = await fetcher(normalizeUrl(base)+'/api/health', {signal: AbortSignal.timeout(6000), cache: 'no-store'}); }
    catch { throw Error('无法连接工作台。请先启动同一台 Mac 的 启动.command，并检查地址和端口'); }
    if (!response.ok) throw Error('工作台检查失败：HTTP '+response.status);
    const health = await response.json();
    if (health.app !== 'mlx-image-workbench' || typeof health.version !== 'string')
        throw Error('此地址不是 MLX Image Workbench，请检查端口');
    return health;
}
export function requireReady(health, references = false) {
    if (!health.tavern_enabled) throw Error('工作台尚未启用酒馆支持，请重新运行安装脚本并启用可选酒馆组件');
    if (!health.models?.some(model => model.id === 'qwen21_turbo' && model.ready))
        throw Error('Qwen-Image-2.1 Turbo 尚未下载完整；请在安装脚本中选择 Qwen Turbo');
    if (references && !health.reference_ready)
        throw Error('人物参考组件尚未安装；请在安装脚本中启用酒馆/人物参考组件后再试');
    return health;
}
async function post(fetcher, headers, route, body) {
    const result = await fetcher('/api/sd/comfy/'+route, {method:'POST', headers:headers(),
        body:JSON.stringify(body), signal:AbortSignal.timeout(10000)});
    if (!result.ok) throw Error('酒馆 ComfyUI 接口 '+route+' 返回 HTTP '+result.status+'；请启用内置图像生成扩展');
    return result;
}
export async function testConnection(fetcher, headers, base) {
    const health = await readHealth(fetcher, base);
    requireReady(health);
    await post(fetcher, headers, 'ping', {url:normalizeUrl(base)});
    return health;
}
export async function applyConfiguration({fetcher, headers, context, base, workflow = DEFAULT_WORKFLOW}) {
    const url = normalizeUrl(base), graph = validateWorkflow(workflow);
    // No existing generation setting changes before both connection checks pass.
    const health = await testConnection(fetcher, headers, url);
    if (!context.extensionSettings.sd) throw Error('请先启用酒馆内置图像生成扩展');
    const names = await (await post(fetcher, headers, 'workflows', {})).json();
    if (!Array.isArray(names)) throw Error('酒馆工作流列表格式不兼容');
    let name = WORKFLOW_NAME, suffix = 2, save = true;
    while (names.includes(name)) {
        const stored = await (await post(fetcher, headers, 'workflow', {file_name:name})).json();
        try { if (JSON.stringify(JSON.parse(stored)) === JSON.stringify(graph)) { save = false; break; } } catch {}
        name = WORKFLOW_NAME.replace('.json', '_'+(suffix++)+'.json');
    }
    if (save) await post(fetcher, headers, 'save-workflow', {file_name:name, workflow:JSON.stringify(graph, null, 2)});
    const settings = context.extensionSettings;
    settings[EXTENSION_KEY] ||= {};
    // Reapplying the extension must not replace the user's original backup.
    if (!settings[EXTENSION_KEY].previousSd)
        settings[EXTENSION_KEY].previousSd = structuredClone(settings.sd);
    settings[EXTENSION_KEY].url = url;
    Object.assign(settings.sd, {source:'comfy', comfy_type:'standard', comfy_url:url, comfy_workflow:name,
        steps:8, scale:1, model:null, sampler:null, scheduler:null, vae:null});
    context.saveSettingsDebounced();
    return {name, health};
}
export function restoreConfiguration(context) {
    const saved = context.extensionSettings[EXTENSION_KEY];
    if (!saved?.previousSd) throw Error('还没有可恢复的设置');
    const target=context.extensionSettings.sd;
    for (const key of Object.keys(target)) delete target[key];
    Object.assign(target, saved.previousSd);
    delete saved.previousSd;
    context.saveSettingsDebounced();
}
