'use strict';
// Synthetic front-end state and bridge tests. No browser, capture, or network.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {State,vocabularyWords} = require('../ui/state.js');

function snapshot(overrides={}) {
  return {
    config: {game:'Saved game',vault:'D:\\Saved',preset:'流畅 1080p60',source:'游戏窗口',
      window:'game-window',monitor:'display-1',mic:'microphone',language:'ja',hotwords:'Saved vocabulary',
      transcription_provider:'qwen',obsidian_exe:'D:\\Obsidian\\Obsidian.exe',configured:true},
    presets:[{id:'one',name:'Saved game',vault:'D:\\Saved'}],active_preset_id:'one',
    readiness:{ready:true,checking:false,errors:[],checked_at:123},
    activity:{busy:false,kind:'idle',status:'待开始',detail:''},sessions:[],
    devices:{window:[{itemName:'Saved game window',itemValue:'game-window',itemEnabled:true}],
      monitor:[{itemName:'Display',itemValue:'display-1',itemEnabled:true}],
      mic:[{itemName:'Microphone',itemValue:'microphone',itemEnabled:true}]},
    model:{state:'missing',downloaded_bytes:0,total_bytes:100},capabilities:{cloud_key:true},
    ...overrides,
  };
}

test('saved identifiers and model capability never substitute for backend readiness',()=>{
  const state=new State();state.accept(snapshot({readiness:{ready:false,checking:false,errors:[{message:'Microphone disconnected'}]}}));
  assert.equal(state.canStart,false);
  state.accept(snapshot({readiness:{ready:true,checking:true,errors:[]}}));assert.equal(state.canStart,false);
  state.accept(snapshot());assert.equal(state.canStart,true);
  state.disconnect();assert.equal(state.canStart,false);
  state.accept(snapshot());state.requestPending=true;assert.equal(state.canStart,false);
});

test('new preset is independent; editing and cancellation preserve every saved setting',()=>{
  const state=new State();state.accept(snapshot());
  const saved=JSON.stringify(state.saved);
  state.openDraft('new');assert.equal(state.editingId,null);assert.equal(state.draft.game,'');
  assert.equal(state.draft.transcription_provider,'local');assert.equal(state.draft.hotwords,'');
  assert.equal(state.draft.obsidian_exe,undefined);assert.equal(state.draft.window,'');
  state.updateDraft('game','Unsaved');state.cancelDraft();assert.equal(JSON.stringify(state.saved),saved);
  state.openDraft('edit');assert.equal(state.editingId,'one');assert.equal(state.draft.vault,state.saved.vault);assert.equal(state.draft.hotword_manual,'Saved vocabulary');assert.deepEqual(state.draft.hotword_files,[]);
  state.updateDraft('hotwords','Unsaved words');state.cancelDraft();state.openDraft('edit');
  assert.equal(state.draft.hotwords,'Saved vocabulary');
});

test('polling and external preset changes do not overwrite an open draft',()=>{
  const state=new State();state.accept(snapshot());state.openDraft('edit');state.updateDraft('game','My draft');state.updateDraft('hotwords','Typing');
  state.accept(snapshot({config:{...snapshot().config,game:'Externally changed',hotwords:'Other'}}));
  assert.equal(state.saved.game,'Externally changed');assert.equal(state.draft.game,'My draft');
  assert.equal(state.draft.hotwords,'Typing');assert.deepEqual(state.startPayload(),{});
});

function firstUseVault(exists=true){return snapshot({presets:[],active_preset_id:null,
  config:{...snapshot().config,vault:'D:\\Shared\\think-aloud-database',configured:false},
  default_vault:{path:'D:\\Shared\\think-aloud-database',exists,is_directory:exists,requires_confirmation:exists},
  readiness:{ready:false,checking:false,errors:[{message:'请先完成设置'}]}});}

