import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../public/index.html', import.meta.url), 'utf8');
const script = fs.readFileSync(new URL('../public/home.js', import.meta.url), 'utf8');
const toolsScript = fs.readFileSync(new URL('../public/home-tools.js', import.meta.url), 'utf8');
const extrasScript = fs.readFileSync(new URL('../public/home-extras.js', import.meta.url), 'utf8');

// Exercise the shipped browser script with DOM events and a controllable clock.
// No network, browser installation, application reimplementation, or real probes.
class Element {
  constructor(tag, document) { this.tagName=tag;this.document=document;this.children=[];this.attributes={};this.dataset={};this.listeners={};this.hidden=false;this.disabled=false;this.value='';this.replacements=0;this.open=false; }
  setAttribute(name,value) { this.attributes[name]=String(value);if(name==='id')this.id=String(value);if(name==='class')this.className=String(value);if(name==='hidden')this.hidden=true;if(name==='value')this.value=String(value);if(name.startsWith('data-'))this.dataset[name.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=String(value); }
  getAttribute(name) { return this.attributes[name]??null; }
  get classList() { const self=this;return {toggle(name,value){const names=new Set((self.className||'').split(/\s+/).filter(Boolean));if(value)names.add(name);else names.delete(name);self.className=[...names].join(' ');},contains(name){return (self.className||'').split(/\s+/).includes(name);}}; }
  append(...nodes) { for(const node of nodes){this.children.push(node);node.parent=this;} }
  replaceChildren(...nodes) { this.replacements++;this.children=[];this.append(...nodes); }
  set textContent(value) { this.children=[{textContent:String(value)}]; }
  get textContent() { return this.children.map(node=>node.textContent??'').join(''); }
  addEventListener(type,fn) { (this.listeners[type]??=[]).push(fn); }
  dispatch(type,event={}) { const promises=(this.listeners[type]??[]).map(fn=>fn({target:this,preventDefault(){},...event}));return Promise.all(promises); }
  click() { return this.disabled?Promise.resolve():this.dispatch('click'); }
  focus() { this.document.activeElement=this; }
  select() { this.selected=true; }
  querySelectorAll(selector) { const found=[];function visit(parent){for(const child of parent.children??[]){if(child instanceof Element){if(matches(child,selector))found.push(child);visit(child);}}}visit(this);return found; }
  querySelector(selector) { return this.querySelectorAll(selector)[0]??null; }
}
function matches(node,selector) { if(selector.startsWith('.'))return (node.className||'').split(/\s+/).includes(selector.slice(1));if(selector.startsWith('['))return node.attributes[selector.slice(1,-1)]!==undefined;return node.tagName===selector; }
function makeDocument() {
  const document={title:'',activeElement:null};const root=new Element('root',document);const stack=[root];const expression=/<\/?([a-zA-Z][\w:-]*)([^>]*?)>/g;let match;let previous=0;
  const voids=new Set(['meta','link','br','input','img','hr','path','circle','rect']);
  while((match=expression.exec(html))){const text=html.slice(previous,match.index);if(text)stack.at(-1).append({textContent:text});previous=expression.lastIndex;const tag=match[1].toLowerCase();if(match[0][1]==='/'){const index=stack.findLastIndex(node=>node.tagName===tag);if(index>0)stack.splice(index);continue;}const node=new Element(tag,document);for(const attribute of match[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g))node.setAttribute(attribute[1],attribute[2]??'');stack.at(-1).append(node);if(!voids.has(tag)&&!match[0].endsWith('/>'))stack.push(node);}
  document.querySelectorAll=selector=>root.querySelectorAll(selector);document.querySelector=selector=>root.querySelector(selector);document.getElementById=id=>root.querySelectorAll('[id]').find(node=>node.id===id)??null;document.createElement=tag=>new Element(tag,document);document.createTextNode=text=>({textContent:text});document.documentElement=document.querySelector('html');return document;
}
const response = (value,status=200) => ({ok:status>=200&&status<300,status,json:async()=>value});
const flush = async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
function result(at,changes={}) { return {scope:'server-host',observedAt:new Date(at).toISOString(),overall:'ok',layers:['gateway','internet','dns','service'].map(id=>({id,status:'ok',p95Ms:8,attempts:3,failed:0})),wifi:{available:false,status:'unknown',signalPct:null},historySaved:true,...changes}; }
function completed(at,value=result(at)) { return {id:'finished',status:'complete',startedAt:new Date(at-1000).toISOString(),completedAt:new Date(at).toISOString(),result:value}; }
function harness({fetcher,initialStorage={},withExtras=false,clipboard=null}={}) {
  let clock=Date.parse('2026-10-27T05:00:00Z');const document=makeDocument();const storage=new Map(Object.entries(initialStorage));const intervals=[];const timers=new Map();let timerId=0;const calls=[];
  class ClockDate extends Date { constructor(...args){super(...(args.length?args:[clock]));}static now(){return clock;} }
  const fetch=async(url,options={})=>{calls.push({url,method:options.method??'GET'});return fetcher?fetcher(url,options,clock):response({job:null});};
  const context={document,localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,String(value))},Date:ClockDate,Intl,AbortController,navigator:{clipboard},fetch,setInterval:fn=>{intervals.push(fn);return intervals.length;},setTimeout:fn=>{const id=++timerId;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id),window:{addEventListener(){}},console};
  if(withExtras){vm.runInNewContext(toolsScript,context);vm.runInNewContext(extrasScript,context);}
  vm.runInNewContext(script,context,{filename:'public/home.js'});
  return {document,storage,calls,get now(){return clock;},get:id=>document.getElementById(id),async advance(ms){clock+=ms;for(const fn of intervals)fn();await flush();},async poll(){const pending=[...timers.entries()];for(const[id,fn]of pending){timers.delete(id);await fn();}await flush();}};
}

