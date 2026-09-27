'use strict';
// Production review UI with pathological synthetic history, never user media.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const {compactGaps,gapVisualBands}=require('../ui/review.js');
const root=path.resolve(__dirname,'..'),read=file=>fs.readFileSync(path.join(root,file),'utf8');
const point=t=>({start:t,end:t,type:'capture',reason:'前台归属无法确认，此次输入未记录'});
const legacy=[{start:7,end:3700,type:'focus',reason:'目标窗口不在前台，操作采集已暂停'},...Array.from({length:466727},(_,i)=>point(100+i/130))];
let start=performance.now();const compact=compactGaps(legacy),compactMs=performance.now()-start;
assert.equal(compact.length,1);assert.equal(compact[0].discarded_events,466727);assert.equal(legacy[0].type,'focus');
assert.deepEqual(compactGaps(compact),compact);
assert.deepEqual(compactGaps([{start:0,end:10,type:'disconnect',device:'xbox'},point(1)]).length,2);
const density=Array.from({length:50000},(_,i)=>point(i/1000));
for(const scale of [12,64,240]){const bands=gapVisualBands(density,0,50,scale);assert.equal(bands.length,1);assert.ok(bands[0].end<=50);}
const data={title:'合成缺口压力测试',game:'合成测试',test:true,desktop:false,created:'2026-09-26T12:00:00',video:'/demo.mp4',segments:[],
  inputs:{version:1,state:'complete',duration:3775,timebase:'video_seconds',intervals:[],gaps:legacy}};
const values={TITLE:data.title,DATA:JSON.stringify(data),CSS:read('ui/review.css'),JS:read('ui/review.js'),PLYR_CSS:read('ui/vendor/plyr/plyr.css'),PLYR_JS:read('ui/vendor/plyr/plyr.min.js'),PLYR_SVG:read('ui/vendor/plyr/plyr.svg'),LICENSE:'Synthetic performance fixture'};
const html=read('player.html').replace(/%%([A-Z_]+)%%/g,(_,key)=>values[key]),media=fs.readFileSync(path.join(root,'docs/prototypes/input-review/demo.mp4'));
const server=http.createServer((req,res)=>{if(req.url==='/demo.mp4'){res.setHeader('Content-Type','video/mp4');res.end(media);}else{res.setHeader('Content-Type','text/html;charset=utf-8');res.end(html);}});
let browser;
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));browser=await chromium.launch({headless:true,channel:'msedge'});
 const page=await browser.newPage({viewport:{width:1280,height:800}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{window.__longTasks=[];new PerformanceObserver(list=>window.__longTasks.push(...list.getEntries().map(e=>e.duration))).observe({type:'longtask',buffered:true});});
 start=performance.now();await page.goto(`http://127.0.0.1:${server.address().port}`,{timeout:30000});
 await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
 const loadMs=performance.now()-start;
 assert.match(await page.locator('#timelineState').textContent(),/未保存有效操作记录/);
 assert.ok(await page.locator('#timelineGaps .timeline-gap').count()<=2);
 const measured=await page.evaluate(async()=>{
   const timeline=document.querySelector('#inputTimeline'),rect=timeline.getBoundingClientRect();
   const start=performance.now();window.__longTasks=[];let maxNodes=0;
   for(let i=0;i<20;i++){
     for(let j=0;j<8;j++)timeline.dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,clientX:rect.left+10,clientY:rect.top+150,deltaY:i%2?120:-120}));
     await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);
     maxNodes=Math.max(maxNodes,document.querySelectorAll('#timelineGaps .timeline-gap').length);
   }
   return {zoomMs:performance.now()-start,maxNodes,maxLongTask:Math.max(0,...window.__longTasks),scale:document.querySelector('#timelineScale').textContent};
 });
 assert.ok(measured.maxNodes<=2,JSON.stringify(measured));assert.ok(measured.zoomMs<5000,JSON.stringify(measured));assert.ok(measured.maxLongTask<500,JSON.stringify(measured));assert.deepEqual(errors,[]);
 const out=path.join(root,'work','input-gap-recovery');fs.mkdirSync(out,{recursive:true});await page.screenshot({path:path.join(out,'legacy-gap-review.png')});
 const report={passed:true,scope:'Synthetic production Edge review; 466727 rejected samples, no user recording.',compactMs,loadMs,...measured,errors};fs.writeFileSync(path.join(out,'browser-performance.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 await browser.close();server.close();
})().catch(async error=>{console.error(error);if(browser)await browser.close();server.close();process.exitCode=1;});
