/* Independent interaction prototype. The media element is the only playback clock. */
(() => {
  'use strict';
  const fixture = window.INPUT_REVIEW_FIXTURE;
  if (!fixture) { document.getElementById('video-error').hidden = false; return; }
  const $ = id => document.getElementById(id);
  const video = $('video');
  const intervals = [...fixture.intervals].sort((a,b) => a.start-b.start || b.end-a.end || a.id.localeCompare(b.id));
  const state = { mode:'keys', tab:'timeline', transcript:'pending', follow:true, device:'auto', layout:'compact', scale:60, activeKey:'', lastTime:-1, quote:null, pinned:false, programmaticScrollUntil:0 };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const format = (time,decimal=false) => `${String(Math.floor(Math.max(0,time)/60)).padStart(2,'0')}:${(Math.max(0,time)%60).toFixed(decimal ? 1 : 0).padStart(decimal ? 4 : 2,'0')}`;
  const group = device => device === 'mouse' ? 'keyboard' : device;
  const deviceName = device => ({keyboard:'键盘 + 鼠标',xbox:'Xbox',dualsense:'DualSense'}[device] || '键盘 + 鼠标');
  const mouseIcon = '<svg viewBox="0 0 22 28" aria-hidden="true"><path d="M3 10a8 8 0 0 1 16 0v8a8 8 0 0 1-16 0Z"/><path d="M11 2v9M3 11h16"/><path d="M7 5v3" stroke-width="3"/></svg>';
  const quoteIcon = '<svg viewBox="0 0 18 18" aria-hidden="true"><path d="M3 4h12v8H9l-4 3v-3H3Z"/><path d="M6 7h6M6 9h4"/></svg>';
  function glyph(item) {
    if (item.device === 'mouse') return mouseIcon + (item.direction ? `<span class="mouse-arrow">${escape(item.direction)}</span>` : '');
    if (item.kind === 'axis') return `<span class="axis-glyph">${item.code === 'LeftStick' ? 'L' : 'R'}<span>${escape(item.direction || '•')}</span></span>`;
    return escape(item.label || item.code);
  }
  function activeAt(t) { return intervals.filter(item => item.start <= t && t < item.end); }
  function gapAt(t) { return fixture.gaps.find(gap => gap.start <= t && t < gap.end); }
  function dominantAt(t) {
    let device = 'keyboard';
    for (const item of intervals) {
      if (item.start > t) break;
      if (item.kind === 'button' || item.value == null || item.value >= .18) device = group(item.device);
    }
    return device;
  }
  function seek(time) {
    if (video.readyState === 0) return;
    video.currentTime = Math.max(0,Math.min(Number(time),fixture.duration));
    update(true);
    if (state.follow) followTime(true);
  }
  function announce(message) { $('announcement').textContent = message; }
  function setFollow(value) {
    state.follow = value;
    $('follow').setAttribute('aria-pressed',String(value));
    $('follow').querySelector('span').textContent = value ? '跟随中' : '恢复跟随';
    if (value) followTime(true);
  }
  function activeScroll() { return $(state.tab === 'timeline' ? 'timeline-scroll' : 'transcript-scroll'); }
  function scrollToPosition(scroller,top) {
    state.programmaticScrollUntil = performance.now()+180;
    scroller.scrollTop = Math.max(0,top);
    pinVisibleKeyLabels();
  }
  function followTime(force=false) {
    if (!state.follow) return;
    if (!force && document.activeElement?.matches('.quote-bar:focus-visible')) return;
    const scroller = activeScroll();
    let y = video.currentTime * state.scale + 14;
    if (state.tab === 'transcript') {
      const active = $('transcript-lines').querySelector('.active');
      if (!active) return;
      y = active.offsetTop + active.offsetHeight/2;
    }
    if (force || y < scroller.scrollTop+55 || y > scroller.scrollTop+scroller.clientHeight-70) scrollToPosition(scroller,y-scroller.clientHeight*.36);
  }
  function setMode(mode) {
    state.mode = mode;
    document.querySelectorAll('[data-mode]').forEach(button => { const selected = button.dataset.mode === mode; button.classList.toggle('selected',selected); button.setAttribute('aria-pressed',String(selected)); });
    $('input-body').hidden = mode === 'collapsed';
    $('collapsed-summary').hidden = mode !== 'collapsed';
    document.querySelector('.input-panel').classList.toggle('is-collapsed',mode === 'collapsed');
    $('device-select-label').hidden = mode !== 'device';
    state.activeKey = ''; update(true);
  }
  function setTab(tab) {
    if (tab === 'transcript' && state.transcript !== 'ready') return;
    state.tab = tab;
    for (const name of ['timeline','transcript']) {
      const selected = name === tab;
      $(`${name}-tab`).setAttribute('aria-selected',String(selected));
      $(`${name}-tab`).classList.toggle('selected',selected);
      $(`${name}-panel`).hidden = !selected;
    }
    $('history-subheading').hidden = tab !== 'timeline';
    update(true); followTime(true);
  }
  function setTranscript(status) {
    state.transcript = status;
    const ready = status === 'ready';
    $('transcript-tab').disabled = !ready;
    $('transcript-tab').textContent = ready ? '原话' : status === 'failed' ? '转写失败' : '转写中';
    if (!ready && state.tab === 'transcript') setTab('timeline');
    renderQuotes(); renderTranscript(); closeQuote(); update(true);
    announce(ready ? '转写完成，原话已加入。播放状态和当前页签保持不变。' : status === 'failed' ? '转写失败，视频和操作时间轴仍可使用。' : '已重置为转写中。');
  }
  const keyboardRows = [
    [['Esc','Escape'],['1'],['2'],['3'],['4'],['5'],['6'],['7'],['8'],['9'],['0'],['−','Minus'],['⌫','Backspace','wide']],
    [['Tab','Tab','wide'],['Q'],['W'],['E'],['R'],['T'],['Y'],['U'],['I'],['O'],['P'],['['],[']']],
    [['Caps','CapsLock','wide'],['A'],['S'],['D'],['F'],['G'],['H'],['J'],['K'],['L'],[';'],['↵','Enter','wide']],
    [['Shift','Shift','wider'],['Z'],['X'],['C'],['V'],['B'],['N'],['M'],[','],['.'],['↑','ArrowUp'],['Shift','ShiftRight','wide']],
    [['Ctrl','Control','wide'],['Win','Meta'],['Alt'],['Space','Space','space'],['Alt','AltRight'],['←','ArrowLeft'],['↓','ArrowDown'],['→','ArrowRight']]
  ];
  function keyboardMarkup() {
    return `<div class="keyboard-mouse"><div class="keyboard" aria-label="键盘">${keyboardRows.map(row => `<div class="key-row">${row.map(([label,code,wide]) => `<span class="device-key ${wide||''}" data-control="${escape(code||label)}">${escape(label)}</span>`).join('')}</div>`).join('')}</div><div class="mouse-device"><svg viewBox="0 0 62 124" aria-label="鼠标"><path class="mouse-shell" d="M5 33a26 26 0 0 1 52 0v43a26 26 0 0 1-52 0Z"/><path class="mouse-control" data-control="MouseLeft" d="M8 33A23 23 0 0 1 29 10v35H8Z"/><path class="mouse-control" data-control="MouseRight" d="M33 10a23 23 0 0 1 21 23v12H33Z"/><rect class="mouse-wheel" x="28" y="24" width="6" height="14" rx="3"/><text class="mouse-motion" data-control="MouseMove" x="31" y="76">↗</text><text x="31" y="121" text-anchor="middle" fill="var(--muted)" font-size="9">鼠标</text></svg></div></div>`;
  }
  function controllerMarkup(device) {
    const ps = device === 'dualsense';
    const control = (code,shape,label,x,y) => `<g><${shape} class="control" data-control="${code}" ${shape==='circle' ? `cx="${x}" cy="${y}" r="13"` : `x="${x-24}" y="${y-10}" width="48" height="20" rx="7"`}/>${label ? `<text x="${x}" y="${y}">${label}</text>` : ''}</g>`;
    const stick = (code,x,y) => `<g><circle class="control" data-control="${code}" cx="${x}" cy="${y}" r="24"/><circle class="stick-nub" data-nub="${code}" cx="${x}" cy="${y}" r="9"/><path class="axis-arrow" data-arrow="${code}" d="M${x} ${y+9}v-18m-5 5 5-5 5 5"/><text class="minor-label" x="${x}" y="${y+35}">${code==='LeftStick'?'L':'R'}</text></g>`;
    const dpad = (x,y) => `<g>${[['DpadUp',x,y-13,'↑'],['DpadDown',x,y+13,'↓'],['DpadLeft',x-13,y,'←'],['DpadRight',x+13,y,'→']].map(([code,cx,cy,label])=>`<rect class="control" data-control="${code}" x="${cx-7}" y="${cy-7}" width="14" height="14" rx="3"/><text x="${cx}" y="${cy}" style="font-size:10px">${label}</text>`).join('')}</g>`;
    const symbols = ps ? [['Triangle','△',334,69],['Circle','○',356,91],['Cross','×',334,113],['Square','□',312,91]] : [['Y','Y',334,69],['B','B',356,91],['A','A',334,113],['X','X',312,91]];
    return `<svg class="controller ${ps?'dualsense':'xbox'}" viewBox="0 0 460 211" role="img" aria-label="${deviceName(device)} 设备图"><path class="controller-shell" d="M120 44C101 44 84 53 79 76L60 163c-5 24 14 36 30 23l44-41h192l44 41c16 13 35 1 30-23l-19-87c-5-23-22-32-41-32Z"/>${control(ps?'L2':'LT','rect',ps?'L2':'LT',137,13)}${control(ps?'R2':'RT','rect',ps?'R2':'RT',323,13)}<rect class="trigger-meter" data-meter="${ps?'L2':'LT'}" x="113" y="20" width="0" height="3" rx="1"/><rect class="trigger-meter" data-meter="${ps?'R2':'RT'}" x="299" y="20" width="0" height="3" rx="1"/>${control(ps?'L1':'LB','rect',ps?'L1':'LB',137,39)}${control(ps?'R1':'RB','rect',ps?'R1':'RB',323,39)}${ps?'<rect class="controller-detail" x="178" y="59" width="104" height="41" rx="7"/>':'<circle class="controller-detail" cx="230" cy="73" r="12"/><text class="minor-label" x="230" y="73">X</text>'}${stick('LeftStick',ps?181:128,ps?130:88)}${stick('RightStick',279,130)}${dpad(ps?126:183,ps?94:132)}${symbols.map(([code,label,x,y])=>control(code,'circle',label,x,y)).join('')}<text class="controller-name" x="230" y="192">${ps?'DualSense':'Xbox'}</text></svg>`;
  }
  let renderedDevice = '';
  function renderDevice(device,active) {
    if (renderedDevice !== device) { $('device-view').innerHTML = device === 'keyboard' ? keyboardMarkup() : controllerMarkup(device); renderedDevice = device; }
    const visible = active.filter(item => group(item.device) === device);
    const byCode = new Map(visible.map(item => [item.code,item]));
    $('device-view').querySelectorAll('[data-control]').forEach(el => { const item=byCode.get(el.dataset.control); el.classList.toggle('active',!!item); if(item?.kind==='motion') el.textContent=item.direction||'↗'; });
    $('device-view').querySelectorAll('[data-meter]').forEach(el => el.setAttribute('width',String(48*(byCode.get(el.dataset.meter)?.value||0))));
    $('device-view').querySelectorAll('[data-arrow]').forEach(el => { const item=byCode.get(el.dataset.arrow); el.classList.toggle('active',!!item); const angle = {'↑':0,'↗':45,'→':90,'↘':135,'↓':180,'↙':225,'←':270,'↖':315}[item?.direction]||0; const circle=$('device-view').querySelector(`[data-control="${el.dataset.arrow}"]`); el.setAttribute('transform',`rotate(${angle} ${circle.getAttribute('cx')} ${circle.getAttribute('cy')})`); });
  }
  function renderInput(t) {
    const gap = gapAt(t);
    const active = gap ? [] : activeAt(t);
    const device = state.device === 'auto' ? dominantAt(t) : state.device;
    const key = `${active.map(item=>item.id).join('|')}/${gap?.type||''}/${device}/${state.mode}`;
    if (key === state.activeKey) return;
    state.activeKey = key;
    $('input-source').textContent = deviceName(device);
    $('input-summary').textContent = gap ? '采集缺口' : active.length ? `${active.length} 项持续中` : '对应视频时刻';
    $('input-gap').hidden = !gap;
    $('current-keys').hidden = !!gap || state.mode !== 'keys';
    $('device-view').hidden = !!gap || state.mode !== 'device';
    $('input-hint').hidden = !!gap;
    if (gap) { $('gap-title').textContent=gap.type==='focus'?'已切出目标程序':'设备连接中断'; $('gap-detail').textContent=gap.reason; return; }
    $('current-keys').innerHTML = active.length ? active.map(item => `<div class="current-item" data-event-id="${escape(item.id)}"><span class="keycap active">${glyph(item)}</span><span class="item-label">${escape(item.kind === 'axis' ? item.label : item.device==='mouse' ? (item.label==='鼠标'?'鼠标移动':`鼠标${item.label}`) : item.device==='keyboard'?'按住':deviceName(item.device))}${item.detail?`<span class="item-detail">${escape(item.detail)}</span>`:''}</span></div>`).join('') : '<div class="idle-state"><svg viewBox="0 0 40 30" aria-hidden="true"><rect x="2" y="4" width="36" height="22" rx="5"/><path d="M8 11h3m4 0h3m4 0h3m4 0h3M8 17h3m4 0h3m4 0h3M11 21h17"/></svg>此刻无操作</div>';
    renderDevice(device,active);
    $('input-hint').textContent = state.mode==='device' && !active.length ? '此刻无操作' : '暖红填充表示此刻按住或持续中的操作';
  }
  let packed=[], laneCounts={};
  const channel = item => item.code==='LeftStick'||(item.device==='keyboard'&&['W','A','S','D'].includes(item.code)) ? 'direction' : ['MouseMove','RightStick'].includes(item.code) ? 'pointing' : 'other';
  function packIntervals() {
    const ends={};laneCounts={};
    packed=intervals.map(item=>{
      const track=state.layout==='directional'?channel(item):'all';
      const lanes=ends[track]||(ends[track]=[]);
      let lane=lanes.findIndex(end=>end<=item.start);
      if(lane<0)lane=lanes.length;
      lanes[lane]=item.end;laneCounts[track]=lanes.length;
      return {...item,lane,track};
    });
  }
  const origin = 14;
  function pinVisibleKeyLabels(){
    const top=$('timeline-scroll').scrollTop;
    $('key-track').querySelectorAll('.key-bar').forEach(bar=>{
      const glyph=bar.querySelector('.bar-glyph');
      const offset=Math.max(0,Math.min(top-bar.offsetTop+3,bar.offsetHeight-21));
      glyph.style.transform=`translateY(${offset}px)`;
    });
  }
  function resizeLanes() {
    const width=$('key-track').clientWidth;
    const fixed=state.layout==='directional';
    const directionWidth=Math.min(82,width*.29),pointingWidth=Math.min(56,width*.20);
    const geometry={all:{left:0,width},direction:{left:0,width:directionWidth},pointing:{left:directionWidth,width:pointingWidth},other:{left:directionWidth+pointingWidth,width:width-directionWidth-pointingWidth}};
    for(const item of packed){
      const area=geometry[item.track],step=Math.min(48,(area.width-4)/Math.max(1,laneCounts[item.track]));
      const bar=$('key-track').querySelector(`[data-id="${item.id}"]`);
      if(bar){bar.style.left=`${area.left+item.lane*step}px`;bar.style.width=`${Math.max(12,step-5)}px`;}
    }
    $('timeline').classList.toggle('fixed-direction',fixed);
    $('input-track-headings').innerHTML=fixed?'<span>方向</span><span>指向</span><span>按键</span>':'操作';
    $('input-track-headings').classList.toggle('fixed-headings',fixed);
    $('input-track-headings').style.gridTemplateColumns=fixed?`${directionWidth}px ${pointingWidth}px 1fr`:'';
    $('key-track').style.setProperty('--direction-width',`${directionWidth}px`);
    $('key-track').style.setProperty('--pointing-end',`${directionWidth+pointingWidth}px`);
  }
  function renderTimeline() {
    packIntervals();
    $('timeline').style.height=`${fixture.duration*state.scale+origin+24}px`;
    $('time-scale').innerHTML=Array.from({length:Math.floor(fixture.duration)+1},(_,second)=>`<div class="time-tick" style="top:${origin+second*state.scale}px"><span>${format(second)}</span></div>`).join('');
    $('key-track').innerHTML=packed.map(item=>`<button class="key-bar ${item.end-item.start<.3?'brief':''}" data-id="${escape(item.id)}" data-start="${item.start}" style="top:${origin+item.start*state.scale}px;height:${(item.end-item.start)*state.scale}px;left:calc(${item.lane} * var(--lane-step))" title="${escape(deviceName(group(item.device))+' · '+(item.detail||item.label)+' · '+format(item.start,true)+' — '+format(item.end,true))}" aria-label="${escape(deviceName(group(item.device))+' '+item.label+'，'+format(item.start,true)+' 至 '+format(item.end,true)+'，点击定位')}"><span class="bar-glyph">${glyph(item)}</span><span class="bar-duration">${(item.end-item.start).toFixed(1)}s</span></button>`).join('');
    $('gap-layer').innerHTML=fixture.gaps.map(gap=>`<button class="timeline-gap" data-start="${gap.start}" style="top:${origin+gap.start*state.scale}px;height:${(gap.end-gap.start)*state.scale}px" title="${escape(gap.reason)}"><span class="gap-tag">${gap.type==='focus'?'Ⅱ 暂停采集':'连接中断'}</span><span>${escape(gap.reason)}</span></button>`).join('');
    $('key-track').querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>seek(button.dataset.start)));
    $('gap-layer').querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>seek(button.dataset.start)));
    renderQuotes(); resizeLanes(); update(true);pinVisibleKeyLabels();
  }
  function renderQuotes() {
    $('quote-track').innerHTML = state.transcript==='ready' ? fixture.segments.map((segment,index)=>`<button class="quote-bar" data-index="${index}" style="top:${origin+segment.start*state.scale}px;height:${(segment.end-segment.start)*state.scale}px" aria-label="原话 ${index+1}，${format(segment.start,true)}，点击固定全文">${quoteIcon}<span>原话 ${index+1}</span></button>`).join('') : '<span class="quote-track-pending">'+(state.transcript==='failed'?'转写失败':'转写中')+'</span>';
    $('quote-track').querySelectorAll('button').forEach(button=>{
      button.addEventListener('mouseenter',()=>{if(!state.pinned)showQuote(Number(button.dataset.index),button,false);});
      button.addEventListener('focus',()=>{
        // Wait for the browser to reveal the focused bar before positioning its preview.
        requestAnimationFrame(()=>{if(document.activeElement===button&&!state.pinned)showQuote(Number(button.dataset.index),button,false);});
      });
      button.addEventListener('blur',event=>{if(!state.pinned&&!$('quote-popover').contains(event.relatedTarget))closeQuote();});
      button.addEventListener('mouseleave',event=>{if(!state.pinned&&!button.matches(':focus-visible')&&!$('quote-popover').contains(event.relatedTarget))closeQuote();});
      button.addEventListener('click',event=>{event.stopPropagation();showQuote(Number(button.dataset.index),button,true);});
    });
  }
  function renderTranscript() {
    $('transcript-lines').innerHTML=state.transcript==='ready' ? fixture.segments.map((segment,index)=>`<button class="transcript-line" data-index="${index}" data-start="${segment.start}"><time>${format(segment.start,true)}</time><span>${escape(segment.text)}</span></button>`).join('') : '';
    $('transcript-lines').querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>seek(button.dataset.start)));
  }
  function showQuote(index,anchor,pinned) {
    const segment=fixture.segments[index]; state.quote=index; state.pinned=pinned;
    $('quote-popover-time').textContent=`${format(segment.start,true)} — ${format(segment.end,true)}`;
    $('quote-popover-text').textContent=segment.text; $('quote-pinned').hidden=!pinned;
    const popover=$('quote-popover');popover.hidden=false;
    const rect=anchor.getBoundingClientRect(); const width=popover.offsetWidth;
    const x=Math.max(12,Math.min(window.innerWidth-width-12,rect.right+12));
    const y=Math.max(12,Math.min(window.innerHeight-popover.offsetHeight-12,rect.top));
    popover.style.left=`${x}px`;popover.style.top=`${y}px`;
    $('quote-track').querySelectorAll('button').forEach(button=>button.classList.toggle('pinned',pinned&&Number(button.dataset.index)===index));
  }
  function closeQuote() { state.quote=null;state.pinned=false;$('quote-popover').hidden=true;$('quote-track').querySelectorAll('.pinned').forEach(el=>el.classList.remove('pinned')); }
  function update(force=false) {
    const t=Number.isFinite(video.currentTime)?video.currentTime:0;
    if(!force&&t===state.lastTime)return;state.lastTime=t;
    $('current-time').textContent=format(t,true);$('seek').value=String(t);
    $('playhead').style.top=`${origin+t*state.scale}px`;$('playhead-time').textContent=format(t,true);
    const activeIds=new Set(activeAt(t).map(item=>item.id));
    $('key-track').querySelectorAll('.key-bar').forEach(bar=>bar.classList.toggle('active',activeIds.has(bar.dataset.id)&&!gapAt(t)));
    $('quote-track').querySelectorAll('.quote-bar').forEach(bar=>{const segment=fixture.segments[Number(bar.dataset.index)];bar.classList.toggle('active',segment.start<=t&&t<segment.end);});
    const currentQuote=fixture.segments.findIndex(segment=>segment.start<=t&&t<segment.end);
    $('transcript-lines').querySelectorAll('.transcript-line').forEach(line=>line.classList.toggle('active',Number(line.dataset.index)===currentQuote));
    $('history-count').textContent=state.tab==='transcript'?`${fixture.segments.length} 段原话`:`${intervals.length} 项操作 · ${fixture.gaps.length} 处采集缺口`;
    renderInput(t);followTime();
  }
  function updatePlayButton() { const paused=video.paused; $('play').setAttribute('aria-label',paused?'播放':'暂停');$('play').innerHTML=paused?'<svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 4 10 6-10 6Z"/></svg>':'<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 4h3v12H5ZM12 4h3v12h-3Z"/></svg>'; }
  $('session-title').textContent=fixture.title;$('duration').textContent=format(fixture.duration);$('seek').max=String(fixture.duration);
  let initialPositionSet = false;
  function setInitialPosition() {
    if (initialPositionSet || video.readyState < 1) return;
    video.currentTime = 4.8;
    initialPositionSet = true;
    update(true);followTime(true);
  }
  video.addEventListener('loadedmetadata',setInitialPosition);
  video.addEventListener('loadeddata',setInitialPosition);
  video.addEventListener('error',()=>{$('video-error').hidden=false;});
  ['play','pause','ended'].forEach(name=>video.addEventListener(name,updatePlayButton));
  ['seeked','timeupdate'].forEach(name=>video.addEventListener(name,()=>update(true)));
  $('play').addEventListener('click',()=>{if(video.paused){if(video.ended)seek(0);video.play().catch(()=>announce('视频暂时无法播放，请检查本地示例视频。'));}else video.pause();});
  $('seek').addEventListener('input',event=>seek(event.target.value));
  $('speed').addEventListener('change',event=>{video.playbackRate=Number(event.target.value);});
  $('scene').addEventListener('change',event=>{seek(event.target.value);followTime(true);});
  document.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>setMode(button.dataset.mode)));
  $('device-select').addEventListener('change',event=>{state.device=event.target.value;state.activeKey='';update(true);});
  $('timeline-tab').addEventListener('click',()=>setTab('timeline'));$('transcript-tab').addEventListener('click',()=>setTab('transcript'));
  $('transcript-ready').addEventListener('click',()=>setTranscript('ready'));$('transcript-reset').addEventListener('click',()=>setTranscript('pending'));$('transcript-fail').addEventListener('click',()=>setTranscript('failed'));
  $('follow').addEventListener('click',()=>setFollow(!state.follow));
  for(const scroller of [$('timeline-scroll'),$('transcript-scroll')]){
    scroller.addEventListener('wheel',()=>setFollow(false),{passive:true});scroller.addEventListener('touchmove',()=>setFollow(false),{passive:true});
    scroller.addEventListener('pointerdown',event=>{if(event.target===scroller)setFollow(false);});
    scroller.addEventListener('keydown',event=>{if(['ArrowDown','ArrowUp','PageDown','PageUp','Home','End',' '].includes(event.key))setFollow(false);});
    scroller.addEventListener('scroll',()=>{
      // Explicit wheel, touch, scrollbar and navigation-key actions pause follow.
      // Revealing keyboard focus is not a manual scroll and must keep the preview.
      if(!state.pinned){
        const focused=document.activeElement;
        if(focused?.matches('.quote-bar:focus-visible'))showQuote(Number(focused.dataset.index),focused,false);
        else closeQuote();
      }
      pinVisibleKeyLabels();
    });
  }
  $('timeline-zoom').addEventListener('change',event=>{const ratio=Number(event.target.value)/state.scale;const top=$('timeline-scroll').scrollTop;state.scale=Number(event.target.value);renderTimeline();if(state.follow)followTime(true);else scrollToPosition($('timeline-scroll'),top*ratio);closeQuote();});
  $('track-layout').addEventListener('change',event=>{state.layout=event.target.value;const top=$('timeline-scroll').scrollTop;renderTimeline();scrollToPosition($('timeline-scroll'),top);closeQuote();});
  $('theme-toggle').addEventListener('click',()=>{const dark=document.documentElement.dataset.theme!=='dark';document.documentElement.dataset.theme=dark?'dark':'light';$('theme-toggle').setAttribute('aria-label',dark?'切换至浅色主题':'切换至深色主题');});
  $('quote-close').addEventListener('click',closeQuote);$('quote-seek').addEventListener('click',()=>{if(state.quote!==null)seek(fixture.segments[state.quote].start);});
  $('quote-popover').addEventListener('mouseleave',event=>{if(!state.pinned&&!event.relatedTarget?.closest?.('.quote-bar'))closeQuote();});
  document.addEventListener('click',event=>{if(!$('quote-popover').contains(event.target)&&!event.target.closest('.quote-bar'))closeQuote();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeQuote();});
  function fitVideoLayout(){
    const layout=document.querySelector('.review-layout');
    if(innerWidth<=680){layout.style.gridTemplateColumns='';return;}
    const style=getComputedStyle(layout),n=value=>parseFloat(value)||0;
    const available=layout.clientWidth-n(style.paddingLeft)-n(style.paddingRight)-n(style.columnGap);
    const height=layout.clientHeight-n(style.paddingTop)-n(style.paddingBottom);
    const sourceWidth=Math.max(280,(height-47-12-224)*16/9);
    const width=Math.max(270,Math.min(sourceWidth,available*.60,available-340));
    layout.style.gridTemplateColumns=`${width}px minmax(0,1fr)`;
  }
  new ResizeObserver(()=>{resizeLanes();if(!state.pinned)closeQuote();}).observe($('timeline'));
  new ResizeObserver(fitVideoLayout).observe(document.querySelector('.review-layout'));
  window.addEventListener('resize',fitVideoLayout);fitVideoLayout();
  renderTimeline();renderTranscript();updatePlayButton();
  video.src=fixture.video;
  video.load();
  if(video.readyState>=1)setInitialPosition();
  function frame(){update();requestAnimationFrame(frame);}requestAnimationFrame(frame);
})();
