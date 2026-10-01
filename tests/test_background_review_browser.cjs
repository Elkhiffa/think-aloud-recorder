'use strict';
// Synthetic window ownership, real production UI and media. No actual capture.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const crypto=require('node:crypto'),{execFileSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),read=file=>fs.readFileSync(path.join(root,file),'utf8');
const out=process.env.TAR_BACKGROUND_OUTPUT||path.join(root,'work','background-review');fs.mkdirSync(out,{recursive:true});
const sourceIdentity={head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),files:Object.fromEntries(['ui/review.js','ui/review.css','player.html','tests/test_background_review_browser.cjs'].map(file=>[file,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')]))};
const press=(id,code,start,end,extra={})=>({id,device:'xbox',kind:'button',code,start,end,...extra});
const inputs={version:1,state:'complete',recording_scope:'all',duration:32,timebase:'video_seconds',window_states:[
 {start:0,end:3,state:'foreground'},{start:3,end:7,state:'background'},{start:7,end:9,state:'unknown'},{start:9,end:32,state:'foreground'}],
 gaps:[{start:8.2,end:8.8,type:'capture',reason:'合成采集缺口'}],intervals:[
 press('through','E',1,12,{device:'keyboard'}),press('bg-tap','A',4.1,4.2),press('unknown-tap','Y',7.3,7.4),press('fg-tap','X',2,2.1),
 press('direction','W',1.1,11,{device:'keyboard'}),
 press('pointing','RightStick',1.2,11,{kind:'axis',direction:'→',value:.5,x:.5,y:0}),
 press('dpad-1','DPadUp',2.5,3.5),press('dpad-2','DPadDown',3.8,3.9),press('dpad-3','DPadRight',4.2,4.3),
 ...Array.from({length:9},(_,i)=>press('dense-'+i,'F'+(i+1),6+i*.01,6.15+i*.01,{device:'keyboard'}))
]};
const data={title:'后台操作区域 · 合成验收',game:'合成测试',session_name:'后台操作区域 · 合成验收',desktop:true,test:true,video:'/demo.mp4',segments:[{start:3.2,end:5.5,text:'这段原话在后台区间中，文字和气泡保持正常可读。'}],transcription:{state:'ready'},inputs};
const media=fs.readFileSync(path.join(root,'docs/prototypes/input-review/demo.mp4'));
const values={TITLE:data.title,DATA:JSON.stringify(data),CSS:read('ui/review.css'),JS:read('ui/review.js'),PLYR_CSS:read('ui/vendor/plyr/plyr.css'),PLYR_JS:read('ui/vendor/plyr/plyr.min.js'),PLYR_SVG:read('ui/vendor/plyr/plyr.svg'),LICENSE:'Synthetic browser acceptance'};
const html=read('player.html').replace(/%%([A-Z_]+)%%/g,(_,key)=>values[key]);
const server=http.createServer((request,response)=>{if(request.url==='/demo.mp4'){response.setHeader('Content-Type','video/mp4');response.setHeader('Accept-Ranges','bytes');const range=/^bytes=(\d+)-(\d*)$/.exec(request.headers.range||'');if(range){const start=+range[1],end=Math.min(range[2]?+range[2]:media.length-1,media.length-1);response.writeHead(206,{'Content-Range':`bytes ${start}-${end}/${media.length}`,'Content-Length':end-start+1});response.end(media.subarray(start,end+1));}else response.end(media);return;}response.setHeader('Content-Type','text/html; charset=utf-8');response.end(html);});
const checks=[],errors=[];let browser;
const check=async(name,fn)=>{try{await fn();checks.push({name,pass:true});}catch(error){checks.push({name,pass:false,error:error.stack});console.error(name,error.stack);}};
async function main(){
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));browser=await chromium.launch({headless:true,channel:'msedge'});
 const page=await browser.newPage({viewport:{width:1600,height:960}});page.on('pageerror',error=>errors.push(error.message));
 await page.addInitScript(snapshot=>{window.__snapshot=snapshot;window.pywebview={api:{get_layout:async()=>({ok:true,data:{}}),save_layout:async()=>({ok:true}),ready:async()=>({ok:true}),get_snapshot:async()=>({ok:true,data:window.__snapshot})}};},data);
 await page.goto(`http://127.0.0.1:${server.address().port}/`);await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
 const settle=()=>page.evaluate(async()=>{await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);});
 const seek=async time=>{await page.locator('video').evaluate((v,t)=>{v.currentTime=t;},time);await page.waitForFunction(t=>!document.querySelector('video').seeking&&Math.abs(document.querySelector('video').currentTime-t)<.01,time);await settle();};
 const playback=()=>page.locator('video').evaluate(v=>({time:v.currentTime,paused:v.paused,rate:v.playbackRate}));
 const mask=id=>page.locator(`[data-input-id="${id}"]`).evaluate(el=>getComputedStyle(el).maskImage);
 await seek(5);await page.waitForFunction(()=>document.querySelector('#timelineWindowStates .background'));
 await check('states and capture gaps are separate, exact regions; source facts preserved',async()=>{
   const regions=await page.locator('.timeline-window-band').evaluateAll(els=>els.map(el=>({state:el.dataset.windowState,start:+el.dataset.start,end:+el.dataset.end})));
   assert.deepEqual(regions,[{state:'background',start:3,end:7},{state:'unknown',start:7,end:9}]);
   assert.equal(await page.locator('#timelineGaps .timeline-gap').count(),1);assert.equal(await page.locator('[data-input-id="through"]').count(),1);
   assert.equal(await page.locator('[data-input-id="through"]').getAttribute('data-end'),'12');
   assert.deepEqual(await page.evaluate(()=>window.__snapshot.inputs),inputs);
   assert.match(await page.locator('.timeline-window-labels').textContent(),/游戏在后台.*窗口状态未知/);
 });
 await check('only background intersections fade across ordinary and fixed input tracks',async()=>{
   assert.match(await mask('through'),/0\.75/);assert.match(await mask('direction'),/0\.75/);assert.match(await mask('pointing'),/0\.75/);assert.match(await mask('dpad-1'),/0\.75/);
   assert.match(await mask('bg-tap'),/0\.75/);assert.equal(await mask('fg-tap'),'none');assert.equal(await mask('unknown-tap'),'none');
   assert.equal(await page.locator('.quote-bar').evaluate(el=>getComputedStyle(el).maskImage),'none');
   const layers=await page.evaluate(()=>Object.fromEntries(['.timeline-window-states','.timeline-ticks','.timeline-inputs','.timeline-playhead'].map(s=>[s,+getComputedStyle(document.querySelector(s)).zIndex])));
   assert.ok(layers['.timeline-window-states']<layers['.timeline-ticks']);assert.ok(layers['.timeline-ticks']<layers['.timeline-inputs']);assert.ok(layers['.timeline-inputs']<layers['.timeline-playhead']);
 });
 for(const theme of ['light','dark'])await check(`${theme} theme readable labels outside input and speech columns`,async()=>{
   if(await page.locator('html').getAttribute('data-theme')!==theme)await page.locator('#themeButton').click();await settle();
   const geometry=await page.evaluate(()=>({label:document.querySelector('.timeline-window-label').getBoundingClientRect().toJSON(),speech:document.querySelector('.quote-bar').getBoundingClientRect().toJSON(),playhead:document.querySelector('#timelinePlayhead').getBoundingClientRect().toJSON()}));
   assert.ok(geometry.label.right<=geometry.speech.left);await page.screenshot({path:path.join(out,`background-${theme}.png`)});
 });
 await check('hover still describes original hold and background status; quote pin is unobstructed',async()=>{
   const item=page.locator('[data-input-id="through"]'),box=await item.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+(4.5-1)*32);await settle();
   assert.match(await page.locator('#inputDetail').textContent(),/长按 11\.00 秒/);assert.match(await page.locator('#inputDetail').textContent(),/游戏在后台/);
   await page.locator('.quote-bar').click();assert.equal(await page.locator('#quotePopover').isVisible(),true);await page.locator('#quoteClose').click();
 });
 await check('foreground filter changes only display; unknown never becomes background',async()=>{
   const before=await playback();await page.locator('#inputScope').selectOption('foreground');await settle();assert.equal(await page.locator('[data-input-id="bg-tap"]').count(),0);
   assert.equal(await page.locator('[data-input-id^="through@"]').count(),2);assert.deepEqual(await playback(),before);
   await page.locator('#inputScope').selectOption('all');await settle();assert.equal(await page.locator('[data-input-id="through"]').count(),1);assert.deepEqual(await page.evaluate(()=>window.__snapshot.inputs),inputs);
 });
 await check('horizontal browse and zoom retain ruler labels and background masks',async()=>{
   const before=await playback();await page.locator('.timeline-horizontal-scroll').evaluate(el=>el.scrollLeft=el.scrollWidth);await settle();
   const position=await page.evaluate(()=>({left:document.querySelector('.timeline-horizontal-scroll').getBoundingClientRect().left,label:document.querySelector('.timeline-window-label').getBoundingClientRect().left}));assert.ok(Math.abs(position.left-position.label)<1);
   const rect=await page.locator('.timeline-horizontal-scroll').boundingBox(),timeline=await page.locator('#inputTimeline').boundingBox();const scale=await page.locator('#timelineScale').textContent();
   await page.mouse.move(rect.x+15,timeline.y+130);await page.mouse.wheel(0,-120);await page.waitForTimeout(120);assert.notEqual(await page.locator('#timelineScale').textContent(),scale);assert.deepEqual(await playback(),before);
   await page.mouse.move(rect.x+rect.width-20,timeline.y+130);await page.mouse.wheel(0,90);await page.waitForTimeout(120);assert.deepEqual(await playback(),before);
   await page.screenshot({path:path.join(out,'background-scrolled-zoomed.png')});
 });
 await check('background region does not intercept timeline drag',async()=>{
   const rect=await page.locator('.timeline-horizontal-scroll').boundingBox(),timeline=await page.locator('#inputTimeline').boundingBox(),before=await playback();
   await page.mouse.move(rect.x+15,timeline.y+80);await page.mouse.down();await page.mouse.move(rect.x+15,timeline.y+150,{steps:6});await page.mouse.up();await settle();const after=await playback();assert.notEqual(after.time,before.time);assert.equal(after.paused,before.paused);assert.equal(after.rate,before.rate);
 });
 await check('no browser exceptions',async()=>assert.deepEqual(errors,[]));
 await browser.close();server.close();const report={scope:'Synthetic production UI validation; not a native recording or user acceptance test.',sourceIdentity,checks,errors,passed:checks.every(c=>c.pass)};fs.writeFileSync(path.join(out,'acceptance.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));if(!report.passed)process.exitCode=1;
}
main().catch(async error=>{console.error(error);if(browser)await browser.close();server.close();process.exitCode=1;});
