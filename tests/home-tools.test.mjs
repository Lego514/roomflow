import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const window={};vm.runInNewContext(fs.readFileSync(new URL('../public/home-tools.js',import.meta.url),'utf8'),{window});
const {cleanResult,compare,summary}=window.RoomFlowHomeTools;
const result=(at=0,p95=25)=>({scope:'server-host',observedAt:new Date(Date.UTC(2026,9,27,5,0,at)).toISOString(),overall:'ok',layers:['gateway','internet','dns','service'].map(id=>({id,status:'ok',p95Ms:p95,attempts:3,failed:0})),wifi:{available:false,status:'unknown',signalPct:null},historySaved:true});
test('comparison reports real before/after differences and preserves failed probe counts',()=>{
  const a=result(),b=result(20,12);b.layers[1]={...b.layers[1],status:'attention',failed:1};b.overall='attention';
  const original=JSON.stringify(a),comp=compare(a,b);assert.equal(comp.valid,true);assert.equal(comp.rows[0].deltaMs,-13);assert.equal(comp.rows[1].afterFailed,1);assert.equal(JSON.stringify(a),original);
  b.layers[0]={id:'gateway',status:'unknown',p95Ms:null,attempts:0,failed:0};
  assert.equal(compare(a,b).rows[0].deltaMs,null,'missing data never becomes zero delay or an improvement');
});
test('comparison rejects different scope, duplicate layers, inconsistent success and unsuitable times',()=>{
  assert.equal(compare(result(),result()).valid,false);assert.equal(compare(result(20),result()).valid,false);
  const distant=result();distant.observedAt=new Date(Date.parse(distant.observedAt)+31*60000).toISOString();assert.equal(compare(result(),distant).reason,'expired');
  for(const bad of [{...result(),scope:'another-device'},{...result(),layers:[result().layers[0],...result().layers.slice(0,3)]},{...result(),overall:'unknown'}])assert.equal(cleanResult(bad),null);
  const impossible=result();impossible.layers[0].failed=3;assert.equal(cleanResult(impossible),null);
  const unknown=result();unknown.wifi={available:true,status:'ok',signalPct:null};assert.equal(cleanResult(unknown),null);
});
test('shareable summaries are bilingual, omit private extra fields and qualify observations',()=>{
  const a=result(),b={...result(20,12),ssid:'private-wifi',host:'private-host',error:'private-error'};b.layers[0].target='192.0.2.1';
  const comp=compare(a,b),zh=summary(b,{condition:'已暫停下載（使用者確認）',comparison:comp}),en=summary(b,{language:'en',comparison:comp});
  assert.match(zh,/使用者確認/);assert.match(zh,/比較基準時間/);assert.match(zh,/不能直接確定原因/);assert.match(en,/not been applied/);assert.match(en,/do not establish cause/);assert.doesNotMatch(zh+en,/private-|192\.0\.2\.1/);
});
