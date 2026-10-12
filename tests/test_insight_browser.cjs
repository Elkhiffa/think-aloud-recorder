'use strict';
// Production insight assets in real Edge with a synthetic bridge; no real vault or agent output.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.join(__dirname,'..'),out=path.resolve(process.env.REVIEW_TEST_OUTPUT||path.join(root,'work','insight-browser'));
fs.mkdirSync(out,{recursive:true});
const S1='20261008-120000-aaaaaa',S2='20261009-120000-bbbbbb';
const row=(session,id,extra={})=>Object.assign({session_id:session,instance_id:id,said_start:12,refers_start:2,refers_end:4,refers_basis:'same_time',screen:'bag',catalog_screen:'bag',elements:[],kind:'confusion',statement:'合成陈述 '+id,issue_tags:[],issue_links:[],event_id:'e1',event_title:'合成活动'},extra);
const instances=[row(S1,'i1',{statement:'清完提示后忘了目标 <img src=x>'}),row(S2,'i1'),row(S2,'i2',{refers_basis:'earlier_session',refers_start:null,refers_end:null}),row(S1,'i3'),row(S2,'i9'),row(S2,'i5',{statement:'教学弹窗左半边多了一层灰色'})];
const link=(session,id,reason='合成理由')=>({session_id:session,instance_id:id,reason});
const overview={vault:'合成资料库',reports:[{name:'r.md',modified:1,bytes:10}],games:['合成游戏'],session_labels:{[S1]:'1008',[S2]:'1009'},instances,
  issues:[{id:'TA-01',title:'目标明确仍有摩擦',description:'合成议题',status:'confirmed',support:[link(S2,'i2')],counter:[],children:[
     {id:'TA-01.1',parent:'TA-01',title:'清完提示后忘了目标',description:'成立理由：合成',status:'candidate',support:[link(S1,'i1')],counter:[link(S2,'i1','专注时少提示反而好')],children:[]}]},
    {id:'BUG',title:'Bug',description:'',status:'confirmed',support:[link(S1,'i3')],counter:[],children:[
     {id:'BUG.1',parent:'BUG',title:'教学弹窗多出遮挡',description:'疑似缺陷',status:'candidate',support:[link(S2,'i5')],counter:[],children:[]}]}],
  bug_unorganized:[{session_id:S2,ref:'t000005',start:30,end:32,text:'现在有几个bug',instances:[],bug_instances:[],state:'raw'}],
  proposed:[{name:'兑换选择',family:'兑换选择',games:['合成游戏'],instances:[{session_id:S1,instance_id:'i3',refers_start:2,said_start:12,statement:'在兑换选择界面',route:['培养','兑换选择']}]}]};
const text=['# 总体判断','玩家清完提示后忘了目标 [1008 i1](i:'+S1+'/i1#TA-01.1)，见 [TA-01.1](issue:TA-01.1)。',
  '','- 不存在的引用 [1008 i8](i:'+S1+'/i8)','- 报告单独引用 [1009 i9](i:'+S2+'/i9)','','| 主题 | 议题 |','|---|---|','| 摩擦 | [TA-01](issue:TA-01) |'].join('\n');
