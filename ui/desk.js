'use strict';
/* 资料台 · 场次库页签。洞察页签由 insight.js 负责；两者共用同一个窗口接口（desk_runtime.DeskAPI）。 */
(function(){
  const $=id=>document.getElementById(id);
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  // The four problem types; a session's 问题数 counts only these.
  const KIND={confusion:'困惑',obstacle:'阻碍',cost:'操作成本',negative:'负面评价'};
  const OTHER=['expectation','suggestion','positive','observation','self_correction'];
  const WEEK='日一二三四五六';
  const STATES=[['all','全部'],['done','已整理'],['todo','待整理'],['running','转写中'],['failed','失败']];
  const SHOWN=3;
  const state={sessions:[],jobs:[],busy:false,game:'',filter:'all',kinds:new Set(),sort:'time',search:'',selected:null,detail:null,signature:'',open:new Set(),editing:false};
  let api=null,toastTimer=null;
  const PLAY='<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 1l9 5-9 5z"/></svg>';
  const GO='<span class="go" aria-hidden="true">→</span>',CHEV='<svg class="chev" viewBox="0 0 10 6" aria-hidden="true"><path d="M0 0h10L5 6z"/></svg>';
  const PENCIL='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10.8 2.6a1.3 1.3 0 0 1 1.8 0l.8.8a1.3 1.3 0 0 1 0 1.8L6 12.6l-2.9.6.6-2.9z"/></svg>';

  // ---- window ----
  function applyFrameColor(){const paper=getComputedStyle(document.documentElement).getPropertyValue('--paper').trim();try{api?.win_set_frame_color?.(paper)?.catch?.(()=>{});}catch(_){}}
  applyFrameColor();
  document.querySelectorAll('[data-win]').forEach(button=>button.onclick=()=>{const name={min:'win_minimize',max:'win_toggle_maximize',close:'win_close'}[button.dataset.win];try{api?.[name]?.()?.catch?.(()=>{});}catch(_){}});
  function toast(message){clearTimeout(toastTimer);$('deskToast').textContent=message;$('deskToast').classList.add('show');toastTimer=setTimeout(()=>$('deskToast').classList.remove('show'),5000);}
  async function call(method,...args){const response=await api[method](...args);if(!response||response.ok!==true)throw new Error(response?.error||'操作未完成，请重试。');return response.data;}

  // Sizes go through CSSOM: the page's content policy forbids inline style attributes.
  function sizes(root){root.querySelectorAll('[data-flex]').forEach(el=>el.style.flex=el.dataset.flex);}
  // ---- tabs ----
  function deskShow(tab){const insight=tab==='insight';$('paneSessions').classList.toggle('hidden',insight);$('paneInsight').classList.toggle('hidden',!insight);
    $('deskTabSessions').classList.toggle('on',!insight);$('deskTabInsight').classList.toggle('on',insight);$('deskTabSessions').setAttribute('aria-selected',String(!insight));$('deskTabInsight').setAttribute('aria-selected',String(insight));}
  window.deskShow=deskShow;
  $('deskTabSessions').onclick=event=>{event.preventDefault();deskShow('sessions');};
  $('deskTabInsight').onclick=event=>{event.preventDefault();deskShow('insight');};

  // ---- session rows ----
  const pad=n=>String(n).padStart(2,'0');
  const problems=s=>Object.keys(KIND).reduce((n,k)=>n+((s.preprocessing?.kinds||{})[k]||0),0);
  const jobFor=s=>state.jobs.find(j=>String(j.session_id)===String(s.id));
  function status(s){
    if(s.error||/失败|错误|failed|error/i.test(String(s.state||'')))return 'failed';
    if(s.preprocessing?.state==='complete')return 'done';
    if(jobFor(s)||/转写中|排队/.test(String(s.state||'')))return 'running';
    return 'todo';
  }
  const preFailed=s=>['failed','invalid','interrupted','stale'].includes(s.preprocessing?.state);
  function statusLabel(s){
    const st=status(s);
    if(st==='failed')return '转写失败';
    if(st==='running')return jobFor(s)?.state==='queued'?'等待转写':'转写中';
    if(st==='todo')return preFailed(s)?'整理未完成':/待转写/.test(String(s.state||''))?'待转写':'待整理';
    return '';
  }
  function title(s){const named=s.session_name||(s.title&&s.title!==s.game?s.title:'');if(named)return {named:true,text:named};const titles=(s.preprocessing?.event_titles||[]).filter(Boolean);const d=new Date(s.created);return {named:false,text:titles.length?titles.join('、'):(Number.isNaN(d.getTime())?'未命名的记录':pad(d.getHours())+':'+pad(d.getMinutes())+' 开始的记录')};}
  function clock(value){const n=Math.max(0,Math.floor(Number(value)||0));return Math.floor(n/3600)+':'+pad(Math.floor(n/60)%60)+':'+pad(n%60);}
  function short(value){const n=Math.max(0,Math.floor(Number(value)||0));return n>=3600?clock(n):pad(Math.floor(n/60))+':'+pad(n%60);}
  const bar=(kinds,big)=>{const present=Object.keys(KIND).filter(k=>kinds[k]);return present.length?`<div class="fp${big?' big':''}">${present.map(k=>`<i class="k-${k}" data-flex="${kinds[k]}"></i>`).join('')}</div>`:'';};
  function visible(){
    const q=state.search.trim().toLowerCase();
    let rows=state.sessions.filter(s=>(state.filter==='all'||status(s)===state.filter)
      &&(!state.kinds.size||[...state.kinds].some(k=>(s.preprocessing?.kinds||{})[k]))
      &&(!q||(title(s).text+' '+(s.activity_details||'')).toLowerCase().includes(q)));
    if(state.sort==='problems')rows=[...rows].sort((a,b)=>problems(b)-problems(a));
    return rows;
  }
  function renderFilters(){
    const counts={all:state.sessions.length,done:0,todo:0,running:0,failed:0};state.sessions.forEach(s=>counts[status(s)]++);
    $('stateChips').innerHTML=STATES.map(([key,label])=>`<button type="button" class="${state.filter===key?'on':''}" data-filter="${key}" aria-pressed="${state.filter===key}">${label} <b>${counts[key]}</b></button>`).join('');
    $('kindMenu').innerHTML=Object.entries(KIND).map(([key,label])=>`<label class="k-${key}"><input type="checkbox" data-kind="${key}"${state.kinds.has(key)?' checked':''}><i class="dot"></i>${label}</label>`).join('');
    $('kindToggle').textContent=state.kinds.size?`问题类型 · ${state.kinds.size}`:'问题类型';$('kindToggle').classList.toggle('on',state.kinds.size>0);
  }
  function item(s){
    const d=new Date(s.created),valid=!Number.isNaN(d.getTime()),t=title(s),st=status(s),label=statusLabel(s);
    const counts=st==='done'?`<span class="pc"><b>${problems(s)}</b>${bar(s.preprocessing?.kinds||{})}</span>`:'<span></span>';
    return `<div class="srow cols${state.selected===s.id?' sel':''}" data-session="${escape(s.id)}" role="button" tabindex="0">`
      +`<span class="day">${valid?pad(d.getMonth()+1)+'/'+pad(d.getDate()):''}</span>`
      +`<span class="nm${t.named?'':' auto'}" title="${escape(t.text)}">${escape(t.text)}</span>`
      +`<span class="c-start">${valid?pad(d.getHours())+':'+pad(d.getMinutes()):''}</span><span class="dur">${clock(s.duration)}</span>${counts}`
      +`<span class="c-st${st==='running'?' running':''}">${escape(label)}</span></div>`;
  }
  function renderList(){
    const rows=visible();let html='',month='';
    for(const s of rows){
      const d=new Date(s.created),key=state.sort==='time'&&!Number.isNaN(d.getTime())?d.getFullYear()+'-'+d.getMonth():'';
      if(state.sort==='time'&&key&&key!==month){month=key;const count=rows.filter(r=>{const x=new Date(r.created);return x.getFullYear()===d.getFullYear()&&x.getMonth()===d.getMonth();}).length;
        html+=`<div class="month">${d.getFullYear()} 年 ${d.getMonth()+1} 月<small>${count} 场</small></div>`;}
      html+=item(s);
    }
    $('sessionScroll').innerHTML=html||'<p class="empty">没有符合筛选的场次。</p>';sizes($('sessionScroll'));
  }
  function render(){renderFilters();renderList();$('deskGame').textContent=state.game||'资料台';document.title='资料台 · '+(state.game||'');}

  // ---- detail ----
  async function select(id){
    state.selected=id;state.open.clear();state.editing=false;renderList();const s=state.sessions.find(row=>row.id===id);if(!s)return;
    renderDetail(s,null);
    try{const detail=await call('session_detail',id);if(state.selected===id){state.detail=detail;renderDetail(s,detail);}}
    catch(error){if(state.selected===id)$('sessionDetail').insertAdjacentHTML('beforeend',`<p class="d-note">${escape(error.message)}</p>`);}
  }
  const quoteLine=(k,q)=>`<li><button class="ln k-${k}" data-at="${q.at}" title="在回看中打开这一刻"><span class="at">${short(q.at)}</span><span class="tx">${escape(q.text)}</span>${GO}</button></li>`;
  function renderDetail(s,detail){
    const d=new Date(s.created),valid=!Number.isNaN(d.getTime()),t=title(s),job=jobFor(s);
    const locked=state.busy||!!job,done=status(s)==='done';
    const end=valid?new Date(d.getTime()+(Number(s.duration)||0)*1000):null;
    const meta=[valid?`${d.getMonth()+1}月${d.getDate()}日 周${WEEK[d.getDay()]}`:'',valid?`${pad(d.getHours())}:${pad(d.getMinutes())}–${pad(end.getHours())}:${pad(end.getMinutes())}`:'',clock(s.duration),detail?.events?.length?`${detail.events.length} 个体验事件`:''].filter(Boolean).join(' · ');
    const actions=`<div class="d-acts"><button class="btn solid" data-act="review"${s.can_review===false?' disabled':''}>${PLAY}回看</button>${done?'':`<button class="btn sm" data-act="handoff">复制整理指令</button>`}`
      +`<button class="btn sm" data-act="copy" id="copyPath">复制资料库路径</button>`
      +`<span class="pop"><button class="btn sm" data-act="more" aria-haspopup="true" aria-expanded="false">更多</button><span class="pop-menu right hidden" id="moreMenu"><button data-act="folder">打开资料文件夹</button><button data-act="process"${locked?' disabled':''}>重新整理</button><button data-act="export"${locked?' disabled':''}>导出</button><button data-act="raw">原始录像</button><button data-act="recover"${locked?' disabled':''}>恢复云端任务</button></span></span></div>`;
    let body='';
    if(!detail)body='<p class="d-note">正在读取这一场的整理结果…</p>';
    else if(detail.state!=='complete')body=`<p class="d-note">${escape(detail.label||'这一场还没有整理结果。')} 复制整理指令，粘贴给 Codex 或 Claude 整理后，原话和问题分布会出现在这里。</p>`;
    else{
      const kinds=detail.kinds||{},total=Object.keys(KIND).reduce((n,k)=>n+(kinds[k]||0),0),other=OTHER.reduce((n,k)=>n+(kinds[k]||0),0);
      const legend=Object.entries(KIND).filter(([k])=>kinds[k]).map(([k,label])=>`<span class="k-${k}"><b>${kinds[k]}</b> ${label}</span>`).join('');
      const groups=Object.entries(KIND).map(([k,label])=>{const rows=detail.quotes[k]||[];if(!rows.length)return '';const fit=rows.filter(q=>q.text.length>=6&&q.text.length<=40);
        const more=rows.length>SHOWN,open=more&&state.open.has(k),list=open?rows:(fit.length?fit:rows).slice(0,SHOWN);
        const head=`<span class="name">${label}</span><small>${rows.length}</small><span class="sp"></span>${more?CHEV:''}`;
        return `<section class="kq k-${k}">${more?`<button class="gh" data-fold="${k}" aria-expanded="${open}" title="${open?'收起，只看前 3 条':'展开全部 '+rows.length+' 条'}">${head}</button>`:`<div class="gh">${head}</div>`}<ul class="lns">${list.map(q=>quoteLine(k,q)).join('')}</ul></section>`;}).join('');
      const ins=detail.insights.length?`<ul class="lns">${detail.insights.slice(0,8).map(i=>`<li><button class="ln ins" data-issue="${escape(i.id)}" title="在洞察里查看"><span class="tx">${escape(i.title)}</span><span class="ct">${i.count}</span>${GO}</button></li>`).join('')}</ul>`:'<p class="note">这一场的证据还没有挂到洞察下。</p>';
      const evs=detail.events.map(e=>`<li><button class="ln" data-at="${e.start}" title="在回看中打开这段活动"><span class="at">${short(e.start)}</span><span class="tx">${escape(e.title)}</span>${GO}</button></li>`).join('');
      body=`<div class="d-sum">${bar(kinds,true)}<div class="d-sum-row"><span class="total"><b>${total}</b> 个问题</span><span class="kleg">${legend}</span></div>${other?`<p class="note">另有 ${other} 条期待、建议、观察和正面评价</p>`:''}</div>`
        +(groups?`<div class="kqs">${groups}</div>`:'<p class="d-note">这一场没有整理出问题。</p>')
        +`<section class="grp"><div class="gh"><span class="name">关联洞察</span></div>${ins}</section>`
        +(evs?`<section class="grp"><div class="gh"><span class="name">体验事件</span><small>${detail.events.length}</small></div><ul class="lns">${evs}</ul></section>`:'');
    }
    const notes=(job?`<p class="d-note">${escape(job.state==='queued'?'等待转写，前面的场次完成后继续。':job.detail||'正在转写，可以继续录制。')}</p>`:'')+(s.error?`<p class="d-note warn">${escape(s.error)}</p>`:'');
    $('sessionDetail').innerHTML=`<div class="d-head"><p class="d-meta">${escape(meta)}</p><h1 id="detailTitle"><span class="tt">${escape(t.text)}</span><button class="edit" data-act="rename" title="重命名" aria-label="重命名">${PENCIL}</button></h1>${actions}${notes}</div>${body}`;
    sizes($('sessionDetail'));
  }
  function dialog(titleText,html,buttons){
    $('deskDialogBody').innerHTML=`<h2>${escape(titleText)}</h2>${html}`;$('deskDialogFoot').replaceChildren();
    const close=document.createElement('button');close.className='btn';close.textContent='取消';close.onclick=()=>$('deskDialog').close();$('deskDialogFoot').append(close);
    for(const [label,run] of buttons){const button=document.createElement('button');button.className='btn solid';button.textContent=label;button.onclick=async()=>{button.disabled=true;try{if(await run()!==false)$('deskDialog').close();}catch(error){toast(error.message);}finally{button.disabled=false;}};$('deskDialogFoot').append(button);}
    $('deskDialog').showModal();
  }
  async function copyText(text){try{await navigator.clipboard.writeText(text);}catch(_){const area=document.createElement('textarea');area.value=text;document.body.append(area);area.select();document.execCommand('copy');area.remove();}}
  async function copyHandoff(s){await copyText(['请用 Think Aloud 的单场整理方法（think-aloud-judgments），整理这一场记录，并按单场整理交接文件验收。','场次文件夹：'+s.path,'只整理这一场；不改议题表、对应表、界面目录、标签和反馈文件。完成后告诉我实例数、提议的新界面和拿不准的地方。'].join('\n'));toast('整理指令已复制，粘贴给 Codex 或 Claude 即可。');}
  function editTitle(s){
    const h1=$('detailTitle');if(!h1||state.editing)return;state.editing=true;
    h1.innerHTML='<input id="renameInput" maxlength="4096" autocomplete="off" aria-label="场次名称，留空恢复默认名称" placeholder="留空恢复默认名称">';
    const input=$('renameInput');input.value=s.session_name||title(s).text;input.focus();input.select();
    let done=false;
    const finish=async save=>{if(done)return;done=true;const value=input.value.trim();state.editing=false;
      if(save&&value!==(s.session_name||'')&&!(value===title(s).text&&!s.session_name)){try{await call('rename_session',s.id,value);toast('名称已保存');state.signature='';await refresh();return;}catch(error){toast(error.message);}}
      renderDetail(s,state.detail?.id===s.id?state.detail:null);};
    input.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();finish(true);}else if(event.key==='Escape'){event.preventDefault();finish(false);}};
    input.onblur=()=>finish(true);
  }
  async function act(name,s){
    try{
      if(name==='review'){await call('review_session',s.id);return;}
      if(name==='handoff'){await copyHandoff(s);return;}
      if(name==='folder'){await call('open_folder',s.id);return;}
      if(name==='copy'){await copyText(s.path);const button=$('copyPath');if(button){button.textContent='已复制';setTimeout(()=>{if(button.isConnected)button.textContent='复制资料库路径';},2000);}return;}
      if(name==='raw'){await call('open_raw',s.id);return;}
      if(name==='export'){await call('package_session',s.id);toast('已开始导出这一场。');return;}
      if(name==='process'){dialog('重新整理这一场','<p>会按当前的转写设置重新转写这一场，旧的逐字稿和整理结果会保留。使用云端转写时会上传这一场的麦克风录音。</p>',[['开始',async()=>{await call('process_session',s.id);toast('已加入整理队列。');}]]);return;}
      if(name==='rename'){editTitle(s);return;}
      if(name==='recover'){dialog('恢复已有云端任务','<p>填写已有任务编号，继续查询原任务，不重新上传录音。</p><input id="recoverInput" autocomplete="off" spellcheck="false" placeholder="已有 task_id">',[['恢复任务',async()=>{const id=$('recoverInput').value.trim();if(!id){toast('请填写任务编号。');return false;}await call('recover_cloud_task',s.id,id);toast('已开始恢复云端任务。');}]]);}
    }catch(error){toast(error.message);}
  }
  // A small menu under its button: 问题类型 and 更多. A click elsewhere closes both.
  function toggleMenu(button,menu,open){open=open??menu.classList.contains('hidden');menu.classList.toggle('hidden',!open);button.setAttribute('aria-expanded',String(open));}
  document.addEventListener('click',event=>{
    if(!event.target.closest('#kindMenu,#kindToggle'))toggleMenu($('kindToggle'),$('kindMenu'),false);
    const more=$('moreMenu');if(more&&!event.target.closest('#moreMenu,[data-act="more"]'))toggleMenu(document.querySelector('[data-act="more"]'),more,false);
  });

  // ---- events ----
  $('stateChips').onclick=event=>{const chip=event.target.closest('[data-filter]');if(!chip)return;state.filter=chip.dataset.filter;render();};
  $('kindToggle').onclick=()=>toggleMenu($('kindToggle'),$('kindMenu'));
  $('kindMenu').onchange=event=>{const k=event.target.dataset.kind;if(!k)return;event.target.checked?state.kinds.add(k):state.kinds.delete(k);renderFilters();renderList();toggleMenu($('kindToggle'),$('kindMenu'),true);};
  $('sortSelect').onchange=()=>{state.sort=$('sortSelect').value;renderList();};
  $('searchInput').oninput=()=>{state.search=$('searchInput').value;renderList();};
  $('sessionScroll').addEventListener('click',event=>{const row=event.target.closest('[data-session]');if(row)select(row.dataset.session);});
  $('sessionScroll').addEventListener('keydown',event=>{const row=event.target.closest('[data-session]');if(row&&(event.key==='Enter'||event.key===' ')){event.preventDefault();select(row.dataset.session);}});
  $('sessionDetail').addEventListener('click',event=>{
    const s=state.sessions.find(row=>row.id===state.selected);if(!s)return;
    const button=event.target.closest('[data-act]');
    if(button?.dataset.act==='more'){toggleMenu(button,$('moreMenu'));return;}
    if(button){if(button.closest('#moreMenu'))toggleMenu(document.querySelector('[data-act="more"]'),$('moreMenu'),false);act(button.dataset.act,s);return;}
    const at=event.target.closest('[data-at]');if(at){call('open_review',s.id,Number(at.dataset.at)).catch(error=>toast(error.message));return;}
    const fold=event.target.closest('[data-fold]');if(fold){const k=fold.dataset.fold;state.open.has(k)?state.open.delete(k):state.open.add(k);renderDetail(s,state.detail);return;}
    const issue=event.target.closest('[data-issue]');if(issue){deskShow('insight');const label=title(s).text;window.insightBridge?.showSession(s.id,label);setTimeout(()=>window.insightBridge?.goToIssue(issue.dataset.issue),60);}
  });

  // ---- data ----
  async function refresh(){
    const data=await call('desk_state');
    const signature=JSON.stringify([data.sessions,data.background_jobs,data.busy,data.recording,data.game]);
    state.game=data.game;state.busy=data.busy||data.recording;state.jobs=data.background_jobs||[];
    if(signature===state.signature)return data;state.signature=signature;
    state.sessions=data.sessions||[];render();
    // Never redraw under a title being edited.
    const current=state.sessions.find(row=>row.id===state.selected);if(current&&!state.editing)renderDetail(current,state.detail?.id===current.id?state.detail:null);
    return data;
  }
  async function start(){
    if(api)return;api=window.pywebview.api;applyFrameColor();
    try{const data=await refresh();deskShow(data.tab==='insight'?'insight':'sessions');if(state.sessions[0]&&!state.selected)select(state.sessions[0].id);}
    catch(error){$('sessionScroll').innerHTML=`<p class="empty">${escape(error.message)}</p>`;}
    setInterval(()=>{if(!document.hidden)refresh().catch(()=>{});},3000);
  }
  if(window.pywebview?.api)start();else window.addEventListener('pywebviewready',start);
})();
