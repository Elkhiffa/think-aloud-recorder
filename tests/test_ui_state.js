'use strict';
// Synthetic front-end state and bridge tests. No browser, capture, or network.
// Session-list rules (row actions, filters, processing badges, row dates) live in ui/desk.js and are
// covered by tests/test_desk_ui.js; this file covers the main window, including its latest-session block.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {State,vocabularyWords,updateView,lastInstallView} = require('../ui/state.js');
const {matchedWindowValue,inventoryView,savedDeviceLabel} = require('../ui/state.js');

test('open drafts retain their vocabulary revision across live agent refreshes',()=>{
  const state=new State();
  state.accept({active_preset_id:'one',config:{game:'Synthetic',vocabulary_revision:'before'}});
  state.openDraft('edit');
  state.accept({active_preset_id:'one',config:{game:'Synthetic',vocabulary_revision:'after'}});
  assert.equal(state.presetPayload().expected_vocabulary_revision,'before');
  state.cancelDraft();state.openDraft('edit');
  assert.equal(state.presetPayload().expected_vocabulary_revision,'after');
  state.openDraft('new');
  assert.equal(state.presetPayload().expected_vocabulary_revision,undefined);
});

test('saved window may display its unique live match without changing a draft',()=>{
  const old='Game:OldRandom:game.exe',live='Game:NewRandom:game.exe';
  const items=[{itemValue:live,itemEnabled:true}];
  const selection={requested:old,resolved:live,status:'matched'};
  assert.equal(matchedWindowValue(old,items,selection),live);
  assert.equal(matchedWindowValue('Manually selected:Class:other.exe',items,selection),'Manually selected:Class:other.exe');
  assert.equal(matchedWindowValue(old,[],selection),old);
  assert.equal(matchedWindowValue(old,[...items,...items],selection),old);
  assert.equal(matchedWindowValue(old,[{itemValue:live,itemEnabled:false}],selection),old);
  assert.equal(matchedWindowValue(old,items,{...selection,status:'ambiguous'}),old);
  const state=new State();state.accept({active_preset_id:'a',config:{window:old},readiness:{window_selection:selection}});
  state.openDraft('edit');assert.equal(state.draft.window,old);
});

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

test('operation capture is opt-in, saved per preset, and cleared on full-screen selection',()=>{
  const state=new State();state.accept(snapshot());state.openDraft('new');
  assert.equal(state.draft.record_inputs,false);
  state.updateDraft('record_inputs',true);assert.equal(state.presetPayload().record_inputs,true);
  state.updateDraft('source','整个显示器');assert.equal(state.draft.record_inputs,false);
  state.updateDraft('record_inputs',true);assert.equal(state.draft.record_inputs,false);
  state.updateDraft('source','游戏窗口');assert.equal(state.draft.record_inputs,false);
  state.cancelDraft();assert.equal(state.saved.record_inputs,undefined);
  state.accept(snapshot({config:{...snapshot().config,record_inputs:true}}));state.openDraft('edit');
  assert.equal(state.draft.record_inputs,true);
  state.accept(snapshot({config:{...snapshot().config,source:'整个显示器',record_inputs:true}}));state.openDraft('edit');
  assert.equal(state.draft.record_inputs,false,'legacy inconsistent settings cannot activate screen-wide capture');
});

test('wizard explains input capture boundary and does not enable it while selecting devices',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();
  const toggle=f.elements.get('recordInputs');assert.equal(toggle.checked,false);assert.equal(toggle.disabled,false);
  toggle.checked=true;toggle.onchange();assert.equal(f.run('store.draft.record_inputs'),true);
  const source=f.elements.get('source');source.value='整个显示器';source.listeners.change();
  assert.equal(toggle.disabled,true);assert.equal(toggle.checked,false);
  assert.match(f.elements.get('inputRecordingHint').textContent,/“游戏窗口”.*操作记录/);
  source.value='游戏窗口';source.listeners.change();assert.equal(toggle.disabled,false);assert.equal(toggle.checked,false);
  assert.equal(f.calls.some(call=>call.name==='start_recording'),false);
});

// Row actions moved to the desk window (tests/test_desk_ui.js). The main window keeps the latest
// session only: review it, and never offer a second transcription while one is running.
test('latest session: a playable processing session opens review but offers no re-transcription',async()=>{
  const sessions=[{id:'pending-text',game:'Game',session_name:'Door <attempt>',state:'转写中',can_review:true},{id:'no-video',game:'Game',state:'转写中',can_review:false}];
  const f=await fixture(snapshot({sessions,background_jobs:sessions.map(s=>({session_id:s.id,state:'running'}))}));
  const last=f.elements.get('lastSession');
  assert.ok(last.innerHTML.includes('Door &lt;attempt&gt;'));assert.ok(!last.innerHTML.includes('Door <attempt>'));
  assert.equal(findTag(last,'data-last-review','pending-text').disabled,false);
  assert.equal(findTag(last,'data-last-process'),null);assert.equal(findTag(last,'data-copy-handoff'),null);
  assert.match(last.innerHTML,/<li class="now">转写中<\/li>/);
  click(last,'data-last-review');await settle();
  assert.deepEqual(plain(f.calls.filter(c=>c.name==='open_review').map(c=>c.args)),[['pending-text']]);
  f.data.snapshot.sessions=[sessions[1],sessions[0]];await f.run('poll()');
  assert.equal(findTag(last,'data-last-review','no-video').disabled,true);
  assert.equal(findTag(last,'data-last-process'),null);
  assert.equal(f.calls.some(c=>c.name==='process_session'),false);
});

test('latest session: external preprocessing labels never change recording state or disable review',async()=>{
  const sessions=['none','processing','complete','failed','stale'].map((state,i)=>({id:'agent-'+i,
    game:'原始名称',state:'可回看',can_review:true,preprocessing:{state,...(state==='none'?{}:{label:'外部 <整理>',reason:'保留原始素材'})}}));
  const f=await fixture(snapshot({sessions}));const last=f.elements.get('lastSession');const titles=new Set();
  for(const s of sessions){
    assert.equal(f.run(`sessionKind(store.snapshot.sessions.find(s=>s.id==='${s.id}'))`),'ready');
    assert.equal(f.run(`canReview(store.snapshot.sessions.find(s=>s.id==='${s.id}'))`),true);
    f.data.snapshot.sessions=[s,...sessions.filter(other=>other!==s)];await f.run('poll()');
    assert.equal(findTag(last,'data-last-review',s.id).disabled,false);
    assert.equal(findTag(last,'data-last-process'),null,'a finished transcription is not offered again');
    assert.doesNotMatch(last.innerHTML,/<整理>/);
    if(['failed','stale'].includes(s.preprocessing.state))assert.match(last.innerHTML,/<li class="fail">外部 &lt;整理&gt;<\/li>/);
    titles.add(/<p class="last-name">(.*?)<\/p>/.exec(last.innerHTML)[1]);
  }
  assert.equal(titles.size,1,'the external label never replaces the session title');assert.doesNotMatch([...titles][0],/外部/);
});

test('latest session: a result still being checked shows a note, never the hand-off, until it is validated',async()=>{
  // 触发路径：用户 → 启动记录器 → 场次列表先返回、整理结果在后台核对（state=checking）→ 上一场显示“正在核对” → 不修会显示“待整理”和“复制整理指令”。
  const checking={id:'checked',game:'Game',state:'可回看',can_review:true,path:'D:\\Saved\\sessions\\checked',preprocessing:{state:'checking',label:'核对中'}};
  const f=await fixture(snapshot({sessions:[checking]}));const last=f.elements.get('lastSession');
  assert.match(last.innerHTML,/正在核对整理结果/);
  assert.doesNotMatch(last.innerHTML,/data-copy-handoff|待整理/);
  assert.equal(findTag(last,'data-last-review','checked').disabled,false);
  f.data.snapshot.sessions=[{...checking,preprocessing:{state:'complete',kinds:{obstacle:2,confusion:1}}}];await f.run('poll()');
  assert.doesNotMatch(last.innerHTML,/正在核对/);assert.match(last.innerHTML,/class="kleg"/);
});

