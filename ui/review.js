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
  function sourceFit({available,height,videoWidth,videoHeight,chromeHeight=0,chromeWidth=0,videoMin=240,textMin=320}) {
    if(![available,height,videoWidth,videoHeight].every(value=>Number.isFinite(value)&&value>0))return null;
    const aspect=videoWidth/videoHeight,slotHeight=Math.max(0,height-chromeHeight);
    const bounds=splitBounds(available,videoMin,textMin,(slotHeight*aspect+chromeWidth)/available);
    const width=available*bounds.value,slotWidth=Math.min(Math.max(0,width-chromeWidth),slotHeight*aspect);
    return {...bounds,width,slotWidth,slotHeight:slotWidth/aspect};
  }
  const inputGroup=device=>device==='mouse'?'keyboard':device;
  function axisDirection(x,y){if(!Number.isFinite(x)||!Number.isFinite(y)||Math.hypot(x,y)<.01)return '';return ['→','↘','↓','↙','←','↖','↑','↗'][(Math.round(Math.atan2(y,x)/(Math.PI/4))+8)%8];}
  function inputChannel(item){return /^D[Pp]ad/.test(item.code)?'dpad':item.code==='LeftStick'||(item.device==='keyboard'&&['W','A','S','D','KeyW','KeyA','KeyS','KeyD'].includes(item.code))?'direction':['MouseMove','RightStick'].includes(item.code)?'pointing':'other';}
  function normalizeInputs(source,override=null){
    if(!source)return {state:'missing',intervals:[],gaps:[],duration:0};
    const valid=item=>item&&Number.isFinite(item.start)&&Number.isFinite(item.end)&&item.start>=0&&item.end>=item.start;
    const candidate=override??source.alignment?.offset_seconds,offset=Number.isFinite(candidate)&&Math.abs(candidate)<=30?candidate:0;
    const limit=Number.isFinite(source.video_duration)&&source.video_duration>0?source.video_duration:Infinity;
    const shift=(item,leading=false)=>({...item,start:leading&&item.start===0?0:Math.max(0,item.start+offset),end:Math.min(limit,Math.max(0,item.end+offset))});
    const inside=item=>valid(item)&&item.end+offset>=0&&item.start+offset<limit;
    return {...source,state:String(source.state||'ready'),duration:Number.isFinite(limit)?limit:Math.max(0,(Number(source.duration)||0)+offset),
      intervals:(Array.isArray(source.intervals)?source.intervals:[]).filter(inside).map((item,i)=>({...shift(item),id:String(item.id??i),direction:item.direction||axisDirection(item.x,item.y)})).sort((a,b)=>a.start-b.start||b.end-a.end||a.id.localeCompare(b.id)),
      gaps:(Array.isArray(source.gaps)?source.gaps:[]).filter(inside).map(item=>shift(item,true)).sort((a,b)=>a.start-b.start)};
  }
  function inputLabel(item){return ({ControlLeft:'Ctrl',ControlRight:'Ctrl',ShiftLeft:'Shift',ShiftRight:'Shift',AltLeft:'Alt',AltRight:'Alt',WinLeft:'Win',WinRight:'Win',Space:'␣',Backspace:'⌫',Escape:'Esc',ArrowUp:'↑',ArrowDown:'↓',ArrowLeft:'←',ArrowRight:'→',DPadUp:'↑',DPadDown:'↓',DPadLeft:'←',DPadRight:'→',DpadUp:'↑',DpadDown:'↓',DpadLeft:'←',DpadRight:'→',Cross:'×',Square:'□',Triangle:'△',Circle:'○'}[item.code])||item.label||item.code;}
  // These are display groups, not inferred physical presses. Original samples
  // remain intact for exact playback state and pointer-time inspection.
  function inputVisualBands(intervals,gaps=[]){
    const result=[],last=new Map(),gapIndex=intervalIndex(gaps),epsilon=1e-6;
    for(const item of intervals){
      const channel=inputChannel(item),fixed=channel!=='other';
      if(fixed&&['axis','motion'].includes(item.kind)&&(item.value??1)<=0){last.delete(channel);continue;}
      const key=fixed?channel:item.device+'/'+item.code,continuous=fixed||(['axis','motion','trigger'].includes(item.kind)&&(item.value??1)>0);
      const previous=last.get(key),blocked=previous&&intervalsInRange(gapIndex,previous.end-epsilon,item.start+epsilon).some(gap=>!gap.device||gap.device===item.device);
      // D-pad focus navigation is a burst, not a held key. Motion sampling may
      // briefly return to neutral. Keep every physical interval inside the band.
      const joinGap=channel==='dpad'?.65:fixed&&['axis','motion'].includes(item.kind)?.12:epsilon;
      if(continuous&&previous&&(fixed||previous.kind===item.kind)&&!item.resumed&&!blocked&&item.start<=previous.end+joinGap){
        previous.end=Math.max(previous.end,item.end);previous.samples.push(item);
        if(previous.changes.at(-1)?.direction!==item.direction)previous.changes.push(item);
      }else{
        const band={...item,fixed};if(continuous){band.samples=[item];band.changes=[item];last.set(key,band);}else last.delete(key);result.push(band);
      }
    }
    for(const band of result)if(band.samples){
      band.sampleIndex=intervalIndex(band.samples);
      band.marks=band.samples.filter((sample,i)=>sample.kind==='button'||!i||sample.start>band.samples[i-1].end+1e-6||sample.device!==band.samples[i-1].device);
      band.markIndex=intervalIndex(band.marks);
      band.activity=band.samples.length>1||['axis','motion'].includes(band.kind);
    }
    return result;
  }
  function inputSampleAt(item,time){
    if(time<item.start||time>=item.end)return null;
    if(!item.samples)return item;
    let lo=0,hi=item.samples.length;while(lo<hi){const mid=(lo+hi)>>>1;if(item.samples[mid].start<=time)lo=mid+1;else hi=mid;}
    const sample=item.samples[lo-1];
    if(inputChannel(item)==='dpad')return sample||null;
    const active=intervalsInRange(item.sampleIndex||intervalIndex(item.samples),time,time+1e-9).filter(value=>value.start<=time&&time<value.end);
    if(!active.length)return null;
    const latest=active.at(-1);
    if(inputChannel(item)==='direction'&&latest.device==='keyboard'){
      const keys=active.filter(value=>value.device==='keyboard').map(value=>value.code.replace(/^Key/,''));
      const direction=axisDirection(Number(keys.includes('D'))-Number(keys.includes('A')),Number(keys.includes('S'))-Number(keys.includes('W')));
      return {...latest,code:keys.join('+'),label:keys.join(' + '),direction,movement:true};
    }
    return latest;
  }
  function packInputIntervals(intervals,{scale=64,minHeight=28,gap=4}={}){
    const ends={},counts={direction:0,pointing:0,dpad:0,other:0},widths={direction:[],pointing:[],dpad:[],other:[]};
    const items=intervals.map(item=>{
      const channel=inputChannel(item),lanes=ends[channel]||(ends[channel]=[]);let lane=lanes.findIndex(end=>end<=item.start+1e-9);if(lane<0)lane=lanes.length;
      if(item.fixed)lane=0;
      const displayEnd=item.fixed?Math.max(item.end,item.start+1/scale):Math.max(item.end,item.start+minHeight/scale);lanes[lane]=displayEnd+gap/scale;counts[channel]=lanes.length;
      const label=inputLabel(item),width=['axis','motion'].includes(item.kind)||/^D[Pp]ad/.test(item.code)||item.device==='mouse'?36:Math.max(36,Math.ceil([...label].reduce((n,c)=>n+(c.charCodeAt(0)>255?12:7.5),16)));
      widths[channel][lane]=Math.max(widths[channel][lane]||0,width);
      return {...item,channel,lane,displayEnd};
    });
    return {items,counts,widths};
  }
  function intervalIndex(items,endKey='end'){
    // A spanning hold must not force a backwards scan through every old tap.
    // Each tree node bounds only its own contiguous range of sorted starts.
    let size=1;while(size<items.length)size*=2;
    const maxEnds=new Float64Array(size*2).fill(-Infinity);
    for(let i=0;i<items.length;i++)maxEnds[size+i]=items[i][endKey];
    for(let i=size-1;i>0;i--)maxEnds[i]=Math.max(maxEnds[i*2],maxEnds[i*2+1]);
    return {items,endKey,size,maxEnds};
  }
  function intervalsInRange(index,start,end){
    let lo=0,hi=index.items.length;while(lo<hi){const mid=(lo+hi)>>>1;if(index.items[mid].start<end)lo=mid+1;else hi=mid;}
    const found=[],limit=lo;
    function visit(node,left,right){
      if(left>=limit||index.maxEnds[node]<start)return;
      if(right-left===1){const item=index.items[left],finish=item[index.endKey];if(finish>start||(item.start===finish&&item.start>=start))found.push(item);return;}
      const middle=(left+right)>>>1;visit(node*2,left,middle);visit(node*2+1,middle,right);
    }
    if(limit)visit(1,0,index.size);return found;
  }
  function meaningfulDevice(intervals,time){let lo=0,hi=intervals.length;while(lo<hi){const mid=(lo+hi)>>>1;if(intervals[mid].start<=time)lo=mid+1;else hi=mid;}for(let i=lo-1;i>=0;i--){const item=intervals[i];if(item.kind==='button'||(item.value??1)>=.18)return inputGroup(item.device);}return 'keyboard';}
  function recentInputs(index,time,retention=2){
    const result=[],analog=new Map();
    for(const item of intervalsInRange(index,time-retention,time+1e-9)){
      if(item.start>time||item.end+retention<=time)continue;
      const value={...item,active:item.start<=time&&time<item.end};
      if(['axis','motion','trigger'].includes(item.kind))analog.set(item.device+'/'+item.code,value);
      else result.push(value);
    }
    return [...result,...analog.values()].sort((a,b)=>a.start-b.start||a.id.localeCompare(b.id));
  }
  function anchoredZoom({scale,delta,viewStart,pointerY,duration,height}){const next=Math.max(12,Math.min(240,scale*Math.exp(-Math.max(-240,Math.min(240,delta))*.0025)));const anchor=viewStart+pointerY/scale;return {scale:next,viewStart:Math.max(0,Math.min(Math.max(0,duration-height/next),anchor-pointerY/next))};}
  function timelinePointerTime({viewStart,scale,top,duration},clientY){return Math.max(0,Math.min(duration,viewStart+(clientY-top)/scale));}
  function timelineGesture(dx,dy,threshold=4){return Math.max(Math.abs(dx),Math.abs(dy))<=threshold?'pending':Math.abs(dy)>Math.abs(dx)?'vertical':'horizontal';}
  if(typeof module==='object'&&module.exports){module.exports={formatTime,activeSegment,splitBounds,sourceFit,inputChannel,axisDirection,normalizeInputs,inputLabel,inputVisualBands,inputSampleAt,packInputIntervals,intervalIndex,intervalsInRange,meaningfulDevice,recentInputs,anchoredZoom,timelinePointerTime,timelineGesture};return;}
  const data=JSON.parse(document.getElementById('review-data').textContent);
  const $=id=>document.getElementById(id),video=$('video'),lines=$('lines');
  let segments=Array.isArray(data.segments)?data.segments:[],nodes=[],inputUI=null;
  let previewInputOffset=null;
  function setTheme(value){
    document.documentElement.dataset.theme=value;
    const label=value==='dark'?'切换浅色模式':'切换深色模式';
    $('themeButton').setAttribute('aria-label',label);$('themeButton').title=label;
    try{localStorage.setItem('recorder-theme',value);}catch(_){}
  }
  try{setTheme(localStorage.getItem('recorder-theme')==='dark'?'dark':'light');}catch(_){setTheme('light');}
  $('themeButton').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
  const copySplit=$('copySplit'),fileActions=$('fileActions'),fileActionsToggle=$('fileActionsToggle');
  document.body.append(fileActions);
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
  document.addEventListener('click',event=>{if(!copySplit.contains(event.target)&&!fileActions.contains(event.target))closeFileActions();});
  for(const element of [copySplit,fileActions])element.addEventListener('focusout',event=>{if(!copySplit.contains(event.relatedTarget)&&!fileActions.contains(event.relatedTarget))closeFileActions();});
  function fileMenuKeydown(event){
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
  }
  copySplit.addEventListener('keydown',fileMenuKeydown);fileActions.addEventListener('keydown',fileMenuKeydown);
  let copyFeedbackTimer=null;
  function resetCopyFeedback(){root.clearTimeout(copyFeedbackTimer);$('copyPath').classList.remove('copied');$('copyLabel').textContent='复制资料库路径';}
  function showCopyFeedback(){resetCopyFeedback();$('copyPath').classList.add('copied');$('copyLabel').textContent='copied!';copyFeedbackTimer=root.setTimeout(resetCopyFeedback,2000);}
  let current=-1,follow=true,ready=false,mediaError=null,pendingSeek=null;
  const status=(message,error=false)=>{$('status').textContent=message;$('status').classList.toggle('error',error);};
  function updateTitle(){const title=data.session_name||data.title||data.game||'体验片段';$('title').textContent=title;$('title').title=title;document.title=title+' · 回看';const date=new Date(data.created);const created=Number.isNaN(date.getTime())?'':date.toLocaleString('zh-CN',{year:'numeric',month:'long',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});$('sessionInfo').textContent=[data.game,created].filter(Boolean).join(' · ');}
  updateTitle();
  $('testLabel').hidden=!data.test;
  const layout=document.querySelector('.review-layout'),splitter=$('reviewSplitter');
  const videoPane=$('videoPane'),textPane=$('transcriptPane'),videoSlot=videoPane.querySelector('.video-slot');
  const stacked=root.matchMedia('(max-width:760px)'),defaults={columns:1.45/2.45,rows:0.54};
  const shares={...defaults},storageKey='experience-review-layout-v1';
  const touched=new Set();
  let dragging=null,frame=null,metrics=null,columnWidth=null,initialColumnFit=false;
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
  function horizontalInsets(element){
    const style=getComputedStyle(element);
    return number(style.paddingLeft)+number(style.paddingRight)+number(style.borderLeftWidth)+number(style.borderRightWidth);
  }
  function applySplit(value){
    layout.style.setProperty('--video-share',value+'fr');
    layout.style.setProperty('--text-share',(1-value)+'fr');
  }
  function sizeVideoSlot(){
    const aspect=video.videoWidth/video.videoHeight;
    const hasSource=Number.isFinite(aspect)&&aspect>0;
    videoSlot.classList.toggle('source-aspect',hasSource);
    if(!hasSource){videoSlot.style.removeProperty('width');videoSlot.style.removeProperty('height');return;}
    const rect=videoPane.getBoundingClientRect();
    const height=Math.max(0,rect.height-fixedHeight(videoPane,videoSlot));
    const width=Math.max(0,rect.width-horizontalInsets(videoPane));
    videoSlot.style.width=width+'px';videoSlot.style.height=Math.min(height,width/aspect)+'px';
  }
  function renderSplit(){
    const mode=axis(),vertical=mode==='rows',rect=layout.getBoundingClientRect(),style=getComputedStyle(layout);
    const before=number(vertical?style.paddingTop:style.paddingLeft),after=number(vertical?style.paddingBottom:style.paddingRight);
    const divider=number(style.getPropertyValue('--splitter-size'));
    const available=Math.max(0,(vertical?rect.height:rect.width)-before-after-divider);
    const textMin=Math.max(280,textPane.querySelector('.review-tabs').scrollWidth+$('follow').offsetWidth+horizontalInsets(textPane)+12);
    if(!vertical){
      if(columnWidth===null)columnWidth=900;
      if(!initialColumnFit&&video.videoWidth>0&&video.videoHeight>0&&!touched.has(mode)){
        // 900 px is a first-open target only. Later window changes retain the
        // current left width; the right pane absorbs space until its minimum.
        const height=Math.max(0,videoPane.clientHeight-fixedHeight(videoPane,videoSlot));
        columnWidth=Math.max(900,height*video.videoWidth/video.videoHeight);initialColumnFit=true;
      }
    }
    let bounds=splitBounds(available,vertical?fixedHeight(videoPane,videoSlot)+72:240,
      vertical?fixedHeight(textPane,lines)+32:textMin,vertical?shares[mode]:columnWidth/available);
    if(!vertical){columnWidth=available*bounds.value;shares[mode]=bounds.value;}
    applySplit(bounds.value);sizeVideoSlot();
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
    shares[m.mode]=Math.max(m.min,Math.min(m.max,requested));if(!m.vertical)columnWidth=shares[m.mode]*m.available;renderSplit();
  });
  for(const name of ['pointerup','pointercancel','lostpointercapture'])splitter.addEventListener(name,finishDrag);
  root.addEventListener('blur',()=>finishDrag());
  function resetSplit(){const mode=axis();touched.delete(mode);shares[mode]=defaults[mode];if(mode==='columns'){columnWidth=null;initialColumnFit=false;}renderSplit();saveShare(mode);}
  splitter.addEventListener('dblclick',resetSplit);
  splitter.addEventListener('keydown',event=>{
    if(event.altKey||event.ctrlKey||event.metaKey||event.isComposing)return;
    const m=renderSplit(),back=m.vertical?'ArrowUp':'ArrowLeft',forward=m.vertical?'ArrowDown':'ArrowRight';
    if(![back,forward,'Home','End','Enter'].includes(event.key))return;
    event.preventDefault();event.stopPropagation();
    if(event.key==='Enter'){resetSplit();return;}
    touched.add(m.mode);
    const step=event.shiftKey?0.1:0.02;
    shares[m.mode]=event.key==='Home'?m.min:event.key==='End'?m.max:
      Math.max(m.min,Math.min(m.max,m.value+(event.key===back?-step:step)));
    if(!m.vertical)columnWidth=shares[m.mode]*m.available;renderSplit();saveShare(m.mode);
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
    if(event.target.classList?.contains('timeline-horizontal-scroll'))return;
    if(event.target.closest('input:not([type="range"]),textarea,select,[contenteditable="true"],[role="separator"],.file-card,.review-header,.copy-split,.file-actions,.input-heading,.review-tabs,.quote-popover,.alignment-panel'))return;
    if(![' ','ArrowLeft','ArrowRight'].includes(event.key))return;
    event.preventDefault();event.stopImmediatePropagation();
    if(event.key===' '){if(!event.repeat)player.togglePlay();}
    else if(event.key==='ArrowLeft')player.rewind(15);
    else player.forward(15);
  },true);
  function reportReady(){if(data.desktop&&ready&&root.pywebview?.api)root.pywebview.api.ready(mediaError).catch(()=>{});}
  function seek(time){const bounded=Math.max(0,Math.min(time,Number.isFinite(video.duration)?video.duration:time));player.currentTime=bounded;player.play().catch(()=>{});}
  function buildTranscript(){lines.replaceChildren();nodes=segments.map((segment,index)=>{
    const button=document.createElement('button');button.className='line';button.type='button';
    const time=document.createElement('time');time.textContent=formatTime(segment.start);
    const text=document.createElement('span');text.className='segment-text';text.textContent=segment.text;button.append(time,text);
    button.addEventListener('click',()=>{if(root.getSelection()?.toString())return;setFollow(true);if(video.readyState)seek(segment.start);else pendingSeek=segment.start;});
    lines.append(button);return button;
  });current=-1;filter();sync();}
  function setFollow(value){follow=value;$('follow').textContent=value?'跟随播放：开':'恢复跟随';$('follow').setAttribute('aria-pressed',String(value));inputUI?.setFollow(value);if(value)scrollCurrent();}
  function scrollCurrent(){const node=nodes[current];if(!follow||lines.hidden||!node||node.hidden)return;const top=node.offsetTop-lines.offsetTop-(lines.clientHeight-node.clientHeight)/2;lines.scrollTo({top:Math.max(0,top),behavior:'smooth'});}
  function sync(){const index=activeSegment(segments,video.currentTime);if(index===current)return;nodes[current]?.classList.remove('active');nodes[current]?.removeAttribute('aria-current');current=index;nodes[current]?.classList.add('active');nodes[current]?.setAttribute('aria-current','true');scrollCurrent();}
  $('follow').onclick=()=>setFollow(!follow);
  lines.addEventListener('wheel',()=>setFollow(false),{passive:true});
  lines.addEventListener('touchstart',()=>setFollow(false),{passive:true});
  lines.addEventListener('pointerdown',event=>{if(event.target===lines)setFollow(false);});
  lines.addEventListener('keydown',event=>{if(['PageDown','PageUp','Home','End','ArrowDown','ArrowUp'].includes(event.key))setFollow(false);});
  function filter(){const query=$('search').value.trim().toLocaleLowerCase();let count=0;nodes.forEach((node,i)=>{node.hidden=!segments[i].text.toLocaleLowerCase().includes(query);if(!node.hidden)count++;});$('lineCount').textContent=count+' 条';$('empty').hidden=count>0;$('empty').textContent=segments.length?'没有匹配的原话。':'没有识别出语音，可以继续查看录像。';}
  $('search').oninput=filter;buildTranscript();video.addEventListener('timeupdate',sync);
  video.addEventListener('loadedmetadata',()=>{ready=true;mediaError=null;status('');scheduleSplit();if(pendingSeek!==null){seek(pendingSeek);pendingSeek=null;}reportReady();});
  video.addEventListener('resize',scheduleSplit);
  video.addEventListener('error',()=>{ready=true;mediaError='录像无法加载，请检查录像.mp4 是否存在，并将资料包完整解压后打开。';status(mediaError,true);reportReady();});
  root.addEventListener('pywebviewready',reportReady);
  video.src=data.video;
  async function native(method,...args){const api=root.pywebview?.api;if(!api||typeof api[method]!=='function')throw new Error('回看窗口尚未连接，请稍后重试。');const result=await api[method](...args);if(!result?.ok)throw new Error(result?.error||'操作未完成。');return result.data;}
  function portablePath(kind){if(kind==='vault'&&!data.vault_path)throw new Error('此离线资料包没有保存原资料库路径。');if(kind==='vault'&&/^(?:[A-Za-z]:[\\/]|\\\\)/.test(data.vault_path))return data.vault_path;const file=kind==='vault'?data.vault_path:kind==='video'?'录像.mp4':kind==='transcript'?'录像.whisper.json':'.';const url=new URL(file,location.href);if(url.protocol!=='file:')return url.href;let path=decodeURIComponent(url.pathname);if(/^\/[A-Za-z]:\//.test(path))path=path.slice(1);return url.hostname?'\\\\'+url.hostname+path.replace(/\//g,'\\'):path.replace(/\//g,'\\');}
  async function copy(kind){resetCopyFeedback();if(data.desktop)await native('copy_path',kind);else{const text=portablePath(kind);try{await navigator.clipboard.writeText(text);}catch(_){const field=document.createElement('textarea');field.value=text;document.body.append(field);field.select();const copied=document.execCommand('copy');field.remove();if(!copied)throw new Error('无法自动复制，路径：'+text);}}status(mediaError||'',!!mediaError);showCopyFeedback();}
  function handle(fn){return async()=>{try{await fn();}catch(error){status(error.message,true);}};}
  document.querySelectorAll('[data-copy]').forEach(button=>button.onclick=handle(async()=>{closeFileActions(button!==$('copyPath'));await copy(button.dataset.copy);}));
  $('folder').onclick=handle(async()=>{if(data.desktop){await native('open_folder');}else{await copy('folder');status('资料路径已复制，可粘贴到文件资源管理器中打开。');}});
  document.querySelectorAll('[data-document]').forEach(button=>button.onclick=handle(async()=>{closeFileActions(true);const kind=button.dataset.document;if(data.desktop)await native('open_document',kind);else root.open(kind==='notes'?'复盘.md':'逐字稿.md','_blank');}));
  $('renameSession').hidden=!data.desktop;
  function cancelRename(){$('renameForm').hidden=true;document.querySelector('.session-title-row').hidden=false;}
  $('renameSession').onclick=()=>{$('sessionName').value=data.session_name||'';$('sessionName').placeholder='留空使用游戏／项目名';$('renameForm').hidden=false;document.querySelector('.session-title-row').hidden=true;$('sessionName').focus();$('sessionName').select();};
  $('cancelRename').onclick=cancelRename;
  $('sessionName').addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();cancelRename();}});
  $('renameForm').addEventListener('submit',async event=>{event.preventDefault();const name=$('sessionName').value.trim();const button=$('renameForm').querySelector('[type=submit]');button.disabled=true;try{const response=await native('rename_session',name);data.session_name=typeof response?.session_name==='string'?response.session_name:name;data.title=typeof response?.title==='string'?response.title:data.session_name||data.game||'体验回看';updateTitle();cancelRename();status('');}catch(error){status(error.message,true);}finally{button.disabled=false;}});

  const alignmentPanel=$('alignmentPanel'),offsetField=$('inputOffset');let restoreMeasured=false;
  function closeAlignment(){previewInputOffset=null;alignmentPanel.hidden=true;inputUI?.update();}
  function previewAlignment(){
    if(!offsetField.checkValidity()||!offsetField.value)return;
    restoreMeasured=false;previewInputOffset=Number(offsetField.value);inputUI?.update();
  }
  $('alignInputs').onclick=()=>{
    closeFileActions();restoreMeasured=false;const alignment=data.inputs?.alignment;
    offsetField.value=String(alignment?.offset_seconds||0);
    $('alignmentHint').textContent=(alignment?.source==='measured'?'已按本片段视频时间自动校准。':alignment?.source==='manual'?'此片段使用手动校准。':'此片段尚无自动校准数据。')+' 仅调整操作显示。';
    $('alignmentError').hidden=true;alignmentPanel.hidden=false;offsetField.focus();offsetField.select();
  };
  $('cancelAlignment').onclick=closeAlignment;
  alignmentPanel.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();closeAlignment();$('alignInputs').focus();}});
  offsetField.addEventListener('input',previewAlignment);
  alignmentPanel.querySelectorAll('[data-offset-step]').forEach(button=>button.onclick=()=>{offsetField.value=String(Math.max(-30,Math.min(30,Math.round((Number(offsetField.value)+Number(button.dataset.offsetStep))*1000)/1000)));previewAlignment();});
  $('resetAlignment').onclick=()=>{restoreMeasured=true;previewInputOffset=data.inputs?.alignment?.measured_offset_seconds||0;offsetField.value=String(previewInputOffset);inputUI.update();};
  $('alignmentForm').addEventListener('submit',async event=>{
    event.preventDefault();const submit=event.submitter||alignmentPanel.querySelector('[type=submit]');submit.disabled=true;
    try{
      const value=restoreMeasured?null:Number(offsetField.value);
      const alignment=data.desktop?await native('set_input_offset',value):{...data.inputs?.alignment,offset_seconds:value??data.inputs?.alignment?.measured_offset_seconds??0,source:value===null?'measured':'manual'};
      data.inputs={...data.inputs,alignment};closeAlignment();status(data.desktop?'':'已应用到本次回看；离线页面不保存设置。');
    }catch(error){$('alignmentError').textContent=error.message;$('alignmentError').hidden=false;}
    finally{submit.disabled=false;}
  });

  inputUI=installInputReview();
  // Snapshot refresh never replaces the media source or player. A completed
  // transcript can arrive while the video is playing, seeking or paused.
  let snapshotBusy=false,closed=false,snapshotTimer=null,segmentSignature=JSON.stringify(segments),snapshotRevision=null;
  async function refreshSnapshot(){
    if(closed||snapshotBusy||document.hidden||!data.desktop||!root.pywebview?.api?.get_snapshot)return;
    snapshotBusy=true;
    try{const next=await native('get_snapshot',snapshotRevision);if(!next)return;
      snapshotRevision=typeof next.revision==='string'?next.revision:null;
      if(next.unchanged===true)return;
      for(const key of ['session_name','game','title','transcription','inputs','vault_path'])if(Object.hasOwn(next,key))data[key]=next[key];
      updateTitle();const signature=JSON.stringify(next.segments);
      if(Array.isArray(next.segments)&&signature!==segmentSignature){segments=next.segments;data.segments=segments;segmentSignature=signature;buildTranscript();}
      inputUI.update();
    }catch(error){$('timelineState').title='暂时无法更新回看状态：'+error.message;}
    finally{snapshotBusy=false;}
  }
  snapshotTimer=root.setInterval(refreshSnapshot,2000);root.addEventListener('pywebviewready',refreshSnapshot);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshSnapshot();});
  root.addEventListener('pagehide',()=>{closed=true;root.clearInterval(snapshotTimer);inputUI.destroy();});
  refreshSnapshot();

  function installInputReview(){
    const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
    const deviceName=device=>({keyboard:'键盘 + 鼠标',xbox:'Xbox',dualsense:'DualSense'}[device]||'输入设备');
    const group=inputGroup;
    const mouseIcon='<svg viewBox="0 0 22 28" aria-hidden="true"><path d="M3 10a8 8 0 0 1 16 0v8a8 8 0 0 1-16 0Z"/><path d="M11 2v9M3 11h16"/></svg>';
    const quoteIcon='<svg viewBox="0 0 18 18" aria-hidden="true"><path d="M3 4h12v8H9l-4 3v-3H3Z"/><path d="M6 7h6M6 9h4"/></svg>';
    const clock=t=>{const safe=Math.max(0,t);return `${formatTime(safe)}.${Math.floor(safe%1*10)}`;};
    const preciseClock=t=>{const milliseconds=Math.max(0,Math.round(t*1000));return `${formatTime(Math.floor(milliseconds/1000))}.${String(milliseconds%1000).padStart(3,'0')}`;};
    const timeline=$('inputTimeline'),ruler=document.createElement('div');ruler.className='timeline-ruler';timeline.append(ruler);
    const layers=[$('timelineTicks'),ruler,$('timelineSpeech'),$('timelineInputs'),$('timelineGaps')];
    const headings=document.querySelector('.timeline-column-headings'),horizontal=document.createElement('div'),grid=document.createElement('div');
    const dpadHeading=document.createElement('span');dpadHeading.textContent='十字键';headings.lastElementChild.before(dpadHeading);
    horizontal.className='timeline-horizontal-scroll';horizontal.setAttribute('aria-label','横向浏览操作轨道');grid.className='timeline-grid';
    headings.before(horizontal);horizontal.append(grid);grid.append(headings,timeline);
    const inputDetail=document.createElement('div');inputDetail.id='inputDetail';inputDetail.className='input-detail';inputDetail.setAttribute('role','tooltip');inputDetail.hidden=true;document.body.append(inputDetail);
    const initialTab=(!data.inputs||['disabled','missing','unavailable'].includes(data.inputs.state))&&(data.transcription?.state||'ready')==='ready'?'transcript':'inputs';
    const state={mode:'keys',device:'auto',tab:initialTab,scale:64,viewStart:0,follow:true,signature:'',quote:null,pinned:false,lastInput:'',renderKey:'',lastClock:-1,stopped:false};
    let source=normalizeInputs(data.inputs,previewInputOffset),bands=inputVisualBands(source.intervals,source.gaps),packed=packInputIntervals(bands,{scale:state.scale}),index=intervalIndex(source.intervals),displayIndex=intervalIndex(packed.items,'displayEnd'),gapIndex=intervalIndex(source.gaps),quoteIndex=intervalIndex(segments.map((item,i)=>({...item,index:i}))),renderStart=0,raf=0;
    const packedById=()=>new Map(packed.items.map(item=>[item.id,item]));let displayed=packedById(),packedScale=state.scale;
    function duration(){return Math.max(Number.isFinite(video.duration)?video.duration:0,source.duration,segments.at(-1)?.end||0,1);}
    function glyph(item){if(item.movement)return `<span class="movement-glyph">${escape(item.direction||'•')}</span>`;if(item.device==='mouse'){const fill=item.code==='MouseLeft'?'<path fill="currentColor" stroke="none" d="M4 10a7 7 0 0 1 6-7v7Z"/>':item.code==='MouseRight'?'<path fill="currentColor" stroke="none" d="M12 3a7 7 0 0 1 6 7h-6Z"/>':item.code==='MouseMiddle'?'<rect fill="currentColor" x="9" y="4" width="4" height="7" rx="2"/>':'';const direction=item.direction||({WheelUp:'↑',WheelDown:'↓',WheelLeft:'←',WheelRight:'→',MouseX1:'4',MouseX2:'5'}[item.code])||'';return mouseIcon.replace('</svg>',fill+'</svg>')+(direction?`<span class="mouse-arrow">${escape(direction)}</span>`:'');}if(item.kind==='axis')return `<span class="axis-glyph">${item.code==='LeftStick'?'L':'R'}<span>${escape(item.direction||'•')}</span></span>`;if(/^D[Pp]ad/.test(item.code))return `<span class="dpad-glyph"><svg viewBox="0 0 18 18" aria-hidden="true"><path d="M6 1h6v5h5v6h-5v5H6v-5H1V6h5Z"/></svg><span>${escape(inputLabel(item))}</span></span>`;return escape(inputLabel(item));}
    function inputMessage(){if(source.state==='disabled'&&source.error?.includes('旧场次'))return '旧场次没有操作记录';return ({missing:'此场次没有操作记录',disabled:'此场次未启用操作记录',failed:'操作记录采集失败',unavailable:'操作记录文件不可用',invalid:'操作记录文件不可用',interrupted:'操作记录未完整保存',pending:'操作记录正在保存',recording:'操作记录正在保存'}[source.state]||'');}
    function gapName(gap){return ({focus:'已切出目标程序',focus_lost:'已切出目标程序',disconnect:'设备连接中断',device_disconnected:'设备连接中断',error:'采集异常'}[gap.type]||'采集缺口');}
    function seekKeep(time,followPlayback=true){if(!video.readyState)return;const limit=Number.isFinite(video.duration)?video.duration:duration();video.currentTime=Math.max(0,Math.min(limit,time));setFollow(followPlayback);render(followPlayback);}
    function setTab(tab){if(tab==='transcript'&&$('transcriptTab').disabled)return;state.tab=tab;$('inputTab').setAttribute('aria-selected',String(tab==='inputs'));$('transcriptTab').setAttribute('aria-selected',String(tab==='transcript'));$('inputTimelinePanel').hidden=tab!=='inputs';lines.hidden=tab!=='transcript';$('transcriptSearch').hidden=tab!=='transcript';$('empty').hidden=tab!=='transcript'||nodes.some(node=>!node.hidden);closeQuote();if(tab==='transcript')scrollCurrent();else render(true);}
    $('inputTab').onclick=()=>setTab('inputs');$('transcriptTab').onclick=()=>setTab('transcript');
    for(const button of [$('inputTab'),$('transcriptTab')])button.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const next=event.key==='Home'||event.key==='ArrowLeft'?$('inputTab'):$('transcriptTab');if(!next.disabled){next.click();next.focus();}}});
    // Device diagrams are static geometry; activity only changes fills and axes.
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
    if (renderedDevice !== device) { $('deviceView').innerHTML = device === 'keyboard' ? keyboardMarkup() : controllerMarkup(device); renderedDevice = device; }
    const visible = active.filter(item => group(item.device) === device);
    const aliases={ShiftLeft:'Shift',ControlLeft:'Control',AltLeft:'Alt',WinLeft:'Meta',BracketLeft:'[',BracketRight:']',Semicolon:';',Comma:',',Period:'.',DPadUp:'DpadUp',DPadDown:'DpadDown',DPadLeft:'DpadLeft',DPadRight:'DpadRight',LS:'LeftStick',L3:'LeftStick',RS:'RightStick',R3:'RightStick'};
    const diagramCode=item=>aliases[item.code]||(item.device==='keyboard'?item.code.replace(/^Key/, ''):item.code);
    const byCode = new Map(visible.map(item => [diagramCode(item),item]));
    $('deviceView').querySelectorAll('[data-control]').forEach(el => { const item=byCode.get(el.dataset.control); el.classList.toggle('active',!!item?.active);el.classList.toggle('recent',!!item&&!item.active); if(item?.kind==='motion') el.textContent=item.direction||'↗'; });
    $('deviceView').querySelectorAll('[data-meter]').forEach(el => el.setAttribute('width',String(48*(byCode.get(el.dataset.meter)?.value||0))));
    $('deviceView').querySelectorAll('[data-arrow]').forEach(el => { const item=byCode.get(el.dataset.arrow); el.classList.toggle('active',item?.kind==='axis'&&item.active);el.classList.toggle('recent',item?.kind==='axis'&&!item.active); const angle = {'↑':0,'↗':45,'→':90,'↘':135,'↓':180,'↙':225,'←':270,'↖':315}[item?.direction]||0; const circle=$('deviceView').querySelector(`[data-control="${el.dataset.arrow}"]`); el.setAttribute('transform',`rotate(${angle} ${circle.getAttribute('cx')} ${circle.getAttribute('cy')})`); });
    const controls=new Set([...$('deviceView').querySelectorAll('[data-control]')].map(el=>el.dataset.control));let extras=$('deviceView').querySelector('.device-extra');if(!extras){extras=document.createElement('div');extras.className='device-extra';$('deviceView').append(extras);}extras.innerHTML=visible.filter(item=>!controls.has(diagramCode(item))).map(item=>`<span class="keycap ${item.active?'active':'recent'}" title="${escape(item.label||item.code)}">${glyph(item)}</span>`).join('');extras.hidden=!extras.childElementCount;
  }

    function renderInput(time){
      const gaps=intervalsInRange(gapIndex,time,time+.000001),gap=gaps[0];
      // A disconnected controller can coexist with valid keyboard input. The
      // capture layer filters missing spans; never erase another device here.
      const active=recentInputs(index,time);
      const device=state.device==='auto'?meaningfulDevice(source.intervals,time):state.device;
      const message=active.length?'':gap?gapName(gap):inputMessage();
      const key=[state.mode,device,message,...active.map(item=>item.id+':'+item.active)].join('|');if(key===state.lastInput)return;state.lastInput=key;
      $('inputSource').textContent=source.intervals.length?deviceName(device):'操作记录';
      $('inputState').textContent=gap?(gap.reason||gapName(gap)):message?(source.error||message):active.length?'按住时高亮 · 松开后保留 2 秒':'最近 2 秒无操作';
      $('inputState').classList.toggle('is-gap',!!gap);$('inputState').title=message;
      $('currentKeys').hidden=state.mode!=='keys'||!!message;$('deviceView').hidden=state.mode!=='device'||!!message;
      $('currentKeys').innerHTML=active.map(item=>`<div class="current-item" data-recent-id="${escape(item.id)}"><span class="keycap ${item.active?'active':'recent'}">${glyph(item)}</span><span>${escape(/^D[Pp]ad/.test(item.code)?'十字键':item.label||item.code)}${item.value!=null&&item.kind!=='button'?` · ${Math.round(item.value*100)}%`:''}</span></div>`).join('');
      if(state.mode==='device')renderDevice(device,active);
    }
    document.querySelectorAll('[data-input-mode]').forEach(button=>button.onclick=()=>{state.mode=button.dataset.inputMode;document.querySelectorAll('[data-input-mode]').forEach(node=>node.setAttribute('aria-pressed',String(node===button)));$('inputBody').hidden=state.mode==='collapsed';$('deviceSelectLabel').hidden=state.mode!=='device';$('inputPanel').classList.toggle('is-collapsed',state.mode==='collapsed');state.lastInput='';renderInput(video.currentTime);});
    $('deviceSelect').onchange=event=>{state.device=event.target.value;state.lastInput='';renderInput(video.currentTime);};
    function geometry(){
      const styles=getComputedStyle(textPane),n=name=>parseFloat(styles.getPropertyValue(name));
      const g={time:n('--time-width'),speech:n('--speech-width'),direction:n('--direction-width'),pointing:n('--pointing-width'),dpad:packed.counts.dpad?48:0};
      dpadHeading.style.visibility=g.dpad?'visible':'hidden';
      g.other=Math.max(44,packed.widths.other.reduce((sum,width)=>sum+width+4,4),horizontal.clientWidth-g.time-g.speech-g.direction-g.pointing-g.dpad);
      for(const channel of ['time','speech','direction','pointing','dpad','other'])grid.style.setProperty('--'+channel+'-width',g[channel]+'px');
      grid.style.width=(g.time+g.speech+g.direction+g.pointing+g.dpad+g.other)+'px';
      return g;
    }
    function column(item,g){const channel=item.channel,left=g.time+g.speech+(channel==='direction'?0:channel==='pointing'?g.direction:channel==='dpad'?g.direction+g.pointing:g.direction+g.pointing+g.dpad);return item.fixed?{left:left+5,width:g[channel]-10}:{left:left+4+packed.widths[channel].slice(0,item.lane).reduce((sum,width)=>sum+width+4,0),width:packed.widths[channel][item.lane]};}
    function repack(){packed=packInputIntervals(bands,{scale:state.scale});displayIndex=intervalIndex(packed.items,'displayEnd');displayed=packedById();packedScale=state.scale;}
    function pointerTime(event,item){return event?.clientY!=null?state.viewStart+(event.clientY-timeline.getBoundingClientRect().top)/state.scale:item.start;}
    function hideInputDetail(){inputDetail.hidden=true;}
    function showInputDetail(item,event){
      const time=pointerTime(event,item),sample=inputSampleAt(item,time),label=sample?.label||item.label||item.code;
      const value=sample?.value!=null?` · ${Math.round(sample.value*100)}%`:'';
      const detail=sample?`${sample.direction||inputLabel(sample)}${item.activity&&time>=sample.end?' · 上次输入（已松开）':''}${value}${sample.x!=null?` · X ${sample.x} / Y ${sample.y}`:''}`:item.end===item.start?'瞬时操作':'此刻已松开';
      inputDetail.innerHTML=`<time>${preciseClock(item.start)} — ${preciseClock(item.end)}</time><strong>${escape(deviceName(group(sample?.device||item.device))+' · '+label)}</strong><span>${preciseClock(Math.max(item.start,time))} · ${escape(detail.trim()||'持续中')}</span>`;
      inputDetail.hidden=false;const rect=event?.currentTarget?.getBoundingClientRect()||timeline.getBoundingClientRect();
      inputDetail.style.left=Math.max(12,Math.min(root.innerWidth-inputDetail.offsetWidth-12,(event?.clientX??rect.right)+14))+'px';
      inputDetail.style.top=Math.max(12,Math.min(root.innerHeight-inputDetail.offsetHeight-12,(event?.clientY??rect.top)+14))+'px';
    }
    function inputMarks(item){
      if(!item.fixed||!item.samples)return '';
      const start=Math.max(item.start,state.viewStart-1),end=state.viewStart+timeline.clientHeight/state.scale+1;
      let lastPixel=-Infinity;
      return intervalsInRange(item.markIndex,start,end).map(sample=>{
        const top=(sample.start-item.start)*state.scale;
        if(top-lastPixel<2)return ''; // Coincident samples share one timing mark.
        lastPixel=top;
        return `<span class="input-mark" style="top:${top}px" aria-hidden="true"></span>`;
      }).join('');
    }
    function rebuild(){
      if(packedScale!==state.scale)repack();
      const g=geometry(),height=timeline.clientHeight,span=height/state.scale;hideInputDetail();
      renderStart=Math.max(0,state.viewStart-span*.5);const end=Math.min(duration(),state.viewStart+span*1.5);
      const visible=intervalsInRange(displayIndex,renderStart,end),quotes=intervalsInRange(quoteIndex,renderStart,end),gaps=intervalsInRange(gapIndex,renderStart,end);
      const tickStep=state.scale<24?5:state.scale<46?2:1,ticks=[];
      for(let t=Math.ceil(renderStart/tickStep)*tickStep;t<=end;t+=tickStep)ticks.push(`<div class="time-tick" style="top:${(t-renderStart)*state.scale}px"><time>${formatTime(t)}</time></div>`);
      $('timelineTicks').innerHTML=ticks.join('').replace(/<time>.*?<\/time>/g,'');ruler.innerHTML=ticks.join('');
      $('timelineInputs').innerHTML=visible.map(item=>{const c=column(item,g);return `<button class="key-bar${item.activity?' activity-band':''}${item.fixed?' fixed-band':''}${item.end===item.start?' instant':''}" data-input-id="${escape(item.id)}" data-start="${item.start}" data-end="${item.end}" data-lane="${item.lane}" data-channel="${item.channel}" style="top:${(item.start-renderStart)*state.scale}px;height:${(item.displayEnd-item.start)*state.scale}px;left:${c.left}px;width:${c.width}px" aria-label="${escape(`${deviceName(group(item.device))} ${item.label||item.code}，${clock(item.start)} 至 ${clock(item.end)}，点击定位`)}" aria-describedby="inputDetail"><span class="bar-glyph">${glyph(item)}</span><span class="bar-duration" style="height:${Math.max(1,(item.end-item.start)*state.scale)}px" aria-hidden="true"></span>${inputMarks(item)}</button>`;}).join('');
      $('timelineSpeech').innerHTML=quotes.map(item=>`<button class="quote-bar" data-quote="${item.index}" style="top:${(item.start-renderStart)*state.scale}px;height:${(item.end-item.start)*state.scale}px;left:${g.time+7}px;width:${g.speech-14}px" aria-label="原话 ${item.index+1}，${clock(item.start)}，点击固定全文">${quoteIcon}<span>${String(item.index+1).padStart(2,'0')}</span></button>`).join('');
      $('timelineGaps').innerHTML=gaps.map(gap=>`<div class="timeline-gap" style="top:${(gap.start-renderStart)*state.scale}px;height:${(gap.end-gap.start)*state.scale}px;left:${g.time+g.speech}px" title="${escape(gap.reason||gapName(gap))}"><span>${escape(gapName(gap))}</span></div>`).join('');
      $('timelineInputs').querySelectorAll('button').forEach(button=>{const item=displayed.get(button.dataset.inputId);
        button.onclick=event=>{if(event.detail&&event.clientX<horizontal.getBoundingClientRect().left+g.time)return;hideInputDetail();seekKeep(item.samples&&event.detail?Math.max(item.start,Math.min(item.end,pointerTime(event,item))):item.start);};
        button.onpointermove=event=>{if(!gesture||gesture.kind==='pending')showInputDetail(item,event);};button.onfocus=()=>showInputDetail(item,{currentTarget:button});button.onmouseleave=hideInputDetail;button.onblur=hideInputDetail;
      });
      $('timelineSpeech').querySelectorAll('button').forEach(button=>{
        button.onmouseenter=()=>{if(!state.pinned&&!gesture&&!hoverSuppressed)showQuote(Number(button.dataset.quote),button,false);};
        button.onfocus=()=>{if(!state.pinned)showQuote(Number(button.dataset.quote),button,false);};
        button.onmouseleave=event=>{if(!state.pinned&&!$('quotePopover').contains(event.relatedTarget))closeQuote();};
        button.onblur=event=>{if(!state.pinned&&!$('quotePopover').contains(event.relatedTarget))closeQuote();};
        button.onclick=event=>{event.stopPropagation();showQuote(Number(button.dataset.quote),button,true);};
      });
    }
    function showQuote(i,anchor,pinned){const segment=segments[i];if(!segment)return;state.quote=i;state.pinned=pinned;$('quoteTime').textContent=clock(segment.start)+' — '+clock(segment.end);$('quoteText').textContent=segment.text;const popover=$('quotePopover');popover.hidden=false;const rect=anchor.getBoundingClientRect();popover.style.left=Math.max(12,Math.min(root.innerWidth-popover.offsetWidth-12,rect.right+12))+'px';popover.style.top=Math.max(12,Math.min(root.innerHeight-popover.offsetHeight-12,rect.top))+'px';$('timelineSpeech').querySelectorAll('button').forEach(button=>button.classList.toggle('pinned',pinned&&Number(button.dataset.quote)===i));}
    function closeQuote(){state.quote=null;state.pinned=false;$('quotePopover').hidden=true;$('timelineSpeech').querySelectorAll('.pinned').forEach(button=>button.classList.remove('pinned'));}
    $('quoteClose').onclick=closeQuote;$('quotePopover').onmouseleave=event=>{if(!state.pinned&&!event.relatedTarget?.closest?.('.quote-bar'))closeQuote();};
    document.addEventListener('click',event=>{if(!$('quotePopover').contains(event.target)&&!event.target.closest('.quote-bar'))closeQuote();});document.addEventListener('keydown',event=>{if(event.key==='Escape')closeQuote();});
    function render(force=false){
      const time=video.currentTime||0;if(!force&&time===state.lastClock)return;state.lastClock=time;renderInput(time);sync();if(state.tab!=='inputs'||timeline.clientHeight<=0)return;
      const height=timeline.clientHeight,span=height/state.scale;
      if(state.follow)state.viewStart=Math.max(0,Math.min(Math.max(0,duration()-span),time-span*.38));
      const key=[Math.floor(state.viewStart/(Math.max(span*.45,.1))),state.scale,timeline.clientWidth,height,state.signature].join('/');
      if(force||key!==state.renderKey){state.renderKey=key;rebuild();}
      const offset=(renderStart-state.viewStart)*state.scale;layers.forEach(layer=>layer.style.transform=`translateY(${offset}px)`);
      $('timelinePlayhead').style.top=((time-state.viewStart)*state.scale)+'px';$('timelinePlayhead').querySelector('time').textContent=clock(time);
      $('timelineInputs').querySelectorAll('button').forEach(button=>{
        const item=displayed.get(button.dataset.inputId),start=item.start,end=item.end;
        const sample=inputSampleAt(item,time),inBand=start<=time&&time<end;
        button.classList.toggle('active',inBand&&!!sample);
        const label=button.firstElementChild;
        if(item.fixed){
          label.hidden=!sample;
          label.style.transform=`translateY(${Math.max(0,(time-start)*state.scale-14)}px)`;
          if(sample){const signature=sample.code+'/'+sample.direction;if(label.dataset.direction!==signature){label.innerHTML=glyph(sample);label.dataset.direction=signature;}}
        }else{
          const labelTop=Math.max(0,Math.min((state.viewStart-start)*state.scale,(item.displayEnd-start)*state.scale-28));label.style.transform=`translateY(${labelTop}px)`;
        }
      });
      $('timelineSpeech').querySelectorAll('button').forEach(button=>{const s=segments[Number(button.dataset.quote)];button.classList.toggle('active',s.start<=time&&time<s.end);});
      $('timelineScale').textContent=(state.scale/64).toFixed(1)+'×';
    }
    timeline.addEventListener('wheel',event=>{event.preventDefault();if(gesture)return;const rect=timeline.getBoundingClientRect(),unit=event.deltaMode===1?16:event.deltaMode===2?rect.height:1,delta=event.deltaY*unit;hideInputDetail();if(Math.abs(event.deltaX)>Math.abs(event.deltaY)){horizontal.scrollLeft+=event.deltaX*unit;return;}if(event.clientX-horizontal.getBoundingClientRect().left<geometry().time){const z=anchoredZoom({scale:state.scale,delta,viewStart:state.viewStart,pointerY:event.clientY-rect.top,duration:duration(),height:rect.height});state.scale=z.scale;state.viewStart=z.viewStart;setFollow(false);render(true);}else{seekKeep(video.currentTime+delta/state.scale);}if(!state.pinned)closeQuote();},{passive:false});
    timeline.addEventListener('keydown',event=>{if(['PageDown','PageUp','ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();const sign=['PageUp','ArrowUp'].includes(event.key)?-1:1;seekKeep(event.key==='Home'?0:event.key==='End'?duration():video.currentTime+sign*(event.key.startsWith('Page')?timeline.clientHeight/state.scale*.8:1));}});
    horizontal.addEventListener('scroll',()=>{grid.style.setProperty('--timeline-scroll-x',horizontal.scrollLeft+'px');hideInputDetail();if(!state.pinned)closeQuote();});
    horizontal.addEventListener('keydown',event=>{if(event.target===horizontal&&['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();event.stopPropagation();horizontal.scrollLeft+=event.key==='ArrowLeft'?-80:80;}});horizontal.tabIndex=0;
    document.addEventListener('keydown',event=>{if(event.key==='Escape')hideInputDetail();});
    const observer=new ResizeObserver(()=>{state.renderKey='';render(true);});observer.observe(horizontal);
    // Capture only an established vertical drag, on the stable viewport rather
    // than a bar that may be rebuilt by a snapshot or scrolling animation.
    let gesture=null,suppressedClick=null,hoverSuppressed=false;
    const clearClickSuppression=()=>{suppressedClick=null;};
    const blockTailClick=event=>{if(event.detail>0&&suppressedClick&&performance.now()<suppressedClick.until&&(event.pointerId==null||event.pointerId===suppressedClick.id)){event.preventDefault();event.stopImmediatePropagation();suppressedClick=null;}};
    function finishGesture(event,complete=false){
      if(!gesture||(event?.pointerId!=null&&event.pointerId!==gesture.id))return;
      const previous=gesture;gesture=null;timeline.classList.remove('is-scrubbing');
      if(timeline.hasPointerCapture(previous.id))timeline.releasePointerCapture(previous.id);
      if(previous.kind==='vertical'){
        if(complete)seekKeep(timelinePointerTime(previous,event.clientY),false);
        state.viewStart=previous.viewStart;state.scale=previous.scale;setFollow(false);render();
      }else{
        state.follow=previous.follow;
        const bounds=horizontal.getBoundingClientRect(),inside=complete&&event.clientX>=bounds.left&&event.clientX<=bounds.right&&event.clientY>=previous.top&&event.clientY<=previous.bottom;
        if(inside&&previous.kind==='pending'){
          const time=timelinePointerTime(previous,event.clientY);
          if(previous.quote){const i=segments.findIndex(segment=>segment.start===previous.quote.start&&segment.end===previous.quote.end&&segment.text===previous.quote.text);const button=i<0?null:$('timelineSpeech').querySelector(`[data-quote="${i}"]`);if(button)showQuote(i,button,true);else closeQuote();}
          else if(previous.item){const item=previous.item;closeQuote();hideInputDetail();seekKeep(item.samples?Math.max(item.start,Math.min(item.end,time)):item.start);}
          else{closeQuote();seekKeep(time,false);}
        }
      }
      if(complete||previous.kind!=='pending')suppressedClick={id:previous.id,until:performance.now()+500};
    }
    timeline.addEventListener('pointerdown',event=>{
      if(event.button!==0||event.isPrimary===false||gesture||!video.readyState)return;
      if(event.target.closest('button,input,a,select')&&!event.target.closest('.key-bar,.quote-bar'))return;
      const rect=timeline.getBoundingClientRect(),ruler=event.clientX-horizontal.getBoundingClientRect().left<geometry().time;
      const button=ruler?null:event.target.closest('.key-bar,.quote-bar');
      const quote=button?.dataset.quote!=null?segments[Number(button.dataset.quote)]:null;
      gesture={id:event.pointerId,x:event.clientX,y:event.clientY,viewStart:state.viewStart,scale:state.scale,top:rect.top,bottom:rect.bottom,duration:Number.isFinite(video.duration)?video.duration:duration(),follow:state.follow,kind:'pending',item:button?.dataset.inputId?displayed.get(button.dataset.inputId):null,quote:quote?{start:quote.start,end:quote.end,text:quote.text}:null};hoverSuppressed=false;
      state.follow=false;hideInputDetail();event.preventDefault();
    });
    function moveGesture(event){
      if(!gesture){hoverSuppressed=false;return;}if(event.pointerId!==gesture.id)return;
      if(!(event.buttons&1)){finishGesture(event);return;}
      if(gesture.kind==='pending'){
        gesture.kind=timelineGesture(event.clientX-gesture.x,event.clientY-gesture.y);
        if(gesture.kind==='vertical'){timeline.setPointerCapture(event.pointerId);timeline.classList.add('is-scrubbing');hoverSuppressed=true;closeQuote();setFollow(false);}
      }
      if(gesture.kind==='vertical'){event.preventDefault();state.viewStart=gesture.viewStart;state.scale=gesture.scale;seekKeep(timelinePointerTime(gesture,event.clientY),false);}
    }
    const endGesture=event=>finishGesture(event,true),cancelGesture=event=>finishGesture(event),blurGesture=()=>finishGesture();
    root.addEventListener('pointermove',moveGesture,{passive:false});root.addEventListener('pointerup',endGesture);root.addEventListener('pointercancel',cancelGesture);root.addEventListener('blur',blurGesture);
    timeline.addEventListener('lostpointercapture',cancelGesture);document.addEventListener('pointerdown',clearClickSuppression,true);document.addEventListener('click',blockTailClick,true);
    function update(){
      const next=JSON.stringify([data.inputs,segments,data.transcription,previewInputOffset]);if(next===state.signature)return;
      state.signature=next;source=normalizeInputs(data.inputs,previewInputOffset);bands=inputVisualBands(source.intervals,source.gaps);repack();index=intervalIndex(source.intervals);gapIndex=intervalIndex(source.gaps);
      const transcript=data.transcription?.state||'ready',isReady=transcript==='ready';quoteIndex=intervalIndex(isReady?segments.map((item,i)=>({...item,index:i})):[]);$('transcriptTab').disabled=!isReady;$('transcriptTab').textContent=isReady?'原话':transcript==='failed'?'转写失败':'转写中';$('transcriptTab').title=data.transcription?.error||'';
      if(!isReady&&state.tab==='transcript')setTab('inputs');
      const message=inputMessage();$('timelineState').textContent=message||`${bands.length} 段记录${source.gaps.length?' · '+source.gaps.length+' 处缺口':''}`;$('timelineState').title=source.error||message||`${source.intervals.length} 个原始采样区间；方向、指向及十字键固定窄轨道；虚线浅色为合并活动，短横线为实际输入。其它键帽最小 28px，左侧细线表示真实持续时间。`;
      state.lastInput='';closeQuote();setTab(state.tab);render(true);
    }
    function frame(){if(state.stopped)return;render();raf=root.requestAnimationFrame(frame);}
    update();frame();return {update,setFollow(value){state.follow=value;if(value)render(true);},destroy(){finishGesture();state.stopped=true;root.cancelAnimationFrame(raf);observer.disconnect();inputDetail.remove();root.removeEventListener('pointermove',moveGesture);root.removeEventListener('pointerup',endGesture);root.removeEventListener('pointercancel',cancelGesture);root.removeEventListener('blur',blurGesture);document.removeEventListener('pointerdown',clearClickSuppression,true);document.removeEventListener('click',blockTailClick,true);}};
  }
})(globalThis);