test('existing sibling database requires explicit reuse, bound to the path and cleared on cancellation',async()=>{
  const f=await fixture(firstUseVault());
  f.run("store.updateDraft('game','New Game');store.updateDraft('window','window-id');store.updateDraft('mic','mic-id');setStep(3)");
  assert.equal(f.elements.get('reuseVaultNotice').classList.contains('hidden'),false);
  assert.equal(f.elements.get('wizardNext').disabled,true);assert.equal(f.calls.some(c=>c.name==='save_preset'),false);
  f.elements.get('reuseVault').onclick();assert.equal(f.elements.get('wizardNext').disabled,false);
  assert.equal(f.run('store.presetPayload().confirmed_vault'),'D:\\Shared\\think-aloud-database');
  await f.run('poll()');assert.equal(f.elements.get('wizardNext').disabled,false);
  f.elements.get('wizardCancel').onclick();f.elements.get('newPresetButton').onclick();f.run('setStep(3)');
  assert.equal(f.elements.get('wizardNext').disabled,true);assert.equal(f.run('store.confirmedVault'),'');
  f.data.chosenDirectory='D:\\Different Library';await f.elements.get('chooseVault').onclick();
  assert.equal(f.run('store.draft.vault'),'D:\\Different Library');assert.equal(f.elements.get('reuseVaultNotice').classList.contains('hidden'),true);
  assert.equal(f.elements.get('wizardNext').disabled,false);
  assert.equal(f.run('store.presetPayload().confirmed_vault'),'D:\\Different Library');
  assert.equal(f.calls.some(c=>c.name==='save_preset'),false);
});

test('folder appearing at save returns wizard to explicit reuse without silently retrying',async()=>{
  const f=await fixture(firstUseVault(false));
  f.run("store.updateDraft('game','New Game');store.updateDraft('window','window-id');store.updateDraft('mic','mic-id');setStep(3)");
  assert.equal(f.elements.get('wizardNext').disabled,false);f.data.vaultRace=true;await f.run('finishWizard()');
  assert.equal(f.elements.get('wizard').open,true);assert.equal(f.elements.get('wizardNext').disabled,true);
  assert.equal(f.calls.filter(c=>c.name==='save_preset').length,1);
  f.elements.get('reuseVault').onclick();await f.run('finishWizard()');
  const saves=f.calls.filter(c=>c.name==='save_preset');assert.equal(saves.length,2);
  assert.equal(saves[0].args[0].confirmed_vault,undefined);assert.equal(saves[1].args[0].confirmed_vault,'D:\\Shared\\think-aloud-database');
  assert.equal(f.elements.get('wizard').open,false);
});

function fakeDOM() {
  const html=fs.readFileSync(path.join(__dirname,'../ui/index.html'),'utf8');
  const elements=new Map();let document;
  class Element {
    constructor(id='') {this.id=id;this.value='';this.textContent='';this.innerHTML='';this.disabled=false;this.open=false;this.scrollTop=0;this.dataset={};this.attributes={};this.listeners={};this.children=[];const classes=new Set();this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,on)=>{if(on===undefined)on=!classes.has(x);on?classes.add(x):classes.delete(x);return on;},contains:x=>classes.has(x)};}
    addEventListener(name,fn){this.listeners[name]=fn;}
    setAttribute(name,value){this.attributes[name]=String(value);}
    removeAttribute(name){delete this.attributes[name];}
    getAttribute(name){return this.attributes[name];}
    focus(){document.activeElement=this;}
    showModal(){this.open=true;}
    close(){this.open=false;}
    replaceChildren(){this.children=[];}
    append(child){this.children.push(child);}
    querySelector(){return null;}
    closest(){return null;}
  }
  for(const match of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const el=new Element(match[3]);el.tagName=match[1].toUpperCase();
    for(const data of match[2].matchAll(/data-([\w-]+)="([^"]*)"/g))el.dataset[data[1]]=data[2];
    elements.set(el.id,el);
  }
  const steps=[0,1,2,3].map(n=>{const el=new Element();el.dataset.step=String(n);return el;});
  document={activeElement:null,documentElement:{dataset:{}},getElementById:id=>elements.get(id),
    querySelector:selector=>selector.startsWith('#')?elements.get(selector.slice(1)):null,
    querySelectorAll:selector=>selector==='[data-draft]'?[...elements.values()].filter(el=>el.dataset.draft):selector==='[data-provider]'?[...elements.values()].filter(el=>el.dataset.provider):selector==='[data-step]'?steps:[],
    createElement:()=>new Element(),addEventListener(){}};
  elements.get('filter').value='all';
  return {document,elements};
}
async function settle(){for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));}
async function fixture(initial=snapshot()) {
  const {document,elements}=fakeDOM();const calls=[];const data={snapshot:initial};
  const api=new Proxy({}, {get(_target,name){return async(...args)=>{calls.push({name,args});if(name==='get_state')return {ok:true,data:JSON.parse(JSON.stringify(data.snapshot))};if(name==='refresh_devices')return data.refreshResult||{ok:true,data:{started:true,refresh_id:'refresh-1'}};if(name==='choose_directory')return {ok:true,data:{path:data.chosenDirectory||null}};if(name==='choose_hotword_files')return data.dictionaryError?{ok:false,error:data.dictionaryError}:{ok:true,data:{files:data.chosenFiles||[]}};if(name==='save_preset'){if(data.vaultRace){data.vaultRace=false;data.snapshot.default_vault={...data.snapshot.default_vault,exists:true,is_directory:true,requires_confirmation:true};return {ok:false,code:'VAULT_REUSE_REQUIRED',error:'请确认使用已有资料库。'};}data.snapshot={...data.snapshot,config:{...args[0],configured:true},active_preset_id:args[1]||'created',presets:[{id:args[1]||'created',name:args[0].name,vault:args[0].vault}],readiness:{ready:false,checking:true,errors:[]}};return {ok:true,data:{id:args[1]||'created'}};}return {ok:true,data:{}};};}});
  const context=vm.createContext({document,window:{pywebview:{api},addEventListener(){}},localStorage:{getItem(){},setItem(){}},setTimeout(){return 1;},clearTimeout(){},setInterval(){},CSS:{escape:x=>x},console});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/state.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/app.js'),'utf8'),context);
  await settle();return {context,elements,calls,data,run:source=>vm.runInContext(source,context)};
}

