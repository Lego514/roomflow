'use strict';
(() => {
  const strings = {
    'zh-Hant': {
      title:'RoomFlow 同住｜讓共享網路，更好相處',skip:'跳到主要內容',brandSub:'同住，順一點。',records:'連線紀錄',lab:'進階實驗',language:'介面語言',eyebrow:'SHARED WIFI. SHARED LIFE.',heroA:'一起上網，',heroB:'重要時刻更穩。',heroDescription:'開會、打遊戲，還是下載大檔？\n選好你的需求，剩下的簡單一點。',illustrationNote:'一個屋簷，各自精彩。',modeTitle:'你現在要做什麼？',modeDescription:'只選自己的需求，不用懂任何網路設定。',routerDisconnected:'尚未連接路由器',priority:'打遊戲／開會',priorityDescription:'重要時刻，想要低延遲。',priorityFoot:'限時需求 · 到期自動恢復',normal:'一般使用',normalDescription:'追劇、瀏覽，照常使用。',normalFoot:'日常預設 · 不用一直操作',background:'我可以讓路',backgroundDescription:'正在下載，願意讓室友優先。',backgroundFoot:'空閒時，仍希望用剩餘頻寬',selectedLabel:'這個瀏覽器的需求',notApplied:'已選擇・尚未套用',duration:'持續時間',minutes30:'30 分鐘',minutes60:'60 分鐘',minutes120:'120 分鐘',endEarly:'提前結束',routerNotice:'目前只保存你的需求，尚未調整實際網路。需要由管理者連接支援的路由器後，模式才能生效。',checkTitle:'覺得網路卡卡的？',checkDescription:'不用猜原因，先幫連線做一次簡單檢查。',quickTitle:'一鍵檢查連線',quickDescription:'檢查到路由器、外部網路與常用服務的連線。',lightweight:'輕量檢查，不做大量下載或上傳',startCheck:'開始檢查',checking:'正在檢查連線，請稍候…',seeDetails:'查看詳細結果',probeLimit:'這些是連線探測結果，無法保證 LOL 或實際通話品質，也不能單靠一次檢查確定故障原因。',checkUnavailable:'這次尚未完成檢查',scopeLabel:'檢查範圍',scopeDescription:'執行 RoomFlow 的這台電腦。從其他裝置開啟頁面時，結果不代表該裝置本身的 Wi-Fi 品質。',moreEyebrow:'WHEN YOU WANT TO KNOW MORE',moreTitle:'想多了解一點？',moreDescription:'平常不用看這些，需要時再打開。',historyTitle:'連線紀錄與異常事件',historyDescription:'查看量測時間、歷史變化與恢復紀錄',labTitle:'進階實驗室',labDescription:'模型比較與保存的封包實測',loadNote:'大量流量與壅塞壓力測試不會由「一鍵檢查」執行，以免打擾正在使用網路的人。',footer:'讓共享網路，更好相處。',localOnly:'本機運作 · 不需要路由器密碼來查看結果',preferenceSaved:'需求已保存在這個瀏覽器，實際網路尚未變更。',preferenceExpired:'這次需求時間已到，已回到一般使用；實際網路未曾變更。',preferenceEnded:'已結束這次需求，回到一般使用；實際網路未曾變更。',storageUnavailable:'瀏覽器無法保存需求，關閉頁面後可能不會保留；實際網路尚未變更。',remaining:'需求剩餘',checkAgain:'重新檢查',retry:'再試一次',runningButton:'檢查中…',resultLabel:'本次連線觀察',staleLabel:'先前的檢查結果 · 請重新檢查',okTitle:'這次探測未發現明顯異常。',okExplanation:'已取得的連線探測在專案設定的門檻內；這不等於每個遊戲或會議一定順暢。',okNext:'如果還是卡頓，先確認遊戲內延遲、畫面幀率，或會議中的音訊狀況。',gatewayTitle:'到路由器的連線出現不穩定跡象。',gatewayExplanation:'部分本地連線探測偏慢或未成功。這個結果還不能確定是 Wi-Fi 干擾、設備忙碌或其他原因。',gatewayNext:'建議先接網路線，或靠近路由器後再檢查。',internetTitle:'外部網路探測出現異常。',internetExplanation:'部分外部連線偏慢或未成功；一次檢查不能確定是家中壅塞、上游路徑或目標端造成。',internetNext:'可先暫停大量下載或備份再比較；若仍持續，保存紀錄交給管理者。',dnsTitle:'查詢網站名稱時遇到異常。',dnsExplanation:'部分名稱查詢偏慢或未成功；這不代表已建立的遊戲或會議連線一定受影響。',dnsNext:'重新檢查，並比較不同網站是否也無法開啟。',serviceTitle:'常用服務的連線探測出現異常。',serviceExplanation:'檢查的是服務網站連線，不是正在進行的視訊或遊戲；目前仍無法判定應用程式的實際品質。',serviceNext:'確認實際使用的服務狀態，並查看詳細結果是否也有其他層異常。',wifiTitle:'這台電腦的 Wi-Fi 狀態需要留意。',wifiExplanation:'取得的無線連線資訊顯示可能需要檢查，但不能單憑訊號數字確定卡頓原因。',wifiNext:'可先靠近路由器或改用網路線，再比較是否改善。',unknownTitle:'目前資料不足，還不能判定連線狀況。',unknownExplanation:'一個或多個檢查未取得足夠資料；沒有量測結果不代表網路正常。',unknownNext:'請重新檢查；若持續缺少資料，可將詳細結果交給管理者。',partialNote:'另有部分檢查資料不足，請展開詳細結果查看。',observedAt:'檢查時間',gateway:'到路由器',internet:'外部網路',dns:'網站名稱查詢',service:'常用服務',ok:'未見明顯異常',attention:'需要留意',unknown:'資料不足',latency:'探測 p95 延遲',failed:'探測未成功',noValue:'未取得',historySaved:'這次結果已保存到本機連線紀錄。',historyNotSaved:'這次結果未保存至歷史紀錄，請保留本頁結果。',requestFailed:'無法取得本機檢查服務的回應。請確認 RoomFlow 正在這台電腦執行，再試一次。',timeout:'本次檢查超過時間限制，尚未取得完整結果。請稍後再試。',pythonUnavailable:'這台電腦的檢查工具尚未準備好，請管理者確認 Python 與 RoomFlow 的設定。',interrupted:'檢查被中斷，未取得完整結果。可以重新檢查。',invalidResult:'檢查結果無法讀取，請重新檢查。',staleExplanation:'以下是先前保存的觀察，不能代表現在的連線狀況。',noRecord:'尚未執行檢查',elapsed:'已經過',seconds:'秒',minuteUnit:'分',secondUnit:'秒'
    },
    en: {
      title:'RoomFlow | A calmer shared connection',skip:'Skip to main content',brandSub:'A little more room for everyone.',records:'Connection history',lab:'Advanced lab',language:'Interface language',eyebrow:'SHARED WIFI. SHARED LIFE.',heroA:'One connection.',heroB:'More room for what matters.',heroDescription:'A call, a game, or a large download?\nChoose what you need. Keep the rest simple.',illustrationNote:'One home. Different moments.',modeTitle:'What are you doing now?',modeDescription:'Choose your own needs. No network knowledge needed.',routerDisconnected:'Router not connected',priority:'Gaming / a call',priorityDescription:'I want low latency for this moment.',priorityFoot:'Timed preference · returns automatically',normal:'Everyday use',normalDescription:'Browsing, streaming, the usual.',normalFoot:'The everyday default · no constant switching',background:'I can make room',backgroundDescription:'I am downloading and can let others go first.',backgroundFoot:'Use spare bandwidth when the connection is quiet',selectedLabel:'Preference in this browser',notApplied:'Selected · not applied',duration:'Duration',minutes30:'30 minutes',minutes60:'60 minutes',minutes120:'120 minutes',endEarly:'End early',routerNotice:'Your preference is saved, but the actual network has not changed. An administrator must connect a supported router before modes can take effect.',checkTitle:'Connection feeling slow?',checkDescription:'Start with a simple check instead of guessing.',quickTitle:'Check my connection',quickDescription:'Check the connection to the router, the internet, and common services.',lightweight:'Lightweight probes. No bulk downloads or uploads.',startCheck:'Start check',checking:'Checking the connection. Please wait…',seeDetails:'See detailed results',probeLimit:'These are connection probes. They do not establish actual League of Legends or call quality, or confirm a fault’s cause.',checkUnavailable:'This check has not completed',scopeLabel:'Check scope',scopeDescription:'The computer running RoomFlow. If you open this page on another device, the results do not describe that device’s own Wi-Fi quality.',moreEyebrow:'WHEN YOU WANT TO KNOW MORE',moreTitle:'A little more detail?',moreDescription:'You only need these when you want a closer look.',historyTitle:'Connection history & incidents',historyDescription:'See measurement times, changes, and recovery records',labTitle:'Advanced lab',labDescription:'Queueing models and saved packet measurements',loadNote:'The connection check never runs bulk traffic or congestion stress tests, so it does not add that load during someone’s call.',footer:'A calmer shared connection.',localOnly:'Runs locally · no router password needed to view results',preferenceSaved:'Preference saved in this browser. The actual network has not changed.',preferenceExpired:'The preference expired and returned to everyday use. The actual network was never changed.',preferenceEnded:'Preference ended and returned to everyday use. The actual network was never changed.',storageUnavailable:'This browser could not save your preference. It may not remain after closing the page. The actual network has not changed.',remaining:'Preference remaining',checkAgain:'Check again',retry:'Try again',runningButton:'Checking…',resultLabel:'Connection observations',staleLabel:'Earlier result · check again for an update',okTitle:'These probes found no obvious issues.',okExplanation:'The available probes were within this project’s thresholds. This does not guarantee a smooth game or call.',okNext:'If you still notice problems, compare in-game latency, frame rate, or the audio in your actual call.',gatewayTitle:'The connection to the router needs a closer look.',gatewayExplanation:'Some local probes were slow or unsuccessful. This does not yet distinguish Wi-Fi interference, a busy device, or another cause.',gatewayNext:'Try an Ethernet cable or move closer to the router, then check again.',internetTitle:'Some internet probes need a closer look.',internetExplanation:'Some external connections were slow or unsuccessful. One check cannot distinguish home congestion, an upstream path, or the destination.',internetNext:'Pause bulk downloads or backups and compare. If the issue continues, share the saved observations with your administrator.',dnsTitle:'Some website-name lookups need a closer look.',dnsExplanation:'Some name lookups were slow or unsuccessful. This does not establish an effect on an already connected game or call.',dnsNext:'Check again and compare whether different websites also fail to open.',serviceTitle:'Some service connection probes need a closer look.',serviceExplanation:'These probes connect to service websites, not your live call or game. They do not establish actual application quality.',serviceNext:'Check the service you are using, and look for issues in other layers in the detailed results.',wifiTitle:'This computer’s Wi-Fi status needs a closer look.',wifiExplanation:'The available wireless information suggests a check may help. Signal information alone does not establish the cause of a problem.',wifiNext:'Move closer to the router or try an Ethernet cable, then compare.',unknownTitle:'There is not enough data to assess this connection.',unknownExplanation:'One or more checks did not produce enough data. Missing measurements do not mean the connection is healthy.',unknownNext:'Try again. If data are still missing, show the detailed results to your administrator.',partialNote:'Some other checks also have missing data. Open the detailed results.',observedAt:'Checked at',gateway:'To the router',internet:'Internet',dns:'Website-name lookup',service:'Common services',ok:'No obvious issue',attention:'Needs a look',unknown:'Not enough data',latency:'Probe p95 latency',failed:'Unsuccessful probes',noValue:'Unavailable',historySaved:'This result was saved in the local connection history.',historyNotSaved:'This result was not saved in the history. Keep this page if you need the observations.',requestFailed:'The local check service did not respond. Confirm that RoomFlow is running on this computer, then try again.',timeout:'The check exceeded its time limit without a complete result. Please try again later.',pythonUnavailable:'The check tool is not ready on this computer. Ask your administrator to check Python and the RoomFlow setup.',interrupted:'The check was interrupted before a complete result was available. You can try again.',invalidResult:'The check result could not be read. Please try again.',staleExplanation:'These are earlier saved observations and do not describe the current connection.',noRecord:'No check yet',elapsed:'Elapsed',seconds:'seconds',minuteUnit:'m',secondUnit:'s'
    }
  };
  Object.assign(strings['zh-Hant'], {wifiDetail:'這台電腦的 Wi-Fi',wifiSignal:'訊號強度',wifiUnavailable:'未取得無線資訊',wifiUnavailableExplanation:'可能使用有線連線，或這台電腦不支援讀取無線資訊；這不代表斷線。'});
  Object.assign(strings.en, {wifiDetail:'This computer’s Wi-Fi',wifiSignal:'Signal strength',wifiUnavailable:'Wireless information unavailable',wifiUnavailableExplanation:'This computer may be using Ethernet, or wireless information may not be supported. This does not mean it is disconnected.'});
  const $ = id => document.getElementById(id);
  const storage = { get(key){try{return localStorage.getItem(key);}catch{return null;}},set(key,value){try{localStorage.setItem(key,value);return true;}catch{return false;}} };
  let language = storage.get('roomflow.home.language') === 'en' ? 'en' : 'zh-Hant';
  let preference = {mode:'normal',expiresAt:null,minutes:60};
  let feedbackKey = '';
  let job = null;
  let errorKey = '';
  let pollTimer = null;
  let checkingStartedAt = null;
  let userStartedCheck = false;
  let startRequestPending = false;
  let resultPresentation = null;
  const t = key => strings[language][key] ?? key;
  try {
    const saved=JSON.parse(storage.get('roomflow.home.preference')||'null');
    if(saved && ['normal','priority','background'].includes(saved.mode) && [30,60,120].includes(saved.minutes)) {
      if(saved.mode==='normal') preference={mode:'normal',expiresAt:null,minutes:saved.minutes};
      else if(Number.isFinite(saved.expiresAt) && saved.expiresAt>Date.now() && saved.expiresAt<=Date.now()+120*60000) preference={mode:saved.mode,expiresAt:saved.expiresAt,minutes:saved.minutes};
    }
  } catch {}
  function persistPreference(){if(!storage.set('roomflow.home.preference',JSON.stringify(preference)))feedbackKey='storageUnavailable';}
  function renderPreference(){
    if(preference.mode!=='normal' && preference.expiresAt<=Date.now()) {preference.mode='normal';preference.expiresAt=null;feedbackKey='preferenceExpired';persistPreference();}
    document.querySelectorAll('[data-mode]').forEach(button=>{const selected=button.dataset.mode===preference.mode;button.classList.toggle('selected',selected);button.setAttribute('aria-checked',String(selected));button.tabIndex=selected?0:-1;});
    $('selected-mode').textContent=t(preference.mode);
    $('mode-duration').value=String(preference.minutes);
    $('mode-duration').disabled=preference.mode==='normal';
    $('mode-countdown').hidden=preference.mode==='normal';
    $('mode-end').hidden=preference.mode==='normal';
    if(preference.mode!=='normal') {
      const total=Math.max(0,Math.ceil((preference.expiresAt-Date.now())/1000));
      $('mode-countdown').textContent=`${t('remaining')} ${Math.floor(total/60)}:${String(total%60).padStart(2,'0')}`;
    }
    $('mode-feedback').textContent=feedbackKey?t(feedbackKey):'';
  }
  document.querySelectorAll('[data-mode]').forEach(button=>button.addEventListener('click',()=>{
    preference.mode=button.dataset.mode;
    preference.expiresAt=preference.mode==='normal'?null:Date.now()+preference.minutes*60000;
    feedbackKey='preferenceSaved';persistPreference();renderPreference();
  }));
  // A radio group is also operable with the standard arrow-key interaction.
  document.querySelector('.mode-grid').addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
    const buttons=[...document.querySelectorAll('[data-mode]')];const current=buttons.indexOf(document.activeElement);if(current<0)return;
    event.preventDefault();let index=event.key==='Home'?0:event.key==='End'?buttons.length-1:(current+(['ArrowLeft','ArrowUp'].includes(event.key)?-1:1)+buttons.length)%buttons.length;
    buttons[index].focus();buttons[index].click();
  });
  $('mode-duration').addEventListener('change',()=>{const minutes=Number($('mode-duration').value);if(![30,60,120].includes(minutes))return;preference.minutes=minutes;if(preference.mode!=='normal')preference.expiresAt=Date.now()+minutes*60000;feedbackKey='preferenceSaved';persistPreference();renderPreference();});
  $('mode-end').addEventListener('click',()=>{preference.mode='normal';preference.expiresAt=null;feedbackKey='preferenceEnded';persistPreference();renderPreference();});
  function formatTime(value){const date=new Date(value);return Number.isFinite(date.getTime())?new Intl.DateTimeFormat(language==='en'?'en-US':'zh-TW',{dateStyle:'short',timeStyle:'medium'}).format(date):t('noValue');}
  const validStatus=value=>['ok','attention','unknown'].includes(value)?value:'unknown';
  function resultState(result){
    const layers=Array.isArray(result.layers)?result.layers:[];
    if(result.wifi?.available && result.wifi.status==='attention')return 'attention';
    if(layers.some(layer=>validStatus(layer.status)==='attention')||result.overall==='attention')return 'attention';
    if(result.wifi?.available && validStatus(result.wifi.status)==='unknown')return 'unknown';
    const required=['gateway','internet','dns','service'];
    if(required.some(id=>!layers.some(layer=>layer.id===id && layer.status==='ok' && Number.isFinite(layer.attempts) && layer.attempts>0))||result.overall!=='ok')return 'unknown';
    return 'ok';
  }
  function refreshResultFreshness(force=false){
    if(!resultPresentation||$('check-result').hidden)return;
    const age=Date.now()-new Date(resultPresentation.result.observedAt).getTime();
    const stale=age>15*60000||age < -60000;
    if(!force&&stale===resultPresentation.stale)return;
    resultPresentation.stale=stale;
    const {state,explanation}=resultPresentation;
    $('check-result').dataset.state=stale?'unknown':state;
    $('result-symbol').textContent=stale?'◷':state==='ok'?'✓':state==='attention'?'!':'?';
    $('result-eyebrow').textContent=t(stale?'staleLabel':'resultLabel');
    $('result-explanation').textContent=stale?`${t('staleExplanation')} ${explanation}`:explanation;
  }
  function showResult(result){
    if(!result || result.scope!=='server-host' || !Array.isArray(result.layers) || !Number.isFinite(new Date(result.observedAt).getTime())) {showError('invalidResult');return;}
    const state=resultState(result);const layers=result.layers;
    let key=state;
    if(state==='attention'){
      key=result.wifi?.available && result.wifi.status==='attention'?'wifi':(['gateway','internet','dns','service'].find(id=>layers.some(layer=>layer.id===id && layer.status==='attention'))||'unknown');
    }
    $('check-result').hidden=false;
    $('result-title').textContent=t(`${key}Title`);
    let explanation=t(`${key}Explanation`);
    if(state==='attention'&&layers.some(layer=>validStatus(layer.status)==='unknown'))explanation+=` ${t('partialNote')}`;
    resultPresentation={result,state,explanation,stale:null};
    refreshResultFreshness(true);$('result-next').textContent=t(`${key}Next`);
    $('result-time').textContent=`${t('observedAt')} ${formatTime(result.observedAt)}`;
    $('history-note').textContent=t(result.historySaved?'historySaved':'historyNotSaved');
    const container=$('layer-results');container.replaceChildren();
    ['gateway','internet','dns','service'].forEach(id=>{
      const layer=layers.find(value=>value.id===id);let status=validStatus(layer?.status);
      if(!Number.isFinite(layer?.attempts)||layer.attempts<=0)status='unknown';
      const card=document.createElement('div');card.className='layer-item';card.dataset.state=status;
      const name=document.createElement('div');name.className='layer-name';name.textContent=t(id);
      const flag=document.createElement('strong');flag.className='layer-status';flag.textContent=t(status);
      const metrics=document.createElement('p');metrics.className='layer-measure';
      const p95=Number.isFinite(layer?.p95Ms)&&layer.p95Ms>=0?`${Math.round(layer.p95Ms*10)/10} ms`:t('noValue');
      const counts=Number.isInteger(layer?.attempts)&&layer.attempts>0&&Number.isInteger(layer.failed)&&layer.failed>=0&&layer.failed<=layer.attempts?`${layer.failed} / ${layer.attempts}`:t('noValue');
      metrics.append(document.createTextNode(`${t('latency')}: ${p95}`),document.createElement('br'),document.createTextNode(`${t('failed')}: ${counts}`));
      card.append(name,flag,metrics);container.append(card);
    });
    const wifi=result.wifi;const available=wifi?.available===true;
    const wifiCard=document.createElement('div');wifiCard.className='layer-item wifi-item';wifiCard.dataset.state=available?validStatus(wifi.status):'unknown';
    const wifiName=document.createElement('div');wifiName.className='layer-name';wifiName.textContent=t('wifiDetail');
    const wifiFlag=document.createElement('strong');wifiFlag.className='layer-status';wifiFlag.textContent=available?t(validStatus(wifi.status)):t('wifiUnavailable');
    const wifiMetrics=document.createElement('p');wifiMetrics.className='layer-measure';
    const signal=Number.isFinite(wifi?.signalPct)&&wifi.signalPct>=0&&wifi.signalPct<=100?`${wifi.signalPct}%`:t('noValue');
    wifiMetrics.textContent=available?`${t('wifiSignal')}: ${signal}`:t('wifiUnavailableExplanation');
    wifiCard.append(wifiName,wifiFlag,wifiMetrics);container.append(wifiCard);
    window.RoomFlowHomeExtras?.onResult(result,job?.id);
  }
  function mappedError(code){
    if(/timeout|timed.?out/i.test(code||''))return 'timeout';
    if(/python|spawn|unavailable|enoent/i.test(code||''))return 'pythonUnavailable';
    if(/interrupt|cancel/i.test(code||''))return 'interrupted';
    if(/invalid|parse|result/i.test(code||''))return 'invalidResult';
    return 'requestFailed';
  }
  function showError(key){errorKey=key;resultPresentation=null;$('check-error').hidden=false;$('check-error-message').textContent=t(key);$('check-result').hidden=true;window.RoomFlowHomeExtras?.onError();}
  function renderJob(){
    const running=job?.status==='running'||startRequestPending;$('quick-check-start').disabled=running;$('check-progress').hidden=!running;
    $('quick-check-start').querySelector('span').textContent=t(running?'runningButton':job?.status==='complete'?'checkAgain':errorKey?'retry':'startCheck');
    if(running){$('check-error').hidden=true;$('check-result').hidden=true;renderProgress();}
    else if(job?.status==='complete'){errorKey='';$('check-error').hidden=true;showResult(job.result);}
    else if(job?.status==='failed'){showError(mappedError(job.errorCode));}
    else if(errorKey)showError(errorKey);
  }
  function renderProgress(){
    let seconds=checkingStartedAt?Math.max(0,Math.floor((Date.now()-checkingStartedAt)/1000)):0;
    $('check-progress-text').textContent=`${t('checking')}${seconds>0?` ${t('elapsed')} ${seconds} ${t('seconds')}`:''}`;
  }
  async function request(url,options={}){
    const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),10000);
    try{const response=await fetch(url,{...options,signal:controller.signal,cache:'no-store'});let value;try{value=await response.json();}catch{throw new Error('requestFailed');}if(!response.ok && !(response.status===409&&value?.job))throw new Error('requestFailed');return value;}
    finally{clearTimeout(timeout);}
  }
  function stopPolling(){clearTimeout(pollTimer);pollTimer=null;}
  function acceptJob(value){
    if(!value || !['running','complete','failed'].includes(value.status) || typeof value.id!=='string')throw new Error('invalidResult');
    stopPolling();
    job=value;errorKey='';checkingStartedAt=Number.isFinite(new Date(value.startedAt).getTime())?new Date(value.startedAt).getTime():Date.now();window.RoomFlowHomeExtras?.onJob(value);renderJob();
    if(job.status==='running')pollTimer=setTimeout(poll,900);
  }
  async function poll(){
    if(!job||job.status!=='running')return;
    try{const value=await request(`/api/quick-check/${encodeURIComponent(job.id)}`);acceptJob(value.job);}
    catch{stopPolling();job=null;errorKey='requestFailed';renderJob();}
  }
  async function startCheck(){
    userStartedCheck=true;
    if(job?.status==='running'||startRequestPending)return;startRequestPending=true;window.RoomFlowHomeExtras?.onStarting();stopPolling();errorKey='';$('check-error').hidden=true;$('check-result').hidden=true;$('quick-check-start').disabled=true;$('check-progress').hidden=false;checkingStartedAt=Date.now();renderProgress();$('quick-check-start').querySelector('span').textContent=t('runningButton');
    try{const value=await request('/api/quick-check',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});acceptJob(value.job);}
    catch{job=null;errorKey='requestFailed';renderJob();}
    finally{startRequestPending=false;renderJob();}
  }
  $('quick-check-start').addEventListener('click',startCheck);
  window.RoomFlowHomeExtras?.attach(startCheck);
  function translate(){
    document.documentElement.lang=language;document.title=t('title');$('home-language').value=language;
    storage.set('roomflow-language',language);
    document.querySelectorAll('[data-t]').forEach(element=>{element.textContent=t(element.dataset.t);});
    document.querySelector('.top-links').setAttribute('aria-label',language==='en'?'Main navigation':'主要導覽');
    renderPreference();renderJob();
    window.RoomFlowHomeExtras?.setLanguage(language);
  }
  $('home-language').addEventListener('change',()=>{language=$('home-language').value==='en'?'en':'zh-Hant';storage.set('roomflow.home.language',language);translate();});
  translate();
  setInterval(()=>{renderPreference();if(job?.status==='running')renderProgress();else if(job?.status==='complete')refreshResultFreshness();},1000);
  // Reading the current job only restores an existing check. It never starts probes.
  request('/api/quick-check').then(value=>{if(!userStartedCheck){if(value.job)acceptJob(value.job);else window.RoomFlowHomeExtras?.onNoJob();}}).catch(()=>{});
  window.addEventListener('beforeunload',stopPolling);
})();
