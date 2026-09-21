(function(root) {
  'use strict';
  function formatTime(seconds) {
    const total=Math.max(0,Math.floor(Number(seconds)||0));
    return [Math.floor(total/3600),Math.floor(total/60)%60,total%60].map(n=>String(n).padStart(2,'0')).join(':');
  }
  function activeSegment(segments,time) {
    let lo=0,hi=segments.length;
    while(lo<hi){const mid=(lo+hi)>>>1;if(segments[mid].start<=time)lo=mid+1;else hi=mid;}
    const i=lo-1;return i>=0&&time<segments[i].end?i:-1;
  }
  function splitBounds(available, firstMin, secondMin, requested) {
    if(!(available>0))return {min:0.5,max:0.5,value:0.5};
    const scale=Math.min(1,available/(firstMin+secondMin));
    const min=firstMin*scale/available,max=Math.max(min,1-secondMin*scale/available);
    return {min,max,value:Math.max(min,Math.min(max,Number.isFinite(requested)?requested:0.5))};
  }
  if(typeof module==='object'&&module.exports){module.exports={formatTime,activeSegment,splitBounds};return;}
  const data=JSON.parse(document.getElementById('review-data').textContent);
  const $=id=>document.getElementById(id),video=$('video'),lines=$('lines'),segments=data.segments;
  function setTheme(value){
    document.documentElement.dataset.theme=value;
    const label=value==='dark'?'切换浅色模式':'切换深色模式';
    $('themeButton').setAttribute('aria-label',label);$('themeButton').title=label;
    try{localStorage.setItem('recorder-theme',value);}catch(_){}
  }
  try{setTheme(localStorage.getItem('recorder-theme')==='dark'?'dark':'light');}catch(_){setTheme('light');}
  $('themeButton').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
  const copySplit=$('copySplit'),fileActions=$('fileActions'),fileActionsToggle=$('fileActionsToggle');
  const menuButtons=[...fileActions.querySelectorAll('button')];
  function closeFileActions(restoreFocus=false){fileActions.hidden=true;fileActionsToggle.setAttribute('aria-expanded','false');if(restoreFocus)fileActionsToggle.focus();}
  function positionFileActions(){
    if(fileActions.hidden)return;
    const anchor=copySplit.getBoundingClientRect(),margin=10,gap=8;
    const above=Math.max(0,anchor.top-gap-margin),below=Math.max(0,root.innerHeight-anchor.bottom-gap-margin);
    const opensAbove=above>=below;
    fileActions.style.maxHeight=Math.max(above,below)+'px';
    const menu=fileActions.getBoundingClientRect();
    fileActions.style.left=Math.max(margin,Math.min(root.innerWidth-menu.width-margin,anchor.right-menu.width))+'px';
    fileActions.style.top=(opensAbove?anchor.top-gap-menu.height:anchor.bottom+gap)+'px';
  }
  function openFileActions(){fileActions.hidden=false;fileActionsToggle.setAttribute('aria-expanded','true');positionFileActions();}
  fileActionsToggle.addEventListener('click',()=>fileActions.hidden?openFileActions():closeFileActions());
  document.addEventListener('click',event=>{if(!copySplit.contains(event.target))closeFileActions();});
  copySplit.addEventListener('focusout',event=>{if(!copySplit.contains(event.relatedTarget))closeFileActions();});
  copySplit.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&!fileActions.hidden){event.preventDefault();event.stopPropagation();closeFileActions(true);return;}
    if(event.target===fileActionsToggle&&['ArrowDown','ArrowUp'].includes(event.key)){
      event.preventDefault();openFileActions();menuButtons[event.key==='ArrowDown'?0:menuButtons.length-1].focus();return;
    }
    const index=menuButtons.indexOf(event.target);
    if(index<0||!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;
    event.preventDefault();
    const next=event.key==='Home'?0:event.key==='End'?menuButtons.length-1:
      (index+(event.key==='ArrowDown'?1:-1)+menuButtons.length)%menuButtons.length;
    menuButtons[next].focus();
  });
  let copyFeedbackTimer=null;
  function resetCopyFeedback(){root.clearTimeout(copyFeedbackTimer);$('copyPath').classList.remove('copied');$('copyLabel').textContent='复制资料路径';}
  function showCopyFeedback(){resetCopyFeedback();$('copyPath').classList.add('copied');$('copyLabel').textContent='copied!';copyFeedbackTimer=root.setTimeout(resetCopyFeedback,2000);}
  let current=-1,follow=true,ready=false,mediaError=null,pendingSeek=null;
  const status=(message,error=false)=>{$('status').textContent=message;$('status').classList.toggle('error',error);};
  $('title').textContent=data.title;
  $('testLabel').hidden=!data.test;
  const date=new Date(data.created);
  $('sessionInfo').textContent=Number.isNaN(date.getTime())?'':date.toLocaleString('zh-CN',{year:'numeric',month:'long',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});
  $('title').title=data.title;
  const layout=document.querySelector('.review-layout'),splitter=$('reviewSplitter');
  const videoPane=$('videoPane'),textPane=$('transcriptPane'),videoSlot=videoPane.querySelector('.video-slot');
  const stacked=root.matchMedia('(max-width:760px)'),defaults={columns:1.45/2.45,rows:0.54};
  const shares={...defaults},storageKey='experience-review-layout-v1';
  const touched=new Set();
  let dragging=null,frame=null,metrics=null;
  const axis=()=>stacked.matches?'rows':'columns';
  const validShare=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0.05&&value<=0.95;
  const number=value=>parseFloat(value)||0;
  function fixedHeight(pane,flexible){
    const style=getComputedStyle(pane);
    const children=[...pane.children].filter(child=>getComputedStyle(child).display!=='none');
    return number(style.paddingTop)+number(style.paddingBottom)+number(style.borderTopWidth)+number(style.borderBottomWidth)
      +Math.max(0,children.length-1)*number(style.rowGap)
      +children.filter(child=>child!==flexible).reduce((sum,child)=>{
        const css=getComputedStyle(child);
        return sum+child.getBoundingClientRect().height+number(css.marginTop)+number(css.marginBottom);
      },0);
  }
  function renderSplit(){
    const mode=axis(),vertical=mode==='rows',rect=layout.getBoundingClientRect(),style=getComputedStyle(layout);
    const before=number(vertical?style.paddingTop:style.paddingLeft),after=number(vertical?style.paddingBottom:style.paddingRight);
    const divider=number(style.getPropertyValue('--splitter-size'));
    const available=Math.max(0,(vertical?rect.height:rect.width)-before-after-divider);
    const bounds=splitBounds(available,vertical?fixedHeight(videoPane,videoSlot)+72:240,
      vertical?fixedHeight(textPane,lines)+32:220,shares[mode]);
    layout.style.setProperty('--video-share',bounds.value+'fr');
    layout.style.setProperty('--text-share',(1-bounds.value)+'fr');
    splitter.setAttribute('aria-orientation',vertical?'horizontal':'vertical');
    splitter.setAttribute('aria-valuemin',Math.round(bounds.min*100));
    splitter.setAttribute('aria-valuemax',Math.round(bounds.max*100));
    splitter.setAttribute('aria-valuenow',Math.round(bounds.value*100));
    splitter.setAttribute('aria-valuetext',`视频 ${Math.round(bounds.value*100)}%，文本 ${Math.round((1-bounds.value)*100)}%`);
    metrics={mode,vertical,available,start:(vertical?rect.top:rect.left)+before,...bounds};
    positionFileActions();
    return metrics;
  }
  function scheduleSplit(){if(frame===null)frame=root.requestAnimationFrame(()=>{frame=null;renderSplit();});}
  async function saveShare(mode){
    touched.add(mode);
    try{
      if(data.desktop){await root.pywebview?.api?.save_layout(mode,shares[mode]);}
      else localStorage.setItem(storageKey,JSON.stringify(shares));
    }catch(_){/* A blocked preference store must not interrupt playback. */}
  }
  async function loadShares(){
    try{
      const response=data.desktop?await root.pywebview?.api?.get_layout():null;
      const saved=data.desktop?(response?.ok?response.data:null):JSON.parse(localStorage.getItem(storageKey)||'null');
      for(const mode of Object.keys(defaults))if(!touched.has(mode)&&validShare(saved?.[mode]))shares[mode]=saved[mode];
      renderSplit();
    }catch(_){renderSplit();}
  }
  function finishDrag(event){
    if(!dragging||(event&&event.pointerId!==dragging.id))return;
    const drag=dragging;dragging=null;
    document.body.classList.remove('resizing-columns','resizing-rows');
    if(splitter.hasPointerCapture(drag.id))splitter.releasePointerCapture(drag.id);
    saveShare(drag.mode);
  }
  splitter.addEventListener('pointerdown',event=>{
    if(event.button!==0||dragging)return;
    const m=renderSplit();
    if(!m.available)return;
    event.preventDefault();splitter.focus({preventScroll:true});
    dragging={id:event.pointerId,mode:m.mode,offset:(m.vertical?event.clientY:event.clientX)-m.start-m.available*m.value};
    touched.add(m.mode);splitter.setPointerCapture(event.pointerId);
    document.body.classList.add('resizing-'+m.mode);
  });
  splitter.addEventListener('pointermove',event=>{
    if(!dragging||event.pointerId!==dragging.id)return;
    const m=renderSplit();
    if(m.mode!==dragging.mode||!m.available){finishDrag();return;}
    const requested=((m.vertical?event.clientY:event.clientX)-m.start-dragging.offset)/m.available;
    shares[m.mode]=Math.max(m.min,Math.min(m.max,requested));renderSplit();
  });
  for(const name of ['pointerup','pointercancel','lostpointercapture'])splitter.addEventListener(name,finishDrag);
  root.addEventListener('blur',()=>finishDrag());
  function resetSplit(){const mode=axis();shares[mode]=defaults[mode];renderSplit();saveShare(mode);}
  splitter.addEventListener('dblclick',resetSplit);
  splitter.addEventListener('keydown',event=>{
    if(event.altKey||event.ctrlKey||event.metaKey||event.isComposing)return;
    const m=renderSplit(),back=m.vertical?'ArrowUp':'ArrowLeft',forward=m.vertical?'ArrowDown':'ArrowRight';
    if(![back,forward,'Home','End','Enter'].includes(event.key))return;
    event.preventDefault();event.stopPropagation();
    if(event.key==='Enter'){resetSplit();return;}
    const step=event.shiftKey?0.1:0.02;
    shares[m.mode]=event.key==='Home'?m.min:event.key==='End'?m.max:
      Math.max(m.min,Math.min(m.max,m.value+(event.key===back?-step:step)));
    renderSplit();saveShare(m.mode);
  });
  const layoutObserver=new ResizeObserver(scheduleSplit);
  for(const element of [layout,videoPane.querySelector('.file-card'),textPane.querySelector('.transcript-heading')])layoutObserver.observe(element);
  stacked.addEventListener('change',()=>{finishDrag();scheduleSplit();});
  renderSplit();
  if(!data.desktop||root.pywebview?.api)loadShares();
  root.addEventListener('pywebviewready',loadShares);
  const player=new Plyr(video,{
    controls:['play-large','rewind','play','fast-forward','progress','current-time','duration','mute','volume','settings','fullscreen'],
    seekTime:15,keyboard:{focused:false,global:false},autopause:false,
    loadSprite:false,iconUrl:'',blankVideo:'',settings:['speed'],
    speed:{selected:1,options:[0.5,0.75,1,1.25,1.5,2]},
    i18n:{play:'播放',pause:'暂停',rewind:'后退 {seektime} 秒',fastForward:'前进 {seektime} 秒',seek:'定位',
      currentTime:'当前时间',duration:'总时长',volume:'音量',mute:'静音',unmute:'取消静音',settings:'设置',
      speed:'播放速度',normal:'正常',enterFullscreen:'全屏',exitFullscreen:'退出全屏'}
  });
  // Expose only the player for desktop smoke diagnostics, never native service state.
  root.reviewPlayer=player;
  // Handle shortcuts before a focused transcript button can turn Space into
  // another seek. Playback and seeking still use Plyr's supported controls.
  document.addEventListener('keydown',event=>{
    if(event.altKey||event.ctrlKey||event.metaKey||event.isComposing)return;
    if(event.target.closest('input:not([type="range"]),textarea,select,[contenteditable="true"],[role="separator"],.file-card,.review-header'))return;
    if(![' ','ArrowLeft','ArrowRight'].includes(event.key))return;
    event.preventDefault();event.stopImmediatePropagation();
    if(event.key===' '){if(!event.repeat)player.togglePlay();}
    else if(event.key==='ArrowLeft')player.rewind(15);
    else player.forward(15);
  },true);
  function reportReady(){if(data.desktop&&ready&&root.pywebview?.api)root.pywebview.api.ready(mediaError).catch(()=>{});}
  function seek(time){const bounded=Math.max(0,Math.min(time,Number.isFinite(video.duration)?video.duration:time));player.currentTime=bounded;player.play().catch(()=>{});}
  const nodes=segments.map((segment,index)=>{
    const button=document.createElement('button');button.className='line';button.type='button';
    const time=document.createElement('time');time.textContent=formatTime(segment.start);
    const text=document.createElement('span');text.className='segment-text';text.textContent=segment.text;button.append(time,text);
    button.addEventListener('click',()=>{if(root.getSelection()?.toString())return;setFollow(true);if(video.readyState)seek(segment.start);else pendingSeek=segment.start;});
    lines.append(button);return button;
  });
  function setFollow(value){follow=value;$('follow').textContent=value?'跟随播放：开':'恢复跟随';$('follow').setAttribute('aria-pressed',String(value));if(value)scrollCurrent();}
  function scrollCurrent(){const node=nodes[current];if(!follow||!node||node.hidden)return;const top=node.offsetTop-lines.offsetTop-(lines.clientHeight-node.clientHeight)/2;lines.scrollTo({top:Math.max(0,top),behavior:'smooth'});}
  function sync(){const index=activeSegment(segments,video.currentTime);if(index===current)return;nodes[current]?.classList.remove('active');nodes[current]?.removeAttribute('aria-current');current=index;nodes[current]?.classList.add('active');nodes[current]?.setAttribute('aria-current','true');scrollCurrent();}
  $('follow').onclick=()=>setFollow(!follow);
  lines.addEventListener('wheel',()=>setFollow(false),{passive:true});
  lines.addEventListener('touchstart',()=>setFollow(false),{passive:true});
  lines.addEventListener('pointerdown',event=>{if(event.target===lines)setFollow(false);});
  lines.addEventListener('keydown',event=>{if(['PageDown','PageUp','Home','End','ArrowDown','ArrowUp'].includes(event.key))setFollow(false);});
  function filter(){const query=$('search').value.trim().toLocaleLowerCase();let count=0;nodes.forEach((node,i)=>{node.hidden=!segments[i].text.toLocaleLowerCase().includes(query);if(!node.hidden)count++;});$('lineCount').textContent=count+' 条';$('empty').hidden=count>0;$('empty').textContent=segments.length?'没有匹配的原话。':'没有识别出语音，可以继续查看录像。';}
  $('search').oninput=filter;filter();video.addEventListener('timeupdate',sync);
  video.addEventListener('loadedmetadata',()=>{ready=true;mediaError=null;status('');if(pendingSeek!==null){seek(pendingSeek);pendingSeek=null;}reportReady();});
  video.addEventListener('error',()=>{ready=true;mediaError='录像无法加载，请检查录像.mp4 是否存在，并将资料包完整解压后打开。';status(mediaError,true);reportReady();});
  root.addEventListener('pywebviewready',reportReady);
  video.src=data.video;
  async function native(method,...args){const api=root.pywebview?.api;if(!api)throw new Error('回看窗口尚未连接，请稍后重试。');const result=await api[method](...args);if(!result?.ok)throw new Error(result?.error||'操作未完成。');}
  function portablePath(kind){const file=kind==='video'?'录像.mp4':kind==='transcript'?'录像.whisper.json':'.';const url=new URL(file,location.href);if(url.protocol!=='file:')return url.href;let path=decodeURIComponent(url.pathname);if(/^\/[A-Za-z]:\//.test(path))path=path.slice(1);return url.hostname?'\\\\'+url.hostname+path.replace(/\//g,'\\'):path.replace(/\//g,'\\');}
  async function copy(kind){resetCopyFeedback();if(data.desktop)await native('copy_path',kind);else{const text=portablePath(kind);try{await navigator.clipboard.writeText(text);}catch(_){const field=document.createElement('textarea');field.value=text;document.body.append(field);field.select();const copied=document.execCommand('copy');field.remove();if(!copied)throw new Error('无法自动复制，路径：'+text);}}status(mediaError||'',!!mediaError);showCopyFeedback();}
  function handle(fn){return async()=>{try{await fn();}catch(error){status(error.message,true);}};}
  document.querySelectorAll('[data-copy]').forEach(button=>button.onclick=handle(async()=>{closeFileActions(button!==$('copyPath'));await copy(button.dataset.copy);}));
  $('folder').onclick=handle(async()=>{if(data.desktop){await native('open_folder');}else{await copy('folder');status('资料路径已复制，可粘贴到文件资源管理器中打开。');}});
  document.querySelectorAll('[data-document]').forEach(button=>button.onclick=handle(async()=>{closeFileActions(true);const kind=button.dataset.document;if(data.desktop)await native('open_document',kind);else root.open(kind==='notes'?'复盘.md':'逐字稿.md','_blank');}));
})(globalThis);
