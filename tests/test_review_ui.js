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
