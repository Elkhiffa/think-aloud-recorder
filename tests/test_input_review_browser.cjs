'use strict';
// Production HTML and scripts, synthetic media/input data and a fake native
// bridge. This verifies browser behavior, not capture or native device support.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http'),vm=require('node:vm');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),read=file=>fs.readFileSync(path.join(root,file),'utf8');
const out=path.join(root,'work','input-review-scrubbing');fs.mkdirSync(out,{recursive:true});
const fixtureContext={window:{}};vm.runInNewContext(read('docs/prototypes/input-review/fixture.js'),fixtureContext);const fixture=JSON.parse(JSON.stringify(fixtureContext.window.INPUT_REVIEW_FIXTURE));
const data={title:'通道入口',session_name:'通道入口',game:'合成示例游戏',created:'2026-09-22T10:30:00',desktop:true,test:true,video:'/demo.mp4',vault_path:'D:\\synthetic\\library',segments:[],transcription:{state:'pending'},inputs:{version:1,state:'complete',duration:fixture.duration,timebase:'video_seconds',intervals:fixture.intervals,gaps:fixture.gaps}};
const media=fs.readFileSync(path.join(root,'docs/prototypes/input-review/demo.mp4'));
const values={TITLE:data.title,DATA:JSON.stringify(data),CSS:read('ui/review.css'),JS:read('ui/review.js'),PLYR_CSS:read('ui/vendor/plyr/plyr.css'),PLYR_JS:read('ui/vendor/plyr/plyr.min.js'),PLYR_SVG:read('ui/vendor/plyr/plyr.svg'),LICENSE:'Synthetic browser acceptance'};
const html=read('player.html').replace(/%%([A-Z_]+)%%/g,(_,key)=>values[key]);
const server=http.createServer((request,response)=>{if(request.url==='/demo.mp4'){response.setHeader('Content-Type','video/mp4');response.setHeader('Accept-Ranges','bytes');const range=/^bytes=(\d+)-(\d*)$/.exec(request.headers.range||'');if(range){const start=+range[1],end=Math.min(range[2]?+range[2]:media.length-1,media.length-1);response.writeHead(206,{'Content-Range':`bytes ${start}-${end}/${media.length}`,'Content-Length':end-start+1});response.end(media.subarray(start,end+1));}else response.end(media);return;}response.setHeader('Content-Type','text/html; charset=utf-8');response.end(html);});
const checks=[],errors=[];let browser;
const check=async(name,fn)=>{try{await fn();checks.push({name,pass:true});}catch(error){checks.push({name,pass:false,error:error.stack});console.error(name,error.stack);}};
async function main(){
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));browser=await chromium.launch({headless:true,channel:'msedge'});const page=await browser.newPage({viewport:{width:1280,height:800}});page.on('pageerror',error=>errors.push(error.message));
 await page.addInitScript(snapshot=>{window.__snapshot=snapshot;window.__calls=[];window.pywebview={api:{get_layout:async()=>({ok:true,data:{}}),save_layout:async()=>({ok:true}),ready:async()=>({ok:true}),get_snapshot:async known=>{window.__calls.push(['snapshot',known]);if(window.__snapshot.revision&&known===window.__snapshot.revision)return {ok:true,data:{unchanged:true,revision:known}};return {ok:true,data:window.__snapshot};},rename_session:async name=>{window.__snapshot.session_name=name;window.__snapshot.title=name||window.__snapshot.game;window.__calls.push(['rename',name]);return {ok:true,data:{session_name:name,title:window.__snapshot.title}};},copy_path:async kind=>{window.__calls.push(['copy',kind]);return {ok:true};},open_folder:async()=>({ok:true}),open_document:async()=>({ok:true})}};},data);
 await page.goto(`http://127.0.0.1:${server.address().port}/`);await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
 const settleVideo=async()=>{await page.waitForFunction(()=>{const v=document.querySelector('video');return !v.seeking&&v.readyState>=2;});await page.evaluate(async()=>{await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);});};
 const seek=async time=>{await page.locator('video').evaluate((video,time)=>{video.currentTime=time;},time);await page.waitForFunction(time=>{const v=document.querySelector('video');return !v.seeking&&v.readyState>=2&&Math.abs(v.currentTime-time)<.03;},time);await settleVideo();};
 const playback=()=>page.locator('video').evaluate(v=>({time:v.currentTime,paused:v.paused,rate:v.playbackRate,rect:v.getBoundingClientRect().toJSON()}));
 await page.waitForTimeout(400);await seek(4.8);await page.waitForFunction(()=>document.querySelectorAll('#currentKeys .keycap').length===4);
 await check('pending review and overlapping held inputs',async()=>{assert.equal(await page.locator('#transcriptTab').textContent(),'转写中');assert.equal(await page.locator('#transcriptTab').isDisabled(),true);assert.equal(await page.locator('#currentKeys .keycap').count(),4);assert.equal(await page.locator('#inputTab').getAttribute('aria-selected'),'true');});
 await check('video source ratio and stable geometry across display modes',async()=>{const before=await playback();assert.ok(Math.abs(before.rect.width/before.rect.height-16/9)<.001);for(const mode of ['device','collapsed','keys']){await page.locator(`[data-input-mode=${mode}]`).click();const after=await playback();for(const k of ['x','y','width','height'])assert.ok(Math.abs(after.rect[k]-before.rect[k])<1);}});
 await check('shared track grid and actual interval durations; long holds never jump lanes',async()=>{
   const measure=()=>page.evaluate(()=>{const rect=el=>el.getBoundingClientRect().toJSON(),bar=id=>rect(document.querySelector(`[data-input-id="${id}"]`));return {heads:[...document.querySelectorAll('.timeline-column-headings span')].map(rect),w:bar('k-w-1'),a:bar('k-a-1'),q:bar('k-q-1'),mouse:bar('m-left-1')};});
   const before=await measure();assert.ok(Math.abs(before.w.x-before.heads[2].x-4)<1);assert.ok(before.a.x>before.w.right);assert.ok(before.q.x>=before.heads[4].x);assert.ok(before.mouse.x>before.q.right);
   const scale=before.w.height/(8.2-1);assert.ok(Math.abs((before.a.y-before.w.y)-(3.2-1)*scale)<1);assert.ok(Math.abs(before.q.height-(4.95-4.5)*scale)<1);
   await seek(5.4);const after=await measure();assert.equal(after.w.x,before.w.x);assert.equal(after.a.x,before.a.x);await seek(4.8);
 });
 await check('content wheel scrubs while paused; ruler wheel scales about pointer time',async()=>{const box=await page.locator('#inputTimeline').boundingBox();await page.mouse.move(box.x+box.width-20,box.y+180);await page.mouse.wheel(0,64);await page.waitForTimeout(100);const after=await playback();assert.equal(after.paused,true);assert.ok(after.time>5.7&&after.time<5.9);const text=await page.locator('#timelineScale').textContent();await page.mouse.move(box.x+15,box.y+180);await page.mouse.wheel(0,-120);await page.waitForTimeout(100);assert.notEqual(await page.locator('#timelineScale').textContent(),text);assert.equal((await playback()).time,after.time);});
 await check('completed transcript retains playing position, speed and selected tab',async()=>{await seek(4.8);await page.locator('video').evaluate(async v=>{v.playbackRate=1.5;await v.play();});await page.evaluate(segments=>{window.__snapshot.segments=segments;window.__snapshot.transcription={state:'ready'};},fixture.segments);await page.waitForFunction(()=>!document.querySelector('#transcriptTab').disabled);const after=await playback();assert.equal(after.paused,false);assert.equal(after.rate,1.5);assert.ok(after.time>4.8);assert.equal(await page.locator('#inputTab').getAttribute('aria-selected'),'true');await page.locator('video').evaluate(v=>v.pause());});
 await seek(4.8);await page.locator('#follow').click();
 await check('speech hover and pin never seek; tooltip has only time text close; outside and Escape dismiss',async()=>{const quote=page.locator('[data-quote="0"]');await quote.hover();assert.equal(await page.locator('#quotePopover').isVisible(),true);const before=await playback();await quote.click();assert.equal((await playback()).time,before.time);assert.equal(await page.locator('#quotePopover button').count(),1);assert.ok(!(await page.locator('#quotePopover').textContent()).includes('已固定'));await page.locator('#title').click();assert.equal(await page.locator('#quotePopover').isHidden(),true);await quote.click();await page.keyboard.press('Escape');assert.equal(await page.locator('#quotePopover').isHidden(),true);});
 await check('Xbox and DualSense auto device switching and foreground gap',async()=>{await page.locator('[data-input-mode=device]').click();await seek(17);assert.equal(await page.locator('#inputSource').textContent(),'Xbox');assert.equal(await page.locator('#deviceView .xbox').count(),1);await seek(25.3);assert.equal(await page.locator('#inputSource').textContent(),'DualSense');assert.equal(await page.locator('#deviceView .dualsense').count(),1);await seek(10.5);assert.equal(await page.locator('#inputState').getAttribute('class'),'input-state is-gap');});
 await check('hot-switch overlap retains both devices and a controller gap does not erase keyboard evidence',async()=>{
   await page.locator('[data-input-mode=keys]').click();await seek(17);
   await page.evaluate(()=>{window.__snapshot.inputs.intervals.push({id:'synthetic-overlap',device:'keyboard',code:'W',label:'W',kind:'button',start:16.5,end:17.5});window.__snapshot.inputs.gaps.push({start:16,end:18,type:'disconnect',device:'dualsense',reason:'合成 DualSense 断开；Xbox 和键鼠仍有记录'});});
   await page.waitForFunction(()=>document.querySelectorAll('#currentKeys .keycap').length===4);assert.equal(await page.locator('.key-bar.active').count(),4);assert.equal(await page.locator('#inputSource').textContent(),'Xbox');assert.equal(await page.locator('#currentKeys').isVisible(),true);
   await page.evaluate(inputs=>window.__snapshot.inputs=inputs,structuredClone(data.inputs));await page.waitForFunction(()=>!document.querySelector('[data-input-id="synthetic-overlap"]'));
 });
 await check('clip rename persists through bridge and retains preset',async()=>{await page.locator('#renameSession').click();await page.locator('#sessionName').fill('入口反复尝试');await page.locator('#renameForm button[type=submit]').click();assert.equal(await page.locator('#title').textContent(),'入口反复尝试');assert.ok((await page.locator('#sessionInfo').textContent()).includes('合成示例游戏'));assert.deepEqual(await page.evaluate(()=>window.__calls.find(item=>item[0]==='rename')),['rename','入口反复尝试']);});
 await check('empty and whitespace rename restore the game title and remain restored after polling',async()=>{
   for(const name of ['', '   ']){
     await page.locator('#renameSession').click();assert.equal(await page.locator('#sessionName').getAttribute('placeholder'),'留空使用游戏／项目名');await page.locator('#sessionName').fill(name);await page.locator('#renameForm button[type=submit]').click();
     assert.equal(await page.locator('#title').textContent(),'合成示例游戏');assert.equal(await page.evaluate(()=>window.__snapshot.game),'合成示例游戏');assert.equal(await page.evaluate(()=>window.__calls.filter(item=>item[0]==='rename').at(-1)[1]),'');
   }
   const count=await page.evaluate(()=>window.__calls.filter(call=>call[0]==='snapshot').length);await page.waitForFunction(count=>window.__calls.filter(call=>call[0]==='snapshot').length>count,count);assert.equal(await page.locator('#title').textContent(),'合成示例游戏');assert.ok((await page.locator('#sessionInfo').textContent()).includes('合成示例游戏'));
 });
 await check('copy library control belongs to header metadata without video overlap; native call uses vault',async()=>{const {video,copy,header}=await page.evaluate(async()=>{for(let i=0;i<3;i++)await new Promise(requestAnimationFrame);return {video:document.querySelector('.video-slot').getBoundingClientRect().toJSON(),copy:document.querySelector('#copySplit').getBoundingClientRect().toJSON(),header:document.querySelector('.review-header').getBoundingClientRect().toJSON()};});assert.ok(copy.y>=header.y&&copy.bottom<=header.bottom&&copy.right<=header.right);assert.ok(copy.bottom<=video.y);assert.equal(await page.locator('.session-meta-row #copySplit').count(),1);await page.locator('#copyPath').click();assert.deepEqual(await page.evaluate(()=>window.__calls.find(item=>item[0]==='copy')),['copy','vault']);await page.locator('#fileActionsToggle').click();await page.locator('[data-copy=video]').click();assert.equal(await page.locator('#fileActions').isHidden(),true);});
 await page.locator('[data-input-mode=keys]').click();await seek(4.8);await settleVideo();await page.screenshot({path:path.join(out,'keyboard-1280.png')});
 await check('no page overflow at a small desktop size and theme remains readable',async()=>{await page.setViewportSize({width:980,height:720});await page.waitForTimeout(150);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);const g=await playback();assert.ok(g.rect.width>200&&g.rect.height>100);await page.locator('#themeButton').click();await settleVideo();await page.screenshot({path:path.join(out,'keyboard-dark-980.png')});});
 await check('old, disabled, failed and missing input states are distinct',async()=>{for(const [inputs,text] of [[null,'此场次没有操作记录'],[{state:'disabled'},'此场次未启用操作记录'],[{state:'failed',error:'合成采集异常'},'操作记录采集失败'],[{state:'unavailable'},'操作记录文件不可用']]){await page.evaluate(inputs=>window.__snapshot.inputs=inputs,inputs);await page.waitForFunction(text=>document.querySelector('#timelineState').textContent===text,text);}});
 await check('missing transcript is visibly failed while video remains playable',async()=>{
   await page.locator('#transcriptTab').click();await seek(4.8);const before=await playback();
   await page.evaluate(inputs=>{window.__snapshot.inputs=inputs;window.__snapshot.transcription={state:'failed',error:'逐字稿暂不可用：已完成的逐字稿文件缺失，请恢复文件或重新转写；录像仍可回看。'};window.__snapshot.segments=[];},structuredClone(data.inputs));
   await page.waitForFunction(()=>document.querySelector('#transcriptTab').textContent==='转写失败');assert.equal(await page.locator('#transcriptTab').isDisabled(),true);assert.equal(await page.locator('#transcriptTab').isVisible(),true);assert.ok((await page.locator('#transcriptTab').getAttribute('title')).includes('缺失'));assert.equal(await page.locator('#inputTab').getAttribute('aria-selected'),'true');
   const after=await playback();assert.equal(after.time,before.time);assert.equal(after.paused,true);assert.equal(after.rate,before.rate);assert.equal(await page.locator('.quote-bar').count(),0);
   await page.locator('.plyr__controls [data-plyr=play]').click();await page.waitForFunction(()=>!document.querySelector('video').paused&&document.querySelector('video').currentTime>4.9);await page.locator('.plyr__controls [data-plyr=play]').click();await settleVideo();await page.screenshot({path:path.join(out,'missing-transcript-still-playable.png')});
 });
 await check('unchanged revision skips 100k history serialization and DOM reset; changed revision refreshes without media reset',async()=>{
   await seek(4.8);
   await page.evaluate(({inputs,segments})=>{
     window.__largeStrings=0;window.__originalStringify=JSON.stringify;
     JSON.stringify=function(value,...args){if(value?.intervals?.length>=100000||(Array.isArray(value)&&value.some(item=>item?.intervals?.length>=100000)))window.__largeStrings++;return window.__originalStringify.call(JSON,value,...args);};
     const tail=Array.from({length:100000},(_,i)=>({id:'large-'+i,device:'keyboard',code:'E',label:'E',kind:'button',start:60+i*.1,end:60+i*.1+.05}));
     window.__snapshot.inputs={...inputs,duration:10061,intervals:[...inputs.intervals,...tail]};window.__snapshot.segments=segments;window.__snapshot.transcription={state:'ready'};window.__snapshot.revision='synthetic-r1';
   },{inputs:structuredClone(data.inputs),segments:fixture.segments});
   await page.waitForFunction(()=>!document.querySelector('#transcriptTab').disabled&&document.querySelector('#timelineState').textContent.startsWith('100019'));
   await page.locator('[data-quote="0"]').click();const before=await playback();
   const strings=await page.evaluate(()=>{window.__heldKeyNode=document.querySelector('[data-input-id="k-w-1"]');window.__heldQuoteNode=document.querySelector('[data-quote="0"]');return window.__largeStrings;});
   await page.waitForFunction(()=>window.__calls.filter(call=>call[0]==='snapshot'&&call[1]==='synthetic-r1').length>=2);
   assert.equal(await page.evaluate(()=>window.__largeStrings),strings);assert.equal(await page.evaluate(()=>window.__heldKeyNode===document.querySelector('[data-input-id="k-w-1"]')&&window.__heldQuoteNode===document.querySelector('[data-quote="0"]')),true);assert.equal(await page.locator('#quotePopover').isVisible(),true);
   const unchanged=await playback();for(const key of ['time','paused','rate'])assert.equal(unchanged[key],before[key]);
   await page.evaluate(()=>{window.__snapshot.session_name='版本变更后的片段';window.__snapshot.segments=[{start:4.2,end:7.8,text:'版本更新后的合成原话'}];window.__snapshot.revision='synthetic-r2';});
   await page.waitForFunction(()=>document.querySelector('#title').textContent==='版本变更后的片段');assert.equal(await page.locator('#lines .segment-text').textContent(),'版本更新后的合成原话');const changed=await playback();for(const key of ['time','paused','rate'])assert.equal(changed[key],before[key]);assert.equal(await page.locator('#inputTab').getAttribute('aria-selected'),'true');
   await page.evaluate(()=>{JSON.stringify=window.__originalStringify;});
 });
 // Synthetic, collector-shaped samples. A value change produces a new raw
 // interval every 20 ms; repeated button presses must remain separate events.
 const denseAxis=Array.from({length:150},(_,i)=>({id:'dense-axis-'+i,device:'xbox',code:'LeftStick',label:'左摇杆',kind:'axis',start:+(1+i*.02).toFixed(6),end:+(1+(i+1)*.02).toFixed(6),value:.5+(i%5)*.02,x:.5+(i%5)*.02,y:0,direction:i<45?'→':i<90?'↑':i<120?'←':'↓'}));
 const denseMouse=denseAxis.map((item,i)=>({...item,id:'dense-mouse-'+i,device:'mouse',code:'MouseMove',label:'鼠标',kind:'motion',direction:i<60?'↗':'↙'}));
 const buttonTypes=[['keyboard','ShiftLeft','Shift'],['xbox','Menu','Menu'],['dualsense','DPadDown','DPadDown'],['dualsense','Options','Options'],['mouse','WheelUp','滚轮上']];
 const denseTaps=Array.from({length:20},(_,i)=>{const [device,code,label]=buttonTypes[i%buttonTypes.length];return {id:'dense-tap-'+i,device,code,label,kind:'button',start:+(2+i*.06).toFixed(6),end:+(2+i*.06+(code==='WheelUp'?0:.02)).toFixed(6)};});
 const denseInputs={version:1,state:'complete',duration:32,intervals:[{id:'dense-w',device:'keyboard',code:'W',label:'W',kind:'button',start:.5,end:7},...denseAxis,...denseMouse,...denseTaps],gaps:[]};
 const visualRows=()=>page.evaluate(()=>[...document.querySelectorAll('#timelineInputs .key-bar')].map(el=>({id:el.dataset.inputId,start:+el.dataset.start,end:+el.dataset.end,lane:+el.dataset.lane,channel:el.dataset.channel,rect:el.getBoundingClientRect().toJSON(),font:getComputedStyle(el.firstElementChild).fontSize,text:el.firstElementChild.textContent,duration:el.querySelector('.bar-duration').getBoundingClientRect().height})));
 const assertCollisions=rows=>{for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){const a=rows[i].rect,b=rows[j].rect;if(rows[i].channel===rows[j].channel)assert.ok(Math.min(a.right,b.right)-Math.max(a.left,b.left)<.1||Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)<.1,`${rows[i].id} overlaps ${rows[j].id}`);}};
 await check('continuous analog samples form activity bands while current input stays raw',async()=>{
   await page.setViewportSize({width:1280,height:800});await page.locator('#themeButton').click();
   await page.evaluate(inputs=>{window.__snapshot.inputs=inputs;window.__snapshot.revision='dense-v1';},denseInputs);
   await page.waitForFunction(()=>document.querySelector('[data-input-id="dense-axis-0"]'));await seek(2.73);
   assert.equal(await page.locator('[data-input-id^="dense-axis-"]').count(),1);assert.equal(await page.locator('[data-input-id^="dense-mouse-"]').count(),1);
   assert.equal(await page.locator('#currentKeys .current-item').filter({hasText:'左摇杆'}).count(),1);assert.ok((await page.locator('#currentKeys').textContent()).includes('52%'));
   assert.ok(await page.locator('[data-input-id="dense-axis-0"] .bar-direction').count()>=2);
   const axis=await page.locator('[data-input-id="dense-axis-0"]').boundingBox(),time=2.73,scale=axis.height/3;
   await page.mouse.move(axis.x+18,axis.y+(time-1)*scale);await page.waitForFunction(()=>!document.querySelector('#inputDetail').hidden);
   const hoverText=await page.locator('#inputDetail>span').textContent(),hoverTime=Number(/00:00:(\d+\.\d+)/.exec(hoverText)[1]);assert.ok(Math.abs(hoverTime-time)<.03);const hoverSample=denseAxis.find(item=>item.start<=hoverTime&&hoverTime<item.end);assert.ok(hoverText.includes(Math.round(hoverSample.value*100)+'%'));assert.ok((await page.locator('#inputDetail').textContent()).includes('00:00:01.000 — 00:00:04.000'));
   await page.mouse.click(axis.x+18,axis.y+(time-1)*scale);assert.ok(Math.abs((await playback()).time-time)<.025);assert.equal((await playback()).paused,true);
   await settleVideo();await page.screenshot({path:path.join(out,'continuous-bands-1280.png')});
 });
 await check('short presses use readable display boxes and leftmost nonoverlapping lanes at every zoom',async()=>{
   for(const delta of [240,240,-240,-240,-240,-240]){
     const box=await page.locator('.timeline-horizontal-scroll').boundingBox(),timeline=await page.locator('#inputTimeline').boundingBox();
     await page.mouse.move(box.x+15,timeline.y+80);await page.mouse.wheel(0,delta);await page.waitForTimeout(90);
     const rows=await visualRows(),taps=rows.filter(item=>item.id.startsWith('dense-tap-'));assert.equal(taps.length,20);assertCollisions(rows);
     const w=rows.find(item=>item.id==='dense-w'),scale=w.rect.height/6.5;
     for(const tap of taps){const raw=denseTaps.find(item=>item.id===tap.id);assert.equal(tap.start,raw.start);assert.equal(tap.end,raw.end);assert.ok(tap.rect.height>=27.99);assert.equal(tap.font,'12px');assert.ok(Math.abs(tap.rect.y-w.rect.y-(tap.start-w.start)*scale)<.15);assert.ok(Math.abs(tap.duration-Math.max(1,(tap.end-tap.start)*scale))<.15);}
     for(const tap of taps){const occupied=taps.filter(other=>other.start<tap.start&&other.rect.bottom+3.9>tap.rect.y).map(other=>other.lane);assert.equal(tap.lane,Array.from({length:21},(_,i)=>i).find(i=>!occupied.includes(i)));}
   }
   const tap=page.locator('[data-input-id="dense-tap-2"]');assert.equal(await tap.locator('.dpad-glyph').count(),1);assert.ok(!(await tap.locator('.bar-glyph').textContent()).includes('DPadDown'));
   const before=(await visualRows()).find(item=>item.id==='dense-w');await seek(3.3);const after=(await visualRows()).find(item=>item.id==='dense-w');assert.equal(after.lane,before.lane);assert.equal(after.rect.x,before.rect.x);
 });
 await check('horizontal track browsing keeps headers aligned and video fixed without hiding events',async()=>{
   await page.setViewportSize({width:980,height:720});await seek(2.73);await page.waitForTimeout(150);
   const before=await playback();const width=await page.locator('.timeline-horizontal-scroll').evaluate(el=>({client:el.clientWidth,scroll:el.scrollWidth}));assert.ok(width.scroll>width.client);
   await page.locator('.timeline-horizontal-scroll').evaluate(el=>{el.scrollLeft=el.scrollWidth;});await page.waitForTimeout(100);
   const after=await playback();for(const key of ['x','y','width','height'])assert.equal(after.rect[key],before.rect[key]);assert.equal(after.time,before.time);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
   const alignment=await page.evaluate(()=>{const header=[...document.querySelectorAll('.timeline-column-headings>span')].map(el=>el.getBoundingClientRect().toJSON()),scroller=document.querySelector('.timeline-horizontal-scroll').getBoundingClientRect();return {header,scroller:scroller.toJSON(),time:document.querySelector('.time-tick time').getBoundingClientRect().toJSON()};});
   assert.ok(Math.abs(alignment.header[0].left-alignment.scroller.left)<1);assert.ok(Math.abs(alignment.time.left-alignment.scroller.left-1)<1);
   const rows=await visualRows(),firstOther=rows.filter(item=>item.channel==='other'&&item.lane===0)[0];assert.ok(Math.abs(firstOther.rect.x-alignment.header[4].x-4)<1);assert.equal(rows.filter(item=>item.id.startsWith('dense-tap-')).length,20);
   for(const row of rows.filter(item=>['Menu','Options','Shift'].includes(item.text)))assert.ok(row.rect.width>=row.text.length*7+14);
   await settleVideo();await page.screenshot({path:path.join(out,'dense-short-presses-980.png')});
   // Horizontal trackpad motion must not seek; the pinned ruler still zooms.
   const timeline=await page.locator('#inputTimeline').boundingBox(),box=await page.locator('.timeline-horizontal-scroll').boundingBox();
   await page.mouse.move(box.x+box.width-20,timeline.y+100);await page.mouse.wheel(-80,0);await page.waitForTimeout(80);assert.equal((await playback()).time,before.time);
   const scale=await page.locator('#timelineScale').textContent();await page.mouse.move(box.x+15,timeline.y+100);await page.mouse.wheel(0,240);await page.waitForTimeout(80);assert.notEqual(await page.locator('#timelineScale').textContent(),scale);assert.equal((await playback()).time,before.time);
 });
 const timelineMap=()=>page.evaluate(()=>{const t=document.querySelector('#inputTimeline').getBoundingClientRect(),h=document.querySelector('.timeline-horizontal-scroll').getBoundingClientRect(),w=document.querySelector('[data-input-id="dense-w"]').getBoundingClientRect();const scale=w.height/6.5;return {top:t.top,bottom:t.bottom,height:t.height,left:h.left,right:h.right,scale,viewStart:.5-(w.top-t.top)/scale};});
 const at=(map,time)=>map.top+(time-map.viewStart)*map.scale;
 const pointed=(map,y)=>Math.max(0,Math.min(32,map.viewStart+(y-map.top)/map.scale));
 const resetTimeline=async()=>{await page.setViewportSize({width:1280,height:800});await page.locator('video').evaluate(v=>v.pause());await page.locator('.timeline-horizontal-scroll').evaluate(el=>{el.scrollLeft=0;});for(let i=0;i<4;i++){const m=await timelineMap(),delta=Math.log(m.scale/64)/.0025;if(Math.abs(delta)<.1)break;await page.mouse.move(m.left+15,m.top+100);await page.mouse.wheel(0,delta);await page.waitForTimeout(60);}if(await page.locator('#follow').getAttribute('aria-pressed')==='false')await page.locator('#follow').click();await seek(2.73);};
 await check('ruler and blank clicks seek by visible time while retaining paused state and rate',async()=>{
   await resetTimeline();let m=await timelineMap();const before=await playback();await page.mouse.click(m.left+15,m.top+120);let after=await playback();assert.ok(Math.abs(after.time-pointed(m,m.top+120))<.03);assert.equal(after.paused,true);assert.equal(after.rate,before.rate);assert.equal(await page.locator('#follow').getAttribute('aria-pressed'),'false');
   m=await timelineMap();const x=m.right-12,y=m.bottom-35;assert.equal(await page.evaluate(({x,y})=>!!document.elementFromPoint(x,y)?.closest('.key-bar,.quote-bar'),{x,y}),false);await page.mouse.click(x,y);after=await playback();assert.ok(Math.abs(after.time-pointed(m,y))<.03);assert.equal(after.rate,before.rate);
 });
 await check('key drag scrubs against frozen coordinates through a snapshot rebuild and never becomes a click',async()=>{
   await resetTimeline();const m=await timelineMap(),key=await page.locator('[data-input-id="dense-w"]').boundingBox(),x=key.x+key.width/2,y=at(m,2.3),target=at(m,3.35),before=await playback();
   await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x,y+12,{steps:3});assert.equal(await page.locator('#inputTimeline').evaluate(el=>el.classList.contains('is-scrubbing')),true);
   await page.evaluate(()=>{window.__snapshot.title='拖动期间刷新';window.__snapshot.session_name='拖动期间刷新';window.__snapshot.segments[0].text='拖动期间到达的新原话';window.__snapshot.revision='scrub-snapshot';});await page.waitForFunction(()=>document.querySelector('#title').textContent==='拖动期间刷新');
   await page.mouse.move(x,target,{steps:8});let current=await playback();assert.ok(Math.abs(current.time-3.35)<.03);assert.equal(current.paused,true);assert.equal(current.rate,before.rate);assert.ok(Math.abs((await timelineMap()).viewStart-m.viewStart)<.01);assert.equal(await page.locator('#follow').getAttribute('aria-pressed'),'false');
   const expected=denseInputs.intervals.filter(item=>item.start<=current.time&&current.time<item.end).length;assert.equal(await page.locator('#currentKeys .current-item').count(),expected);
   await page.mouse.up();current=await playback();assert.ok(Math.abs(current.time-3.35)<.03);assert.equal(await page.locator('#inputTimeline').evaluate(el=>el.classList.contains('is-scrubbing')),false);assert.equal(await page.locator('#quotePopover').isHidden(),true);
   const head=await page.locator('#timelinePlayhead').boundingBox();assert.ok(Math.abs(head.y-target)<1);await settleVideo();await page.screenshot({path:path.join(out,'timeline-drag-header-copy-1280.png')});
 });
 await check('quote dragging seeks without pinning while quote clicks pin and outside key body header clicks dismiss',async()=>{
   await resetTimeline();let m=await timelineMap(),quote=await page.locator('[data-quote="0"]').boundingBox(),x=quote.x+quote.width/2,y=at(m,4.5),target=at(m,5.2);
   await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x,target,{steps:8});await page.mouse.up();assert.ok(Math.abs((await playback()).time-5.2)<.03);assert.equal(await page.locator('#quotePopover').isHidden(),true);
   const pin=async()=>{const bounds=await page.locator('[data-quote="0"]').boundingBox(),map=await timelineMap(),before=await playback();await page.mouse.click(bounds.x+bounds.width/2,at(map,4.5));assert.equal((await playback()).time,before.time);assert.equal(await page.locator('#quotePopover').isVisible(),true);};
   await pin();let key=await page.locator('[data-input-id="dense-w"]').boundingBox();const keyPoint={x:key.x+key.width/2,y:at(await timelineMap(),2)};assert.equal(await page.evaluate(({x,y})=>document.elementFromPoint(x,y)?.closest('.key-bar')?.dataset.inputId,keyPoint),'dense-w');await page.mouse.click(keyPoint.x,keyPoint.y);assert.equal(await page.locator('#quotePopover').isHidden(),true);assert.equal((await playback()).time,.5);
   await pin();m=await timelineMap();await page.mouse.click(m.right-12,m.bottom-25);assert.equal(await page.locator('#quotePopover').isHidden(),true);
   await pin();await page.locator('#title').click();assert.equal(await page.locator('#quotePopover').isHidden(),true);
 });
 await check('dragging while playing preserves playback and speed and leaves browsing position fixed',async()=>{
   await resetTimeline();await page.locator('.plyr__controls [data-plyr=play]').click();await page.waitForFunction(()=>!document.querySelector('video').paused);const m=await timelineMap(),before=await playback(),x=m.left+15,y=at(m,2.5),target=at(m,3.8);
   await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x,target,{steps:6});await page.mouse.up();const after=await playback();assert.equal(after.paused,false);assert.equal(after.rate,before.rate);assert.ok(after.time>=3.77&&after.time<4.15);assert.ok(Math.abs((await timelineMap()).viewStart-m.viewStart)<.03);assert.equal(await page.locator('#follow').getAttribute('aria-pressed'),'false');
   await page.locator('.plyr__controls [data-plyr=play]').click();
 });
 await check('a quote pressed before snapshot reordering never pins another transcript',async()=>{
   await resetTimeline();const m=await timelineMap(),quote=await page.locator('[data-quote="0"]').boundingBox(),before=await playback(),intended=await page.evaluate(()=>window.__snapshot.segments[0].text);
   await page.mouse.move(quote.x+quote.width/2,at(m,4.5));await page.mouse.down();
   await page.evaluate(()=>{window.__snapshot.segments.unshift({start:.1,end:.4,text:'新插入的原话，不是按下时的目标'});window.__snapshot.revision='scrub-reordered';});await page.waitForFunction(()=>document.querySelector('#lines .segment-text').textContent==='新插入的原话，不是按下时的目标');
   await page.mouse.up();assert.equal((await playback()).time,before.time);assert.equal(await page.locator('#quoteText').textContent(),intended);assert.equal(await page.locator('#quotePopover').isVisible(),true);await page.locator('#title').click();
 });
 await check('release outside and pointer cancellation lost capture or window blur never leave scrubbing active',async()=>{
   await resetTimeline();await page.evaluate(()=>{document.querySelector('#inputTimeline').addEventListener('pointerdown',event=>window.__scrubPointer=event.pointerId);});
   for(const ending of ['outside','pointercancel','lostcapture','blur']){
     const m=await timelineMap(),x=m.left+15,y=at(m,2.1),end=at(m,2.9);await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x,end,{steps:4});
     if(ending==='outside'){await page.mouse.move(m.left-120,end);await page.mouse.up();}
     else{await page.evaluate(ending=>{const el=document.querySelector('#inputTimeline');if(ending==='pointercancel')el.dispatchEvent(new PointerEvent('pointercancel',{bubbles:true,pointerId:window.__scrubPointer}));else if(ending==='lostcapture')el.releasePointerCapture(window.__scrubPointer);else window.dispatchEvent(new Event('blur'));},ending);await page.mouse.up();}
     assert.equal(await page.locator('#inputTimeline').evaluate(el=>el.classList.contains('is-scrubbing')),false);const stop=await playback();await page.mouse.move(x,end+50);assert.equal((await playback()).time,stop.time);assert.equal(stop.paused,true);
   }
 });
 await check('horizontal gestures and right clicks do not seek or pin a quote',async()=>{
   await resetTimeline();const m=await timelineMap(),quote=await page.locator('[data-quote="0"]').boundingBox(),x=quote.x+quote.width/2,y=at(m,4.5),before=await playback();
   await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+45,y+2,{steps:6});await page.mouse.up();assert.equal((await playback()).time,before.time);await page.mouse.move(m.right-12,m.bottom-20);assert.equal(await page.locator('#quotePopover').isHidden(),true);
   await page.mouse.click(m.left+15,m.top+80,{button:'right'});await page.keyboard.press('Escape');assert.equal((await playback()).time,before.time);
 });
 await check('visible ruler clicks and drag remain accurate after zoom and horizontal browsing; compact copy stays above video',async()=>{
   await page.setViewportSize({width:980,height:720});await page.locator('.timeline-horizontal-scroll').evaluate(el=>{el.scrollLeft=el.scrollWidth;});let m=await timelineMap();await page.mouse.move(m.left+15,m.top+100);await page.mouse.wheel(0,-120);await page.waitForTimeout(100);m=await timelineMap();const y=m.top+150;await page.mouse.click(m.left+15,y);assert.ok(Math.abs((await playback()).time-pointed(m,y))<.03);
   await page.mouse.move(m.left+15,y);await page.mouse.down();await page.mouse.move(m.left+15,y+50,{steps:5});await page.mouse.up();assert.ok(Math.abs((await playback()).time-pointed(m,y+50))<.03);assert.equal(await page.locator('#follow').getAttribute('aria-pressed'),'false');
   await page.setViewportSize({width:560,height:540});await page.waitForTimeout(150);const boxes=await page.evaluate(()=>{const box=s=>document.querySelector(s).getBoundingClientRect().toJSON();return {header:box('.review-header'),copy:box('#copySplit'),video:box('.video-slot'),overflow:document.documentElement.scrollWidth>innerWidth+1};});assert.ok(boxes.copy.bottom<=boxes.header.bottom&&boxes.copy.bottom<boxes.video.top);assert.equal(boxes.overflow,false);await settleVideo();await page.screenshot({path:path.join(out,'header-copy-compact-560.png')});
 });
 await check('no browser exceptions',async()=>assert.deepEqual(errors,[]));
 await browser.close();server.close();const report={scope:'Synthetic production browser acceptance; no actual OBS/device/native capture validation.',checks,errors,passed:checks.every(c=>c.pass)};fs.writeFileSync(path.join(out,'acceptance.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));if(!report.passed)process.exitCode=1;
}
main().catch(async error=>{console.error(error);if(browser)await browser.close();server.close();process.exitCode=1;});
