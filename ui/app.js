'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon=name=>`<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const store=new RecorderState.State();
const providerNames={later:'仅保存录制',local:'在本机转成文字',qwen:'Qwen 云端转写'};
let pollTask=null,booted=false,firstSetupHandled=false,toastTimer=null,step=0,saving=false,wizardMode='edit',sheetMode=null,sheetTab='game';
let libraryRootDraft=null,gamesSignature='',lastSignature='',currentBlockers=[];
let downloadDirectory=null,presetSignature='',deviceSignature='',sessionSignature='',expandedSession=null,vocabularySignature='';
let dialogGeneration=0,connectionMessage='',lastActivitySignature='',actionContext=null;
let deviceInventoryRequest=null;
let updatePending='',updateError='',updateChannelDirty=false,updateInstallAccepted=false;
let microphoneRequest=null,microphoneSession=null,microphoneUpdated=0;
let microphoneQuiet=0,microphoneWarning=false;
const setText=(id,value)=>{const n=document.getElementById(id);const text=String(value??'');if(n.textContent!==text)n.textContent=text;};
const show=(id,value)=>document.getElementById(id).classList.toggle('hidden',!value);
function notify(message){clearTimeout(toastTimer);setText('toast',message);$('#toast').classList.add('show');toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),6000);}
function wizardError(message=''){setText('wizardError',message);show('wizardError',!!message);}
// Light only: the native frame strip takes the paper color.
function applyFrameColor(){const paper=getComputedStyle(document.documentElement).getPropertyValue('--paper').trim();try{window.pywebview?.api?.win_set_frame_color?.(paper)?.catch?.(()=>{});}catch(_){}}
// Self-drawn title bar: the buttons hand back to Windows (window_chrome.py); dragging is the CSS app-region.
function windowCommand(name){try{window.pywebview?.api?.['win_'+name]?.()?.catch?.(()=>{});}catch(_){}}
$('#winMin').onclick=()=>windowCommand('minimize');$('#winMax').onclick=()=>windowCommand('toggle_maximize');$('#winClose').onclick=()=>windowCommand('close');
function sheetOpen(){return !$('#sheet').classList.contains('hidden');}
async function api(method,...args){if(!window.pywebview?.api?.[method])throw new Error('尚未连接记录器，请稍后重试。');const response=await window.pywebview.api[method](...args);if(!response||response.ok!==true){const error=new Error(response?.error||'操作未完成，请检查后重试。');error.code=response?.code;throw error;}return response.data;}
function poll(){if(pollTask)return pollTask;pollTask=(async()=>{try{const snapshot=await api('get_state');store.accept(snapshot);connectionMessage='';render();return true;}catch(error){store.disconnect();connectionMessage=error.message||'连接中断，请稍后重试。';renderHome();renderControls();return false;}finally{pollTask=null;}})();return pollTask;}
async function freshPoll(){if(pollTask)await pollTask;return poll();}
async function action(method,args=[],success='',context=null){if(store.requestPending){notify('请等待当前请求完成。');return {ok:false};}store.requestPending=true;actionContext=context;renderControls();try{const data=await api(method,...args);const fresh=await freshPoll();if(success)notify(success);return {ok:true,data,fresh};}catch(error){reportError(error.message||'操作未完成。');return {ok:false};}finally{store.requestPending=false;renderControls();}}
function reportError(message){if(sheetOpen()){wizardError(message);$('#wizardBody').scrollTop=0;}else showDialog('操作未完成','<p>'+escapeHTML(message)+'</p>');}
function showDialog(title,body,actions=[]){const generation=++dialogGeneration;if($('#actionDialog').open)$('#actionDialog').close();$('#actionDialog').classList.toggle('method-dialog',title==='让想法跟上体验');$('#actionBody').innerHTML='<h2 id="actionTitle">'+escapeHTML(title)+'</h2>'+body;$('#actionFooter').replaceChildren();const close=document.createElement('button');close.className='secondary-button';close.textContent='关闭';close.onclick=()=>$('#actionDialog').close();$('#actionFooter').append(close);for(const item of actions){const button=document.createElement('button');button.className=item.primary?'primary-button':'secondary-button';button.textContent=item.label;button.onclick=async()=>{button.disabled=true;try{const result=await item.run();if(result!==false&&result?.ok!==false&&generation===dialogGeneration&&$('#actionDialog').open)$('#actionDialog').close();}catch(error){reportError(error.message);}finally{button.disabled=false;}};$('#actionFooter').append(button);}$('#actionDialog').showModal();}
function formatTime(value){if(value==null||value==='')return '—';if(typeof value==='string'&&value.includes(':'))return value;const n=Math.max(0,Math.floor(Number(value)||0));return [Math.floor(n/3600),Math.floor(n/60)%60,n%60].map(x=>String(x).padStart(2,'0')).join(':');}
function formatDate(value){const raw=String(value??'').trim();if(!raw)return '—';const date=new Date(raw);if(Number.isNaN(date.getTime()))return raw;const pad=n=>String(n).padStart(2,'0');return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;}
function bytes(value){let n=Number(value)||0;if(n<1024)return n+' B';let unit=0;n/=1024;const units=['KiB','MiB','GiB','TiB'];while(n>=1024&&unit<3){n/=1024;unit++;}return n.toFixed(n<10?2:1)+' '+units[unit];}
function updateState(){return RecorderState.updateView(store.snapshot?.updates,store.connected,$('#updateChannel').value==='preview');}
function renderLastInstall(raw){
 const result=RecorderState.lastInstallView(raw);show('updateLastResult',!!result);if(!result)return;
 $('#updateLastResult').classList.toggle('warning',result.warning);setText('updateLastTitle',result.title);
 setText('updateLastMeta',[result.version?'v'+result.version.replace(/^v/i,''):'',result.time?formatDate(new Date(result.time*1000).toISOString()):''].filter(Boolean).join(' · '));
 setText('updateLastMessage',result.message||'未提供详细结果，请保留更新报告。');
 show('updateBackupArea',!!result.backupPath);if($('#updateBackupPath').value!==result.backupPath)$('#updateBackupPath').value=result.backupPath;
 const recoveryValue=result.recoveryPath;show('updateRecoveryArea',!!recoveryValue);
 setText('updateRecoveryLabel','恢复文件 · 可选中复制');if($('#updateRecoveryValue').value!==recoveryValue)$('#updateRecoveryValue').value=recoveryValue;
 show('updateRecoveryHint',result.recovery);
 setText('updateRecoveryHint',result.recoveryPath?'请先关闭记录器、回看窗口，以及从该目录启动的 OBS，再双击下面的恢复文件。恢复完成前请保留备份。':'请保留备份与更新事务文件。恢复步骤见软件目录中的 docs/updates.md；恢复前请关闭记录器和回看窗口。');
}
function renderUpdates(){
 const raw=store.snapshot?.updates;
 if(!updateChannelDirty)$('#updateChannel').value=raw?.include_prerelease===true?'preview':'stable';
 const u=updateState(),version=value=>String(value||'').replace(/^v/i,''),currentKnown=!!u.current_version&&u.current_version!=='unknown';
 renderLastInstall(u.last_install);
 if(updateInstallAccepted&&store.connected&&store.snapshot?.closing===false&&u.error)updateInstallAccepted=false;
 const hasUpdate=['available','downloading','verifying','ready'].includes(u.state)&&!!u.latest_version;
 const versionLabel=currentKnown?'v'+version(u.current_version):'版本与更新';
 setText('updateCurrent',currentKnown?'v'+version(u.current_version):u.current_version==='unknown'?'版本未知':'尚未获取');
 setText('updateLatest',u.latest_version?'v'+version(u.latest_version):u.state==='no_release'?'暂无发布':'尚未检查');
 const status={idle:['尚未检查更新','点击检查更新，查看当前频道的可用版本。'],checking:['正在检查更新','正在获取 GitHub Release 信息…'],available:['有新版本可用','下载完成并校验后，再由你确认退出更新。'],current:['已是当前频道的最新版本','暂时没有更新版本。'],no_release:['此频道暂无可用版本','稍后重试，或查看 Release 页面。'],downloading:['正在下载更新','关闭此窗口后，下载仍会继续。'],verifying:['正在校验更新','正在确认下载的文件是否完整。'],ready:['更新已下载并校验','准备好后，可退出记录器并安装更新。'],installing:['正在退出并更新','更新完成后会重新打开记录器。'],error:['更新未完成','可以重试，或前往 Release 页面查看。']};
 let [heading,detail]=status[u.state];
 if(!u.present){heading='暂时无法读取更新信息';detail='请等待记录器连接，或重新打开软件后再试。';}
 if(!store.connected){heading='记录器连接已中断';detail='重新连接后才能检查或安装更新。';}
 if(u.channelChanged&&!u.busy){heading='更新频道已更改';detail='请先检查更新，确认此频道的可用版本。';}
 if(updateInstallAccepted){heading='正在退出并更新';detail='更新完成后会重新打开记录器。';}
 if(u.cancelPending){heading='取消尚未确认';detail='请保留记录器窗口。取消确认前不能关闭软件，请重试取消。';}
 setText('updateStatus',heading);setText('updateDetail',detail);
 const error=updateError||u.error||'';setText('updateError',error);show('updateError',!!error);
 const downloading=['downloading','verifying'].includes(u.state);show('updateProgressArea',downloading);
 setText('updateProgressLabel',u.state==='verifying'?'正在校验':'正在下载');
 setText('updateBytes',bytes(u.downloaded_bytes)+(u.total_bytes?' / '+bytes(u.total_bytes):''));
 if(u.total_bytes&&u.state==='downloading')$('#updateProgress').value=Math.min(100,u.downloaded_bytes/u.total_bytes*100);else $('#updateProgress').removeAttribute('value');
 show('updateReleaseInfo',!!u.latest_version);setText('updateNotes',u.notes||'此版本未提供更新说明。');setText('updateSize',u.total_bytes?'软件包 '+bytes(u.total_bytes):'');
 show('updateInstallInfo',u.state==='ready'&&!u.cancelPending);setText('updateCloseSummary','将关闭记录器和 '+u.review_count+' 个回看窗口。');
 const blockers=[...u.blockers];if(u.state==='ready'&&!u.can_install&&!blockers.length)blockers.push('正在等待记录器确认是否可以更新。');
 $('#updateBlockers').innerHTML=blockers.map(message=>'<li>'+escapeHTML(message)+'</li>').join('');show('updateBlockers',blockers.length>0);
 const locked=!!updatePending||updateInstallAccepted;
 $('#updateChannel').disabled=!u.present||!store.connected||u.busy||locked;
 $('#updateCheck').disabled=!u.canCheck||locked;setText('updateCheck',updatePending==='check'||u.state==='checking'?'正在检查…':u.state==='error'?'重新检查':'检查更新');
 show('updateCheck',!u.cancelPending&&!['downloading','verifying','installing'].includes(u.state)&&!updateInstallAccepted);
 show('updateCancel',u.cancelPending||['checking','downloading'].includes(u.state));setText('updateCancel',u.cancelPending?(updatePending==='cancel'?'正在重试…':'重试取消'):u.state==='checking'?'取消检查':'取消下载');$('#updateCancel').disabled=!store.connected||!!updatePending||updateInstallAccepted&&!u.cancelPending;
 show('updateDownload',!u.cancelPending&&['available','error'].includes(u.state)&&!!u.latest_version);$('#updateDownload').disabled=!u.canDownload||locked;setText('updateDownload',updatePending==='download'?'正在准备…':u.state==='error'?'重试下载':'下载更新');
 show('updateInstall',!u.cancelPending&&(u.state==='ready'||u.state==='installing'||updateInstallAccepted));$('#updateInstall').disabled=!u.canInstall||locked;setText('updateInstall',updatePending==='install'||updateInstallAccepted||u.state==='installing'?'正在退出…':'退出并更新');
 $('#updateRelease').disabled=!u.present||!store.connected||locked||u.cancelPending;
}
async function updateAction(actionName){
 const u=updateState();if(updatePending||updateInstallAccepted&&!(actionName==='cancel'&&u.cancelPending))return;
 if(u.cancelPending&&actionName!=='cancel')return;
 if(actionName==='check'&&!u.canCheck||actionName==='download'&&!u.canDownload||actionName==='install'&&!u.canInstall)return;
 if(!u.present||!store.connected)return;
 updatePending=actionName;updateError='';renderUpdates();
 try{
  const request={action:actionName};if(actionName==='check')request.include_prerelease=$('#updateChannel').value==='preview';
  await api('update_action',request);
  if(actionName==='install')updateInstallAccepted=true;
  if(actionName==='check')updateChannelDirty=false;
  await freshPoll();
 }catch(error){updateError=error.message||'更新未完成，请重试。';}
 finally{updatePending='';renderUpdates();}
}
// Update availability: a dot on the settings gear, the 通用 tab and the 版本与更新 heading.
function renderUpdateBadge(){const u=updateState(),has=['available','downloading','verifying','ready'].includes(u.state)&&!!u.latest_version;$('#settingsButton').classList.toggle('badge',has);$('#tabGeneral').classList.toggle('badge',has);$('#updateGroup').classList.toggle('badge-text',has);$('#settingsButton').title=has?'设置 · 有新版本 v'+String(u.latest_version).replace(/^v/i,''):'设置';$('#settingsButton').setAttribute('aria-label',$('#settingsButton').title);}
$('#updateChannel').onchange=()=>{updateChannelDirty=true;updateError='';renderUpdates();};
$('#updateCheck').onclick=()=>updateAction('check');$('#updateDownload').onclick=()=>updateAction('download');$('#updateCancel').onclick=()=>updateAction('cancel');$('#updateInstall').onclick=()=>updateAction('install');$('#updateRelease').onclick=()=>updateAction('open_release');
function render(){renderHome();renderGames();renderLast();renderInsight();if(store.draft){completeDeviceSetup();renderDeviceOptions();renderResources();renderVaultChoice();renderVocabulary();}renderControls();const a=store.activity;const signature=JSON.stringify([a.kind,a.status,a.detail]);if(signature!==lastActivitySignature){lastActivitySignature=signature;if(sheetOpen()&&a.status==='操作未完成'&&a.detail)wizardError(a.detail);else if(!sheetOpen()&&store.readiness.ready&&a.status==='操作未完成'&&a.detail)notify('上次操作未完成：'+a.detail);if(sheetOpen()&&actionContext==='verify'&&a.kind==='idle'&&a.detail)setText('cloudFeedback',a.detail);}
 if(!firstSetupHandled&&store.snapshot){firstSetupHandled=true;if(!store.presets.length&&!store.recording)openSheet('first');}}
