import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../public/monitor.js',import.meta.url),'utf8');

// Exercise the actual renderer without a browser dependency. The fixture keeps
// generated SVG attributes so gap semantics can be checked, not just source text.
function mount(payload, options = {}) {
  const flatten = node => [node,...node.children.flatMap(flatten)];
  const matches = (node, selector) => {
    const attribute = /\[([^=\]]+)="([^"]*)"\]/.exec(selector);
    const simple = selector.replace(/\[[^\]]+\]/g,'');
    return (simple.startsWith('#') ? node.id === simple.slice(1) : simple.startsWith('.') ? node.className.split(' ').includes(simple.slice(1)) : node.tagName === simple) && (!attribute || node.getAttribute(attribute[1]) === attribute[2]);
  };
  class Element {
    constructor(tag) { this.tagName=tag; this.children=[]; this.attributes={}; this.dataset={}; this.className=''; this.listeners={}; this.classList={contains:()=>true}; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children=[...nodes]; }
    setAttribute(key,value) { this.attributes[key]=String(value); if(key==='class') this.className=String(value); }
    getAttribute(key) { return this.attributes[key] ?? null; }
    addEventListener(name,callback) { (this.listeners[name] ||= []).push(callback); }
    dispatchEvent(event) { for (const callback of this.listeners[event.type] || []) callback(event); }
    click() { if (!this.disabled) this.dispatchEvent({type:'click'}); }
    querySelectorAll(selector) { return flatten(this).slice(1).filter(node=>matches(node,selector)); }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    focus() { document.activeElement=this; }
  }
  const root=new Element('section');
  const document={
    documentElement:{lang:'en'}, body:new Element('body'), activeElement:null,
    getElementById:id=>id==='observations'?root:flatten(root).find(node=>node.id===id) || null, querySelector:()=>null,
    createElement:tag=>new Element(tag), createElementNS:(_,tag)=>new Element(tag),
    createTextNode:text=>Object.assign(new Element('#text'),{textContent:text}),
    listeners:{}, addEventListener(name,callback) { (this.listeners[name] ||= []).push(callback); },
    dispatchEvent(event) { for (const callback of this.listeners[event.type] || []) callback(event); },
  };
  const timers = new Map(); let timerId=0;
  vm.runInNewContext(source,{window:{ROOMFLOW_OFFLINE_DATA:payload,ROOMFLOW_OFFLINE_SOURCES:options.sources,scrollTo:()=>{},scrollY:0},document,localStorage:{getItem:()=>null},Intl,
    setTimeout:callback=>{const id=++timerId;timers.set(id,callback);return id;},clearTimeout:id=>timers.delete(id)});
  return {root,document,elements:()=>flatten(root),byId:id=>document.getElementById(id),
    find:selector=>root.querySelector(selector),text:()=>flatten(root).map(node=>node.textContent || '').join(' '),
    tick:()=>{ const pending=[...timers.values()];timers.clear();for(const callback of pending)callback(); },timerCount:()=>timers.size,
    language:value=>document.dispatchEvent({type:'roomflow:languagechange',detail:{language:value}})};
}
const render=payload=>mount(payload).elements();

const at=seconds=>new Date(Date.UTC(2026,0,1,0,0,seconds)).toISOString();
function sample(seconds,status='degraded',gatewayStatus=status,p95=20) {
  return {at:at(seconds),status,layers:{
    gateway:{status:gatewayStatus,p95Ms:p95,p50Ms:10,attempts:5,failed:0},
    internet:{status:'degraded',p95Ms:200,p50Ms:100,attempts:5,failed:0},
  }};
}
function snapshot(timeline,gaps=[]) {
  return {schemaVersion:1,source:{kind:'historical-demo'},monitor:{status:'historical'},policy:{maxGapSeconds:900},
    latest:timeline.at(-1),timeline,incidents:[{id:'case',status:'resolved',startedAt:timeline[0].at,resolvedAt:timeline.at(-1).at,evidenceGaps:gaps}]};
}
const classIs=(element,value)=>element.className.split(' ').includes(value);

test('a point incomplete-check marker cuts both adjacent incident shading intervals',()=>{
  const timeline=[sample(0),sample(10),sample(20,'unknown','unknown',99999),sample(30),sample(40)];
  const elements=render(snapshot(timeline,[{from:at(20),to:at(20),reason:'incomplete-check'}]));
  const regions=elements.filter(element=>classIs(element,'rf-incident-region'));
  assert.equal(regions.length,2);
  // Plot spans x=44..882 over 40s. Only 0..10s and 30..40s are observed.
  const intervals=regions.map(region=>[Number(region.attributes.x),Number(region.attributes.x)+Number(region.attributes.width)]);
  assert.deepEqual(intervals,[[44,253.5],[672.5,882]]);
  const gatewayPath=elements.find(element=>classIs(element,'rf-gateway-line')).attributes.d;
  assert.equal((gatewayPath.match(/M/g)||[]).length,2,'unknown layer must start a new segment');
  assert.equal((gatewayPath.match(/L/g)||[]).length,2,'neither side connects to the unknown numeric sample');
  assert.equal(elements.filter(element=>element.tagName==='circle').length,9,'exclude the stale unknown p95 point, retain known internet data');
  const scaleButton=elements.find(element=>classIs(element,'rf-scale-button'));
  assert.equal(scaleButton.attributes['aria-pressed'],'false','unknown outlier must not force a logarithmic scale');
});

