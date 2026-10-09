'use strict';

// Production recorder DOM in real headless Edge. All bridge/device states are
// synthetic; no OBS, native devices, real recording or private installation.
// PLAYWRIGHT_MODULE may point to an existing bundled runtime. No downloads.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const crypto=require('node:crypto');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..');
const output=path.resolve(process.env.TAR_INVENTORY_OUTPUT||path.join(root,'work/preset-device-validation/browser-evidence/preset-inventory'));
const saved='合成游戏#3A测试:OldRandom:game.exe',live='合成游戏#3A测试:NewRandom:game.exe',other='另一个合成游戏:OtherClass:other.exe';
const blank={window:[],monitor:[],mic:[]};
const devices={
  window:[{itemName:'合成游戏：当前窗口',itemValue:live,itemEnabled:true},{itemName:'另一个合成游戏',itemValue:other,itemEnabled:true}],
  monitor:[{itemName:'合成副显示器',itemValue:'secondary',itemEnabled:true},{itemName:'合成主显示器',itemValue:'primary',itemEnabled:true}],
  mic:[{itemName:'默认麦克风（合成）',itemValue:'default',itemEnabled:true},{itemName:'另一麦克风（合成）',itemValue:'another-mic',itemEnabled:true}],
};
const match={requested:saved,resolved:live,status:'matched',matched_by:'exe_title'};
function snapshot(){return {
  config:{game:'预设设备识别 · 合成验收',vault:'D:\\synthetic-only',preset:'均衡 1080p30',source:'游戏窗口',window:saved,monitor:'saved-monitor',mic:'default',language:'zh',transcription_provider:'local',record_inputs:true},
  active_preset_id:'synthetic',presets:[{id:'synthetic',name:'预设设备识别 · 合成验收',vault:'D:\\synthetic-only'}],
  devices:blank,device_defaults:{},device_inventory:{id:'',state:'idle',checked_at:null,window_selection:null},
  readiness:{ready:false,checking:false,errors:[{code:'OBS_UNAVAILABLE',step:1,message:'无法连接录制引擎。'}]},
  activity:{kind:'idle',busy:false,status:'待开始',detail:''},sessions:[],background_jobs:[],model:{state:'missing'},capabilities:{cloud_key:false},
};}
const report={scope:'Real headless Edge with production DOM/CSS/JS and synthetic bridge/device inventory only. Not native WebView2, OBS or live recording acceptance.',started_at:new Date().toISOString(),checks:[],screenshots:[],errors:[],source_sha256:{}};
for(const file of ['ui/app.js','ui/state.js','ui/index.html','ui/styles.css'])report.source_sha256[file]=crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex');
const server=http.createServer((req,res)=>{
  const pathname=new URL(req.url,'http://127.0.0.1').pathname;
  if(pathname==='/favicon.ico'){res.writeHead(204);res.end();return;}
  const file=path.resolve(root,'.'+pathname);
  if(!file.startsWith(path.join(root,'ui')+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
  const type={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml'};
  res.setHeader('Content-Type',type[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));
});
let context,origin;
async function makePage(initial=snapshot(),mode='hold'){
  const page=await context.newPage();
  await page.addInitScript(({initial,mode})=>{
    const f=window.syntheticInventory={snapshot:initial,mode,calls:[],sequence:0};
    window.pywebview={api:new Proxy({},{get:(_,method)=>async(...args)=>{
      if(method==='get_state')return {ok:true,data:JSON.parse(JSON.stringify(f.snapshot))};
      f.calls.push({method,args});
      if(method==='refresh_device_inventory'){
        const id='synthetic-inventory-'+(++f.sequence);
        if(f.mode==='reject')return {ok:false,error:f.rejectionMessage||'合成读取请求失败'};
        if(f.mode==='defer')return new Promise(resolve=>f.resolve=resolve);
        f.snapshot.device_inventory={id,state:'running',checked_at:null,window_selection:null};
        return {ok:true,data:{inventory_id:id}};
      }
      if(method==='refresh_devices'){f.snapshot.device_refresh={id:'synthetic-engine',state:'succeeded'};return {ok:true,data:{refresh_id:'synthetic-engine'}};}
      throw new Error('Synthetic harness blocked native action: '+String(method));
    }})};
  },{initial,mode});
  await page.goto(origin+'/ui/index.html');await page.locator('#settingsButton:not([disabled])').waitFor();
  return page;
}
async function patch(page,patch){await page.evaluate(value=>{Object.assign(window.syntheticInventory.snapshot,value);return poll();},patch);}
async function complete(page,options={}){
  const id=await page.evaluate(()=>window.syntheticInventory.snapshot.device_inventory.id);
  await patch(page,{devices,device_defaults:{monitor:'primary',mic:'default'},device_inventory:{id,state:'succeeded',checked_at:Date.now()/1000,window_selection:match},...options});
}
async function choices(page){return page.evaluate(()=>JSON.stringify([store.draft.source,store.draft.window,store.draft.monitor,store.draft.mic,store.draft.record_inputs]));}
async function calls(page,name){return page.evaluate(name=>window.syntheticInventory.calls.filter(c=>c.method===name),name);}
async function screenshot(page,name){await page.screenshot({path:path.join(output,name+'.png')});report.screenshots.push(name+'.png');}
async function check(name,fn){try{await fn();report.checks.push({name,pass:true});}catch(error){report.checks.push({name,pass:false,error:error.stack});console.error(name+'\n'+error.stack);}}

async function main(){
  fs.mkdirSync(output,{recursive:true});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin='http://127.0.0.1:'+server.address().port;
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try{
    context=await browser.newContext({viewport:{width:1060,height:780}});context.setDefaultTimeout(5000);
    await context.route('**/*',route=>{if(route.request().url().startsWith(origin+'/'))return route.continue();report.errors.push('Blocked external request: '+route.request().url());return route.abort();});
    context.on('page',page=>page.on('pageerror',error=>report.errors.push(error.message)));
    const page=await makePage();await page.locator('#settingsButton').click();
    const original=await choices(page);
    await check('edit opens with automatic read, readable saved labels and unlocked cancel, without engine setup',async()=>{
      await page.waitForFunction(()=>window.syntheticInventory.calls.some(c=>c.method==='refresh_device_inventory'));
      assert.equal((await calls(page,'refresh_device_inventory')).length,1);assert.equal((await calls(page,'refresh_devices')).length,0);
      assert.match(await page.locator('#target option:checked').innerText(),/合成游戏:测试（game.exe）.*未确认/);
      assert.match(await page.locator('#mic option:checked').innerText(),/默认麦克风.*未确认/);
      assert.match(await page.locator('#deviceFeedback').innerText(),/正在读取/);
      assert.equal(await page.locator('#refreshDevices').isDisabled(),true);assert.equal(await page.locator('#refreshDevices').innerText(),'正在读取…');
      await page.evaluate(()=>document.querySelector('#refreshDevices').click());assert.equal((await calls(page,'refresh_device_inventory')).length,1);
      assert.doesNotMatch(await page.locator('#target').innerText(),/当前未找到/);
      assert.equal(await page.locator('#wizardCancel').isEnabled(),true);assert.equal(await page.locator('#source').isEnabled(),true);
      await screenshot(page,'edit-reading');
    });
    await check('unique live window match uses inventory evidence even with engine readiness blocked, and changes no saved choice',async()=>{
      await complete(page);
      assert.equal(await page.locator('#target').inputValue(),live);assert.match(await page.locator('#target option:checked').innerText(),/已匹配当前窗口/);
      assert.match(await page.locator('#deviceFeedback').innerText(),/已识别当前选择的游戏窗口和麦克风/);assert.doesNotMatch(await page.locator('#deviceFeedback').innerText(),/打开游戏/);
      assert.equal(await page.locator('#refreshDevices').isEnabled(),true);assert.equal(await page.locator('#refreshDevices').innerText(),'刷新设备');
      assert.equal(await choices(page),original);assert.equal(await page.evaluate(()=>window.syntheticInventory.snapshot.config.window),saved);
      assert.equal(await page.locator('#recordButton').isDisabled(),true);assert.equal(await page.locator('#reconnectEngine').isVisible(),true);
      assert.equal((await calls(page,'save_preset')).length,0);assert.equal((await calls(page,'start_recording')).length,0);
      await screenshot(page,'edit-matched-engine-blocked');
      const readiness=await page.evaluate(()=>window.syntheticInventory.snapshot.readiness);
      await patch(page,{readiness:{...readiness,checking:true}});
      assert.equal(await page.locator('#reconnectEngine').isVisible(),false);assert.equal(await page.locator('#engineFeedback').isVisible(),false);
      await patch(page,{readiness});
    });
    await check('explicit engine reconnection and repeated inventory refresh preserve every existing selection',async()=>{
      await page.locator('#reconnectEngine').click();assert.equal((await calls(page,'refresh_devices')).length,1);assert.equal(await choices(page),original);
      await page.locator('#refreshDevices').click();await complete(page);assert.equal(await choices(page),original);
    });
    await check('failed read never labels saved selection missing and retry stays reachable',async()=>{
      await patch(page,{devices:blank,device_inventory:{id:'newer-failure',state:'failed',error:'合成 Windows 设备枚举失败'}});
      assert.match(await page.locator('#deviceFeedback').innerText(),/合成 Windows 设备枚举失败/);
      assert.match(await page.locator('#target option:checked').innerText(),/读取失败，未确认/);assert.doesNotMatch(await page.locator('#target').innerText(),/当前未找到/);
      assert.equal(await page.locator('#refreshDevices').isEnabled(),true);assert.equal(await choices(page),original);
      await screenshot(page,'edit-read-failed');
    });
    await check('successful empty list is missing; ambiguous windows never auto-select a candidate',async()=>{
      await complete(page,{devices:blank,device_inventory:{id:'newer-empty',state:'succeeded',window_selection:{requested:saved,status:'missing'}}});
      assert.match(await page.locator('#target option:checked').innerText(),/当前未找到/);assert.match(await page.locator('#deviceFeedback').innerText(),/读取完成，当前未找到/);
      await complete(page,{devices:{...devices,window:[]},device_inventory:{id:'window-missing',state:'succeeded',window_selection:{requested:saved,status:'missing'}}});
      assert.match(await page.locator('#deviceFeedback').innerText(),/当前未找到所选游戏窗口，请打开游戏后刷新/);
      assert.doesNotMatch(await page.locator('#deviceFeedback').innerText(),/连接麦克风/);
      await complete(page,{device_inventory:{id:'newer-ambiguous',state:'succeeded',window_selection:{requested:saved,status:'ambiguous'}}});
      assert.equal(await page.locator('#target').inputValue(),saved);assert.match(await page.locator('#target option:checked').innerText(),/多个匹配，请重新选择/);
      assert.match(await page.locator('#deviceFeedback').innerText(),/多个匹配的游戏窗口/);
      assert.equal(await choices(page),original);await screenshot(page,'edit-ambiguous');
    });
    await check('manual window and mic choices survive in-flight read and later matching results',async()=>{
      await page.locator('#target').selectOption(other);await page.locator('#mic').selectOption('another-mic');
      await page.locator('#refreshDevices').click();await complete(page);
      assert.equal(await page.locator('#target').inputValue(),other);assert.equal(await page.locator('#mic').inputValue(),'another-mic');
      await page.locator('#wizardCancel').click();assert.equal(await page.evaluate(()=>window.syntheticInventory.snapshot.config.window),saved);
      assert.equal((await calls(page,'save_preset')).length,0);
    });
    await page.close();
    await check('cancel and reopen ignore a late RPC and consume newer inventory without freezing',async()=>{
      const p=await makePage(snapshot(),'defer');await p.locator('#settingsButton').click();await p.waitForFunction(()=>!!window.syntheticInventory.resolve);
      assert.equal(await p.locator('#wizardCancel').isEnabled(),true);await p.locator('#wizardCancel').click();
      await p.evaluate(()=>{window.syntheticInventory.mode='hold';});await p.locator('#newPresetButton').click();
      await p.evaluate(()=>window.syntheticInventory.resolve({ok:true,data:{inventory_id:'late-old-rpc'}}));
      await complete(p,{device_inventory:{id:'latest-auto-probe',state:'succeeded',window_selection:match}});
      assert.equal(await p.evaluate(()=>store.draft.source),'游戏窗口');assert.equal(await p.evaluate(()=>store.draft.mic),'');
      assert.equal(await p.locator('#refreshDevices').isEnabled(),true);await p.close();
    });
    await check('new drafts get no defaults from automatic reads; explicit first refresh keeps existing defaults semantics',async()=>{
      const p=await makePage();await p.locator('#newPresetButton').click();await p.locator('#wizardNext').click();await complete(p);
      assert.equal(await p.locator('#source').inputValue(),'游戏窗口');assert.equal(await p.locator('#mic').inputValue(),'');
      await p.locator('#wizardCancel').click();await patch(p,{devices:blank});await p.locator('#newPresetButton').click();await p.locator('#wizardNext').click();
      await complete(p,{devices:blank,device_defaults:{}});
      await p.locator('#refreshDevices').click();await complete(p);
      assert.equal(await p.locator('#source').inputValue(),'整个显示器');assert.equal(await p.locator('#target').inputValue(),'primary');assert.equal(await p.locator('#mic').inputValue(),'default');
      assert.match(await p.locator('#deviceFeedback').innerText(),/已识别当前选择的显示器和麦克风/);assert.doesNotMatch(await p.locator('#deviceFeedback').innerText(),/游戏窗口/);
      await p.locator('#target').selectOption('secondary');await p.locator('#mic').selectOption('another-mic');await p.locator('#refreshDevices').click();await complete(p);
      assert.equal(await p.locator('#target').inputValue(),'secondary');assert.equal(await p.locator('#mic').inputValue(),'another-mic');
      await p.close();
    });
    await check('new draft device choices changed during reading, including changing back, block late defaults',async()=>{
      const p=await makePage();await p.locator('#newPresetButton').click();await p.locator('#wizardNext').click();await complete(p,{devices:blank,device_defaults:{}});await p.locator('#refreshDevices').click();
      await p.locator('#source').selectOption('整个显示器');await p.locator('#source').selectOption('游戏窗口');await p.locator('#game').click();await complete(p);
      assert.equal(await p.locator('#source').inputValue(),'游戏窗口');assert.equal(await p.locator('#mic').inputValue(),'');
      await p.close();
    });
    await check('RPC rejection is retryable; compact dark layout keeps both device and engine actions usable',async()=>{
      const p=await makePage(snapshot(),'reject');await p.setViewportSize({width:390,height:667});await p.locator('#themeButton').click();await p.locator('#settingsButton').click();
      await p.waitForFunction(()=>document.querySelector('#deviceFeedback').textContent.includes('合成读取请求失败'));
      assert.equal(await p.locator('#refreshDevices').isEnabled(),true);assert.equal(await p.locator('#wizardCancel').isEnabled(),true);
      await p.locator('#reconnectEngine').scrollIntoViewIfNeeded();
      assert.equal(await p.locator('#wizard').evaluate(n=>n.scrollWidth<=n.clientWidth+1),true);
      assert.equal(await p.locator('#wizardBody').evaluate(n=>n.scrollWidth<=n.clientWidth+1),true);
      const box=await p.locator('#reconnectEngine').boundingBox();assert.ok(box.x>=0&&box.x+box.width<=390);
      await screenshot(p,'compact-dark-read-failed');
      await complete(p,{device_inventory:{id:'new-evidence-after-rejection',state:'succeeded',window_selection:match}});
      assert.equal(await p.locator('#target').inputValue(),live);assert.doesNotMatch(await p.locator('#deviceFeedback').innerText(),/合成读取请求失败/);
      await p.evaluate(()=>{window.syntheticInventory.mode='hold';});await p.locator('#refreshDevices').click();await complete(p);
      assert.equal(await p.locator('#target').inputValue(),live);await p.locator('#wizardCancel').click();assert.equal(await p.locator('#recordButton').isDisabled(),true);await p.close();
    });
    for(const [code,label] of [['RECORDING_UNCONFIRMED','重新检查录制状态'],['READINESS_FAILED','重新检查录制条件'],['READINESS_STALE','重新检查录制条件']]){
      await check(`${code}: full recovery remains reachable after native read rejection, without implying recording stopped`,async()=>{
        const initial=snapshot();initial.readiness={ready:false,checking:false,errors:[{code,step:1,message:'合成录制检查阻塞'}]};
        const p=await makePage(initial,'reject');
        await p.evaluate(()=>{window.syntheticInventory.rejectionMessage='合成：上次录制状态尚未确认。';});
        await p.locator('#settingsButton').click();
        await p.waitForFunction(()=>document.querySelector('#deviceFeedback').textContent.includes('合成：上次录制状态尚未确认。'));
        assert.equal(await p.locator('#reconnectEngine').innerText(),label);assert.equal(await p.locator('#reconnectEngine').isEnabled(),true);
        assert.match(await p.locator('#target option:checked').innerText(),/读取失败，未确认/);assert.doesNotMatch(await p.locator('#target').innerText(),/当前未找到/);
        assert.equal(await p.locator('#recordButton').isDisabled(),true);
        if(code==='RECORDING_UNCONFIRMED')await screenshot(p,'unknown-recording-recovery');
        const original=await choices(p);await p.locator('#reconnectEngine').click();
        assert.equal((await calls(p,'refresh_devices')).length,1);assert.equal(await choices(p),original);
        assert.equal(await p.locator('#recordButton').isDisabled(),true,'accepted recovery alone does not establish readiness');
        await complete(p);assert.equal(await p.locator('#recordButton').isDisabled(),true,'successful device inventory alone does not establish readiness');
        await patch(p,{activity:{kind:'devices',busy:true,status:'合成完整检查中'}});
        assert.equal(await p.locator('#reconnectEngine').isVisible(),false);assert.equal(await p.locator('#refreshDevices').isDisabled(),true);
        await p.evaluate(()=>document.querySelector('#reconnectEngine').click());assert.equal((await calls(p,'refresh_devices')).length,1);
        await patch(p,{activity:{kind:'idle',busy:false},readiness:{...initial.readiness,checking:true}});
        assert.equal(await p.locator('#reconnectEngine').isVisible(),false);assert.equal(await p.locator('#recordButton').isDisabled(),true);
        await patch(p,{readiness:{ready:true,checking:false,errors:[]}});assert.equal(await p.locator('#recordButton').isEnabled(),true);
        await patch(p,{activity:{kind:'recording',busy:false,status:'合成正在录制'},readiness:initial.readiness});
        assert.equal(await p.locator('#reconnectEngine').isVisible(),false);assert.equal(await p.locator('#source').isDisabled(),true);assert.equal(await p.locator('#refreshDevices').isDisabled(),true);
        await p.evaluate(()=>document.querySelector('#reconnectEngine').click());assert.equal((await calls(p,'refresh_devices')).length,1);
        assert.equal((await calls(p,'start_recording')).length,0);assert.equal((await calls(p,'stop_recording')).length,0);
        await p.locator('#wizardCancel').click();assert.equal(await p.locator('#settingsButton').isDisabled(),true);
        await p.evaluate(()=>openWizard('edit'));assert.equal(await p.locator('#wizard').isVisible(),false);
        await p.close();
      });
    }
    await check('no browser exceptions or unintended external requests',()=>assert.deepEqual(report.errors,[]));
    await context.close();
  }finally{await browser.close();server.close();}
  report.passed=report.checks.every(x=>x.pass);fs.writeFileSync(path.join(output,'acceptance.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({passed:report.passed,checks:report.checks.length,failures:report.checks.filter(x=>!x.pass),output},null,2));
  if(!report.passed)process.exitCode=1;
}
main().catch(error=>{console.error(error.stack);server.close();process.exitCode=1;});
