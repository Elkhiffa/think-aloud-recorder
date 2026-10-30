'use strict';
/* 场次库和洞察窗口的左右分隔条：拖动、方向键、双击或回车恢复默认；两栏各有像素最小宽度。
   比例（左栏占可分配宽度的份额）经窗口接口 get_layout / save_layout 存在软件的 state 目录。 */
(function(root){
  const valid=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0.05&&value<=0.95;
  function attach({layout,handle,key,share,minFirst,minSecond,label,api}){
    let value=share,dragging=null;
    const fallback=share;
    function measure(){
      const style=getComputedStyle(layout),size=handle.getBoundingClientRect().width;
      const available=layout.clientWidth-(parseFloat(style.paddingLeft)||0)-(parseFloat(style.paddingRight)||0)-size;
      if(available<=0)return null;
      // When the window is narrower than both minimums, the first column keeps its minimum and the second shrinks.
      const min=Math.min(1,minFirst/available),max=Math.max(min,1-minSecond/available);
      return {available,min,max,start:layout.getBoundingClientRect().left+(parseFloat(style.paddingLeft)||0)};
    }
    function render(){
      const m=measure();if(!m)return null;
      const clamped=Math.max(m.min,Math.min(m.max,value));
      layout.style.setProperty('--first',Math.round(clamped*m.available)+'px');
      handle.setAttribute('aria-valuemin',String(Math.round(m.min*100)));
      handle.setAttribute('aria-valuemax',String(Math.round(m.max*100)));
      handle.setAttribute('aria-valuenow',String(Math.round(clamped*100)));
      handle.setAttribute('aria-valuetext',`${label[0]} ${Math.round(clamped*100)}%，${label[1]} ${Math.round((1-clamped)*100)}%`);
      return {...m,value:clamped};
    }
    async function save(){try{await api()?.save_layout?.(key,value);}catch(_){/* An unsaved width must not interrupt reading. */}}
    function set(next){const m=render();if(!m)return;value=Math.max(m.min,Math.min(m.max,next));render();}
    function reset(){value=fallback;render();save();}
    function finish(event){
      if(!dragging||(event&&event.pointerId!==dragging.id))return;
      if(handle.hasPointerCapture?.(dragging.id))handle.releasePointerCapture(dragging.id);
      dragging=null;document.body.classList.remove('resizing-columns');save();
    }
    handle.setAttribute('role','separator');handle.setAttribute('aria-orientation','vertical');handle.tabIndex=0;
    handle.addEventListener('pointerdown',event=>{
      if(event.button!==0||dragging)return;
      const m=render();if(!m)return;
      event.preventDefault();handle.focus({preventScroll:true});
      dragging={id:event.pointerId,offset:event.clientX-m.start-m.available*m.value};
      handle.setPointerCapture(event.pointerId);document.body.classList.add('resizing-columns');
    });
    handle.addEventListener('pointermove',event=>{
      if(!dragging||event.pointerId!==dragging.id)return;
      const m=measure();if(!m)return;
      set((event.clientX-m.start-dragging.offset)/m.available);
    });
    for(const name of ['pointerup','pointercancel','lostpointercapture'])handle.addEventListener(name,finish);
    root.addEventListener('blur',()=>finish());
    handle.addEventListener('dblclick',reset);
    handle.addEventListener('keydown',event=>{
      if(event.altKey||event.ctrlKey||event.metaKey||event.isComposing)return;
      if(!['ArrowLeft','ArrowRight','Home','End','Enter'].includes(event.key))return;
      event.preventDefault();
      if(event.key==='Enter'){reset();return;}
      const m=render();if(!m)return;
      const step=event.shiftKey?0.1:0.02;
      set(event.key==='Home'?m.min:event.key==='End'?m.max:m.value+(event.key==='ArrowLeft'?-step:step));save();
    });
    new ResizeObserver(()=>render()).observe(layout);
    render();
    return {
      async load(){try{const response=await api()?.get_layout?.();const saved=response?.ok?response.data?.[key]:null;if(valid(saved)&&!dragging){value=saved;render();}}catch(_){}},
      render
    };
  }
  root.ThinkAloudSplit={attach};
})(globalThis);
