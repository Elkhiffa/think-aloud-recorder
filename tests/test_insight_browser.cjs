'use strict';
// Production insight assets in real Edge with a synthetic bridge; no real vault or agent output.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.join(__dirname,'..'),out=path.resolve(process.env.REVIEW_TEST_OUTPUT||path.join(root,'work','insight-browser'));
fs.mkdirSync(out,{recursive:true});
const S1='20261008-120000-aaaaaa',S2='20261009-120000-bbbbbb';
const row=(session,id,extra={})=>Object.assign({session_id:session,instance_id:id,said_start:12,refers_start:2,refers_end:4,refers_basis:'same_time',screen:'bag',catalog_screen:'bag',elements:[],kind:'confusion',statement:'合成陈述 '+id,issue_tags:[],issue_links:[],event_id:'e1',event_title:'合成活动'},extra);
const instances=[row(S1,'i1',{statement:'清完提示后忘了目标 <img src=x>'}),row(S1,'i6',{refers_start:2,refers_end:300,said_start:600}),row(S2,'i1'),row(S2,'i2',{refers_basis:'earlier_session',refers_start:null,refers_end:null}),row(S1,'i3'),row(S2,'i9'),row(S2,'i5',{statement:'教学弹窗左半边多了一层灰色'}),row(S2,'i7',{statement:'染色方案存不下来',kind:'obstacle'})];
const link=(session,id,reason='合成理由')=>({session_id:session,instance_id:id,reason});
const overview={vault:'合成资料库',reports:[{name:'r.md',modified:1,bytes:10}],feedback:[],
  tag_groups:[{id:'cross',name:'跨系统'},{id:'play',name:'活动 / 玩法'},{id:'system',name:'系统'}],
  tags:[{id:'jhy',name:'江湖弈',group:'play',keywords:['江湖弈']},{id:'wll',name:'武林录',group:'play',keywords:[]},{id:'shop',name:'商店',group:'system',keywords:['商店']},
    ...Array.from({length:60},(_,i)=>({id:'x'+i,name:'跨系统评价'+i,group:'cross',keywords:[]}))],
  instance_tags:{[S1+'/i1']:['jhy'],[S2+'/i7']:['jhy'],[S1+'/i3']:['wll'],[S2+'/i1']:['shop']},session_labels:{[S1]:'1008',[S2]:'1009'},instances,
  issues:[{id:'TA-01',title:'目标明确仍有摩擦',description:'合成议题',status:'confirmed',support:[link(S2,'i2')],counter:[],children:[
     {id:'TA-07',parent:'TA-01',title:'外观染色中的断点',description:'中间议题',status:'confirmed',support:[],counter:[],children:[
      {id:'TA-07.1',parent:'TA-07',title:'染色方案存不下来',description:'第三层',status:'confirmed',support:[link(S2,'i7')],counter:[],children:[]}]},
     {id:'TA-01.1',parent:'TA-01',title:'清完提示后忘了目标',description:'成立理由：见 1008 i6、i1 和 1009 i9；并入 TA-07 之外。',status:'confirmed',support:[link(S1,'i1'),link(S1,'i6')],counter:[link(S2,'i1','专注时少提示反而好')],children:[]}]},
    {id:'BUG',title:'Bug',description:'',status:'confirmed',support:[link(S1,'i3')],counter:[],children:[
     {id:'BUG.1',parent:'BUG',title:'疑似：教学弹窗多出遮挡',description:'疑似缺陷',status:'confirmed',support:[link(S2,'i5')],counter:[],children:[]}]}],
  bug_unorganized:[{session_id:S2,ref:'t000005',start:30,end:32,text:'现在有几个bug',instances:[],bug_instances:[],state:'raw'}]};
