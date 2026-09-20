const {Plugin,Notice}=require('obsidian');
module.exports=class ExperienceOpener extends Plugin {
  async onload(){
    // Upstream 1.3.0 seeks on timestamps only. Also support clicking the words.
    this.registerDomEvent(document,'click',event=>{
      const row=event.target.closest?.('.mt-segment');
      if(!row||event.target.closest('.mt-ts')||window.getSelection()?.toString())return;
      const leaf=this.app.workspace.getLeavesOfType('media-transcript-view').find(l=>l.view.containerEl.contains(row));
      if(!leaf?.view.mediaEl)return;
      leaf.view.manualScrollUntil=0;
      leaf.view.mediaEl.currentTime=Number(row.dataset.start);
      leaf.view.mediaEl.play().catch(()=>new Notice('点击视频播放按钮以开始回放。'));
    });
    this.registerObsidianProtocolHandler('experience',async p=>{
      this.app.workspace.onLayoutReady(()=>this.openExperience(p.file,p.nonce));
    });
    this.lastNonce='';
    this.registerInterval(window.setInterval(async()=>{
      if(this.busy)return;
      try {
        const files=(await this.app.vault.adapter.list('.experience/requests')).files.filter(p=>p.endsWith('.json')).sort();
        if(!files.length)return;
        const request=JSON.parse(await this.app.vault.adapter.read(files[files.length-1]));
        if(!request.nonce||request.nonce===this.lastNonce||Date.now()-request.created>60000)return;
        this.busy=true;this.lastNonce=request.nonce;
        await this.openExperience(request.file,request.nonce);
      }catch(e){console.debug('Experience opener waiting',e.message)}finally{this.busy=false;}
    },500));
  }
  async openExperience(path,nonce){
    if(!path||path.includes('..'))return;
    if(!/^[a-f0-9]{32}$/.test(nonce||''))nonce=crypto.randomUUID().replaceAll('-','');
    const file=this.app.vault.getAbstractFileByPath(path);
    if(!file){new Notice('未找到录像，请确认打开的是完整资料库。');return;}
    if(!this.app.plugins.getPlugin('media-transcript')){new Notice('请启用 Media Transcript 插件。');return;}
    const leaf=this.app.workspace.getLeaf(false);
    await leaf.setViewState({type:'media-transcript-view',state:{file:path},active:true});
    this.app.workspace.leftSplit.collapse();
    this.app.workspace.revealLeaf(leaf);
    const media=leaf.view.mediaEl;
    for(let i=0;i<50&&media&&media.readyState<1&&!media.error;i++)await new Promise(r=>setTimeout(r,100));
    const result={file:path,nonce,opened:Date.now(),duration:media?.duration,segments:leaf.view.segments?.length,error:media?.error?.message||(!media||media.readyState<1?'录像未加载':null)};
    if(!await this.app.vault.adapter.exists('.experience/ack'))await this.app.vault.adapter.mkdir('.experience/ack');
    await this.app.vault.adapter.write('.experience/ack/'+nonce+'.json',JSON.stringify(result));
    if(media)this.registerDomEvent(media,'seeked',()=>this.app.vault.adapter.write('.experience/ack/seek-'+Date.now()+'.json',JSON.stringify({file:path,time:media.currentTime,paused:media.paused,active:leaf.view.activeIndex})));
  }
};
