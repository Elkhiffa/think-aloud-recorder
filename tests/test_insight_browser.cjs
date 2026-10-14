'use strict';
// Production insight assets in real Edge with a synthetic bridge; no real vault or agent output.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.join(__dirname,'..'),out=path.resolve(process.env.REVIEW_TEST_OUTPUT||path.join(root,'work','insight-browser'));
fs.mkdirSync(out,{recursive:true});
const S1='20261008-120000-aaaaaa',S2='20261009-120000-bbbbbb';
const row=(session,id,extra={})=>Object.assign({session_id:session,instance_id:id,said_start:12,refers_start:2,refers_end:4,refers_basis:'same_time',screen:'bag',catalog_screen:'bag',elements:[],kind:'confusion',statement:'合成陈述 '+id,issue_tags:[],issue_links:[],event_id:'e1',event_title:'合成活动'},extra);
const instances=[row(S1,'i1',{statement:'清完提示后忘了目标 <img src=x>'}),row(S1,'i6',{refers_start:2,refers_end:300,said_start:600}),row(S2,'i1'),row(S2,'i2',{refers_basis:'earlier_session',refers_start:null,refers_end:null}),row(S1,'i3'),row(S2,'i9'),row(S2,'i5',{statement:'教学弹窗左半边多了一层灰色'}),row(S2,'i7',{statement:'染色方案存不下来'})];
const link=(session,id,reason='合成理由')=>({session_id:session,instance_id:id,reason});
const overview={vault:'合成资料库',reports:[{name:'r.md',modified:1,bytes:10}],feedback:[],session_labels:{[S1]:'1008',[S2]:'1009'},instances,
  issues:[{id:'TA-01',title:'目标明确仍有摩擦',description:'合成议题',status:'confirmed',support:[link(S2,'i2')],counter:[],children:[
     {id:'TA-01.1',parent:'TA-01',title:'清完提示后忘了目标',description:'成立理由：合成',status:'confirmed',support:[link(S1,'i1'),link(S1,'i6')],counter:[link(S2,'i1','专注时少提示反而好')],children:[]},
     {id:'TA-07',parent:'TA-01',title:'外观染色中的断点',description:'中间议题',status:'confirmed',support:[],counter:[],children:[
      {id:'TA-07.1',parent:'TA-07',title:'染色方案存不下来',description:'第三层',status:'confirmed',support:[link(S2,'i7')],counter:[],children:[]}]}]},
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
    assert.match(await first.locator('.feedback-target').textContent(),/困惑 · 合成活动 1009 i7（在“染色方案存不下来”下）/);
    await first.locator('[data-feedback-edit]').click();await page.locator('#feedbackText').fill('界面名应为包裹/道具');
    await first.locator('button[type="submit"]').click();
    await page.waitForFunction(()=>document.querySelector('.feedback-text')?.textContent==='界面名应为包裹/道具');
    const second=page.locator('.feedback-item').nth(1);
    await second.locator('[data-feedback-remove]').click();await second.locator('[data-feedback-remove]').click();
    await page.waitForFunction(()=>document.querySelector('#feedbackCount').textContent==='(1)');
    await page.locator('.feedback-item [data-feedback-go]').click();
    assert.equal(await page.locator('#evidencePane').isVisible(),true);
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