test('latest session: handoff copy names the session folder; start and retry transcription need confirmation',async()=>{
  const ready={id:'ready',game:'Game',state:'可回看',can_review:true,path:'D:\\Saved\\sessions\\ready',preprocessing:{state:'none'}};
  const f=await fixture(snapshot({sessions:[ready]}));const last=f.elements.get('lastSession');
  assert.equal(findTag(last,'data-last-process'),null);
  await click(last,'data-copy-handoff','ready');await settle();
  assert.match(f.data.clipboard,/场次文件夹：D:\\Saved\\sessions\\ready/);assert.match(f.data.clipboard,/资料库：D:\\Saved/);
  assert.equal(f.calls.some(c=>['process_session','open_review'].includes(c.name)),false);
  f.data.snapshot.sessions=[{id:'failed',game:'Game',state:'失败',error:'Cloud <failure>',can_review:false}];await f.run('poll()');
  assert.ok(findTag(last,'data-last-process','failed'));assert.equal(findTag(last,'data-last-review','failed').disabled,true);
  assert.match(last.innerHTML,/>重试转写</);assert.match(last.innerHTML,/Cloud &lt;failure&gt;/);
  click(last,'data-last-process','failed');
  assert.equal(f.elements.get('actionDialog').open,true);assert.match(f.elements.get('actionBody').innerHTML,/上传这次的麦克风录音到 Qwen/);
  assert.equal(f.calls.some(c=>c.name==='process_session'),false,'nothing is uploaded before confirmation');
  await f.elements.get('actionFooter').children.find(button=>button.textContent==='开始整理').onclick();
  assert.deepEqual(plain(f.calls.filter(c=>c.name==='process_session').map(c=>c.args)),[['failed']]);
  f.data.snapshot.sessions=[{id:'pending',game:'Game',state:'待转写',can_review:false}];await f.run('poll()');
  assert.match(last.innerHTML,/>开始转写</);
  f.data.snapshot.config.transcription_provider='later';await f.run('poll()');
  click(last,'data-last-process','pending');assert.equal(f.elements.get('actionDialog').open,true);
  assert.equal(f.elements.get('actionFooter').children.some(button=>button.textContent==='开始整理'),false);
  assert.equal(f.calls.filter(c=>c.name==='process_session').length,1);
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
const fillFirstUse="store.updateDraft('game','New Game');store.updateDraft('window','window-id');store.updateDraft('mic','mic-id')";

test('existing sibling database requires explicit reuse, bound to the path and cleared on cancellation',async()=>{
  const f=await fixture(firstUseVault());assert.equal(f.run('sheetMode'),'first');
  f.run(fillFirstUse);toStep(f,'vault');
  assert.equal(f.elements.get('reuseVaultNotice').classList.contains('hidden'),false);
  assert.equal(f.elements.get('wizardNext').disabled,true);assert.equal(f.calls.some(c=>c.name==='save_preset'),false);
  f.elements.get('reuseVault').onclick();assert.equal(f.elements.get('wizardNext').disabled,false);
  assert.equal(f.run('store.presetPayload().confirmed_vault'),'D:\\Shared\\think-aloud-database');
  await f.run('poll()');assert.equal(f.elements.get('wizardNext').disabled,false);
  f.elements.get('wizardCancel').onclick();assert.equal(sheetIsOpen(f),false);
  f.elements.get('settingsButton').onclick();assert.equal(f.run('sheetMode'),'first');f.run(fillFirstUse);toStep(f,'vault');
  assert.equal(f.elements.get('wizardNext').disabled,true);assert.equal(f.run('store.confirmedVault'),'');
  f.data.chosenDirectory='D:\\Different Library';await f.elements.get('chooseVault').onclick();
  assert.equal(f.run('store.draft.vault'),'D:\\Different Library');assert.equal(f.elements.get('reuseVaultNotice').classList.contains('hidden'),true);
  assert.equal(f.elements.get('wizardNext').disabled,false);
  assert.equal(f.run('store.presetPayload().confirmed_vault'),'D:\\Different Library');
  assert.equal(f.calls.some(c=>c.name==='save_preset'),false);
});

test('folder appearing at save returns wizard to explicit reuse without silently retrying',async()=>{
  const f=await fixture(firstUseVault(false));
  f.run(fillFirstUse);toStep(f,'vault');
  assert.equal(f.elements.get('wizardNext').disabled,false);f.data.vaultRace=true;await f.run('finishWizard()');
  assert.equal(sheetIsOpen(f),true);assert.equal(f.run('currentStepKey()'),'vault');assert.equal(f.elements.get('wizardNext').disabled,true);
  assert.equal(f.elements.get('reuseVault').classList.contains('hidden'),false);
  assert.equal(f.calls.filter(c=>c.name==='save_preset').length,1);
  f.elements.get('reuseVault').onclick();await f.run('finishWizard()');
  const saves=f.calls.filter(c=>c.name==='save_preset');assert.equal(saves.length,2);
  assert.equal(saves[0].args[0].confirmed_vault,undefined);assert.equal(saves[1].args[0].confirmed_vault,'D:\\Shared\\think-aloud-database');
  assert.equal(saves[1].args[1],null);
  assert.equal(sheetIsOpen(f),false);
});

function fakeDOM() {
  const html=fs.readFileSync(path.join(__dirname,'../ui/index.html'),'utf8');
  const elements=new Map();let document;
  class Element {
    constructor(id='') {this.id=id;this.value='';this.textContent='';this.innerHTML='';this.disabled=false;this.open=false;this.scrollTop=0;this.style={};this.dataset={};this.attributes={};this.listeners={};this.children=[];const classes=new Set();this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,on)=>{if(on===undefined)on=!classes.has(x);on?classes.add(x):classes.delete(x);return on;},contains:x=>classes.has(x)};}
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
    const cls=/\bclass="([^"]*)"/.exec(match[2]);if(cls)cls[1].split(/\s+/).filter(Boolean).forEach(name=>el.classList.add(name));
    elements.set(el.id,el);
  }
  document={activeElement:null,documentElement:{dataset:{}},getElementById:id=>elements.get(id),
    querySelector:selector=>selector.startsWith('#')?elements.get(selector.slice(1)):null,
    querySelectorAll:selector=>selector==='[data-draft]'?[...elements.values()].filter(el=>el.dataset.draft):selector==='[data-provider]'?[...elements.values()].filter(el=>el.dataset.provider):[],
    createElement:()=>new Element(),addEventListener(){}};
  return {document,elements};
}
// Delegated clicks: find the first rendered tag carrying `attr` (optionally with `value`) inside an element's
// innerHTML and hand its data-* attributes to the handler registered on `target` (default: the same element).
const decode=text=>String(text).replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&amp;/g,'&');
function findTag(el,attr,value){
  for(const match of el.innerHTML.matchAll(/<(\w+)\b([^>]*)>/g)){
    const attrs=match[2],hit=new RegExp(`(?:^|\\s)${attr}(?:="([^"]*)")?(?=[\\s>/]|$)`).exec(attrs);
    if(!hit||value!==undefined&&decode(hit[1]??'')!==value)continue;
    const dataset={};for(const data of attrs.matchAll(/(?:^|\s)data-([\w-]+)(?:="([^"]*)")?/g))dataset[data[1].replace(/-(\w)/g,(_,c)=>c.toUpperCase())]=decode(data[2]??'');
    return {dataset,attrs,disabled:/(?:^|\s)disabled(?=[\s>/]|$)/.test(attrs),hasAttribute:name=>new RegExp(`(?:^|\\s)${name}(?=[\\s=>/]|$)`).test(attrs)};
  }
  return null;
}
function click(el,attr,value,target=el){
  const node=findTag(el,attr,value);assert.ok(node,`${attr} ${value??''} is rendered`);
  return target.listeners.click({target:{closest:selector=>selector.split(',').some(part=>part.trim()===`[${attr}]`)?node:null},preventDefault(){}});
}
const plain=value=>JSON.parse(JSON.stringify(value));
const sheetIsOpen=f=>!f.elements.get('sheet').classList.contains('hidden');
const openGeneral=f=>f.elements.get('tabGeneral').onclick({preventDefault(){}});
function toStep(f,key){
  for(let i=0;i<4&&f.run('currentStepKey()')!==key;i++){f.elements.get('wizardNext').onclick();assert.equal(f.elements.get('wizardError').textContent,'');}
  assert.equal(f.run('currentStepKey()'),key);
}
const GENERAL_KEYS=['source','monitor','mic','preset','language','transcription_provider','record_inputs'];
const GAME_PAYLOAD_KEYS=['name','game','window','vault','hotword_manual','game_hotword_files','expected_vocabulary_revision','confirmed_vault'];
const mergeFiles=(general,game)=>{const seen=new Set();return [...general,...game].filter(file=>file&&!seen.has(file.id)&&seen.add(file.id));};
async function settle(){for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));}
async function fixture(initial=snapshot()) {
  const {document,elements}=fakeDOM();const calls=[],timers=[];const data={snapshot:initial,inventorySequence:0,holdInventory:initial.device_inventory?.state==='idle'};
  // Plausible bridge: save_general merges shared keys into every game's config; save_preset stores one game.
  function saveGeneral(payload){
    const allowed=new Set([...GENERAL_KEYS,'general_hotword_files','expected_vocabulary_revision','library_root']);
    const extra=Object.keys(payload).filter(key=>!allowed.has(key));if(extra.length)return {ok:false,error:'通用设置包含不支持的字段：'+extra.join('、')};
    const config={...data.snapshot.config},oldGeneral=new Set((config.general_hotword_files||[]).map(file=>file.id));
    if(!Array.isArray(config.hotword_files)&&config.hotword_manual===undefined)config.hotword_manual=config.hotwords||'';
    const game=(config.hotword_files||[]).filter(file=>!oldGeneral.has(file.id));
    for(const key of GENERAL_KEYS)if(key in payload)config[key]=payload[key];
    if(Array.isArray(payload.general_hotword_files)){config.general_hotword_files=payload.general_hotword_files;config.hotword_files=mergeFiles(payload.general_hotword_files,game);}
    if('library_root' in payload)config.library_root=payload.library_root;
    data.snapshot={...data.snapshot,config,readiness:{ready:false,checking:true,errors:[]}};
    return {ok:true,data:config};
  }
  function savePreset(payload,presetId){
    if(data.vaultRace){data.vaultRace=false;data.snapshot.default_vault={...data.snapshot.default_vault,exists:true,is_directory:true,requires_confirmation:true};return {ok:false,code:'VAULT_REUSE_REQUIRED',error:'请确认使用已有资料库。'};}
    const presets=data.snapshot.presets||[],id=presetId||(presets.some(p=>p.id==='created')?'created-'+(presets.length+1):'created');
    const {name,game_hotword_files,expected_vocabulary_revision,confirmed_vault,...fields}=payload;
    const config={...data.snapshot.config,...fields,game:name,configured:true};
    if(Array.isArray(game_hotword_files))config.hotword_files=mergeFiles(config.general_hotword_files||[],game_hotword_files);
    const row={id,name,vault:config.vault};
    data.snapshot={...data.snapshot,config,active_preset_id:id,presets:presetId?presets.map(p=>p.id===presetId?row:p):[...presets,row],readiness:{ready:false,checking:true,errors:[]}};
    return {ok:true,data:{id}};
  }
  const api=new Proxy({}, {get(_target,name){return async(...args)=>{calls.push({name,args});if(name==='get_state')return {ok:true,data:JSON.parse(JSON.stringify(data.snapshot))};if(name==='refresh_device_inventory'){if(data.inventoryHandler)return data.inventoryHandler();const id='inventory-'+(++data.inventorySequence);data.snapshot.device_inventory={id,state:data.holdInventory?'running':'succeeded',window_selection:data.snapshot.device_inventory?.window_selection||data.snapshot.readiness?.window_selection};return data.inventoryResult||{ok:true,data:{inventory_id:id}};}if(name==='refresh_devices')return data.refreshResult||{ok:true,data:{started:true,refresh_id:'refresh-1'}};if(name==='choose_directory')return {ok:true,data:{path:data.chosenDirectory||null}};if(name==='choose_hotword_files')return data.dictionaryError?{ok:false,error:data.dictionaryError}:{ok:true,data:{files:data.chosenFiles||[]}};if(name==='save_general')return saveGeneral(plain(args[0]));if(name==='save_preset')return savePreset(plain(args[0]),args[1]);return {ok:true,data:{}};};}});
  const context=vm.createContext({document,window:{pywebview:{api},addEventListener(){}},localStorage:{getItem(){},setItem(){}},setTimeout(fn,ms){timers.push({fn,ms});return timers.length;},clearTimeout(){},setInterval(){},CSS:{escape:x=>x},performance,console,matchMedia:()=>({matches:false,addEventListener(){}}),getComputedStyle:()=>({getPropertyValue:()=>''}),navigator:{clipboard:{writeText:async text=>{data.clipboard=text;}}}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/state.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/app.js'),'utf8'),context);
  await settle();return {context,elements,calls,timers,data,run:source=>vm.runInContext(source,context)};
}

test('actual UI opens first-use wizard; cancel does not persist or enable recording',async()=>{
  const f=await fixture(snapshot({presets:[],active_preset_id:null,config:{...snapshot().config,configured:false},readiness:{ready:false,checking:false,errors:[{step:1,message:'Create preset'}]}}));
  assert.equal(sheetIsOpen(f),true);assert.equal(f.run('sheetMode'),'first');assert.equal(f.run('currentStepKey()'),'method');
  f.elements.get('wizardCancel').onclick();
  assert.equal(sheetIsOpen(f),false);assert.equal(f.run('store.draft'),null);
  assert.equal(f.elements.get('recordButton').disabled,true);
  assert.equal(f.calls.some(call=>['save_preset','save_general'].includes(call.name)),false);
});

test('with no game yet, the ＋ tab runs the full first-use setup and cannot save without a microphone',async()=>{
  const f=await fixture(snapshot({presets:[],active_preset_id:null,config:{...snapshot().config,configured:false},readiness:{ready:false,checking:false,errors:[{step:1,message:'Create preset'}]}}));
  f.elements.get('wizardCancel').onclick();
  await click(f.elements.get('gameTabs'),'data-game-add');
  assert.equal(f.run('sheetMode'),'first','a first game also needs the shared microphone and transcription settings');
  f.run("store.updateDraft('game','New Game');store.updateDraft('window','window-id');store.updateDraft('mic','');store.updateDraft('vault','D:\\\\Library\\\\New Game')");
  await f.run('finishWizard()');
  assert.equal(f.calls.some(call=>call.name==='save_preset'),false,'no save while the microphone is empty');
  assert.match(f.elements.get('wizardError').textContent,/麦克风/);
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

test('actual settings save stores only the edited tab, then polls fresh state before reporting; never starts capture',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();await settle();
  assert.equal(f.elements.get('wizardNext').classList.contains('hidden'),true);assert.equal(f.elements.get('wizardCancel').textContent,'关闭');
  const input=f.elements.get('game');input.value='Edited preset';input.listeners.input();
  assert.equal(f.elements.get('sheetMessage').textContent,'有未保存的修改');
  assert.equal(f.elements.get('wizardNext').classList.contains('hidden'),false);assert.equal(f.elements.get('wizardNext').textContent,'保存');
  let before=f.calls.length;f.elements.get('wizardNext').onclick();await settle();
  let calls=f.calls.slice(before);assert.equal(calls[0].name,'save_preset');assert.equal(calls[0].args[1],'one');
  assert.equal(calls[0].args[0].name,'Edited preset');
  assert.deepEqual(Object.keys(calls[0].args[0]).filter(key=>!GAME_PAYLOAD_KEYS.includes(key)),[],'a game save carries no shared settings');
  assert.equal(calls.at(-1).name,'get_state');assert.equal(f.elements.get('toast').textContent,'游戏设置已保存。');
  assert.equal(f.run('store.dirty'),false);assert.equal(f.run('store.draft.game'),'Edited preset');
  assert.equal(f.elements.get('sheetMessage').textContent,'');assert.equal(f.elements.get('wizardNext').classList.contains('hidden'),true);
  assert.equal(f.elements.get('recordButton').disabled,true);
  openGeneral(f);const language=f.elements.get('language');language.value='en';language.listeners.change();
  before=f.calls.length;f.elements.get('wizardNext').onclick();await settle();
  calls=f.calls.slice(before);assert.equal(calls[0].name,'save_general');assert.equal(calls[0].args.length,1);
  assert.deepEqual(Object.keys(calls[0].args[0]).filter(key=>![...GENERAL_KEYS,'general_hotword_files','expected_vocabulary_revision','library_root'].includes(key)),[],'a shared save carries no game fields');
  assert.equal(calls[0].args[0].language,'en');assert.equal(calls.at(-1).name,'get_state');
  assert.equal(f.run('store.saved.language'),'en');assert.equal(f.run('store.saved.game'),'Edited preset');
  assert.equal(f.calls.some(call=>call.name==='start_recording'),false);
});

test('session dates use local minute precision and preserve readable invalid values',async()=>{
  const timestamp='2026-09-20T17:26:53.973896+08:00';
  const expected=new Intl.DateTimeFormat('sv-SE',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(timestamp));
  const f=await fixture(snapshot({sessions:[{id:'dated',game:'Dated session',created:timestamp,duration:10,state:'待整理'}]}));
  assert.equal(f.run(`formatDate(${JSON.stringify(timestamp)})`),expected);
  const local=new Date(timestamp),pad=n=>String(n).padStart(2,'0'),rendered=f.elements.get('lastSession').innerHTML;
  assert.ok(rendered.includes('<h2 class="sec-title">上一场</h2>'));assert.ok(rendered.includes(`<p class="note">${local.getMonth()+1}月${local.getDate()}日 周${'日一二三四五六'[local.getDay()]} ${pad(local.getHours())}:${pad(local.getMinutes())} · 00:00:10`));
  assert.ok(!rendered.includes(timestamp));assert.ok(!rendered.includes(`${pad(local.getHours())}:${pad(local.getMinutes())}:${pad(local.getSeconds())}`));
  assert.equal(f.run("formatDate('2026-01-02T03:04:59')"),'2026-01-02 03:04');
  assert.equal(f.run("formatDate('未记录时间')"),'未记录时间');
  assert.equal(f.run("formatDate('not-a-date')"),'not-a-date');
  assert.equal(f.run('formatDate(null)'),'—');
  f.data.snapshot.sessions=[{id:'undated',game:'Undated',created:'未记录时间',duration:10,state:'待整理'}];await f.run('poll()');
  assert.doesNotMatch(f.elements.get('lastSession').innerHTML,/NaN|Invalid Date|undefined/);
});

test('background transcription leaves Start and game switching available; capture save and readiness still block',async()=>{
  const jobs=[{id:'job-a',session_id:'a',game:'Game A',state:'running',detail:'Uploading microphone'},
    {id:'job-b',session_id:'b',game:'Game B',state:'queued',detail:''}];
  const sessions=[{id:'a',game:'Game A',state:'转写中',duration:60},{id:'b',game:'Game B',state:'待整理',duration:30}];
  const f=await fixture(snapshot({background_jobs:jobs,sessions,presets:[{id:'one',name:'Saved game',vault:'D:\\Saved'},{id:'two',name:'Other game',vault:'D:\\Other'}]}));
  assert.equal(f.elements.get('recordButton').disabled,false);assert.equal(f.elements.get('recordButtonText').textContent,'开始录制');
  const tabs=f.elements.get('gameTabs');assert.ok(findTag(tabs,'data-game','two'));assert.doesNotMatch(tabs.innerHTML,/lock/);
  assert.equal(f.elements.get('settingsButton').disabled,false);
  assert.equal(f.elements.get('jobDetail').textContent,'');
  const last=f.elements.get('lastSession');
  assert.match(last.innerHTML,/<li class="now">转写中<\/li>/);assert.equal(findTag(last,'data-last-process'),null);
  f.data.snapshot.sessions=[sessions[1],sessions[0]];await f.run('poll()');
  assert.match(last.innerHTML,/<li class="now">等待转写<\/li>/);assert.equal(findTag(last,'data-last-process'),null);
  await click(tabs,'data-game','two');
  assert.deepEqual(plain(f.calls.filter(call=>call.name==='select_preset').map(call=>call.args)),[['two']]);
  f.elements.get('recordButton').onclick();await settle();assert.ok(f.calls.some(call=>call.name==='start_recording'));
  f.data.snapshot.activity={busy:true,kind:'saving',status:'正在保存录像',detail:''};await f.run('poll()');
  assert.equal(f.elements.get('recordButton').disabled,true);assert.equal(f.elements.get('recordButtonText').textContent,'正在保存…');
  f.data.snapshot.activity={busy:false,kind:'idle'};f.data.snapshot.readiness={ready:false,checking:false,errors:[{message:'游戏窗口未打开'}]};await f.run('poll()');
  assert.equal(f.elements.get('recordButton').disabled,true);assert.deepEqual(plain(f.run('currentBlockers')),['游戏窗口未打开']);assert.match(f.elements.get('blockers').innerHTML,/游戏窗口未打开/);
});

test('background progress and failures stay on their session without replacing current timer or Stop',async()=>{
  const initial=snapshot({activity:{kind:'recording',busy:false,status:'录制中',active_id:'b',elapsed_seconds:18},
    background_jobs:[{id:'job-a',session_id:'a',state:'running',detail:'Uploading A'}],
    sessions:[{id:'a',game:'A',state:'转写中'},{id:'b',game:'B',state:'录制中'}]});
  const f=await fixture(initial);
  assert.equal(f.elements.get('recordButton').disabled,false);assert.equal(f.elements.get('recordButtonText').textContent,'结束录制');
  assert.equal(f.elements.get('recordingTime').textContent,'00:00:18');assert.equal(f.elements.get('jobDetail').textContent,'');
  assert.equal(f.elements.get('lastSection').classList.contains('hidden'),true);assert.equal(f.elements.get('liveGauges').classList.contains('hidden'),false);
  f.data.snapshot.background_jobs[0].detail='<Waiting for cloud>';await f.run('poll()');
  assert.equal(f.elements.get('jobDetail').textContent,'');assert.doesNotMatch(f.elements.get('homeStatus').textContent+f.elements.get('blockers').innerHTML,/Waiting/);
  f.data.snapshot.background_jobs=[];f.data.snapshot.sessions[0]={id:'a',game:'A',state:'失败',error:'Cloud failure'};await f.run('poll()');
  assert.deepEqual(plain(f.run('currentBlockers')),[]);assert.equal(f.elements.get('statusSlot').classList.contains('hidden'),true);
  assert.equal(f.elements.get('recordButton').disabled,false);
  assert.equal(f.elements.get('recordingTime').textContent,'00:00:18');assert.equal(f.elements.get('jobDetail').textContent,'');
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
  const f=await fixture();f.elements.get('settingsButton').onclick();await settle();openGeneral(f);
  assert.equal(f.run('currentStepKey()'),'general');
  f.data.chosenFiles=[{id:'a',name:'角色.txt',words:['同词','角色']},{id:'b',name:'<道具>.txt',words:['同词','道具']}];
  await f.elements.get('chooseHotwordFiles').onclick();
  assert.equal(f.run('store.draft.hotword_files.length'),2);assert.equal(f.run('store.draft.hotwords'),'同词\n角色\n道具\nSaved vocabulary');
  assert.ok(f.elements.get('hotwordFiles').innerHTML.includes('&lt;道具&gt;.txt'));assert.ok(!f.elements.get('gameHotwordFiles').innerHTML.includes('道具'));
  assert.ok(f.elements.get('vocabularyCount').textContent.includes('4 个词'));
  assert.equal(f.calls.some(call=>['save_preset','save_general'].includes(call.name)),false);
  f.data.chosenFiles=[];await f.elements.get('chooseHotwordFiles').onclick();assert.equal(f.run('store.draft.hotword_files.length'),2);
  f.data.dictionaryError='无法读取词库';await f.elements.get('chooseHotwordFiles').onclick();assert.equal(f.run('store.draft.hotword_files.length'),2);
  assert.equal(f.elements.get('wizardError').textContent,'无法读取词库');
  click(f.elements.get('hotwordFiles'),'data-remove-vocabulary','a',f.elements.get('wizardBody'));
  assert.equal(f.run('store.draft.hotwords'),'同词\n道具\nSaved vocabulary');
  assert.equal(f.calls.some(call=>['save_preset','save_general'].includes(call.name)),false);
  f.elements.get('wizardNext').onclick();await settle();
  const save=f.calls.find(call=>call.name==='save_general');assert.ok(save);assert.deepEqual(plain(save.args[0].general_hotword_files.map(file=>file.id)),['b']);
  assert.equal(f.calls.some(call=>call.name==='save_preset'),false);
  assert.equal(f.run('store.draft.hotword_files.length'),1);assert.equal(f.run('store.draft.hotword_files[0].id'),'b');
  f.elements.get('wizardCancel').onclick();assert.equal(sheetIsOpen(f),false);
  f.elements.get('settingsButton').onclick();openGeneral(f);assert.equal(f.run('store.draft.hotword_files.length'),1);assert.equal(f.run('store.draft.hotword_files[0].id'),'b');
  assert.ok(f.elements.get('hotwordFiles').innerHTML.includes('&lt;道具&gt;.txt'));
  await f.elements.get('dictionaryDownload').onclick({preventDefault(){}});await settle();
  const link=f.calls.find(call=>call.name==='open_dictionary_site');assert.ok(link);assert.equal(link.args.length,0);
});


test('first-use method introduction advances without saving; device validation still gates later steps',async()=>{
  const f=await fixture(firstUseVault(false));
  assert.equal(f.run('step'),0);assert.equal(f.run('currentStepKey()'),'method');
  assert.equal(f.elements.get('panelMethod').classList.contains('hidden'),false);
  assert.equal(f.elements.get('wizardNext').textContent,'开始设置');
  f.elements.get('wizardNext').onclick();
  assert.equal(f.run('step'),1);assert.equal(f.run('currentStepKey()'),'general');
  const language=f.elements.get('language');language.value='en';language.listeners.change();
  f.elements.get('wizardBack').onclick();assert.equal(f.run('step'),0);
  f.elements.get('wizardNext').onclick();assert.equal(f.run('store.draft.language'),'en');
  f.elements.get('wizardNext').onclick();assert.equal(f.run('step'),1);
  assert.ok(f.elements.get('wizardError').textContent.includes('麦克风'));
  const mic=f.elements.get('mic');mic.value='microphone';mic.listeners.change();
  f.elements.get('wizardNext').onclick();assert.equal(f.run('currentStepKey()'),'game');
  f.elements.get('game').value='合成体验';f.elements.get('game').listeners.input();
  f.elements.get('wizardBack').onclick();assert.equal(f.run('currentStepKey()'),'general');
  f.elements.get('wizardNext').onclick();assert.equal(f.run('currentStepKey()'),'game');assert.equal(f.run('store.draft.game'),'合成体验');
  f.elements.get('wizardNext').onclick();assert.equal(f.run('currentStepKey()'),'game');
  assert.ok(f.elements.get('wizardError').textContent.includes('窗口'));
  assert.equal(f.calls.some(call=>['save_preset','save_general','start_recording'].includes(call.name)),false);
  f.elements.get('wizardCancel').onclick();assert.equal(f.run('store.draft'),null);
  f.elements.get('methodButton').onclick();assert.equal(f.elements.get('actionDialog').open,true);
  assert.equal(f.run('store.draft'),null);
});

// Per the redesign the method guide belongs to the first launch only; a new game is two steps (game, folder).
test('editing a preset excludes the guide and Back cannot enter it; only first use shows the guide',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();
  assert.equal(f.run('sheetMode'),'settings');assert.equal(f.run('currentStepKey()'),'game');
  assert.equal(f.elements.get('panelMethod').classList.contains('hidden'),true);
  assert.equal(f.elements.get('wizardBack').classList.contains('hidden'),true);
  f.elements.get('wizardBack').onclick();assert.equal(f.run('currentStepKey()'),'game');
  openGeneral(f);assert.equal(f.run('currentStepKey()'),'general');assert.equal(f.elements.get('panelMethod').classList.contains('hidden'),true);
  f.elements.get('wizardCancel').onclick();
  await click(f.elements.get('gameTabs'),'data-game-add');
  assert.equal(f.run('sheetMode'),'new');assert.equal(f.run('step'),0);assert.equal(f.run('currentStepKey()'),'game');
  assert.equal(f.elements.get('panelMethod').classList.contains('hidden'),true);assert.doesNotMatch(f.elements.get('wizardSteps').innerHTML,/记录方法/);
  f.elements.get('wizardBack').onclick();assert.equal(f.run('currentStepKey()'),'game');
  f.run("store.updateDraft('game','Second game');store.updateDraft('window','game-window')");
  f.elements.get('wizardNext').onclick();assert.equal(f.run('currentStepKey()'),'vault');
  f.elements.get('wizardBack').onclick();assert.equal(f.run('currentStepKey()'),'game');
  f.elements.get('wizardBack').onclick();assert.equal(f.run('currentStepKey()'),'game');
  assert.equal(f.elements.get('panelMethod').classList.contains('hidden'),true);
  assert.equal(f.calls.some(call=>['save_preset','save_general','start_recording'].includes(call.name)),false);
});

test('readiness and specific blockers replace each other in the same live status slot',async()=>{
  const f=await fixture();
  assert.match(f.elements.get('homeStatus').innerHTML,/^<span>已就绪<\/span><span>游戏窗口 · [^<]+<\/span><span>麦克风<\/span>$/);
  assert.equal(f.elements.get('statusSlot').classList.contains('hidden'),true);
  f.data.snapshot.readiness={ready:false,checking:false,errors:[
    {message:'未找到游戏窗口，请先打开游戏。',step:1},
    {message:'云端密钥缺失，请重新配置。',step:2},
    {message:'麦克风不可用。',step:3},
  ]};
  await f.run('poll()');
  assert.equal(f.elements.get('recordButton').disabled,true);
  assert.equal(f.elements.get('homeStatus').textContent,'3 项检查未通过\n处理右侧事项后重新检查');
  assert.equal(f.elements.get('statusSlot').classList.contains('hidden'),false);
  // At most two reasons in the alert; the full list is one click away and never scrolls inside the alert.
  assert.equal(f.elements.get('blockers').innerHTML,'<li><span>未找到游戏窗口，请先打开游戏。</span></li><li><span>云端密钥缺失，请重新配置。</span></li>');
  assert.equal(f.elements.get('alertMore').classList.contains('hidden'),false);
  assert.equal(f.elements.get('alertMore').textContent,'全部 3 项');
  f.elements.get('alertMore').onclick();
  assert.match(f.elements.get('actionBody').innerHTML,/未找到游戏窗口，请先打开游戏。<\/li><li>云端密钥缺失，请重新配置。<\/li><li>麦克风不可用。/);
  assert.equal(f.elements.get('capturePanel').classList.contains('alerting'),true);
  f.data.snapshot.readiness={ready:true,checking:false,errors:[]};await f.run('poll()');
  assert.equal(f.elements.get('recordButton').disabled,false);
  assert.match(f.elements.get('homeStatus').innerHTML,/^<span>已就绪<\/span><span>游戏窗口 · [^<]+<\/span><span>麦克风<\/span>$/);
  assert.equal(f.elements.get('homeStatus').classList.contains('hidden'),false);
  assert.equal(f.elements.get('statusSlot').classList.contains('hidden'),true);
  assert.deepEqual(plain(f.run('currentBlockers')),[]);
  assert.equal(f.elements.get('capturePanel').classList.contains('alerting'),false);
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
  assert.equal(f.elements.get('statusSlot').classList.contains('hidden'),true);
});

test('with the game in front, the last check stays and an unchecked state is not called unmet',async()=>{
  // 触发路径：用户切到游戏窗口 → 记录器暂停空闲检查 → 主页仍显示上次的“已就绪”；还没检查过时写“切回这里时检查”，不说条件未满足。
  const f=await fixture(snapshot({readiness:{ready:true,checking:false,errors:[],deferred:true}}));
  assert.match(f.elements.get('homeStatus').innerHTML,/^<span>已就绪<\/span>/);
  assert.equal(f.elements.get('recordButton').disabled,false);
  f.data.snapshot.readiness={ready:false,checking:false,errors:[],deferred:true};await f.run('poll()');
  assert.equal(f.elements.get('homeStatus').textContent,'切回这里时检查录制条件');
  assert.equal(f.elements.get('statusSlot').classList.contains('hidden'),true);
});

test('a historical operation error cannot replace fresh ready status after recovery',async()=>{
  const f=await fixture(snapshot({activity:{busy:false,kind:'idle',status:'操作未完成',detail:'旧的密钥验证失败'}}));
  assert.equal(f.elements.get('recordButton').disabled,false);
  assert.match(f.elements.get('homeStatus').innerHTML,/^<span>已就绪<\/span><span>游戏窗口 · [^<]+<\/span><span>麦克风<\/span>$/);
  assert.equal(f.elements.get('statusSlot').classList.contains('hidden'),true);
  assert.deepEqual(plain(f.run('currentBlockers')),[]);
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
  const f=await fixture(snapshot({default_hotword_files:[bundled],config:{...snapshot().config,general_hotword_files:[bundled],hotword_files:[bundled]}}));
  await click(f.elements.get('gameTabs'),'data-game-add');assert.equal(f.run('sheetMode'),'new');
  assert.deepEqual(plain(f.run('store.draft.hotword_files.map(file=>file.id)')),['uiux-default']);
  assert.ok(f.elements.get('hotwordFiles').innerHTML.includes('uiux-terms.txt'));assert.ok(!f.elements.get('gameHotwordFiles').innerHTML.includes('uiux-terms.txt'));
  click(f.elements.get('hotwordFiles'),'data-view-vocabulary',bundled.id,f.elements.get('wizardBody'));
  assert.equal(f.elements.get('actionDialog').open,true);
  assert.match(f.elements.get('actionBody').innerHTML,/心智模型/);
  assert.match(f.elements.get('actionBody').innerHTML,/&lt;script&gt;unsafe&lt;\/script&gt;/);
  assert.doesNotMatch(f.elements.get('actionBody').innerHTML,/<script>/);
  assert.ok(!f.calls.some(call=>['save_preset','save_general','open_folder','start_recording'].includes(call.name)));
});

test('entering device setup focuses the name input, but polling never steals user focus',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();
  f.elements.get('mic').focus();await f.run('poll()');
  assert.equal(f.run('document.activeElement.id'),'mic');
  f.elements.get('wizardCancel').onclick();f.elements.get('settingsButton').onclick();
  assert.equal(f.run('document.activeElement.id'),'game','opening game settings focuses the game name');
  f.elements.get('wizardCancel').onclick();await click(f.elements.get('gameTabs'),'data-game-add');
  assert.equal(f.run('document.activeElement.id'),'game','a new game opens on its name');
});

test('two transcription tabs change only the draft and support keyboard selection',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();openGeneral(f);
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
  assert.equal(f.calls.some(c=>['save_preset','save_general','save_cloud_key','model_action'].includes(c.name)),false);
});