// What the ready record block lists under 已就绪: the target and the microphone (with input capture when on).
function readyLines(){const c=store.saved;return [c.source==='整个显示器'?'整个显示器 · '+deviceLabel('monitor',c.monitor):'游戏窗口 · '+deviceLabel('window',c.window),'麦克风'+(c.record_inputs?' · 操作记录':'')];}
function liveSummary(){const c=store.saved;return [c.source==='整个显示器'?'录整个显示器':'只录游戏窗口',String(c.preset||'').split(' ').pop(),c.record_inputs?'操作记录中':'',providerNames[c.transcription_provider]||''].filter(Boolean).join('　');}
function renderHome(){
 const a=store.activity,r=store.readiness,recording=store.recording;
 syncMicrophoneVisibility();
 const closing=!!store.snapshot?.closing;
 const foreground=!!a.busy&&!['devices','idle'].includes(a.kind);
 const checking=r.checking===true||a.kind==='devices'&&a.busy===true;
 const errors=Array.isArray(r.errors)?r.errors:[];
 let label=store.presets.length?'':'先在设置里添加一个游戏',button='开始录制';
 if(recording){
  label=/中断|异常|失败/.test(a.status||'')?a.status:'';
  if(microphoneWarning)label=(/中断|异常/.test(label)?label+'；':'')+'超过 2 分钟未检测到麦克风声音';
  button=store.saved.transcription_provider==='later'?'结束并保存':'结束录制';
 }else if(foreground){
  label=a.status||'正在处理';button=a.kind==='starting'?'正在开始…':a.kind==='saving'?'正在保存…':'正在处理…';
 }else if(!store.connected)label='正在连接记录器';
 else if(store.requestPending)label='正在处理请求…';
 else if(checking)label='正在检查录制条件';
 else if(r.ready)label='已就绪';
 else if(store.activeId)label='录制条件尚未满足';
 if(closing){label='正在安全关闭';button='正在安全关闭…';}
 const cancelPending=store.snapshot?.updates?.cancel_pending===true;
 if(cancelPending){label='取消尚未确认，请保留窗口';button='等待取消确认';}
 let blockers=[];
 if(!closing&&!store.connected&&connectionMessage)blockers=[connectionMessage];
 else if(!closing&&!recording&&!foreground&&!checking&&!store.requestPending){
  blockers=errors.map(e=>e.message).filter(Boolean);
  if(!r.ready&&!sheetOpen()&&a.status==='操作未完成'&&a.detail&&!blockers.includes(a.detail))blockers.push(a.detail);
 }
 // Blocked: the record block says it cannot record; the reasons are listed on the right, never scrolled.
 const alerting=blockers.length>0&&!recording;
 const ready=!recording&&!alerting&&!closing&&!checking&&!foreground&&!store.requestPending&&r.ready===true&&store.connected;
 if(alerting)button='暂不能录制';
 const panel=$('#capturePanel');panel.classList.toggle('recording',recording);panel.classList.toggle('alerting',alerting);panel.classList.toggle('off',!recording&&!ready);
 setText('recordingTime',recording?formatTime(a.elapsed_seconds):'00:00:00');show('liveClock',recording);
 setText('recordButtonText',button);setText('recordGame',recording?'':store.presets.find(p=>p.id===store.activeId)?.name||'');
 $('#recordButton').classList.toggle('stopping',recording);
 const status=alerting?`${blockers.length} 项检查未通过\n处理右侧事项后重新检查`:ready?[label,...readyLines()].join('\n'):label;
 // Ready: one line per item, cut with an ellipsis rather than wrapped, so the record button keeps its size.
 if(ready){$('#homeStatus').innerHTML=status.split('\n').map(line=>'<span>'+escapeHTML(line)+'</span>').join('');$('#homeStatus').title=readyLines().join('\n');}else{setText('homeStatus',status);$('#homeStatus').title='';}
 $('#homeStatus').className='checks'+(ready?' ready':'')+(recording&&microphoneWarning?' microphone-warning':'');show('homeStatus',!!status);
 currentBlockers=blockers;
 $('#blockers').innerHTML=blockers.slice(0,2).map(message=>'<li><span>'+escapeHTML(message)+'</span></li>').join('');
 show('statusSlot',alerting);show('alertRecheck',alerting&&store.connected);show('alertSettings',alerting&&store.connected);
 const clipped=$$('#blockers li span').some(el=>el.scrollHeight>el.clientHeight+1);
 setText('alertMore',blockers.length>2?`全部 ${blockers.length} 项`:'查看全文');show('alertMore',alerting&&(blockers.length>2||clipped));
 show('jobDetail',cancelPending||closing||foreground&&!!a.detail);
 setText('jobDetail',cancelPending?'更新助手尚未确认取消，请在设置的“版本与更新”里重试取消。':closing?'正在保存并等待现有整理完成，完成后此窗口会自动关闭。':foreground?a.detail:'');
 // Recording: only what is glanced at from a second monitor.
 show('livePrompt',recording);setText('liveSummary',recording?liveSummary():'');
 show('lastSection',!recording);show('insightSection',!recording&&!alerting&&!!store.snapshot?.sessions?.length);
}
function renderGames(){
 const signature=JSON.stringify([store.presets.map(p=>[p.id,p.name]),store.activeId,store.recording]);if(signature===gamesSignature)return;gamesSignature=signature;
 if(store.recording){const active=store.presets.find(p=>p.id===store.activeId);$('#gameTabs').innerHTML=`<span class="g on">${escapeHTML(active?.name||'')}</span><span class="g lock">录制中不能切换游戏</span>`;return;}
 $('#gameTabs').innerHTML=store.presets.map(p=>`<a href="#" class="g${p.id===store.activeId?' on':''}" data-game="${escapeHTML(p.id)}"${p.id===store.activeId?' aria-current="page"':''}>${escapeHTML(p.name)}</a>`).join('')+'<span class="more hidden" id="gamesMore"><button type="button" class="g more-toggle" id="gamesMoreButton" aria-haspopup="menu" aria-expanded="false" aria-controls="gamesMoreMenu">更多</button><span class="more-menu hidden" id="gamesMoreMenu" role="menu" aria-label="其他游戏"></span></span><a href="#" class="g add" data-game-add title="新游戏" aria-label="新游戏">＋ 新增</a>';
 fitGames();
}
// Games that do not fit move, last first, into 更多; ＋ goes last. The current game keeps its width.
function fitGames(){
 const nav=$('#gameTabs'),more=$('#gamesMore'),menu=$('#gamesMoreMenu');if(!more||!menu)return;
 nav.classList.add('fitting');try{fold(nav,more,menu);}finally{nav.classList.remove('fitting');}
}
function fold(nav,more,menu){
 if(!(nav.scrollWidth>nav.clientWidth))return;
 more.classList.remove('hidden');
 for(const tab of [...nav.querySelectorAll('.g[data-game]:not(.on)')].reverse()){if(nav.scrollWidth<=nav.clientWidth)break;tab.className='item';tab.setAttribute('role','menuitem');menu.prepend(tab);}
 const add=nav.querySelector('.g[data-game-add]');if(add&&nav.scrollWidth>nav.clientWidth){add.className='item';add.setAttribute('role','menuitem');add.textContent='＋ 新游戏';menu.append(add);}
}
function toggleGamesMenu(open){const menu=$('#gamesMoreMenu'),button=$('#gamesMoreButton');if(!menu||!button)return;open=open??menu.classList.contains('hidden');if(open){const r=button.getBoundingClientRect();menu.style.left=Math.round(r.left)+'px';menu.style.top=Math.round(r.bottom+4)+'px';}menu.classList.toggle('hidden',!open);button.setAttribute('aria-expanded',String(open));}
document.addEventListener('click',event=>{if(!event.target?.closest?.('#gamesMore'))toggleGamesMenu(false);});
// On resize the same nodes are put back and folded again, so focus and the current game survive.
function unfoldGames(){const more=$('#gamesMore'),menu=$('#gamesMoreMenu');if(!more||!menu)return;toggleGamesMenu(false);for(const item of [...menu.children]){const add=item.hasAttribute('data-game-add');item.className=add?'g add':'g';item.removeAttribute('role');if(add){item.textContent='＋ 新增';more.after(item);}else{const at=id=>store.presets.findIndex(p=>p.id===id),next=[...$('#gameTabs').querySelectorAll(':scope > [data-game]')].find(tab=>at(tab.dataset.game)>at(item.dataset.game));(next||more).before(item);}}more.classList.add('hidden');}
let gamesFrame=0;window.addEventListener?.('resize',()=>{cancelAnimationFrame(gamesFrame);gamesFrame=requestAnimationFrame(()=>{unfoldGames();fitGames();});});
$('#gameTabs').addEventListener('click',async event=>{if(event.target.closest('#gamesMoreButton')){toggleGamesMenu();return;}const target=event.target.closest('[data-game],[data-game-add]');if(!target)return;event.preventDefault();toggleGamesMenu(false);if(target.hasAttribute('data-game-add')){openSheet('new');return;}const id=target.dataset.game;if(id===store.activeId)return;const result=await action('select_preset',[id]);if(!result.ok){gamesSignature='';renderGames();}else{lastSignature='';renderLast();}});
// The four problem types; a session's 问题数 counts only these.
const KIND_NAMES={confusion:'困惑',obstacle:'阻碍',cost:'操作成本',negative:'负面评价'};
const WEEKDAYS='日一二三四五六';
function pad2(n){return String(n).padStart(2,'0');}
function sessionDisplayTitle(s){const named=s.session_name||(s.title&&s.title!==s.game?s.title:'');if(named)return {named:true,text:named};const titles=(s.preprocessing?.event_titles||[]).filter(Boolean);return {named:false,text:titles.length?titles.join('、'):(()=>{const d=new Date(s.created);return Number.isNaN(d.getTime())?'未命名的记录':pad2(d.getHours())+':'+pad2(d.getMinutes())+' 开始的记录';})()};}
function pipeline(s,job,kind,p){
 const saved=!/录制中|启动中|保存中/.test(String(s.state||'')),transcribed=kind==='ready',ps=p.state||'none',failedPre=['failed','interrupted','invalid','stale'].includes(ps);
 const steps=[[saved?'done':'now',saved?'已保存':'保存中'],
  [transcribed?'done':kind==='failed'?'fail':saved?'now':'',transcribed?'已转写':kind==='failed'?'转写失败':job?(job.state==='queued'?'等待转写':'转写中'):'待转写'],
  [!transcribed?'':ps==='processing'?'now':failedPre?'fail':'now',!transcribed?'待整理':ps==='processing'?'整理中':failedPre?(p.label||'整理未完成'):'待整理']];
 const list='<ul class="steps">'+steps.map(([c,t])=>`<li class="${c}">${escapeHTML(t)}</li>`).join('')+'</ul>';
 const handoff=transcribed&&ps!=='processing'?`<div class="handoff"><button class="btn solid" data-copy-handoff="${escapeHTML(s.id)}">复制整理指令</button><p>粘贴给 Codex 或 Claude。整理完成后，问题数和原话会出现在这里。</p></div>`:'';
 const retry=kind==='failed'||kind==='pending'&&!job?`<div class="handoff"><button class="btn" data-last-process="${escapeHTML(s.id)}">${kind==='failed'?'重试转写':'开始转写'}</button>${s.error?`<p>${escapeHTML(s.error)}</p>`:''}</div>`:'';
 return list+handoff+retry;
}
function shortDate(d){return `${d.getMonth()+1}月${d.getDate()}日`;}
function renderLast(){
 const sessions=store.snapshot?.sessions||[],s=sessions[0],alerting=$('#capturePanel').classList.contains('alerting');
 const signature=JSON.stringify([s,store.backgroundJobs,sessions.length,alerting]);if(signature===lastSignature)return;lastSignature=signature;
 setText('sessionCount',sessions.length);
 const latest=s?new Date(s.created):null;setText('libraryBrief',latest&&!Number.isNaN(latest.getTime())?' · 最近 '+shortDate(latest):'');
 const jobs=store.backgroundJobs,running=jobs.filter(job=>job.state==='running').length,queued=jobs.filter(job=>job.state==='queued').length;
 setText('queueBrief',[running?running+' 段转写中':'',queued?queued+' 段排队':''].filter(Boolean).join(' · '));show('queueBrief',(running||queued)>0);
 if(!s){$('#lastSession').innerHTML='<p class="empty">还没有记录。点开始录制，边玩边说出你此刻的想法。</p>';return;}
 const d=new Date(s.created),valid=!Number.isNaN(d.getTime()),p=s.preprocessing||{},title=sessionDisplayTitle(s);
 const when=(valid?`${shortDate(d)} 周${WEEKDAYS[d.getDay()]} ${pad2(d.getHours())}:${pad2(d.getMinutes())} · `:'')+formatTime(s.duration);
 let body='';
 if(p.state==='complete'){
  const kinds=p.kinds||{},present=Object.keys(KIND_NAMES).filter(k=>kinds[k]);
  const bar=present.length?`<div class="fp">${present.map(k=>`<i class="k-${k}" data-flex="${kinds[k]}"></i>`).join('')}</div>`:'';
  const legend=`<p class="kleg">${present.map(k=>`<span class="k-${k}"><b>${kinds[k]}</b> ${KIND_NAMES[k]}</span>`).join('')||'<span>没有问题类型的判断</span>'}</p>`;
  // Blocked: the quote steps aside so the reasons and the session both fit.
  const quote=p.quote&&!alerting?`<div class="quote"><p class="note">${escapeHTML(formatTime(p.quote.at))}${KIND_NAMES[p.quote.kind]?' · '+KIND_NAMES[p.quote.kind]:''}</p><p>“${escapeHTML(p.quote.text)}”</p></div>`:'';
  body=bar+legend+quote;
 }else body=pipeline(s,store.sessionJob(s.id),sessionKind(s),p);
 $('#lastSession').innerHTML=`<p class="note">上一场 · ${escapeHTML(when)}</p><div class="last-top"><span class="last-name">${title.named?'':'<span class="unnamed">未命名</span>'}${escapeHTML(title.text)}${s.test?'<span class="test-tag">合成测试</span>':''}</span><button class="btn sm" data-last-review="${escapeHTML(s.id)}"${canReview(s)?'':' disabled'}>回看</button></div>${body}`;
 $$('#lastSession [data-flex]').forEach(el=>{el.style.flex=el.dataset.flex;});
}
function renderInsight(){const insight=store.snapshot?.insight||{},latest=insight.latest;setText('insightCount',insight.insights??'—');let brief='洞察 · 还没有报告';if(latest){const d=new Date(latest.modified*1000);brief='洞察 · 最新报告 '+(Number.isNaN(d.getTime())?latest.name:shortDate(d));}setText('insightBrief',brief);}
async function copyHandoff(s){if(!s)return;const text=['请用 Think Aloud 的单场整理方法（think-aloud-judgments），整理这一场记录，并按单场整理交接文件验收。','场次文件夹：'+s.path,'资料库：'+store.saved.vault,'只整理这一场；不改议题表、对应表、界面目录、标签和反馈文件。完成后告诉我实例数、提议的新界面和拿不准的地方。'].join('\n');try{await navigator.clipboard.writeText(text);}catch(_){const area=document.createElement('textarea');area.value=text;document.body.append(area);area.select();document.execCommand('copy');area.remove();}notify('整理指令已复制，粘贴给 Codex 或 Claude 即可。');}
$('#lastSession').addEventListener('click',event=>{const review=event.target.closest('[data-last-review]');if(review){action('open_review',[review.dataset.lastReview]);return;}const copy=event.target.closest('[data-copy-handoff]');if(copy){copyHandoff(findSession(copy.dataset.copyHandoff));return;}const process=event.target.closest('[data-last-process]');if(process){const s=findSession(process.dataset.lastProcess);if(s)processSession(s);}});
function openDesk(tab){const api=window.pywebview?.api;return api?.open_desk?action('open_desk',[tab]):action('open_insight');}
$('#openLibrary').onclick=event=>{event.preventDefault();openDesk('sessions');};
$('#openInsight').onclick=event=>{event.preventDefault();openDesk('insight');};
function showMicrophone(data={state:'connecting',level:0}){
 const states={
  connecting:['正在读取音量…','说句话，确认音量条随声音变化。'],
  signal:['有声音','说句话，确认音量条随声音变化。'],
  quiet:['暂时安静','说句话，确认音量条随声音变化。'],
  silent:['持续未收到明显声音','如果你正在说话，请检查麦克风静音键、连接和所选设备。录像仍在继续。'],
  muted:['麦克风已静音','录制引擎中的麦克风已静音，请取消静音后确认音量条有变化。'],
  unrouted:['口述音轨未接入','当前麦克风未送入口述音轨。请结束这段录制，检查录制设置后重试。'],
  loud:['音量偏高','声音可能失真，试着离麦克风远一点或降低麦克风增益。'],
  unavailable:['音量状态暂不可用','暂时无法确认麦克风是否收到声音，正在重试。录像不会因此停止。']
 };
 const state=Object.hasOwn(states,data.state)?data.state:'unavailable',copy=states[state];
 $('#microphoneMonitor').dataset.state=state;
 if(data.name)$('#microphoneMonitor').title=data.name;
 const value=['signal','quiet','silent','loud'].includes(state)&&Number.isFinite(data.level)?Math.max(0,Math.min(1,data.level)):0;
 $('#microphoneFill').style.transform=`scaleX(${value})`;
 $('#microphoneLevel').setAttribute('aria-valuenow',Math.round(value*100));
 $('#microphoneLevel').setAttribute('aria-valuetext',copy[0]);
}
function refreshMicrophoneWarning(){
 const quiet=microphoneQuiet+Math.max(0,(performance.now()-microphoneUpdated)/1000);
 const warning=!!microphoneSession&&quiet>=120;
 if(warning!==microphoneWarning){microphoneWarning=warning;renderHome();}
}
function syncMicrophoneVisibility(){
 const id=store.recording?store.activity.active_id:null;
 show('microphoneMonitor',!!id);
 if(id!==microphoneSession){microphoneSession=id;microphoneUpdated=performance.now();microphoneQuiet=0;microphoneWarning=false;$('#microphoneMonitor').title='麦克风音量';showMicrophone();}
 if(id&&!store.connected)showMicrophone({state:'unavailable'});
}
async function pollMicrophone(){
 syncMicrophoneVisibility();
 const id=microphoneSession;if(!id)return;
 refreshMicrophoneWarning();
 if(performance.now()-microphoneUpdated>2500)showMicrophone({state:'unavailable'});
 if(microphoneRequest||!store.connected)return;
 const token={};microphoneRequest=token;
 try{
  const data=await api('get_microphone_state');
  if(id===microphoneSession&&store.connected&&data?.session_id===id){
   const elapsed=Math.max(0,(performance.now()-microphoneUpdated)/1000);
   microphoneQuiet=Number.isFinite(data.quiet_seconds)?Math.max(0,data.quiet_seconds):['signal','loud'].includes(data.state)?0:microphoneQuiet+elapsed;
   microphoneUpdated=performance.now();showMicrophone(data);refreshMicrophoneWarning();
  }
 }catch(_){if(id===microphoneSession)showMicrophone({state:'unavailable'});}
 finally{if(microphoneRequest===token)microphoneRequest=null;}
}
function renderControls(){renderHome();renderUpdates();renderUpdateBadge();const locked=!store.connected||store.requestPending||store.busy;$('#recordButton').disabled=store.recording?(!store.connected||store.requestPending||!!store.activity.busy):!store.canStart;$('#settingsButton').disabled=!store.connected||store.requestPending||store.busy&&!sheetOpen();$('#openVault').disabled=!store.connected||store.requestPending||!store.activeId;
 const requestLocked=!store.connected||store.requestPending||saving;const conflict=store.recording||!!store.activity.busy&&store.activity.kind!=='devices';const fieldsLocked=requestLocked||conflict;
 ['game','source','target','monitor','mic','preset','language','hotwords','cloudKey'].forEach(id=>$('#'+id).disabled=fieldsLocked);
 $$('[data-provider]').forEach(button=>button.disabled=fieldsLocked);renderInputRecording(fieldsLocked);
 ['chooseVault','chooseHotwordFiles','chooseGameHotwordFiles','chooseLibrary','deleteGame','existingModel','modelLocation','verifyCloud','reconnectEngine'].forEach(id=>$('#'+id).disabled=locked||saving);
 $('#refreshDevices').disabled=locked||saving||deviceInventory().state==='running';
 $$('[data-remove-vocabulary]').forEach(button=>button.disabled=fieldsLocked);$('#dictionaryDownload').setAttribute('aria-disabled',requestLocked?'true':'false');$('#dictionaryDownload').tabIndex=requestLocked?-1:0;$('#bailianConsole').setAttribute('aria-disabled',requestLocked?'true':'false');$('#bailianConsole').tabIndex=requestLocked?-1:0;
 ['wizardCancel','wizardBack'].forEach(id=>$('#'+id).disabled=store.requestPending||saving);$('#reuseVault').disabled=fieldsLocked||store.snapshot?.default_vault?.is_directory===false;$('#wizardNext').disabled=locked&&!sheetOpen()||store.requestPending||saving||conflict||(currentStepKey()==='vault'||sheetMode==='settings'&&sheetTab==='game')&&store.needsVaultConfirmation;
 const m=store.snapshot?.model||{};$('#downloadModel').disabled=locked||saving||['verifying','ready'].includes(m.state);$('#existingModel').disabled=locked||saving||['downloading','verifying'].includes(m.state);$('#modelLocation').disabled=locked||saving||['downloading','verifying'].includes(m.state);$('#verifyCloud').disabled=locked||saving||!store.snapshot?.capabilities?.cloud_key||!!$('#cloudKey').value.trim();
 renderSheetFoot();}
