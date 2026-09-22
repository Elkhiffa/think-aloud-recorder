'use strict';
const assert=require('node:assert/strict');
const {formatTime,activeSegment,splitBounds,sourceFit}=require('../ui/review.js');
assert.equal(formatTime(90061),'25:01:01');
assert.equal(formatTime(-1),'00:00:00');
const segments=[{start:0,end:2},{start:4,end:6},{start:6,end:8}];
assert.equal(activeSegment(segments,0),0);
assert.equal(activeSegment(segments,2),-1);
assert.equal(activeSegment(segments,4),1);
assert.equal(activeSegment(segments,6),2);
assert.equal(activeSegment(segments,8),-1);
assert.equal(activeSegment([],0),-1);
assert.equal(activeSegment(segments,1),0); // Backward seeking restores earlier highlight.
// A saved preference clamps in a small window and restores when there is room.
assert.equal(splitBounds(800,240,220,.7).value,.7);
assert.equal(splitBounds(500,240,220,.7).value,.56);
assert.equal(splitBounds(800,240,220,.7).value,.7);
assert.equal(splitBounds(1000,240,220,-1).value,.24);
assert.equal(splitBounds(1000,240,220,2).value,.78);
assert.deepEqual(splitBounds(0,240,220,.7),{min:.5,max:.5,value:.5});
const cramped=splitBounds(300,180,180,.8);
assert.deepEqual(cramped,{min:.5,max:.5,value:.5});
const close=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-8,`${actual} != ${expected}`);
// Width budget already excludes layout padding and the divider. The measured
// chrome includes the toolbar, its wrapped rows, gaps and video-pane padding.
const source={available:1200,height:700,chromeHeight:52,videoWidth:1920,videoHeight:1080};
let fit=sourceFit(source);
close(fit.width,880);close(fit.slotWidth/fit.slotHeight,16/9); // Auto fit keeps 320 px of readable text.
close(fit.slotHeight,495); // Width-limited videos do not fill a tall black slot.
fit=sourceFit({...source,available:1800,chromeWidth:20});
close(fit.width,1172);close(fit.slotHeight,648);close(fit.slotWidth,1152);
fit=sourceFit({...source,videoWidth:2560,videoHeight:1080});
close(fit.width,880);close(fit.slotHeight,371.25);
fit=sourceFit({...source,videoWidth:1080,videoHeight:1920});
close(fit.width,364.5);close(fit.slotHeight,648);
fit=sourceFit({...source,videoWidth:1080,videoHeight:1920,chromeHeight:102});
close(fit.width,336.375);close(fit.slotHeight,598); // Wrapped toolbar measured afresh.
fit=sourceFit({...source,height:300,videoWidth:1080,videoHeight:1920});
close(fit.width,240);close(fit.slotWidth,139.5);close(fit.slotHeight,248);
fit=sourceFit({...source,available:300});
close(fit.width,300*240/560);close(fit.slotWidth/fit.slotHeight,16/9);
for(const invalid of [{videoWidth:0},{videoHeight:0},{videoWidth:NaN},{videoHeight:Infinity},{available:0},{height:0}]){
  assert.equal(sourceFit({...source,...invalid}),null);
}
console.log('Review timeline, divider and source-aspect tests passed.');
const input=require('../ui/review.js');
const items=input.normalizeInputs({state:'ready',intervals:[
  {id:'w',device:'keyboard',code:'W',kind:'button',start:1,end:8},
  {id:'a',device:'keyboard',code:'A',kind:'button',start:3,end:5},
  {id:'s',device:'keyboard',code:'S',kind:'button',start:5,end:6},
  {id:'q',device:'keyboard',code:'Q',kind:'button',start:4,end:4.07},
  {id:'ls',device:'xbox',code:'LeftStick',kind:'axis',value:.8,start:9,end:12},
  {id:'drift',device:'mouse',code:'MouseMove',kind:'motion',value:.01,start:10,end:11},
  {id:'ps',device:'dualsense',code:'Cross',kind:'button',start:13,end:14}
]}).intervals;
const packed=input.packInputIntervals(items),byId=new Map(packed.items.map(item=>[item.id,item]));
assert.equal(byId.get('w').lane,0);assert.equal(byId.get('a').lane,1);assert.equal(byId.get('s').lane,2); // The 4 px visual gap also reserves space.
assert.equal(byId.get('q').channel,'other');assert.equal(byId.get('ls').channel,'direction');assert.equal(byId.get('drift').channel,'pointing');
const idx=input.intervalIndex(packed.items);
assert.deepEqual(input.intervalsInRange(idx,4.03,4.03001).map(item=>item.id),['w','a','q']);
assert.deepEqual(input.intervalsInRange(idx,5,5.00001).map(item=>item.id),['w','s']);
assert.deepEqual(input.intervalsInRange(idx,4.1,4.10001).map(item=>item.id),['w','a']);
assert.equal(input.meaningfulDevice(items,10.5),'xbox');assert.equal(input.meaningfulDevice(items,13.5),'dualsense');assert.equal(input.meaningfulDevice(items,4),'keyboard');
assert.equal(input.normalizeInputs(null).state,'missing');assert.equal(input.normalizeInputs({state:'disabled'}).state,'disabled');
assert.equal(input.normalizeInputs({intervals:[{start:NaN,end:2},{start:2,end:1},{start:-1,end:3}]}).intervals.length,0);
const pulse=input.intervalIndex([{start:2,end:2}]);assert.equal(input.intervalsInRange(pulse,1,3).length,1);assert.equal(input.intervalsInRange(pulse,2,3).length,1);assert.equal(input.intervalsInRange(pulse,2.1,3).length,0);
assert.equal(input.axisDirection(0,-1),'↑');assert.equal(input.axisDirection(-1,1),'↙');
const zoom=input.anchoredZoom({scale:64,delta:-120,viewStart:100,pointerY:160,duration:1000,height:500});
close(100+160/64,zoom.viewStart+160/zoom.scale);assert.ok(zoom.scale>64);
// A three-hour history query only returns intervals overlapping its viewport.
const large=input.intervalIndex(Array.from({length:100000},(_,i)=>({start:i*.1,end:i*.1+.05})));
assert.ok(input.intervalsInRange(large,9000,9010).length<=101);
console.log('Input interval reconstruction, lane reuse, device switch and anchored zoom tests passed.');