test('editing a legacy record-only preset requires an explicit choice before saving',async()=>{
  const f=await fixture(snapshot({config:{...snapshot().config,transcription_provider:'later'}}));
  f.elements.get('settingsButton').onclick();assert.equal(f.run('store.draft.transcription_provider'),'');
  assert.equal(f.run("'transcription_provider' in store.gamePayload()"),false,'saving a game cannot convert the shared choice');
  openGeneral(f);assert.equal(f.elements.get('providerChoiceHint').classList.contains('hidden'),false);
  const language=f.elements.get('language');language.value='en';language.listeners.change();
  assert.equal(f.elements.get('wizardNext').classList.contains('hidden'),false);
  f.elements.get('wizardNext').onclick();await settle();
  assert.equal(f.run('currentStepKey()'),'general');
  assert.match(f.elements.get('wizardError').textContent,/本地转写.*Qwen/);
  assert.equal(f.calls.some(c=>['save_preset','save_general'].includes(c.name)),false);
  assert.equal(f.elements.get('providerChoiceHint').classList.contains('hidden'),false);
  f.elements.get('wizardCancel').onclick();assert.equal(f.run('store.saved.transcription_provider'),'later');
});

const setupSnapshot=()=>snapshot({devices:{monitor:[],mic:[],window:[]},device_inventory:{id:'',state:'idle'},device_defaults:{monitor:'',mic:''}});
// Device defaults only initialize the first-use draft: a new game with existing games copies the shared devices.
const firstSetupSnapshot=()=>({...setupSnapshot(),presets:[],active_preset_id:null,config:{...snapshot().config,configured:false}});
const detectedDefaults=(id='inventory-1')=>({
  devices:{window:[],monitor:[{itemName:'Secondary',itemValue:'secondary',itemEnabled:true},{itemName:'Primary',itemValue:'primary',itemEnabled:true}],mic:[{itemName:'Default',itemValue:'default',itemEnabled:true}]},
  device_defaults:{monitor:'primary',mic:'default'},device_inventory:{id,state:'succeeded',error:''}
});

