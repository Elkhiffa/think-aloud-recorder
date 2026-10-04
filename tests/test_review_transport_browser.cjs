'use strict';
// Production review UI, synthetic media and bridge; no user recordings or settings.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),read=p=>fs.readFileSync(path.join(root,p),'utf8');
const output=path.join(root,'work','review-transport');fs.mkdirSync(output,{recursive:true});
const data={title:'合成验证：探索路线与交互反馈',game:'合成示例游戏',created:'2026-10-04T10:00:00',test:true,desktop:true,video:'/demo.mp4',
 activity_details:'NPC 同行与剧情观看 + 地图定位与目标查找 + 战斗挑战与道具使用 + 众生探索线索浏览 + 月亮解谜与交付任务',
 segments:[{start:1,end:5,text:'我想先看看这条路能不能走过去，再确认旁边的入口是否已经开放。',speaker_id:0},{start:7,end:10,text:'刚才这里有个反馈，但我没看清；暂停之后再对照一下。',speaker_id:0}],
 speakers:{available:true,selected_id:0,source:'auto',confidence:'recommended',speakers:[]},transcription:{state:'ready'},
 inputs:{state:'complete',duration:32,recording_scope:'all',timebase:'video_seconds',intervals:[{id:'held',device:'xbox',code:'RB',label:'RB',kind:'button',start:1,end:5},{id:'tap',device:'xbox',code:'A',label:'A',kind:'button',start:1.5,end:1.8}],gaps:[],window_states:[{start:0,end:32,state:'foreground'}]}};