test('mode preference expires automatically and never calls router/model APIs',async()=>{
  const app=harness();await flush();await app.get('mode-priority').click();assert.equal(app.get('mode-priority').getAttribute('aria-checked'),'true');assert.match(app.get('mode-feedback').textContent,/尚未變更/);assert.match(app.get('mode-countdown').textContent,/60:00/);
  await app.advance(60*60000+1);assert.equal(app.get('mode-normal').getAttribute('aria-checked'),'true');assert.equal(app.get('mode-countdown').hidden,true);assert.match(app.get('mode-feedback').textContent,/時間已到/);assert.equal(JSON.parse(app.storage.get('roomflow.home.preference')).mode,'normal');assert.deepEqual(app.calls.map(call=>call.method),['GET']);
});

const setupFixture=()=>({scope:'server-host',details:{deviceAlias:'我的筆電',routerBrand:'',routerModel:'',managementAccess:'unknown'},preparation:{deviceNamed:true,routerDetailsProvided:false},capability:{routerConnected:false,deviceBound:false,controlAvailable:false}});
test('guided comparison pairs the requested new job, stores both observations, and survives reload',async()=>{
  const initial=Date.parse('2026-10-27T05:00:00Z');let phase='before';
  const app=harness({withExtras:true,fetcher:(url,options,at)=>{
    if(url==='/api/home-setup')return response(setupFixture());
    if(options.method==='POST'){phase='running';return response({job:{id:'comparison-new',status:'running',startedAt:new Date(at).toISOString()}});}
    if(url.includes('/api/quick-check/')){phase='after';return response({job:{...completed(at,result(at,{layers:result(at).layers.map(row=>({...row,p95Ms:3}))})),id:'comparison-new'}});}
    return response({job:completed(initial)});
  }});
  await flush();assert.equal(app.get('device-name').textContent,'我的筆電');assert.match(app.get('device-verification').textContent,/尚未綁定/);
  await app.advance(1000);await app.get('compare-paused').click();await flush();assert.equal(phase,'running');assert.equal(app.get('compare-ethernet').disabled,true);
  app.get('home-language').value='en';await app.get('home-language').dispatch('change');assert.equal(app.get('check-progress').hidden,false);
  await app.advance(1000);await app.poll();assert.equal(phase,'after');assert.equal(app.get('comparison-section').hidden,false);assert.match(app.get('comparison-condition').textContent,/user reported/);assert.match(app.get('comparison-rows').textContent,/8.0 → 3.0/);
  const stored=JSON.parse(app.storage.get('roomflow.home.comparisons.v1'));assert.equal(stored.length,1);assert.equal(stored[0].condition,'paused');assert.equal(stored[0].before.layers[0].p95Ms,8);assert.equal(stored[0].after.layers[0].p95Ms,3);
  const reloaded=harness({withExtras:true,initialStorage:Object.fromEntries(app.storage),fetcher:url=>url==='/api/home-setup'?response(setupFixture()):response({job:null})});await flush();assert.equal(reloaded.get('comparison-section').hidden,false);assert.match(reloaded.get('comparison-rows').textContent,/8.0 → 3.0/);assert.equal(reloaded.calls.filter(call=>call.method==='POST').length,0);
});
test('stale baselines, failed checks, and another browser running a check never create false comparisons',async()=>{
  const app=harness({withExtras:true,fetcher:(url,options,at)=>url==='/api/home-setup'?response(setupFixture()):options.method==='POST'?response({job:{id:'older-running',status:'running',startedAt:new Date(at-10000).toISOString()}},409):response({job:completed(at)})});
  await flush();await app.get('compare-ethernet').click();await flush();assert.match(app.get('action-feedback').textContent,/另一個檢查/);assert.equal(app.get('comparison-section').hidden,true);assert.equal(app.storage.get('roomflow.home.pending-comparison.v1'),'null');
  const stale=harness({withExtras:true,fetcher:(url,options,at)=>url==='/api/home-setup'?response(setupFixture()):response({job:completed(at-16*60000)})});await flush();await stale.get('compare-paused').click();assert.equal(stale.calls.filter(call=>call.method==='POST').length,0);assert.match(stale.get('action-feedback').textContent,/15 分鐘/);
  const failure=harness({withExtras:true,fetcher:(url,options,at)=>url==='/api/home-setup'?response(setupFixture()):response({job:options.method==='POST'?{id:'failed-new',status:'failed',errorCode:'timeout'}:completed(at)})});await flush();await failure.get('compare-closer').click();await flush();assert.equal(failure.get('comparison-section').hidden,true);assert.equal(failure.storage.get('roomflow.home.pending-comparison.v1'),'null');
});
test('setup saves a local device label, stays unbound, and manual copy fallback exposes only a filtered summary',async()=>{
  let saved=null;const app=harness({withExtras:true,fetcher:(url,options,at)=>{if(url==='/api/home-setup'){if(options.method==='POST')saved=JSON.parse(options.body);return response({...setupFixture(),details:saved??setupFixture().details});}return response({job:completed(at)});}});
  await flush();await app.get('open-setup').click();assert.equal(app.get('setup-panel').open,true);app.get('device-alias').value='遊戲筆電';await app.get('setup-form').dispatch('submit');assert.equal(saved.deviceAlias,'遊戲筆電');assert.equal(app.get('device-name').textContent,'遊戲筆電');assert.match(app.get('setup-feedback').textContent,/尚未套用/);assert.match(app.get('device-verification').textContent,/尚未綁定/);
  await app.get('copy-check').click();assert.equal(app.get('manual-copy').hidden,false);assert.match(app.get('copy-text').value,/RoomFlow 連線觀察摘要/);assert.match(app.get('copy-text').value,/未套用/);assert.equal(app.get('copy-text').selected,true);
  const posts=app.calls.filter(call=>call.method==='POST');assert.equal(posts.length,1);assert.equal(posts[0].url,'/api/home-setup');
});

