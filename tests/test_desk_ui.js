'use strict';
// Synthetic desk-window (资料台 · 场次) tests: the session list, row status, detail actions and their locks.
// No browser, capture, or network. ui/desk.js runs against a fake DOM built from ui/desk.html and a fake
// desk_runtime.DeskAPI bridge (desk_state, session_detail and the row actions).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function fakeDOM() {
  const html=fs.readFileSync(path.join(__dirname,'../ui/desk.html'),'utf8');
  const elements=new Map();let document;
  class Element {
    constructor(id='') {this.id=id;this.value='';this.textContent='';this.innerHTML='';this.disabled=false;this.open=false;this.style={};this.dataset={};this.attributes={};this.listeners={};this.children=[];const classes=new Set();this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,on)=>{if(on===undefined)on=!classes.has(x);on?classes.add(x):classes.delete(x);return on;},contains:x=>classes.has(x)};}
    addEventListener(name,fn){this.listeners[name]=fn;}
    setAttribute(name,value){this.attributes[name]=String(value);}
    getAttribute(name){return this.attributes[name];}
    insertAdjacentHTML(_position,markup){this.innerHTML+=markup;}
    querySelectorAll(){return [];}
    querySelector(){return null;}
    focus(){document.activeElement=this;}
    select(){}
    showModal(){this.open=true;}
    close(){this.open=false;}
    replaceChildren(){this.children=[];}
    append(child){this.children.push(child);}
    remove(){}
  }
  for(const match of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const el=new Element(match[3]);el.tagName=match[1].toUpperCase();
    const cls=/\bclass="([^"]*)"/.exec(match[2]);if(cls)cls[1].split(/\s+/).filter(Boolean).forEach(name=>el.classList.add(name));
    elements.set(el.id,el);
  }
  // Inputs created by dialogs (renameInput, recoverInput) exist only inside some element's innerHTML.
  const byId=id=>{if(!elements.has(id)&&[...elements.values()].some(el=>el.innerHTML.includes(`id="${id}"`)))elements.set(id,new Element(id));return elements.get(id);};
  document={activeElement:null,title:'',hidden:false,documentElement:{dataset:{}},body:{append(){}},getElementById:byId,
    querySelectorAll:()=>[],createElement:()=>new Element(),addEventListener(){}};
  return {document,elements};
}
const decode=text=>String(text).replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&amp;/g,'&');
function findTag(el,attr,value){
  for(const match of el.innerHTML.matchAll(/<(\w+)\b([^>]*)>/g)){
    const attrs=match[2],hit=new RegExp(`(?:^|\\s)${attr}(?:="([^"]*)")?(?=[\\s>/]|$)`).exec(attrs);
    if(!hit||value!==undefined&&decode(hit[1]??'')!==value)continue;
    const dataset={};for(const data of attrs.matchAll(/(?:^|\s)data-([\w-]+)(?:="([^"]*)")?/g))dataset[data[1].replace(/-(\w)/g,(_,c)=>c.toUpperCase())]=decode(data[2]??'');
    return {dataset,attrs,disabled:/(?:^|\s)disabled(?=[\s>/]|$)/.test(attrs),closest:()=>null};
  }
  return null;
}
function click(el,attr,value){
  const node=findTag(el,attr,value);assert.ok(node,`${attr} ${value??''} is rendered`);
  return el.listeners.click({target:{closest:selector=>selector===`[${attr}]`?node:null},preventDefault(){}});
}
const plain=value=>JSON.parse(JSON.stringify(value));
async function settle(){for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));}
const emptyDetail=id=>({id,state:'none',label:'',kinds:{},quotes:{},events:[],insights:[]});

async function fixture(state={}) {
  const {document,elements}=fakeDOM();const calls=[];let poll=null;
  const data={state:{tab:'sessions',game:'Synthetic game',sessions:[],background_jobs:[],busy:false,recording:false,insight:null,...state},details:{}};
  const api=new Proxy({}, {get(_target,name){return async(...args)=>{calls.push({name,args});
    if(name==='desk_state')return {ok:true,data:plain(data.state)};
    if(name==='session_detail')return {ok:true,data:plain(data.details[args[0]]||emptyDetail(args[0]))};
    return {ok:true,data:{}};};}});
  const context=vm.createContext({document,window:{pywebview:{api},addEventListener(){}},localStorage:{getItem(){return null;},setItem(){}},
    matchMedia:()=>({matches:false,addEventListener(){}}),getComputedStyle:()=>({getPropertyValue:()=>''}),setTimeout(){return 1;},clearTimeout(){},
    setInterval(fn){poll=fn;return 1;},navigator:{clipboard:{writeText:async text=>{data.clipboard=text;}}},console});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/desk.js'),'utf8'),context);
  await settle();
  const el=id=>elements.get(id);
  return {elements,el,calls,data,async refresh(){poll();await settle();},
    async select(id){click(el('sessionScroll'),'data-session',id);await settle();},
    act:name=>findTag(el('sessionDetail'),'data-act',name)};
}
const LOCKED=['process','export','recover'],FREE=['folder','raw','rename'];

