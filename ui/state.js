/* Configuration drafts never mutate the persisted preset snapshot. */
(function (root, factory) {
  const exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  else root.RecorderState = exported;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const FIELDS = ['game','vault','preset','source','window','monitor','mic','language','hotwords','hotword_files','hotword_manual','transcription_provider','record_inputs'];
  const clone = value => JSON.parse(JSON.stringify(value));
  const splitWords = text => String(text||'').replace(/^\uFEFF/,'').split(/[,，;；、\r\n]+/).map(word=>word.normalize('NFC').trim()).filter(Boolean);
  const vocabularyWords = draft => [...new Set([...(draft?.hotword_files||[]).flatMap(file=>file.words||[]),...splitWords(draft?.hotword_manual)].map(word=>word.normalize('NFC').trim()).filter(Boolean))];
  function defaults(vault='') {
    return {game:'',vault,preset:'均衡 1080p30',source:'游戏窗口',window:'',monitor:'',mic:'',language:'zh',hotwords:'',hotword_files:[],hotword_manual:'',transcription_provider:'local',record_inputs:false};
  }
  class State {
    constructor() { this.snapshot=null;this.connected=false;this.draft=null;this.editingId=null;this.step=1;this.requestPending=false;this.confirmedVault=''; }
    accept(snapshot) { this.snapshot=clone(snapshot);this.connected=true; }
    disconnect() { this.connected=false; }
    get saved() { return this.snapshot?.config||{}; }
    get activity() { return this.snapshot?.activity||{}; }
    get readiness() { return this.snapshot?.readiness||{ready:false,checking:true,errors:[]}; }
    get presets() { return this.snapshot?.presets||[]; }
    get activeId() { return this.snapshot?.active_preset_id||null; }
    get backgroundJobs() { return this.snapshot?.background_jobs||[]; }
    sessionJob(id) { return this.backgroundJobs.find(job=>String(job.session_id)===String(id)); }
    get recording() { return this.activity.kind==='recording'; }
    get busy() { return !!this.snapshot?.closing||!!this.activity.busy||this.recording; }
    get canStart() { return this.connected&&!this.requestPending&&!this.busy&&this.readiness.ready===true&&this.readiness.checking!==true; }
    get canConfigure() { return this.connected&&!this.requestPending&&!this.busy; }
    sameVault(a,b) { return !!a&&!!b&&String(a).replace(/\\/g,'/').replace(/\/$/,'').toLowerCase()===String(b).replace(/\\/g,'/').replace(/\/$/,'').toLowerCase(); }
    get defaultVaultSelected() { return !!this.draft&&this.sameVault(this.draft.vault,this.snapshot?.default_vault?.path); }
    get needsVaultConfirmation() { return this.defaultVaultSelected&&this.snapshot?.default_vault?.requires_confirmation===true&&!this.sameVault(this.confirmedVault,this.draft.vault); }
    confirmVault() { if(this.draft)this.confirmedVault=this.draft.vault; }
    openDraft(mode='edit') {
      this.confirmedVault='';
      this.editingId=mode==='edit'?this.activeId:null;
      this.draft=defaults(this.snapshot?.suggested_vault||this.saved.vault||this.snapshot?.default_vault?.path||'');
      if(!this.editingId)this.draft.hotword_files=clone(this.snapshot?.default_hotword_files||[]);
      if(this.editingId) for(const key of FIELDS) if(this.saved[key]!==undefined)this.draft[key]=clone(this.saved[key]);
      this.draft.record_inputs=this.draft.source==='游戏窗口'&&this.draft.record_inputs===true;
      // Legacy record-only presets remain intact until the user saves an explicit
      // transcription choice. Never silently turn an old preset into cloud use.
      if(!['local','qwen'].includes(this.draft.transcription_provider))this.draft.transcription_provider='';
      if(!Array.isArray(this.draft.hotword_files))this.draft.hotword_files=[];
      if(this.editingId&&!Array.isArray(this.saved.hotword_files))this.draft.hotword_manual=this.saved.hotwords||'';
      this.syncVocabulary();
      this.step=1;
      return this.draft;
    }
    cancelDraft() { this.draft=null;this.editingId=null;this.step=1;this.confirmedVault=''; }
    updateDraft(key,value) { if(this.draft&&FIELDS.includes(key)){this.draft[key]=key==='record_inputs'?value===true:value;if(this.draft.source!=='游戏窗口')this.draft.record_inputs=false;if(key==='hotwords')this.draft.hotword_manual=value;if(['hotwords','hotword_files','hotword_manual'].includes(key))this.syncVocabulary();} }
    syncVocabulary() { if(this.draft)this.draft.hotwords=vocabularyWords(this.draft).join('\n'); }
    addVocabularyFiles(files) { if(!this.draft)return 0;const ids=new Set(this.draft.hotword_files.map(file=>file.id));let count=0;for(const file of files||[]){if(!ids.has(file.id)){this.draft.hotword_files.push(clone(file));ids.add(file.id);count++;}}this.syncVocabulary();return count; }
    removeVocabularyFile(id) { if(this.draft){this.draft.hotword_files=this.draft.hotword_files.filter(file=>file.id!==id);this.syncVocabulary();} }
    presetPayload() { if(!this.draft)throw new Error('没有正在编辑的预设。');return {...clone(this.draft),name:this.draft.game.trim(),game:this.draft.game.trim(),...(this.sameVault(this.confirmedVault,this.draft.vault)?{confirmed_vault:this.confirmedVault}:{})}; }
    startPayload() { return {}; }
    validateStep(step=this.step) {
      const d=this.draft;if(!d)return '请先打开录制设置。';
      if(step===1){if(!d.game.trim())return '请填写游戏或项目名称。';if(!d[d.source==='整个显示器'?'monitor':'window'])return '请选择要录制的窗口或显示器。';if(!d.mic)return '请选择麦克风。';}
      if(step===2&&!['local','qwen'].includes(d.transcription_provider))return '请选择本地转写或 Qwen 转写。';
      if(step===3&&!d.vault)return '请选择保存文件夹。';
      if(step===3&&this.needsVaultConfirmation)return '发现已有资料库。请先选择“使用已有资料库”，或选择其他位置。';
      return '';
    }
  }
  return {State,FIELDS,defaults,splitWords,vocabularyWords};
});
