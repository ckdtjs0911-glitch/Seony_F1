(async()=>{
 'use strict';
 const el=id=>document.getElementById(id), status=el('replay-status');
 try {
  const bytes=Uint8Array.from(atob(el('replay-payload').textContent.trim()),c=>c.charCodeAt(0));
  const data=JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text());
  const a=el('replay-a'), b=el('replay-b'), lap=el('replay-lap'), rate=el('replay-rate'), seek=el('replay-seek'), button=el('replay-play');
  const canvas=el('replay-canvas'), c=canvas.getContext('2d');
  const drivers=data.drivers;
  let pair=[],start=0,end=0,now=0,playing=true,last=0,raf=0;
  const visible=new Map();
  for(const select of [a,b]) for(const d of drivers){
   const o=document.createElement('option');o.value=d.number;o.textContent=d.name+(d.rows.length?'':' (차량 데이터 없음)');select.add(o);
  }
  const available=drivers.filter(d=>d.rows.length);
  a.value=String((available.find(d=>d.number===3)||available[0]||drivers[0]).number);
  b.value=String((available.find(d=>d.number===1&&String(d.number)!==a.value)||available.find(d=>String(d.number)!==a.value)||drivers[1]||drivers[0]).number);
  function sample(d,t){
   const rows=d.rows;let lo=0,hi=rows.length;
   while(lo<hi){const m=(lo+hi)>>1;if(rows[m][0]<=t*1000)lo=m+1;else hi=m;}
   const r=rows[lo-1];return r&&t*1000-r[0]<=1000?r:null;
  }
  function text(s,x,y,color='#edf4fc',size=22){c.fillStyle=color;c.font=`${size}px system-ui`;c.fillText(s,x,y);}
  function draw(){
   c.fillStyle='#0b1321';c.fillRect(0,0,1280,720);
   text('SEONY F1 / 두 선수 차량 데이터 비교',36,40,'#6deac9',24);
   text(`랩 ${lap.value||'—'} · 같은 UTC 시각 · ${rate.value}배속`,36,77,'#b7c9df',20);
   if(end<=start){text('함께 비교할 수 있는 주행 구간이 없습니다.',36,160);return;}
   pair.forEach((d,j)=>{
    const x=36+j*624,r=sample(d,now);c.fillStyle='#152339';c.fillRect(x,100,600,112);
    text(`${j+1}. ${d.name}`,x+16,136,d.replayColor,26);
    if(r){
     let s=`${r[1]??'—'} km/h   기어 ${r[4]??'—'}`;
     if([10,12,14].includes(r[5]))s+='   DRS 작동';
     else if([0,1,8].includes(r[5]))s+='   DRS 꺼짐';
     text(s,x+16,182);
    }else text('차량 데이터 공백',x+16,182,'#b7c9df');
   });
   const left=220,right=1238,w=right-left;
   [[1,'속도 (km/h)',370],[2,'가속 페달 (%)',100],[3,'브레이크 사용',100]].forEach(([index,label,max],k)=>{
    const top=250+k*117,h=82;
    text(label,36,top+38,'#b7c9df',20);text(String(max),174,top+10,'#b7c9df',14);text('0',193,top+h,'#b7c9df',14);
    c.strokeStyle='#35465e';c.strokeRect(left,top,w,h);
    for(const [j,d] of pair.entries()){
     c.strokeStyle=d.replayColor;c.setLineDash(j?[8,4]:[]);c.lineWidth=2;c.beginPath();let previous=null;
     for(const r of visible.get(d.number)||[]){const t=r[0]/1000;
      if(r[index]==null){previous=null;continue;}
      const x=left+(t-start)/(end-start)*w,y=top+h-Math.max(0,Math.min(max,r[index]))/max*h;
      if(previous&&t-previous.t<=1){c.lineTo(x,previous.y);c.lineTo(x,y);}else c.moveTo(x,y);
      previous={t,y};
     }c.stroke();c.setLineDash([]);
     const r=sample(d,now);if(r&&r[index]!=null){const x=left+(now-start)/(end-start)*w,y=top+h-Math.max(0,Math.min(max,r[index]))/max*h;c.beginPath();c.arc(x,y,5,0,2*Math.PI);c.fillStyle=d.replayColor;c.fill();}
    }
    const x=left+(now-start)/(end-start)*w;c.beginPath();c.strokeStyle='white';c.lineWidth=1;c.moveTo(x,top);c.lineTo(x,top+h);c.stroke();
   });
   text('첫 번째 선수: 실선 · 두 번째 선수: 점선 · 브레이크: 0=해제 / 100=사용',36,660,'#b7c9df',20);
   const utc=new Date((data.start+now)*1000).toISOString().slice(11,23);
   text(`${utc} UTC`,36,697,'#6deac9',20);el('replay-clock').textContent=utc+' UTC';
   seek.value=String(Math.round((now-start)/(end-start)*1000));
   canvas.dataset.time=String(now);canvas.dataset.driverA=a.value;canvas.dataset.driverB=b.value;
  }
  function bounds(){
   const x=pair[0]?.laps.find(r=>String(r[0])===lap.value),y=pair[1]?.laps.find(r=>String(r[0])===lap.value);
   start=x&&y?Math.max(x[1],y[1]):0;end=x&&y?Math.min(x[1]+x[2],y[1]+y[2]):0;now=start;playing=end>start;button.textContent=playing?'일시정지':'재생';
   for(const d of pair)visible.set(d.number,d.rows.filter(r=>r[0]>=start*1000&&r[0]<=end*1000));
   status.textContent=playing?'선택한 두 선수의 실제 차량 데이터를 자동 재생 중입니다.':'공통 랩 또는 겹치는 주행 시각의 데이터가 없습니다.';draw();
  }
  function selection(){
   if(a.value===b.value){const other=drivers.find(d=>String(d.number)!==a.value);if(other)b.value=String(other.number);}
   pair=[drivers.find(d=>String(d.number)===a.value),drivers.find(d=>String(d.number)===b.value)];
   pair=pair.map((d,j)=>({...d,replayColor:j&&d.color===pair[0].color?'#6deac9':d.color}));
   const old=lap.value;lap.replaceChildren();
   const common=pair[0].laps.filter(x=>pair[1].laps.some(y=>x[0]===y[0]&&Math.min(x[1]+x[2],y[1]+y[2])>Math.max(x[1],y[1])));
   for(const x of common){const o=document.createElement('option');o.value=x[0];o.textContent=`${x[0]}랩`;lap.add(o);}
   if(common.some(x=>String(x[0])===old))lap.value=old;else if(common.length)lap.value=String(common[Math.max(0,common.length-2)][0]);
   if(!pair.every(d=>d.rows.length)){lap.replaceChildren();}
   bounds();
  }
  a.addEventListener('change',selection);b.addEventListener('change',selection);lap.addEventListener('change',bounds);
  seek.addEventListener('input',()=>{now=start+(end-start)*Number(seek.value)/1000;draw();});
  button.addEventListener('click',()=>{if(end<=start)return;playing=!playing;button.textContent=playing?'일시정지':'재생';});
  function tick(t){if(!canvas.isConnected)return;const delta=Math.min((t-last)/1000,.1);last=t;if(playing&&end>start){now+=delta*Number(rate.value);if(now>end)now=start;draw();}raf=requestAnimationFrame(tick);}
  selection();raf=requestAnimationFrame(tick);
 }catch(e){status.textContent='차량 비교 화면을 불러오지 못했습니다. 최신 브라우저에서 다시 열어 주세요.';console.error(e);}
})();