test('collection gaps stay unshaded and line segments break without explicit gap metadata',()=>{
  const timeline=[sample(0),sample(10),sample(2000),sample(2010)];
  const elements=render(snapshot(timeline));
  const regions=elements.filter(element=>classIs(element,'rf-incident-region'));
  assert.equal(regions.length,2);
  const shadedWidth=regions.reduce((total,region)=>total+Number(region.attributes.width),0);
  assert.ok(Math.abs(shadedWidth-(882-44)*20/2010)<1e-9);
  for(const key of ['gateway','internet']) {
    const path=elements.find(element=>classIs(element,`rf-${key}-line`)).attributes.d;
    assert.equal((path.match(/M/g)||[]).length,2);
  }
});

function incidentEvidence(start = 10, end = 40) {
  const layers = Object.fromEntries(['gateway','internet','dns','service'].map(name=>[name,{
    peakP95Ms:name==='internet'?350:12,peakP95At:at(start),latencyThresholdMs:name==='gateway'?30:120,failureThresholdPct:5,
    attempts:20,failed:0,failurePct:0,countsComplete:true,countedChecks:4,missingCountChecks:0,
    abnormalChecks:name==='internet'?4:0,healthyChecks:name==='internet'?0:4,unknownChecks:0,latencyBreaches:name==='internet'?4:0,failureBreaches:0,
  }]));
  return {startAt:at(start),endAt:at(end),checkCount:4,layers};
}
const deepFreeze=value=>{ if(value && typeof value==='object') {Object.freeze(value);Object.values(value).forEach(deepFreeze);}return value; };

test('incident click focuses the actual chart with context, and Full history resets it without mutating data',()=>{
  const timeline=Array.from({length:21},(_,index)=>sample(index*10));
  const data=snapshot(timeline);
  Object.assign(data.incidents[0],{startedAt:at(80),openedAt:at(100),resolvedAt:at(100),lastObservedAt:at(100),evidence:incidentEvidence(80,100)});
  const initial=JSON.stringify(data), ui=mount(deepFreeze(data));
  assert.equal(ui.byId('rf-chart-window').dataset.start,String(Date.parse(at(0))));
  assert.equal(ui.byId('rf-chart-window').dataset.end,String(Date.parse(at(200))));
  assert.equal(ui.elements().filter(node=>node.tagName==='circle').length,42,'default retains whole history despite default detail selection');
  ui.find('.rf-incident-button').click();
  assert.equal(ui.byId('rf-chart-window').dataset.start,String(Date.parse(at(60))));
  assert.equal(ui.byId('rf-chart-window').dataset.end,String(Date.parse(at(120))));
  assert.equal(ui.elements().filter(node=>node.tagName==='circle').length,14,'the drawn chart changes, not only its description');
  assert.match(ui.text(),/Incident context window/);
  assert.equal(ui.byId('rf-full-history').textContent,'Full history');
  ui.byId('rf-full-history').click();
  assert.equal(ui.elements().filter(node=>node.tagName==='circle').length,42);
  assert.equal(ui.byId('rf-full-history'),null);
  assert.equal(JSON.stringify(data),initial);
});

test('focused context discloses clipped or unavailable history, and preserves unknown evidence gaps',()=>{
  const data=snapshot([sample(20),sample(30),sample(40,'unknown','unknown'),sample(50),sample(60)]);
  Object.assign(data.incidents[0],{startedAt:at(20),resolvedAt:at(60)});
  const ui=mount(data); ui.find('.rf-incident-button').click();
  assert.match(ui.text(),/Context extends beyond the saved timeline/);
  assert.equal(ui.elements().filter(node=>classIs(node,'rf-incident-region')).length,2);
  const older=snapshot([sample(200),sample(210)]);
  Object.assign(older.incidents[0],{startedAt:at(0),resolvedAt:at(10)});
  older.timelineTruncated=true;older.timelineTotal=100;
  const unavailable=mount(older);unavailable.find('.rf-incident-button').click();
  assert.match(unavailable.text(),/no samples in the saved chart timeline/);
  assert.equal(unavailable.elements().filter(node=>node.tagName==='circle').length,0);
  assert.ok(Number(unavailable.byId('rf-chart-window').dataset.end)>Number(unavailable.byId('rf-chart-window').dataset.start));
});