$('#methodButton').onclick=()=>showDialog('让想法跟上体验',$('#methodContent').innerHTML);
$('#methodLink').onclick=()=>showDialog('让想法跟上体验',$('#methodContent').innerHTML);
$('#recordButton').onclick=()=>{if(store.recording)action('stop_recording');else if(store.canStart)action('start_recording',[store.startPayload()]);};
$('#openVault').onclick=()=>action('open_folder');
$('#settingsButton').onclick=()=>{if(sheetOpen())return;openSheet(store.presets.length?'settings':'first','game');};
$('#alertMore').onclick=()=>showDialog('录制条件尚未满足','<ol class="alert-list">'+currentBlockers.map(message=>'<li>'+escapeHTML(message)+'</li>').join('')+'</ol>');
$('#alertRecheck').onclick=()=>{if(store.canConfigure)action('refresh_devices');};
$('#alertSettings').onclick=()=>{const codes=(store.readiness.errors||[]).map(e=>String(e.code||''));openSheet(store.presets.length?'settings':'first',codes.some(code=>/MIC|MICROPHONE|AUDIO/.test(code))?'general':'game');};
// ---- Settings page and wizards share one sheet and one set of fields ----
// settings: 游戏 | 通用 tabs; new: a new game in two steps; first: the first launch.
const SHEET_STEPS={new:[['game','游戏与窗口'],['vault','保存位置']],first:[['method','记录方法'],['general','设备与转写'],['game','游戏与窗口'],['vault','保存位置']]};
function sheetSteps(){return SHEET_STEPS[sheetMode]||[];}
function currentStepKey(){return sheetMode==='settings'?sheetTab:sheetSteps()[step]?.[0]||'';}
function settingsDirty(){return store.dirty||!!$('#cloudKey').value.trim()||libraryRootDraft!==null;}
function fillFields(){for(const el of $$('[data-draft]'))el.value=String(store.draft[el.dataset.draft]??'');$('#libraryRoot').value=libraryRootDraft??store.saved.library_root??'';}
function openSheet(mode='settings',tab='game'){
 if(!store.connected||store.requestPending||store.recording||mode!=='first'&&store.busy)return;
 if(mode==='new'&&!store.presets.length)mode='first';
 sheetMode=mode;sheetTab=tab;wizardMode=mode==='settings'?'edit':'new';deviceInventoryRequest=null;libraryRootDraft=null;
 store.openDraft(wizardMode);store.addedGeneralIds=[];if(mode==='first')store.markGeneral(store.draft.hotword_files);
 if(mode==='new'&&store.presets.length){for(const key of RecorderState.GENERAL_KEYS)if(store.saved[key]!==undefined)store.draft[key]=JSON.parse(JSON.stringify(store.saved[key]));store.draft.hotword_files=JSON.parse(JSON.stringify(store.saved.general_hotword_files||[]));store.draft.hotword_manual='';store.draft.vault='';store.syncVocabulary();}
 step=0;deviceSignature='';vocabularySignature='';downloadDirectory=null;wizardError();$('#cloudKey').value='';
 setText('cloudFeedback','新密钥在保存设置时保存，取消时清空。');setText('downloadDestination','下载到软件所在文件夹。下载可暂停，关闭设置后会继续。');
 fillFields();
 store.snapshotBaseline();
 $('#sheet').classList.remove('hidden');$('#settingsButton').classList.add('on');
 layoutSheet();renderDeviceOptions(true);renderResources();renderVocabulary();renderVaultChoice();renderControls();
 if(currentStepKey()!=='game')$('#sheetTitle').focus({preventScroll:true});void refreshDeviceInventory();
}
function layoutSheet(){
 const settings=sheetMode==='settings',current=currentStepKey(),steps=sheetSteps();
 setText('sheetTitle',settings?'设置':sheetMode==='first'?'开始使用':'新建游戏');
 show('sheetTabs',settings);show('wizardSteps',!settings);
 $('#tabGame').classList.toggle('on',settings&&sheetTab==='game');$('#tabGeneral').classList.toggle('on',settings&&sheetTab==='general');
 show('gameSubtabs',settings&&sheetTab==='game');
 if(settings)$('#gameSubtabs').innerHTML=store.presets.map(p=>`<a href="#" data-sub-game="${escapeHTML(p.id)}" class="${p.id===store.activeId?'on':''}">${escapeHTML(p.name)}</a>`).join('')+'<a href="#" class="add" data-sub-add>＋ 新游戏</a>';
 else $('#wizardSteps').innerHTML=steps.map(([,label],i)=>`<span class="${i===step?'on':''}"><b>${i+1}</b>${escapeHTML(label)}</span>`).join('');
 show('deviceBar',current==='game'||current==='general');show('panelMethod',current==='method');show('panelGeneral',current==='general');show('panelGame',current==='game'||current==='vault');
 $('#panelGeneral').classList.toggle('wizard',!settings);
 $$('#panelGame [data-in]').forEach(field=>{const key=field.dataset.in;field.classList.toggle('hidden',current==='vault'?key!=='game-vault':!settings&&(key==='game-vault'||key==='game-delete'));});
 $('#wizardBody').scrollTop=0;renderSheetFoot();renderUpdateBadge();
 if(current==='game')$('#game').focus({preventScroll:true});
}
function renderSheetFoot(){
 if(!sheetOpen())return;const settings=sheetMode==='settings',steps=sheetSteps(),last=!settings&&step===steps.length-1,dirty=settingsDirty();
 setText('sheetMessage',settings&&dirty?'有未保存的修改':'');
 setText('wizardCancel',settings&&!dirty?'关闭':'取消');
 show('wizardNext',!settings||dirty);show('wizardBack',!settings&&step>0);
 setText('wizardNext',saving?'正在保存…':settings?'保存':last?(sheetMode==='first'?'开始使用':'创建游戏'):step===0&&sheetMode==='first'?'开始设置':'下一步');
}
function renderSummary(){renderSheetFoot();}
function closeSheet(){deviceInventoryRequest=null;libraryRootDraft=null;$('#cloudKey').value='';store.cancelDraft();$('#sheet').classList.add('hidden');$('#settingsButton').classList.remove('on');sheetMode=null;wizardError();renderHome();renderControls();}
function cancelWizard(){if(store.requestPending||saving)return;closeSheet();}
$('#wizardCancel').onclick=cancelWizard;
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&sheetOpen()&&!$('#actionDialog').open)cancelWizard();});
function setSheetTab(tab){if(sheetTab===tab)return;if(settingsDirty()){wizardError('请先保存或取消当前修改，再切换。');return;}wizardError();sheetTab=tab;layoutSheet();}
$('#tabGame').onclick=event=>{event.preventDefault();setSheetTab('game');};$('#tabGeneral').onclick=event=>{event.preventDefault();setSheetTab('general');};
$('#gameSubtabs').addEventListener('click',async event=>{const target=event.target.closest('[data-sub-game],[data-sub-add]');if(!target)return;event.preventDefault();if(settingsDirty()){wizardError('请先保存或取消当前修改，再切换游戏。');return;}if(target.hasAttribute('data-sub-add')){closeSheet();openSheet('new');return;}const id=target.dataset.subGame;if(id===store.activeId)return;closeSheet();const result=await action('select_preset',[id]);if(result.ok)openSheet('settings','game');});
function gameStepError(){const d=store.draft;if(!d.game.trim())return '请填写游戏名称。';if(d.source!=='整个显示器'&&!d.window)return '请选择游戏窗口。';return '';}
function proposeVault(){const d=store.draft,root=libraryRootDraft??store.saved.library_root;if(d.vault)return;if(root)d.vault=root.replace(/[\\/]+$/,'')+'\\'+d.game.trim().replace(/[<>:"/\\|?*\x00-\x1f]/g,'_');else if(sheetMode==='first')d.vault=store.snapshot?.default_vault?.path||'';$('#vault').value=d.vault;}
function nextStep(){const key=currentStepKey(),error=key==='general'?store.validateGeneral():key==='game'?gameStepError():key==='vault'?store.validateGame():'';if(error){wizardError(error);return;}wizardError();if(step<sheetSteps().length-1){step++;if(currentStepKey()==='vault')proposeVault();layoutSheet();renderVaultChoice();renderControls();}else finishWizard();}
$('#wizardBack').onclick=()=>{if(step>0){step--;wizardError();layoutSheet();renderControls();}};
$('#wizardNext').onclick=()=>{if(sheetMode==='settings')saveSettingsSheet();else nextStep();};
async function finishWizard(){
 if(saving||store.requestPending)return;const full=!(sheetMode==='new'&&store.presets.length);const error=store.validateGame()||(full?store.validateGeneral():'');if(error){wizardError(error);return;}
 saving=true;store.requestPending=true;wizardError();renderControls();let saved=false;
 try{
  const payload=full?store.presetPayload():store.gamePayload();
  await api('save_preset',payload,null);saved=true;
  const key=$('#cloudKey').value.trim();if(store.draft.transcription_provider==='qwen'&&key){await api('save_cloud_key',key);$('#cloudKey').value='';}
  const fresh=await freshPoll();if(!fresh)throw new Error('游戏已创建，但还没有收到新的检查结果。请稍后重试。');
  const first=sheetMode==='first';closeSheet();notify(first?'设置完成，正在检查是否可以开始录制。':'游戏已创建，正在检查是否可以开始录制。');
 }catch(error){if(error.code==='VAULT_REUSE_REQUIRED'){store.confirmedVault='';await freshPoll();renderVaultChoice();}wizardError((saved?'游戏已创建。':'')+(error.message||'保存未完成，请检查后重试。'));$('#wizardBody').scrollTop=0;}
 finally{saving=false;store.requestPending=false;renderHome();renderControls();}
}
async function saveSettingsSheet(){
 if(saving||store.requestPending)return;const general=sheetTab==='general';const error=general?store.validateGeneral():store.validateGame();if(error){wizardError(error);return;}
 saving=true;store.requestPending=true;wizardError();renderControls();let saved=false;
 try{
  if(general)await api('save_general',{...store.generalPayload(),...(libraryRootDraft!==null?{library_root:libraryRootDraft}:{})});else await api('save_preset',store.gamePayload(),store.editingId);
  saved=true;const key=$('#cloudKey').value.trim();if(general&&store.draft.transcription_provider==='qwen'&&key){await api('save_cloud_key',key);$('#cloudKey').value='';}
  const fresh=await freshPoll();if(!fresh)throw new Error('设置已保存，但还没有收到新的检查结果。请稍后重试。');
  libraryRootDraft=null;store.openDraft('edit');store.addedGeneralIds=[];fillFields();store.snapshotBaseline();vocabularySignature='';
  renderVocabulary();renderResources();renderDeviceOptions(true);layoutSheet();notify(general?'通用设置已保存，所有游戏都会使用。':'游戏设置已保存。');
 }catch(error){if(error.code==='VAULT_REUSE_REQUIRED'){store.confirmedVault='';await freshPoll();renderVaultChoice();}wizardError((saved?'设置已保存。':'')+(error.message||'保存未完成，请检查后重试。'));$('#wizardBody').scrollTop=0;}
 finally{saving=false;store.requestPending=false;renderHome();renderControls();}
}
// Deleting a game removes its settings and entries; the data folder stays unless ticked and the name is repeated.
let deletingGame=false,deleteSync=null;
function confirmDeleteGame(){
 const preset=store.presets.find(p=>p.id===store.editingId);if(!preset||!store.canConfigure||deletingGame)return;
 const name=preset.name;
 showDialog('删除游戏“'+name+'”？',
  '<p>会从软件里移除这个游戏：游戏窗口、游戏词库和补充词条的设置，以及页签和资料台里的入口。</p>'+
  '<p>资料文件夹默认保留，里面的录像、逐字稿和整理结果都不动：</p><p class="path-text">'+escapeHTML(preset.vault||'')+'</p>'+
  '<label class="check"><input type="checkbox" id="deleteData"><span>同时把资料文件夹移到回收站</span></label>'+
  '<div class="delete-data hidden" id="deleteDataConfirm"><p class="inline-error">文件夹里的全部场次、录像、逐字稿、整理结果和洞察报告会一起移走，可以从回收站还原。</p><label for="deleteConfirmName">输入游戏名称“'+escapeHTML(name)+'”确认</label><input id="deleteConfirmName" autocomplete="off" spellcheck="false"></div>'+
  '<p class="inline-error hidden" id="deleteError" role="alert"></p>',
  [{label:'删除游戏',primary:true,run:()=>deleteGame(preset)}]);
 const button=$('#actionFooter').lastElementChild;button.classList.add('danger');$('#actionFooter').firstElementChild.textContent='取消';
 deleteSync=()=>{const data=$('#deleteData').checked;show('deleteDataConfirm',data);button.textContent=deletingGame?'正在删除…':data?'删除游戏和资料':'删除游戏';button.disabled=deletingGame||data&&$('#deleteConfirmName').value!==name;};
 $('#deleteData').onchange=deleteSync;$('#deleteConfirmName').oninput=deleteSync;deleteSync();
}
async function deleteGame(preset){
 if(deletingGame)return false;
 const data=$('#deleteData').checked,confirmName=data?$('#deleteConfirmName').value:'';
 deletingGame=true;store.requestPending=true;deleteSync?.();renderControls();
 try{
  const result=await api('delete_preset',preset.id,{delete_data:data,confirm_name:confirmName});
  closeSheet();await freshPoll();
  if(result.data_error){showDialog('游戏已删除，资料文件夹没有移走','<p>'+escapeHTML(result.data_error)+'</p><p class="path-text">'+escapeHTML(result.vault)+'</p>');return false;}
  notify(result.recycled?'已删除“'+result.name+'”，资料文件夹已移到回收站。':'已删除“'+result.name+'”，资料文件夹保留在原处。');
  return {ok:true};
 }catch(error){setText('deleteError',error.message||'删除未完成，请重试。');show('deleteError',true);return false;}
 finally{deletingGame=false;store.requestPending=false;renderHome();renderControls();setTimeout(()=>deleteSync?.(),0);}
}
$('#deleteGame').onclick=confirmDeleteGame;
$('#chooseLibrary').onclick=async()=>{const result=await action('choose_directory',['vault']);if(result.ok&&result.data?.path){libraryRootDraft=result.data.path;$('#libraryRoot').value=libraryRootDraft;renderSheetFoot();}};
function fieldChanged(element){store.updateDraft(element.dataset.draft,element.value);if(element.id==='source'){deviceSignature='';renderDeviceOptions(true);renderInputRecording();}if(element.id==='mic'||element.id==='monitor')renderDeviceOptions();if(element.dataset.draft==='hotword_manual')renderVocabulary();renderSummary();}
$$('[data-draft]').forEach(el=>el.addEventListener(el.tagName==='SELECT'?'change':'input',()=>fieldChanged(el)));
$('#cloudKey').addEventListener('input',()=>{setText('cloudFeedback',$('#cloudKey').value.trim()?'新密钥将在完成设置时保存。取消会清空输入。':'留空将保留已保存密钥。');renderControls();});
function deviceItems(kind){return store.snapshot?.devices?.[kind]||[];}
function deviceInventory(){
 const request=deviceInventoryRequest;
 if(request?.draft===store.draft){
  if(request.requesting)return {state:'running'};
  if(request.error&&request.initialInventory===inventorySignature())return {state:'failed',error:request.error};
 }
 return RecorderState.inventoryView(store.snapshot);
}
function matchedDeviceValue(kind,value){const inventory=deviceInventory();return kind==='window'&&['succeeded','cached'].includes(inventory.state)?RecorderState.matchedWindowValue(value,deviceItems(kind),inventory.window_selection):value;}
function deviceLabel(kind,value){return deviceItems(kind).find(i=>String(i.itemValue)===String(matchedDeviceValue(kind,value)))?.itemName||RecorderState.savedDeviceLabel(kind,value);}
function fillDevice(select,kind,value){
 if(document.activeElement===select)return false;
 const inventory=deviceInventory(),confirmed=inventory.state==='succeeded',selection=inventory.window_selection;
 const ambiguous=confirmed&&kind==='window'&&selection?.requested===value&&selection.status==='ambiguous';
 const current=String(matchedDeviceValue(kind,value)??''),items=deviceItems(kind);
 const exists=!ambiguous&&items.some(i=>String(i.itemValue)===current&&i.itemEnabled!==false);
 const status={idle:'尚未读取，未确认',running:'正在读取，未确认',failed:'读取失败，未确认',cached:'上次读取，待确认'}[inventory.state];
 const missing=ambiguous?'多个匹配，请重新选择':confirmed?'当前未找到':status;
 const placeholder=current?`${deviceLabel(kind,value)}（${missing}）`:'请选择'+(kind==='mic'?'麦克风':kind==='monitor'?'显示器':'游戏窗口');
 select.innerHTML=(exists?'':`<option value="${escapeHTML(current)}">${escapeHTML(placeholder)}</option>`)+items.filter(i=>exists||String(i.itemValue)!==current).map(i=>`<option value="${escapeHTML(i.itemValue)}" ${i.itemEnabled===false?'disabled':''}>${escapeHTML(i.itemName)}${String(i.itemValue)===current&&current!==String(value??'')?'（已匹配当前窗口）':''}${!confirmed?'（'+status+'）':''}</option>`).join('');
 select.value=current;return true;
}
function renderInputRecording(locked=false){
 const d=store.draft,available=d?.source==='游戏窗口';
 $('#recordInputs').checked=!!d?.record_inputs;
 $('#recordInputs').disabled=locked||!available;
 setText('inputRecordingHint',available?'录制期间完整记录键鼠和手柄操作，包括切到其他软件时的操作；目标窗口的前后台状态另行保存，回看时可筛选。':'选择“游戏窗口”及目标程序后可启用操作记录。操作只在录制期间采集，结束后停止。');
}
$('#recordInputs').onchange=()=>{if(store.draft&&store.draft.source==='游戏窗口'){store.updateDraft('record_inputs',$('#recordInputs').checked);renderSummary();}};
function engineRecovery(){
 if(store.recording||store.busy||store.readiness.checking===true||store.readiness.ready===true)return null;
 const errors=store.readiness.errors||[];
 const recovery=[
  ['RECORDING_UNCONFIRMED','重新检查录制状态','上次录制状态或归属尚未确认。请重新检查，确认前无法开始新录制。'],
  ['OBS_UNAVAILABLE','重新连接录制引擎','录制引擎尚未就绪，可重新连接并检查录制条件。'],
  ['OBS_CONFIGURATION','重新连接录制引擎','录制引擎尚未就绪，可重新连接并检查录制条件。'],
  ['READINESS_FAILED','重新检查录制条件','录制条件检查未完成，请重新检查。'],
  ['READINESS_STALE','重新检查录制条件','录制条件检查结果已过期，请重新检查。'],
 ];
 return recovery.find(([code])=>errors.some(error=>error.code===code))||null;
}
function successfulDeviceFeedback(draft,inventory){
 const kind=draft.source==='整个显示器'?'monitor':'window',targetName=kind==='monitor'?'显示器':'游戏窗口';
 if(kind==='window'&&draft.window&&inventory.window_selection?.requested===draft.window&&inventory.window_selection.status==='ambiguous')return '检测到多个匹配的游戏窗口，请选择要录制的窗口。';
 if(devicesEmpty())return '读取完成，当前未找到可用设备。请打开游戏或连接设备后刷新。';
 const missing=[],unselected=[];
 for(const [key,name] of [[kind,targetName],['mic','麦克风']]){
  if(!draft[key])unselected.push(name);
  else if(!deviceItems(key).some(item=>item.itemEnabled!==false&&String(item.itemValue)===String(matchedDeviceValue(key,draft[key]))))missing.push(key);
 }
 if(missing.length){const names=missing.map(key=>key==='mic'?'麦克风':targetName).join('和'),steps=missing.map(key=>key==='window'?'打开游戏':key==='mic'?'连接麦克风':'连接显示器').join('或');return `当前未找到所选${names}，请${steps}后刷新。`;}
 if(unselected.length)return '读取完成，请选择'+unselected.join('和')+'。';
 return `已识别当前选择的${targetName}和麦克风。`+(store.editingId?'已保存的预设保持不变。':'');
}
function renderDeviceOptions(force=false){
 if(!store.draft)return;
 const d=store.draft,kind=d.source==='整个显示器'?'monitor':'window',inventory=deviceInventory();
 const signature=JSON.stringify([store.snapshot?.devices,inventory,kind,d.window,d.monitor,d.mic]);
 if(force||signature!==deviceSignature){const a=fillDevice($('#target'),'window',d.window);const b=fillDevice($('#mic'),'mic',d.mic);const c=fillDevice($('#monitor'),'monitor',d.monitor);if(a&&b&&c)deviceSignature=signature;}
 show('target',kind!=='monitor');show('targetMonitorNote',kind==='monitor');show('monitorField',kind==='monitor');setText('refreshDevices',inventory.state==='running'?'正在读取…':'刷新设备');
 const feedback={idle:'尚未读取设备，已保存的选择待确认。',running:'正在读取可用窗口和麦克风，已保存的选择保持不变…',failed:'设备读取失败：'+(inventory.error||'请重试。')+' 已保存的选择尚未确认。',cached:'显示上次读取的设备，请刷新确认当前是否可用。',succeeded:successfulDeviceFeedback(d,inventory)};
 setText('deviceFeedback',feedback[inventory.state]);
 const recovery=engineRecovery();
 show('reconnectEngine',!!recovery);show('engineFeedback',!!recovery);
 setText('reconnectEngine',recovery?.[1]||'重新连接录制引擎');setText('engineFeedback',recovery?.[2]||'');
}
$('#target').onchange=()=>{if(store.draft){store.updateDraft('window',$('#target').value);renderDeviceOptions();renderSummary();}};
function devicesEmpty(){return ['monitor','window','mic'].every(kind=>!deviceItems(kind).some(item=>item.itemEnabled!==false&&String(item.itemValue??'')));}
function selectionSignature(draft){return JSON.stringify([draft.source,draft.window,draft.monitor,draft.mic]);}
function inventorySignature(){const inventory=store.snapshot?.device_inventory;return JSON.stringify([inventory?.id,inventory?.checked_at,inventory?.state]);}
function completeDeviceSetup(){
 const pending=deviceInventoryRequest;if(!pending?.initialize||pending.requesting)return;
 if(store.draft!==pending.draft||!sheetOpen()||store.deviceChoiceRevision!==pending.revision||selectionSignature(store.draft)!==pending.selection){pending.initialize=false;return;}
 const refresh=store.snapshot?.device_inventory;if(!refresh||!['succeeded','failed'].includes(refresh.state))return;
 pending.initialize=false;
 if(refresh.id!==pending.id||refresh.state!=='succeeded'||wizardMode!=='new'||store.editingId||store.draft.window||store.draft.monitor||store.draft.mic)return;
 const defaults=store.snapshot?.device_defaults||{};
 const valid=(kind,value)=>!!value&&deviceItems(kind).some(item=>String(item.itemValue)===String(value)&&item.itemEnabled!==false);
 store.updateDraft('source','整个显示器');
 store.updateDraft('monitor',valid('monitor',defaults.monitor)?String(defaults.monitor):'');
 store.updateDraft('mic',valid('mic',defaults.mic)?String(defaults.mic):'');
 $('#source').value=store.draft.source;
 deviceSignature='';renderDeviceOptions(true);renderSummary();
 const missing=[];if(!store.draft.monitor)missing.push('主显示器');if(!store.draft.mic)missing.push('默认麦克风');
 wizardError(missing.length?'未能确认'+missing.join('和')+'，请从已获取的设备中手动选择。':'');
}
async function refreshDeviceInventory(explicit=false){
 const draft=store.draft;if(!draft||!store.connected||store.recording)return;
 if(explicit&&deviceInventory().state==='running')return;
 const request={draft,requesting:true,id:null,error:'',initialInventory:inventorySignature(),selection:selectionSignature(draft),revision:store.deviceChoiceRevision,
  initialize:explicit&&wizardMode==='new'&&!store.editingId&&devicesEmpty()&&!draft.window&&!draft.monitor&&!draft.mic&&store.deviceChoiceRevision===0};
 deviceInventoryRequest=request;deviceSignature='';renderDeviceOptions();renderControls();
 try{
  const result=await api('refresh_device_inventory');
  if(deviceInventoryRequest!==request||store.draft!==draft||!sheetOpen())return;
  if(!result?.inventory_id)throw new Error('尚未确认设备读取结果，请重试。');
  request.id=result.inventory_id;request.requesting=false;
  await freshPoll();
 }catch(error){if(deviceInventoryRequest===request&&store.draft===draft){request.error=error.message||'无法读取设备，请重试。';request.initialize=false;}}
 finally{if(deviceInventoryRequest===request&&store.draft===draft){request.requesting=false;completeDeviceSetup();renderDeviceOptions();renderControls();}}
}
$('#refreshDevices').onclick=()=>refreshDeviceInventory(true);
$('#reconnectEngine').onclick=()=>{if(store.canConfigure&&engineRecovery())return action('refresh_devices');};
function chooseProvider(provider,focus=false){
 const button=$$('[data-provider]').find(button=>button.dataset.provider===provider);
 if(!store.draft||!button||button.disabled)return;
 store.updateDraft('transcription_provider',provider);wizardError();renderResources();renderSummary();
 if(focus)button.focus({preventScroll:true});
}
$$('[data-provider]').forEach(button=>{
 button.onclick=()=>chooseProvider(button.dataset.provider);
 button.onkeydown=event=>{
  if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();chooseProvider(event.key==='Home'?'local':event.key==='End'?'qwen':button.dataset.provider==='local'?'qwen':'local',true);
 };
});
function renderResources(){if(!store.draft)return;const provider=store.draft.transcription_provider;show('localControls',provider==='local');show('cloudControls',provider==='qwen');show('providerChoiceHint',!['local','qwen'].includes(provider));setText('providerChoiceHint','尚未选择转写方式，请选择本地转写或 Qwen 转写。');$$('[data-provider]').forEach(button=>{const selected=button.dataset.provider===provider;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected||!provider&&button.dataset.provider==='local'?0:-1;});const m=store.snapshot?.model||{};const names={missing:'未准备',downloading:'下载中',paused:'已暂停',verifying:'正在校验',ready:'已准备好',error:'未完成'};setText('modelStatus',names[m.state]||'正在读取');$('#modelStatus').className='state-label '+(m.state||'');setText('modelPath',m.path||'可选择已有的模型文件夹，无需再次复制。');show('modelProgressArea',['downloading','paused','verifying'].includes(m.state));setText('modelProgressLabel',m.state==='verifying'?'正在检查文件是否完整':'已下载');setText('modelBytes',bytes(m.downloaded_bytes)+(m.total_bytes?' / '+bytes(m.total_bytes):''));if(m.total_bytes&&m.state!=='verifying')$('#modelProgress').value=Math.min(100,(m.downloaded_bytes||0)/m.total_bytes*100);else $('#modelProgress').removeAttribute('value');setText('modelError',m.error||'');show('modelError',!!m.error);setText('downloadModel',{downloading:'暂停下载',paused:'继续下载',verifying:'正在校验',ready:'已准备好',error:'重试下载'}[m.state]||'下载模型');setText('cloudStatus',store.snapshot?.capabilities?.cloud_key?'密钥已保存':'尚未保存密钥');renderControls();}
$('#chooseVault').onclick=async()=>{const result=await action('choose_directory',['vault']);if(result.ok&&result.data?.path&&store.draft){store.updateDraft('vault',result.data.path);store.confirmVault();$('#vault').value=result.data.path;renderSummary();renderVaultChoice();renderControls();}};
function renderVaultChoice(){if(!store.draft)return;const info=store.snapshot?.default_vault||{},same=store.defaultVaultSelected,exists=same&&info.requires_confirmation===true;show('reuseVaultNotice',exists);show('reuseVault',exists&&store.needsVaultConfirmation&&info.is_directory!==false);setText('reuseVaultMessage',info.is_directory===false?'该位置已有同名文件，请选择其他文件夹。':store.needsVaultConfirmation?'发现已有同名资料库。是否使用它并保留其中的录像和笔记？':'将使用已有资料库，保留其中的录像和笔记。');setText('chooseVault',exists?'选择其他位置':'选择');setText('vaultHint',same?'默认保存在软件父级的 think-aloud-database，更新版本后可继续使用。':'每场体验分别保存，不覆盖已有录像或笔记。');}
$('#reuseVault').onclick=()=>{if(!store.canConfigure||!store.draft||store.snapshot?.default_vault?.is_directory===false)return;store.confirmVault();renderVaultChoice();renderControls();};
// Vocabulary: the shared list lives in 通用, each game's own list in 游戏; transcription merges both.
function vocabularyChips(files){return files.map(file=>`<span class="chip on" title="${escapeHTML(file.name)}">${escapeHTML(file.name)} <b>${file.words.length}</b><button type="button" class="x" data-view-vocabulary="${escapeHTML(file.id)}" aria-label="查看词库 ${escapeHTML(file.name)}" title="查看">&#xE890;</button><button type="button" class="x" data-remove-vocabulary="${escapeHTML(file.id)}" aria-label="移除词库 ${escapeHTML(file.name)}" title="移除">&#xE711;</button></span>`).join('');}
function renderVocabulary(){
 if(!store.draft)return;
 const general=store.generalFiles(),game=store.gameFiles(),signature=JSON.stringify([general,game]);
 if(signature!==vocabularySignature){vocabularySignature=signature;$('#hotwordFiles').innerHTML=vocabularyChips(general);$('#gameHotwordFiles').innerHTML=vocabularyChips(game);}
 const manualCount=new Set(RecorderState.splitWords(store.draft.hotword_manual)).size,total=RecorderState.vocabularyWords(store.draft).length;
 setText('vocabularyCount',total?`通用 ${general.length} 份 · 本游戏 ${game.length} 份 · 合并后 ${total} 个词`:'尚未选择词库');
 setText('manualWordCount',manualCount?manualCount+' 个词':'可选');show('vocabularyStorage',general.length>0);
 renderSheetFoot();
}
async function chooseVocabulary(general){const result=await action('choose_hotword_files');if(result.ok&&store.draft&&result.data?.files?.length){const count=store.addVocabularyFiles(result.data.files);if(general)store.markGeneral(result.data.files);vocabularySignature='';renderVocabulary();renderControls();notify(count?'已加入 '+count+' 份词库，保存后生效。':'这些词库已在列表中。');}}
$('#chooseHotwordFiles').onclick=()=>chooseVocabulary(true);$('#chooseGameHotwordFiles').onclick=()=>chooseVocabulary(false);
$('#wizardBody').addEventListener('click',event=>{
 if(!store.draft)return;
 const view=event.target.closest('[data-view-vocabulary]');
 if(view?.dataset.viewVocabulary){const file=store.draft.hotword_files.find(item=>item.id===view.dataset.viewVocabulary);if(!file)return;showDialog(file.name,`<p>${file.words.length} 个词</p><ul class="vocabulary-words" aria-label="词库词条">${file.words.map(word=>'<li>'+escapeHTML(word)+'</li>').join('')}</ul><p>词条用于辅助识别，不会替换原话。移除词库不删除原文件。</p>`);return;}
 const button=event.target.closest('[data-remove-vocabulary]');if(!button||!store.canConfigure||saving)return;
 store.removeVocabularyFile(button.dataset.removeVocabulary);vocabularySignature='';renderVocabulary();renderControls();
});
$('#dictionaryDownload').onclick=event=>{event.preventDefault();if(!store.connected||store.requestPending||saving)return;action('open_dictionary_site');};
$('#verifyCloud').onclick=async()=>{setText('cloudFeedback','正在验证已保存的密钥…');await action('verify_cloud_key',[],'','verify');};
$('#modelLocation').onclick=async()=>{const result=await action('choose_directory',['download']);if(result.ok&&result.data?.path){downloadDirectory=result.data.path;setText('downloadDestination','下载到 '+downloadDirectory+'。关闭设置后下载会继续。');}};
$('#downloadModel').onclick=()=>{const m=store.snapshot?.model;if(m?.state==='downloading')action('model_action',['pause']);else if(m?.state==='paused')action('model_action',['download',downloadDirectory]);else showDialog('准备本地转写模型','<p>下载 Whisper large-v3，约 3.09 GB。下载完成后会检查文件完整性，之后更新软件无需重复下载。</p><p>保存位置：'+escapeHTML(downloadDirectory||'软件文件夹内的 models / large-v3')+'</p>',[{label:'开始下载',primary:true,run:()=>action('model_action',['download',downloadDirectory])}]);};
$('#existingModel').onclick=async()=>{const result=await action('choose_directory',['model']);if(result.ok&&result.data?.path)showDialog('使用已有模型','<p>'+escapeHTML(result.data.path)+'</p><p>检查通过后直接使用，不复制文件。移动目录后需要重新选择。</p>',[{label:'检查并使用',primary:true,run:()=>action('model_action',['import',result.data.path])}]);};
function sessionTitle(s){return s.title||s.session_name||s.game||s.id;}
function canReview(s){return s.can_review===true||(s.can_review!==false&&sessionKind(s)==='ready');}

function sessionKind(s){if(store.sessionJob(s.id))return 'processing';const status=String(s.state||'');if(s.error||/失败|错误|failed|error/i.test(status))return 'failed';if(/待整理|待转写|pending|recorded|saved/i.test(status))return 'pending';if(/可回看|完成|就绪|ready|done|complete/i.test(status))return 'ready';return 'other';}
function preprocessingLabel(s){return s.preprocessing?.state==='complete'&&Number.isInteger(s.preprocessing.events)?`预处理 ${s.preprocessing.events} 个事件`:s.preprocessing?.label||'';}
function findSession(id){return (store.snapshot?.sessions||[]).find(s=>String(s.id)===String(id));}
function processSession(s){if(store.saved.transcription_provider==='later'){showDialog('先选择整理方式','<p>当前预设只保存录制。选择本地或云端转写后，再回来整理此场次。</p>',[{label:'设置整理方式',primary:true,run:()=>{setTimeout(()=>openSheet('settings','general'),0);}}]);return;}showDialog('整理这次体验','<p>'+escapeHTML(s.game||s.id)+'\n使用'+escapeHTML(providerNames[store.saved.transcription_provider]||'已保存的方式')+'。旧版文字与复盘会保留。</p>'+(store.saved.transcription_provider==='qwen'?'<p>将上传这次的麦克风录音到 Qwen，可能产生服务费用。</p>':'')+'<p>如果上次云端任务结果不确定，请从详情恢复原任务，避免重复提交。</p>',[{label:'开始整理',primary:true,run:()=>action('process_session',[s.id])}]);}
function recoverSession(s){showDialog('恢复已有云端任务','<p>填写已有任务编号，继续查询原任务，不重新上传录音。</p><label for="recoveryId">云端任务编号</label><input id="recoveryId" autocomplete="off" spellcheck="false" placeholder="已有 task_id">',[{label:'恢复任务',primary:true,run:()=>{const id=$('#recoveryId').value.trim();if(!id){notify('请填写已有任务编号。');return false;}return action('recover_cloud_task',[s.id,id]);}}]);}
function begin(){if(booted)return;booted=true;poll();setInterval(poll,1000);setInterval(pollMicrophone,200);}window.addEventListener('pywebviewready',begin);if(window.pywebview?.api)begin();setTimeout(()=>{if(!booted){connectionMessage='尚未连接记录器。请从桌面应用打开。';renderHome();}},6000);

// A fixed external destination, opened by the native bridge without any key.
$('#bailianConsole').onclick=async event=>{event.preventDefault();if(store.requestPending||saving)return;await action('open_bailian_console');};
applyFrameColor();window.addEventListener('pywebviewready',applyFrameColor);