test('actual UI opens first-use wizard; cancel does not persist or enable recording',async()=>{
  const f=await fixture(snapshot({presets:[],active_preset_id:null,config:{...snapshot().config,configured:false},readiness:{ready:false,checking:false,errors:[{step:1,message:'Create preset'}]}}));
  assert.equal(f.elements.get('wizard').open,true);
  f.elements.get('wizardCancel').onclick();
  assert.equal(f.elements.get('wizard').open,false);
  assert.equal(f.elements.get('recordButton').disabled,true);
  assert.equal(f.calls.some(call=>call.name==='save_preset'),false);
});

test('actual UI retains focused draft on polling and starts with persisted settings only',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();
  const input=f.elements.get('game');input.value='Draft name';input.focus();input.listeners.input();
  f.data.snapshot.config.game='Saved update';await f.run('poll()');
  assert.equal(input.value,'Draft name');assert.equal(f.run('store.draft.game'),'Draft name');
  f.elements.get('wizardCancel').onclick();f.elements.get('recordButton').onclick();await settle();
  const start=f.calls.find(call=>call.name==='start_recording');assert.ok(start);assert.deepEqual(JSON.parse(JSON.stringify(start.args)),[{}]);
  assert.equal(f.calls.some(call=>call.name==='save_preset'),false);
});

test('actual wizard saves named preset then polls fresh state before closing; never starts capture',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();
  const input=f.elements.get('game');input.value='Edited preset';input.listeners.input();
  const before=f.calls.length;await f.run('finishWizard()');
  const calls=f.calls.slice(before);assert.equal(calls[0].name,'save_preset');assert.equal(calls[0].args[1],'one');
  assert.equal(calls[0].args[0].name,'Edited preset');assert.equal(calls.at(-1).name,'get_state');
  assert.equal(f.elements.get('wizard').open,false);assert.equal(f.elements.get('recordButton').disabled,true);
  assert.equal(calls.some(call=>call.name==='start_recording'),false);
});

test('session dates use local minute precision and preserve readable invalid values',async()=>{
  const timestamp='2026-09-20T17:26:53.973896+08:00';
  const expected=new Intl.DateTimeFormat('sv-SE',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(timestamp));
  const f=await fixture(snapshot({sessions:[{id:'dated',game:'Dated session',created:timestamp,duration:10,state:'待整理'}]}));
  assert.equal(f.run(`formatDate(${JSON.stringify(timestamp)})`),expected);
  const rendered=f.elements.get('sessionList').innerHTML;
  assert.ok(rendered.includes(expected));assert.ok(!rendered.includes(timestamp));
  assert.equal(f.run("formatDate('2026-01-02T03:04:59')"),'2026-01-02 03:04');
  assert.equal(f.run("formatDate('未记录时间')"),'未记录时间');
  assert.equal(f.run("formatDate('not-a-date')"),'not-a-date');
  assert.equal(f.run('formatDate(null)'),'—');
});