test('early end and language changes preserve the selected preference and expiry',async()=>{
  const app=harness();await flush();await app.get('mode-background').click();app.get('mode-duration').value='30';await app.get('mode-duration').dispatch('change');const before=JSON.parse(app.storage.get('roomflow.home.preference'));
  app.get('home-language').value='en';await app.get('home-language').dispatch('change');assert.equal(app.get('selected-mode').textContent,'I can make room');assert.equal(app.document.documentElement.lang,'en');assert.equal(JSON.parse(app.storage.get('roomflow.home.preference')).expiresAt,before.expiresAt);
  assert.equal(app.storage.get('roomflow-language'),'en','history and lab use the same selected language');
  await app.get('mode-end').click();assert.equal(app.get('selected-mode').textContent,'Everyday use');assert.match(app.get('mode-feedback').textContent,/never changed/);assert.equal(app.calls.filter(call=>call.method==='POST').length,0);
});

test('a late initial GET cannot overwrite a new running POST job',async()=>{
  let initialResolve;const app=harness({fetcher:(url,options,at)=>options.method==='POST'?response({job:{id:'new',status:'running',startedAt:new Date(at).toISOString(),result:null}}):new Promise(resolve=>{initialResolve=()=>resolve(response({job:completed(at)}));})});
  await app.get('quick-check-start').click();assert.equal(app.get('check-progress').hidden,false);initialResolve();await flush();assert.equal(app.get('check-progress').hidden,false);assert.equal(app.get('check-result').hidden,true);assert.equal(app.get('quick-check-start').disabled,true);assert.deepEqual(app.calls.map(call=>call.method),['GET','POST']);
});

