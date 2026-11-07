const rows = REPORT_ROWS;
const sessionNames = ['프랙티스 1','프랙티스 2','프랙티스 3','퀄리파잉','레이스'];
const tablist = document.getElementById('session-tabs');
const driverSelect = document.getElementById('chart-driver');
const tooltip = document.getElementById('chart-tooltip');
const metrics = [['time','랩타임','#6deac9'],['s1','섹터 1','#83b7ff'],['s2','섹터 2','#c6a0ff'],['s3','섹터 3','#ffce80']];
let activeSession = sessionNames.find(s => rows.some(r => r.session === s)) || sessionNames[0];
const tyres = {
  HARD: ['H','하드','#ffffff'], MEDIUM: ['M','미디엄','#ffe34d'], SOFT: ['S','소프트','#ff4f5e'],
  INTERMEDIATE: ['I','인터미디어트','#52d983'], WET: ['W','웨트','#58a6ff'],
  UNKNOWN: ['?','미확인','#9aaabd']
};
function tyreInfo(lap){return tyres[lap.tyre] || tyres.UNKNOWN;}
const legend=document.createElement('div');legend.className='tyre-legend';legend.setAttribute('aria-label','사용 타이어 범례');
for(const [code,label,color] of Object.values(tyres)){const badge=document.createElement('span');badge.style.setProperty('--tyre',color);badge.textContent=code+' · '+label;legend.append(badge);}
document.getElementById('chart-summary').after(legend);
function precise(value, key) {
  if (!Number.isFinite(value)) return '기록 없음';
  return key === 'time' ? `${Math.floor(value/60)}:${(value%60).toFixed(3).padStart(6,'0')} (${value.toFixed(3)}초)` : `${value.toFixed(3)}초`;
}
function hideTooltip(){tooltip.hidden=true;}
function showTooltip(event, lap, metric, row) {
  const [key,label] = metric;
  tooltip.replaceChildren();
  const title=document.createElement('strong'); title.textContent=`${row.session} · #${row.number} ${row.name}`;
  const value=document.createElement('div'); value.textContent=`L${lap.lap} · ${label} ${precise(lap[key],key)}`;
  tooltip.append(title,value);
  const [code,compound,tireColor]=tyreInfo(lap);
  const tyre=document.createElement('div');tyre.className='tooltip-tyre';
  const badge=document.createElement('span');badge.style.background=tireColor;badge.className='tyre-swatch';
  tyre.append(badge,document.createTextNode(`타이어 ${code} · ${compound}`));tooltip.append(tyre);
  if(lap.deleted){const note=document.createElement('div');note.textContent='삭제 확인 랩';tooltip.append(note);}
  tooltip.hidden=false;
  const box=event.currentTarget.getBoundingClientRect();
  const pointer=Number.isFinite(event.clientX);
  const px=pointer?event.clientX:box.left+box.width/2, py=pointer?event.clientY:box.top;
  tooltip.style.left=Math.max(8,Math.min(px+14,window.innerWidth-tooltip.offsetWidth-12))+'px';
  tooltip.style.top=Math.max(8,Math.min(py+14,window.innerHeight-tooltip.offsetHeight-12))+'px';
}
function renderChart(svg, row, metric) {
  const [key,label,color]=metric;
  svg.replaceChildren();
  const ns='http://www.w3.org/2000/svg';
  function el(tag,attrs={},text){const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;svg.append(n);return n;}
  const points=row ? row.laps.filter(l=>Number.isFinite(l[key])&&l[key]>0) : [];
  if(!points.length){el('text',{x:550,y:150,fill:'#b7c9df','text-anchor':'middle'},`${label} · 데이터 대기 / 기록 없음`);return;}
  const low=Math.floor(Math.min(...points.map(p=>p[key]))-1),high=Math.ceil(Math.max(...points.map(p=>p[key]))+1);
  const max=Math.max(2,...row.laps.map(p=>p.lap)),X=l=>80+(l-1)/(max-1)*975,Y=t=>265-(t-low)/(high-low)*230;
  for(let i=0;i<6;i++){const value=low+(high-low)*i/5,y=Y(value);el('line',{x1:80,x2:1055,y1:y,y2:y,stroke:'#30435d'});el('text',{x:68,y:y+4,fill:'#adbed3','text-anchor':'end','font-size':13},value.toFixed(1)+'s');}
  const step=Math.max(1,Math.ceil(max/12));
  for(let l=1;l<=max;l+=step)el('text',{x:X(l),y:295,fill:'#adbed3','text-anchor':'middle','font-size':13},'L'+l);
  let prev=null;
  for(const p of row.laps){if(!Number.isFinite(p[key])||p[key]<=0){prev=null;continue;}if(prev&&p.lap===prev.lap+1)el('line',{x1:X(prev.lap),x2:X(p.lap),y1:Y(prev[key]),y2:Y(p[key]),stroke:color,'stroke-width':1.6});prev=p;}
  for(const p of points){const hit=el('circle',{cx:X(p.lap),cy:Y(p[key]),r:10,fill:'transparent',tabindex:0,role:'button','aria-label':`L${p.lap} ${label} ${precise(p[key],key)} 타이어 ${tyreInfo(p)[0]} ${tyreInfo(p)[1]}`});
    const dot=el('circle',{cx:X(p.lap),cy:Y(p[key]),r:4.5,fill:tyreInfo(p)[2],stroke:p.deleted?'#ff7474':'#152339','stroke-width':p.deleted?2.5:1,'pointer-events':'none'});
    const title=document.createElementNS(ns,'title');title.textContent=`L${p.lap}: ${precise(p[key],key)} · ${tyreInfo(p)[0]} ${tyreInfo(p)[1]}`;hit.append(title);
    ['pointerenter','pointermove','click','focus'].forEach(type=>hit.addEventListener(type,e=>showTooltip(e,p,metric,row)));
    hit.addEventListener('pointerleave',hideTooltip);hit.addEventListener('blur',hideTooltip);
    hit.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showTooltip(e,p,metric,row);}if(e.key==='Escape')hideTooltip();});
  }
}
function draw(){hideTooltip();const row=rows.find(r=>r.session===activeSession&&r.number===+driverSelect.value);
  metrics.forEach(metric=>renderChart(document.getElementById('chart-'+metric[0]),row,metric));
  document.getElementById('chart-summary').textContent=row?`${activeSession} · #${row.number} ${row.name} · ${row.records}개 랩 기록`:`${activeSession} · 수집된 세션 데이터가 없습니다.`;
}
function selectSession(name){const previous=driverSelect.value;activeSession=name;
  document.querySelectorAll('#session-tabs button').forEach(b=>{b.setAttribute('aria-selected',String(b.textContent===name));b.tabIndex=b.textContent===name?0:-1;});
  driverSelect.replaceChildren();rows.filter(r=>r.session===name).forEach(r=>{const o=document.createElement('option');o.value=r.number;o.textContent=`#${r.number} ${r.name}`;driverSelect.append(o);});
  if([...driverSelect.options].some(o=>o.value===previous))driverSelect.value=previous;
  driverSelect.disabled=!driverSelect.options.length;draw();
}
for(const name of sessionNames){const b=document.createElement('button');b.type='button';b.setAttribute('role','tab');b.textContent=name;b.setAttribute('aria-controls','chart-panel');b.addEventListener('click',()=>selectSession(name));b.addEventListener('keydown',e=>{if(!['ArrowRight','ArrowLeft','Home','End'].includes(e.key))return;e.preventDefault();let i=sessionNames.indexOf(activeSession);const n=sessionNames.length;i=e.key==='Home'?0:e.key==='End'?n-1:(i+(e.key==='ArrowRight'?1:n-1))%n;selectSession(sessionNames[i]);tablist.children[i].focus();});tablist.append(b);}
const pagers=[...document.querySelectorAll('.result-table')].map((container,index)=>{
  const all=[...container.querySelectorAll('tbody tr[data-search]')];
  const nav=document.createElement('nav');nav.className='table-pagination';nav.setAttribute('aria-label',`결과표 ${index+1} 페이지`);container.after(nav);
  let page=0;
  function render(reset=false){if(reset)page=0;const query=(document.getElementById('search')?.value||'').trim().toLowerCase();const filtered=all.filter(r=>r.dataset.search.includes(query));const count=Math.max(1,Math.ceil(filtered.length/10));page=Math.min(page,count-1);all.forEach(r=>r.hidden=true);filtered.slice(page*10,(page+1)*10).forEach(r=>r.hidden=false);nav.replaceChildren();
    function button(label,target,disabled=false){const b=document.createElement('button');b.type='button';b.textContent=label;b.disabled=disabled;b.addEventListener('click',()=>{page=target;render();});nav.append(b);return b;}
    button('이전',page-1,page===0);
    for(let i=0;i<count;i++){const start=i*10+1,end=Math.min((i+1)*10,filtered.length);const b=button(filtered.length?`${start}–${end}`:'0명',i,!filtered.length);if(i===page)b.setAttribute('aria-current','page');}
    button('다음',page+1,page===count-1);
    const status=document.createElement('span');status.setAttribute('aria-live','polite');status.textContent=filtered.length?`전체 ${filtered.length}명 중 ${page*10+1}–${Math.min((page+1)*10,filtered.length)}명`:'검색 결과 없음';nav.append(status);
  }
  render();return ()=>render(true);
});
const search=document.getElementById('search');if(search)search.oninput=()=>pagers.forEach(reset=>reset());

driverSelect.onchange=draw;window.addEventListener('wheel',hideTooltip,{passive:true});window.addEventListener('touchmove',hideTooltip,{passive:true});window.addEventListener('resize',hideTooltip);document.addEventListener('keydown',e=>{if(e.key==='Escape')hideTooltip();});selectSession(activeSession);