test('inventory metadata is required before an absent saved choice can be called missing',()=>{
  assert.equal(inventoryView({devices:{window:[],mic:[]}}).state,'idle');
  assert.equal(inventoryView(snapshot()).state,'cached');
  for(const state of ['idle','running','failed','succeeded'])assert.equal(inventoryView({device_inventory:{state}}).state,state);
  assert.equal(savedDeviceLabel('window','Game#3ATitle:OldClass:game.exe'),'Game:Title（game.exe）');
  assert.equal(savedDeviceLabel('mic','default'),'默认麦克风');
  assert.equal(savedDeviceLabel('mic','{opaque-guid}'),'已保存的麦克风');
  assert.equal(savedDeviceLabel('monitor','opaque-display-interface'),'已保存的显示器');
  assert.equal(savedDeviceLabel('window','opaque-window-id'),'已保存的游戏窗口');
});

test('opening an existing preset automatically reads inventory without changing saved or draft selections',async()=>{
  const f=await fixture(setupSnapshot());f.elements.get('settingsButton').onclick();await settle();
  const original=f.run('JSON.stringify(store.draft)');
  assert.equal(f.calls.filter(c=>c.name==='refresh_device_inventory').length,1);
  assert.equal(f.calls.filter(c=>c.name==='refresh_devices').length,0);
  assert.match(f.elements.get('deviceFeedback').textContent,/正在读取/);
  assert.equal(f.elements.get('refreshDevices').disabled,true);assert.equal(f.elements.get('refreshDevices').textContent,'正在读取…');
  await f.elements.get('refreshDevices').onclick();assert.equal(f.calls.filter(c=>c.name==='refresh_device_inventory').length,1);
  assert.equal(f.elements.get('wizardCancel').disabled,false);assert.equal(f.elements.get('source').disabled,false);
  assert.match(f.elements.get('target').innerHTML,/未确认/);
  assert.doesNotMatch(f.elements.get('target').innerHTML,/当前未找到/);
  Object.assign(f.data.snapshot,detectedDefaults());await f.run('poll()');
  assert.equal(f.run('JSON.stringify(store.draft)'),original);
  assert.match(f.elements.get('target').innerHTML,/当前未找到/);
  assert.equal(f.elements.get('refreshDevices').textContent,'刷新设备');
  assert.equal(f.run('store.saved.source'),'游戏窗口');
  assert.equal(f.calls.some(c=>['save_preset','start_recording'].includes(c.name)),false);
});

