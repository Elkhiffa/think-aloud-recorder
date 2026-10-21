'use strict';
/* 资料台 · 场次页签。洞察页签由 insight.js 负责；两者共用同一个窗口接口（desk_runtime.DeskAPI）。 */
(function(){
  const $=id=>document.getElementById(id);
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const KIND={confusion:'困惑',obstacle:'阻碍',cost:'操作成本',negative:'负面'};
  const OTHER=['expectation','suggestion','positive','observation','self_correction'];
  const WEEK='日一二三四五六';
  const STATES=[['all','全部'],['todo','待整理'],['done','已整理'],['failed','失败']];
  const state={sessions:[],jobs:[],busy:false,game:'',filter:'all',kinds:new Set(),sort:'time',search:'',selected:null,detail:null,signature:''};
  let api=null,toastTimer=null;

  // ---- appearance and window ----
  function applyFrameColor(){const paper=getComputedStyle(document.documentElement).getPropertyValue('--paper').trim();try{api?.win_set_frame_color?.(paper)?.catch?.(()=>{});}catch(_){}}
  applyFrameColor();
  document.querySelectorAll('[data-win]').forEach(button=>button.onclick=()=>{const name={min:'win_minimize',max:'win_toggle_maximize',close:'win_close'}[button.dataset.win];try{api?.[name]?.()?.catch?.(()=>{});}catch(_){}});
  function toast(message){clearTimeout(toastTimer);$('deskToast').textContent=message;$('deskToast').classList.add('show');toastTimer=setTimeout(()=>$('deskToast').classList.remove('show'),5000);}
  async function call(method,...args){const response=await api[method](...args);if(!response||response.ok!==true)throw new Error(response?.error||'操作未完成，请重试。');return response.data;}

  // Sizes go through CSSOM: the page's content policy forbids inline style attributes.
  function sizes(root){root.querySelectorAll('[data-flex]').forEach(el=>el.style.flex=el.dataset.flex);root.querySelectorAll('[data-width]').forEach(el=>el.style.width=el.dataset.width+'%');}
  // ---- tabs ----
  function deskShow(tab){const insight=tab==='insight';$('paneSessions').classList.toggle('hidden',insight);$('paneInsight').classList.toggle('hidden',!insight);
    $('deskTabSessions').classList.toggle('on',!insight);$('deskTabInsight').classList.toggle('on',insight);$('deskTabSessions').setAttribute('aria-selected',String(!insight));$('deskTabInsight').setAttribute('aria-selected',String(insight));}
  window.deskShow=deskShow;
  $('deskTabSessions').onclick=event=>{event.preventDefault();deskShow('sessions');};
  $('deskTabInsight').onclick=event=>{event.preventDefault();deskShow('insight');};

  // ---- session rows ----
  const problems=s=>Object.keys(KIND).reduce((n,k)=>n+((s.preprocessing?.kinds||{})[k]||0),0);
  function status(s){if(s.error||/失败|错误|failed|error/i.test(String(s.state||'')))return 'failed';return s.preprocessing?.state==='complete'?'done':'todo';}
  const preFailed=s=>['failed','invalid','interrupted','stale'].includes(s.preprocessing?.state);
  function title(s){const named=s.session_name||(s.title&&s.title!==s.game?s.title:'');if(named)return {named:true,text:named};const titles=(s.preprocessing?.event_titles||[]).filter(Boolean);const d=new Date(s.created);return {named:false,text:titles.length?titles.join('、'):(Number.isNaN(d.getTime())?'未命名的记录':pad(d.getHours())+':'+pad(d.getMinutes())+' 开始的记录')};}
  const pad=n=>String(n).padStart(2,'0');
  function clock(value){const n=Math.max(0,Math.floor(Number(value)||0));return Math.floor(n/3600)+':'+pad(Math.floor(n/60)%60)+':'+pad(n%60);}
  function short(value){const n=Math.max(0,Math.floor(Number(value)||0));return n>=3600?clock(n):pad(Math.floor(n/60))+':'+pad(n%60);}
  function visible(){
    const q=state.search.trim().toLowerCase();
    let rows=state.sessions.filter(s=>(state.filter==='all'||status(s)===state.filter)
      &&(!state.kinds.size||[...state.kinds].some(k=>(s.preprocessing?.kinds||{})[k]))
      &&(!q||(title(s).text+' '+(s.activity_details||'')).toLowerCase().includes(q)));
    if(state.sort==='problems')rows=[...rows].sort((a,b)=>problems(b)-problems(a));
    return rows;
  }
  function renderChips(){
    const counts={all:state.sessions.length,todo:0,done:0,failed:0};state.sessions.forEach(s=>counts[status(s)]++);
    $('stateChips').innerHTML=STATES.map(([key,label])=>`<button class="chip${state.filter===key?' on':''}" data-filter="${key}" aria-pressed="${state.filter===key}">${label} <b>${counts[key]}</b></button>`).join('');
    $('kindChips').innerHTML=Object.entries(KIND).map(([key,label])=>`<button class="chip k k-${key}${state.kinds.has(key)?' on':''}" data-kind="${key}" aria-pressed="${state.kinds.has(key)}">${label}</button>`).join('');
  }
  function item(s){
    const d=new Date(s.created),valid=!Number.isNaN(d.getTime()),t=title(s),k=s.preprocessing?.kinds||{};
    const mini=Object.keys(KIND).filter(key=>k[key]).map(key=>`<i class="k-${key}" data-flex="${k[key]}"></i>`).join('');
    const st=status(s)==='failed'?'<span class="st">转写失败</span>':status(s)==='todo'?(preFailed(s)?'<span class="st">整理未完成</span>':'<span class="st">待整理</span>'):'';
    return `<div class="item${state.selected===s.id?' sel':''}" data-session="${escape(s.id)}" role="button" tabindex="0"><div><div class="d">${valid?d.getDate():''}</div><div class="w">${valid?'周'+WEEK[d.getDay()]:''}</div></div>
      <div><h4>${t.named?'':'<span class="unnamed">未命名</span>'}${escape(t.text)}</h4><div class="m">${valid?pad(d.getHours())+':'+pad(d.getMinutes())+' · ':''}${clock(s.duration)}${st}</div></div>
      <div class="n">${status(s)==='done'?`<b>${problems(s)}</b><div class="mini">${mini}</div>`:''}</div></div>`;
  }
  function renderList(){
    const rows=visible();let html='',month='';
    for(const s of rows){
      const d=new Date(s.created),key=state.sort==='time'&&!Number.isNaN(d.getTime())?d.getFullYear()+'-'+d.getMonth():'';
      if(state.sort==='time'&&key&&key!==month){month=key;const count=rows.filter(r=>{const x=new Date(r.created);return x.getFullYear()===d.getFullYear()&&x.getMonth()===d.getMonth();}).length;
        html+=`<div class="month">${['一','二','三','四','五','六','七','八','九','十','十一','十二'][d.getMonth()]}月<small>${d.getFullYear()} · ${count} 场</small></div>`;}
      html+=item(s);
    }
    $('sessionScroll').innerHTML=html||'<p class="empty">没有符合筛选的场次。</p>';sizes($('sessionScroll'));
  }
  function render(){renderChips();renderList();$('deskGame').textContent=state.game||'资料台';document.title='资料台 · '+(state.game||'');}

  // ---- detail ----
  async function select(id){
    state.selected=id;renderList();const s=state.sessions.find(row=>row.id===id);if(!s)return;
    renderDetail(s,null);
    try{const detail=await call('session_detail',id);if(state.selected===id){state.detail=detail;renderDetail(s,detail);}}
    catch(error){if(state.selected===id)$('sessionDetail').insertAdjacentHTML('beforeend',`<p class="d-note">${escape(error.message)}</p>`);}
  }
  function renderDetail(s,detail){
    const d=new Date(s.created),valid=!Number.isNaN(d.getTime()),t=title(s),job=state.jobs.find(j=>String(j.session_id)===String(s.id));
    const locked=state.busy||!!job,done=status(s)==='done';
    const date=valid?`${d.getFullYear()} 年 ${d.getMonth()+1} 月 ${d.getDate()} 日 周${WEEK[d.getDay()]} · ${pad(d.getHours())}:${pad(d.getMinutes())} 开始 · 时长 ${clock(s.duration)}`:'时长 '+clock(s.duration);
    const actions=`<div class="d-acts"><button class="btn solid" data-act="review"${s.can_review===false?' disabled':''}>回看</button>${done?'':`<button class="btn" data-act="handoff">复制整理指令</button>`}<button class="link" data-act="rename">重命名</button><button class="link" data-act="process"${locked?' disabled':''}>重新整理</button><button class="link" data-act="folder">资料文件夹</button><button class="link" data-act="export"${locked?' disabled':''}>导出</button><button class="link" data-act="raw">原始录像</button><button class="link" data-act="recover"${locked?' disabled':''}>恢复云端任务</button></div>`;
    let body='';
    if(!detail)body='<p class="d-note">正在读取这一场的整理结果…</p>';
    else if(detail.state!=='complete')body=`<p class="d-note">${escape(detail.label||'这一场还没有整理结果。')} 复制整理指令，粘贴给 Codex 或 Claude 整理后，原话和问题分布会出现在这里。</p>`;
    else{
      const kinds=detail.kinds||{},max=Math.max(1,...Object.keys(KIND).map(k=>kinds[k]||0)),other=OTHER.reduce((n,k)=>n+(kinds[k]||0),0);
      const quotes=Object.entries(KIND).map(([k,label])=>{const rows=detail.quotes[k]||[];if(!rows.length)return '';const shown=rows.filter(q=>q.text.length>=6&&q.text.length<=40);const list=(shown.length?shown:rows);
        return `<div class="kq k-${k}"><h5>${label}<small>${rows.length} 条</small></h5><ul>${list.slice(0,3).map(q=>`<li><button data-at="${q.at}" title="在回看中打开这一刻">${short(q.at)}</button><p>${escape(q.text)}</p></li>`).join('')}</ul>${list.length>3?`<button class="link more" data-more="${k}">展开其余 ${list.length-3} 条</button>`:''}</div>`;}).join('');
      const dist=Object.entries(KIND).map(([k,label])=>`<li class="k-${k}"><span>${label}</span><b>${kinds[k]||0}</b><i class="bar" data-width="${(kinds[k]||0)/max*100}"></i></li>`).join('');
      const ins=detail.insights.length?`<ul class="ins">${detail.insights.slice(0,8).map(i=>`<li data-issue="${escape(i.id)}">${escape(i.title)}<b>${i.count}</b></li>`).join('')}</ul>`:'<p class="note">这一场的证据还没有挂到洞察下。</p>';
      const evs=detail.events.map(e=>`<li><span>${short(e.start)}–${short(e.end)}</span>${escape(e.title)}</li>`).join('');
      body=`<div class="d-grid"><div><h3 class="d-h">原话 · 按问题类型</h3>${quotes||'<p class="note">这一场没有整理出问题。</p>'}</div>
        <div><div class="side-sec"><h3 class="d-h">问题分布</h3><ul class="dist">${dist}</ul><p class="note">另有 ${other} 条期待、建议、观察和正面评价</p></div>
        <div class="side-sec"><h3 class="d-h">挂在这些洞察下</h3>${ins}</div><div class="side-sec"><h3 class="d-h">活动</h3><ul class="evs">${evs}</ul></div></div></div>`;
    }
    $('sessionDetail').innerHTML=`<p class="d-date">${escape(date)}</p><h1>${t.named?'':'<span class="unnamed">未命名</span>'}${escape(t.text)}</h1>${actions}${job?`<p class="d-note">${escape(job.state==='queued'?'等待转写，前面的场次完成后继续。':job.detail||'正在转写，可以继续录制。')}</p>`:''}${s.error?`<p class="d-note">${escape(s.error)}</p>`:''}${body}`;
    sizes($('sessionDetail'));
  }
  function dialog(titleText,html,buttons){
    $('deskDialogBody').innerHTML=`<h2>${escape(titleText)}</h2>${html}`;$('deskDialogFoot').replaceChildren();
    const close=document.createElement('button');close.className='btn';close.textContent='取消';close.onclick=()=>$('deskDialog').close();$('deskDialogFoot').append(close);
    for(const [label,run] of buttons){const button=document.createElement('button');button.className='btn solid';button.textContent=label;button.onclick=async()=>{button.disabled=true;try{if(await run()!==false)$('deskDialog').close();}catch(error){toast(error.message);}finally{button.disabled=false;}};$('deskDialogFoot').append(button);}
    $('deskDialog').showModal();
  }
  async function copyHandoff(s){const text=['请用 Think Aloud 的单场整理方法（think-aloud-judgments），整理这一场记录，并按单场整理交接文件验收。','场次文件夹：'+s.path,'只整理这一场；不改议题表、对应表、界面目录、标签和反馈文件。完成后告诉我实例数、提议的新界面和拿不准的地方。'].join('\n');try{await navigator.clipboard.writeText(text);}catch(_){const area=document.createElement('textarea');area.value=text;document.body.append(area);area.select();document.execCommand('copy');area.remove();}toast('整理指令已复制，粘贴给 Codex 或 Claude 即可。');}
  async function act(name,s){
    try{
      if(name==='review'){await call('review_session',s.id);return;}
      if(name==='handoff'){await copyHandoff(s);return;}
      if(name==='folder'){await call('open_folder',s.id);return;}
      if(name==='raw'){await call('open_raw',s.id);return;}
      if(name==='export'){await call('package_session',s.id);toast('已开始导出这一场。');return;}
      if(name==='process'){dialog('重新整理这一场','<p>会按当前的转写设置重新转写这一场，旧的逐字稿和整理结果会保留。使用云端转写时会上传这一场的麦克风录音。</p>',[['开始',async()=>{await call('process_session',s.id);toast('已加入整理队列。');}]]);return;}
      if(name==='rename'){dialog('重命名','<input id="renameInput" maxlength="4096" autocomplete="off"><p class="note">留空恢复默认名称。</p>',[['保存',async()=>{const value=$('renameInput').value.trim();await call('rename_session',s.id,value);await refresh();toast('名称已保存');}]]);$('renameInput').value=s.session_name||'';$('renameInput').focus();return;}
      if(name==='recover'){dialog('恢复已有云端任务','<p>填写已有任务编号，继续查询原任务，不重新上传录音。</p><input id="recoverInput" autocomplete="off" spellcheck="false" placeholder="已有 task_id">',[['恢复任务',async()=>{const id=$('recoverInput').value.trim();if(!id){toast('请填写任务编号。');return false;}await call('recover_cloud_task',s.id,id);toast('已开始恢复云端任务。');}]]);}
    }catch(error){toast(error.message);}
  }

  // ---- events ----
  $('stateChips').onclick=event=>{const chip=event.target.closest('[data-filter]');if(!chip)return;state.filter=chip.dataset.filter;render();};
  $('kindChips').onclick=event=>{const chip=event.target.closest('[data-kind]');if(!chip)return;const k=chip.dataset.kind;state.kinds.has(k)?state.kinds.delete(k):state.kinds.add(k);render();};
  $('sortSelect').onchange=()=>{state.sort=$('sortSelect').value;renderList();};
  $('searchToggle').onclick=()=>{$('searchInput').classList.toggle('hidden');if(!$('searchInput').classList.contains('hidden'))$('searchInput').focus();else{$('searchInput').value='';state.search='';renderList();}};
  $('searchInput').oninput=()=>{state.search=$('searchInput').value;renderList();};
  $('sessionScroll').addEventListener('click',event=>{const row=event.target.closest('[data-session]');if(row)select(row.dataset.session);});
  $('sessionScroll').addEventListener('keydown',event=>{const row=event.target.closest('[data-session]');if(row&&(event.key==='Enter'||event.key===' ')){event.preventDefault();select(row.dataset.session);}});
  $('sessionDetail').addEventListener('click',event=>{
    const s=state.sessions.find(row=>row.id===state.selected);if(!s)return;
    const button=event.target.closest('[data-act]');if(button){act(button.dataset.act,s);return;}
    const at=event.target.closest('[data-at]');if(at){call('open_review',s.id,Number(at.dataset.at)).catch(error=>toast(error.message));return;}
    const more=event.target.closest('[data-more]');if(more){const box=more.closest('.kq'),k=more.dataset.more,rows=state.detail?.quotes?.[k]||[];box.querySelector('ul').innerHTML=rows.map(q=>`<li><button data-at="${q.at}" title="在回看中打开这一刻">${short(q.at)}</button><p>${escape(q.text)}</p></li>`).join('');more.remove();return;}
    const issue=event.target.closest('[data-issue]');if(issue){deskShow('insight');const label=title(s).text;window.insightBridge?.showSession(s.id,label);setTimeout(()=>window.insightBridge?.goToIssue(issue.dataset.issue),60);}
  });

  // ---- data ----
  async function refresh(){
    const data=await call('desk_state');
    const signature=JSON.stringify([data.sessions,data.background_jobs,data.busy,data.recording,data.game]);
    state.game=data.game;state.busy=data.busy||data.recording;state.jobs=data.background_jobs||[];
    if(signature===state.signature)return data;state.signature=signature;
    state.sessions=data.sessions||[];render();
    const current=state.sessions.find(row=>row.id===state.selected);if(current)renderDetail(current,state.detail?.id===current.id?state.detail:null);
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