test('background transcription leaves Start and presets available; capture save and readiness still block',async()=>{
  const jobs=[{id:'job-a',session_id:'a',game:'Game A',state:'running',detail:'Uploading microphone'},
    {id:'job-b',session_id:'b',game:'Game B',state:'queued',detail:''}];
  const sessions=[{id:'a',game:'Game A',state:'转写中',duration:60},{id:'b',game:'Game B',state:'待整理',duration:30}];
  const f=await fixture(snapshot({background_jobs:jobs,sessions}));
  assert.equal(f.elements.get('recordButton').disabled,false);assert.equal(f.elements.get('recordButtonText').textContent,'开始录制');
  assert.equal(f.elements.get('presetSelect').disabled,false);assert.equal(f.elements.get('settingsButton').disabled,false);
  assert.equal(f.elements.get('jobDetail').textContent,'');
  assert.equal(f.elements.get('backgroundSummary').textContent,'1 段整理中 · 1 段排队');
  assert.ok(f.elements.get('sessionList').innerHTML.includes('Uploading microphone'));
  assert.ok(f.elements.get('sessionList').innerHTML.includes('等待整理'));
  assert.equal(f.run("sessionActionBlocked('a','process')"),true);assert.equal(f.run("sessionActionBlocked('a','export')"),true);
  assert.equal(f.run("sessionActionBlocked('a','folder')"),false);assert.equal(f.run("sessionActionBlocked('other','process')"),false);
  f.elements.get('recordButton').onclick();await settle();assert.ok(f.calls.some(call=>call.name==='start_recording'));
  f.data.snapshot.activity={busy:true,kind:'saving',status:'正在保存录像',detail:''};await f.run('poll()');
  assert.equal(f.elements.get('recordButton').disabled,true);assert.equal(f.elements.get('recordButtonText').textContent,'正在保存…');
  f.data.snapshot.activity={busy:false,kind:'idle'};f.data.snapshot.readiness={ready:false,checking:false,errors:[{message:'游戏窗口未打开'}]};await f.run('poll()');
  assert.equal(f.elements.get('recordButton').disabled,true);assert.equal(f.elements.get('blockers').textContent,'游戏窗口未打开');
});

test('background progress and failures stay on their session without replacing current timer or Stop',async()=>{
  const initial=snapshot({activity:{kind:'recording',busy:false,status:'录制中',active_id:'b',elapsed_seconds:18},
    background_jobs:[{id:'job-a',session_id:'a',state:'running',detail:'Uploading A'}],
    sessions:[{id:'a',game:'A',state:'转写中'},{id:'b',game:'B',state:'录制中'}]});
  const f=await fixture(initial);
  assert.equal(f.elements.get('recordButton').disabled,false);assert.equal(f.elements.get('recordButtonText').textContent,'结束并转写');
  assert.equal(f.elements.get('homeTitle').textContent,'00:00:18');assert.equal(f.elements.get('jobDetail').textContent,'');
  f.data.snapshot.background_jobs[0].detail='<Waiting for cloud>';await f.run('poll()');
  assert.ok(f.elements.get('sessionList').innerHTML.includes('&lt;Waiting for cloud&gt;'));
  f.data.snapshot.background_jobs=[];f.data.snapshot.sessions[0]={id:'a',game:'A',state:'失败',error:'Cloud failure'};await f.run('poll()');
  assert.equal(f.elements.get('blockers').textContent,'');assert.equal(f.elements.get('recordButton').disabled,false);
  assert.equal(f.elements.get('homeTitle').textContent,'00:00:18');assert.equal(f.elements.get('backgroundSummary').textContent,'');
  assert.ok(f.elements.get('sessionList').innerHTML.includes('重试'));
  f.elements.get('recordButton').onclick();await settle();assert.ok(f.calls.some(call=>call.name==='stop_recording'));
});

