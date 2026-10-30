'use strict';
/* 场次库和洞察两个窗口共用的自绘外框：窗口按钮、边框配色、标题「游戏名 场次库 / 洞察」。 */
(function(root){
  const api=()=>root.pywebview?.api;
  function frameColor(){const paper=getComputedStyle(document.documentElement).getPropertyValue('--paper').trim();try{api()?.win_set_frame_color?.(paper)?.catch?.(()=>{});}catch(_){}}
  document.querySelectorAll('[data-win]').forEach(button=>button.onclick=()=>{const name={min:'win_minimize',max:'win_toggle_maximize',close:'win_close'}[button.dataset.win];try{api()?.[name]?.()?.catch?.(()=>{});}catch(_){}});
  // The window word (场次库 / 洞察) is fixed by the page; the game follows the main window.
  function title(game){const text=[game,document.body.dataset.window].filter(Boolean).join(' ');document.getElementById('deskGame').textContent=text;document.title=text;}
  frameColor();
  if(api())frameColor();else root.addEventListener('pywebviewready',frameColor);
  root.ThinkAloudChrome={title};
})(globalThis);
