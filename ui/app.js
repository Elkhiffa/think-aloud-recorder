'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon=name=>`<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const store=new RecorderState.State();
const providerNames={later:'仅保存录制',local:'在本机转成文字',qwen:'Qwen 云端转写'};
let pollTask=null,booted=false,firstSetupHandled=false,toastTimer=null,step=1,saving=false,wizardMode='edit';
let downloadDirectory=null,presetSignature='',deviceSignature='',sessionSignature='',expandedSession=null,vocabularySignature='';
let dialogGeneration=0,connectionMessage='',lastActivitySignature='',actionContext=null;
let pendingDeviceSetup=null;
let updatePending='',updateError='',updateChannelDirty=false,updateInstallAccepted=false;
const firstWizardStep=()=>wizardMode==='edit'?1:0;
const setText=(id,value)=>{const n=document.getElementById(id);const text=String(value??'');if(n.textContent!==text)n.textContent=text;};
const show=(id,value)=>document.getElementById(id).classList.toggle('hidden',!value);
function notify(message){clearTimeout(toastTimer);setText('toast',message);$('#toast').classList.add('show');toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),6000);}
function wizardError(message=''){setText('wizardError',message);show('wizardError',!!message);}
function theme(value){document.documentElement.dataset.theme=value;$('#themeButton').setAttribute('aria-label',value==='dark'?'切换浅色模式':'切换深色模式');$('#themeButton').title=value==='dark'?'切换浅色模式':'切换深色模式';try{localStorage.setItem('recorder-theme',value);}catch(_){}}
try{theme(localStorage.getItem('recorder-theme')==='dark'?'dark':'light');}catch(_){theme('light');}
$('#themeButton').onclick=()=>theme(document.documentElement.dataset.theme==='dark'?'light':'dark');
async function api(method,...args){if(!window.pywebview?.api?.[method])throw new Error('尚未连接记录器，请稍后重试。');const response=await window.pywebview.api[method](...args);if(!response||response.ok!==true){const error=new Error(response?.error||'操作未完成，请检查后重试。');error.code=response?.code;throw error;}return response.data;}
function poll(){if(pollTask)return pollTask;pollTask=(async()=>{try{const snapshot=await api('get_state');store.accept(snapshot);connectionMessage='';render();return true;}catch(error){store.disconnect();connectionMessage=error.message||'连接中断，请稍后重试。';renderHome();renderControls();return false;}finally{pollTask=null;}})();return pollTask;}
async function freshPoll(){if(pollTask)await pollTask;return poll();}
async function action(method,args=[],success='',context=null){if(store.requestPending){notify('请等待当前请求完成。');return {ok:false};}store.requestPending=true;actionContext=context;renderControls();try{const data=await api(method,...args);const fresh=await freshPoll();if(success)notify(success);return {ok:true,data,fresh};}catch(error){reportError(error.message||'操作未完成。');return {ok:false};}finally{store.requestPending=false;renderControls();}}
function reportError(message){if($('#wizard').open){wizardError(message);$('#wizardBody').scrollTop=0;}else showDialog('操作未完成','<p>'+escapeHTML(message)+'</p>');}
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
 setText('versionButton',currentKnown?'v'+version(u.current_version):'版本与更新');
 $('#versionButton').title='版本与更新'+(currentKnown?' · v'+version(u.current_version):'');
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
$('#versionButton').onclick=()=>{updateChannelDirty=false;renderUpdates();$('#updateDialog').showModal();$('#updateClose').focus();};
$('#updateClose').onclick=()=>$('#updateDialog').close();
$('#updateDialog').addEventListener('close',()=>$('#versionButton').focus());
$('#updateChannel').onchange=()=>{updateChannelDirty=true;updateError='';renderUpdates();};
$('#updateCheck').onclick=()=>updateAction('check');$('#updateDownload').onclick=()=>updateAction('download');$('#updateCancel').onclick=()=>updateAction('cancel');$('#updateInstall').onclick=()=>updateAction('install');$('#updateRelease').onclick=()=>updateAction('open_release');
function render(){renderHome();renderPresets();if(store.draft){completeDeviceSetup();renderDeviceOptions();renderResources();renderSummary();renderVaultChoice();}renderSessions();renderControls();const a=store.activity;const signature=JSON.stringify([a.kind,a.status,a.detail]);if(signature!==lastActivitySignature){lastActivitySignature=signature;if($('#wizard').open&&a.status==='操作未完成'&&a.detail)wizardError(a.detail);else if(!$('#wizard').open&&store.readiness.ready&&a.status==='操作未完成'&&a.detail)notify('上次操作未完成：'+a.detail);if($('#wizard').open&&actionContext==='verify'&&a.kind==='idle'&&a.detail)setText('cloudFeedback',a.detail);}
 if(!firstSetupHandled&&store.snapshot){firstSetupHandled=true;if(!store.presets.length&&!store.recording)openWizard('new',0,true);}}