test('automatic new-draft read never applies defaults; explicit first refresh applies only verified defaults',async()=>{
  const f=await fixture(firstSetupSnapshot());await settle();assert.equal(f.run('sheetMode'),'first');
  Object.assign(f.data.snapshot,detectedDefaults());await f.run('poll()');
  assert.equal(f.run('store.draft.source'),'游戏窗口');assert.equal(f.run('store.draft.mic'),'');
  f.elements.get('wizardCancel').onclick();Object.assign(f.data.snapshot,firstSetupSnapshot());await f.run('poll()');
  f.elements.get('settingsButton').onclick();assert.equal(f.run('sheetMode'),'first');await settle();f.data.snapshot.device_inventory.state='succeeded';await f.run('poll()');await f.elements.get('refreshDevices').onclick();
  Object.assign(f.data.snapshot,detectedDefaults('inventory-3'));await f.run('poll()');
  assert.equal(f.run('store.draft.source'),'整个显示器');assert.equal(f.run('store.draft.monitor'),'primary');assert.equal(f.run('store.draft.mic'),'default');
  assert.equal(f.run('store.saved.source'),'游戏窗口');
  const monitor=f.elements.get('monitor');monitor.value='secondary';monitor.listeners.change();
  await f.elements.get('refreshDevices').onclick();Object.assign(f.data.snapshot,detectedDefaults('inventory-4'));await f.run('poll()');
  assert.equal(f.run('store.draft.monitor'),'secondary');
});

