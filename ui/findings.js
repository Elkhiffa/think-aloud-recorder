'use strict';
/* 回看与资料台共用的整理结果视图：按问题类型筛选，「问题」按类型分组，「体验事件」每个事件一段。
   Bug 是和类型并列的一组（设计没问题、实现出了问题）：一条判断仍有自己的类型，是 bug 时两组都列出。
   调用方持有状态并决定点击去向（回看原地跳转，资料台打开回看）；这里只负责画和接点击。 */
(function(root){
  const PROBLEM={confusion:'困惑',obstacle:'阻碍',cost:'操作成本',negative:'负面评价'};
  const OTHER={expectation:'预期',suggestion:'建议',positive:'正向体验',observation:'观察',self_correction:'自我修正'};
  const LABEL={...PROBLEM,...OTHER};
  const GROUPS=[...Object.keys(PROBLEM),'bug','other'];
  const GROUP_LABEL={...PROBLEM,bug:'Bug',other:'其他'};
  const BUG_LABEL={explicit:'Bug',suspected:'疑似 Bug'};
  const CHEV='<svg class="fd-chev" viewBox="0 0 10 6" aria-hidden="true"><path d="M0 0h10L5 6z"/></svg>';
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const groupOf=kind=>kind in PROBLEM?kind:'other';
  const isVersion2=result=>Array.isArray(result?.instances);
  // One scroll listener per scroller; the desk re-creates the view on every detail render.
  const SCROLLERS=new WeakMap();

  // bugs: instance id -> 'explicit' | 'suspected', from the result and the library's BUG links.
  function model(result,activities,bugs){
    const events=[...(result?.events||[])].sort((a,b)=>a.start-b.start||a.end-b.end);
    const eventById=new Map(events.map(event=>[event.id,event]));
    const tags=new Map(events.map(event=>[event.id,[]]));
    for(const activity of activities||[])for(const id of activity.event_ids||[])if(tags.has(id)&&!tags.get(id).includes(activity.name))tags.get(id).push(activity.name);
    const items=(result?.instances||[]).map(item=>{
      const said=[...(item.said||[])].sort((a,b)=>a.start-b.start);
      return {id:item.id,kind:item.kind,group:groupOf(item.kind),at:said[0]?.start??item.refers_to?.start??0,
        quote:said.map(ref=>ref.text).filter(Boolean).join(' … '),statement:item.statement||'',screen:item.screen||'',
        refers:item.refers_to||null,compare:item.compare_to||null,event:item.event_id,bug:bugs?.[item.id]||item.bug||null};
    }).sort((a,b)=>a.at-b.at);
    return {events,eventById,tags,items};
  }
  const inGroup=(item,group)=>group==='bug'?!!item.bug:item.group===group;
  function counts(items){const value=Object.fromEntries(GROUPS.map(group=>[group,0]));for(const item of items){value[item.group]++;if(item.bug)value.bug++;}return value;}
  // Sizes go through CSSOM: the desk's content policy forbids inline style attributes.
  function sizeBars(container){container.querySelectorAll('[data-flex]').forEach(el=>{el.style.flex=el.dataset.flex;});}
  function bar(count){const present=Object.keys(PROBLEM).filter(kind=>count[kind]);return present.length?`<span class="fd-fp" aria-hidden="true">${present.map(kind=>`<i class="k-${kind}" data-flex="${count[kind]}"></i>`).join('')}</span>`:'<span class="fd-fp is-empty" aria-hidden="true"></span>';}
  function legend(count){const parts=Object.keys(PROBLEM).filter(kind=>count[kind]).map(kind=>`<span class="k-${kind}"><b>${count[kind]}</b> ${PROBLEM[kind]}</span>`);if(count.bug)parts.push(`<span class="k-bug"><b>${count.bug}</b> Bug</span>`);if(count.other)parts.push(`<span class="k-other"><b>${count.other}</b> 其他</span>`);return parts.length?parts.join(''):'<span>没有整理出判断</span>';}

  function create(container,options={}){
    const clock=options.clock||(seconds=>String(Math.round(seconds)));
    const state=options.state||{};
    state.view=state.view||'problems';state.filter=state.filter||new Set();state.activity=state.activity||'';
    state.open=state.open||new Set();state.folded=state.folded||new Set();state.auto=state.auto??null;state.current=state.current??null;
    container.classList.add('findings');
    let data=null,view=null;

    const visible=item=>(!state.filter.size||[...state.filter].some(group=>inGroup(item,group)))&&(!state.activity||view.tags.get(item.event)?.includes(state.activity));
    const timeButton=(time,label,extra='')=>`<button type="button" class="fd-jump" data-seek="${time}"${extra}>${escape(label)}</button>`;
    function row(item,{showEvent,group}){
      const event=view.eventById.get(item.event),refers=item.refers;
      const referred=!refers?'':refers.basis==='earlier_session'?`<span title="${escape(refers.note||'')}">指本场之前</span>`:
        (Math.abs(refers.start-item.at)<1&&Math.abs((refers.end??refers.start)-item.at)<8)?'':timeButton(refers.start,`指 ${clock(refers.start)}–${clock(refers.end??refers.start)}`,` data-event="${escape(item.event)}"`);
      const compared=item.compare?timeButton(item.compare.start,`对照 ${clock(item.compare.start)}`,` data-event="${escape(item.event)}"`):'';
      // In the Bug group each row names its own kind; elsewhere a bug carries a small mark.
      const badge=item.bug&&group!=='bug'?`<span class="fd-bug-mark${item.bug==='suspected'?' is-suspected':''}">${BUG_LABEL[item.bug]}</span>`:'';
      const kind=group==='other'||group==='bug'?`<span class="fd-kind">${escape(LABEL[item.kind]||item.kind)}${group==='bug'&&item.bug==='suspected'?' · 疑似':''}</span>`:'';
      const meta=[kind,badge,item.screen?`<span class="fd-screen">${escape(item.screen)}</span>`:'',referred,compared,
        showEvent&&event?`<button type="button" class="fd-event-link" data-goto-event="${escape(event.id)}" title="在「体验事件」里查看这一段">${escape(event.title)}</button>`:''].filter(Boolean).join('');
      return `<li class="fd-row k-${group}" data-item="${escape(item.id)}"><button type="button" class="fd-at" data-seek="${item.at}" data-event="${escape(item.event)}" title="定位到说出口的时刻">${clock(item.at)}</button>`+
        `<div class="fd-main">${item.quote?`<p class="fd-quote">${escape(item.quote)}</p>`:''}<p class="fd-stmt">${escape(item.statement)}</p>${meta?`<p class="fd-meta">${meta}</p>`:''}</div></li>`;
    }
    function groups(items,{showEvent,prefix}){
      return GROUPS.map(group=>{const rows=items.filter(item=>inGroup(item,group));if(!rows.length)return '';const key=prefix+group,folded=state.folded.has(key);
        return `<section class="fd-group k-${group}"><button type="button" class="fd-gh" data-fold="${escape(key)}" aria-expanded="${!folded}"><span class="fd-name">${GROUP_LABEL[group]}</span><small>${rows.length}</small><span class="fd-sp"></span>${CHEV}</button>`+
          `<ul class="fd-rows"${folded?' hidden':''}>${rows.map(item=>row(item,{showEvent,group})).join('')}</ul></section>`;}).join('');
    }
    function filterBar(scope){
      const count=counts(scope);
      const chips=GROUPS.filter(group=>count[group]||state.filter.has(group)).map(group=>`<button type="button" class="fd-chip k-${group}" data-filter="${group}" aria-pressed="${state.filter.has(group)}">${GROUP_LABEL[group]} <b>${count[group]}</b></button>`).join('');
      const activity=state.activity?`<button type="button" class="fd-chip fd-activity-chip" data-clear-activity title="取消活动筛选">活动：${escape(state.activity)} <span aria-hidden="true">×</span></button>`:'';
      return `<div class="fd-bar" role="group" aria-label="按问题类型筛选">${chips}${activity}</div>`;
    }
    function coverage(result){
      const c=result.coverage;if(!c)return '';const scope={full:'全部',partial:'部分',none:'未检查'};
      return `<details class="fd-coverage"><summary>查看整理范围与资料限制</summary><p>画面检查：${c.video_ranges?.length?c.video_ranges.map(r=>`${clock(r.start)}${r.end>r.start?'–'+clock(r.end):''}`).join('、'):'未检查'}</p><p>原话：${scope[c.transcript]||'未检查'}；操作：${scope[c.inputs]||'未检查'}</p>${(c.limitations||[]).map(text=>`<p>${escape(text)}</p>`).join('')}</details>`;
    }
    function section(event,items){
      const open=state.open.has(event.id),own=items.filter(item=>item.event===event.id),count=counts(own),tags=view.tags.get(event.id)||[];
      const parts=String(event.summary||'').split(/(?:^|\n)\s*备注[：:]\s*/),summary=parts[0].trim();
      const extra=open?[event.issue?`<p class="fd-issue"><strong>问题与感受</strong>${escape(event.issue)}</p>`:'',[...parts.slice(1),event.notes].filter(Boolean).length?`<p class="fd-notes">备注：${escape([...parts.slice(1),event.notes].filter(Boolean).join('\n'))}</p>`:''].join(''):'';
      const edit=options.editable?.()?`<button type="button" class="fd-edit" data-edit="${escape(event.id)}" aria-label="校准这个体验事件">校准</button>`:'';
      return `<section class="fd-sec${open?' is-open':''}${state.current===event.id?' is-current':''}" data-sec="${escape(event.id)}">`+
        `<div class="fd-sh"><button type="button" class="fd-toggle" data-toggle="${escape(event.id)}" aria-expanded="${open}">${CHEV}<span class="fd-title">${escape(event.title)}</span></button>${edit}</div>`+
        `<div class="fd-sm">${timeButton(event.start,`${clock(event.start)}–${clock(event.end)}`,` data-event="${escape(event.id)}" data-section-time`)}${bar(count)}<span class="fd-legend">${legend(count)}</span>${event.manually_edited?'<span class="fd-edited">已校准</span>':''}</div>`+
        (summary?`<p class="fd-sum">${escape(summary)}</p>`:'')+
        (tags.length?`<div class="fd-tags">${tags.map(name=>`<button type="button" class="fd-tag${state.activity===name?' on':''}" data-activity="${escape(name)}" title="只看带这个活动的事件">${escape(name)}</button>`).join('')}</div>`:'')+
        `<div class="fd-body"${open?'':' hidden'}>${extra}${own.length?groups(own.filter(visible),{showEvent:false,prefix:event.id+':'}):'<p class="fd-empty">这一段没有整理出判断。</p>'}</div></section>`;
    }
    const scroller=options.scroller||container;
    function render(){
      if(!data){container.replaceChildren();return;}
      const scopeItems=view.items.filter(item=>!state.activity||view.tags.get(item.event)?.includes(state.activity));
      const items=scopeItems.filter(visible),filtered=state.filter.size>0||!!state.activity;
      let body='';
      if(state.view==='problems'){
        body=items.length?groups(items,{showEvent:true,prefix:''}):`<p class="fd-empty">${view.items.length?'没有符合筛选的判断。':'这一场没有整理出判断。'}</p>`;
      }else{
        const events=view.events.filter(event=>(!state.activity||view.tags.get(event.id)?.includes(state.activity))&&(!state.filter.size||items.some(item=>item.event===event.id)));
        body=coverage(data.result)+(events.length?events.map(event=>section(event,items)).join(''):`<p class="fd-empty">${view.events.length?'没有符合筛选的体验事件。':'这一场没有整理出体验事件。'}</p>`);
      }
      container.innerHTML=filterBar(scopeItems)+(filtered&&state.view==='problems'&&items.length?`<p class="fd-count">${items.length} 条</p>`:'')+`<div class="fd-view">${body}<div class="fd-next" hidden></div></div>`;
      sizeBars(container);applySpacer();measure();updateStuck();
    }
    // Scroll a section's head (or a group's head) to just under the sticky heads above it.
    function reveal(id){revealNode(container.querySelector(`[data-sec="${CSS.escape(id)}"]`));}
    function revealNode(node){if(!node)return;const bar=container.querySelector('.fd-bar'),section=node.matches('.fd-group')?node.closest('.fd-sec'):null;
      const above=(bar?.offsetHeight||0)+(section?section.querySelector('.fd-sh')?.offsetHeight||0:0);
      scroller.scrollTop+=node.getBoundingClientRect().top-scroller.getBoundingClientRect().top-above;updateStuck();}
    // Long sections and groups, as in the insight outline: the open section's head, and under it the head of the
    // problem type being read, stick below the filter bar (CSS). Heads of the next problem type and the next
    // section that are out of view wait at the bottom, drawn like the heads themselves. The scroller's padding is
    // where sticky boxes would otherwise stop, letting rows show above the bar; the offsets cancel it.
    function measure(){
      if(!scroller.isConnected&&scroller!==container)return;
      const style=root.getComputedStyle?.(scroller),bar=container.querySelector('.fd-bar');
      container.style.setProperty?.('--fd-pad-top',(parseFloat(style?.paddingTop)||0)+'px');
      container.style.setProperty?.('--fd-pad-bottom',(parseFloat(style?.paddingBottom)||0)+'px');
      if(bar?.offsetHeight)container.style.setProperty?.('--fd-bar-h',bar.offsetHeight+'px');
      container.querySelectorAll('.fd-sec.is-open').forEach(section=>{const head=section.querySelector('.fd-sh');if(head?.offsetHeight)section.style.setProperty('--fd-sh-h',head.offsetHeight+'px');});
    }
    const top=node=>node.getBoundingClientRect().top;
    // The last of `list` whose head has reached `line`, and the first one still below it.
    function around(list,line){let i=-1;list.forEach((node,k)=>{if(top(node)<=line)i=k;});return [list[i],list[i+1]];}
    const groupOpen=group=>!group.querySelector('.fd-rows')?.hidden;
    function pinSection(section){return `<div class="fd-sec fd-pin"><div class="fd-sh"><button type="button" class="fd-toggle" data-next="sec:${escape(section.dataset.sec)}" aria-expanded="false" title="跳到这个体验事件">${CHEV}<span class="fd-title">${escape(section.querySelector('.fd-title')?.textContent||'')}</span></button></div></div>`;}
    function pinGroup(group){const head=group.querySelector('.fd-gh');return `<div class="${escape(group.className)} fd-pin${group.closest('.fd-body')?' fd-nested':''}"><button type="button" class="fd-gh" data-next="grp:${escape(head.dataset.fold)}" aria-expanded="${groupOpen(group)}" title="跳到这一类">${head.innerHTML}</button></div>`;}
    function updateStuck(){
      const pins=container.querySelector('.fd-next'),bar=container.querySelector('.fd-bar');if(!pins||!bar?.getBoundingClientRect)return;
      const line=bar.getBoundingClientRect().bottom+2,bottom=Math.min(scroller.getBoundingClientRect().bottom,root.innerHeight||Infinity);
      container.querySelectorAll('.is-stuck').forEach(node=>node.classList.remove('is-stuck'));
      const candidates=[];
      if(state.view==='events'){
        const [section,nextSection]=around([...container.querySelectorAll('.fd-view>.fd-sec')],line);
        if(section?.classList.contains('is-open')){
          if(top(section)<line-4)section.classList.add('is-stuck');
          const groups=[...section.querySelectorAll('.fd-body>.fd-group')],[,nextGroup]=around(groups,line+(section.querySelector('.fd-sh')?.offsetHeight||0));
          if(nextGroup)candidates.push([nextGroup,pinGroup]);
          if(nextSection)candidates.push([nextSection,pinSection]);
        }
      }else{
        const [group,nextGroup]=around([...container.querySelectorAll('.fd-view>.fd-group')],line);
        if(group&&groupOpen(group)&&nextGroup)candidates.push([nextGroup,pinGroup]);
      }
      // A head is pinned only while it is hidden behind the pins or below the view; measure once with all, once with the kept ones.
      let shown=candidates;
      for(let pass=0;pass<2;pass++){
        const markup=shown.map(([node,draw])=>draw(node)).join('');if(pins.dataset.markup!==markup){pins.dataset.markup=markup;pins.innerHTML=markup;}
        pins.hidden=!shown.length;const limit=bottom-(pins.offsetHeight||0);
        const kept=candidates.filter(([node])=>top(node)>limit-2);if(kept.length===shown.length)break;shown=kept;
      }
      if(!shown.length){pins.hidden=true;pins.innerHTML='';pins.dataset.markup='';}
    }
    // Expanding or collapsing keeps the clicked head where it was on screen. When the list is then too short for
    // that (a stuck head collapsing near the end), a temporary run-out below the list holds it: it can only be
    // scrolled up, and shrinks by as much as it is scrolled up until the list is its real height again.
    let spacer=null;
    function applySpacer(){
      let node=container.querySelector(':scope>.fd-spacer');
      if(!spacer||spacer.height<=0){node?.remove();spacer=null;return;}
      if(!node){node=document.createElement('div');node.className='fd-spacer';node.setAttribute('aria-hidden','true');container.append(node);}
      node.style.height=spacer.height+'px';
    }
    function keepScroll(desired){
      const max=scroller.scrollHeight-scroller.clientHeight,current=spacer?.height||0;
      const height=Math.max(0,current+desired-max);spacer=height>0.5?{height,at:desired}:null;applySpacer();
      scroller.scrollTop=desired;if(spacer)spacer.at=scroller.scrollTop;
    }
    function shrinkSpacer(){
      if(!spacer||scroller.scrollTop>=spacer.at)return;
      spacer.height-=spacer.at-scroller.scrollTop;spacer.at=scroller.scrollTop;applySpacer();
    }
    function anchored(target,selector,change){
      const before=target.getBoundingClientRect().top;change();
      const node=container.querySelector(selector);if(node)keepScroll(scroller.scrollTop+node.getBoundingClientRect().top-before);
      updateStuck();
    }
    // playhead: review opened at this event, so it is also the section under the playhead.
    function openEvent(id,{scroll=true,playhead=false}={}){state.view='events';state.open.add(id);if(state.activity&&!view.tags.get(id)?.includes(state.activity))state.activity='';
      if(playhead){if(state.auto&&state.auto!==id)state.open.delete(state.auto);state.auto=null;state.current=id;}
      render();options.onView?.(state.view);if(scroll)reveal(id);}
    if(!SCROLLERS.has(scroller)){const run=()=>SCROLLERS.get(scroller)?.();scroller.addEventListener('scroll',run);root.addEventListener?.('resize',()=>{run();});}
    SCROLLERS.set(scroller,()=>{if(container.isConnected!==false){shrinkSpacer();measure();updateStuck();}});
    container.addEventListener('click',event=>{
      const target=event.target.closest('button');if(!target||!container.contains(target)||target.disabled)return;
      if(target.dataset.filter){const group=target.dataset.filter;state.filter.has(group)?state.filter.delete(group):state.filter.add(group);render();return;}
      if(target.hasAttribute('data-clear-activity')){state.activity='';render();return;}
      if(target.dataset.activity){state.activity=state.activity===target.dataset.activity?'':target.dataset.activity;render();return;}
      if(target.dataset.fold){const key=target.dataset.fold;anchored(target,`.fd-view [data-fold="${CSS.escape(key)}"]`,()=>{state.folded.has(key)?state.folded.delete(key):state.folded.add(key);render();});return;}
      if(target.dataset.next!==undefined){const [kind,key]=[target.dataset.next.slice(0,3),target.dataset.next.slice(4)];
        revealNode(kind==='sec'?container.querySelector(`.fd-view>[data-sec="${CSS.escape(key)}"]`):container.querySelector(`.fd-view [data-fold="${CSS.escape(key)}"]`)?.closest('.fd-group'));return;}
      if(target.dataset.toggle){const id=target.dataset.toggle;anchored(target,`.fd-view>[data-sec="${CSS.escape(id)}"] [data-toggle]`,()=>{if(state.open.has(id)){state.open.delete(id);if(state.auto===id)state.auto=null;}else state.open.add(id);render();});return;}
      if(target.dataset.gotoEvent){openEvent(target.dataset.gotoEvent);return;}
      if(target.dataset.edit){options.onEdit?.(target.dataset.edit);return;}
      if(target.dataset.seek!==undefined){const time=Number(target.dataset.seek);if(Number.isFinite(time))options.onSeek?.(time,{view:state.view,event:target.dataset.event||'',section:target.hasAttribute('data-section-time')});}
    });
    return {
      state,
      update(next){data=next&&next.result?next:null;view=data?model(data.result,data.activities,data.bugs):null;render();},
      setView(next){state.view=next;render();},
      openEvent,
      counts(){return view?counts(view.items):counts([]);},
      // Review: the section under the playhead opens by itself and closes again when the playhead leaves it,
      // unless it was opened by hand.
      setTime(time){
        if(!view)return;const event=view.events.find(row=>time>=row.start&&time<row.end),id=event?.id??null;if(id===state.current)return;
        state.current=id;if(state.auto&&state.auto!==id){state.open.delete(state.auto);state.auto=null;}
        if(id&&!state.open.has(id)){state.open.add(id);state.auto=id;}
        if(state.view==='events'){const top=container.scrollTop;render();container.scrollTop=top;}
      },
    };
  }
  const api={PROBLEM,OTHER,LABEL,GROUPS,GROUP_LABEL,groupOf,isVersion2,model,counts,create};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ThinkAloudFindings=api;
})(globalThis);
