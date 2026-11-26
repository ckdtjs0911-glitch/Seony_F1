(async()=>{try{
 const $=id=>document.getElementById(id),bytes=Uint8Array.from(atob($('gap-payload').textContent),c=>c.charCodeAt(0));
 const data=JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text());
 const canvas=$('gap-canvas'),mapContext=canvas.getContext('2d');
 const circle=$('gap-circle'),circleContext=circle.getContext('2d'),seek=$('gap-seek');
 let c=mapContext,now=0,playing=true,last=0;
 const track=data.track||[],rawX=track.map(p=>p[0]),rawY=track.map(p=>p[1]);
 const rotate=Math.max(...rawY)-Math.min(...rawY)>Math.max(...rawX)-Math.min(...rawX),orient=r=>rotate?[r[1],-r[0]]:r;
 const extent=track.map(orient),xs=extent.map(p=>p[0]),ys=extent.map(p=>p[1]),minx=Math.min(...xs),miny=Math.min(...ys),width=Math.max(...xs)-minx||1,height=Math.max(...ys)-miny||1;
 const scale=Math.min(450/width,420/height),point=r=>{const p=orient(r);return [40+(450-width*scale)/2+(p[0]-minx)*scale,110+(420-height*scale)/2+(p[1]-miny)*scale];};
 const at=(rows,t,age=Infinity)=>{let l=0,h=rows.length;while(l<h){const m=(l+h)>>1;if(rows[m][0]<=t)l=m+1;else h=m;}const r=rows[l-1];return r&&t-r[0]<=age?{r,next:rows[l]}:null;};
 const label=(s,x,y,color='#edf4fc',size=17)=>{c.fillStyle=color;c.font=`${size}px system-ui`;c.fillText(s,x,y);};
 const gap=(r,leader)=>leader?'선두':typeof r?.[1]==='number'&&r[1]>=0?`+${r[1].toFixed(3)} s`:typeof r?.[1]==='string'?r[1]:'—';
 const eased=new Map(),easedX=new Map();
 const timing=JSON.parse($('gap-timing-data').textContent),table=$('gap-timing-body');
 const compounds={SOFT:'S',MEDIUM:'M',HARD:'H',INTERMEDIATE:'I',WET:'W'};
 const completedLaps=new Map(Object.entries(timing).map(([number,laps])=>[Number(number),laps.filter(r=>r[2]>0).map(r=>[r[0]+r[2]*1000,r]).sort((a,b)=>a[0]-b[0])]));
 let lastTable;
 function updateTiming(rows,elapsed){
  const t=Math.round(data.start*1000+elapsed);
  const current=rows.map(({d,pos,g})=>{
   const laps=timing[d.number]||[],lap=at(laps,t)?.r;
   const completed=at(completedLaps.get(d.number)||[],t)?.r[1];
   const pit=(d.pit_laps||[]).some(([start,end])=>start<=elapsed&&elapsed<=end);
   return {d:[d.name,d.color],pos,interval:gap(g,pos===1),lead:gap([0,g?.[2]],false),lap:lap?.[1],compound:compounds[lap?.[3]],completed,pit};
  });
  const signature=JSON.stringify(current);
  if(signature===lastTable)return;
  lastTable=signature;
  if(!current.length){
   const row=table.insertRow();
   const cell=row.insertCell();cell.colSpan=4;cell.textContent='타이밍 기록을 기다리는 구간입니다.';
   table.replaceChildren(row);return;
  }
  const fragment=document.createDocumentFragment();
  for(const row of current){
   const tr=document.createElement('tr');fragment.append(tr);
   const cell=(text)=>{const td=tr.insertCell();td.textContent=text;return td;};
   const detail=(td,text)=>{const small=document.createElement('small');small.textContent=text;td.append(small);};
   const driver=cell(`${row.pos} `);driver.className='gap-team';driver.style.borderColor=row.d[1];
   const name=document.createElement('span');name.className='gap-driver-name';name.textContent=row.d[0];name.style.color=row.d[1];driver.append(name);
   const interval=cell(row.interval);if(row.pos!==1&&row.lead!=='—')detail(interval,`선두 ${row.lead}`);
   const seconds=row.completed?.[2];
   const lapTime=cell(seconds>0?`${Math.floor(seconds/60)}:${(seconds%60).toFixed(3).padStart(6,'0')}`:'—');
   if(row.completed)detail(lapTime,`랩 ${row.completed[1]}`);
   const tyre=cell(row.compound||'—');if(row.lap)detail(tyre,`진행 랩 ${row.lap}${row.pit?' · PIT LAP':''}`);
  }
  table.replaceChildren(fragment);
 }
 function draw(){
  c=mapContext;
  c.clearRect(0,0,canvas.width,canvas.height);
  if(track.length){c.beginPath();track.forEach((r,i)=>{const p=point(r);i?c.lineTo(...p):c.moveTo(...p);});c.closePath();c.strokeStyle='#4c5b70';c.lineWidth=9;c.stroke();}
  const pitPaths=data.pit_reference?.segments||data.pit_tracks||[];
  for(const segment of pitPaths){c.beginPath();segment.forEach((r,i)=>{const p=point(r);i?c.lineTo(...p):c.moveTo(...p);});c.strokeStyle='#0b1321';c.lineWidth=7;c.stroke();c.strokeStyle='#38dfc8';c.lineWidth=3;c.setLineDash(data.pit_reference?[]:[6,4]);c.stroke();c.setLineDash([]);}
  label(pitPaths.length?'PIT LANE · 청록색 참고선':'PIT LANE · 분리 경로 미확인',30,575,'#38dfc8',17);
  const active=[];
  for(const d of data.drivers){
   const pos=at(d.positions,now*1000)?.r[1],g=at(d.gaps,now*1000,10000)?.r,loc=at(d.locations,now*1000,2000);
   if(loc){let r=loc.r.slice(1),next=loc.next;if(next&&next[0]-loc.r[0]<=2000){const f=(now*1000-loc.r[0])/(next[0]-loc.r[0]);r=r.map((v,i)=>v+(next[i+1]-v)*f);}const [x,y]=point(r);const pit=(d.pit_laps||[]).some(p=>p[0]<=now*1000&&now*1000<=p[1]);c.beginPath();c.arc(x,y,pit?7:5,0,Math.PI*2);c.fillStyle=pit?'#ffd65c':d.color;c.fill();label(d.name+(pit?' PIT LAP':''),x+7,y-6,pit?'#ffd65c':d.color,16);}
   if(pos)active.push({d,pos,g:pos===1?[now*1000,null,0]:g});
  }
  active.sort((a,b)=>a.pos-b.pos||a.d.number-b.d.number);
  updateTiming(active,now*1000);
  c=circleContext;
  c.clearRect(0,0,circle.width,circle.height);
  const withGap=active.filter(x=>x.g);
  const maxGap=Math.max(10,...withGap.map(x=>typeof x.g[2]==='number'?Math.max(0,x.g[2]):0));
  const cx=260,cy=292,radius=103;
  c.strokeStyle='#4c5b70';c.lineWidth=8;c.beginPath();c.arc(cx,cy,radius,0,Math.PI*2);c.stroke();
  c.textAlign='center';
  label('선두 기준 시간차',cx,cy-12,'#b7c9df',19);
  label(`0–${maxGap.toFixed(1)} s`,cx,cy+22,'#edf4fc',24);
  c.textAlign='left';
  const annotations=[],lapped=[];
  for(const {d,pos,g} of withGap){
   if(typeof g[2]!=='number'||g[2]<0){lapped.push(`${d.name} ${g[2]??'—'}`);continue;}
   const target=-Math.PI/2+Math.log1p(g[2])/Math.log1p(maxGap)*Math.PI*1.8;
   const angle=(easedX.get(d.number)??target)*.85+target*.15;easedX.set(d.number,angle);
   const x=cx+Math.cos(angle)*radius,y=cy+Math.sin(angle)*radius;
   c.beginPath();c.arc(x,y,6,0,Math.PI*2);c.fillStyle=d.color;c.fill();
   annotations.push({d,pos,g,x,y,right:x>=cx});
  }
  for(const right of [false,true]){
   const group=annotations.filter(a=>a.right===right).sort((a,b)=>a.y-b.y);let prev=32;
   for(const a of group){a.ly=Math.max(a.y,prev+23);prev=a.ly;}
   let bottom=545;for(const a of group.slice().reverse()){a.ly=Math.min(a.ly,bottom);bottom=a.ly-23;}
   for(const a of group){const key='label'+a.d.number;a.ly=(eased.get(key)??a.ly)*.8+a.ly*.2;eased.set(key,a.ly);const lx=right?375:145;
    c.strokeStyle=a.d.color;c.lineWidth=1;c.beginPath();c.moveTo(a.x,a.y);c.lineTo(lx,a.ly);c.stroke();
    const rank=`P${a.pos} `,name=a.d.name,interval=` ${gap(a.g,a.pos===1)}`;
    c.font='17px system-ui';
    const rankWidth=c.measureText(rank).width,nameWidth=c.measureText(name).width;
    const start=right?lx:lx-rankWidth-nameWidth-c.measureText(interval).width;
    label(rank,start,a.ly,'#edf4fc',17);
    label(name,start+rankWidth,a.ly,a.d.color,17);
    label(interval,start+rankWidth+nameWidth,a.ly,'#edf4fc',17);
   }
  }
  label('원형 눈금: 큰 시간차는 압축 · 실제 서킷 위치와 별개',18,572,'#b7c9df',16);
  if(lapped.length)label(lapped.join(' · ').slice(0,90),18,594,'#b7c9df',15);
  const clock=new Date((data.start+now)*1000).toISOString().slice(11,19);$('gap-clock').textContent=clock+' UTC';seek.value=Math.round(now/(data.end-data.start)*1000);canvas.dataset.time=now;
  $('gap-status').textContent=active.length?`같은 시각 위치·간격 기록 · ${clock} UTC`:'현재 시각의 위치·간격 기록을 기다리는 구간입니다.';
 }
 seek.oninput=()=>{now=Number(seek.value)/1000*(data.end-data.start);eased.clear();easedX.clear();draw();};
 $('gap-play').onclick=()=>{playing=!playing;$('gap-play').textContent=playing?'일시정지':'재생';};
 function tick(t){if(!canvas.isConnected)return;const dt=Math.min((t-last)/1000,.1);last=t;if(playing){now+=dt*Number($('gap-rate').value);if(now>data.end-data.start)now=0;draw();}requestAnimationFrame(tick);}
 draw();requestAnimationFrame(tick);
}catch(e){document.getElementById('gap-status').textContent='레이스 위치 재생을 불러오지 못했습니다.';console.error(e);}})();
