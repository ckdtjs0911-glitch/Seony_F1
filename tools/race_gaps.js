(async()=>{try{
 const $=id=>document.getElementById(id),bytes=Uint8Array.from(atob($('gap-payload').textContent),c=>c.charCodeAt(0));
 const data=JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text());
 const canvas=$('gap-canvas'),c=canvas.getContext('2d'),seek=$('gap-seek');let now=0,playing=true,last=0;
 const track=data.track||[],xs=track.map(p=>p[0]),ys=track.map(p=>p[1]);
 const minx=Math.min(...xs),miny=Math.min(...ys),scale=Math.min(450/(Math.max(...xs)-minx||1),420/(Math.max(...ys)-miny||1));
 const point=r=>[40+(r[0]-minx)*scale,110+(r[1]-miny)*scale];
 const at=(rows,t,age=Infinity)=>{let l=0,h=rows.length;while(l<h){const m=(l+h)>>1;if(rows[m][0]<=t)l=m+1;else h=m;}const r=rows[l-1];return r&&t-r[0]<=age?{r,next:rows[l]}:null;};
 const label=(s,x,y,color='#edf4fc',size=17)=>{c.fillStyle=color;c.font=`${size}px system-ui`;c.fillText(s,x,y);};
 const gap=(r,leader)=>leader?'선두':typeof r?.[1]==='number'&&r[1]>=0?`+${r[1].toFixed(3)} s`:typeof r?.[1]==='string'?r[1]:'—';
 const eased=new Map(),easedX=new Map();
 function draw(){
  c.fillStyle='#0b1321';c.fillRect(0,0,1280,600);label('서킷 위치 · 시간별 재생',30,38,'#6deac9',24);label('원형 시간 간격 · 앞차와 간격(s)',540,38,'#6deac9',24);
  if(track.length){c.beginPath();track.forEach((r,i)=>{const p=point(r);i?c.lineTo(...p):c.moveTo(...p);});c.closePath();c.strokeStyle='#4c5b70';c.lineWidth=9;c.stroke();}
  for(const segment of data.pit_tracks||[]){c.beginPath();segment.forEach((r,i)=>{const p=point(r);i?c.lineTo(...p):c.moveTo(...p);});c.strokeStyle='#ffd65c';c.lineWidth=4;c.setLineDash([6,4]);c.stroke();c.setLineDash([]);}
  label((data.pit_tracks||[]).length?'PIT LANE · 노란 점선 (위치 기반 추정)':'PIT LANE · 분리 경로 미확인',30,575,'#ffd65c',14);
  const active=[];
  for(const d of data.drivers){
   const pos=at(d.positions,now*1000)?.r[1],g=at(d.gaps,now*1000,10000)?.r,loc=at(d.locations,now*1000,2000);
   if(loc){let r=loc.r.slice(1),next=loc.next;if(next&&next[0]-loc.r[0]<=2000){const f=(now*1000-loc.r[0])/(next[0]-loc.r[0]);r=r.map((v,i)=>v+(next[i+1]-v)*f);}const [x,y]=point(r);const pit=(d.pit_laps||[]).some(p=>p[0]<=now*1000&&now*1000<=p[1]);c.beginPath();c.arc(x,y,pit?7:5,0,Math.PI*2);c.fillStyle=pit?'#ffd65c':d.color;c.fill();label(d.name+(pit?' PIT LAP':''),x+7,y-6,pit?'#ffd65c':d.color,12);}
   if(pos&&(g||pos===1))active.push({d,pos,g:pos===1?[now*1000,null,0]:g});
  }
  active.sort((a,b)=>a.pos-b.pos||a.d.number-b.d.number);
  const maxGap=Math.max(10,...active.map(x=>typeof x.g[2]==='number'?Math.max(0,x.g[2]):0));
  const cx=900,cy=305,radius=155;
  c.strokeStyle='#4c5b70';c.lineWidth=8;c.beginPath();c.arc(cx,cy,radius,0,Math.PI*2);c.stroke();
  label('선두 기준 시간차',cx-67,cy-12,'#b7c9df',16);label(`0–${maxGap.toFixed(1)} s`,cx-58,cy+22,'#edf4fc',21);
  const annotations=[],lapped=[];
  for(const {d,pos,g} of active){
   if(typeof g[2]!=='number'||g[2]<0){lapped.push(`${d.name} ${g[2]??'—'}`);continue;}
   const target=-Math.PI/2+Math.log1p(g[2])/Math.log1p(maxGap)*Math.PI*1.8;
   const angle=(easedX.get(d.number)??target)*.85+target*.15;easedX.set(d.number,angle);
   const x=cx+Math.cos(angle)*radius,y=cy+Math.sin(angle)*radius;
   c.beginPath();c.arc(x,y,6,0,Math.PI*2);c.fillStyle=d.color;c.fill();
   annotations.push({d,pos,g,x,y,right:x>=cx});
  }
  for(const right of [false,true]){
   const group=annotations.filter(a=>a.right===right).sort((a,b)=>a.y-b.y);let prev=80;
   for(const a of group){a.ly=Math.max(a.y,prev+20);prev=a.ly;}
   let bottom=530;for(const a of group.slice().reverse()){a.ly=Math.min(a.ly,bottom);bottom=a.ly-20;}
   for(const a of group){const key='label'+a.d.number;a.ly=(eased.get(key)??a.ly)*.8+a.ly*.2;eased.set(key,a.ly);const lx=right?1085:715;
    c.strokeStyle=a.d.color;c.lineWidth=1;c.beginPath();c.moveTo(a.x,a.y);c.lineTo(lx,a.ly);c.stroke();
    c.textAlign=right?'left':'right';label(`P${a.pos} ${a.d.name} ${gap(a.g,a.pos===1)}`,lx,a.ly,a.d.color,14);c.textAlign='left';
   }
  }
  label('원형 눈금: 큰 시간차는 압축 · 실제 서킷 위치와 별개',540,570,'#b7c9df',13);
  if(lapped.length)label(lapped.join(' · ').slice(0,90),540,590,'#b7c9df',12);
  const clock=new Date((data.start+now)*1000).toISOString().slice(11,19);$('gap-clock').textContent=clock+' UTC';seek.value=Math.round(now/(data.end-data.start)*1000);canvas.dataset.time=now;
  $('gap-status').textContent=active.length?`같은 시각 위치·간격 기록 · ${clock} UTC`:'현재 시각의 위치·간격 기록을 기다리는 구간입니다.';
 }
 seek.oninput=()=>{now=Number(seek.value)/1000*(data.end-data.start);eased.clear();easedX.clear();draw();};
 $('gap-play').onclick=()=>{playing=!playing;$('gap-play').textContent=playing?'일시정지':'재생';};
 function tick(t){if(!canvas.isConnected)return;const dt=Math.min((t-last)/1000,.1);last=t;if(playing){now+=dt*Number($('gap-rate').value);if(now>data.end-data.start)now=0;draw();}requestAnimationFrame(tick);}
 draw();requestAnimationFrame(tick);
}catch(e){document.getElementById('gap-status').textContent='레이스 위치 재생을 불러오지 못했습니다.';console.error(e);}})();