test('vocabulary files stay independent and removal preserves overlapping and manual words',()=>{
  assert.deepEqual(vocabularyWords({hotword_files:[{words:['Café']}],hotword_manual:'Cafe\u0301'}),['Café']);
  const a={id:'a',name:'角色.txt',words:['重叠词','角色名']},b={id:'b',name:'道具.scel',words:['重叠词','道具名']};
  const saved=snapshot();saved.config={...saved.config,hotword_files:[a],hotword_manual:'手动词',hotwords:'重叠词\n角色名\n手动词'};
  const state=new State();state.accept(saved);state.openDraft('edit');
  assert.equal(state.addVocabularyFiles([a,b]),1);state.removeVocabularyFile('a');
  assert.equal(state.draft.hotwords,'重叠词\n道具名\n手动词');assert.equal(state.saved.hotword_files.length,1);
  assert.equal(state.saved.hotword_files[0].id,'a');state.accept(saved);assert.equal(state.draft.hotword_files[0].id,'b');
  assert.deepEqual(state.presetPayload().hotword_files,[b]);state.cancelDraft();state.openDraft('edit');
  assert.equal(state.draft.hotword_files[0].id,'a');state.openDraft('new');assert.equal(state.draft.hotword_files.length,0);assert.equal(state.draft.hotword_manual,'');
});

test('actual file-first UI supports multi-select, cancel, failure, removal and saved re-entry',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();
  assert.equal(f.elements.get('manualWords').open,false);
  f.data.chosenFiles=[{id:'a',name:'角色.txt',words:['同词','角色']},{id:'b',name:'<道具>.txt',words:['同词','道具']}];
  await f.elements.get('chooseHotwordFiles').onclick();
  assert.equal(f.run('store.draft.hotword_files.length'),2);assert.equal(f.run('store.draft.hotwords'),'同词\n角色\n道具\nSaved vocabulary');
  assert.ok(f.elements.get('hotwordFiles').innerHTML.includes('&lt;道具&gt;.txt'));
  assert.ok(f.elements.get('vocabularyCount').textContent.includes('4 个词'));
  assert.equal(f.calls.some(call=>call.name==='save_preset'),false);
  f.data.chosenFiles=[];await f.elements.get('chooseHotwordFiles').onclick();assert.equal(f.run('store.draft.hotword_files.length'),2);
  f.data.dictionaryError='无法读取词库';await f.elements.get('chooseHotwordFiles').onclick();assert.equal(f.run('store.draft.hotword_files.length'),2);
  assert.equal(f.elements.get('wizardError').textContent,'无法读取词库');
  f.elements.get('hotwordFiles').onclick({target:{closest:()=>({dataset:{removeVocabulary:'a'}})}});
  assert.equal(f.run('store.draft.hotwords'),'同词\n道具\nSaved vocabulary');
  await f.run('finishWizard()');f.elements.get('settingsButton').onclick();assert.equal(f.run('store.draft.hotword_files.length'),1);assert.equal(f.run('store.draft.hotword_files[0].id'),'b');
  await f.elements.get('dictionaryDownload').onclick({preventDefault(){}});await settle();
  const link=f.calls.find(call=>call.name==='open_dictionary_site');assert.ok(link);assert.equal(link.args.length,0);
});


test('first-use method introduction advances without saving; device validation still gates later steps',async()=>{
  const f=await fixture(firstUseVault(false));
  assert.equal(f.run('step'),0);
  assert.equal(f.elements.get('step0').classList.contains('hidden'),false);
  assert.equal(f.elements.get('wizardNext').textContent,'开始设置');
  f.elements.get('wizardNext').onclick();
  assert.equal(f.run('step'),1);
  f.elements.get('game').value='合成体验';f.elements.get('game').listeners.input();
  f.elements.get('wizardBack').onclick();assert.equal(f.run('step'),0);
  f.elements.get('wizardNext').onclick();assert.equal(f.run('store.draft.game'),'合成体验');
  f.elements.get('wizardNext').onclick();assert.equal(f.run('step'),1);
  assert.ok(f.elements.get('wizardError').textContent.includes('窗口'));
  assert.equal(f.calls.some(call=>['save_preset','start_recording'].includes(call.name)),false);
  f.elements.get('wizardCancel').onclick();assert.equal(f.run('store.draft'),null);
  f.elements.get('methodButton').onclick();assert.equal(f.elements.get('actionDialog').open,true);
  assert.equal(f.run('store.draft'),null);
});

