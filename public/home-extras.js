'use strict';
(()=>{
  const $=id=>document.getElementById(id),tools=window.RoomFlowHomeTools;
  const copy={
    'zh-Hant':{deviceLabel:'需求裝置／量測主機',host:'執行 RoomFlow 的這台電腦',deviceUnbound:'名稱尚未綁定路由器',firstSetup:'第一次設定／管理者協助',setupTitle:'首次設定與準備狀態',setupIntro:'先命名這台電腦。有路由器資料時再補上；儲存資料不會變更網路。',stepDevice:'1. 命名這台電腦',stepRouter:'2. 提供路由器資料',stepConnect:'3. 管理者連接與設備綁定',stepConnectPending:'等待支援設備與實際驗證',aliasLabel:'這台電腦的名稱',aliasNote:'只是方便辨認的名稱，並非路由器設備綁定。',accessLabel:'路由器管理權',accessUnknown:'還不清楚',accessHelp:'需要找管理者協助',accessAvailable:'我有管理權（尚未驗證）',brandLabel:'路由器品牌（可稍後填）',modelLabel:'型號（可稍後填）',saveSetup:'儲存準備資料',copySetup:'複製給管理者的清單',setupNotConnected:'路由器控制尚未開通',setupLimit:'目前僅限本機。提供品牌型號後，仍需確認支援、管理權、設備對應與策略讀回，才能顯示「已套用」。不需在這裡輸入路由器密碼。',roomPolicy:'多人使用準備規則：同級公平分享、各自只改自己的裝置、限時自動恢復；目前尚未啟用。',nextAction:'接下來，你可以這樣做',changeNote:'完成下列調整後再按，我們會保留前後觀察。調整內容由你確認，工具不會自動修改網路。',compareEthernet:'我接好網路線了，再檢查',comparePaused:'已暫停下載，再比較',compareCloser:'已靠近路由器，再比較',copyCheck:'複製檢查摘要',comparisonTitle:'已保存的前後比較',comparisonHistory:'比較紀錄（這個瀏覽器）',comparisonLimit:'每次是少量探測。前後負載與時間可能不同，不能直接認定調整造成改善，也不代表遊戲或通話品質。',copyComparison:'複製這份比較摘要',manualCopy:'瀏覽器無法直接複製，可選取以下文字手動複製',named:'名稱已儲存；設備綁定待確認',notNamed:'尚未命名',provided:'已填寫，支援性待驗證',missingRouter:'可稍後提供品牌與型號',saved:'準備資料已儲存。路由器尚未連接，模式尚未套用。',setupError:'設定資料目前無法讀取或儲存，請稍後重試。',copied:'已複製摘要。',copyFallback:'請使用頁面下方的文字框手動複製。',storageError:'瀏覽器無法保存比較，請複製摘要留存。',wait:'正在檢查，完成後會顯示前後觀察。',oldBaseline:'這份結果已超過 15 分鐘或時間異常，請先重新檢查，再做比較。',comparisonFailed:'這次未完成比較。已保留先前資料，請重新檢查後再試。',otherJob:'另一個檢查已經開始，不能當作本次調整後的量測。完成後可重新比較。',invalidComparison:'這兩次結果時間相同、間隔過長或資料不足，無法建立這次比較。',ethernet:'已接上網路線（使用者確認）',paused:'已暫停下載／備份（使用者確認）',closer:'已靠近路由器（使用者確認）',before:'調整前',after:'調整後',decreased:'減少',increased:'增加',same:'相近',unavailable:'資料不足',attempts:'探測未成功',gateway:'到路由器',internet:'外部網路',dns:'網站名稱查詢',service:'常用服務',adminTitle:'RoomFlow 管理者準備清單',adminSteps:'待管理者確認：支援型號與韌體、管理權、設備對應、上下行頻寬、策略讀回與到期恢復。',adminLimit:'目前只保存準備資料；未連接路由器，未綁定設備，未套用流量策略。',unknown:'未提供',aliasPlaceholder:'例如：我的筆電'},
    en:{deviceLabel:'Preference device / measurement host',host:'The computer running RoomFlow',deviceUnbound:'Name is not bound to a router device',firstSetup:'First-time setup / admin help',setupTitle:'Setup and preparation status',setupIntro:'Name this computer first. Add router details when available. Saving details does not change the network.',stepDevice:'1. Name this computer',stepRouter:'2. Provide router details',stepConnect:'3. Administrator connection and device binding',stepConnectPending:'Awaiting supported hardware and verification',aliasLabel:'Name for this computer',aliasNote:'A friendly label, not a verified router device binding.',accessLabel:'Router management access',accessUnknown:'Not sure yet',accessHelp:'I need administrator help',accessAvailable:'I have access (not verified)',brandLabel:'Router brand (optional for now)',modelLabel:'Model (optional for now)',saveSetup:'Save preparation details',copySetup:'Copy administrator checklist',setupNotConnected:'Router control is not connected',setupLimit:'Local computer only. A model name still requires support, access, device mapping and policy readback checks before a mode can be marked applied. Do not enter a router password here.',roomPolicy:'Planned shared-use rules: fair sharing at the same priority, control only your own bound device, and automatic expiry. These rules are not active yet.',nextAction:'What you can do next',changeNote:'Make a change below before pressing its button. We will keep the observations from both checks. Changes are reported by you; RoomFlow does not modify the network.',compareEthernet:'Ethernet connected — check again',comparePaused:'Downloads paused — compare',compareCloser:'Closer to router — compare',copyCheck:'Copy check summary',comparisonTitle:'Saved before-and-after comparison',comparisonHistory:'Comparisons in this browser',comparisonLimit:'Each check is a small sample. Time and load may differ. A change in observations does not establish causation or actual game/call quality.',copyComparison:'Copy this comparison',manualCopy:'Automatic copy is unavailable. Select the text below to copy manually.',named:'Name saved; device binding unverified',notNamed:'Not named yet',provided:'Provided; support unverified',missingRouter:'Brand and model can be added later',saved:'Preparation details saved. Router disconnected; no policy applied.',setupError:'Setup details could not be read or saved. Please try again.',copied:'Summary copied.',copyFallback:'Use the text box below to copy the summary manually.',storageError:'This browser could not save comparisons. Copy the summary to keep it.',wait:'Checking. The observations will be compared when complete.',oldBaseline:'This result is over 15 minutes old or has an unexpected time. Run a fresh check before comparing.',comparisonFailed:'This comparison did not complete. Earlier records are kept. Run a fresh check and try again.',otherJob:'Another check had already started. It cannot represent the change you just made. You can compare again after it finishes.',invalidComparison:'The checks have the same time, are too far apart, or lack required data. This comparison is unavailable.',ethernet:'Ethernet connected (user reported)',paused:'Downloads / backups paused (user reported)',closer:'Moved closer to the router (user reported)',before:'Before',after:'After',decreased:'Lower by',increased:'Higher by',same:'Similar',unavailable:'Not enough data',attempts:'Unsuccessful probes',gateway:'To the router',internet:'Internet',dns:'DNS',service:'Common services',adminTitle:'RoomFlow administrator checklist',adminSteps:'Verify supported model and firmware, management access, device mapping, upload/download rates, policy readback and automatic expiry.',adminLimit:'Preparation details only. Router disconnected, device unbound, and no traffic policy applied.',unknown:'Not provided',aliasPlaceholder:'e.g. My laptop'}
  };
  Object.assign(copy['zh-Hant'],{compareUnchanged:'維持現況，再量一次比較',unchanged:'未調整設定，只重新量測'});
  Object.assign(copy.en,{compareUnchanged:'Same setup — measure again',unchanged:'No settings changed; repeated measurement'});
  let language='zh-Hant',setup=null,formDirty=false,current=null,currentId=null,busy=false,feedback='',setupFeedback='';
  let comparisons=[],selectedComparison=0,pending=null;
  const conditions=['ethernet','paused','closer','unchanged'];
  const key='roomflow.home.comparisons.v1',pendingKey='roomflow.home.pending-comparison.v1';
  const t=name=>copy[language][name]??name;
  const getStored=name=>{try{return localStorage.getItem(name);}catch{return null;}};
  const setStored=(name,value)=>{try{localStorage.setItem(name,JSON.stringify(value));return true;}catch{return false;}};
  try{const raw=getStored(key);if(raw?.length<100000){const entries=JSON.parse(raw);if(Array.isArray(entries))comparisons=entries.filter(x=>conditions.includes(x.condition)&&tools.cleanResult(x.before)&&tools.cleanResult(x.after)&&tools.compare(x.before,x.after).valid).slice(0,6);}}catch{}
  try{const p=JSON.parse(getStored(pendingKey));if(p&&conditions.includes(p.condition)&&tools.cleanResult(p.before)&&Number.isFinite(p.requestedAt)&&Date.now()-p.requestedAt>=0&&Date.now()-p.requestedAt<120000)pending=p;}catch{}
  function persistPending(){setStored(pendingKey,pending);}
  function formatDate(value){try{return new Intl.DateTimeFormat(language==='en'?'en-US':'zh-TW',{dateStyle:'short',timeStyle:'medium'}).format(new Date(value));}catch{return '—';}}
  function renderSetup(){
    $('device-name').textContent=setup?.details.deviceAlias||t('host');
    $('device-verification').textContent=t('deviceUnbound');
    $('setup-device-state').textContent=t(setup?.preparation.deviceNamed?'named':'notNamed');
    $('setup-router-state').textContent=t(setup?.preparation.routerDetailsProvided?'provided':'missingRouter');
    $('setup-feedback').textContent=setupFeedback?t(setupFeedback):'';
    $('device-alias').setAttribute('placeholder',t('aliasPlaceholder'));
  }
  function renderActions(){
    for(const id of conditions)$(`compare-${id}`).disabled=busy||!current;
    $('copy-check').disabled=busy||!current;
    $('action-feedback').textContent=feedback?t(feedback):'';
  }
  function renderComparison(){
    const section=$('comparison-section');section.hidden=!comparisons.length;if(!comparisons.length)return;
    const select=$('comparison-history');select.replaceChildren();
    comparisons.forEach((item,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=`${formatDate(item.after.observedAt)} · ${t(item.condition)}`;select.append(option);});
    selectedComparison=Math.min(selectedComparison,comparisons.length-1);select.value=String(selectedComparison);
    const entry=comparisons[selectedComparison],comp=tools.compare(entry.before,entry.after);
    $('comparison-condition').textContent=t(entry.condition);
    $('comparison-times').textContent=`${t('before')}: ${formatDate(entry.before.observedAt)} → ${t('after')}: ${formatDate(entry.after.observedAt)}`;
    const rows=$('comparison-rows');rows.replaceChildren();
    for(const row of comp.rows){
      const card=document.createElement('div');card.className='comparison-row';
      const title=document.createElement('strong');title.textContent=t(row.id);
      const numbers=document.createElement('p');numbers.textContent=`${row.beforeMs===null?'—':row.beforeMs.toFixed(1)} → ${row.afterMs===null?'—':row.afterMs.toFixed(1)} ms`;
      const delta=document.createElement('span');delta.textContent=row.deltaMs===null?t('unavailable'):Math.abs(row.deltaMs)<0.1?t('same'):`${t(row.deltaMs<0?'decreased':'increased')} ${Math.abs(row.deltaMs).toFixed(1)} ms`;
      const counts=document.createElement('small');counts.textContent=`${t('attempts')}: ${row.beforeFailed}/${row.beforeAttempts} → ${row.afterFailed}/${row.afterAttempts}`;
      card.append(title,numbers,delta,counts);rows.append(card);
    }
  }
  function onResult(value,id){
    const result=tools.cleanResult(value);if(!result){current=null;currentId=null;onError();return;}
    current=result;currentId=id;
    if(pending){
      if(pending.jobId===id&&id!==pending.beforeId){
        const comparison=tools.compare(pending.before,result);
        if(comparison.valid){
          const entry={condition:pending.condition,before:pending.before,after:result};
          comparisons=[entry,...comparisons.filter(x=>x.after.observedAt!==result.observedAt)].slice(0,6);selectedComparison=0;
          feedback=setStored(key,comparisons)?'':'storageError';
        }else feedback='invalidComparison';
      }else feedback='comparisonFailed';
      pending=null;persistPending();
    }
    busy=false;renderActions();renderComparison();
  }
  function onJob(job){
    busy=job.status==='running';
    if(busy&&pending){
      if(Date.parse(job.startedAt)<pending.requestedAt-1000){pending=null;feedback='otherJob';}
      else pending.jobId=job.id;
      persistPending();
    }
    if(job.status==='failed')onError();
    renderActions();
  }
  function onError(){busy=false;if(pending){feedback='comparisonFailed';pending=null;persistPending();}renderActions();}
  async function copyText(text,feedbackTarget){
    if(!text)return;
    try{if(!navigator.clipboard?.writeText)throw new Error('manual');await navigator.clipboard.writeText(text);$('manual-copy').hidden=true;feedbackTarget.textContent=t('copied');}
    catch{$('copy-text').value=text;$('manual-copy').hidden=false;$('copy-text').focus();$('copy-text').select();feedbackTarget.textContent=t('copyFallback');}
  }
  let startCheck=null;
  for(const condition of conditions)$(`compare-${condition}`).addEventListener('click',()=>{
    if(busy||!current||!startCheck)return;
    const age=Date.now()-Date.parse(current.observedAt);
    if(age>15*60000||age < -60000){feedback='oldBaseline';renderActions();return;}
    pending={condition,before:tools.cleanResult(current),beforeId:currentId,requestedAt:Date.now(),jobId:null};persistPending();
    busy=true;feedback='wait';renderActions();startCheck();
  });
  $('copy-check').addEventListener('click',()=>copyText(tools.summary(current,{language}),$('action-feedback')));
  $('copy-comparison').addEventListener('click',()=>{const entry=comparisons[selectedComparison];if(entry)copyText(tools.summary(entry.after,{language,condition:t(entry.condition),comparison:tools.compare(entry.before,entry.after)}),$('comparison-feedback'));});
  $('comparison-history').addEventListener('change',()=>{const value=Number($('comparison-history').value);if(Number.isInteger(value)&&value>=0&&value<comparisons.length){selectedComparison=value;renderComparison();}});
  $('open-setup').addEventListener('click',()=>{$('setup-panel').open=true;$('device-alias').focus();});
  for(const id of ['device-alias','router-brand','router-model','management-access'])$(id).addEventListener('input',()=>{formDirty=true;});
  async function setupRequest(options){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);try{const response=await fetch('/api/home-setup',{...options,signal:controller.signal,cache:'no-store'});if(!response.ok)throw new Error('setup');const value=await response.json();if(value.scope!=='server-host'||typeof value.details?.deviceAlias!=='string'||value.capability?.routerConnected!==false||value.capability?.deviceBound!==false)throw new Error('setup');return value;}finally{clearTimeout(timer);}}
  function fillForm(){if(!setup||formDirty)return;$('device-alias').value=setup.details.deviceAlias;$('router-brand').value=setup.details.routerBrand;$('router-model').value=setup.details.routerModel;$('management-access').value=setup.details.managementAccess;}
  $('setup-form').addEventListener('submit',async event=>{
    event.preventDefault();if($('setup-fields').disabled)return;
    $('setup-fields').disabled=true;
    const details={deviceAlias:$('device-alias').value.trim(),routerBrand:$('router-brand').value.trim(),routerModel:$('router-model').value.trim(),managementAccess:$('management-access').value};
    try{setup=await setupRequest({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(details)});formDirty=false;fillForm();setupFeedback='saved';}
    catch{setupFeedback='setupError';}finally{$('setup-fields').disabled=false;renderSetup();}
  });
  $('copy-setup').addEventListener('click',()=>{
    const d=setup?.details;
    const lines=[t('adminTitle'),`${t('aliasLabel')}: ${d?.deviceAlias||t('unknown')}`,`${t('brandLabel')}: ${d?.routerBrand||t('unknown')}`,`${t('modelLabel')}: ${d?.routerModel||t('unknown')}`,`${t('accessLabel')}: ${t(d?.managementAccess==='available'?'accessAvailable':d?.managementAccess==='need-help'?'accessHelp':'accessUnknown')}`,t('adminSteps'),t('adminLimit')];
    copyText(lines.join('\n'),$('setup-feedback'));
  });
  window.RoomFlowHomeExtras={attach(callback){startCheck=callback;},onResult,onJob,onError,
    onStarting(){busy=true;renderActions();},onNoJob(){if(pending){pending=null;feedback='comparisonFailed';persistPending();renderActions();}},
    setLanguage(value){language=value==='en'?'en':'zh-Hant';document.querySelectorAll('[data-x]').forEach(el=>{el.textContent=t(el.dataset.x);});renderSetup();renderActions();renderComparison();}};
  window.RoomFlowHomeExtras.setLanguage(document.documentElement.lang);
  setupRequest().then(value=>{setup=value;fillForm();renderSetup();}).catch(()=>{setupFeedback='setupError';renderSetup();});
})();
