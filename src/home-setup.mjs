import fs from 'node:fs';
import path from 'node:path';
import { atomicJson } from './session.mjs';

const DEFAULT = {deviceAlias:'',routerBrand:'',routerModel:'',managementAccess:'unknown'};
const KEYS = Object.keys(DEFAULT);
const invalid = () => Object.assign(new Error('Invalid setup details.'), {status:400});
export function validateSetup(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(key=>!KEYS.includes(key))) throw invalid();
  const result = {};
  for (const key of ['deviceAlias','routerBrand','routerModel']) {
    const text = value[key];
    if (typeof text !== 'string' || /[\u0000-\u001f\u007f]/.test(text) || text.trim().length > (key==='deviceAlias'?40:64)) throw invalid();
    result[key] = text.trim();
  }
  if (!result.deviceAlias || !['unknown','available','need-help'].includes(value.managementAccess)) throw invalid();
  result.managementAccess = value.managementAccess;
  return result;
}
export class HomeSetupStore {
  constructor({dataDir,now=Date.now}) { this.file=path.join(dataDir,'home-setup.json');this.now=now; }
  read() {
    let details={...DEFAULT},updatedAt=null;
    if(fs.existsSync(this.file)) {
      try {
        if(fs.statSync(this.file).size>8192) throw new Error('Too large');
        const saved=JSON.parse(fs.readFileSync(this.file,'utf8'));
        details=validateSetup(saved.details);
        if(typeof saved.updatedAt!=='string'||!Number.isFinite(Date.parse(saved.updatedAt)))throw new Error('Invalid time');
        updatedAt=saved.updatedAt;
      } catch { throw Object.assign(new Error('Setup details could not be read. Save the form to repair them.'),{status:503}); }
    }
    return this.view(details,updatedAt);
  }
  view(details,updatedAt) {
    return {schemaVersion:1,details,updatedAt,scope:'server-host',
      preparation:{deviceNamed:Boolean(details.deviceAlias),routerDetailsProvided:Boolean(details.routerBrand&&details.routerModel)},
      capability:{routerConnected:false,deviceBound:false,controlAvailable:false,multiUserAvailable:false,access:'localhost-only'},
      policy:{multiplePriority:'fair-share',policyApplied:false}};
  }
  save(value) {
    const details=validateSetup(value),updatedAt=new Date(this.now()).toISOString();
    try { atomicJson(this.file,{schemaVersion:1,details,updatedAt}); }
    catch { throw Object.assign(new Error('Setup details could not be saved. Please retry.'),{status:503}); }
    return this.view(details,updatedAt);
  }
}
