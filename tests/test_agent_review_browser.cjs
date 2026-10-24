'use strict';
// Production review assets, real Edge/media, synthetic external-agent results.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(process.env.REVIEW_ASSET_ROOT||path.join(__dirname,'..')),read=name=>fs.readFileSync(path.join(root,name),'utf8'),out=path.resolve(process.env.REVIEW_TEST_OUTPUT||path.join(__dirname,'..','work','agent-integration'));
fs.mkdirSync(out,{recursive:true});
const result={version:1,session_id:'synthetic-agent',revision:'fixture',summary:'仅检查了合成按钮的状态变化。',coverage:{video_ranges:[{start:2,end:4}],transcript:'full',inputs:'none',limitations:['合成数据，无真实游戏结论。']},events:[{id:'e1',start:2,end:4,title:'按钮状态难以判断',summary:'记录者说不知道是否成功。<img src=x onerror=alert(1)>',basis:'explicit',kind:'friction',context:'目标需核对。',evidence:[{kind:'quote',ref:'t000001',start:2,end:4,text:'我不知道这个按钮的状态。'},{kind:'video',start:3,end:3,text:'合成按钮保持在原处。'}]}],questions:[{id:'q1',event_id:'e1',question:'后来怎样确认？',reason:'片段尚未说明。'}],ideas:[{id:'h1',event_id:'e1',idea:'比较状态提示的辨识度。',reason:'以原话为线索，待进一步验证。'}]};
const ready={editing:{result_sha256:'synthetic-result',corrections_revision:''},state:'complete',label:'已整理 · 1 个体验事件',events:1,questions:1,ideas:1,result};
// A single raw segment with distant phrases; only the later words support this event.
const excerptReady=structuredClone(ready);
Object.assign(excerptReady.result.events[0],{start:8,end:9,evidence:[{kind:'quote_words',ref:'t000001',word_range:[3,6],start:8.2,end:8.8,text:'这是后半句。<img src=x>',speaker_id:0}]});
const data={id:'synthetic-agent',game:'合成接口验证',title:'合成接口验证',test:true,desktop:true,video:'/demo.mp4',transcription:{state:'ready'},segments:[{start:2,end:4,text:'我不知道这个按钮的状态。'}],inputs:{state:'disabled',intervals:[],gaps:[],duration:12},preprocessing:{state:'none'}};
function render(url){const d=structuredClone(data);if(url.includes('ready'))d.preprocessing=ready;if(url.includes('words'))d.preprocessing=excerptReady;if(url.includes('portable'))d.desktop=false;if(url.includes('initial'))d.initial_time=3;const vars={TITLE:d.title,DATA:JSON.stringify(d).replaceAll('<','\\u003c'),CSS:read('ui/review.css'),JS:read('ui/review.js'),FINDINGS_JS:read('ui/findings.js'),FINDINGS_CSS:read('ui/findings.css'),FONTS: '', PLYR_CSS:read('ui/vendor/plyr/plyr.css'),PLYR_JS:read('ui/vendor/plyr/plyr.min.js'),PLYR_SVG:read('ui/vendor/plyr/plyr.svg'),LICENSE:'Synthetic test'};return read('player.html').replace(/%%([A-Z_]+)%%/g,(_,k)=>vars[k]);}
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
 await check('agent text is escaped and optional questions do not block completed UI',async()=>{assert.equal(await page.locator('#experienceEvents img').count(),0);assert.match(await page.locator('#experienceEvents').textContent(),/<img src=x/);assert.match(await page.locator('.event-footnote').textContent(),/不影响本轮整理完成/);assert.equal(await page.locator('#experienceEvents input, #experienceEvents textarea').count(),0);});
 await page.screenshot({path:path.join(out,'events-1440.png')});
 await check('tab keyboard navigation includes events and never steals video controls',async()=>{await page.locator('#eventsTab').focus();await page.keyboard.press('ArrowLeft');assert.equal(await page.locator('#transcriptTab').getAttribute('aria-selected'),'true');await page.keyboard.press('End');assert.equal(await page.locator('#eventsTab').getAttribute('aria-selected'),'true');});
 await check('stale result disappears while active and returns to usable original transcript',async()=>{await page.evaluate(()=>window.__snapshot.preprocessing={state:'stale',label:'需重新预处理',reason:'素材已更新，旧结果已保留。'});await page.waitForFunction(()=>document.querySelector('#eventsTab').hidden);assert.equal(await page.locator('#lines').isVisible(),true);assert.match(await page.locator('#preprocessingNotice').textContent(),/需重新预处理/);assert.equal(await page.locator('video').evaluate(v=>v.currentTime),3);});
 await check('failure leaves both original tabs available',async()=>{await page.evaluate(()=>window.__snapshot.preprocessing={state:'failed',label:'整理未完成',reason:'合成失败'});await page.waitForFunction(()=>document.querySelector('#preprocessingNotice').textContent.includes('合成失败'));await page.locator('#inputTab').click();assert.equal(await page.locator('#inputTimelinePanel').isVisible(),true);await page.locator('#transcriptTab').click();assert.equal(await page.locator('#lines').isVisible(),true);});
 await check('narrow view contains all content within the scrollable event panel',async()=>{await page.evaluate(value=>window.__snapshot.preprocessing=value,ready);await page.waitForFunction(()=>!document.querySelector('#eventsTab').hidden);await page.setViewportSize({width:560,height:700});await page.locator('#eventsTab').click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.ok(await page.locator('#experienceEvents').evaluate(el=>el.clientHeight>50&&el.scrollHeight>el.clientHeight));await page.locator('.event-evidence summary').click();await page.screenshot({path:path.join(out,'events-560.png')});});
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
 await check('insight evidence opens the review paused at its moment',async()=>{
   await page.goto(origin+'/initial');await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
   await page.waitForFunction(()=>Math.abs(document.querySelector('video').currentTime-3)<.01);
   assert.equal(await page.locator('video').evaluate(v=>v.paused),true);
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
 await check('v2 judgments render and seek said and referred times',async()=>{
   /** 触发路径：用户在回看窗口打开体验事件 → 阅读判断实例并点击“说”和“指” → 两种时间不同 → 混用时间会定位到错误片段。 */
   const judgments=structuredClone(excerptReady);
   judgments.result.version=2;
   judgments.notice='整理后同步偏移／记录者已改动，整理结果里的操作时间可能有偏差';
   judgments.result.instances=[{id:'i01',event_id:'e1',said:[{kind:'quote_words',ref:'t000001',word_range:[3,6],start:8.2,end:8.8,text:'这是后半句。'}],refers_to:{start:3,end:4,basis:'retrospective'},screen:null,elements:[],kind:'confusion',statement:'回顾刚才的按钮状态。',issue_tags:['TA-03'],evidence:[],confidence:'high'},{id:'i02',event_id:'e1',said:[{kind:'quote',ref:'t000001',start:5,end:6,text:'又是前两天那个问题。'}],refers_to:{start:null,end:null,basis:'earlier_session',note:'前两天那场'},compare_to:{start:2,end:2.5},screen:null,elements:[],kind:'negative',statement:'认为同样的问题又出现了。',issue_tags:[],evidence:[],confidence:'medium'}];
   await page.goto(origin);await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
   await page.evaluate(value=>window.__snapshot.preprocessing=value,judgments);
   // A v2 result adds 问题 beside 体验事件; both views share one panel and one filter row.
   await page.waitForFunction(()=>!document.querySelector('#problemsTab').hidden);
   assert.equal(await page.locator('#problemsTab').innerText(),'问题 2');
   await page.locator('#problemsTab').click();
   const instance=page.locator('[data-item="i01"]');
   assert.match(await instance.locator('xpath=ancestor::section[1]').locator('.fd-name').innerText(),/困惑/);
   assert.match(await instance.innerText(),/这是后半句。/);assert.match(await instance.innerText(),/回顾刚才的按钮状态/);
   assert.match(await page.locator('#preprocessingNotice').innerText(),/同步偏移／记录者已改动/);
   await instance.locator('.fd-at').click();assert.ok(Math.abs(await page.locator('video').evaluate(v=>v.currentTime)-8.2)<.00001);
   await instance.getByText('指 00:00:03–00:00:04').click();assert.equal(await page.locator('video').evaluate(v=>v.currentTime),3);
   assert.equal(await page.locator('video').evaluate(v=>v.paused),true);
   // 指向本场之前的判断没有本场时间，只显示说明；对照时刻可以定位。
   const earlier=page.locator('[data-item="i02"]');
   assert.match(await earlier.locator('xpath=ancestor::section[1]').locator('.fd-name').innerText(),/负面评价/);assert.match(await earlier.innerText(),/指本场之前/);
   await earlier.getByText('对照 00:00:02').click();assert.equal(await page.locator('video').evaluate(v=>v.currentTime),2);
   // The kind filter narrows both views.
   await page.locator('[data-filter="negative"]').click();
   assert.equal(await page.locator('#experienceEvents .fd-row').count(),1);
   await page.locator('#eventsTab').click();
   assert.equal(await page.locator('[data-filter="negative"]').getAttribute('aria-pressed'),'true');
   await page.locator('[data-filter="negative"]').click();
   await page.screenshot({path:path.join(out,'judgment-instances-1440.png')});
 });
 await check('a bug sits in the Bug group and in its own kind group; the Bug chip filters to bugs',async()=>{
   /** 触发路径：用户在回看里看一条“设计没问题、实现出了问题”的判断 → 它在 Bug 组里写着原本的类型，在类型组里带 Bug 标记。 */
   const bugs=structuredClone(excerptReady);bugs.result.version=2;bugs.bugs={i01:'suspected',i02:'explicit'};
   bugs.result.instances=[{id:'i01',event_id:'e1',said:[{kind:'quote',ref:'t000001',start:2,end:4,text:'这个按钮又没反应。'}],refers_to:{start:2,end:4,basis:'same_time'},screen:null,elements:[],kind:'obstacle',statement:'按钮时灵时不灵。',issue_tags:[],evidence:[],confidence:'high'},
     {id:'i02',event_id:'e1',said:[{kind:'quote',ref:'t000001',start:5,end:6,text:'这是 bug 吧，字被裁了。'}],refers_to:{start:5,end:6,basis:'same_time'},screen:null,elements:[],kind:'observation',statement:'按钮文字被裁切。',issue_tags:['BUG'],evidence:[],confidence:'high'},
     {id:'i03',event_id:'e1',said:[{kind:'quote',ref:'t000001',start:7,end:8,text:'这个入口在哪？'}],refers_to:{start:7,end:8,basis:'same_time'},screen:null,elements:[],kind:'confusion',statement:'找不到入口。',issue_tags:[],evidence:[],confidence:'high'}];
   await page.setViewportSize({width:1440,height:900});await page.goto(origin);await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
   await page.evaluate(value=>window.__snapshot.preprocessing=value,bugs);
   await page.waitForFunction(()=>!document.querySelector('#problemsTab').hidden);await page.locator('#problemsTab').click();
   assert.equal(await page.locator('#problemsTab').innerText(),'问题 2','bugs are not counted twice');
   assert.deepEqual(await page.locator('#experienceEvents .fd-view>.fd-group .fd-name').allInnerTexts(),['困惑','阻碍','Bug','其他']);
   const bugGroup=page.locator('#experienceEvents .fd-view>.fd-group.k-bug');
   assert.deepEqual(await bugGroup.locator('.fd-row').evaluateAll(rows=>rows.map(row=>row.dataset.item)),['i01','i02']);
   assert.match(await bugGroup.locator('[data-item="i01"] .fd-kind').innerText(),/阻碍 · 疑似/);
   assert.match(await bugGroup.locator('[data-item="i02"] .fd-kind').innerText(),/^观察$/);
   assert.equal(await page.locator('#experienceEvents .fd-group.k-obstacle [data-item="i01"] .fd-bug-mark').innerText(),'疑似 Bug');
   assert.equal(await page.locator('#experienceEvents .fd-group.k-other [data-item="i02"] .fd-bug-mark').innerText(),'Bug');
   assert.equal(await page.locator('#experienceEvents .fd-group.k-confusion .fd-bug-mark').count(),0);
   assert.equal((await page.locator('[data-filter="bug"]').textContent()).trim(),'Bug 2');
   await page.locator('[data-filter="bug"]').click();
   assert.deepEqual(await page.locator('#experienceEvents .fd-view>.fd-group .fd-name').allInnerTexts(),['阻碍','Bug','其他'],'the Bug chip keeps only bugs, in every group they belong to');
   await page.locator('#eventsTab').click();
   assert.match(await page.locator('#experienceEvents .fd-sec .fd-legend').first().innerText(),/2 Bug/);
   await page.locator('[data-filter="bug"]').click();
 });
 await check('long event sections: heads stick, next heads wait at the bottom, a toggle keeps its head still',async()=>{
   /** 触发路径：用户在回看里展开一个很长的体验事件 → 往下读 → 要能看到当前事件和问题类型、找到下一个，并从吸顶标题直接收起，标题不跳。 */
   const long=structuredClone(ready);long.result.version=2;
   const kinds=['confusion','obstacle','cost','negative'];
   long.result.events=Array.from({length:4},(_,e)=>({id:'e'+e,start:e*3,end:e*3+3,title:'合成长事件 '+e,summary:'合成概述。',basis:'explicit',kind:'friction',evidence:[]}));
   long.result.instances=long.result.events.flatMap((event,e)=>Array.from({length:40},(_,i)=>({id:`i${e}_${i}`,event_id:event.id,kind:kinds[Math.floor(i/10)],
     said:[{kind:'quote',ref:'t000001',start:event.start+i*0.05,end:event.start+i*0.05+0.02,text:'合成原话 '+i}],refers_to:{start:event.start+i*0.05,end:event.start+i*0.05+0.02,basis:'same_time'},
     screen:null,elements:[],statement:'合成陈述，用来把这一段撑得足够长。'.repeat(2),issue_tags:[],evidence:[],confidence:'high'})));
   await page.setViewportSize({width:1280,height:800});await page.goto(origin);await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
   await page.evaluate(value=>window.__snapshot.preprocessing=value,long);
   await page.waitForFunction(()=>!document.querySelector('#eventsTab').hidden);await page.locator('#eventsTab').click();
   const state=await page.locator('#experienceEvents').evaluate(async panel=>{
     const wait=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
     const head=id=>panel.querySelector(`.fd-view>[data-sec="${id}"] [data-toggle]`);
     if(!panel.querySelector('[data-sec="e1"]').classList.contains('is-open'))head('e1').click();await wait();
     const second=panel.querySelector('[data-sec="e1"] .fd-body>.fd-group:nth-child(2)');
     panel.scrollTop+=panel.querySelector('[data-sec="e1"] .fd-body>.fd-group').getBoundingClientRect().top-panel.getBoundingClientRect().top+80;await wait();
     const bar=panel.querySelector('.fd-bar').getBoundingClientRect(),stuck=panel.querySelector('.is-stuck');
     const pins=[...panel.querySelectorAll('.fd-next .fd-pin')].map(pin=>pin.textContent.trim());
     const pinGroup=panel.querySelector('.fd-next .fd-pin .fd-gh'),realGroup=second.querySelector('.fd-gh');
     const look=node=>{const s=getComputedStyle(node);return [s.backgroundColor,s.fontSize,s.paddingLeft,s.borderLeftWidth].join('|');};
     const above=document.elementFromPoint(bar.left+bar.width/2,bar.top+2)?.closest('.fd-bar')!==null;
     // Collapse from the stuck head near the end: the head stays put and a run-out holds it.
     panel.scrollTop=panel.scrollHeight;await wait();
     const last=panel.querySelector('.is-stuck [data-toggle]'),before=last.getBoundingClientRect().top,id=last.dataset.toggle;last.click();await wait();
     const after=head(id).getBoundingClientRect().top,runOut=panel.querySelector('.fd-spacer')?.offsetHeight||0,held=panel.scrollTop;
     panel.scrollTop+=300;await wait();const down=panel.scrollTop-held;
     return {stuck:stuck?.dataset.sec,pins,same:look(pinGroup)===look(realGroup),above,before,after,runOut,down};});
   assert.equal(state.stuck,'e1','the open section head sticks under the filter row');
   assert.equal(state.pins.length,2,'the next problem type and the next section wait at the bottom');assert.match(state.pins[1],/合成长事件 2/);
   assert.equal(state.same,true,'a pinned head looks like the head itself');
   assert.equal(state.above,true,'nothing scrolls above the filter row');
   assert.ok(Math.abs(state.after-state.before)<=1,'collapsing from a stuck head keeps it still');
   assert.ok(state.runOut>0&&state.down===0,'a run-out holds it and cannot be scrolled down');
   const chip=page.locator('[data-filter="cost"]'),size=await chip.boundingBox();await chip.hover();
   assert.deepEqual(await chip.boundingBox(),size,'hover never resizes a chip');
   await page.screenshot({path:path.join(out,'long-sections-1280.png')});
 });
 assert.deepEqual(report.errors,[]);report.pass=true;
}
main().catch(error=>{report.error=String(error.stack||error);process.exitCode=1;}).finally(async()=>{fs.writeFileSync(path.join(out,'browser-acceptance.json'),JSON.stringify(report,null,2));if(browser)await browser.close();server.close();console.log(JSON.stringify(report));});
