'use strict';
// Synthetic front-end state and bridge tests. No browser, capture, or network.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {State} = require('../ui/state.js');

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
  assert.equal(state.draft.transcription_provider,'later');assert.equal(state.draft.hotwords,'');
  assert.equal(state.draft.obsidian_exe,'');assert.equal(state.draft.window,'');
  state.updateDraft('game','Unsaved');state.cancelDraft();assert.equal(JSON.stringify(state.saved),saved);
  state.openDraft('edit');assert.equal(state.editingId,'one');assert.deepEqual(state.draft,Object.fromEntries(Object.keys(state.draft).map(key=>[key,state.saved[key]])));
  state.updateDraft('hotwords','Unsaved words');state.cancelDraft();state.openDraft('edit');
  assert.equal(state.draft.hotwords,'Saved vocabulary');
});

test('polling and external preset changes do not overwrite an open draft',()=>{
  const state=new State();state.accept(snapshot());state.openDraft('edit');state.updateDraft('game','My draft');state.updateDraft('hotwords','Typing');
  state.accept(snapshot({config:{...snapshot().config,game:'Externally changed',hotwords:'Other'}}));
  assert.equal(state.saved.game,'Externally changed');assert.equal(state.draft.game,'My draft');
  assert.equal(state.draft.hotwords,'Typing');assert.deepEqual(state.startPayload(),{});
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
  const steps=[1,2,3].map(n=>{const el=new Element();el.dataset.step=String(n);return el;});
  document={activeElement:null,documentElement:{dataset:{}},getElementById:id=>elements.get(id),
    querySelector:selector=>selector.startsWith('#')?elements.get(selector.slice(1)):null,
    querySelectorAll:selector=>selector==='[data-draft]'?[...elements.values()].filter(el=>el.dataset.draft):selector==='[data-step]'?steps:[],
    createElement:()=>new Element(),addEventListener(){}};
  elements.get('filter').value='all';
  return {document,elements};
}
async function settle(){for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));}
async function fixture(initial=snapshot()) {
  const {document,elements}=fakeDOM();const calls=[];const data={snapshot:initial};
  const api=new Proxy({}, {get(_target,name){return async(...args)=>{calls.push({name,args});if(name==='get_state')return {ok:true,data:JSON.parse(JSON.stringify(data.snapshot))};if(name==='save_preset'){data.snapshot={...data.snapshot,config:{...args[0],configured:true},active_preset_id:args[1]||'created',presets:[{id:args[1]||'created',name:args[0].name,vault:args[0].vault}],readiness:{ready:false,checking:true,errors:[]}};return {ok:true,data:{id:args[1]||'created'}};}return {ok:true,data:{}};};}});
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