function renderHome(){
 const a=store.activity,r=store.readiness,recording=store.recording;
 const closing=!!store.snapshot?.closing;
 const foreground=!!a.busy&&!['devices','idle'].includes(a.kind);
 const checking=r.checking===true||a.kind==='devices'&&a.busy===true;
 const errors=Array.isArray(r.errors)?r.errors:[];
 let label='请选择或新建录制预设',title='记录体验',subtitle='边体验，边说出你此刻的想法。',button='开始录制';
 if(recording){
  label=a.status||'正在录制';title=formatTime(a.elapsed_seconds);subtitle=store.saved.game||'正在记录这次体验';
  button=store.saved.transcription_provider==='later'?'结束并保存':'结束并转写';
 }else if(foreground){
  label=a.status||'正在处理';button=a.kind==='starting'?'正在开始…':a.kind==='saving'?'正在保存…':'正在处理…';
 }else if(!store.connected)label='正在连接记录器';
 else if(store.requestPending)label='正在处理请求…';
 else if(checking)label='正在检查录制条件';
 else if(r.ready)label='准备就绪';
 else if(store.activeId)label='录制条件尚未满足，请重新检查';
 if(closing){label='正在安全关闭';button='正在安全关闭…';}
 const cancelPending=store.snapshot?.updates?.cancel_pending===true;
 if(cancelPending){label='取消尚未确认，请保留窗口';button='等待取消确认';}
 let blockers=[];
 if(!closing&&!store.connected&&connectionMessage)blockers=[connectionMessage];
 else if(!closing&&!recording&&!foreground&&!checking&&!store.requestPending){
  blockers=errors.map(e=>e.message).filter(Boolean);
  if(!r.ready&&!$('#wizard').open&&a.status==='操作未完成'&&a.detail&&!blockers.includes(a.detail))blockers.push(a.detail);
 }
 // Readiness and its blockers replace each other inside ONE above-button slot.
 // Keep the service's start/stop authority; presentation never enables capture.
 $('#homeTitle').classList.toggle('is-timer',recording);
 setText('homeTitle',title);setText('homeSubtitle',subtitle);
 setText('homeStatus',blockers.length?'':label);
 $('#homeStatus').className='capture-label'+(recording?' recording':!closing&&!checking&&!store.requestPending&&r.ready&&store.connected?' ready':'');
 const blockerText=blockers.join('\n'),changed=$('#blockers').textContent!==blockerText;
 show('homeStatus',!blockers.length);setText('blockers',blockerText);show('blockers',!!blockers.length);
 if(changed)$('#statusSlot').scrollTop=0;
 $('#statusSlot').tabIndex=$('#statusSlot').scrollHeight>$('#statusSlot').clientHeight?0:-1;
 setText('recordButtonText',button);$('#recordButton').classList.toggle('stopping',recording);
 show('jobDetail',cancelPending||closing||foreground&&!!a.detail);
 setText('jobDetail',cancelPending?'更新助手尚未确认取消，请打开顶部“版本与更新”重试取消。':closing?'正在保存并等待现有整理完成，完成后此窗口会自动关闭。':foreground?a.detail:'');
 setText('savedLocation',store.activeId&&store.saved.vault?'保存到 '+store.saved.vault:'尚未选择保存位置');
 $('#openVault').title=store.saved.vault||'';
}
function renderPresets(){const signature=JSON.stringify([store.presets,store.activeId]);if(signature===presetSignature)return;presetSignature=signature;$('#presetSelect').innerHTML=(store.activeId?'':'<option value="">选择录制预设</option>')+store.presets.map(p=>`<option value="${escapeHTML(p.id)}">${escapeHTML(p.name)}</option>`).join('');$('#presetSelect').value=store.activeId||'';}
function renderControls(){renderHome();renderUpdates();const locked=!store.connected||store.requestPending||store.busy;$('#recordButton').disabled=store.recording?(!store.connected||store.requestPending||!!store.activity.busy):!store.canStart;$('#presetSelect').disabled=locked||!store.presets.length;$('#newPresetButton').disabled=locked;$('#settingsButton').disabled=locked||!store.activeId;$('#openVault').disabled=!store.connected||store.requestPending||!store.activeId;
 const requestLocked=!store.connected||store.requestPending||saving;const conflict=store.recording||!!store.activity.busy&&store.activity.kind!=='devices';const fieldsLocked=requestLocked||conflict;$('#deviceFields').disabled=fieldsLocked;$('#recordingFields').disabled=fieldsLocked;
 ['game','source','target','mic','preset','language','hotwords','cloudKey'].forEach(id=>$('#'+id).disabled=fieldsLocked);
 $$('[data-provider]').forEach(button=>button.disabled=fieldsLocked);renderInputRecording(fieldsLocked);
 ['chooseVault','chooseHotwordFiles','existingModel','modelLocation','verifyCloud','refreshDevices'].forEach(id=>$('#'+id).disabled=locked||saving);
 $$('[data-remove-vocabulary]').forEach(button=>button.disabled=fieldsLocked);$('#dictionaryDownload').setAttribute('aria-disabled',requestLocked?'true':'false');$('#dictionaryDownload').tabIndex=requestLocked?-1:0;$('#bailianConsole').setAttribute('aria-disabled',requestLocked?'true':'false');$('#bailianConsole').tabIndex=requestLocked?-1:0;
 ['wizardClose','wizardCancel','wizardBack'].forEach(id=>$('#'+id).disabled=store.requestPending||saving);$('#reuseVault').disabled=fieldsLocked||store.snapshot?.default_vault?.is_directory===false;$('#wizardNext').disabled=locked||saving||(step===3&&store.needsVaultConfirmation);$('#wizardBack').classList.toggle('hidden',step===firstWizardStep());setText('wizardNext',saving?'正在保存…':step===3?'保存预设':step===0?'开始设置':'下一步');$$('[data-step]').forEach(b=>b.disabled=store.requestPending||saving);
 const m=store.snapshot?.model||{};$('#downloadModel').disabled=locked||saving||['verifying','ready'].includes(m.state);$('#existingModel').disabled=locked||saving||['downloading','verifying'].includes(m.state);$('#modelLocation').disabled=locked||saving||['downloading','verifying'].includes(m.state);$('#verifyCloud').disabled=locked||saving||!store.snapshot?.capabilities?.cloud_key||!!$('#cloudKey').value.trim();$$('[data-session-action]').forEach(b=>b.disabled=(!store.connected||store.requestPending||store.snapshot?.closing||(!['review','folder','rename'].includes(b.dataset.sessionAction)&&store.busy)||sessionActionBlocked(b.dataset.id,b.dataset.sessionAction)));}