test('editing a preset excludes the guide and Back cannot enter it; new presets retain the guide',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();
  assert.equal(f.run('step'),1);
  assert.equal(f.run("document.querySelectorAll('[data-step]')[0].classList.contains('hidden')"),true);
  assert.equal(f.elements.get('wizardBack').classList.contains('hidden'),true);
  f.elements.get('wizardBack').onclick();assert.equal(f.run('step'),1);
  f.elements.get('wizardNext').onclick();assert.equal(f.run('step'),2);
  f.elements.get('wizardBack').onclick();assert.equal(f.run('step'),1);
  f.elements.get('wizardCancel').onclick();
  f.elements.get('newPresetButton').onclick();assert.equal(f.run('step'),0);
  assert.equal(f.run("document.querySelectorAll('[data-step]')[0].classList.contains('hidden')"),false);
  assert.equal(f.calls.some(call=>['save_preset','start_recording'].includes(call.name)),false);
});

test('readiness and specific blockers replace each other in the same live status slot',async()=>{
  const f=await fixture();
  assert.equal(f.elements.get('homeStatus').textContent,'准备就绪');
  assert.equal(f.elements.get('blockers').classList.contains('hidden'),true);
  f.data.snapshot.readiness={ready:false,checking:false,errors:[
    {message:'未找到游戏窗口，请先打开游戏。',step:1},
    {message:'云端密钥缺失，请重新配置。',step:2},
  ]};
  await f.run('poll()');
  assert.equal(f.elements.get('recordButton').disabled,true);
  assert.equal(f.elements.get('homeStatus').classList.contains('hidden'),true);
  assert.equal(f.elements.get('homeStatus').textContent,'');
  assert.equal(f.elements.get('blockers').classList.contains('hidden'),false);
  assert.equal(f.elements.get('blockers').textContent,'未找到游戏窗口，请先打开游戏。\n云端密钥缺失，请重新配置。');
  f.data.snapshot.readiness={ready:true,checking:false,errors:[]};await f.run('poll()');
  assert.equal(f.elements.get('recordButton').disabled,false);
  assert.equal(f.elements.get('homeStatus').textContent,'准备就绪');
  assert.equal(f.elements.get('homeStatus').classList.contains('hidden'),false);
  assert.equal(f.elements.get('blockers').classList.contains('hidden'),true);
  assert.equal(f.elements.get('blockers').textContent,'');
});

test('pending requests and device refresh never advertise ready above a disabled Start',async()=>{
  const f=await fixture();
  f.run('store.requestPending=true;renderControls()');
  assert.equal(f.elements.get('recordButton').disabled,true);
  assert.equal(f.elements.get('homeStatus').textContent,'正在处理请求…');
  f.run('store.requestPending=false');
  f.data.snapshot.activity={busy:true,kind:'devices',status:'正在刷新设备'};await f.run('poll()');
  assert.equal(f.elements.get('recordButton').disabled,true);
  assert.equal(f.elements.get('homeStatus').textContent,'正在检查录制条件');
  f.data.snapshot.activity={busy:false,kind:'idle'};f.data.snapshot.closing=true;await f.run('poll()');
  assert.equal(f.elements.get('recordButton').disabled,true);
  assert.equal(f.elements.get('homeStatus').textContent,'正在安全关闭');
  assert.equal(f.elements.get('blockers').classList.contains('hidden'),true);
});

test('a historical operation error cannot replace fresh ready status after recovery',async()=>{
  const f=await fixture(snapshot({activity:{busy:false,kind:'idle',status:'操作未完成',detail:'旧的密钥验证失败'}}));
  assert.equal(f.elements.get('recordButton').disabled,false);
  assert.equal(f.elements.get('homeStatus').textContent,'准备就绪');
  assert.equal(f.elements.get('blockers').classList.contains('hidden'),true);
  assert.equal(f.elements.get('blockers').textContent,'');
  assert.ok(f.elements.get('toast').textContent.includes('旧的密钥验证失败'));
});

test('provider console opens without sending typed secrets or saving the preset',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();
  f.elements.get('cloudKey').value='synthetic-unsaved-not-a-real-key';
  await f.elements.get('bailianConsole').onclick({preventDefault(){}});await settle();
  assert.deepEqual(f.calls.find(call=>call.name==='open_bailian_console').args,[]);
  assert.equal(f.calls.some(call=>['save_cloud_key','save_preset'].includes(call.name)),false);
  assert.equal(f.elements.get('cloudKey').value,'synthetic-unsaved-not-a-real-key');
});