// Dense samples model collector output: tiny value changes close/open the same
// axis at identical timestamps. Display grouping never mutates raw evidence.
const sample=(id,start,end,props={})=>({id,device:'xbox',code:'LeftStick',kind:'axis',value:.5,x:.5,y:0,direction:'→',start,end,...props});
const raw=Array.from({length:150},(_,i)=>sample('axis-'+i,+(1+i*.02).toFixed(6),+(1+(i+1)*.02).toFixed(6),{value:.5+(i%5)*.01,direction:i<75?'→':'↑'}));
const original=JSON.stringify(raw),band=input.inputVisualBands(raw);
assert.equal(band.length,1);assert.equal(band[0].id,'axis-0');assert.equal(band[0].samples.length,150);assert.equal(band[0].changes.length,2);assert.equal(JSON.stringify(raw),original);
assert.equal(input.inputSampleAt(band[0],2.72).id,'axis-86');assert.equal(input.inputSampleAt(band[0],4),null);
for(const boundary of [
  {gaps:[{start:2,end:2.01}]},
  {gaps:[{start:2,end:2,device:'xbox'}]},
  {resumed:true},
]){
 const values=[sample('a',1,2),sample('b',2,3,boundary.resumed?{resumed:true}:{})];
 assert.equal(input.inputVisualBands(values,boundary.gaps||[]).length,2);
}
assert.equal(input.inputVisualBands([sample('a',1,2),sample('b',2,3)],[{start:2,end:2.1,device:'dualsense'}]).length,1);
assert.equal(input.inputVisualBands([sample('a',1,2),sample('b',2.001,3)]).length,2);
assert.equal(input.inputVisualBands([sample('a',1,2),sample('zero',2,2.1,{value:0}),sample('b',2.1,3)]).length,3);
const taps=Array.from({length:20},(_,i)=>sample('tap-'+i,2+i*.06,2+i*.06+.02,{device:'keyboard',code:'ShiftLeft',kind:'button'}));
assert.equal(input.inputVisualBands(taps).length,taps.length);
for(const scale of [12,32,64,120,240]){
 const p=input.packInputIntervals(taps,{scale}),byLane=new Map();
 for(const item of p.items){assert.ok((item.displayEnd-item.start)*scale>=28-1e-8);const before=byLane.get(item.lane);if(before)assert.ok((item.start-before.displayEnd)*scale>=4-1e-8);byLane.set(item.lane,item);}
 for(let i=1;i<p.items.length;i++){
   const item=p.items[i],available=p.items.slice(0,i).filter(other=>other.displayEnd+4/scale>item.start+1e-9).map(other=>other.lane);
   assert.equal(item.lane,Array.from({length:21},(_,lane)=>lane).find(lane=>!available.includes(lane)));
 }
 assert.ok(p.widths.other.every(width=>width>=54));
 // A minimum-height display tail stays queryable, but never becomes held input.
 const tail=p.items[0];assert.equal(input.intervalsInRange(input.intervalIndex([tail],'displayEnd'),tail.end+.001,tail.displayEnd).length,1);
 assert.equal(input.intervalsInRange(input.intervalIndex([tail]),tail.end+.001,tail.displayEnd).length,0);
}
assert.equal(input.inputLabel({code:'DPadDown'}),'↓');assert.equal(input.inputLabel({code:'ShiftLeft'}),'Shift');
console.log('Continuous display groups, raw samples, boundary preservation and scale-aware readable lane tests passed.');
// A single full-session axis/trigger plus 100k short taps was pathological for
// the old prefix-max backwards scan. Assert traversal work, not machine timing.
const worst=input.intervalIndex([{id:'long',start:0,end:20000},...Array.from({length:100000},(_,i)=>({id:'short-'+i,start:1+i*.1,end:1+i*.1+.02}))]);
let reads=0;worst.maxEnds=new Proxy(worst.maxEnds,{get(target,key){if(/^\d+$/.test(String(key)))reads++;return target[key];}});
const nearEnd=input.intervalsInRange(worst,9990,9991);assert.equal(nearEnd.length,11);assert.equal(nearEnd[0].id,'long');assert.ok(reads<200,`Range query visited ${reads} tree nodes`);
// Validate against a direct filter, including long overlaps and point events.
for(const start of [0,.99,1,1.02,100,9990,10001,19999,20000]){
 const end=start+.25,expected=worst.items.filter(item=>item.start<end&&(item.end>start||(item.start===item.end&&item.start>=start)));
 assert.deepEqual(input.intervalsInRange(worst,start,end),expected);
}
console.log('Spanning activity band plus 100k taps: bounded range traversal passed.');
const frozen={viewStart:9,scale:64,top:120,duration:60};
assert.equal(input.timelinePointerTime(frozen,248),11);assert.equal(input.timelinePointerTime(frozen,-9999),0);assert.equal(input.timelinePointerTime(frozen,99999),60);
assert.equal(input.timelineGesture(1,4),'pending');assert.equal(input.timelineGesture(2,5),'vertical');assert.equal(input.timelineGesture(-8,2),'horizontal');assert.equal(input.timelineGesture(5,5),'horizontal');
assert.equal(input.timelinePointerTime({...frozen,scale:128},248),10);
console.log('Frozen pointer timeline coordinates, clamping and vertical gesture threshold passed.');