test('missing required measurements cannot be shown as a healthy result',async()=>{
  const app=harness({fetcher:(url,options,at)=>response({job:completed(at,result(at,{layers:[{id:'gateway',status:'ok',p95Ms:2,attempts:3,failed:0}]}))})});await flush();assert.equal(app.get('check-result').dataset.state,'unknown');assert.match(app.get('result-title').textContent,/資料不足/);const children=app.get('layer-results').children;assert.equal(children[1].dataset.state,'unknown');assert.equal(app.calls.length,1);
});

test('Wi-Fi information explains attention and unknown results; unavailable does not imply disconnection',async()=>{
  for(const status of ['attention','unknown']){
    const app=harness({fetcher:(url,options,at)=>response({job:completed(at,result(at,{wifi:{available:true,status,signalPct:status==='attention'?28:null}}))})});await flush();assert.equal(app.get('check-result').dataset.state,status);const wifi=app.get('layer-results').children.at(-1);assert.match(wifi.textContent,/Wi-Fi/);assert.match(wifi.textContent,/訊號強度/);if(status==='attention'){assert.match(app.get('result-title').textContent,/Wi-Fi/);assert.match(wifi.textContent,/28%/);}else assert.match(wifi.textContent,/未取得/);
  }
  const app=harness({fetcher:(url,options,at)=>response({job:completed(at)})});await flush();assert.equal(app.get('check-result').dataset.state,'ok');assert.match(app.get('layer-results').children.at(-1).textContent,/可能使用有線連線/);assert.match(app.get('layer-results').children.at(-1).textContent,/不代表斷線/);
  app.get('home-language').value='en';await app.get('home-language').dispatch('change');assert.match(app.get('layer-results').children.at(-1).textContent,/may be using Ethernet/);assert.match(app.get('layer-results').children.at(-1).textContent,/does not mean it is disconnected/);
});

test('fresh results turn stale in place without rebuilding details or issuing new probes',async()=>{
  const app=harness({fetcher:(url,options,at)=>response({job:completed(at)})});await flush();const layers=app.get('layer-results');const originalCards=[...layers.children];const replacements=layers.replacements;app.get('check-details').open=true;app.get('check-details').focus();assert.equal(app.get('check-result').dataset.state,'ok');
  await app.advance(15*60000+1);assert.equal(app.get('check-result').dataset.state,'unknown');assert.match(app.get('result-eyebrow').textContent,/先前/);assert.match(app.get('result-explanation').textContent,/不能代表現在/);assert.equal(layers.replacements,replacements);assert.deepEqual(layers.children,originalCards);assert.equal(app.get('check-details').open,true);assert.equal(app.document.activeElement,app.get('check-details'));assert.deepEqual(app.calls.map(call=>call.method),['GET']);
  await app.advance(1000);assert.equal(layers.replacements,replacements);
});