test('playable processing session allows review and naming but keeps reprocessing blocked',async()=>{
  const sessions=[{id:'pending-text',game:'Game',session_name:'Door <attempt>',state:'转写中',can_review:true},{id:'no-video',game:'Game',state:'转写中',can_review:false}];
  const f=await fixture({sessions,background_jobs:sessions.map(s=>({session_id:s.id,state:'running'}))});
  const list=f.el('sessionScroll').innerHTML;
  assert.ok(list.includes('Door &lt;attempt&gt;'));assert.ok(!list.includes('Door <attempt>'));
  assert.ok(findTag(f.el('sessionScroll'),'data-session','no-video'));
  assert.ok(f.el('sessionDetail').innerHTML.includes('Door &lt;attempt&gt;'),'the first session opens on load');
  assert.equal(f.act('review').disabled,false);
  for(const name of LOCKED)assert.equal(f.act(name).disabled,true,`${name} is blocked while transcribing`);
  for(const name of FREE)assert.equal(f.act(name).disabled,false,`${name} stays available while transcribing`);
  await click(f.el('sessionDetail'),'data-act','review');
  assert.deepEqual(plain(f.calls.filter(c=>c.name==='review_session').map(c=>c.args)),[['pending-text']]);
  // Since the redesign the name is edited in place in the detail title; Enter saves.
  click(f.el('sessionDetail'),'data-act','rename');
  assert.equal(f.el('renameInput').value,'Door <attempt>');f.el('renameInput').value=' Door 2 ';
  f.el('renameInput').onkeydown({key:'Enter',preventDefault(){}});await settle();
  assert.deepEqual(plain(f.calls.filter(c=>c.name==='rename_session').map(c=>c.args)),[['pending-text','Door 2']]);
  await f.select('no-video');
  assert.equal(f.act('review').disabled,true);assert.equal(f.act('process').disabled,true);
  f.el('searchInput').value='door';f.el('searchInput').oninput();
  assert.ok(findTag(f.el('sessionScroll'),'data-session','pending-text'));assert.equal(findTag(f.el('sessionScroll'),'data-session','no-video'),null);
  assert.equal(f.calls.some(c=>['process_session','package_session','recover_cloud_task'].includes(c.name)),false);
});

test('external preprocessing badges never change recording state or disable review',async()=>{
  const sessions=['none','processing','complete','failed','stale'].map((state,i)=>({id:'agent-'+i,
    game:'原始名称',state:'可回看',can_review:true,preprocessing:{state,...(state==='none'?{}:{label:'外部 <整理>',reason:'保留原始素材'})}}));
  const f=await fixture({sessions});
  for(const s of sessions)f.data.details[s.id]={...emptyDetail(s.id),state:s.preprocessing.state,label:s.preprocessing.label||''};
  const titles=[...f.el('sessionScroll').innerHTML.matchAll(/<span class="nm[^"]*" title="[^"]*">(.*?)<\/span>/g)].map(match=>match[1]);
  assert.equal(titles.length,5);assert.equal(new Set(titles).size,1,'the external label never replaces the session title');
  assert.doesNotMatch(f.el('sessionScroll').innerHTML,/外部|<整理>/);
  for(const s of sessions){
    await f.select(s.id);const detail=f.el('sessionDetail').innerHTML;
    assert.equal(f.act('review').disabled,false,`${s.id} stays reviewable`);
    for(const name of [...LOCKED,...FREE])assert.equal(f.act(name).disabled,false,`${name} is not locked by an external label`);
    assert.doesNotMatch(detail,/<整理>/);
    if(!['none','complete'].includes(s.preprocessing.state))assert.match(detail,/外部 &lt;整理&gt;/);
  }
  assert.equal(f.calls.filter(c=>c.name==='session_detail').length>=5,true);
});

