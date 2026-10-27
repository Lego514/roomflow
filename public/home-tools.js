'use strict';
// Shared, side-effect-free comparison and export rules. Saved browser data is
// validated again; it never establishes router control or a physical identity.
((root)=>{
  const ids=['gateway','internet','dns','service'];
  const status=value=>['ok','attention','unknown'].includes(value);
  function cleanResult(value){
    if(!value||value.scope!=='server-host'||!Number.isFinite(Date.parse(value.observedAt))||!Array.isArray(value.layers)||!status(value.overall))return null;
    const layers=[];
    for(const id of ids){
      const matches=value.layers.filter(row=>row?.id===id);if(matches.length!==1)return null;const row=matches[0];
      if(!status(row.status)||!Number.isInteger(row.attempts)||row.attempts<0||row.attempts>1000||!Number.isInteger(row.failed)||row.failed<0||row.failed>row.attempts||!(row.p95Ms===null||Number.isFinite(row.p95Ms)&&row.p95Ms>=0&&row.p95Ms<=1e9))return null;
      if(row.status==='ok'&&(!row.attempts||row.failed||row.p95Ms===null))return null;
      if(!row.attempts&&(row.status!=='unknown'||row.p95Ms!==null))return null;
      if(row.failed===row.attempts&&row.p95Ms!==null)return null;
      layers.push({id,status:row.status,p95Ms:row.p95Ms,attempts:row.attempts,failed:row.failed});
    }
    let wifi=null;
    if(value.wifi){const w=value.wifi;if(typeof w.available!=='boolean'||!status(w.status)||!(w.signalPct===null||Number.isFinite(w.signalPct)&&w.signalPct>=0&&w.signalPct<=100)||!w.available&&(w.status!=='unknown'||w.signalPct!==null)||w.available&&w.status==='ok'&&w.signalPct===null)return null;wifi={available:w.available,status:w.status,signalPct:w.signalPct};}
    const states=[...layers.map(row=>row.status),...(wifi?.available?[wifi.status]:[])];
    if(value.overall!==(states.includes('attention')?'attention':states.includes('unknown')?'unknown':'ok'))return null;
    return {scope:'server-host',observedAt:value.observedAt,overall:value.overall,layers,wifi,historySaved:value.historySaved===true,p95Basis:'maximum-target-p95'};
  }
  function compare(before,after){
    const a=cleanResult(before),b=cleanResult(after);
    if(!a||!b)return {valid:false,reason:'invalid'};
    const gap=Date.parse(b.observedAt)-Date.parse(a.observedAt);
    if(gap<=0)return {valid:false,reason:'order'};
    if(gap>30*60000)return {valid:false,reason:'expired'};
    return {valid:true,beforeAt:a.observedAt,afterAt:b.observedAt,rows:ids.map(id=>{
      const x=a.layers.find(row=>row.id===id),y=b.layers.find(row=>row.id===id);
      const known=x.status!=='unknown'&&y.status!=='unknown';
      const beforeMs=known?x.p95Ms:null,afterMs=known?y.p95Ms:null;
      return {id,beforeMs,afterMs,deltaMs:beforeMs!==null&&afterMs!==null?afterMs-beforeMs:null,
        beforeFailed:x.failed,beforeAttempts:x.attempts,afterFailed:y.failed,afterAttempts:y.attempts};
    })};
  }
  const labels={ 'zh-Hant':{gateway:'到路由器',internet:'外部網路',dns:'網站名稱查詢',service:'常用服務'},en:{gateway:'To router',internet:'Internet',dns:'DNS',service:'Service TCP'}};
  function summary(value,{language='zh-Hant',condition=null,comparison=null}={}){
    const r=cleanResult(value);if(!r)return '';
    const en=language==='en',names=labels[en?'en':'zh-Hant'];
    const lines=[en?'RoomFlow connection observations':'RoomFlow 連線觀察摘要',`${en?'Observed at':'量測時間'}: ${r.observedAt}`,
      en?'Scope: computer running RoomFlow; router policy has not been applied.':'範圍：執行 RoomFlow 的電腦；未套用路由器優先權。'];
    for(const row of r.layers)lines.push(`${names[row.id]}: ${row.status}; p95 ${row.p95Ms===null?'—':row.p95Ms.toFixed(1)} ms; ${en?'unsuccessful':'探測未成功'} ${row.failed}/${row.attempts}`);
    lines.push(`Wi-Fi: ${r.wifi?.available?r.wifi.status:'unknown'}; ${en?'signal':'訊號'} ${r.wifi?.signalPct==null?'—':r.wifi.signalPct+'%'}`);
    if(condition)lines.push(`${en?'User-reported change':'使用者表示的調整'}: ${condition}`);
    if(comparison?.valid){lines.push(`${en?'Comparison baseline':'比較基準時間'}: ${comparison.beforeAt}`);for(const row of comparison.rows)lines.push(`${names[row.id]} p95: ${row.beforeMs??'—'} → ${row.afterMs??'—'} ms`);}
    lines.push(en?'p95 is the maximum target p95 from a small sample, not a pooled percentile.':'p95 是少量探測中最慢目標的 p95，不是合併樣本百分位。',
      en?'Before/after observations do not establish cause or actual game/call quality.':'前後觀察不能直接確定原因，也不代表實際遊戲／通話品質。');
    return lines.join('\n');
  }
  root.RoomFlowHomeTools={cleanResult,compare,summary};
})(typeof window!=='undefined'?window:globalThis);