test('bundled UIUX defaults seed only new drafts and explicit removal survives editing',()=>{
  const bundled={id:'uiux-default',name:'uiux-terms.txt',words:['心智模型','用户界面']};
  const state=new State();state.accept(snapshot({default_hotword_files:[bundled]}));
  state.openDraft('new');assert.equal(state.draft.hotwords,'心智模型\n用户界面');
  state.draft.hotword_files[0].words.push('仅草稿');assert.equal(bundled.words.length,2);
  assert.equal(state.snapshot.default_hotword_files[0].words.length,2);
  state.removeVocabularyFile(bundled.id);assert.equal(state.draft.hotwords,'');
  const payload=state.presetPayload();assert.deepEqual(payload.hotword_files,[]);
  state.accept(snapshot({default_hotword_files:[bundled],config:{...snapshot().config,...payload}}));
  state.openDraft('edit');assert.deepEqual(state.draft.hotword_files,[]);
  state.openDraft('new');assert.equal(state.draft.hotwords,'心智模型\n用户界面');
  state.cancelDraft();state.accept(snapshot({default_hotword_files:[bundled]}));
  state.openDraft('edit');assert.equal(state.draft.hotwords,'Saved vocabulary');
});

test('vocabulary preview shows selected snapshot safely without saving or external actions',async()=>{
  const bundled={id:'uiux-default',name:'uiux-terms.txt',words:['心智模型','<script>unsafe</script>']};
  const f=await fixture(snapshot({default_hotword_files:[bundled]}));
  f.elements.get('newPresetButton').onclick();
  assert.equal(f.elements.get('vocabularySummary').textContent,'UI/UX 已选');
  f.elements.get('hotwordFiles').onclick({target:{closest:selector=>selector==='[data-view-vocabulary]'?{dataset:{viewVocabulary:bundled.id}}:null}});
  assert.equal(f.elements.get('actionDialog').open,true);
  assert.match(f.elements.get('actionBody').innerHTML,/心智模型/);
  assert.match(f.elements.get('actionBody').innerHTML,/&lt;script&gt;unsafe&lt;\/script&gt;/);
  assert.ok(!f.calls.some(call=>['save_preset','open_folder','start_recording'].includes(call.name)));
});

test('entering device setup focuses the name input, but polling never steals user focus',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();
  assert.equal(f.run('document.activeElement.id'),'game');
  f.elements.get('mic').focus();await f.run('poll()');
  assert.equal(f.run('document.activeElement.id'),'mic');
  f.elements.get('wizardCancel').onclick();f.elements.get('newPresetButton').onclick();
  f.elements.get('wizardNext').onclick();assert.equal(f.run('document.activeElement.id'),'game');
});

test('two transcription tabs change only the draft and support keyboard selection',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();f.run('setStep(2)');
  assert.equal(f.elements.has('transcription_provider'),false);
  assert.equal(f.elements.get('providerQwen').getAttribute('aria-selected'),'true');
  f.elements.get('providerLocal').onclick();
  assert.equal(f.run('store.draft.transcription_provider'),'local');
  assert.equal(f.elements.get('localControls').classList.contains('hidden'),false);
  assert.equal(f.elements.get('cloudControls').classList.contains('hidden'),true);
  f.elements.get('providerLocal').onkeydown({key:'ArrowRight',preventDefault(){}});
  assert.equal(f.run('store.draft.transcription_provider'),'qwen');
  assert.equal(f.run('document.activeElement.id'),'providerQwen');
  f.elements.get('wizardCancel').onclick();
  assert.equal(f.run('store.saved.transcription_provider'),'qwen');
  assert.equal(f.calls.some(c=>['save_preset','save_cloud_key','model_action'].includes(c.name)),false);
});

test('editing a legacy record-only preset requires an explicit choice before saving',async()=>{
  const f=await fixture(snapshot({config:{...snapshot().config,transcription_provider:'later'}}));
  f.elements.get('settingsButton').onclick();await f.run('finishWizard()');
  assert.equal(f.run('step'),2);
  assert.match(f.elements.get('wizardError').textContent,/本地转写.*Qwen/);
  assert.equal(f.calls.some(c=>c.name==='save_preset'),false);
  assert.equal(f.elements.get('providerChoiceHint').classList.contains('hidden'),false);
  f.elements.get('wizardCancel').onclick();assert.equal(f.run('store.saved.transcription_provider'),'later');
});