const media=fs.readFileSync(path.join(root,'docs/prototypes/input-review/demo.mp4'));
function html(){const values={TITLE:data.title,DATA:JSON.stringify(data),CSS:read('ui/review.css'),JS:read('ui/review.js'),PLYR_CSS:read('ui/vendor/plyr/plyr.css'),PLYR_JS:read('ui/vendor/plyr/plyr.min.js'),PLYR_SVG:read('ui/vendor/plyr/plyr.svg'),LICENSE:'Synthetic transport verification'};return read('player.html').replace(/%%([A-Z_]+)%%/g,(_,k)=>values[k]);}
const server=http.createServer((req,res)=>{if(req.url==='/demo.mp4'){res.setHeader('Content-Type','video/mp4');res.setHeader('Accept-Ranges','bytes');const range=/^bytes=(\d+)-(\d*)$/.exec(req.headers.range||'');if(range){const start=+range[1],end=Math.min(range[2]?+range[2]:media.length-1,media.length-1);res.writeHead(206,{'Content-Range':`bytes ${start}-${end}/${media.length}`,'Content-Length':end-start+1});res.end(media.subarray(start,end+1));}else res.end(media);return;}res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html());});
const evidence={scope:'Synthetic Edge UI only; native and packaged acceptance reported separately.',checks:[],errors:[]};let browser;
async function check(name,fn){try{evidence.checks.push({name,pass:true,details:await fn()});}catch(e){evidence.checks.push({name,pass:false,error:e.stack});console.error(name,e.stack);}}
async function main(){
 await new Promise(r=>server.listen(0,'127.0.0.1',r));browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1920,height:1080}});page.on('pageerror',e=>evidence.errors.push(e.stack));
 await page.addInitScript(()=>{window.pywebview={api:{ready:async()=>({ok:true}),get_layout:async()=>({ok:true,data:{}}),save_layout:async()=>({ok:true}),get_snapshot:async()=>({ok:true,data:{unchanged:true}}),get_playback_preferences:async()=>({ok:true,data:JSON.parse(localStorage.getItem('test-native-playback')||'{"double_click_fullscreen":true}')}),save_playback_preferences:async value=>{localStorage.setItem('test-native-playback',JSON.stringify({double_click_fullscreen:value}));return {ok:true};}}};});
 await page.goto(`http://127.0.0.1:${server.address().port}/review`);await page.waitForFunction(()=>document.querySelector('video').readyState>=2&&window.reviewPlayer);
 const settle=()=>page.evaluate(async()=>{for(let i=0;i<6;i++)await new Promise(requestAnimationFrame);});
 const seek=async at=>{await page.locator('video').evaluate((v,t)=>{v.pause();v.currentTime=t;v.dispatchEvent(new Event('timeupdate'));},at);await page.waitForFunction(t=>!document.querySelector('video').seeking&&Math.abs(document.querySelector('video').currentTime-t)<.1,at);await settle();};
 await seek(2);
 await check('transport stays below footage and anchors controls at opposite edges',async()=>{
   assert.equal(await page.locator('[data-plyr=rewind],[data-plyr=fast-forward],.plyr__control--overlaid').count(),0);
   const result=await page.evaluate(()=>{const rect=s=>document.querySelector(s).getBoundingClientRect().toJSON();return {picture:rect('.plyr__video-wrapper'),controls:rect('.plyr__controls'),play:rect('[data-plyr=play]'),time:rect('.plyr__time--current'),volume:rect('.plyr__volume'),speed:rect('#playbackSpeed'),settings:rect('#playbackSettings')};});
   assert.ok(result.controls.top>=result.picture.bottom-1);assert.ok(result.time.left>=result.play.right);assert.ok(result.volume.left>result.controls.left+result.controls.width/2);assert.ok(result.settings.left>result.speed.left);
   await page.locator('[data-plyr=play]').click();await page.mouse.move(0,0);await page.waitForTimeout(2400);
   assert.equal(await page.locator('.plyr__controls').evaluate(e=>getComputedStyle(e).opacity),'1');await seek(2);return result;
 });
 await check('spoken words remain under the video across tabs and retain a labeled previous quote in silence',async()=>{
   assert.equal(await page.locator('#currentQuoteText').textContent(),data.segments[0].text);
   await page.locator('#transcriptTab').click();assert.equal(await page.locator('#currentQuotePanel').isVisible(),true);
   await seek(6);assert.equal(await page.locator('#currentQuoteLabel').textContent(),'上一句');assert.equal(await page.locator('#currentQuoteTime').textContent(),'00:00:01');
   await seek(8);assert.equal(await page.locator('#currentQuoteText').textContent(),data.segments[1].text);
   await page.locator('#inputTab').click();await seek(2);
   const before=await page.locator('video').boundingBox();for(const mode of ['device','collapsed','keys']){await page.locator(`[data-input-mode=${mode}]`).click();await settle();const after=await page.locator('video').boundingBox();assert.ok(Math.abs(before.height-after.height)<1);}
   assert.equal(await page.locator('#status').textContent(),'');
 });
 await check('speed is direct; gear contains only double-click fullscreen; clicks toggle once',async()=>{
   await page.locator('#playbackSpeed').click();await page.locator('[data-rate="1.5"]').click();await page.waitForFunction(()=>document.querySelector('video').playbackRate===1.5);assert.equal(await page.locator('#playbackSpeed').textContent(),'1.5×');
   await page.locator('#playbackSettings').click();assert.equal(await page.locator('#playbackSettingsMenu button').count(),1);await page.locator('#doubleClickFullscreen').click();assert.equal(await page.locator('#doubleClickFullscreen').getAttribute('aria-checked'),'false');
   await page.keyboard.press('Escape');await seek(2);
   await page.locator('.plyr__video-wrapper').dblclick();await page.waitForTimeout(350);assert.equal(await page.locator('video').evaluate(v=>v.paused),false);assert.equal(await page.evaluate(()=>!!document.fullscreenElement),false);
   await page.locator('.plyr__video-wrapper').dblclick();await page.waitForTimeout(350);assert.equal(await page.locator('video').evaluate(v=>v.paused),true);
   await page.reload();await page.waitForFunction(()=>document.querySelector('video').readyState>=2);assert.equal(await page.locator('#doubleClickFullscreen').getAttribute('aria-checked'),'false');
   await page.locator('#playbackSettings').click();await page.locator('#doubleClickFullscreen').click();await page.keyboard.press('Escape');await seek(2);
   await page.locator('.plyr__video-wrapper').dblclick();await page.waitForFunction(()=>!!document.fullscreenElement);assert.equal(await page.locator('video').evaluate(v=>v.paused),true);
   await page.locator('[data-plyr=fullscreen]').click();await page.waitForFunction(()=>!document.fullscreenElement);await seek(2);
 });
 await check('responsive geometry, full metadata width, quiet compact companion, retained quote hover',async()=>{
   const results=[];
   for(const viewport of [{width:1920,height:1080},{width:1280,height:800},{width:960,height:720},{width:560,height:800}]){
     await page.setViewportSize(viewport);await settle();const g=await page.evaluate(()=>{const rect=s=>document.querySelector(s).getBoundingClientRect().toJSON();return {viewport:innerWidth,overflow:document.documentElement.scrollWidth,video:rect('.plyr__video-wrapper'),bar:rect('.plyr__controls'),companion:rect('#reviewCompanion'),quote:rect('#currentQuotePanel'),input:rect('#inputPanel'),session:rect('.review-session'),details:rect('#sessionContent'),pane:rect('#videoPane'),sidebar:rect('#transcriptPane')};});
     assert.ok(g.overflow<=g.viewport);assert.ok(g.video.height>=48,'picture remains usable');assert.ok(g.bar.top>=g.video.bottom-1);assert.ok(g.companion.top>=g.bar.bottom-1);assert.ok(g.companion.bottom<=g.pane.bottom+1);assert.ok(Math.abs(g.details.width-g.session.width)<1);assert.ok(g.input.height<=176);
     if(g.companion.width>700)assert.ok(Math.abs(g.quote.top-g.input.top)<1);else assert.ok(g.input.top>=g.quote.bottom);
     await page.screenshot({path:path.join(output,`review-${viewport.width}.png`)});results.push(g);
   }
   await page.setViewportSize({width:1280,height:800});await settle();await page.locator('#themeButton').click();await page.waitForTimeout(300);await page.screenshot({path:path.join(output,'review-dark.png')});
   const quote=page.locator('[data-quote="0"]');await quote.hover();await page.waitForFunction(()=>!document.querySelector('#quotePopover').hidden);assert.equal(await page.locator('#quoteText').textContent(),data.segments[0].text);
   return results;
 });
 await check('all visible padding, margins and gaps use the specified spacing scale',async()=>{
   const violations=await page.evaluate(()=>{const allowed=new Set([0,4,8,16,24,32,40]),bad=[];for(const el of document.body.querySelectorAll('*')){if(!el.getClientRects().length||el.closest('svg')||getComputedStyle(el).visibility==='hidden')continue;const s=getComputedStyle(el);for(const prop of ['marginTop','marginRight','marginBottom','marginLeft','paddingTop','paddingRight','paddingBottom','paddingLeft','rowGap','columnGap']){const val=s[prop];if(val.endsWith('px')&&!allowed.has(parseFloat(val)))bad.push({element:el.id||el.className,prop,value:val});}}return bad;});
   assert.deepEqual(violations,[]);return violations;
 });
 assert.deepEqual(evidence.errors,[]);
}
main().catch(e=>{evidence.errors.push(e.stack);console.error(e.stack);process.exitCode=1;}).finally(async()=>{fs.writeFileSync(path.join(output,'result.json'),JSON.stringify(evidence,null,2));if(evidence.checks.some(c=>!c.pass)||evidence.errors.length)process.exitCode=1;await browser?.close();server.close();console.log(JSON.stringify({checks:evidence.checks.map(({name,pass})=>({name,pass})),errors:evidence.errors}));});
