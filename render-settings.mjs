// Same levels/ratio calculation as the workbench's reference-image mode.
export const SETTINGS_KEY='mlx_plot_render_settings_v1';
export const LEVELS=[{edge:512,name:'试跑'},{edge:768,name:'小图'},{edge:1280,name:'常用'},{edge:1920,name:'全高清'},{edge:2560,name:'2K'}];
export const RATIOS=[['2:3','2:3 竖图'],['3:2','3:2 横图'],['16:9','16:9 宽屏'],['9:16','9:16 手机'],['1:1','1:1 方图'],['4:3','4:3 横图'],['3:4','3:4 竖图'],['custom','自定义']];
export const STYLES=[['iphone','高清真实 iPhone 拍摄'],['japanese','日式写真'],['default','默认风格（当前彩色写实漫画）'],['manhwa','韩漫风格']];
export function normalizeSettings(value={}){
    if(!value||typeof value!=='object')value={};
    const aspectRatio=RATIOS.some(([id])=>id===value.aspectRatio)?value.aspectRatio:'16:9';
    const level=Number.isInteger(value.level)&&value.level>=0&&value.level<LEVELS.length?value.level:2;
    const style=STYLES.some(([id])=>id===value.style)?value.style:'default';
    const align=n=>Math.max(256,Math.min(2560,Math.round((Number(n)||1024)/32)*32));
    let width=align(value.width),height=align(value.height);
    if(aspectRatio!=='custom'){
        const [a,b]=aspectRatio.split(':').map(Number);
        const scale=Math.min(Math.floor(2560/(32*Math.max(a,b))),Math.max(1,Math.round(LEVELS[level].edge/(32*Math.max(a,b)))))*32;
        width=a*scale;height=b*scale;
    }
    return {aspectRatio,level,style,width,height};
}
export const settingsFor=metadata=>normalizeSettings(metadata?.[SETTINGS_KEY]);
export const styleLabel=settings=>STYLES.find(([id])=>id===settings.style)?.[1]||STYLES[2][1];
export const aspectLabel=settings=>settings.aspectRatio==='custom'?`${settings.width}:${settings.height}`:settings.aspectRatio;
export function withRenderSettings(plan,settings){
    const selected=normalizeSettings(settings);
    return {...plan,width:selected.width,height:selected.height,render_settings:selected};
}
