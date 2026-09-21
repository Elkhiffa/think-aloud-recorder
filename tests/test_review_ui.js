'use strict';
const assert=require('node:assert/strict');
const {formatTime,activeSegment,splitBounds}=require('../ui/review.js');
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
console.log('Review timeline tests passed.');