const text=['# 总体判断','玩家清完提示后忘了目标 [1008 i1](i:'+S1+'/i1#TA-01.1)，见 [TA-01.1](issue:TA-01.1)。染色存不下来 [1009 i7](i:'+S2+'/i7#TA-07.1)。',
  '','- 不存在的引用 [1008 i8](i:'+S1+'/i8)','- 报告单独引用 [1009 i9](i:'+S2+'/i9)','','| 主题 | 议题 |','|---|---|','| 摩擦 | [TA-01](issue:TA-01) |'].join('\n');
const report={name:'r.md',text,citations:[
  {kind:'instance',session_id:S1,instance_id:'i1',issue:'TA-01.1',resolved:true},{kind:'issue',issue:'TA-01.1',resolved:true},{kind:'instance',session_id:S2,instance_id:'i7',issue:'TA-07.1',resolved:true},
  {kind:'instance',session_id:S1,instance_id:'i8',issue:null,resolved:false},{kind:'instance',session_id:S2,instance_id:'i9',issue:null,resolved:true},{kind:'issue',issue:'TA-01',resolved:true}]};
const types={'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript'};
const server=http.createServer((req,res)=>{const name=req.url==='/'?'insight.html':req.url.slice(1);const file=path.join(root,'ui',name);if(!['insight.html','insight.css','insight.js'].includes(name)){res.statusCode=404;return res.end();}res.setHeader('Content-Type',types[path.extname(file)]);res.end(fs.readFileSync(file));});
let browser;const result={scope:'Synthetic insight bridge; checks layout and interactions only.',checks:[],errors:[]};
async function main(){
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin=`http://127.0.0.1:${server.address().port}`;
  browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1440,height:900}});
  page.on('pageerror',error=>result.errors.push(String(error)));
  await page.addInitScript(([overview,report])=>{
    const pixel='data:image/gif;base64,R0lGODlhAQABAAAAACw=';
    window.__calls=[];window.__overview=overview;
    window.pywebview={api:{ready:async()=>({ok:true}),get_overview:async()=>({ok:true,data:structuredClone(window.__overview)}),read_report:async()=>({ok:true,data:report}),
      thumbnail:async()=>({ok:true,data:pixel}),open_review:async(session,at)=>{window.__calls.push(['open_review',session,at]);return {ok:true,data:{ready:true}};},
      add_feedback:async request=>{window.__calls.push(['add_feedback',request]);window.__overview.feedback.push({id:'f'+window.__overview.feedback.length,created:'2026-10-14T18:00:00+08:00',status:'open',...request});return {ok:true,data:structuredClone(window.__overview.feedback)};},
      edit_feedback:async(id,text)=>{window.__calls.push(['edit_feedback',id,text]);window.__overview.feedback.find(item=>item.id===id).text=text;return {ok:true,data:structuredClone(window.__overview.feedback)};},
      set_cover:async(tag,session,at)=>{window.__calls.push(['set_cover',tag,session,at]);const found=window.__overview.tags.find(item=>item.id===tag);found.cover={session_id:session,at};return {ok:true,data:structuredClone(window.__overview.tags)};},
      remove_feedback:async id=>{window.__calls.push(['remove_feedback',id]);window.__overview.feedback=window.__overview.feedback.filter(item=>item.id!==id);return {ok:true,data:structuredClone(window.__overview.feedback)};}}};
  },[overview,report]);
  const check=async(name,run)=>{await run();result.checks.push({name,pass:true});};
  await page.goto(origin);await page.waitForSelector('#issue-TA-01');
  await check('tree leads with titles; issue codes stay small at the end; sub-issues start collapsed',async()=>{
    const sub=page.locator('#issue-TA-01\\.1>.row>.toggle');
    assert.match(await sub.locator('.label').textContent(),/^清完提示后忘了目标/);
    assert.equal(await sub.locator('.code').textContent(),'TA-01.1');
    assert.match(await sub.locator('.n').textContent(),/^支持 2 · 反例 1/);
    assert.equal(await page.locator('#issue-TA-01-body').isVisible(),true);
    assert.equal(await page.locator('#issue-TA-01\\.1-body').isHidden(),true);
    assert.equal(await page.locator('#issue-BUG>.row>.toggle .label').textContent(),'BUG');
    assert.equal(await page.locator('#tabIssues,#tabProposed,#issuesPane,#proposedPane').count(),0);
    assert.equal(await page.locator('#toc').count(),0);
  });
  await check('report citation expands the collapsed sub-issue and scrolls to the card',async()=>{
    await page.locator('.cite',{hasText:'1008 i1'}).click();
    const card=page.locator('#issue-TA-01\\.1 .card[data-key="'+S1+'/i1"]');
    await card.waitFor({state:'visible'});await page.waitForTimeout(600);
    assert.equal(await card.isVisible(),true);
    const box=await card.boundingBox();assert.ok(box.y>0&&box.y<900,'card is inside the viewport');
  });
  await check('agent text is escaped and counter evidence is marked',async()=>{
    assert.equal(await page.locator('#evidenceList img[src="x"]').count(),0);
    assert.equal(await page.locator('.card.counter .badge',{hasText:'反例'}).count(),1);
  });
  await check('unresolved citation is marked and report-only citation gets a section',async()=>{
    assert.equal(await page.locator('.cite.unresolved').count(),1);
    assert.equal(await page.locator('#issue-cited .card[data-key="'+S2+'/i9"]').count(),1);
    assert.equal(await page.locator('table .cite',{hasText:'TA-01'}).count(),1);
  });
  await check('collapse all and expand all',async()=>{
    await page.locator('#collapseAll').click();
    assert.equal(await page.locator('#issue-TA-01-body').isHidden(),true);
    await page.locator('#expandAll').click();
    assert.equal(await page.locator('#issue-TA-01\\.1-body').isVisible(),true);
    assert.equal(await page.locator('#issue-BUG-raw-body').isVisible(),true);
  });
  await check('collapsed tree is the outline: collapse all, then open an issue and a sub-issue',async()=>{
    await page.locator('#collapseAll').click();
    assert.equal(await page.locator('#issue-TA-01-body').isHidden(),true);
    await page.locator('#issue-TA-01>.row>.toggle').click();
    await page.locator('#issue-TA-01\\.1>.row>.toggle').click();
    assert.equal(await page.locator('#issue-TA-01\\.1-body').isVisible(),true);
  });
  await check('evidence times open the review at that moment',async()=>{
    await page.locator('#expandAll').click();
    const card=page.locator('#issue-TA-01\\.1 .card[data-key="'+S1+'/i1"]');
    assert.equal(await card.locator('.card-title').textContent(),'困惑合成活动');
    assert.equal(await card.locator('.jump').textContent(),'00:02–00:12');
    await card.locator('.jump').click();
    await page.locator('#issue-BUG-raw-body .jump').click();
    await page.locator('[id="issue-TA-01.1"] .card[data-key="'+S1+'/i6"] .jump').click();
    const calls=await page.evaluate(()=>window.__calls);
    assert.deepEqual(calls.slice(-3),[['open_review',S1,2],['open_review',S2,30],['open_review',S1,590]]);
  });
  await page.screenshot({path:path.join(out,'insight-1440.png')});
  await check('three levels: a citation to a third-level card opens both ancestors; counts add up',async()=>{
    await page.locator('#collapseAll').click();
    assert.match(await page.locator('#issue-TA-01>.row>.toggle .n').textContent(),/^支持 4 · 反例 1/);
    await page.locator('.cite',{hasText:'1009 i7'}).click();
    const card=page.locator('[id="issue-TA-07.1"] .card[data-key="'+S2+'/i7"]');
    await card.waitFor({state:'visible'});
    assert.equal(await page.locator('#issue-TA-07-body').isVisible(),true);
    assert.equal(await page.locator('#issue-TA-07>.row>.toggle .label').textContent(),'外观染色中的断点');
  });
  await check('flag on an issue and on a card records feedback; the feedback tab edits and removes it',async()=>{
    await page.locator('#issue-TA-07>.row>.flag').click();
    await page.locator('#feedbackText').fill('应该并进操作路径那一组');await page.locator('.feedback-form button[type="submit"]').click();
    await page.waitForFunction(()=>document.querySelector('#feedbackCount').textContent==='(1)');
    await page.locator('[id="issue-TA-07.1"] .card[data-key="'+S2+'/i7"] .flag').click();
    await page.locator('#feedbackText').fill('界面名不对');await page.locator('.feedback-form button[type="submit"]').click();
    await page.waitForFunction(()=>document.querySelector('#feedbackCount').textContent==='(2)');
    const calls=(await page.evaluate(()=>window.__calls)).filter(call=>call[0]==='add_feedback');
    assert.deepEqual(calls.map(call=>call[1]),[{target:{kind:'issue',id:'TA-07'},text:'应该并进操作路径那一组'},
      {target:{kind:'instance',session_id:S2,instance_id:'i7',issue:'TA-07.1'},text:'界面名不对'}]);
    await page.locator('#tabFeedback').click();
    const first=page.locator('.feedback-item').first();
    assert.match(await first.locator('.feedback-target').textContent(),/阻碍 · 合成活动 1009 i7（在“染色方案存不下来”下）/);
    await first.locator('[data-feedback-edit]').click();await page.locator('#feedbackText').fill('界面名应为包裹/道具');
    await first.locator('button[type="submit"]').click();
    await page.waitForFunction(()=>document.querySelector('.feedback-text')?.textContent==='界面名应为包裹/道具');
    const second=page.locator('.feedback-item').nth(1);
    await second.locator('[data-feedback-remove]').click();await second.locator('[data-feedback-remove]').click();
    await page.waitForFunction(()=>document.querySelector('#feedbackCount').textContent==='(1)');
    await page.locator('.feedback-item [data-feedback-go]').click();
    assert.equal(await page.locator('#evidencePane').isVisible(),true);
  });
  await check('while scrolling, the current 洞察 and 议题 stay on top and the next 洞察 waits at the bottom',async()=>{
    await page.locator('#tabEvidence').click();await page.locator('#expandAll').click();
    const card=page.locator('[id="issue-TA-01.1"] .card[data-key="'+S1+'/i6"]');
    await page.locator('#evidencePane').evaluate(pane=>{const line=document.querySelector('.evidence-head').getBoundingClientRect().bottom;pane.scrollTop+=document.getElementById('issue-TA-01.1').getBoundingClientRect().top-line+120;});await page.waitForTimeout(200);
    const head=await page.locator('.evidence-head').boundingBox();
    const top1=await page.locator('#issue-TA-01>.row').boundingBox(),top2=await page.locator('[id="issue-TA-01.1"]>.row').boundingBox();
    assert.ok(Math.abs(top1.y-(head.y+head.height))<=2,'洞察 row sticks under the toolbar');
    assert.ok(Math.abs(top2.y-(top1.y+top1.height))<=2,'议题 row sticks under the 洞察 row');
    const cardBox=await card.boundingBox();assert.ok(cardBox.y+cardBox.height>top2.y+top2.height,'card scrolls beneath the sticky rows');
    await page.waitForFunction(()=>!document.querySelector('#nextBar').hidden);
    assert.match(await page.locator('#nextBar').textContent(),/BUG/);
    await page.locator('#nextBar [data-next="issue-BUG"]').click();await page.waitForTimeout(700);
    const bug=await page.locator('#issue-BUG>.row').boundingBox();assert.ok(bug.y>=head.y+head.height-2&&bug.y<450,'next 洞察 is brought up into view');
    // At the end of a 议题 its row is pushed up; it must slide under the 洞察 row, not cover it.
    const covered=await page.locator('#evidencePane').evaluate(pane=>{
      const section=document.getElementById('issue-TA-01.1'),row=document.querySelector('#issue-TA-01>.row');
      pane.scrollTop+=section.getBoundingClientRect().bottom-row.getBoundingClientRect().bottom-10;
      const box=row.getBoundingClientRect(),hit=document.elementFromPoint(box.left+box.width/2,box.top+box.height/2);
      return hit.closest('.row')===row;});
    assert.equal(covered,true,'洞察 row stays on top at the end of a 议题');
    await page.locator('#collapseAll').click();
  });
  await check('busier 议题 come first; references in descriptions are quiet marks that locate the card',async()=>{
    await page.locator('#collapseAll').click();await page.locator('#issue-TA-01>.row>.toggle').click();
    const order=await page.locator('#issue-TA-01-body>section').evaluateAll(list=>list.map(node=>node.id));
    assert.deepEqual(order.slice(0,2),['issue-TA-01.1','issue-TA-07']);
    await page.locator('[id="issue-TA-01.1"]>.row>.toggle').click();
    const desc=page.locator('[id="issue-TA-01.1-body"]>.desc');
    assert.deepEqual(await desc.locator('.cite').allTextContents(),['1008 i6','i1','1009 i9','TA-07']);
    await desc.locator('.cite',{hasText:'1009 i9'}).click();
    await page.locator('#issue-cited .card[data-key="'+S2+'/i9"]').waitFor({state:'visible'});
    await page.locator('#collapseAll').click();
  });
  await check('screen library: tag cards filter the tree, kind chips stack, filters clear',async()=>{
    await page.locator('#tabEvidence').click();await page.locator('#tabLibrary').click();
    assert.equal(await page.locator('#report').isHidden(),true);
    assert.deepEqual(await page.locator('.lib-toggle>span:first-child').allTextContents(),['跨系统','活动 / 玩法','系统']);
    assert.deepEqual(await page.locator('#lib-play .tag-name').allTextContents(),['江湖弈','武林录']);
    assert.equal(await page.locator('#lib-play .tag-card[data-tag="jhy"] .n').textContent(),'2');
    const coverBox=await page.locator('.tag-card[data-tag="jhy"] .cover').boundingBox(),nameBox=await page.locator('.tag-card[data-tag="jhy"] .tag-name').boundingBox();
    assert.ok(nameBox.y>=coverBox.y+coverBox.height,'name sits below the cover, not on it');
    await page.locator('.tag-card[data-tag="jhy"]').click();
    assert.match(await page.locator('#filterBar').textContent(),/江湖弈 ×/);
    assert.equal(await page.locator('#issue-BUG').count(),0);
    assert.deepEqual(await page.locator('#evidenceList .card').evaluateAll(cards=>cards.map(card=>card.dataset.key).sort()),[S1+'/i1',S2+'/i7'].sort());
    await page.locator('#issue-TA-01 .kinds [data-kind="obstacle"]').first().click();
    assert.deepEqual(await page.locator('#evidenceList .card').evaluateAll(cards=>cards.map(card=>card.dataset.key)),[S2+'/i7']);
    assert.equal(await page.locator('#kindBar [data-kind="obstacle"]').getAttribute('aria-pressed'),'true');
    await page.locator('.tag-card[data-tag="wll"]').click();
    assert.equal(await page.locator('#issue-BUG').count(),0,'kind filter still applies to the union of tags');
    await page.locator('[data-clear-all]').click();
    assert.equal(await page.locator('#filterBar').isHidden(),true);
    assert.equal(await page.locator('#issue-BUG').count(),1);
  });
  await check('the kind bar beside expand/collapse lists every kind with counts, multi-selects and clears',async()=>{
    await page.locator('#tabEvidence').click();
    assert.deepEqual(await page.locator('#kindBar .kind-chip').allTextContents(),['困惑 6','阻碍 1']);
    await page.locator('#kindBar [data-kind="confusion"]').click();await page.locator('#kindBar [data-kind="obstacle"]').click();
    assert.equal(await page.locator('#kindBar .kind-chip.active').count(),2);
    assert.equal(await page.locator('#filterBar').isHidden(),true,'kinds live in the kind bar, not the tag filter line');
    await page.locator('#kindBar [data-kind="confusion"]').click();
    assert.deepEqual(await page.locator('#evidenceList .card').evaluateAll(cards=>[...new Set(cards.map(card=>card.dataset.key))]),[S2+'/i7']);
    await page.locator('[data-clear-kinds]').click();
    assert.equal(await page.locator('#kindBar .kind-chip.active').count(),0);
  });
  await check('screen library: the current dimension sticks on top and the next one waits at the bottom',async()=>{
    await page.locator('#tabLibrary').click();await page.locator('#library').evaluate(pane=>pane.scrollTop=0);await page.waitForTimeout(100);
    await page.waitForFunction(()=>!document.querySelector('#libNext').hidden);
    assert.match(await page.locator('#libNext').textContent(),/活动 \/ 玩法/);
    await page.locator('#library').evaluate(pane=>pane.scrollTop=300);await page.waitForTimeout(150);
    const top=(await page.locator('#library').boundingBox()).y,head=await page.locator('#libgroup-cross>.lib-toggle').boundingBox();
    assert.ok(Math.abs(head.y-top)<=2,'current dimension heading sticks to the top');
    await page.locator('#libNext [data-lib-next]').click();await page.waitForTimeout(700);
    const next=await page.locator('#libgroup-play>.lib-toggle').boundingBox();assert.ok(next.y>=top-2&&next.y<top+600,'next dimension is brought into view');
    await page.locator('#library').evaluate(pane=>pane.scrollTop=0);
    // Collapsing a dimension may remove the scrollbar; the reserved gutter keeps card sizes still.
    const before=(await page.locator('#libgroup-play .tag-card').first().boundingBox()).width;
    await page.locator('#libgroup-cross>.lib-toggle').click();
    const after=(await page.locator('#libgroup-play .tag-card').first().boundingBox()).width;
    assert.equal(after,before,'card width does not jump when the scrollbar comes and goes');
    await page.locator('#libgroup-cross>.lib-toggle').click();
  });
  await check('right-click an evidence card sets the cover of its tag; citations clear filters to land',async()=>{
    await page.locator('#expandAll').click();
    await page.locator('[id="issue-TA-07.1"] .card[data-key="'+S2+'/i7"]').click({button:'right'});
    assert.equal(await page.locator('#menu').isVisible(),true);
    await page.locator('#menu [data-cover-tag="jhy"]').click();
    assert.deepEqual((await page.evaluate(()=>window.__calls)).at(-1),['set_cover','jhy',S2,2]);
    await page.waitForFunction(()=>document.querySelector('.tag-card[data-tag="jhy"] .cover')?.dataset.session);
    assert.equal(await page.locator('.tag-card[data-tag="jhy"] .cover').getAttribute('data-session'),S2);
    await page.locator('.tag-card[data-tag="wll"]').click();
    await page.locator('#tabReport').click();
    await page.locator('.cite',{hasText:'1008 i1'}).click();
    await page.locator('#issue-TA-01\\.1 .card[data-key="'+S1+'/i1"]').waitFor({state:'visible'});
    assert.equal(await page.locator('#filterBar').isHidden(),true);
    assert.equal(await page.locator('.flag svg').count()>0,true);
    assert.equal(await page.locator('.flag').first().getAttribute('aria-label'),'有问题？写一句怎么调');
  });
  await check('narrow window keeps the tree without horizontal scroll',async()=>{
    await page.locator('#tabEvidence').click();await page.setViewportSize({width:800,height:900});
    assert.equal(await page.locator('#expandAll').isVisible(),true);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    await page.screenshot({path:path.join(out,'insight-800.png')});
  });
  assert.deepEqual(result.errors,[]);
}
main().then(()=>{fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));},error=>{result.errors.push(String(error.stack||error));fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();server.close();});
