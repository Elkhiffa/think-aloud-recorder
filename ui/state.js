/* Configuration drafts never mutate the persisted preset snapshot. */
(function (root, factory) {
  const exported = factory();
  if (typeof module === 'object' && module.exports) module.exports = exported;
  else root.RecorderState = exported;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const FIELDS = ['game','vault','preset','source','window','monitor','mic','language','hotwords','hotword_files','hotword_manual','transcription_provider','obsidian_exe'];
  const clone = value => JSON.parse(JSON.stringify(value));
  const splitWords = text => String(text||'').replace(/^\uFEFF/,'').split(/[,，;；、\r\n]+/).map(word=>word.normalize('NFC').trim()).filter(Boolean);
  const vocabularyWords = draft => [...new Set([...(draft?.hotword_files||[]).flatMap(file=>file.words||[]),...splitWords(draft?.hotword_manual)].map(word=>word.normalize('NFC').trim()).filter(Boolean))];
  function defaults(vault='') {
    return {game:'',vault,preset:'均衡 1080p30',source:'游戏窗口',window:'',monitor:'',mic:'',language:'zh',hotwords:'',hotword_files:[],hotword_manual:'',transcription_provider:'later',obsidian_exe:''};
  }
  class State {
    constructor() { this.snapshot=null;this.connected=false;this.draft=null;this.editingId=null;this.step=1;this.requestPending=false; }
    accept(snapshot) { this.snapshot=clone(snapshot);this.connected=true; }
    disconnect() { this.connected=false; }
    get saved() { return this.snapshot?.config||{}; }
    get activity() { return this.snapshot?.activity||{}; }
    get readiness() { return this.snapshot?.readiness||{ready:false,checking:true,errors:[]}; }
    get presets() { return this.snapshot?.presets||[]; }
    get activeId() { return this.snapshot?.active_preset_id||null; }
    get recording() { return this.activity.kind==='recording'; }
    get busy() { return !!this.activity.busy||this.recording; }
    get canStart() { return this.connected&&!this.requestPending&&!this.busy&&this.readiness.ready===true&&this.readiness.checking!==true; }
    get canConfigure() { return this.connected&&!this.requestPending&&!this.busy; }
    openDraft(mode='edit') {
      this.editingId=mode==='edit'?this.activeId:null;
      this.draft=defaults(this.snapshot?.suggested_vault||this.saved.vault||'');
      if(this.editingId) for(const key of FIELDS) if(this.saved[key]!==undefined)this.draft[key]=clone(this.saved[key]);
      if(!Array.isArray(this.draft.hotword_files))this.draft.hotword_files=[];
      if(this.editingId&&!Array.isArray(this.saved.hotword_files))this.draft.hotword_manual=this.saved.hotwords||'';
      this.syncVocabulary();
      this.step=1;
      return this.draft;
    }
    cancelDraft() { this.draft=null;this.editingId=null;this.step=1; }
    updateDraft(key,value) { if(this.draft&&FIELDS.includes(key)){this.draft[key]=value;if(key==='hotwords')this.draft.hotword_manual=value;if(['hotwords','hotword_files','hotword_manual'].includes(key))this.syncVocabulary();} }
    syncVocabulary() { if(this.draft)this.draft.hotwords=vocabularyWords(this.draft).join('\n'); }
    addVocabularyFiles(files) { if(!this.draft)return 0;const ids=new Set(this.draft.hotword_files.map(file=>file.id));let count=0;for(const file of files||[]){if(!ids.has(file.id)){this.draft.hotword_files.push(clone(file));ids.add(file.id);count++;}}this.syncVocabulary();return count; }
    removeVocabularyFile(id) { if(this.draft){this.draft.hotword_files=this.draft.hotword_files.filter(file=>file.id!==id);this.syncVocabulary();} }
    presetPayload() { if(!this.draft)throw new Error('没有正在编辑的预设。');return {...clone(this.draft),name:this.draft.game.trim(),game:this.draft.game.trim()}; }
    startPayload() { return {}; }
    validateStep(step=this.step) {
      const d=this.draft;if(!d)return '请先打开录制设置。';
      if(step===1){if(!d.game.trim())return '请填写游戏或项目名称。';if(!d[d.source==='整个显示器'?'monitor':'window'])return '请选择要录制的窗口或显示器。';if(!d.mic)return '请选择麦克风。';}
      if(step===2&&!['later','local','qwen'].includes(d.transcription_provider))return '请选择录制结束后的整理方式。';
      if(step===3&&!d.vault)return '请选择保存文件夹。';
      return '';
    }
  }
  return {State,FIELDS,defaults,splitWords,vocabularyWords};
});
