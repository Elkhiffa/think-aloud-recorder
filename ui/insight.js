(()=>{
  'use strict';
  const $=id=>document.getElementById(id);
  const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const KIND={confusion:'困惑',obstacle:'阻碍',cost:'操作成本',positive:'正向体验',negative:'负面评价',expectation:'预期',suggestion:'建议',self_correction:'自我修正',observation:'观察'};
  const CONTEXT={hud:'HUD / 战斗 / 大世界',multi_screen:'跨多个界面',outside_game:'游戏外窗口',unknown:'认不出界面'};
  const state={overview:null,instances:new Map(),labels:{},reports:[],report:null,issues:new Map(),feedback:[]};
  let api=null;

  async function call(method,...args){
    const response=await api[method](...args);
    if(!response?.ok)throw new Error(response?.error||'操作未完成。');
    return response.data;
  }
  function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
  function formatTime(seconds){
    if(!Number.isFinite(seconds))return '—';
    const total=Math.floor(seconds),h=Math.floor(total/3600),m=Math.floor(total%3600/60),s=total%60;
    return (h?h+':'+String(m).padStart(2,'0'):String(m).padStart(2,'0'))+':'+String(s).padStart(2,'0');
  }
  const key=(session,instance)=>session+'/'+instance;
  const label=row=>(state.labels[row.session_id]||row.session_id)+' '+row.instance_id;

  // Thumbnails decode video frames natively; load lazily, two at a time.
  const thumbQueue=[];let thumbActive=0;
  const thumbObserver=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){thumbObserver.unobserve(entry.target);thumbQueue.push(entry.target);pumpThumbs();}},{rootMargin:'400px'});
  function pumpThumbs(){
    while(thumbActive<2&&thumbQueue.length){
      const button=thumbQueue.shift();thumbActive++;
      call('thumbnail',button.dataset.session,Number(button.dataset.time)).then(src=>{const img=document.createElement('img');img.alt='所指时刻画面';img.src=src;button.replaceChildren(img);}).catch(()=>{button.textContent='无画面';}).finally(()=>{thumbActive--;pumpThumbs();});
    }
  }
  function thumb(session,time,caption){
    if(!Number.isFinite(time))return '<span class="thumb"></span>';
    return `<button type="button" class="thumb" data-session="${escape(session)}" data-time="${time}" data-caption="${escape(caption)}" title="查看大图"></button>`;
  }
  function jump(session,time,text){return Number.isFinite(time)?`<button type="button" class="jump" data-open-session="${escape(session)}" data-open-time="${time}" title="在新窗口打开回看并停在这一刻">${escape(text)}</button>`:'';}

  // One span covers what was evaluated and when it was said. The review opens at its start,
  // or 10 seconds before the remark when the span is longer than two minutes.
  function span(row){
    if(row.refers_basis==='earlier_session'||!Number.isFinite(row.refers_start))return [row.said_start,row.said_start,row.said_start];
    const from=Math.min(row.refers_start,row.said_start),to=Math.max(row.refers_end,row.said_start);
    return [from,to,to-from>120?Math.max(from,row.said_start-10):from];
  }
  function card(row,link,issue){
    const at=row.frame_at??row.refers_start??row.said_start,[from,to,open]=span(row);
    const time=jump(row.session_id,open,from===to?formatTime(from):`${formatTime(from)}–${formatTime(to)}`);
    const earlier=row.refers_basis==='earlier_session'?'<span>指向本场之前</span>':'';
    const compare=row.compare_to?jump(row.session_id,row.compare_to.start,`对照 ${formatTime(row.compare_to.start)}`):'';
    let screen=row.catalog_screen||row.screen;
    screen=screen?escape(screen)+(row.screen_proposed&&!row.catalog_screen?'（提议的界面）':''):escape(CONTEXT[row.screen_context]||'未注明界面');
    if(row.route?.length)screen+=' · 路线：'+escape(row.route.join(' -> '));
    if(row.elements?.length)screen+=' › '+escape(row.elements.join('、'));
    const counter=link?.role==='counter';
    return `<article class="card${counter?' counter':''}" data-key="${escape(key(row.session_id,row.instance_id))}" data-issue="${escape(issue||'')}">${thumb(row.session_id,at,label(row)+' · '+formatTime(at))}<div>`+
      `<h4 class="card-title"><span class="kind kind-${escape(row.kind)}">${escape(KIND[row.kind]||row.kind)}</span><span>${escape(row.event_title||'未归入活动')}</span>${counter?'<span class="badge">反例</span>':''}</h4>`+
      `<p class="statement">${escape(row.statement)}</p>`+
      `<div class="aside"><span class="meta">${time}${earlier}${compare}<span>${escape(label(row))}</span>${flag({kind:'instance',session_id:row.session_id,instance_id:row.instance_id,issue:issue&&issue!=='cited'?issue:undefined})}</span><div>界面：${screen}</div>${link?.reason?`<div>归入理由：${escape(link.reason)}</div>`:''}</div></div></article>`;
  }
  function cards(links,issue,role){
    return links.map(link=>{const row=state.instances.get(key(link.session_id,link.instance_id));return row?card(row,{...link,role},issue):'';}).join('');
  }
  function counts(node){
    let support=node.support.length,counter=node.counter.length;
    for(const child of node.children){const n=counts(child);support+=n.support;counter+=n.counter;}
    return {support,counter};
  }
  function countText(node,extra=0){const n=counts(node);return `支持 ${n.support+extra}`+(n.counter?` · 反例 ${n.counter}`:'');}
  function toggle(id,text,n,expanded,level,code=''){return `<button type="button" class="toggle" aria-expanded="${expanded}" aria-controls="${id}-body" data-level="${level}"><span class="label" title="${escape(text.replace(/<[^>]+>/g,''))}">${text}</span><span class="n">${escape(n)}${code?`<span class="code">${escape(code)}</span>`:''}</span></button>`;}
  const issueName=id=>state.issues.get(id)?.title||id;
  // The feedback entry stays outside the toggle button so it never expands or collapses the section.
  function flag(target){return `<button type="button" class="flag" data-flag="${escape(JSON.stringify(target))}" title="这里不对？写一句该怎么调">有问题</button>`;}
  function row(id,text,n,expanded,level,code,target){return `<div class="row">${toggle(id,text,n,expanded,level,code)}${target?flag(target):''}</div>`;}
  function evidenceBlock(node){
    let html='';
    if(node.support.length)html+=`<div class="cards">${cards(node.support,node.id,'support')}</div>`;
    if(node.counter.length)html+=`<p class="subhead">反例</p><div class="cards">${cards(node.counter,node.id,'counter')}</div>`;
    return html;
  }
  // 洞察 → 议题 → 子议题: one recursive section per level; leaves show their cards directly.
  function issueSection(node,level=1){
    const status=node.status==='candidate'?' <span class="badge">待你定</span>':'';
    const title=node.id==='BUG'?'BUG':escape(node.title);
    let body=node.description?`<p class="desc">${escape(node.description)}</p>`:'';
    for(const child of node.children)body+=issueSection(child,level+1);
    const own=node.support.length+node.counter.length;
    if(own&&(node.children.length||level===1)){
      const name=node.children.length?'未归入下级':'证据';
      body+=`<section class="group level-${level+1}" id="issue-${escape(node.id)}-own" data-issue="${escape(node.id)}">${row('issue-'+node.id+'-own',name,`${own} 条`,false,level+1)}<div id="issue-${escape(node.id)}-own-body" hidden>${evidenceBlock(node)}</div></section>`;
    }else if(own)body+=evidenceBlock(node);
    let extra=0;
    if(node.id==='BUG'&&state.overview.bug_unorganized.length){
      extra=state.overview.bug_unorganized.length;
      body+=`<section class="group level-2" id="issue-BUG-raw">${row('issue-BUG-raw','未整理的 bug 原话',`${extra} 处`,false,2)}<ul class="hits" id="issue-BUG-raw-body" hidden>`+
        state.overview.bug_unorganized.map(hit=>`<li>${jump(hit.session_id,hit.start,(state.labels[hit.session_id]||hit.session_id)+' '+formatTime(hit.start))}<span>“${escape(hit.text)}”${hit.state==='instance'?` <span class="badge">已是实例 ${escape(hit.instances.join('、'))}，未挂 BUG</span>`:''}</span></li>`).join('')+'</ul></section>';
    }
    if(!body)body='<p class="desc">暂无证据。</p>';
    const n=node.id==='BUG'&&extra?countText(node)+` · 未整理 ${extra}`:countText(node);
    return `<section class="${level===1?'issue':'group'} level-${level}" id="issue-${escape(node.id)}" data-issue="${escape(node.id)}">${row('issue-'+node.id,`${title}${status}`,n,level===1,level,node.id==='BUG'?'':node.id,{kind:'issue',id:node.id})}<div id="issue-${escape(node.id)}-body"${level===1?'':' hidden'}>${body}</div></section>`;
  }
  function orderedIssues(){
    // BUG is a fixed issue; keep it last so design issues lead.
    const nodes=state.overview.issues.filter(node=>node.id!=='BUG');
    const bug=state.overview.issues.find(node=>node.id==='BUG');
    return bug?nodes.concat(bug):nodes;
  }
  function cited(){
    // Report citations that no issue section shows still need a place on the right.
    const shown=new Set();
    const walk=node=>{for(const link of node.support.concat(node.counter))shown.add(key(link.session_id,link.instance_id));node.children.forEach(walk);};
    state.overview.issues.forEach(walk);
    const extra=[];
    for(const row of state.report?.citations||[])if(row.kind==='instance'&&row.resolved){const k=key(row.session_id,row.instance_id);if(!shown.has(k)&&!extra.includes(k))extra.push(k);}
    return extra;
  }
  function renderEvidence(){
    const nodes=orderedIssues();
    state.issues=new Map();
    const index=node=>{state.issues.set(node.id,node);node.children.forEach(index);};nodes.forEach(index);
    let html=nodes.map(node=>issueSection(node)).join('');
    const extra=cited();
    if(extra.length)html+=`<section class="issue level-1" id="issue-cited" data-issue="cited">${row('issue-cited','报告引用的其他证据',`${extra.length} 条`,true,1)}<div id="issue-cited-body"><div class="cards">${extra.map(k=>card(state.instances.get(k),null,'cited')).join('')}</div></div></section>`;
    $('evidenceList').innerHTML=html||'<p class="empty">资料库里还没有议题。</p>';
    document.querySelectorAll('#evidenceList .thumb[data-session]').forEach(button=>thumbObserver.observe(button));
    measureRows();updateStuck();
  }

  // Sticky rows: the current 洞察 / 议题 / 子议题 stay on top while their cards scroll; the next
  // 议题 in this 洞察 and the next 洞察 wait at the bottom. Row heights feed the sticky offsets.
  function measureRows(){
    const pane=$('evidencePane');
    for(const level of [1,2,3]){const row=document.querySelector(`#evidenceList .level-${level}>.row`);if(row)pane.style.setProperty('--r'+level,row.offsetHeight+'px');}
  }
  const sections=(parent,level)=>[...parent.querySelectorAll(`:scope>section.level-${level},:scope>div>section.level-${level}`)];
  function current(list,line){let found=-1;list.forEach((section,i)=>{if(section.getBoundingClientRect().top<=line)found=i;});return found;}
  let stuckFrame=0;
  function updateStuck(){
    stuckFrame=0;
    const pane=$('evidencePane'),bar=$('nextBar');
    if(pane.hidden){bar.hidden=true;return;}
    const box=pane.getBoundingClientRect(),head=document.querySelector('.evidence-head').getBoundingClientRect().bottom;
    const r1=parseFloat(pane.style.getPropertyValue('--r1'))||0;
    const bottom=box.bottom-(bar.hidden?0:bar.offsetHeight);
    const tops=[...$('evidenceList').children].filter(node=>node.matches('section'));
    const i=current(tops,head+2),items=[];
    const below=section=>section&&section.getBoundingClientRect().top>bottom-4;
    if(i>=0){
      const body=tops[i].querySelector(':scope>div[id$="-body"]');
      if(body&&!body.hidden){
        const subs=sections(body,2),j=current(subs,head+r1+2),next=subs[j+1];
        if(below(next))items.push([next,2]);
      }
    }
    const nextTop=tops[i+1]||(i<0?tops[0]:null);
    if(below(nextTop))items.push([nextTop,1]);
    bar.innerHTML=items.map(([section,level])=>{const toggle=section.querySelector(':scope>.row>.toggle');
      return `<button type="button" class="next level-${level}" data-next="${escape(section.id)}">${toggle.querySelector('.label').innerHTML}<span class="n">${toggle.querySelector('.n').innerHTML}</span></button>`;}).join('');
    bar.hidden=!items.length;
  }
  function scheduleStuck(){if(!stuckFrame)stuckFrame=requestAnimationFrame(updateStuck);}
  function setExpanded(button,expanded){
    button.setAttribute('aria-expanded',String(expanded));
    const body=$(button.getAttribute('aria-controls'));if(body)body.hidden=!expanded;
  }
  function revealSection(id){
    const section=$('issue-'+id);if(!section)return null;
    for(let node=section;node&&node!==$('evidenceList');node=node.parentElement){
      if(node.matches?.('section.issue,section.group'))setExpanded(node.querySelector(':scope>.row>.toggle'),true);
    }
    return section;
  }
  function flash(element){element.classList.remove('flash');void element.offsetWidth;element.classList.add('flash');}
  function showEvidenceTab(){selectTab('evidence');}
  function goToIssue(id){
    showEvidenceTab();
    const section=revealSection(id);
    if(!section){status('右栏没有这个议题：'+id,true);return;}
    section.scrollIntoView({block:'start',behavior:'smooth'});
  }
  function goToInstance(sessionId,instanceId,issue){
    showEvidenceTab();
    const k=key(sessionId,instanceId);
    const all=[...document.querySelectorAll('#evidenceList .card')].filter(card=>card.dataset.key===k);
    const target=all.find(card=>card.dataset.issue===issue)||all.find(card=>issue&&card.dataset.issue.startsWith(issue+'.'))||all[0];
    if(!target){status('右栏没有这条证据：'+k,true);return;}
    for(let node=target.parentElement;node&&node!==$('evidenceList');node=node.parentElement){
      if(node.matches('section.issue,section.group'))setExpanded(node.querySelector(':scope>.row>.toggle'),true);
    }
    status(all.length>1?`这条证据出现在 ${all.length} 处，已定位到“${escape(issueName(target.dataset.issue))}”。`:'');
    target.scrollIntoView({block:'start',behavior:'smooth'});flash(target);
  }

  // Minimal Markdown: headings, paragraphs, lists, quotes, tables, bold, code and the two citation forms.
  function inline(text){
    let html=escape(text);
    html=html.replace(/\[([^\]\n]{1,80})\]\((i|issue):([^)\s#]+)(?:#([^)\s]+))?\)/g,(match,text,kind,target,issue)=>{
      let resolved;
      if(kind==='issue')resolved=state.issues.has(target);
      else{const [session,...rest]=target.split('/');resolved=state.instances.has(key(session,rest.join('/')));}
      const attrs=kind==='issue'?`data-cite-issue="${target}"`:`data-cite-instance="${target}" data-cite-in="${issue||''}"`;
      return `<a class="cite${resolved?'':' unresolved'}" href="#" ${attrs}${resolved?'':' title="资料库里找不到这条引用"'}>${text}</a>`;
    });
    html=html.replace(/\[([^\]\n]+)\]\(([^)\s]+)\)/g,'$1');
    html=html.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>');
    return html;
  }
  function markdown(source){
    const lines=source.replace(/\r\n?/g,'\n').split('\n');const out=[];let i=0;
    const cells=line=>line.trim().replace(/^\||\|$/g,'').split('|').map(cell=>cell.trim());
    while(i<lines.length){
      const line=lines[i];
      if(!line.trim()){i++;continue;}
      let match=line.match(/^(#{1,4})\s+(.*)$/);
      if(match){out.push(`<h${match[1].length}>${inline(match[2])}</h${match[1].length}>`);i++;continue;}
      if(/^\s*(-{3,}|\*{3,})\s*$/.test(line)){out.push('<hr>');i++;continue;}
      if(/^\s*\|/.test(line)&&/^\s*\|?\s*:?-{2,}/.test(lines[i+1]||'')){
        const head=cells(line);i+=2;const rows=[];
        while(i<lines.length&&/^\s*\|/.test(lines[i])){rows.push(cells(lines[i]));i++;}
        out.push('<table><thead><tr>'+head.map(cell=>`<th>${inline(cell)}</th>`).join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(cell=>`<td>${inline(cell)}</td>`).join('')+'</tr>').join('')+'</tbody></table>');
        continue;
      }
      if(/^\s*>/.test(line)){const quote=[];while(i<lines.length&&/^\s*>/.test(lines[i])){quote.push(lines[i].replace(/^\s*>\s?/,''));i++;}out.push(`<blockquote>${markdown(quote.join('\n'))}</blockquote>`);continue;}
      if(/^\s*([-*]|\d+[.)])\s+/.test(line)){
        // Nested lists are indented by two or more spaces.
        const items=[];const ordered=/^\s*\d/.test(line);
        while(i<lines.length&&(/^\s*([-*]|\d+[.)])\s+/.test(lines[i])||/^\s{2,}\S/.test(lines[i]))){
          const item=lines[i].match(/^(\s*)([-*]|\d+[.)])\s+(.*)$/);
          if(item&&item[1].length<2)items.push({text:item[3],children:[]});
          else if(items.length)items[items.length-1].children.push(lines[i].replace(/^\s{2,4}/,''));
          i++;
        }
        const tag=ordered?'ol':'ul';
        out.push(`<${tag}>`+items.map(item=>`<li>${inline(item.text)}${item.children.length?markdown(item.children.join('\n')):''}</li>`).join('')+`</${tag}>`);
        continue;
      }
      const para=[];
      while(i<lines.length&&lines[i].trim()&&!/^(#{1,4}\s|\s*>|\s*([-*]|\d+[.)])\s+|\s*\|)/.test(lines[i])){para.push(lines[i]);i++;}
      if(!para.length){para.push(line);i++;}
      out.push(`<p>${para.map(inline).join('<br>')}</p>`);
    }
    return out.join('');
  }
  function renderReport(){
    if(!state.report){
      $('report').innerHTML=state.reports.length?'<p class="empty">请选择报告。</p>':'<p class="empty">资料库的“洞察”目录下还没有报告。跨场次分析 agent 写好报告后，点“刷新”。</p>';
      return;
    }
    $('report').innerHTML=markdown(state.report.text);
    const missing=state.report.citations.filter(row=>!row.resolved).length;
    if(missing)status(`报告里有 ${missing} 条引用在资料库中找不到，已用虚线标出。`,true);
  }

  function selectTab(name){
    for(const [tab,pane,id] of [['tabEvidence','evidencePane','evidence'],['tabFeedback','feedbackPane','feedback']]){
      $(tab).setAttribute('aria-selected',String(id===name));$(pane).hidden=id!==name;
    }
    scheduleStuck();
  }

  // Feedback: agent output is accepted by default; the user only marks what is wrong and how to adjust it.
  function targetName(target){
    if(target.kind==='issue')return issueName(target.id);
    const row=state.instances.get(key(target.session_id,target.instance_id));
    const where=target.issue?`（在“${issueName(target.issue)}”下）`:'';
    return row?`${KIND[row.kind]||row.kind} · ${row.event_title||'未归入活动'} ${label(row)}${where}`:`${target.session_id} ${target.instance_id}${where}`;
  }
  function feedbackForm(value=''){return `<form class="feedback-form"><label class="sr-only" for="feedbackText">哪里不对、该怎么调</label><textarea id="feedbackText" name="text" rows="2" required maxlength="2000" placeholder="哪里不对、该怎么调，例如：这条应该归到“找不到入口”">${escape(value)}</textarea><div class="form-actions"><button type="submit">记下</button><button type="button" data-feedback-cancel>取消</button></div></form>`;}
  function openFlag(button){
    document.querySelectorAll('#evidenceList .feedback-form').forEach(form=>form.remove());
    const target=JSON.parse(button.dataset.flag);
    const anchor=button.closest('.row')||button.closest('.card');
    anchor.insertAdjacentHTML('afterend',feedbackForm());
    const form=anchor.nextElementSibling;form.querySelector('textarea').focus();
    form.onsubmit=async event=>{
      event.preventDefault();
      try{
        state.feedback=await call('add_feedback',{target,text:String(new FormData(form).get('text')).trim()});
        form.remove();renderFeedback();status(`已记下对“${targetName(target)}”的反馈，下一轮整理时会按它调整。`);
      }catch(error){status(error.message,true);}
    };
  }
  function renderFeedback(){
    const open=state.feedback.filter(item=>item.status==='open').length;
    $('feedbackCount').textContent=open?`(${open})`:'';
    if(!state.feedback.length){$('feedbackList').innerHTML='<p class="empty">还没有反馈。在证据页任意议题或证据卡旁点“有问题”，写一句哪里不对、该怎么调。</p>';return;}
    $('feedbackList').innerHTML=[...state.feedback].reverse().map(item=>`<article class="feedback-item${item.status==='open'?'':' resolved'}" data-feedback-id="${escape(item.id)}">`+
      `<p class="feedback-target"><a href="#" data-feedback-go>${escape(targetName(item.target))}</a><span class="badge">${item.status==='open'?'待处理':'已处理'}</span><span class="when">${escape(item.created.slice(0,16).replace('T',' '))}</span></p>`+
      `<p class="feedback-text">${escape(item.text)}</p>${item.resolution?`<p class="feedback-resolution">处理：${escape(item.resolution)}</p>`:''}`+
      `${item.status==='open'?'<div class="form-actions"><button type="button" data-feedback-edit>修改</button><button type="button" data-feedback-remove>删除</button></div>':''}</article>`).join('');
  }
  async function feedbackAction(article,action){
    const id=article.dataset.feedbackId,item=state.feedback.find(entry=>entry.id===id);
    if(action==='go'){item.target.kind==='issue'?goToIssue(item.target.id):goToInstance(item.target.session_id,item.target.instance_id,item.target.issue||null);return;}
    if(action==='remove'){
      const button=article.querySelector('[data-feedback-remove]');
      if(!button.dataset.armed){button.dataset.armed='1';button.textContent='再点一次删除';return;}
      state.feedback=await call('remove_feedback',id);renderFeedback();status('已删除这条反馈。');return;
    }
    article.querySelector('.form-actions').outerHTML=feedbackForm(item.text);
    const form=article.querySelector('form');form.querySelector('textarea').focus();
    form.onsubmit=async event=>{
      event.preventDefault();
      try{state.feedback=await call('edit_feedback',id,String(new FormData(form).get('text')).trim());renderFeedback();status('已修改这条反馈。');}
      catch(error){status(error.message,true);}
    };
  }
  async function openReport(name){
    state.report=name?await call('read_report',name):null;
    renderReport();renderEvidence();
  }
  async function load(){
    status('正在读取资料库…');
    try{
      const overview=await call('get_overview');
      state.overview=overview;state.labels=overview.session_labels;state.reports=overview.reports;state.feedback=overview.feedback;
      state.instances=new Map(overview.instances.map(row=>[key(row.session_id,row.instance_id),row]));
      $('title').textContent='洞察 · '+overview.vault;document.title=$('title').textContent;
      const previous=$('reportSelect').value;
      $('reportSelect').innerHTML=overview.reports.length?overview.reports.map(row=>`<option value="${escape(row.name)}">${escape(row.name)}</option>`).join(''):'<option value="">（没有报告）</option>';
      if(overview.reports.some(row=>row.name===previous))$('reportSelect').value=previous;
      renderEvidence();renderFeedback();
      await openReport($('reportSelect').value);
      if(!state.report||!state.report.citations.some(row=>!row.resolved))status('');
    }catch(error){status(error.message,true);}
  }

  document.addEventListener('click',event=>{
    const open=event.target.closest('[data-open-session]');
    if(open){
      status('正在打开回看…');
      call('open_review',open.dataset.openSession,Number(open.dataset.openTime)).then(()=>status('')).catch(error=>status(error.message,true));
      return;
    }
    const cite=event.target.closest('.cite');
    if(cite){
      event.preventDefault();
      if(cite.classList.contains('unresolved')){status('资料库里找不到这条引用。',true);return;}
      if(cite.dataset.citeIssue)goToIssue(cite.dataset.citeIssue);
      else{const [session,...rest]=cite.dataset.citeInstance.split('/');goToInstance(session,rest.join('/'),cite.dataset.citeIn||null);}
      return;
    }
    const button=event.target.closest('.toggle');
    if(button){
      const expanded=button.getAttribute('aria-expanded')!=='true';setExpanded(button,expanded);
      const section=button.closest('section');
      if(!expanded&&section.getBoundingClientRect().top<document.querySelector('.evidence-head').getBoundingClientRect().bottom)section.scrollIntoView({block:'start'});
      scheduleStuck();return;
    }
    const next=event.target.closest('[data-next]');
    if(next){const section=$(next.dataset.next);setExpanded(section.querySelector(':scope>.row>.toggle'),true);section.scrollIntoView({block:'start',behavior:'smooth'});return;}
    const flagButton=event.target.closest('[data-flag]');
    if(flagButton){openFlag(flagButton);return;}
    if(event.target.closest('[data-feedback-cancel]')){const form=event.target.closest('form');form.closest('.feedback-item')?renderFeedback():form.remove();return;}
    const feedbackButton=event.target.closest('[data-feedback-go],[data-feedback-edit],[data-feedback-remove]');
    if(feedbackButton){
      event.preventDefault();
      const action=feedbackButton.hasAttribute('data-feedback-go')?'go':feedbackButton.hasAttribute('data-feedback-edit')?'edit':'remove';
      feedbackAction(feedbackButton.closest('.feedback-item'),action).catch(error=>status(error.message,true));
      return;
    }
    const thumbButton=event.target.closest('.thumb[data-session]');
    if(thumbButton){
      $('lightboxCaption').textContent=thumbButton.dataset.caption;$('lightboxImage').removeAttribute('src');$('lightbox').hidden=false;
      call('thumbnail',thumbButton.dataset.session,Number(thumbButton.dataset.time),true).then(src=>{$('lightboxImage').src=src;}).catch(error=>{$('lightboxCaption').textContent=error.message;});
      return;
    }
    if(event.target.closest('#lightbox'))$('lightbox').hidden=true;
  });
  document.addEventListener('keydown',event=>{if(event.key==='Escape')$('lightbox').hidden=true;});
  // Cards and sections scroll to just below the sticky outline, whatever its current height.
  new ResizeObserver(()=>$('evidencePane').style.setProperty('--head',document.querySelector('.evidence-head').offsetHeight-16+'px')).observe(document.querySelector('.evidence-head'));
  $('expandAll').onclick=()=>{document.querySelectorAll('#evidenceList .toggle').forEach(button=>setExpanded(button,true));scheduleStuck();};
  $('collapseAll').onclick=()=>{document.querySelectorAll('#evidenceList .toggle').forEach(button=>setExpanded(button,false));$('evidencePane').scrollTop=0;scheduleStuck();};
  $('evidencePane').addEventListener('scroll',scheduleStuck,{passive:true});
  new ResizeObserver(()=>{measureRows();scheduleStuck();}).observe($('evidencePane'));
  $('reportSelect').onchange=()=>openReport($('reportSelect').value).catch(error=>status(error.message,true));
  $('refresh').onclick=load;
  $('tabEvidence').onclick=()=>selectTab('evidence');
  $('tabFeedback').onclick=()=>selectTab('feedback');

  function start(){
    if(api)return;
    api=window.pywebview.api;
    api.ready().catch(()=>{});
    load();
  }
  if(window.pywebview?.api)start();else window.addEventListener('pywebviewready',start);
})();
