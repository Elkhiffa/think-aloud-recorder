'use strict';
// Production review assets, real Edge/media, synthetic external-agent results.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(process.env.REVIEW_ASSET_ROOT||path.join(__dirname,'..')),read=name=>fs.readFileSync(path.join(root,name),'utf8'),out=path.resolve(process.env.REVIEW_TEST_OUTPUT||path.join(__dirname,'..','work','agent-integration'));
fs.mkdirSync(out,{recursive:true});
const result={version:1,session_id:'synthetic-agent',revision:'fixture',summary:'仅检查了合成按钮的状态变化。',coverage:{video_ranges:[{start:2,end:4}],transcript:'full',inputs:'none',limitations:['合成数据，无真实游戏结论。']},events:[{id:'e1',start:2,end:4,title:'按钮状态难以判断',summary:'记录者说不知道是否成功。<img src=x onerror=alert(1)>',basis:'explicit',kind:'friction',context:'目标需核对。',evidence:[{kind:'quote',ref:'t000001',start:2,end:4,text:'我不知道这个按钮的状态。'},{kind:'video',start:3,end:3,text:'合成按钮保持在原处。'}]}],questions:[{id:'q1',event_id:'e1',question:'后来怎样确认？',reason:'片段尚未说明。'}],ideas:[{id:'h1',event_id:'e1',idea:'比较状态提示的辨识度。',reason:'以原话为线索，待进一步验证。'}]};
const ready={editing:{result_sha256:'synthetic-result',corrections_revision:''},state:'complete',label:'已预处理 · 1 个事件',events:1,questions:1,ideas:1,result};
// A single raw segment with distant phrases; only the later words support this event.
const excerptReady=structuredClone(ready);
Object.assign(excerptReady.result.events[0],{start:8,end:9,evidence:[{kind:'quote_words',ref:'t000001',word_range:[3,6],start:8.2,end:8.8,text:'这是后半句。<img src=x>',speaker_id:0}]});
const data={id:'synthetic-agent',game:'合成接口验证',title:'合成接口验证',test:true,desktop:true,video:'/demo.mp4',transcription:{state:'ready'},segments:[{start:2,end:4,text:'我不知道这个按钮的状态。'}],inputs:{state:'disabled',intervals:[],gaps:[],duration:12},preprocessing:{state:'none'}};
function render(url){const d=structuredClone(data);if(url.includes('ready'))d.preprocessing=ready;if(url.includes('words'))d.preprocessing=excerptReady;if(url.includes('portable'))d.desktop=false;const vars={TITLE:d.title,DATA:JSON.stringify(d).replaceAll('<','\\u003c'),CSS:read('ui/review.css'),JS:read('ui/review.js'),PLYR_CSS:read('ui/vendor/plyr/plyr.css'),PLYR_JS:read('ui/vendor/plyr/plyr.min.js'),PLYR_SVG:read('ui/vendor/plyr/plyr.svg'),LICENSE:'Synthetic test'};return read('player.html').replace(/%%([A-Z_]+)%%/g,(_,k)=>vars[k]);}
const media=fs.readFileSync(path.join(__dirname,'..','docs/prototypes/input-review/demo.mp4'));
const server=http.createServer((req,res)=>{if(req.url==='/demo.mp4'){res.setHeader('Content-Type','video/mp4');res.setHeader('Accept-Ranges','bytes');const range=/^bytes=(\d+)-(\d*)$/.exec(req.headers.range||'');if(range){const start=+range[1],end=Math.min(range[2]?+range[2]:media.length-1,media.length-1);res.writeHead(206,{'Content-Range':`bytes ${start}-${end}/${media.length}`,'Content-Length':end-start+1});res.end(media.subarray(start,end+1));}else res.end(media);return;}res.setHeader('Content-Type','text/html; charset=utf-8');res.end(render(req.url));});
let browser;const report={scope:'Synthetic local protocol UI; no real agent inference claim.',checks:[],errors:[]};
async function main(){
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin=`http://127.0.0.1:${server.address().port}`;
 browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1440,height:900}});page.on('pageerror',e=>report.errors.push(String(e)));
 await page.addInitScript(d=>{window.__snapshot=structuredClone(d);window.__ready=null;window.pywebview={api:{ready:async error=>{window.__ready={error};return {ok:true};},edit_event:async request=>{window.__editRequest=request;if(window.__editError)return {ok:false,error:window.__editError};Object.assign(window.__snapshot.preprocessing.result.events[0],request.fields,{manually_edited:true});window.__snapshot.preprocessing.editing.corrections_revision='saved-edit';return {ok:true,data:structuredClone(window.__snapshot.preprocessing)};},get_layout:async()=>({ok:true,data:{}}),save_layout:async()=>({ok:true}),get_snapshot:async()=>({ok:true,data:window.__snapshot})}};},data);
 const check=async(name,run)=>{await run();report.checks.push({name,pass:true});};
 await page.goto(origin);await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
 await check('no agent means no empty event tab or unfinished notice',async()=>{assert.equal(await page.locator('#eventsTab').isHidden(),true);assert.equal(await page.locator('#preprocessingNotice').isHidden(),true);assert.equal(await page.locator('.line').count(),1);assert.deepEqual(await page.evaluate(()=>window.__ready),{error:null});});
 await check('arrival updates only optional presentation, keeps video node and playhead',async()=>{await page.locator('video').evaluate(v=>{v.currentTime=1;window.__video=v;});await page.evaluate(value=>window.__snapshot.preprocessing=value,ready);await page.waitForFunction(()=>!document.querySelector('#eventsTab').hidden);assert.equal(await page.evaluate(()=>window.__video===document.querySelector('video')),true);assert.equal(await page.locator('video').evaluate(v=>v.currentTime),1);await page.locator('#eventsTab').click();assert.equal(await page.locator('#experienceEvents').isVisible(),true);assert.equal(await page.locator('#follow').isHidden(),true);});
 await check('event and evidence seek to their exact source time without automatic playback',async()=>{await page.locator('.event-title').click();assert.equal(await page.locator('video').evaluate(v=>v.currentTime),2);assert.equal(await page.locator('video').evaluate(v=>v.paused),true);await page.locator('.event-evidence summary').click();await page.locator('.event-evidence-row .event-jump').nth(1).click();assert.equal(await page.locator('video').evaluate(v=>v.currentTime),3);assert.match(await page.locator('.event-quote').textContent(),/我不知道/);});
 await check('agent text is escaped and optional questions do not block completed UI',async()=>{assert.equal(await page.locator('#experienceEvents img').count(),0);assert.match(await page.locator('#experienceEvents').textContent(),/<img src=x/);assert.match(await page.locator('.event-footnote').textContent(),/不影响本轮预处理完成/);assert.equal(await page.locator('#experienceEvents input, #experienceEvents textarea').count(),0);});
 await page.screenshot({path:path.join(out,'events-1440.png')});
 await check('tab keyboard navigation includes events and never steals video controls',async()=>{await page.locator('#eventsTab').focus();await page.keyboard.press('ArrowLeft');assert.equal(await page.locator('#transcriptTab').getAttribute('aria-selected'),'true');await page.keyboard.press('End');assert.equal(await page.locator('#eventsTab').getAttribute('aria-selected'),'true');});
 await check('stale result disappears while active and returns to usable original transcript',async()=>{await page.evaluate(()=>window.__snapshot.preprocessing={state:'stale',label:'需重新预处理',reason:'素材已更新，旧结果已保留。'});await page.waitForFunction(()=>document.querySelector('#eventsTab').hidden);assert.equal(await page.locator('#lines').isVisible(),true);assert.match(await page.locator('#preprocessingNotice').textContent(),/需重新预处理/);assert.equal(await page.locator('video').evaluate(v=>v.currentTime),3);});
 await check('failure leaves both original tabs available',async()=>{await page.evaluate(()=>window.__snapshot.preprocessing={state:'failed',label:'预处理未完成',reason:'合成失败'});await page.waitForFunction(()=>document.querySelector('#preprocessingNotice').textContent.includes('合成失败'));await page.locator('#inputTab').click();assert.equal(await page.locator('#inputTimelinePanel').isVisible(),true);await page.locator('#transcriptTab').click();assert.equal(await page.locator('#lines').isVisible(),true);});
 await check('narrow and dark view contains all content within the scrollable event panel',async()=>{await page.evaluate(value=>window.__snapshot.preprocessing=value,ready);await page.waitForFunction(()=>!document.querySelector('#eventsTab').hidden);await page.setViewportSize({width:560,height:700});await page.locator('#themeButton').click();await page.locator('#eventsTab').click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.ok(await page.locator('#experienceEvents').evaluate(el=>el.clientHeight>50&&el.scrollHeight>el.clientHeight));await page.locator('.event-evidence summary').click();await page.screenshot({path:path.join(out,'events-dark-560.png')});});
 await check('exported review shows results without a native bridge',async()=>{await page.setViewportSize({width:1440,height:900});await page.goto(origin+'/ready-portable');await page.locator('#eventsTab').click();assert.equal(await page.locator('.experience-event').count(),1);await page.locator('.event-title').click();});
 await check('word quote arrival preserves original transcript and seeks only to excerpt start',async()=>{
   await page.goto(origin);await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
   await page.locator('video').evaluate(v=>{v.currentTime=1;window.__video=v;});
   await page.evaluate(value=>window.__snapshot.preprocessing=value,excerptReady);
   await page.waitForFunction(()=>!document.querySelector('#eventsTab').hidden);
   assert.equal(await page.evaluate(()=>window.__video===document.querySelector('video')),true);
   assert.equal(await page.locator('video').evaluate(v=>v.currentTime),1);
   await page.locator('#eventsTab').click();await page.locator('.event-evidence summary').click();
   const quote=page.locator('.event-evidence-row .event-jump');assert.match(await quote.textContent(),/原话节选/);
   assert.equal(await page.locator('.event-quote').textContent(),'这是后半句。<img src=x>');
   assert.equal(await page.locator('.event-evidence-row img').count(),0);
   await quote.click();assert.ok(Math.abs(await page.locator('video').evaluate(v=>v.currentTime)-8.2)<.00001);
   assert.equal(await page.locator('video').evaluate(v=>v.paused),true);
   await page.screenshot({path:path.join(out,'word-quote-1440.png')});
   await page.locator('#transcriptTab').click();assert.equal(await page.locator('.line').count(),1);
   assert.match(await page.locator('#lines').textContent(),/我不知道这个按钮的状态/);
 });
 await check('exported word quotes retain label and exact local seek',async()=>{
   await page.goto(origin+'/words-portable');await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
   await page.locator('#eventsTab').click();await page.locator('.event-evidence summary').click();
   const quote=page.locator('.event-evidence-row .event-jump');assert.match(await quote.textContent(),/原话节选/);
   await quote.click();assert.ok(Math.abs(await page.locator('video').evaluate(v=>v.currentTime)-8.2)<.00001);
   assert.equal(await page.locator('video').evaluate(v=>v.paused),true);
 });
 await page.goto(origin+'/ready');await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
 await page.evaluate(value=>window.__snapshot.preprocessing=structuredClone(value),ready);
 await page.locator('#eventsTab').click();
 await check('editable event has all fields, cancellation and concurrent-save error keep text',async()=>{
   await page.locator('.event-edit').click();await page.locator('#eventEdittitle').fill('未保存标题');await page.locator('#cancelEventEdit').click();
   assert.equal(await page.locator('.event-title').textContent(),result.events[0].title);
   await page.locator('.event-edit').click();await page.locator('#eventEditend').fill('00:00:01');await page.locator('#saveEventEdit').click();
   assert.match(await page.locator('#eventEditError').textContent(),/结束时间/);
   await page.locator('#eventEditstart').fill('00:00:01.500');await page.locator('#eventEditend').fill('00:00:05.250');
   await page.locator('#eventEdittitle').fill('红点含义不清楚');await page.locator('#eventEditsummary').fill('查看经营界面的选中与上架。');
   await page.locator('#eventEditissue').fill('选中状态难辨认；红点含义与位置不清楚。');await page.locator('#eventEditnotes').fill('尚未核实实际键位冲突。');
   await page.evaluate(()=>window.__editError='体验事件已更新，请重新打开');await page.locator('#saveEventEdit').click();
   assert.equal(await page.locator('#eventEdittitle').inputValue(),'红点含义不清楚');assert.equal(await page.locator('#eventDialog').isVisible(),true);
   await page.evaluate(()=>window.__editError='');await page.locator('#saveEventEdit').click();await page.waitForFunction(()=>!document.querySelector('#eventDialog').open);
   const saved=await page.evaluate(()=>window.__editRequest);assert.equal(saved.fields.start,1.5);assert.equal(saved.fields.end,5.25);
   assert.equal(saved.result_sha256,'synthetic-result');assert.match(await page.locator('.event-issue').textContent(),/红点含义/);
   assert.match(await page.locator('.event-meta').textContent(),/已校准/);
   const colors=await page.locator('.experience-event').evaluate(el=>({description:getComputedStyle(el.querySelector('.event-description')).color,notes:getComputedStyle(el.querySelector('.event-notes')).color}));assert.notEqual(colors.description,colors.notes);
   assert.equal(await page.locator('.event-evidence').getAttribute('open'),null);
 });
 await check('long evidence keeps collapse at the top, then returns to its event',async()=>{
   await page.evaluate(()=>{const e=window.__snapshot.preprocessing.result.events[0];e.evidence=Array.from({length:20},(_,i)=>({kind:'quote',start:2,end:4,text:`合成证据 ${i+1}：原话用于验证滚动和收起。`}));});
   await page.waitForFunction(()=>document.querySelectorAll('.event-evidence-row').length===20);
   await page.locator('.event-evidence summary').click();
   await page.locator('#experienceEvents').evaluate(panel=>panel.scrollTop=900);
   const top=await page.locator('.event-evidence summary').boundingBox(),panel=await page.locator('#experienceEvents').boundingBox();
   assert.ok(Math.abs(top.y-panel.y)<3);assert.match(await page.locator('.event-evidence summary').innerText(),/收起证据/);
   await page.screenshot({path:path.join(out,'sticky-evidence.png')});
   await page.locator('.event-evidence summary').click();await page.waitForTimeout(100);assert.equal(await page.locator('.event-evidence').getAttribute('open'),null);
   assert.equal(await page.locator('.event-title').isVisible(),true);
   await page.locator('.event-edit').click();await page.screenshot({path:path.join(out,'event-edit.png')});await page.locator('#cancelEventEdit').click();
 });
 await page.goto(origin+'/ready-portable');await page.locator('#eventsTab').click();assert.equal(await page.locator('.event-edit').count(),0);
 assert.deepEqual(report.errors,[]);report.pass=true;
}
main().catch(error=>{report.error=String(error.stack||error);process.exitCode=1;}).finally(async()=>{fs.writeFileSync(path.join(out,'browser-acceptance.json'),JSON.stringify(report,null,2));if(browser)await browser.close();server.close();console.log(JSON.stringify(report));});