test('an unfinished external preprocessing run reads 整理未完成, never 转写失败',async()=>{
  const sessions=['failed','stale','complete'].map(state=>({id:'pre-'+state,game:'Game',state:'可回看',can_review:true,preprocessing:{state}}));
  const f=await fixture({sessions});
  const rows=f.el('sessionScroll').innerHTML,row=id=>rows.slice(rows.indexOf(`data-session="${id}"`)).split('data-session=')[1];
  for(const id of ['pre-failed','pre-stale']){assert.match(row(id),/<span class="c-st[^"]*">整理未完成<\/span>/);assert.doesNotMatch(row(id),/转写失败|待整理/);}
  assert.doesNotMatch(row('pre-complete'),/<span class="c-st[^"]*">[^<]+<\/span>/,'a finished session carries no status text');
});

test('session dates use local minute precision and never leak raw or invalid values',async()=>{
  const timestamp='2026-09-20T17:26:53.973896+08:00',local=new Date(timestamp),pad=n=>String(n).padStart(2,'0');
  const f=await fixture({sessions:[{id:'dated',game:'Dated session',created:timestamp,duration:3725,state:'待整理'},{id:'undated',game:'Undated',created:'未记录时间',duration:10,state:'待整理'}]});
  const list=f.el('sessionScroll').innerHTML,detail=f.el('sessionDetail').innerHTML,week='日一二三四五六'[local.getDay()],hm=`${pad(local.getHours())}:${pad(local.getMinutes())}`;
  assert.ok(list.includes(`<span class="day">${pad(local.getMonth()+1)}/${pad(local.getDate())}</span>`));assert.ok(list.includes(`<span class="c-start">${hm}</span><span class="dur">1:02:05</span>`));
  const end=new Date(local.getTime()+3725000);
  assert.ok(detail.includes(`${local.getMonth()+1}月${local.getDate()}日 周${week} · ${hm}–${pad(end.getHours())}:${pad(end.getMinutes())} · 1:02:05`));
  for(const html of [list,detail]){assert.ok(!html.includes(timestamp));assert.ok(!html.includes(`${hm}:${pad(local.getSeconds())}`));}
  await f.select('undated');
  assert.doesNotMatch(f.el('sessionDetail').innerHTML,/NaN|Invalid Date|undefined/);assert.match(f.el('sessionDetail').innerHTML,/0:00:10/);
  assert.doesNotMatch(f.el('sessionScroll').innerHTML,/NaN|Invalid Date|undefined/,'an undated session must not produce a garbage month header');
});

test('background transcription locks only its own session; folder, raw, rename and other sessions stay available',async()=>{
  const jobs=[{id:'job-a',session_id:'a',game:'Game A',state:'running',detail:'Uploading <microphone>'},{id:'job-b',session_id:'b',game:'Game B',state:'queued',detail:''}];
  const sessions=[{id:'a',game:'Game A',state:'转写中',duration:60},{id:'b',game:'Game B',state:'待整理',duration:30},{id:'other',game:'Game C',state:'待整理',duration:20,can_review:false}];
  const f=await fixture({background_jobs:jobs,sessions});
  assert.match(f.el('sessionDetail').innerHTML,/Uploading &lt;microphone&gt;/);
  for(const name of LOCKED)assert.equal(f.act(name).disabled,true);
  for(const name of FREE)assert.equal(f.act(name).disabled,false);
  await click(f.el('sessionDetail'),'data-act','folder');await click(f.el('sessionDetail'),'data-act','raw');
  assert.deepEqual(plain(f.calls.filter(c=>['open_folder','open_raw'].includes(c.name)).map(c=>[c.name,...c.args])),[['open_folder','a'],['open_raw','a']]);
  await f.select('b');
  assert.equal(f.act('process').disabled,true,'a queued session cannot be submitted twice');assert.match(f.el('sessionDetail').innerHTML,/等待转写|正在转写/,'the detail says whether the job is queued or running');
  await f.select('other');
  for(const name of [...LOCKED,...FREE])assert.equal(f.act(name).disabled,false);
  click(f.el('sessionDetail'),'data-act','process');assert.equal(f.el('deskDialog').open,true);
  assert.match(f.el('deskDialogBody').innerHTML,/上传这一场的麦克风录音/);
  assert.equal(f.calls.some(c=>c.name==='process_session'),false,'nothing is submitted before confirmation');
  await f.el('deskDialogFoot').children.find(button=>button.textContent==='开始').onclick();
  assert.deepEqual(plain(f.calls.filter(c=>c.name==='process_session').map(c=>c.args)),[['other']]);
  f.data.state.busy=true;await f.refresh();
  for(const name of LOCKED)assert.equal(f.act(name).disabled,true,`${name} is blocked while the recorder is busy`);
  for(const name of FREE)assert.equal(f.act(name).disabled,false);
});

test('background progress and failures stay on their session',async()=>{
  const f=await fixture({recording:false,background_jobs:[{id:'job-a',session_id:'a',state:'running',detail:'Uploading A'}],
    sessions:[{id:'a',game:'A',state:'转写中',duration:60},{id:'b',game:'B',state:'待整理',duration:30}]});
  f.data.state.background_jobs[0].detail='<Waiting for cloud>';await f.refresh();
  assert.match(f.el('sessionDetail').innerHTML,/&lt;Waiting for cloud&gt;/);
  await f.select('b');assert.doesNotMatch(f.el('sessionDetail').innerHTML,/Waiting for cloud/);
  await f.select('a');
  f.data.state.background_jobs=[];f.data.state.sessions[0]={id:'a',game:'A',state:'失败',error:'Cloud <failure>',duration:60};await f.refresh();
  assert.match(f.el('sessionDetail').innerHTML,/Cloud &lt;failure&gt;/);assert.doesNotMatch(f.el('sessionDetail').innerHTML,/Waiting for cloud/);
  assert.equal(f.act('process').disabled,false,'a failed session can be retried');
  const rows=f.el('sessionScroll').innerHTML;
  assert.match(rows,/data-session="a"[\s\S]*?<span class="c-st[^"]*">转写失败<\/span>/);
  assert.doesNotMatch(rows.slice(rows.indexOf('data-session="b"')),/失败/);
});
