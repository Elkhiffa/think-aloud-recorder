'use strict';
// Actual review assets and browser media; synthetic payload and native bridge.
// No OBS, microphone, keyboard listener, private recording or cloud request.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),read=name=>fs.readFileSync(path.join(root,name),'utf8');
const out=path.join(root,'work/startup-review');fs.mkdirSync(out,{recursive:true});
const media=fs.readFileSync(path.join(root,'docs/prototypes/input-review/demo.mp4'));
const fixture=(variant='normal')=>({title:'启动准备 · 合成验证',game:'合成游戏',created:'2026-09-24T10:00:00',desktop:true,test:true,video:'/demo.mp4',
 segments:[{start:.75,end:1.2,text:'时间保持原样的合成原话'}],transcription:{state:'ready'},
 inputs:{version:1,timebase:'video_seconds',state:variant==='failed'?'failed':'complete',duration:32,video_duration:32,
 alignment:{source:variant==='uncalibrated'?'uncalibrated':variant==='manual'?'manual':'measured',offset_seconds:variant==='manual'?-.2:1.5},
 intervals:[{id:'synthetic-key',device:'keyboard',code:'E',label:'E',kind:'button',start:.6,end:.8}],
 gaps:[{start:0,end:.5,type:'capture',reason:'录像启动确认前尚未采集操作'},{start:.3,end:6,type:'focus',reason:'目标窗口不在前台'},{start:12,end:13,type:'capture',reason:'实际中断'}]}});
function html(variant){const data=fixture(variant);const values={TITLE:data.title,DATA:JSON.stringify(data),CSS:read('ui/review.css'),JS:read('ui/review.js'),PLYR_CSS:read('ui/vendor/plyr/plyr.css'),PLYR_JS:read('ui/vendor/plyr/plyr.min.js'),PLYR_SVG:read('ui/vendor/plyr/plyr.svg'),LICENSE:'Synthetic acceptance'};return read('player.html').replace(/%%([A-Z_]+)%%/g,(_,key)=>values[key]);}
const server=http.createServer((request,response)=>{if(request.url==='/demo.mp4'){
 response.setHeader('Content-Type','video/mp4');response.setHeader('Accept-Ranges','bytes');
 const range=/^bytes=(\d+)-(\d*)$/.exec(request.headers.range||'');if(range){const start=+range[1],end=Math.min(range[2]?+range[2]:media.length-1,media.length-1);response.writeHead(206,{'Content-Range':`bytes ${start}-${end}/${media.length}`,'Content-Length':end-start+1});response.end(media.subarray(start,end+1));}else response.end(media);return;}
 response.setHeader('Content-Type','text/html; charset=utf-8');response.end(html(request.url.slice(1)));
});
const checks=[],errors=[];let browser,origin;
async function check(name,fn){try{await fn();checks.push({name,pass:true});}catch(error){checks.push({name,pass:false,error:error.stack});}}
async function pageFor(variant='normal',delayed=false){
 const page=await browser.newPage({viewport:{width:1400,height:820}});page.on('pageerror',error=>errors.push(error.message));
 await page.addInitScript(data=>{window.__fixture=data;window.pywebview={api:{get_layout:async()=>({ok:true,data:{}}),save_layout:async()=>({ok:true}),ready:async()=>({ok:true}),get_snapshot:async()=>({ok:true,data:window.__fixture})}};},fixture(variant));
 let release;if(delayed){const barrier=new Promise(resolve=>release=resolve);await page.route('**/demo.mp4',async route=>{await barrier;await route.continue();});}
 await page.goto(origin+'/'+variant,{waitUntil:'domcontentloaded'});return {page,release};
}
const loaded=page=>page.waitForFunction(()=>{const v=document.querySelector('video');return v.readyState>=2&&!v.seeking;});
const position=page=>page.locator('video').evaluate(v=>({time:v.currentTime,paused:v.paused}));
(async()=>{try{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin=`http://127.0.0.1:${server.address().port}`;
 browser=await chromium.launch({channel:'msedge',headless:true});
 await check('open at calibrated preparation end, stay paused and retain real focus gap',async()=>{
  const {page}=await pageFor();await loaded(page);assert.deepEqual(await position(page),{time:2,paused:true});
  assert.match(await page.locator('#status').textContent(),/准备完成/);
  assert.equal(await page.locator('.timeline-gap.preparation').textContent(),'录制准备');
  assert.equal(await page.locator('.timeline-gap.preparation').evaluate(el=>getComputedStyle(el).backgroundImage),'none');
  assert.match(await page.locator('#timelineState').textContent(),/2 处缺口/);
  assert.ok(await page.locator('.timeline-gap').filter({hasText:'已切出目标程序'}).count()>0);
  await page.screenshot({path:path.join(out,'preparation-light.png')});
  await page.locator('video').evaluate(v=>v.currentTime=0);await loaded(page);assert.equal((await position(page)).time,0);
  await page.evaluate(()=>{window.__fixture.inputs.alignment={source:'manual',offset_seconds:4};window.__fixture.segments.push({start:3,end:4,text:'后来的合成转写'});});
  await page.waitForFunction(()=>document.querySelector('#lineCount').textContent==='2 条');assert.equal((await position(page)).time,0);
  await page.close();
 });
 for(const [variant,expected] of [['manual',.3],['failed',0],['uncalibrated',0]])await check(`${variant}: initial playback respects calibration and evidence`,async()=>{
  const {page}=await pageFor(variant);await loaded(page);assert.ok(Math.abs((await position(page)).time-expected)<.001);
  if(variant==='failed')assert.equal(await page.locator('.timeline-gap.preparation').count(),0);await page.close();
 });
 await check('explicit transcript click before media loads takes priority over automatic start',async()=>{
  const {page,release}=await pageFor('normal',true);
  await page.locator('#transcriptTab').click();await page.locator('#lines .line').first().click();release();await loaded(page);
  const time=(await position(page)).time;assert.ok(time>=.74&&time<1.5,`unexpected time ${time}`);await page.close();
 });
 await check('early interaction without a seek preserves zero rather than jumping afterward',async()=>{
  const {page,release}=await pageFor('normal',true);await page.locator('#themeButton').click();release();await loaded(page);
  assert.deepEqual(await position(page),{time:0,paused:true});await page.close();
 });
 await check('no browser errors',()=>assert.deepEqual(errors,[]));
}finally{if(browser)await browser.close();server.close();}
const report={scope:'Production browser with synthetic fixtures; no native OBS or capture.',passed:checks.every(item=>item.pass),checks,errors};fs.writeFileSync(path.join(out,'acceptance.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));if(!report.passed)process.exitCode=1;
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
