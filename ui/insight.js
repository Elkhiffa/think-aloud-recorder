(()=>{
  'use strict';
  const $=id=>document.getElementById(id);
  const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const KIND={confusion:'困惑',obstacle:'阻碍',cost:'操作成本',positive:'正向体验',negative:'负面评价',expectation:'预期',suggestion:'建议',self_correction:'自我修正',observation:'观察'};
  const CONTEXT={hud:'HUD / 战斗 / 大世界',multi_screen:'跨多个界面',outside_game:'游戏外窗口',unknown:'认不出界面'};
  const state={overview:null,instances:new Map(),labels:{},reports:[],report:null,issues:new Map(),feedback:[],
    tags:[],tagGroups:[],instanceTags:{},filters:{kinds:new Set(),tags:new Set(),session:null,sessionLabel:''}};
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
  // Decoded frames are kept per session and time, so re-rendering after a filter shows covers at once.
  const thumbCache=new Map(),thumbKey=node=>node.dataset.session+'@'+node.dataset.time;
  function showThumb(node,src){const img=document.createElement('img');img.alt='所指时刻画面';img.src=src;node.replaceChildren(img);}
  const thumbObserver=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){thumbObserver.unobserve(entry.target);
    const cached=thumbCache.get(thumbKey(entry.target));cached?showThumb(entry.target,cached):(thumbQueue.push(entry.target),pumpThumbs());}},{rootMargin:'400px'});
  function pumpThumbs(){
    while(thumbActive<2&&thumbQueue.length){
      const button=thumbQueue.shift();
      if(!button.isConnected)continue;
      const cached=thumbCache.get(thumbKey(button));if(cached){showThumb(button,cached);continue;}
      thumbActive++;
      call('thumbnail',button.dataset.session,Number(button.dataset.time)).then(src=>{thumbCache.set(thumbKey(button),src);showThumb(button,src);}).catch(()=>{button.textContent='无画面';}).finally(()=>{thumbActive--;pumpThumbs();});
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
      `<h4 class="card-title"><span class="kind kind-${escape(row.kind)}">${escape(KIND[row.kind]||row.kind)}</span><span>${escape(row.event_title||'未归入事件')}</span>${counter?'<span class="badge">反例</span>':''}</h4>`+
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
  function flag(target){return `<button type="button" class="flag" data-flag="${escape(JSON.stringify(target))}" title="有问题？写一句怎么调" aria-label="有问题？写一句怎么调"><svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path d="M10.8 2.6a1.3 1.3 0 0 1 1.8 0l.8.8a1.3 1.3 0 0 1 0 1.8L6 12.6l-2.9.6.6-2.9z" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg></button>`;}
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
    let body=node.description?`<p class="desc">${describe(node.description,node.id)}</p>`:'';
    // 洞察 and 议题 levels list the busiest first; 子议题 keep the analyst's order.
    const children=level<=1?byCount(node.children):node.children;
    for(const child of children)body+=issueSection(child,level+1);
    const own=node.support.length+node.counter.length;
    if(own&&(node.children.length||level===1)){
      const name=node.children.length?'未归入下级':'证据';
      body+=`<section class="group level-${level+1}" id="issue-${escape(node.id)}-own" data-issue="${escape(node.id)}">${row('issue-'+node.id+'-own',name,node.children.length?`${own} 条`:'',false,level+1)}<div id="issue-${escape(node.id)}-own-body" hidden>${evidenceBlock(node)}</div></section>`;
    }else if(own)body+=evidenceBlock(node);
    let extra=0;
    if(node.id==='BUG'&&state.overview.bug_unorganized.length&&!filtering()){
      extra=state.overview.bug_unorganized.length;
      body+=`<section class="group level-2" id="issue-BUG-raw">${row('issue-BUG-raw','未整理的 bug 原话',`${extra} 处`,false,2)}<ul class="hits" id="issue-BUG-raw-body" hidden>`+
        state.overview.bug_unorganized.map(hit=>`<li>${jump(hit.session_id,hit.start,(state.labels[hit.session_id]||hit.session_id)+' '+formatTime(hit.start))}<span>“${escape(hit.text)}”${hit.state==='instance'?` <span class="badge">已是实例 ${escape(hit.instances.join('、'))}，未挂 BUG</span>`:''}</span></li>`).join('')+'</ul></section>';
    }
    if(!body)body='<p class="desc">暂无证据。</p>';
    const n=node.id==='BUG'&&extra?countText(node)+` · 未整理 ${extra}`:countText(node);
    return `<section class="${level===1?'issue':'group'} level-${level}" id="issue-${escape(node.id)}" data-issue="${escape(node.id)}">${row('issue-'+node.id,`${title}${status}`,n,level===1,level,node.id==='BUG'?'':node.id,{kind:'issue',id:node.id})}<div id="issue-${escape(node.id)}-body"${level===1?'':' hidden'}>${body}</div></section>`;
  }
  const total=node=>{const n=counts(node);return n.support+n.counter;};
  const byCount=nodes=>[...nodes].sort((a,b)=>total(b)-total(a));
  // Plain references inside agent-written descriptions become the same quiet marks as report citations.
  function describe(text,issue){
    let html=escape(text);
    html=html.replace(/(?<![\w.-])(TA-\d{2}[A-Z]?(?:\.\d{1,3}){0,2}|N-\d{3}(?:\.\d{1,3}){0,2}|BUG\.\d{1,3})(?![\w.])/g,
      (match,id)=>state.issues.has(id)?`<a class="cite" href="#" data-cite-issue="${id}">${id}</a>`:match);
    const sessions=new Map(Object.entries(state.labels).map(([session,name])=>[name,session]));
    html=html.replace(/(?<![\d·])(\d{4}(?:·\d{4})?) ?(i\d{1,3}(?:[、，, ]+i\d{1,3})*)/g,(match,name,ids)=>{
      const session=sessions.get(name);if(!session)return match;
      let first=true,found=false;
      const out=ids.replace(/i\d{1,3}/g,id=>{if(!state.instances.has(key(session,id)))return id;found=true;const text=first?`${name} ${id}`:id;first=false;
        return `<a class="cite" href="#" data-cite-instance="${session}/${id}" data-cite-in="${escape(issue)}">${text}</a>`;});
      return found?(first?name+' ':'')+out:match;
    });
    return html;
  }
  function orderedIssues(){
    // BUG is a fixed issue; keep it last so design issues lead. The rest go busiest first.
    const nodes=byCount(state.overview.issues.filter(node=>node.id!=='BUG'));
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
  // Filters: judgment kinds and screen-library tags narrow every level at once; empty branches hide.
  const filtering=()=>state.filters.kinds.size>0||state.filters.tags.size>0||!!state.filters.session;
  function passes(k,ignoreTags=false){
    const row=state.instances.get(k);if(!row)return false;
    if(state.filters.session&&row.session_id!==state.filters.session)return false;
    if(state.filters.kinds.size&&!state.filters.kinds.has(row.kind))return false;
    if(!ignoreTags&&state.filters.tags.size&&!(state.instanceTags[k]||[]).some(tag=>state.filters.tags.has(tag)))return false;
    return true;
  }
  function prune(node){
    const keep=link=>passes(key(link.session_id,link.instance_id));
    return {...node,support:node.support.filter(keep),counter:node.counter.filter(keep),children:node.children.map(prune).filter(child=>total(child))};
  }
  const tagName=id=>state.tags.find(tag=>tag.id===id)?.name||id;
  function renderKindBar(){
    const found=new Map(),seen=new Set();
    const walk=node=>{for(const link of node.support.concat(node.counter)){const k=key(link.session_id,link.instance_id);
      if(seen.has(k))continue;seen.add(k);
      const row=state.instances.get(k);if(!row)continue;
      if(state.filters.tags.size&&!(state.instanceTags[k]||[]).some(tag=>state.filters.tags.has(tag)))continue;
      found.set(row.kind,(found.get(row.kind)||0)+1);}node.children.forEach(walk);};
    state.overview.issues.forEach(walk);
    const kinds=Object.keys(KIND).filter(kind=>found.has(kind)||state.filters.kinds.has(kind));
    $('kindBar').innerHTML=kinds.map(kind=>`<button type="button" class="kind-chip kind-${kind}${state.filters.kinds.has(kind)?' active':''}" data-kind="${kind}" aria-pressed="${state.filters.kinds.has(kind)}">${escape(KIND[kind])} ${found.get(kind)||0}</button>`).join('')+
      (state.filters.kinds.size?'<button type="button" class="filter-clear" data-clear-kinds>清除类型</button>':'');
  }
  function renderFilterBar(){
    const chips=[...state.filters.tags].map(id=>`<button type="button" class="filter-chip" data-clear-tag="${escape(id)}" title="取消这个筛选">${escape(tagName(id))} ×</button>`);
    if(state.filters.session)chips.unshift(`<button type="button" class="filter-chip" data-clear-session title="取消这个筛选">只看 ${escape(state.filters.sessionLabel||state.filters.session)} ×</button>`);
    $('filterBar').hidden=!chips.length;
    $('filterBar').innerHTML=chips.length?`<span class="hint">正在看：</span>${chips.join('')}<button type="button" class="filter-clear" data-clear-all>清除全部</button>`:'';
  }
  function applyFilters(){renderKindBar();renderFilterBar();renderEvidence();renderLibrary();}
  // Open/folded state outlives sections a filter hides for a while; expand/collapse all starts it over.
  const openMemory=new Map();
  // The last thing clicked in each pane is the anchor: after a filter re-renders, it goes back to the same height
  // on screen; if it was filtered out, its nearest remaining ancestor takes its place.
  const anchors={evidence:null,library:null};
  const PANES={evidence:['evidenceList','evidencePane'],library:['libraryList','library']};
  function anchorOf(item){
    if(item.card)return document.querySelector(`#evidenceList .card[data-key="${CSS.escape(item.card)}"][data-issue="${CSS.escape(item.issue||'')}"]`)||document.querySelector(`#evidenceList .card[data-key="${CSS.escape(item.card)}"]`);
    if(item.tag)return document.querySelector(`#libraryList .tag-card[data-tag="${CSS.escape(item.tag)}"]`);
    return document.getElementById(item.id);
  }
  function remember(target){
    for(const [name,[list,pane]] of Object.entries(PANES)){
      if(!$(list).contains(target))continue;
      const chain=[];
      for(let node=target;node&&node!==$(list);node=node.parentElement){
        if(node.matches('.card[data-key]'))chain.push({card:node.dataset.key,issue:node.dataset.issue});
        else if(node.matches('.tag-card[data-tag]'))chain.push({tag:node.dataset.tag});
        else if(node.matches('section[id]'))chain.push({id:node.id});
      }
      if(chain.length)anchors[name]={chain};
    }
  }
  // Measured just before re-rendering, so scrolling after the click is respected.
  function anchorOffset(name){
    const anchor=anchors[name],pane=$(PANES[name][1]);
    for(const item of anchor?.chain||[]){const node=anchorOf(item);if(node&&node.getClientRects().length)return node.getBoundingClientRect().top-pane.getBoundingClientRect().top;}
    return null;
  }
  function relocate(name,offset){
    const anchor=anchors[name],pane=$(PANES[name][1]);
    if(!anchor||offset===null)return false;
    for(const item of anchor.chain){
      const node=anchorOf(item);
      if(node&&node.getClientRects().length){pane.scrollTop+=node.getBoundingClientRect().top-pane.getBoundingClientRect().top-offset;return true;}
    }
    return false;
  }
  function openStates(selector){for(const button of document.querySelectorAll(selector))openMemory.set(button.getAttribute('aria-controls'),button.getAttribute('aria-expanded')==='true');return openMemory;}
  function renderEvidence(){
    const opened=openStates('#evidenceList .toggle'),scroll=$('evidencePane').scrollTop,offset=anchorOffset('evidence');
    state.issues=new Map();
    const index=node=>{state.issues.set(node.id,node);node.children.forEach(index);};state.overview.issues.forEach(index);
    let nodes=orderedIssues();
    if(filtering())nodes=nodes.map(prune).filter(node=>total(node));
    let html=nodes.map(node=>issueSection(node)).join('');
    const extra=cited().filter(k=>passes(k));
    if(extra.length)html+=`<section class="issue level-1" id="issue-cited" data-issue="cited">${row('issue-cited','报告引用的其他证据',`${extra.length} 条`,true,1)}<div id="issue-cited-body"><div class="cards">${extra.map(k=>card(state.instances.get(k),null,'cited')).join('')}</div></div></section>`;
    $('evidenceList').innerHTML=html||(filtering()?'<p class="empty">没有符合当前筛选的证据。</p>':'<p class="empty">资料库里还没有议题。</p>');
    document.querySelectorAll('#evidenceList .toggle').forEach(button=>{const id=button.getAttribute('aria-controls');if(opened.has(id))setExpanded(button,opened.get(id));});
    $('evidencePane').scrollTop=scroll;relocate('evidence',offset);
    document.querySelectorAll('#evidenceList .thumb[data-session]').forEach(button=>thumbObserver.observe(button));
    measureRows();updateStuck();
  }

  // Sticky rows: the current 洞察 / 议题 / 子议题 stay on top while their cards scroll; the next
  // 议题 in this 洞察 and the next 洞察 wait at the bottom. Row heights feed the sticky offsets.
  function measureRows(){
    const pane=$('evidencePane');
    // A hidden pane measures 0; keep the last real height so sticky rows never stack on one line.
    for(const level of [1,2,3]){const row=document.querySelector(`#evidenceList .level-${level}>.row`);if(row?.offsetHeight)pane.style.setProperty('--r'+level,row.offsetHeight+'px');}
  }
  const sections=(parent,level)=>[...parent.querySelectorAll(`:scope>section.level-${level},:scope>div>section.level-${level}`)];
  // Before any heading has scrolled past the line, the first section is the current one.
  function current(list,line){let found=list.length?0:-1;list.forEach((section,i)=>{if(section.getBoundingClientRect().top<=line)found=i;});return found;}
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
    // Pinned heads are drawn like the rows themselves; clicking one goes there.
    bar.innerHTML=items.map(([section,level])=>{const toggle=section.querySelector(':scope>.row>.toggle');
      return `<div class="pin level-${level}${level>1?' nested':''}"><div class="row"><button type="button" class="toggle" data-next="${escape(section.id)}" aria-expanded="${toggle.getAttribute('aria-expanded')}">${toggle.innerHTML}</button></div></div>`;}).join('');
    bar.hidden=!items.length;
  }
  function scheduleStuck(){if(!stuckFrame)stuckFrame=requestAnimationFrame(updateStuck);}
  // Expanding or collapsing keeps the clicked head where it was on screen (same rules as ui/findings.js). When the
  // list is then too short for that, a temporary run-out after it holds the head: it can only be scrolled up, and
  // shrinks by as much as it is scrolled up until the list is its real height again.
  const runOuts=new Map();
  function setRunOut(pane,list,value){
    let node=list.nextElementSibling?.classList.contains('run-out')?list.nextElementSibling:null;
    if(!value||value.height<=0.5){node?.remove();runOuts.delete(pane);return;}
    if(!node){node=document.createElement('div');node.className='run-out';node.setAttribute('aria-hidden','true');list.after(node);}
    node.style.height=value.height+'px';runOuts.set(pane,{...value,list});
  }
  function keepHead(pane,list,button,change){
    const before=button.getBoundingClientRect().top;change();
    const desired=pane.scrollTop+button.getBoundingClientRect().top-before,max=pane.scrollHeight-pane.clientHeight;
    setRunOut(pane,list,{height:(runOuts.get(pane)?.height||0)+desired-max,at:desired});
    pane.scrollTop=desired;const held=runOuts.get(pane);if(held)held.at=pane.scrollTop;
  }
  function shrinkRunOut(pane){const held=runOuts.get(pane);if(!held||pane.scrollTop>=held.at)return;setRunOut(pane,held.list,{height:held.height-(held.at-pane.scrollTop),at:pane.scrollTop});}
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
    if(!$('issue-'+id)&&filtering()){clearFilters();status('已清除筛选，以便定位这条引用。');}
    const section=revealSection(id);
    if(!section){status('右栏没有这个议题：'+id,true);return;}
    section.scrollIntoView({block:'start',behavior:'smooth'});
  }
  function goToInstance(sessionId,instanceId,issue){
    showEvidenceTab();
    const k=key(sessionId,instanceId);
    if(filtering()&&!document.querySelector(`#evidenceList .card[data-key="${CSS.escape(k)}"]`)){clearFilters();status('已清除筛选，以便定位这条引用。');}
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
    if(missing)status(`报告里有 ${missing} 条引用在资料库中找不到，已标为“找不到”。`,true);
  }

  function clearFilters(){state.filters.kinds.clear();state.filters.tags.clear();state.filters.session=null;state.filters.sessionLabel='';applyFilters();}

  // Screen library: tag dimensions are collapsible headings; tags are cover-on-top cards that filter the tree.
  function treeKeys(){
    const keys=[];const seen=new Set();
    const walk=node=>{for(const link of node.support.concat(node.counter)){const k=key(link.session_id,link.instance_id);if(!seen.has(k)&&passes(k,true)){seen.add(k);keys.push(k);}}node.children.forEach(walk);};
    orderedIssues().forEach(walk);
    return keys;
  }
  function renderLibrary(){
    if(!state.overview)return;
    if(!state.tags.length){$('libraryList').innerHTML='<p class="empty">资料库还没有系统 / 玩法标签。跨场次分析 agent 建好标签（tags.json）后点“刷新”。</p>';scheduleLibStuck();return;}
    const opened=openStates('#libraryList .lib-toggle'),scroll=$('library').scrollTop,offset=anchorOffset('library');
    const keys=treeKeys();
    const byTag=new Map(state.tags.map(tag=>[tag.id,[]]));
    for(const k of keys)for(const tag of state.instanceTags[k]||[])byTag.get(tag)?.push(k);
    $('libraryList').innerHTML=state.tagGroups.map(group=>{
      const tags=state.tags.filter(tag=>tag.group===group.id).sort((a,b)=>byTag.get(b.id).length-byTag.get(a.id).length);
      const n=new Set(tags.flatMap(tag=>byTag.get(tag.id))).size;
      const cards=tags.map(tag=>{
        const hits=byTag.get(tag.id),row=state.instances.get(hits.find(k=>Number.isFinite(state.instances.get(k)?.frame_at??state.instances.get(k)?.refers_start))||'');
        const cover=tag.cover||(row?{session_id:row.session_id,at:row.frame_at??row.refers_start}:null);
        const image=cover?`<span class="thumb cover" data-session="${escape(cover.session_id)}" data-time="${cover.at}" data-caption="${escape(tag.name)}"></span>`:'<span class="cover empty-cover"></span>';
        return `<article class="tag-card${state.filters.tags.has(tag.id)?' active':''}${hits.length?'':' none'}" data-tag="${escape(tag.id)}" tabindex="0" role="button" aria-pressed="${state.filters.tags.has(tag.id)}">${image}<div class="tag-meta"><span class="tag-name" title="${escape(tag.name)}">${escape(tag.name)}</span><span class="n">${hits.length}</span>${flag({kind:'tag',id:tag.id})}</div></article>`;
      }).join('');
      return `<section class="lib-group" id="libgroup-${escape(group.id)}" data-name="${escape(group.name)}" data-count="${n}"><button type="button" class="lib-toggle" aria-expanded="true" aria-controls="lib-${escape(group.id)}"><span>${escape(group.name)}</span><span class="n">${n} 条</span></button><div class="lib-grid" id="lib-${escape(group.id)}">${cards}</div></section>`;
    }).join('');
    document.querySelectorAll('#libraryList .lib-toggle').forEach(button=>{const id=button.getAttribute('aria-controls');
      if(opened.has(id)&&!opened.get(id)){button.setAttribute('aria-expanded','false');$(id).hidden=true;}});
    $('library').scrollTop=scroll;relocate('library',offset);
    document.querySelectorAll('#library .thumb[data-session]').forEach(node=>thumbObserver.observe(node));
    scheduleLibStuck();
  }
  // Like the evidence tree: the current dimension heading sticks on top, the next one waits at the bottom.
  let libFrame=0;
  function updateLibStuck(){
    libFrame=0;
    const pane=$('library'),bar=$('libNext');
    if(pane.hidden){bar.hidden=true;return;}
    const box=pane.getBoundingClientRect(),groups=[...document.querySelectorAll('#libraryList .lib-group')];
    const i=current(groups,box.top+4),next=groups[i+1]||(i<0?groups[0]:null);
    const bottom=box.bottom-(bar.hidden?0:bar.offsetHeight);
    if(next&&next.getBoundingClientRect().top>bottom-4){
      const toggle=next.querySelector('.lib-toggle');
      bar.innerHTML=`<div class="lib-group pin"><button type="button" class="lib-toggle" data-lib-next="${escape(next.id)}" aria-expanded="${toggle.getAttribute('aria-expanded')}">${toggle.innerHTML}</button></div>`;
      bar.hidden=false;
    }else bar.hidden=true;
  }
  function scheduleLibStuck(){if(!libFrame)libFrame=requestAnimationFrame(updateLibStuck);}
  function selectLeft(name){
    for(const [tab,pane,id] of [['tabReport','report','report'],['tabLibrary','library','library']]){
      $(tab).setAttribute('aria-selected',String(id===name));$(pane).hidden=id!==name;
    }
    document.querySelector('.report-choice').hidden=name!=='report';
    scheduleLibStuck();
  }
  function openMenu(card,x,y){
    const row=state.instances.get(card.dataset.key);if(!row)return;
    const at=row.frame_at??row.refers_start??row.said_start,tags=state.instanceTags[card.dataset.key]||[];
    $('menu').innerHTML=tags.length?tags.map(tag=>`<button type="button" role="menuitem" data-cover-tag="${escape(tag)}" data-cover-session="${escape(row.session_id)}" data-cover-at="${at}">设为「${escape(tagName(tag))}」封面</button>`).join('')
      :'<button type="button" role="menuitem" disabled>设为封面（这条证据没有界面库标签）</button>';
    $('menu').hidden=false;
    const box=$('menu').getBoundingClientRect();
    $('menu').style.left=Math.min(x,innerWidth-box.width-8)+'px';$('menu').style.top=Math.min(y,innerHeight-box.height-8)+'px';
    $('menu').querySelector('button:not([disabled])')?.focus();
  }
  function selectTab(name){
    $('treeActions').hidden=name!=='evidence';
    for(const [tab,pane,id] of [['tabEvidence','evidencePane','evidence'],['tabFeedback','feedbackPane','feedback']]){
      $(tab).setAttribute('aria-selected',String(id===name));$(pane).hidden=id!==name;
    }
    measureRows();scheduleStuck();
  }

  // Feedback: agent output is accepted by default; the user only marks what is wrong and how to adjust it.
  function targetName(target){
    if(target.kind==='issue')return issueName(target.id);
    const row=state.instances.get(key(target.session_id,target.instance_id));
    const where=target.issue?`（在“${issueName(target.issue)}”下）`:'';
    return row?`${KIND[row.kind]||row.kind} · ${row.event_title||'未归入事件'} ${label(row)}${where}`:`${target.session_id} ${target.instance_id}${where}`;
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
      state.tags=overview.tags||[];state.tagGroups=overview.tag_groups||[];state.instanceTags=overview.instance_tags||{};
      for(const id of [...state.filters.tags])if(!state.tags.some(tag=>tag.id===id))state.filters.tags.delete(id);
      state.instances=new Map(overview.instances.map(row=>[key(row.session_id,row.instance_id),row]));
      $('title').textContent='洞察 · '+overview.vault;document.title=$('title').textContent;
      const previous=$('reportSelect').value;
      $('reportSelect').innerHTML=overview.reports.length?overview.reports.map(row=>`<option value="${escape(row.name)}">${escape(row.name)}</option>`).join(''):'<option value="">（没有报告）</option>';
      if(overview.reports.some(row=>row.name===previous))$('reportSelect').value=previous;
      renderKindBar();renderFilterBar();renderEvidence();renderFeedback();renderLibrary();
      await openReport($('reportSelect').value);
      if(!state.report||!state.report.citations.some(row=>!row.resolved))status('');
    }catch(error){status(error.message,true);}
  }

  document.addEventListener('click',event=>remember(event.target),true);
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
    const button=event.target.closest('.toggle:not([data-next])');
    if(button){
      const expanded=button.getAttribute('aria-expanded')!=='true';
      keepHead($('evidencePane'),$('evidenceList'),button,()=>setExpanded(button,expanded));
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
    const coverItem=event.target.closest('[data-cover-tag]');
    if(coverItem){
      $('menu').hidden=true;
      call('set_cover',coverItem.dataset.coverTag,coverItem.dataset.coverSession,Number(coverItem.dataset.coverAt))
        .then(tags=>{state.tags=tags;renderLibrary();status(`已把这张画面设为「${tagName(coverItem.dataset.coverTag)}」的封面。`);}).catch(error=>status(error.message,true));
      return;
    }
    if(!event.target.closest('#menu'))$('menu').hidden=true;
    const libToggle=event.target.closest('.lib-toggle:not([data-lib-next])');
    if(libToggle){
      const open=libToggle.getAttribute('aria-expanded')!=='true';
      keepHead($('library'),$('libraryList'),libToggle,()=>{libToggle.setAttribute('aria-expanded',String(open));$(libToggle.getAttribute('aria-controls')).hidden=!open;});
      scheduleLibStuck();return;
    }
    const libNext=event.target.closest('[data-lib-next]');
    if(libNext){
      const group=$(libNext.dataset.libNext),toggle=group.querySelector('.lib-toggle');
      if(toggle.getAttribute('aria-expanded')!=='true'){toggle.setAttribute('aria-expanded','true');$(toggle.getAttribute('aria-controls')).hidden=false;}
      group.scrollIntoView({block:'start',behavior:'smooth'});return;
    }
    const tagCard=event.target.closest('[data-tag]');
    if(tagCard){const id=tagCard.dataset.tag;state.filters.tags.has(id)?state.filters.tags.delete(id):state.filters.tags.add(id);applyFilters();return;}
    const kindChip=event.target.closest('[data-kind]');
    if(kindChip){const kind=kindChip.dataset.kind;state.filters.kinds.has(kind)?state.filters.kinds.delete(kind):state.filters.kinds.add(kind);applyFilters();return;}
    const clear=event.target.closest('[data-clear-tag],[data-clear-kind],[data-clear-kinds],[data-clear-all],[data-clear-session]');
    if(clear){
      if(clear.hasAttribute('data-clear-all'))clearFilters();
      else if(clear.hasAttribute('data-clear-session')){state.filters.session=null;state.filters.sessionLabel='';applyFilters();}
      else if(clear.hasAttribute('data-clear-kinds')){state.filters.kinds.clear();applyFilters();}
      else{clear.dataset.clearTag?state.filters.tags.delete(clear.dataset.clearTag):state.filters.kinds.delete(clear.dataset.clearKind);applyFilters();}
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
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'){$('lightbox').hidden=true;$('menu').hidden=true;}
    if((event.key==='Enter'||event.key===' ')&&event.target.matches?.('[data-tag]')){event.preventDefault();event.target.click();}
  });
  document.addEventListener('contextmenu',event=>{
    const card=event.target.closest('#evidenceList .card');
    if(!card)return;
    event.preventDefault();openMenu(card,event.clientX,event.clientY);
  });
  // Cards and sections scroll to just below the sticky outline, whatever its current height.
  new ResizeObserver(()=>$('evidencePane').style.setProperty('--head',document.querySelector('.evidence-head').offsetHeight-16+'px')).observe(document.querySelector('.evidence-head'));
  $('expandAll').onclick=()=>{openMemory.clear();document.querySelectorAll('#evidenceList .toggle').forEach(button=>setExpanded(button,true));scheduleStuck();};
  $('collapseAll').onclick=()=>{openMemory.clear();document.querySelectorAll('#evidenceList .toggle').forEach(button=>setExpanded(button,false));setRunOut($('evidencePane'),$('evidenceList'),null);$('evidencePane').scrollTop=0;scheduleStuck();};
  $('evidencePane').addEventListener('scroll',()=>{shrinkRunOut($('evidencePane'));scheduleStuck();},{passive:true});
  $('library').addEventListener('scroll',()=>{shrinkRunOut($('library'));scheduleLibStuck();},{passive:true});
  new ResizeObserver(()=>{measureRows();scheduleStuck();}).observe($('evidencePane'));
  $('reportSelect').onchange=()=>openReport($('reportSelect').value).catch(error=>status(error.message,true));
  $('refresh').onclick=load;
  $('tabEvidence').onclick=()=>selectTab('evidence');
  $('tabFeedback').onclick=()=>selectTab('feedback');
  $('tabReport').onclick=()=>selectLeft('report');
  $('tabLibrary').onclick=()=>selectLeft('library');

  function start(){
    if(api)return;
    api=window.pywebview.api;
    api.ready().catch(()=>{});
    load();
  }
  // The desk window's 场次 tab jumps here: reveal an insight, or show only one session's evidence.
  window.insightBridge={goToIssue,showSession(id,label){state.filters.session=id;state.filters.sessionLabel=label||'';showEvidenceTab();applyFilters();},reload:load};
  if(window.pywebview?.api)start();else window.addEventListener('pywebviewready',start);
})();