test('unverified defaults, superseded results and changed-back device choices never initialize the draft',async()=>{
  const f=await fixture(firstSetupSnapshot());await settle();assert.equal(f.run('sheetMode'),'first');
  f.data.snapshot.device_inventory.state='succeeded';await f.run('poll()');
  await f.elements.get('refreshDevices').onclick();
  Object.assign(f.data.snapshot,detectedDefaults('inventory-2'));f.data.snapshot.device_defaults={monitor:'missing',mic:'disabled'};
  f.data.snapshot.devices.mic.push({itemValue:'disabled',itemName:'Disabled',itemEnabled:false});await f.run('poll()');
  assert.equal(f.run('store.draft.monitor'),'');assert.equal(f.run('store.draft.mic'),'');assert.match(f.elements.get('wizardError').textContent,/手动选择/);
  f.elements.get('wizardCancel').onclick();Object.assign(f.data.snapshot,firstSetupSnapshot());await f.run('poll()');
  f.elements.get('settingsButton').onclick();assert.equal(f.run('sheetMode'),'first');await settle();f.data.snapshot.device_inventory.state='succeeded';await f.run('poll()');await f.elements.get('refreshDevices').onclick();
  const source=f.elements.get('source');source.value='整个显示器';source.listeners.change();source.value='游戏窗口';source.listeners.change();
  Object.assign(f.data.snapshot,detectedDefaults('inventory-4'));await f.run('poll()');
  assert.equal(f.run('store.draft.source'),'游戏窗口');assert.equal(f.run('store.draft.mic'),'');
  assert.equal(f.elements.get('refreshDevices').disabled,false);
});