const report={name:'r.md',text,citations:[
  {kind:'instance',session_id:S1,instance_id:'i1',issue:'TA-01.1',resolved:true},{kind:'issue',issue:'TA-01.1',resolved:true},
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
      list_screens:async()=>({ok:true,data:[{id:'bag',name:'背包',aliases:[]}]}),
      update_issue:async request=>{window.__calls.push(['update_issue',request]);const walk=node=>{if(node.id===request.id)Object.assign(node,request.status?{status:request.status}:{},request.title?{title:request.title}:{});node.children.forEach(walk);};window.__overview.issues.forEach(walk);return {ok:true,data:{}};},
      dismiss_issue:async id=>{window.__calls.push(['dismiss_issue',id]);for(const node of window.__overview.issues)node.children=node.children.filter(child=>child.id!==id);return {ok:true,data:{}};},
      merge_issue:async(from,into)=>{window.__calls.push(['merge_issue',from,into]);return {ok:true,data:{}};},
      confirm_proposed:async request=>{window.__calls.push(['confirm',request]);window.__overview.proposed=[];return {ok:true,data:{result:{screen:request.into},proposed:[]}};}}};
  },[overview,report]);
  const check=async(name,run)=>{await run();result.checks.push({name,pass:true});};
  await page.goto(origin);await page.waitForSelector('#issue-TA-01');
  await check('outline lists issues and sub-issues with counts; sub-issues start collapsed',async()=>{
    assert.match(await page.locator('#toc').textContent(),/TA-01\.1 清完提示后忘了目标支持 1 · 反例 1/);
    assert.equal(await page.locator('#issue-TA-01-body').isVisible(),true);
    assert.equal(await page.locator('#issue-TA-01\\.1-body').isHidden(),true);
    assert.match(await page.locator('#toc').textContent(),/BUG Bug/);
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
  await check('outline link reveals its section and the outline folds away',async()=>{
    await page.locator('#collapseAll').click();
    await page.locator('#toc a[data-target="TA-01.1"]').click();
    assert.equal(await page.locator('#issue-TA-01\\.1').isVisible(),true);
    await page.locator('#tocToggle').click();assert.equal(await page.locator('#toc').isHidden(),true);
    await page.locator('#tocToggle').click();
  });
  await check('evidence times open the review at that moment',async()=>{
    await page.locator('#expandAll').click();
    const card=page.locator('#issue-TA-01\\.1 .card[data-key="'+S1+'/i1"]');
    assert.equal(await card.locator('.card-title').textContent(),'困惑合成活动');
    assert.equal(await card.locator('.jump').textContent(),'00:02–00:12');
    await card.locator('.jump').click();
    await page.locator('#issue-BUG-raw-body .jump').click();
    const calls=await page.evaluate(()=>window.__calls);
    assert.deepEqual(calls.slice(-2),[['open_review',S1,2],['open_review',S2,30]]);
  });
  await page.screenshot({path:path.join(out,'insight-1440.png')});
  await check('proposed screen can be merged into an existing screen',async()=>{
    await page.locator('#tabProposed').click();
    assert.equal(await page.locator('#proposedCount').textContent(),'(1)');
    await page.locator('[data-proposal="into"]').click();
    await page.locator('#intoId').fill('bag');await page.locator('button[type="submit"]').click();
    await page.waitForFunction(()=>document.querySelector('#proposedCount').textContent==='');
    const calls=await page.evaluate(()=>window.__calls);
    assert.deepEqual(calls.at(-1),['confirm',{game:'合成游戏',proposed:'兑换选择',into:'bag'}]);
  });
  await check('candidate issue is confirmed while viewing its evidence',async()=>{
    await page.locator('#tabIssues').click();
    assert.equal(await page.locator('#issueCount').textContent(),'(2)');
    const bug=page.locator('#issueList .proposal[data-issue-id="BUG.1"]');
    await bug.locator('[data-issue-action="dismiss"]').click();
    assert.match(await bug.locator('[data-issue-action="dismiss"]').textContent(),/再点一次/);
    await bug.locator('[data-issue-action="dismiss"]').click();
    await page.waitForFunction(()=>document.querySelector('#issueCount').textContent==='(1)');
    assert.deepEqual((await page.evaluate(()=>window.__calls)).at(-1),['dismiss_issue','BUG.1']);
    const article=page.locator('#issueList .proposal[data-issue-id="TA-01.1"]');
    assert.equal(await article.locator('.shot').count(),2);
    assert.match(await article.textContent(),/属于 TA-01/);
    await article.locator('[data-issue-action="title"]').click();
    await page.locator('#issueTitle').fill('清完提示后忘了原本目标');await page.locator('#issueList button[type="submit"]').click();
    await page.waitForFunction(()=>document.querySelector('#issueList h3')?.textContent.includes('原本目标'));
    await page.locator('#issueList [data-issue-action="confirm"]').click();
    await page.waitForFunction(()=>document.querySelector('#issueCount').textContent==='');
    const calls=await page.evaluate(()=>window.__calls);
    assert.deepEqual(calls.slice(-2),[['update_issue',{id:'TA-01.1',title:'清完提示后忘了原本目标'}],['update_issue',{id:'TA-01.1',status:'confirmed'}]]);
    assert.equal(await page.locator('#toc a[data-target="TA-01.1"]').textContent().then(t=>t.includes('原本目标')),true);
  });
  await check('narrow window switches the outline to a select',async()=>{
    await page.locator('#tabEvidence').click();await page.setViewportSize({width:800,height:900});
    assert.equal(await page.locator('#toc').isHidden(),true);
    await page.locator('#tocSelect').selectOption('BUG');
    assert.equal(await page.locator('#issue-BUG').isVisible(),true);
    await page.screenshot({path:path.join(out,'insight-800.png')});
  });
  assert.deepEqual(result.errors,[]);
}
main().then(()=>{fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));},error=>{result.errors.push(String(error.stack||error));fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2));console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();server.close();});
