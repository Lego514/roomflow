import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {HomeSetupStore,validateSetup} from '../src/home-setup.mjs';
import {createApp} from '../src/server.mjs';
const details=()=>({deviceAlias:'我的筆電',routerBrand:'',routerModel:'',managementAccess:'unknown'});
test('setup persists a friendly name without claiming router connection, binding, or applied policy',t=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'roomflow-setup-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const store=new HomeSetupStore({dataDir:dir,now:()=>0});
  assert.equal(store.read().preparation.deviceNamed,false);
  assert.equal(fs.existsSync(store.file),false,'reading preparation does not create a fake verified state');
  const saved=store.save({...details(),routerBrand:'Example',routerModel:'Model',managementAccess:'available'});
  assert.equal(saved.preparation.routerDetailsProvided,true);
  assert.equal(saved.capability.routerConnected,false);assert.equal(saved.capability.deviceBound,false);assert.equal(saved.capability.controlAvailable,false);assert.equal(saved.capability.multiUserAvailable,false);assert.equal(saved.policy.policyApplied,false);
  assert.deepEqual(new HomeSetupStore({dataDir:dir}).read(),saved);
  fs.writeFileSync(store.file,'{broken');assert.throws(()=>store.read(),error=>error.status===503);
  assert.equal(store.save(details()).details.deviceAlias,'我的筆電','explicit save can repair corrupt preparation data');
  fs.mkdirSync(store.file+'.tmp');assert.throws(()=>store.save(details()),error=>error.status===503&&!error.message.includes(dir),'storage errors must not expose a local path or claim success');
});
test('setup rejects privileged fields, credentials, invalid shapes and oversized labels',()=>{
  for(const value of [null,[],{}, {...details(),password:'secret'}, {...details(),routerConnected:true}, {...details(),deviceBound:true}, {...details(),deviceAlias:''}, {...details(),deviceAlias:'x'.repeat(41)}, {...details(),routerModel:'x'.repeat(65)}, {...details(),deviceAlias:'bad\nname'}, {...details(),managementAccess:'verified'}])assert.throws(()=>validateSetup(value),error=>error.status===400);
});
test('HTTP setup is local-only, persists preparation and never starts a network check',async t=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'roomflow-setup-http-'));let starts=0;
  const app=createApp({dataDir:dir,quickCheckController:{get:()=>null,start:()=>{starts++;},dispose:async()=>{}}});
  await new Promise(resolve=>app.server.listen(0,'127.0.0.1',resolve));t.after(async()=>{await app.dispose();fs.rmSync(dir,{recursive:true,force:true});});
  const base=`http://127.0.0.1:${app.server.address().port}`;
  assert.equal((await(await fetch(base+'/api/home-setup')).json()).scope,'server-host');
  const post=(body,origin)=>fetch(base+'/api/home-setup',{method:'POST',headers:{'Content-Type':'application/json',...(origin?{Origin:origin}:{})},body:JSON.stringify(body)});
  assert.equal((await post(details(),'https://example.com')).status,403);
  assert.equal((await post({...details(),controlAvailable:true})).status,400);
  assert.equal((await post(details())).status,200);
  assert.equal((await(await fetch(base+'/api/home-setup')).json()).details.deviceAlias,'我的筆電');
  assert.equal(starts,0);
});
