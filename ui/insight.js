(()=>{
  'use strict';
  const $=id=>document.getElementById(id);
  const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const KIND={confusion:'困惑',obstacle:'阻碍',cost:'操作成本',positive:'正向体验',negative:'负面评价',expectation:'预期',suggestion:'建议',self_correction:'自我修正',observation:'观察'};
  const CONTEXT={hud:'HUD / 战斗 / 大世界',multi_screen:'跨多个界面',outside_game:'游戏外窗口',unknown:'认不出界面'};
  const state={overview:null,instances:new Map(),labels:{},reports:[],report:null,issues:new Map(),hidden:new Set(),hiddenIssues:new Set()};
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
      `<div class="aside"><span class="meta">${time}${earlier}${compare}<span>${escape(label(row))}</span></span><div>界面：${screen}</div>${link?.reason?`<div>归入理由：${escape(link.reason)}</div>`:''}</div></div></article>`;
  }
  function cards(links,issue,role){
    return links.map(link=>{const row=state.instances.get(key(link.session_id,link.instance_id));return row?card(row,{...link,role},issue):'';}).join('');
  }
  function counts(node){
    let support=node.support.length,counter=node.counter.length;
    for(const child of node.children){support+=child.support.length;counter+=child.counter.length;}
    return {support,counter};
  }
  function countText(node,extra=0){const n=counts(node);return `支持 ${n.support+extra}`+(n.counter?` · 反例 ${n.counter}`:'');}
  function toggle(id,text,n,expanded,level,code=''){return `<button type="button" class="toggle" aria-expanded="${expanded}" aria-controls="${id}-body" data-level="${level}"><span class="label">${text}</span><span class="n">${escape(n)}${code?`<span class="code">${escape(code)}</span>`:''}</span></button>`;}
  const issueName=id=>state.issues.get(id)?.title||id;
  function evidenceBlock(node){
    let html='';
    if(node.support.length)html+=`<div class="cards">${cards(node.support,node.id,'support')}</div>`;
    if(node.counter.length)html+=`<p class="subhead">反例</p><div class="cards">${cards(node.counter,node.id,'counter')}</div>`;
    return html;
  }
  function issueSection(node){
    const status=node.status==='candidate'?' <span class="badge">候选</span>':'';
    const desc=node.description?`<p class="desc">${escape(node.description)}</p>`:'';
    let body=desc;
    for(const child of node.children){
      body+=`<section class="group" id="issue-${escape(child.id)}" data-issue="${escape(child.id)}">${toggle('issue-'+child.id,`${escape(child.title)}${child.status==='candidate'?' <span class="badge">候选</span>':''}`,countText(child),false,2,child.id)}`+
        `<div id="issue-${escape(child.id)}-body" hidden>${child.description?`<p class="desc">${escape(child.description)}</p>`:''}${evidenceBlock(child)}</div></section>`;
    }
    const own=node.support.length+node.counter.length;
    if(own&&node.children.length)body+=`<section class="group" id="issue-${escape(node.id)}-own" data-issue="${escape(node.id)}">${toggle('issue-'+node.id+'-own','未归入子议题',`${own} 条`,false,2)}<div id="issue-${escape(node.id)}-own-body" hidden>${evidenceBlock(node)}</div></section>`;
    else if(own)body+=`<section class="group" id="issue-${escape(node.id)}-own" data-issue="${escape(node.id)}">${toggle('issue-'+node.id+'-own','证据',`${own} 条`,false,2)}<div id="issue-${escape(node.id)}-own-body" hidden>${evidenceBlock(node)}</div></section>`;
    let extra=0;
    if(node.id==='BUG'&&state.overview.bug_unorganized.length){
      extra=state.overview.bug_unorganized.length;
      body+=`<section class="group" id="issue-BUG-raw">${toggle('issue-BUG-raw','未整理的 bug 原话',`${extra} 处`,false,2)}<ul class="hits" id="issue-BUG-raw-body" hidden>`+
        state.overview.bug_unorganized.map(hit=>`<li>${jump(hit.session_id,hit.start,(state.labels[hit.session_id]||hit.session_id)+' '+formatTime(hit.start))}<span>“${escape(hit.text)}”${hit.state==='instance'?` <span class="badge">已是实例 ${escape(hit.instances.join('、'))}，未挂 BUG</span>`:''}</span></li>`).join('')+'</ul></section>';
    }
    if(!body)body='<p class="desc">暂无证据。</p>';
    return `<section class="issue" id="issue-${escape(node.id)}" data-issue="${escape(node.id)}">${toggle('issue-'+node.id,`${escape(node.id==='BUG'?'BUG':node.title)}${status}`,node.id==='BUG'&&extra?countText(node)+` · 未整理 ${extra}`:countText(node),true,1,node.id==='BUG'?'':node.id)}<div id="issue-${escape(node.id)}-body">${body}</div></section>`;
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
    let html=nodes.map(issueSection).join('');
    const extra=cited();
    if(extra.length)html+=`<section class="issue" id="issue-cited" data-issue="cited">${toggle('issue-cited','报告引用的其他证据',`${extra.length} 条`,true,1)}<div id="issue-cited-body"><div class="cards">${extra.map(k=>card(state.instances.get(k),null,'cited')).join('')}</div></div></section>`;
    $('evidenceList').innerHTML=html||'<p class="empty">资料库里还没有议题。</p>';
    document.querySelectorAll('#evidenceList .thumb[data-session]').forEach(button=>thumbObserver.observe(button));
  }
  function setExpanded(button,expanded){
    button.setAttribute('aria-expanded',String(expanded));
    const body=$(button.getAttribute('aria-controls'));if(body)body.hidden=!expanded;
  }
  function revealSection(id){
    const section=$('issue-'+id);if(!section)return null;
    for(let node=section;node&&node!==$('evidenceList');node=node.parentElement){
      if(node.matches?.('section.issue,section.group'))setExpanded(node.querySelector(':scope>.toggle'),true);
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
      if(node.matches('section.issue,section.group'))setExpanded(node.querySelector(':scope>.toggle'),true);
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

  // Proposed screens: confirm while browsing; results stay untouched.
  const families=groups=>{const map=new Map();for(const group of groups){if(state.hidden.has(group.name))continue;if(!map.has(group.family))map.set(group.family,[]);map.get(group.family).push(group);}return map;};
  function renderProposed(){
    const groups=state.overview.proposed;
    const visible=groups.filter(group=>!state.hidden.has(group.name));
    $('proposedCount').textContent=visible.length?`(${visible.length})`:'';
    if(!visible.length){$('proposedList').innerHTML='<p class="empty">没有待确认的界面。</p>';return;}
    let html='';
    for(const [family,items] of families(groups)){
      html+=`<section class="family">${items.length>1?`<h2>名称相近：${escape(family)}</h2>`:''}`+items.map(group=>{
        const shots=group.instances.map(row=>{const at=row.frame_at??row.refers_start??row.said_start,name=(state.labels[row.session_id]||row.session_id)+' '+row.instance_id;
          return `<div class="shot">${thumb(row.session_id,at,name+' · '+formatTime(at))}<p>${escape(name)} ${jump(row.session_id,at,formatTime(at))}</p><p>${escape(row.statement.slice(0,80))}${row.statement.length>80?'…':''}</p>${row.route?.length?`<p>路线：${escape(row.route.join(' -> '))}</p>`:''}</div>`;}).join('');
        return `<article class="proposal" data-name="${escape(group.name)}" data-game="${escape(group.games[0]||'')}"><h3>${escape(group.name)} <span class="count">${group.instances.length} 处</span></h3><div class="shots">${shots}</div>`+
          `<div class="actions"><button type="button" data-proposal="new">收为新界面</button><button type="button" data-proposal="into">并入已有界面</button><button type="button" data-proposal="skip">暂不处理</button></div></article>`;
      }).join('')+'</section>';
    }
    $('proposedList').innerHTML=html;
    document.querySelectorAll('#proposedList .thumb[data-session]').forEach(button=>thumbObserver.observe(button));
  }
  const screenLists=new Map();
  async function screensFor(game){if(!screenLists.has(game))screenLists.set(game,await call('list_screens',game));return screenLists.get(game);}
  async function proposalAction(article,action){
    const name=article.dataset.name,game=article.dataset.game;
    if(action==='skip'){state.hidden.add(name);renderProposed();return;}
    const actions=article.querySelector('.actions');
    if(action==='new'){
      actions.innerHTML=`<form><label class="sr-only" for="newId">界面编号</label><input id="newId" name="id" value="${escape(name)}" required placeholder="完整导航路径，如 培养/装备/槽位调平"><label class="sr-only" for="newName">显示名称</label><input id="newName" name="name" placeholder="显示名称（默认取最后一级）"><button type="submit">确认收入</button><button type="button" data-proposal="cancel">取消</button></form>`;
    }else{
      const screens=await screensFor(game);
      actions.innerHTML=`<form><label class="sr-only" for="intoId">已有界面</label><input id="intoId" name="into" list="screenOptions" required placeholder="搜索目录里的界面编号"><datalist id="screenOptions">${screens.map(row=>`<option value="${escape(row.id)}">${escape(row.name)}${row.aliases.length?'（'+escape(row.aliases.join('、'))+'）':''}</option>`).join('')}</datalist><button type="submit">确认并入</button><button type="button" data-proposal="cancel">取消</button></form>`;
    }
    const form=actions.querySelector('form');form.querySelector('input').focus();
    form.onsubmit=async event=>{
      event.preventDefault();const data=new FormData(form);
      try{
        const request={game,proposed:name};
        if(action==='new'){request.new_id=String(data.get('id')).trim();request.name=String(data.get('name')||'').trim();}
        else request.into=String(data.get('into')).trim();
        const result=await call('confirm_proposed',request);
        state.overview.proposed=result.proposed;screenLists.delete(game);
        status(`已把“${name}”${action==='new'?'收为新界面 '+result.result.screen:'并入 '+result.result.screen}。`);
        renderProposed();
      }catch(error){status(error.message,true);}
    };
  }

  function selectTab(name){
    for(const [tab,pane,id] of [['tabEvidence','evidencePane','evidence'],['tabIssues','issuesPane','issues'],['tabProposed','proposedPane','proposed']]){
      $(tab).setAttribute('aria-selected',String(id===name));$(pane).hidden=id!==name;
    }
  }

  // Candidate issues: decide while looking at their evidence, like proposed screens.
  function candidates(){
    const found=[];
    const walk=(node,parent)=>{if(node.status==='candidate'&&!state.hiddenIssues.has(node.id))found.push({node,parent});node.children.forEach(child=>walk(child,node));};
    state.overview.issues.forEach(node=>walk(node,null));
    return found;
  }
  function renderCandidates(){
    const found=candidates();
    $('issueCount').textContent=found.length?`(${found.length})`:'';
    $('confirmAll').hidden=found.length<2;$('confirmAll').textContent='全部确认';delete $('confirmAll').dataset.armed;
    if(!found.length){$('issueList').innerHTML='<p class="empty">没有待确认的议题。</p>';return;}
    $('issueList').innerHTML=found.map(({node,parent})=>{
      const links=[...node.support.map(link=>({...link,role:'support'})),...node.counter.map(link=>({...link,role:'counter'}))];
      for(const child of node.children)links.push(...child.support.map(link=>({...link,role:'support'})));
      const shots=links.slice(0,6).map(link=>{const row=state.instances.get(key(link.session_id,link.instance_id));if(!row)return '';
        const at=row.frame_at??row.refers_start??row.said_start;
        return `<div class="shot">${thumb(row.session_id,at,label(row)+' · '+formatTime(at))}<p>${link.role==='counter'?'<span class="badge">反例</span> ':''}<strong>${escape(KIND[row.kind]||row.kind)}</strong> ${escape(label(row))} ${jump(row.session_id,at,formatTime(at))}</p><p>${escape(row.statement.slice(0,80))}${row.statement.length>80?'…':''}</p></div>`;}).join('');
      return `<article class="proposal" data-issue-id="${escape(node.id)}"><h3>${escape(node.title)} <span class="count">${escape(countText(node))}</span><span class="code">${escape(node.id)}</span></h3>`+
        `${parent?`<p class="hint">属于“${escape(parent.title)}”</p>`:''}${node.description?`<p class="desc">${escape(node.description)}</p>`:''}<div class="shots">${shots}</div>`+
        `${links.length>6?`<p class="hint">另有 ${links.length-6} 条证据，可在“证据”页签里查看。</p>`:''}`+
        `<div class="actions"><button type="button" data-issue-action="confirm">确认</button><button type="button" data-issue-action="title">改标题</button><button type="button" data-issue-action="merge">并入其他议题</button><button type="button" data-issue-action="dismiss">驳回</button><button type="button" data-issue-action="skip">暂不处理</button></div></article>`;
    }).join('');
    document.querySelectorAll('#issueList .thumb[data-session]').forEach(button=>thumbObserver.observe(button));
  }
  async function issueAction(article,action){
    const id=article.dataset.issueId,node=state.issues.get(id);
    if(action==='skip'){state.hiddenIssues.add(id);renderCandidates();return;}
    if(action==='confirm'){await call('update_issue',{id,status:'confirmed'});status(`已确认 ${id}。`);await load();return;}
    if(action==='dismiss'){
      const button=article.querySelector('[data-issue-action="dismiss"]');
      if(!button.dataset.armed){button.dataset.armed='1';button.textContent='再点一次驳回（移除这个候选和它的证据对应）';return;}
      await call('dismiss_issue',id);status(`已驳回 ${id}。`);await load();return;
    }
    const actions=article.querySelector('.actions');
    if(action==='title'){
      actions.innerHTML=`<form><label class="sr-only" for="issueTitle">新标题</label><input id="issueTitle" name="title" required value="${escape(node.title)}"><button type="submit">保存标题</button><button type="button" data-issue-action="cancel">取消</button></form>`;
    }else{
      const descendants=new Set([id,...node.children.map(child=>child.id)]);
      const options=[...state.issues.values()].filter(other=>!descendants.has(other.id)&&other.id!=='BUG');
      actions.innerHTML=`<form><label class="sr-only" for="mergeInto">并入的议题</label><input id="mergeInto" name="into" list="issueOptions" required placeholder="搜索议题编号或标题"><datalist id="issueOptions">${options.map(other=>`<option value="${escape(other.id)}">${escape(other.title)}</option>`).join('')}</datalist><button type="submit">确认并入</button><button type="button" data-issue-action="cancel">取消</button></form>`;
    }
    const form=actions.querySelector('form');form.querySelector('input').focus();
    form.onsubmit=async event=>{
      event.preventDefault();const data=new FormData(form);
      try{
        if(action==='title'){await call('update_issue',{id,title:String(data.get('title')).trim()});status(`已修改 ${id} 的标题。`);}
        else{const into=String(data.get('into')).trim();await call('merge_issue',id,into);status(`已把 ${id} 并入 ${into}，证据一起移过去了。`);}
        await load();
      }catch(error){status(error.message,true);}
    };
  }
  async function confirmAll(){
    const button=$('confirmAll'),found=candidates();
    if(!button.dataset.armed){button.dataset.armed='1';button.textContent=`再点一次，确认全部 ${found.length} 个`;return;}
    for(const {node} of found)await call('update_issue',{id:node.id,status:'confirmed'});
    status(`已确认 ${found.length} 个议题。`);await load();
  }
  async function openReport(name){
    state.report=name?await call('read_report',name):null;
    renderReport();renderEvidence();
  }
  async function load(){
    status('正在读取资料库…');
    try{
      const overview=await call('get_overview');
      state.overview=overview;state.labels=overview.session_labels;state.reports=overview.reports;
      state.instances=new Map(overview.instances.map(row=>[key(row.session_id,row.instance_id),row]));
      $('title').textContent='洞察 · '+overview.vault;document.title=$('title').textContent;
      const previous=$('reportSelect').value;
      $('reportSelect').innerHTML=overview.reports.length?overview.reports.map(row=>`<option value="${escape(row.name)}">${escape(row.name)}</option>`).join(''):'<option value="">（没有报告）</option>';
      if(overview.reports.some(row=>row.name===previous))$('reportSelect').value=previous;
      renderEvidence();renderProposed();renderCandidates();
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
    if(button){setExpanded(button,button.getAttribute('aria-expanded')!=='true');return;}
    const issueButton=event.target.closest('[data-issue-action]');
    if(issueButton){
      if(issueButton.dataset.issueAction==='cancel')renderCandidates();
      else issueAction(issueButton.closest('.proposal'),issueButton.dataset.issueAction).catch(error=>status(error.message,true));
      return;
    }
    const proposal=event.target.closest('[data-proposal]');
    if(proposal){
      const article=proposal.closest('.proposal');
      if(proposal.dataset.proposal==='cancel')renderProposed();
      else proposalAction(article,proposal.dataset.proposal).catch(error=>status(error.message,true));
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
  $('expandAll').onclick=()=>document.querySelectorAll('#evidenceList .toggle').forEach(button=>setExpanded(button,true));
  $('collapseAll').onclick=()=>document.querySelectorAll('#evidenceList .toggle').forEach(button=>setExpanded(button,false));
  $('reportSelect').onchange=()=>openReport($('reportSelect').value).catch(error=>status(error.message,true));
  $('refresh').onclick=load;
  $('tabEvidence').onclick=()=>selectTab('evidence');
  $('tabProposed').onclick=()=>selectTab('proposed');
  $('tabIssues').onclick=()=>selectTab('issues');
  $('confirmAll').onclick=()=>confirmAll().catch(error=>status(error.message,true));

  function start(){
    if(api)return;
    api=window.pywebview.api;
    api.ready().catch(()=>{});
    load();
  }
  if(window.pywebview?.api)start();else window.addEventListener('pywebviewready',start);
})();
