/* Actual recording UI with an explicitly synthetic bridge; no device access. */
const assert=require('node:assert/strict'),fs=require('node:fs'),http=require('node:http'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'work/microphone-acceptance');
fs.mkdirSync(out,{recursive:true});
const server=http.createServer((req,res)=>{
 const name=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
 if(!name.startsWith(path.join(root,'ui')+path.sep)||!fs.existsSync(name)){res.writeHead(404);res.end();return;}
 res.setHeader('Content-Type',({'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript'})[path.extname(name)]||'application/octet-stream');res.end(fs.readFileSync(name));
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1240,height:960}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.addInitScript(()=>{
   window.fixture={calls:0,hold:false,level:{session_id:'synthetic-recording',state:'signal',quiet_seconds:0,level:.72,name:'示例麦克风（合成测试）'},state:{
    config:{game:'麦克风反馈 · 合成测试',vault:'F:\\synthetic-only',configured:true,mic:'synthetic-mic',source:'游戏窗口',transcription_provider:'later'},
    presets:[{id:'synthetic-preset',name:'麦克风反馈 · 合成测试'}],active_preset_id:'synthetic-preset',
    activity:{kind:'recording',busy:false,status:'录制中',active_id:'synthetic-recording',elapsed_seconds:84},
    readiness:{ready:false,checking:false,errors:[]},sessions:[],devices:{mic:[],window:[],monitor:[]},model:{state:'missing'},capabilities:{cloud_key:false}
   }};
   window.pywebview={api:{get_state:async()=>({ok:true,data:structuredClone(fixture.state)}),get_microphone_state:async()=>{
    fixture.calls++;if(fixture.hold)await new Promise(resolve=>fixture.release=resolve);
    return {ok:true,data:structuredClone(fixture.level)};
   }}};
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/ui/index.html`);
  const state=async(value,extra={})=>{
   await page.evaluate(({value,extra})=>Object.assign(fixture.level,{state:value,level:0},extra),{value,extra});
   await page.waitForFunction(v=>document.querySelector('#microphoneMonitor').dataset.state===v,value);
  };
  await page.waitForFunction(()=>document.querySelector('#microphoneMonitor').dataset.state==='signal');
  assert.equal(await page.locator('#microphoneLevel').getAttribute('aria-valuenow'),'72');
  assert.equal(await page.locator('#recordButton').isEnabled(),true);
  await page.screenshot({path:path.join(out,'recording-signal.png')});
  const height=await page.locator('#capturePanel').evaluate(el=>el.offsetHeight);
  for(const value of ['quiet','silent','muted','unrouted','unavailable','loud']){
   await state(value);
   assert.equal(await page.locator('#microphoneLevel').getAttribute('aria-valuenow'),'0');
   assert.equal(await page.locator('#recordButton').isEnabled(),true);
   assert.equal(await page.locator('#capturePanel').evaluate(el=>el.offsetHeight),height);
  }
  await state('silent',{quiet_seconds:121});await page.waitForFunction(()=>document.querySelector('#homeStatus').classList.contains('microphone-warning'));
  assert.match(await page.locator('#homeStatus').textContent(),/2 分钟/);
  assert.equal(await page.locator('.capture-time-row #microphoneMonitor').count(),1);
  await page.screenshot({path:path.join(out,'recording-silent.png')});
  for(const [width,height] of [[820,620],[3440,1440],[390,640]]){
   await page.setViewportSize({width,height});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
   const rect=await page.locator('#microphoneMonitor').boundingBox();assert.ok(rect.x>=0&&rect.x+rect.width<=width+1);
  }
  await page.setViewportSize({width:820,height:620});await page.locator('#themeButton').click();
  await page.screenshot({path:path.join(out,'recording-silent-compact-dark.png')});
  await state('signal',{level:.4,quiet_seconds:0});
  await page.waitForFunction(()=>!document.querySelector('#homeStatus').classList.contains('microphone-warning'));
  assert.equal(await page.locator('#microphoneMonitor').textContent(),'');
  await page.evaluate(()=>fixture.hold=true);
  await page.waitForFunction(()=>typeof fixture.release==='function');
  const calls=await page.evaluate(()=>fixture.calls);
  await page.waitForFunction(()=>document.querySelector('#microphoneMonitor').dataset.state==='unavailable',{},{timeout:6000});
  assert.equal(await page.evaluate(()=>fixture.calls),calls,'one pending request, no queue of meter reads');
  await page.evaluate(()=>{fixture.hold=false;fixture.release();});
  await page.waitForFunction(()=>document.querySelector('#microphoneMonitor').dataset.state==='signal');
  await page.evaluate(()=>{fixture.state.activity={kind:'idle',busy:false,status:'待开始'};});
  await page.waitForFunction(()=>document.querySelector('#microphoneMonitor').classList.contains('hidden'));
  const stoppedCalls=await page.evaluate(()=>fixture.calls);await page.waitForTimeout(600);
  assert.equal(await page.evaluate(()=>fixture.calls),stoppedCalls,'no microphone polling outside recording');
  await page.evaluate(()=>{fixture.state.activity={kind:'recording',busy:false,active_id:'next-synthetic',status:'录制中'};});
  await page.waitForFunction(()=>!document.querySelector('#microphoneMonitor').classList.contains('hidden'));
  await page.waitForTimeout(500);
  assert.notEqual(await page.locator('#microphoneMonitor').getAttribute('data-state'),'signal','old session response cannot light new meter');
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify({ok:true,states:8,sizes:4,stale_bridge:true,session_isolation:true,page_errors:errors},null,2));
  console.log('Microphone UI passed: states, resize, dark theme, stale bridge, stop and next-session isolation.');
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;server.close();});