test('read failure preserves choices, has concrete retry feedback, and consumes newer inventory ids',async()=>{
  const f=await fixture(setupSnapshot());f.elements.get('settingsButton').onclick();await settle();
  f.data.snapshot.device_inventory={id:'newer-inventory',state:'failed',error:'Windows 设备枚举失败'};await f.run('poll()');
  assert.match(f.elements.get('deviceFeedback').textContent,/Windows 设备枚举失败/);
  assert.match(f.elements.get('target').innerHTML,/读取失败，未确认/);assert.doesNotMatch(f.elements.get('target').innerHTML,/当前未找到/);
  assert.equal(f.elements.get('refreshDevices').disabled,false);
  f.data.inventoryResult={ok:false,error:'读取请求被拒绝'};await f.elements.get('refreshDevices').onclick();
  assert.match(f.elements.get('deviceFeedback').textContent,/读取请求被拒绝/);assert.equal(f.elements.get('wizardCancel').disabled,false);
  assert.equal(f.run('store.draft.source'),'游戏窗口');assert.equal(f.run('store.draft.mic'),'microphone');
  Object.assign(f.data.snapshot,detectedDefaults('newer-automatic-probe'));await f.run('poll()');
  assert.doesNotMatch(f.elements.get('deviceFeedback').textContent,/读取请求被拒绝/);
  assert.match(f.elements.get('target').innerHTML,/当前未找到/);
});

test('cancelled inventory RPC cannot affect a reopened draft or leave its read state locked',async()=>{
  const f=await fixture(setupSnapshot());let resolveOld;
  f.data.inventoryHandler=()=>new Promise(resolve=>resolveOld=resolve);
  await click(f.elements.get('gameTabs'),'data-game-add');await settle();assert.equal(f.run('sheetMode'),'new');assert.equal(f.elements.get('wizardCancel').disabled,false);
  f.elements.get('wizardCancel').onclick();f.data.inventoryHandler=null;
  f.elements.get('settingsButton').onclick();await settle();assert.equal(f.run('sheetMode'),'settings');
  resolveOld({ok:true,data:{inventory_id:'late'}});await settle();
  Object.assign(f.data.snapshot,detectedDefaults('newer'));await f.run('poll()');
  assert.equal(f.run('store.draft.window'),'game-window');assert.equal(f.run('store.draft.source'),'游戏窗口');
  assert.equal(f.elements.get('refreshDevices').disabled,false);
});

test('engine recovery is separately labelled and inventory success cannot enable Start or alter an edit',async()=>{
  const s=setupSnapshot();s.readiness={ready:false,checking:false,errors:[{code:'OBS_UNAVAILABLE',message:'无法连接录制引擎。'}]};
  const f=await fixture(s);f.elements.get('settingsButton').onclick();await settle();
  Object.assign(f.data.snapshot,detectedDefaults());await f.run('poll()');
  assert.equal(f.elements.get('reconnectEngine').classList.contains('hidden'),false);
  assert.equal(f.elements.get('recordButton').disabled,true);
  const original=f.run('JSON.stringify(store.draft)');await f.elements.get('reconnectEngine').onclick();
  assert.equal(f.calls.filter(c=>c.name==='refresh_devices').length,1);assert.equal(f.run('JSON.stringify(store.draft)'),original);
  f.data.snapshot.readiness.checking=true;await f.run('poll()');
  assert.equal(f.elements.get('reconnectEngine').classList.contains('hidden'),true);
  assert.equal(f.elements.get('engineFeedback').classList.contains('hidden'),true);
});

test('uncertain recording and failed or stale readiness retain guarded full-check recovery paths',async()=>{
  for(const [code,label] of [['RECORDING_UNCONFIRMED','重新检查录制状态'],['READINESS_FAILED','重新检查录制条件'],['READINESS_STALE','重新检查录制条件']]){
    const s=setupSnapshot();s.readiness={ready:false,checking:false,errors:[{code,message:'Synthetic recovery blocker'}]};
    const f=await fixture(s);f.data.inventoryResult={ok:false,error:'上次录制状态尚未确认。'};
    f.elements.get('settingsButton').onclick();await settle();
    assert.equal(f.elements.get('reconnectEngine').classList.contains('hidden'),false);assert.equal(f.elements.get('reconnectEngine').textContent,label);
    assert.match(f.elements.get('target').innerHTML,/读取失败，未确认/);assert.doesNotMatch(f.elements.get('target').innerHTML,/当前未找到/);
    assert.equal(f.elements.get('recordButton').disabled,true);
    const original=f.run('JSON.stringify(store.draft)');await f.elements.get('reconnectEngine').onclick();
    assert.equal(f.calls.filter(c=>c.name==='refresh_devices').length,1);assert.equal(f.run('JSON.stringify(store.draft)'),original);
    assert.equal(f.elements.get('recordButton').disabled,true);
    for(const activity of [{kind:'devices',busy:true},{kind:'recording',busy:false}]){
      f.data.snapshot.activity=activity;await f.run('poll()');
      assert.equal(f.elements.get('reconnectEngine').disabled,true);assert.equal(f.elements.get('reconnectEngine').classList.contains('hidden'),true);
      await f.elements.get('reconnectEngine').onclick();assert.equal(f.calls.filter(c=>c.name==='refresh_devices').length,1);
      for(const id of ['source','target','mic'])assert.equal(f.elements.get(id).disabled,activity.kind==='recording',`${id} locked only while recording`);
    }
    f.data.snapshot.activity={kind:'idle',busy:false};f.data.snapshot.readiness.checking=true;await f.run('poll()');
    assert.equal(f.elements.get('reconnectEngine').classList.contains('hidden'),true);assert.equal(f.elements.get('recordButton').disabled,true);
  }
});

test('update eligibility fails closed and does not use recording readiness',()=>{
  assert.equal(updateView(undefined).canCheck,false);
  for(const raw of [null,{}, {state:'ready'}, {state:'ready',can_install:'true'}, {state:'future',can_install:true}])assert.equal(updateView(raw).canInstall,false);
  const ready={state:'ready',can_install:true,review_count:2};
  assert.equal(updateView(ready).canInstall,true);
  assert.equal(updateView({...ready,install_blockers:['场次正在整理']}).canInstall,false);
  assert.equal(updateView(ready,false).canInstall,false);
  assert.equal(updateView(ready,true,true).canInstall,false);
  assert.equal(updateView({...ready,review_count:-1,total_bytes:-10,downloaded_bytes:Infinity}).review_count,0);
  assert.equal(updateView({...ready,downloaded_bytes:Infinity}).downloaded_bytes,0);
});

// The update panel lives in 设置 → 通用; a badge on the gear and the 通用 tab replaces the old version button.
test('update panel is safe on older snapshots and never checks on opening',async()=>{
  const f=await fixture();f.elements.get('settingsButton').onclick();await settle();
  const before=f.calls.length;openGeneral(f);await settle();
  assert.equal(f.calls.length,before,'opening the update panel makes no bridge call');
  assert.equal(f.elements.get('panelGeneral').classList.contains('hidden'),false);
  assert.equal(f.elements.get('updateCheck').disabled,true);
  assert.equal(f.elements.get('updateCurrent').textContent,'尚未获取');
  assert.equal(f.elements.get('recordButton').disabled,false);
  assert.equal(f.elements.get('settingsButton').classList.contains('badge'),false);
  f.data.snapshot.updates={current_version:'unknown',state:'idle'};await f.run('poll()');
  assert.equal(f.elements.get('updateCurrent').textContent,'版本未知');
  assert.equal(f.elements.get('settingsButton').title,'设置');assert.equal(f.elements.get('settingsButton').classList.contains('badge'),false);
  assert.equal(f.calls.some(c=>c.name==='update_action'),false);
});

