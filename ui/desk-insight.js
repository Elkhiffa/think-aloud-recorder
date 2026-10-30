'use strict';
/* 洞察窗口：标题跟随当前游戏，左右两栏之间的分隔条。洞察本身由 insight.js 负责。 */
(function(){
  const api=()=>window.pywebview?.api;
  const split=ThinkAloudSplit.attach({layout:document.querySelector('.split'),handle:document.getElementById('insightSplit'),key:'insight',share:.5,
    minFirst:440,minSecond:400,label:['报告','证据'],api});
  async function start(){
    split.load();
    try{const response=await api().desk_state();if(response?.ok)ThinkAloudChrome.title(response.data.game);}catch(_){}
  }
  ThinkAloudChrome.title('');
  if(api())start();else window.addEventListener('pywebviewready',start,{once:true});
})();