test('incident table includes healthy gateway, measured bounds, partial counts and explicit unavailable evidence',()=>{
  const data=snapshot([sample(10),sample(20),sample(30),sample(40)]);
  data.incidents[0].evidence=incidentEvidence();
  Object.assign(data.incidents[0].evidence.layers.dns,{peakP95Ms:null,peakP95At:null,attempts:10,failed:6,failurePct:60,countsComplete:false,countedChecks:2,missingCountChecks:2,abnormalChecks:2,healthyChecks:0,unknownChecks:2});
  Object.assign(data.incidents[0].evidence.layers.service,{peakP95Ms:null,peakP95At:null,attempts:null,failed:null,failurePct:null,countsComplete:false,countedChecks:0,missingCountChecks:4});
  const ui=mount(data);
  assert.equal(ui.elements().filter(node=>node.tagName==='tr' && node.dataset.layer).length,4);
  const gateway=ui.elements().find(node=>node.dataset.layer==='gateway');
  assert.match(gateway.children[3].children[0].textContent,/Healthy 4 · abnormal 0 · unknown 0/);
  assert.match(ui.text(),/350 ms/);
  assert.match(ui.text(),/Threshold > 120 ms/);
  assert.match(ui.text(),/6 \/ 10 \(60%\)/);
  assert.match(ui.text(),/Partial counts: 2\/4 samples counted; 2 missing/);
  assert.match(ui.text(),/Recovery confirmation is excluded/);
  assert.match(ui.text(),/not a pooled percentile/);
  assert.match(ui.text(),/— ms/);
  ui.language('zh-Hant');
  assert.match(ui.text(),/部分次數：2\/4 筆有次數；2 筆缺少/);
  assert.match(ui.text(),/正常 4 · 異常 0 · 未知 0/);
  delete data.incidents[0].evidence;
  const legacy=mount(data);
  assert.match(legacy.text(),/older incident has no numerical evidence/);
  assert.equal(legacy.elements().filter(node=>classIs(node,'rf-evidence-table')).length,0);
});

function drillFixture() {
  const timeline=Array.from({length:7},(_,index)=>sample(index*10,index===0 || index>=5?'ok':'degraded','ok',index===6?91234:12));
  const final={id:'drill-case',status:'resolved',startedAt:at(10),openedAt:at(30),lastObservedAt:at(60),lastAbnormalAt:at(40),resolvedAt:at(60),durationSeconds:50,affectedLayers:['internet'],evidence:incidentEvidence(),observations:['FUTURE FINAL DETAILS'],transitions:[{type:'opened',at:at(30)},{type:'resolved',at:at(60)}]};
  const frames=timeline.map((row,index)=>{
    const current={...final,status:'open',resolvedAt:null,lastObservedAt:row.at,lastAbnormalAt:at(Math.min(index*10,40)),evidence:incidentEvidence(10,Math.min(index*10,40)),observations:['Evidence available at this step'],transitions:final.transitions.slice(0,1)};
    const incidents=index<3?[]:[index===6?final:current];
    return {sampleCount:index+1,at:row.at,stage:['normal','pending','pending','open','open','recovering','resolved'][index],incidents,notifications:incidents.flatMap(item=>item.transitions),pendingAbnormalChecks:index===1 || index===2?index:0,pendingRecoveryChecks:index===5?1:0};
  });
  return {schemaVersion:1,source:{kind:'lab-drill',windowStart:at(0),windowEnd:at(60)},policy:{openAfter:3,recoverAfter:2,maxGapSeconds:900},monitor:{status:'historical'},latest:timeline.at(-1),timeline,incidents:[final],notifications:final.transitions,replay:{available:true,totalSamples:7,frames}};
}