test('update channel is local until explicit check and never enters a preset',async()=>{
  const f=await fixture(snapshot({updates:{current_version:'0.6.0-preview.3',state:'idle'}}));
  f.elements.get('settingsButton').onclick();openGeneral(f);assert.equal(f.elements.get('updateChannel').value,'stable');
  f.elements.get('updateChannel').value='preview';f.elements.get('updateChannel').onchange();
  await f.run('poll()');assert.equal(f.elements.get('updateChannel').value,'preview');
  assert.equal(f.elements.get('sheetMessage').textContent,'');assert.equal(f.run('store.dirty'),false);
  assert.equal(f.calls.some(c=>c.name==='update_action'),false);
  await f.elements.get('updateCheck').onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(f.calls.find(c=>c.name==='update_action').args)),[{action:'check',include_prerelease:true}]);
  assert.equal(f.run('store.generalPayload().include_prerelease'),undefined);assert.equal(f.run('store.gamePayload().include_prerelease'),undefined);
  f.run("store.openDraft('edit')");assert.equal(f.run('store.presetPayload().include_prerelease'),undefined);
});

test('startup discovery advertises updates without opening a dialog or blocking recording',async()=>{
  const f=await fixture(snapshot({updates:{current_version:'0.7.0',latest_version:'0.7.1',state:'available'}}));
  assert.equal(f.elements.get('settingsButton').classList.contains('badge'),true);
  assert.equal(f.elements.get('tabGeneral').classList.contains('badge'),true);
  assert.equal(f.elements.get('updateGroup').classList.contains('badge-text'),true);
  assert.match(f.elements.get('settingsButton').title,/v0\.7\.1/);
  assert.equal(sheetIsOpen(f),false);
  assert.equal(f.elements.get('recordButton').disabled,false);
  assert.equal(f.calls.some(c=>c.name==='update_action'),false);
  f.data.snapshot.updates={current_version:'0.7.0',state:'error',error:'网络不可用'};await f.run('poll()');
  assert.equal(f.elements.get('settingsButton').classList.contains('badge'),false);assert.equal(f.elements.get('settingsButton').title,'设置');
  assert.equal(f.elements.get('tabGeneral').classList.contains('badge'),false);
  assert.equal(f.elements.get('recordButton').disabled,false);
  assert.equal(sheetIsOpen(f),false);
  f.elements.get('settingsButton').onclick();openGeneral(f);
  assert.equal(f.elements.get('updateCheck').disabled,false);
  await f.elements.get('updateCheck').onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(f.calls.find(c=>c.name==='update_action').args)),[{action:'check',include_prerelease:false}]);
});

test('update progress and channel changes cannot enable installation or disable recording',async()=>{
  const f=await fixture(snapshot({updates:{state:'downloading',latest_version:'0.7.0',downloaded_bytes:25,total_bytes:100}}));
  assert.equal(f.elements.get('updateProgress').value,25);
  assert.equal(f.elements.get('recordButton').disabled,false);assert.equal(f.elements.get('updateInstall').disabled,true);
  f.data.snapshot.updates={state:'ready',latest_version:'0.7.0',can_install:true,review_count:3,install_blockers:['等待整理完成']};await f.run('poll()');
  assert.equal(f.elements.get('updateInstall').disabled,true);assert.ok(f.elements.get('updateBlockers').innerHTML.includes('等待整理完成'));
  assert.equal(f.elements.get('updateCloseSummary').textContent,'将关闭记录器和 3 个回看窗口。');
  f.data.snapshot.updates.install_blockers=[];await f.run('poll()');assert.equal(f.elements.get('updateInstall').disabled,false);
  f.elements.get('updateChannel').value='preview';f.elements.get('updateChannel').onchange();assert.equal(f.elements.get('updateInstall').disabled,true);
  await f.elements.get('updateInstall').onclick();assert.equal(f.calls.some(c=>c.name==='update_action'),false);
});

test('accepted install returns to retryable state on asynchronous backend failure',async()=>{
  const f=await fixture(snapshot({closing:false,updates:{state:'ready',current_version:'0.6.0',latest_version:'0.7.0',can_install:true}}));
  f.data.snapshot.closing=true;await f.elements.get('updateInstall').onclick();
  assert.equal(f.run('updateInstallAccepted'),true);assert.equal(f.elements.get('updateInstall').disabled,true);
  f.data.snapshot.closing=false;f.data.snapshot.updates.error='回看窗口未能关闭，请重试。';await f.run('poll()');
  assert.equal(f.run('updateInstallAccepted'),false);assert.equal(f.elements.get('updateInstall').disabled,false);
  assert.equal(f.elements.get('updateError').textContent,'回看窗口未能关闭，请重试。');
});

test('unconfirmed cancellation remains actionable after install acceptance and does not promise safe exit',async()=>{
  const f=await fixture(snapshot({closing:true,updates:{state:'ready',can_install:true,cancel_pending:true,error:'取消未确认'}}));
  f.run('updateInstallAccepted=true;renderUpdates()');
  assert.equal(f.elements.get('updateCancel').textContent,'重试取消');assert.equal(f.elements.get('updateCancel').disabled,false);
  assert.equal(f.elements.get('updateInstall').classList.contains('hidden'),true);
  assert.equal(f.elements.get('updateStatus').textContent,'取消尚未确认');
  assert.ok(!f.elements.get('homeStatus').textContent.includes('安全关闭'));
  assert.ok(!f.elements.get('jobDetail').textContent.includes('自动关闭'));
  await f.elements.get('updateCancel').onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(f.calls.filter(c=>c.name==='update_action').at(-1).args)),[{action:'cancel'}]);
  assert.equal(f.elements.get('updateCancel').disabled,false);
  f.data.snapshot.updates.cancel_pending=false;f.data.snapshot.closing=false;f.data.snapshot.updates.error='已取消这次安装，当前版本保留。';await f.run('poll()');
  assert.equal(f.run('updateInstallAccepted'),false);assert.equal(f.elements.get('updateCancel').classList.contains('hidden'),true);
});

test('last update failure and recovery details remain separate from idle discovery state',async()=>{
  for(const raw of [null,[],{},false])assert.equal(lastInstallView(raw),null);
  assert.equal(lastInstallView({state:'failed',time:1e30}).time,0);
  const f=await fixture(snapshot({updates:{state:'idle',last_install:{state:'recovery_required',version:'0.7.0',time:1790130434,message:'保留备份，等待恢复。',backup_path:'D:\\synthetic-only\\transaction\\backup',recovery_path:'synthetic recovery file'}}}));
  assert.equal(f.elements.get('updateLastTitle').textContent,'上次更新需要恢复');
  assert.equal(f.elements.get('updateLastResult').classList.contains('hidden'),false);
  assert.equal(f.elements.get('updateBackupPath').value,'D:\\synthetic-only\\transaction\\backup');
  assert.equal(f.elements.get('updateRecoveryValue').value,'synthetic recovery file');
  await f.run('poll()');assert.equal(f.elements.get('updateLastTitle').textContent,'上次更新需要恢复');
  assert.equal(f.calls.some(c=>c.name==='update_action'),false);
});

test('a running readiness check is followed closely for a bounded time, then the 1 s rhythm resumes',async()=>{
  // 触发路径：用户 → 切回主窗口 → 后台就绪检查约 0.1 s 完成 → 界面 250 ms 后再取一次状态并启用“开始录制”，最多补 12 次 → 不修要等下一次 1 s 轮询才能开始。
  const f=await fixture(snapshot({readiness:{ready:false,checking:true,errors:[]}}));
  const followUps=()=>f.timers.filter(timer=>timer.ms===250);
  assert.equal(followUps().length,1);
  await f.run('poll()');await f.run('poll()');
  assert.equal(followUps().length,1);
  const before=f.calls.filter(call=>call.name==='get_state').length;
  for(let ran=0;ran<followUps().length;ran++){followUps()[ran].fn();await settle();}
  assert.equal(followUps().length,12);
  assert.equal(f.calls.filter(call=>call.name==='get_state').length,before+12);
  f.data.snapshot.readiness={ready:true,checking:false,errors:[]};await f.run('poll()');
  f.data.snapshot.readiness={ready:false,checking:true,errors:[]};await f.run('poll()');
  assert.equal(followUps().length,13);
});