$('#methodButton').onclick=()=>showDialog('让想法跟上体验',$('#methodContent').innerHTML);
$('#recordButton').onclick=()=>{if(store.recording)action('stop_recording');else if(store.canStart)action('start_recording',[store.startPayload()]);};
$('#openVault').onclick=()=>action('open_folder');
$('#newPresetButton').onclick=()=>openWizard('new');$('#settingsButton').onclick=()=>openWizard('edit');
$('#presetSelect').onchange=async event=>{const id=event.target.value;if(!id||id===store.activeId)return;const result=await action('select_preset',[id]);if(!result.ok){presetSignature='';renderPresets();}else{expandedSession=null;sessionSignature='';renderSessions();}};
function openWizard(mode='edit',requestedStep=null,automatic=false){if(!store.connected||store.requestPending||store.recording||(!automatic&&store.busy))return;wizardMode=mode;pendingDeviceSetup=null;store.openDraft(mode);step=Math.min(3,Math.max(firstWizardStep(),requestedStep??firstWizardStep()));store.step=step;deviceSignature='';vocabularySignature='';downloadDirectory=null;wizardError();$('#cloudKey').value='';setText('cloudFeedback','新密钥在完成设置时保存，取消时清空。');setText('downloadDestination','下载到软件所在文件夹。下载可暂停，关闭设置后会继续。');$('#advancedSettings').open=false;$('#manualWords').open=false;for(const el of $$('[data-draft]'))el.value=String(store.draft[el.dataset.draft]??'');$('#games').innerHTML=store.presets.map(p=>`<option value="${escapeHTML(p.name)}"></option>`).join('');setText('wizardContext',mode==='new'?'新建录制预设':'编辑录制预设');setText('presetDescription',mode==='new'?'为这款游戏保存一套录制设置。':'修改这套预设，下次录制会使用更新后的设置。');show('presetOnce',mode==='new');renderDeviceOptions(true);renderResources();renderVocabulary();renderSummary();renderVaultChoice();setStep(step,false);$('#wizard').showModal();renderControls();focusWizardStep();}
function cancelWizard(){if(store.requestPending||saving)return;pendingDeviceSetup=null;$('#cloudKey').value='';store.cancelDraft();$('#wizard').close();renderHome();renderControls();}
$('#wizardClose').onclick=cancelWizard;$('#wizardCancel').onclick=cancelWizard;$('#wizard').addEventListener('cancel',event=>{event.preventDefault();cancelWizard();});
function setStep(next,focus=true){step=Math.min(3,Math.max(firstWizardStep(),next));store.step=step;for(let i=0;i<=3;i++)show('step'+i,i===step);setText('wizardTitle',['记录方法','游戏与设备','录制与转写','保存位置'][step]);$$('[data-step]').forEach(b=>{const n=Number(b.dataset.step);b.classList.toggle('hidden',n<firstWizardStep());const number=b.querySelector('span');if(number)number.textContent=String(n-firstWizardStep()+1);b.classList.toggle('active',n===step);b.classList.toggle('completed',n<step);if(n===step)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');});$('#wizardBody').scrollTop=0;renderResources();renderSummary();renderControls();if(focus)focusWizardStep();}
function focusWizardStep(){const target=step===1?$('#game'):$('#wizardTitle');target.focus({preventScroll:true});}
function moveStep(next){if(next>step){for(let i=step;i<next;i++){const error=store.validateStep(i);if(error){wizardError(error);return;}}}wizardError();setStep(next);}
$('#wizardBack').onclick=()=>moveStep(Math.max(firstWizardStep(),step-1));$$('[data-step]').forEach(b=>b.onclick=()=>moveStep(Number(b.dataset.step)));$('#wizardNext').onclick=()=>{if(step<3)moveStep(step+1);else finishWizard();};
function fieldChanged(element){if(element.id==='source'||element.id==='mic')pendingDeviceSetup=null;store.updateDraft(element.dataset.draft,element.value);if(element.id==='source'){deviceSignature='';renderDeviceOptions(true);renderInputRecording();}if(element.dataset.draft==='hotword_manual')renderVocabulary();renderSummary();}
$$('[data-draft]').forEach(el=>el.addEventListener(el.tagName==='SELECT'?'change':'input',()=>fieldChanged(el)));
$('#cloudKey').addEventListener('input',()=>{setText('cloudFeedback',$('#cloudKey').value.trim()?'新密钥将在完成设置时保存。取消会清空输入。':'留空将保留已保存密钥。');renderControls();});
function deviceItems(kind){return store.snapshot?.devices?.[kind]||[];}
function deviceLabel(kind,value){return deviceItems(kind).find(i=>String(i.itemValue)===String(value))?.itemName||String(value||'尚未选择');}
function fillDevice(select,kind,value){if(document.activeElement===select)return false;const current=String(value??''),items=deviceItems(kind),exists=items.some(i=>String(i.itemValue)===current);select.innerHTML=(exists?'':`<option value="${escapeHTML(current)}">${current?'已保存的选择（当前未找到）':'请选择'+(kind==='mic'?'麦克风':kind==='monitor'?'显示器':'游戏窗口')}</option>`)+items.map(i=>`<option value="${escapeHTML(i.itemValue)}" ${i.itemEnabled===false?'disabled':''}>${escapeHTML(i.itemName)}</option>`).join('');select.value=current;return true;}
function renderInputRecording(locked=false){
 const d=store.draft,available=d?.source==='游戏窗口';
 $('#recordInputs').checked=!!d?.record_inputs;
 $('#recordInputs').disabled=locked||!available;
 setText('inputRecordingHint',available?'仅在选定游戏窗口位于前台时采集；切换到其他软件后暂停操作记录。支持键鼠与手柄在录制中切换。':'将录制范围改为“游戏窗口”并选择目标程序后，才能启用操作记录，避免记入其他软件中的按键。');
}
$('#recordInputs').onchange=()=>{if(store.draft&&store.draft.source==='游戏窗口'){store.updateDraft('record_inputs',$('#recordInputs').checked);renderSummary();}};
function renderDeviceOptions(force=false){if(!store.draft)return;const d=store.draft,kind=d.source==='整个显示器'?'monitor':'window';const signature=JSON.stringify([store.snapshot?.devices,kind,d.window,d.monitor,d.mic]);if(force||signature!==deviceSignature){const a=fillDevice($('#target'),kind,d[kind]);const b=fillDevice($('#mic'),'mic',d.mic);if(a&&b)deviceSignature=signature;}setText('targetLabel',kind==='monitor'?'显示器':'游戏窗口');const empty=devicesEmpty();setText('refreshDevices',empty?'设置 OBS':'刷新设备');setText('deviceFeedback',store.activity.kind==='devices'&&store.activity.busy?'正在查找可用窗口和麦克风…':empty?'尚未获取到设备。设置 OBS 后，将选中主显示器和默认麦克风。':'找不到游戏窗口？先打开游戏，再刷新。');}
$('#target').onchange=()=>{pendingDeviceSetup=null;if(store.draft){store.updateDraft(store.draft.source==='整个显示器'?'monitor':'window',$('#target').value);renderSummary();}};
function devicesEmpty(){return ['monitor','window','mic'].every(kind=>!deviceItems(kind).some(item=>item.itemEnabled!==false&&String(item.itemValue??'')));}
function selectionSignature(draft){return JSON.stringify([draft.source,draft.window,draft.monitor,draft.mic]);}
function completeDeviceSetup(){
 const pending=pendingDeviceSetup;if(!pending)return;
 if(store.draft!==pending.draft||!$('#wizard').open||selectionSignature(store.draft)!==pending.selection){pendingDeviceSetup=null;return;}
 const refresh=store.snapshot?.device_refresh;if(refresh?.id!==pending.id||refresh.state==='running')return;
 pendingDeviceSetup=null;
 if(refresh.state!=='succeeded'){wizardError(refresh.error||'OBS 设置未完成，请重试。');return;}
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
$('#refreshDevices').onclick=async()=>{
 const draft=store.draft,initialize=devicesEmpty(),selection=draft?selectionSignature(draft):'';
 pendingDeviceSetup=null;
 const result=await action('refresh_devices');
 if(initialize&&result.ok&&result.data?.refresh_id&&store.draft===draft&&$('#wizard').open&&selectionSignature(draft)===selection){
  pendingDeviceSetup={id:result.data.refresh_id,draft,selection};completeDeviceSetup();
 }
};
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
function renderResources(){if(!store.draft)return;const provider=store.draft.transcription_provider;show('localControls',provider==='local');show('cloudControls',provider==='qwen');show('advancedSettings',['local','qwen'].includes(provider));show('providerChoiceHint',!['local','qwen'].includes(provider));setText('providerChoiceHint','此预设尚未选择转写方式，请选择本地转写或 Qwen 转写。');$$('[data-provider]').forEach(button=>{const selected=button.dataset.provider===provider;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected||!provider&&button.dataset.provider==='local'?0:-1;});const m=store.snapshot?.model||{};const names={missing:'未准备',downloading:'下载中',paused:'已暂停',verifying:'正在校验',ready:'已准备好',error:'未完成'};setText('modelStatus',names[m.state]||'正在读取');$('#modelStatus').className='state-label '+(m.state||'');setText('modelPath',m.path||'可选择已有的模型文件夹，无需再次复制。');show('modelProgressArea',['downloading','paused','verifying'].includes(m.state));setText('modelProgressLabel',m.state==='verifying'?'正在检查文件是否完整':'已下载');setText('modelBytes',bytes(m.downloaded_bytes)+(m.total_bytes?' / '+bytes(m.total_bytes):''));if(m.total_bytes&&m.state!=='verifying')$('#modelProgress').value=Math.min(100,(m.downloaded_bytes||0)/m.total_bytes*100);else $('#modelProgress').removeAttribute('value');setText('modelError',m.error||'');show('modelError',!!m.error);setText('downloadModel',{downloading:'暂停下载',paused:'继续下载',verifying:'正在校验',ready:'已准备好',error:'重试下载'}[m.state]||'下载模型');setText('cloudStatus',store.snapshot?.capabilities?.cloud_key?'密钥已保存':'尚未保存密钥');renderControls();}
function renderSummary(){if(!store.draft)return;const d=store.draft,kind=d.source==='整个显示器'?'monitor':'window';setText('summaryGame',d.game.trim()||'未命名预设');setText('summaryChoices',deviceLabel(kind,d[kind])+' · '+d.preset+' · '+(providerNames[d.transcription_provider]||'')+(d.record_inputs?' · 记录操作':''));}
async function finishWizard(){if(saving||store.requestPending)return;for(let i=1;i<=3;i++){const error=store.validateStep(i);if(error){setStep(i);wizardError(error);return;}}saving=true;store.requestPending=true;wizardError();renderControls();let saved=false;try{const result=await api('save_preset',store.presetPayload(),store.editingId);saved=true;store.editingId=result?.id||result?.active_preset_id||store.editingId;let key=$('#cloudKey').value.trim();if(store.draft.transcription_provider==='qwen'&&key){await api('save_cloud_key',key);key='';$('#cloudKey').value='';}const fresh=await freshPoll();if(!fresh)throw new Error('预设已保存，但还没有收到新的检查结果。请稍后重试。');store.cancelDraft();$('#wizard').close();notify('预设已保存，正在检查是否可以开始。');}catch(error){if(error.code==='VAULT_REUSE_REQUIRED'){store.confirmedVault='';await freshPoll();setStep(3);renderVaultChoice();}wizardError((saved?'预设已保存。':'')+(error.message||'保存未完成，请检查后重试。'));$('#wizardBody').scrollTop=0;}finally{saving=false;store.requestPending=false;renderHome();renderControls();}}
$('#chooseVault').onclick=async()=>{const result=await action('choose_directory',['vault']);if(result.ok&&result.data?.path&&store.draft){store.updateDraft('vault',result.data.path);store.confirmVault();$('#vault').value=result.data.path;renderSummary();renderVaultChoice();renderControls();}};
function renderVaultChoice(){if(!store.draft)return;const info=store.snapshot?.default_vault||{},same=store.defaultVaultSelected,exists=same&&info.requires_confirmation===true;show('reuseVaultNotice',exists);show('reuseVault',exists&&store.needsVaultConfirmation&&info.is_directory!==false);setText('reuseVaultMessage',info.is_directory===false?'该位置已有同名文件，请选择其他文件夹。':store.needsVaultConfirmation?'发现已有同名资料库。是否使用它并保留其中的录像和笔记？':'将使用已有资料库，保留其中的录像和笔记。');setText('chooseVault',exists?'选择其他位置':'选择');setText('vaultHint',same?'默认保存在软件父级的 think-aloud-database，更新版本后可继续使用。':'每场体验分别保存，不覆盖已有录像或笔记。');}
$('#reuseVault').onclick=()=>{if(!store.canConfigure||!store.draft||store.snapshot?.default_vault?.is_directory===false)return;store.confirmVault();renderVaultChoice();renderControls();};
function renderVocabulary(){
 if(!store.draft)return;
 const files=store.draft.hotword_files||[],signature=JSON.stringify(files);
 if(signature!==vocabularySignature){
  vocabularySignature=signature;
  $('#hotwordFiles').innerHTML=files.map(file=>`<li><div class="vocabulary-file-info"><span class="vocabulary-file-name" title="${escapeHTML(file.name)}">${escapeHTML(file.name)}</span><span class="field-note">${file.words.length} 个词</span></div><button type="button" class="text-button vocabulary-view" data-view-vocabulary="${escapeHTML(file.id)}" aria-label="查看词库 ${escapeHTML(file.name)}">查看</button><button type="button" class="icon-button" data-remove-vocabulary="${escapeHTML(file.id)}" aria-label="移除词库 ${escapeHTML(file.name)}" title="移除词库">${icon('close')}</button></li>`).join('');
 }
 show('hotwordFiles',files.length>0);
 const manualCount=new Set(RecorderState.splitWords(store.draft.hotword_manual)).size,total=RecorderState.vocabularyWords(store.draft).length;
 const hasDefault=files.some(file=>(store.snapshot?.default_hotword_files||[]).some(bundled=>bundled.id===file.id));
 setText('vocabularySummary',hasDefault?'UI/UX 已选':files.length?'已选 '+files.length+' 份词库':total?'已添加词条':'未选词库');
 setText('vocabularyCount',total?`${files.length?'已选 '+files.length+' 份词库 · ':''}合并后 ${total} 个词`:'尚未选择词库');
 setText('manualWordCount',manualCount?manualCount+' 个词':'可选');show('vocabularyStorage',files.length>0);
}
$('#chooseHotwordFiles').onclick=async()=>{const result=await action('choose_hotword_files');if(result.ok&&store.draft&&result.data?.files?.length){const count=store.addVocabularyFiles(result.data.files);renderVocabulary();renderControls();notify(count?'已加入 '+count+' 份词库，完成设置后生效。':'这些词库已在列表中。');}};
$('#hotwordFiles').onclick=event=>{
 if(!store.draft)return;
 const view=event.target.closest('[data-view-vocabulary]');
 if(view?.dataset.viewVocabulary){
  const file=store.draft.hotword_files.find(item=>item.id===view.dataset.viewVocabulary);if(!file)return;
  showDialog(file.name,`<p>${file.words.length} 个词 · 当前预设选用的词条</p><ul class="vocabulary-words" aria-label="词库词条">${file.words.map(word=>'<li>'+escapeHTML(word)+'</li>').join('')}</ul><p>词条用于辅助识别，不会替换原话。移除词库只影响当前预设，不删除原文件。</p>`);
  return;
 }
 const button=event.target.closest('[data-remove-vocabulary]');if(!button||!store.canConfigure||saving)return;
 store.removeVocabularyFile(button.dataset.removeVocabulary);renderVocabulary();renderControls();$('#chooseHotwordFiles').focus();
};
$('#dictionaryDownload').onclick=event=>{event.preventDefault();if(!store.connected||store.requestPending||saving)return;action('open_dictionary_site');};
$('#verifyCloud').onclick=async()=>{setText('cloudFeedback','正在验证已保存的密钥…');await action('verify_cloud_key',[],'','verify');};
$('#modelLocation').onclick=async()=>{const result=await action('choose_directory',['download']);if(result.ok&&result.data?.path){downloadDirectory=result.data.path;setText('downloadDestination','下载到 '+downloadDirectory+'。关闭设置后下载会继续。');}};
$('#downloadModel').onclick=()=>{const m=store.snapshot?.model;if(m?.state==='downloading')action('model_action',['pause']);else if(m?.state==='paused')action('model_action',['download',downloadDirectory]);else showDialog('准备本地转写模型','<p>下载 Whisper large-v3，约 3.09 GB。下载完成后会检查文件完整性，之后更新软件无需重复下载。</p><p>保存位置：'+escapeHTML(downloadDirectory||'软件文件夹内的 models / large-v3')+'</p>',[{label:'开始下载',primary:true,run:()=>action('model_action',['download',downloadDirectory])}]);};
$('#existingModel').onclick=async()=>{const result=await action('choose_directory',['model']);if(result.ok&&result.data?.path)showDialog('使用已有模型','<p>'+escapeHTML(result.data.path)+'</p><p>检查通过后直接使用，不复制文件。移动目录后需要重新选择。</p>',[{label:'检查并使用',primary:true,run:()=>action('model_action',['import',result.data.path])}]);};
function sessionActionBlocked(id,action){
 const s=findSession(id);
 if(action==='review')return s?.can_review===false||(!s?.can_review&&!!store.sessionJob(id));
 return !!store.sessionJob(id)&&!['folder','raw','rename'].includes(action);
}
function sessionTitle(s){return s.session_name||s.game||s.id;}
function canReview(s){return s.can_review===true||(s.can_review!==false&&sessionKind(s)==='ready');}

function sessionKind(s){if(store.sessionJob(s.id))return 'processing';const status=String(s.state||'');if(s.error||/失败|错误|failed|error/i.test(status))return 'failed';if(/待整理|待转写|pending|recorded|saved/i.test(status))return 'pending';if(/可回看|完成|就绪|ready|done|complete/i.test(status))return 'ready';return 'other';}
function sessionDetail(s){return '<div class="session-detail">'+(s.error?'<p class="error-text">'+escapeHTML(s.error)+'</p>':'')+(s.warning?'<p>'+escapeHTML(s.warning)+'</p>':'')+'<p>'+escapeHTML(s.path||'')+'</p><div class="button-row">'+[['review','打开回看'],['process','重新整理'],['raw','原始录像'],['folder','资料文件夹'],['export','导出场次'],['recover','恢复云端任务']].map(([action,label])=>`<button class="text-button" data-session-action="${action}" data-id="${escapeHTML(s.id)}">${label}</button>`).join('')+'</div></div>';}
function sessionRow(s){
 const kind=sessionKind(s),job=store.sessionJob(s.id),state=job?(job.state==='queued'?'等待整理':'后台整理'):s.state||'状态未知';
 const progress=job?(job.state==='queued'?'已保存，等待前面的场次整理完成。':job.detail||'正在整理，仍可继续录制。'):'';
 const title=sessionTitle(s),ident=escapeHTML(s.id);
 const rename=`<button class="session-rename" data-session-action="rename" data-id="${ident}" aria-label="编辑片段名称：${escapeHTML(title)}" title="编辑片段名称"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4 5 5M4 20l5-1L20 8a2 2 0 0 0-5-5L4 14Z"/></svg></button>`;
 return `<article class="session-row"><div class="session-main"><div class="session-name"><div class="session-title-row"><strong>${escapeHTML(title)}${s.test?' <span class="test-tag">合成测试</span>':''}</strong>${rename}</div>${s.session_name?`<p class="session-game">${escapeHTML(s.game||'')}</p>`:''}<p class="session-meta"><span>${escapeHTML(formatDate(s.created))}</span><span class="session-duration"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/></svg>${escapeHTML(formatTime(s.duration))}</span></p>${progress?`<p class="session-progress">${escapeHTML(progress)}</p>`:''}</div><span class="session-state ${kind}">${escapeHTML(state)}</span>${canReview(s)?`<button class="session-quick" data-session-action="review" data-id="${ident}">${icon('play')}回看</button>`:['pending','failed'].includes(kind)?`<button class="session-quick" data-session-action="process" data-id="${ident}">${kind==='failed'?'重试':'整理'}</button>`:''}<button class="session-toggle" data-detail="${ident}" aria-expanded="${expandedSession===s.id}" aria-label="${expandedSession===s.id?'收起':'展开'}${escapeHTML(title)}详情">${icon('chevron')}</button></div>${expandedSession===s.id?sessionDetail(s):''}</article>`;
}
function renameSession(s){
 showDialog('编辑片段名称',`<p class="field-note">${escapeHTML(s.game||'')} · ${escapeHTML(formatDate(s.created))}</p><label for="sessionName">片段名称</label><input id="sessionName" maxlength="100" autocomplete="off" value="${escapeHTML(s.session_name||'')}" placeholder="例如：通道入口、首次使用背包"><p class="field-note">留空恢复默认名称。预设名称与保存位置不变。</p><p id="sessionNameError" class="error-text" role="alert"></p>`,[{label:'保存',primary:true,run:async()=>{
  const input=$('#sessionName'),name=input.value.trim();
  if(name.length>100||/[\u0000-\u001f\u007f]/.test(name)){setText('sessionNameError','名称最多 100 字，不能包含换行或控制字符。');return false;}
  try{await api('rename_session',s.id,name);await freshPoll();notify('片段名称已保存');return true;}
  catch(error){setText('sessionNameError',error.message||'名称保存失败，请重试。');return false;}
 }}]);
 const field=$('#sessionName');field.focus();field.select();
 field.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing){event.preventDefault();$('#actionFooter').lastElementChild?.click();}});
}
function renderSessions(force=false){const sessions=store.snapshot?.sessions||[],jobs=store.backgroundJobs,filter=$('#filter').value,search=$('#search').value.trim().toLowerCase();const signature=JSON.stringify([sessions,jobs,filter,search,expandedSession,store.activeId]);if(!force&&signature===sessionSignature)return;sessionSignature=signature;setText('sessionCount',sessions.length);const running=jobs.filter(job=>job.state==='running').length,queued=jobs.filter(job=>job.state==='queued').length;setText('backgroundSummary',[running?running+' 段整理中':'',queued?queued+' 段排队':''].filter(Boolean).join(' · '));show('backgroundSummary',!!jobs.length);const list=sessions.filter(s=>(filter==='all'||(filter==='ready'?canReview(s):sessionKind(s)===filter))&&`${s.session_name||''} ${s.game||''} ${s.id||''}`.toLowerCase().includes(search));const region=$('#sessionList'),scroll=region.scrollTop;region.innerHTML=list.length?list.map(sessionRow).join(''):'<div class="empty-state">'+(sessions.length?'没有符合条件的场次。':'<strong>这里会留下你的体验片段</strong><p>完成第一段录制后，回来看看当时的想法。</p>')+'</div>';region.scrollTop=scroll;renderControls();}
$('#search').oninput=()=>renderSessions();$('#filter').onchange=()=>renderSessions();
function findSession(id){return (store.snapshot?.sessions||[]).find(s=>String(s.id)===String(id));}
function processSession(s){if(store.saved.transcription_provider==='later'){showDialog('先选择整理方式','<p>当前预设只保存录制。选择本地或云端转写后，再回来整理此场次。</p>',[{label:'设置整理方式',primary:true,run:()=>{setTimeout(()=>openWizard('edit',2),0);}}]);return;}showDialog('整理这次体验','<p>'+escapeHTML(s.game||s.id)+'\n使用'+escapeHTML(providerNames[store.saved.transcription_provider]||'已保存的方式')+'。旧版文字与复盘会保留。</p>'+(store.saved.transcription_provider==='qwen'?'<p>将上传这次的麦克风录音到 Qwen，可能产生服务费用。</p>':'')+'<p>如果上次云端任务结果不确定，请从详情恢复原任务，避免重复提交。</p>',[{label:'开始整理',primary:true,run:()=>action('process_session',[s.id])}]);}
function recoverSession(s){showDialog('恢复已有云端任务','<p>填写已有任务编号，继续查询原任务，不重新上传录音。</p><label for="recoveryId">云端任务编号</label><input id="recoveryId" autocomplete="off" spellcheck="false" placeholder="已有 task_id">',[{label:'恢复任务',primary:true,run:()=>{const id=$('#recoveryId').value.trim();if(!id){notify('请填写已有任务编号。');return false;}return action('recover_cloud_task',[s.id,id]);}}]);}
$('#sessionList').addEventListener('click',event=>{const detail=event.target.closest('[data-detail]');if(detail){const id=detail.dataset.detail;expandedSession=String(expandedSession)===id?null:id;renderSessions();$('#sessionList').querySelector(`[data-detail="${CSS.escape(id)}"]`)?.focus();return;}const button=event.target.closest('[data-session-action]');if(!button)return;const s=findSession(button.dataset.id);if(!s)return;const name=button.dataset.sessionAction;if(name==='rename')renameSession(s);else if(name==='process')processSession(s);else if(name==='recover')recoverSession(s);else if(name==='review')action('open_review',[s.id]);else action({folder:'open_folder',raw:'open_raw',export:'package_session'}[name],[s.id]);});
function begin(){if(booted)return;booted=true;poll();setInterval(poll,1000);}window.addEventListener('pywebviewready',begin);if(window.pywebview?.api)begin();setTimeout(()=>{if(!booted){connectionMessage='尚未连接记录器。请从桌面应用打开。';renderHome();}},6000);

// A fixed external destination, opened by the native bridge without any key.
$('#bailianConsole').onclick=async event=>{event.preventDefault();if(store.requestPending||saving)return;await action('open_bailian_console');};