test('saved drill playback shows authoritative pending/open/recovering/resolved state without future leaks',()=>{
  const data=drillFixture(),initial=JSON.stringify(data),ui=mount(deepFreeze(data));
  const state=()=>ui.find('.rf-replay-state');
  assert.equal(state().dataset.stage,'normal');
  assert.equal(state().dataset.sampleCount,'1');
  assert.equal(ui.find('.rf-incident-button'),null);
  assert.doesNotMatch(ui.text(),/91,234|FUTURE FINAL DETAILS/);
  assert.equal(ui.elements().filter(node=>node.tagName==='circle').length,2);
  ui.byId('rf-replay-next').click();
  assert.equal(state().dataset.stage,'pending');
  assert.match(ui.text(),/Abnormal streak 1 \/ 3/);
  assert.equal(ui.find('.rf-incident-button'),null);
  assert.equal(ui.elements().filter(node=>classIs(node,'rf-incident-region')).length,0);
  ui.byId('rf-replay-next').click();ui.byId('rf-replay-next').click();
  assert.equal(state().dataset.stage,'open');
  assert.equal(ui.find('.rf-incident-button').dataset.incidentId,'drill-case');
  assert.equal(ui.find('.rf-state').dataset.status,'open');
  ui.find('.rf-incident-button').click();
  assert.ok(Number(ui.byId('rf-chart-window').dataset.end)<=Date.parse(at(30)),'focus cannot include future evidence');
  assert.doesNotMatch(ui.text(),/FUTURE FINAL DETAILS|91,234/);
  ui.byId('rf-replay-next').click();ui.byId('rf-replay-next').click();
  assert.equal(state().dataset.stage,'recovering');
  assert.equal(ui.find('.rf-state').dataset.status,'open','first recovery sample must remain open');
  assert.match(ui.text(),/recovery streak 1 \/ 2/);
  ui.byId('rf-replay-next').click();
  assert.equal(state().dataset.stage,'resolved');
  assert.equal(ui.find('.rf-state').dataset.status,'resolved');
  assert.match(ui.text(),/FUTURE FINAL DETAILS|91,234/);
  assert.equal(ui.byId('rf-replay-next').disabled,true);
  ui.byId('rf-replay-previous').click();
  assert.equal(state().dataset.stage,'recovering');
  assert.doesNotMatch(ui.text(),/FUTURE FINAL DETAILS|91,234/);
  ui.byId('rf-replay-restart').click();
  assert.equal(state().dataset.sampleCount,'1');
  assert.equal(ui.find('.rf-incident-button'),null);
  assert.match(ui.text(),/Saved replay; no new probes/);
  assert.equal(JSON.stringify(data),initial);
});

test('autoplay survives language changes with one timer, pauses, finishes and resets on source/scenario changes',()=>{
  const drill=deepFreeze(drillFixture()), demo=snapshot([sample(0),sample(10)]);
  const ui=mount(demo,{sources:{demo,'drill-delay':drill,'drill-dns':drill}});
  const selectSource=value=>{const field=ui.byId('rf-source');field.value=value;field.dispatchEvent({type:'change'});};
  selectSource('drill');
  ui.byId('rf-replay-play').focus();ui.byId('rf-replay-play').click();assert.equal(ui.timerCount(),1);
  assert.equal(ui.document.activeElement.id,'rf-replay-pause','re-render retains keyboard focus on the playback control');
  ui.tick();assert.equal(ui.find('.rf-replay-state').dataset.sampleCount,'2');
  ui.language('zh-Hant');
  assert.equal(ui.find('.rf-replay-state').dataset.sampleCount,'2');
  assert.equal(ui.byId('rf-replay-pause').textContent,'暫停');
  assert.equal(ui.timerCount(),1);
  ui.byId('rf-replay-pause').click();assert.equal(ui.timerCount(),0);
  assert.equal(ui.document.activeElement.id,'rf-replay-play');
  ui.byId('rf-replay-play').click();ui.byId('rf-replay-next').click();
  assert.equal(ui.timerCount(),0,'manual next pauses playback');
  assert.equal(ui.find('.rf-replay-state').dataset.sampleCount,'3');
  ui.byId('rf-replay-play').click();
  for(let index=0;index<4;index++)ui.tick();
  assert.equal(ui.find('.rf-replay-state').dataset.stage,'resolved');assert.equal(ui.timerCount(),0);
  assert.ok(ui.byId('rf-replay-play'));
  ui.find('.rf-incident-button').click();ui.language('en');
  assert.equal(ui.find('.rf-replay-state').dataset.sampleCount,'7');
  assert.ok(ui.byId('rf-full-history'),'language changes retain event focus');
  ui.byId('rf-replay-play').click();assert.equal(ui.find('.rf-replay-state').dataset.sampleCount,'1');
  const scenario=ui.byId('rf-scenario');scenario.value='dns';scenario.dispatchEvent({type:'change'});
  assert.equal(ui.timerCount(),0);assert.equal(ui.find('.rf-replay-state').dataset.sampleCount,'1');
  ui.byId('rf-replay-play').click();selectSource('demo');
  assert.equal(ui.timerCount(),0);assert.equal(ui.find('.rf-replay-state'),null);
  assert.equal(ui.byId('rf-full-history'),null);
});

test('older or capped lab snapshots disclose unavailable playback and retain their saved final view',()=>{
  const data=drillFixture();data.replay={available:false,frames:[],totalSamples:201,reason:'sample-limit'};
  const ui=mount(data);
  assert.match(ui.text(),/No step-by-step state is available/);
  assert.equal(ui.byId('rf-replay-play'),null);
  assert.equal(ui.find('.rf-state').dataset.status,'resolved');
});