const setupSnapshot=()=>snapshot({devices:{monitor:[],mic:[],window:[]},device_refresh:{id:'',state:'idle'},device_defaults:{monitor:'',mic:''}});
const detectedDefaults=()=>({
  devices:{window:[],monitor:[{itemName:'Secondary',itemValue:'secondary',itemEnabled:true},{itemName:'Primary',itemValue:'primary',itemEnabled:true}],mic:[{itemName:'Default',itemValue:'default',itemEnabled:true}]},
  device_defaults:{monitor:'primary',mic:'default'},device_refresh:{id:'refresh-1',state:'succeeded',error:''}
});

test('empty-device setup waits for its own completion then selects only verified defaults in the draft',async()=>{
  const f=await fixture(setupSnapshot());f.elements.get('settingsButton').onclick();
  assert.equal(f.elements.get('refreshDevices').textContent,'设置 OBS');
  await f.elements.get('refreshDevices').onclick();
  assert.equal(f.run('store.draft.source'),'游戏窗口');
  Object.assign(f.data.snapshot,detectedDefaults());await f.run('poll()');
  assert.equal(f.run('store.draft.source'),'整个显示器');
  assert.equal(f.run('store.draft.monitor'),'primary');assert.equal(f.run('store.draft.mic'),'default');
  assert.equal(f.elements.get('refreshDevices').textContent,'刷新设备');
  assert.equal(f.run('store.saved.source'),'游戏窗口');
  assert.equal(f.calls.some(c=>['save_preset','start_recording'].includes(c.name)),false);
  f.elements.get('target').value='secondary';f.elements.get('target').onchange();
  await f.elements.get('refreshDevices').onclick();await f.run('poll()');
  assert.equal(f.run('store.draft.monitor'),'secondary','ordinary refresh preserves the selected display');
});

test('setup never guesses defaults or reuses old completion metadata',async()=>{
  const f=await fixture(setupSnapshot());f.elements.get('settingsButton').onclick();
  await f.elements.get('refreshDevices').onclick();
  Object.assign(f.data.snapshot,detectedDefaults(),{device_refresh:{id:'old-refresh',state:'succeeded'}});
  await f.run('poll()');assert.equal(f.run('store.draft.source'),'游戏窗口');
  f.data.snapshot.device_refresh={id:'refresh-1',state:'succeeded'};
  f.data.snapshot.device_defaults={monitor:'missing',mic:'disabled'};
  f.data.snapshot.devices.mic.push({itemValue:'disabled',itemName:'Disabled',itemEnabled:false});
  await f.run('poll()');assert.equal(f.run('store.draft.monitor'),'');assert.equal(f.run('store.draft.mic'),'');
  assert.match(f.elements.get('wizardError').textContent,/手动选择/);
});

test('late setup results cannot overwrite a reopened draft or a manually edited device choice',async()=>{
  const f=await fixture(setupSnapshot());f.elements.get('settingsButton').onclick();
  await f.elements.get('refreshDevices').onclick();f.elements.get('wizardCancel').onclick();
  f.elements.get('settingsButton').onclick();Object.assign(f.data.snapshot,detectedDefaults());await f.run('poll()');
  assert.equal(f.run('store.draft.source'),'游戏窗口');
  Object.assign(f.data.snapshot,setupSnapshot());await f.run('poll()');
  await f.elements.get('refreshDevices').onclick();
  const mic=f.elements.get('mic');mic.value='my-manual-choice';mic.listeners.change();
  Object.assign(f.data.snapshot,detectedDefaults());await f.run('poll()');
  assert.equal(f.run('store.draft.mic'),'my-manual-choice');assert.equal(f.run('store.draft.source'),'游戏窗口');
});

test('failed OBS setup keeps existing draft choices and shows the concrete failure',async()=>{
  const f=await fixture(setupSnapshot());f.elements.get('settingsButton').onclick();
  await f.elements.get('refreshDevices').onclick();
  f.data.snapshot.device_refresh={id:'refresh-1',state:'failed',error:'OBS 未能启动'};await f.run('poll()');
  assert.equal(f.run('store.draft.source'),'游戏窗口');assert.equal(f.run('store.draft.mic'),'microphone');
  assert.match(f.elements.get('wizardError').textContent,/OBS 未能启动/);
});
