(()=>{const root=document.currentScript.closest('.qualifying-replay');(async()=>{try{
 const $=s=>root.querySelector(s),bytes=Uint8Array.from(atob($('.q-payload').textContent),c=>c.charCodeAt(0));
 const data=JSON.parse(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text());
 const c=$('.q-canvas').getContext('2d'),canvas=c.canvas,track=data.track||[],rawX=track.map(p=>p[0]),rawY=track.map(p=>p[1]);
 const rotate=Math.max(...rawY)-Math.min(...rawY)>Math.max(...rawX)-Math.min(...rawX),orient=r=>rotate?[r[1],-r[0]]:r;
 const extent=track.map(orient),xs=extent.map(p=>p[0]),ys=extent.map(p=>p[1]),minx=Math.min(...xs),miny=Math.min(...ys),width=Math.max(...xs)-minx||1,height=Math.max(...ys)-miny||1;
 const scale=Math.min(470/width,450/height),point=r=>{const p=orient(r);return [35+(470-width*scale)/2+(p[0]-minx)*scale,110+(450-height*scale)/2+(p[1]-miny)*scale];};
 let phase,start,end,now,playing=true,last=0;
 const text=(s,x,y,color='#edf4fc',size=18)=>{c.fillStyle=color;c.font=`${size}px system-ui`;c.fillText(s,x,y);};
 for(const option of $('.q-phase').options)option.disabled=!data.phases.some(p=>p[0]===Number(option.value));
 const tyres={SOFT:['소프트','#ff7a83'],MEDIUM:['미디엄','#ffdb65'],HARD:['하드','#f2f5fa'],INTERMEDIATE:['인터미디어트','#64df9c'],WET:['웨트','#75b8ff']};
 const column={rank:560,driver:625,lap:835,gap:1020,tyre:1050};
 function right(s,x,y,color,size){c.textAlign='right';text(s,x,y,color,size);c.textAlign='left';}
 function draw(){
  const phaseName=data.label||`Q${phase}`;
  c.fillStyle='#0b1321';c.fillRect(0,0,1280,680);text(`${phaseName} · 서킷 위치`,30,40,'#6deac9',25);text(`${phaseName} · 현재까지 유효 최고 랩`,560,40,'#6deac9',25);
  if(track.length){c.beginPath();track.forEach((r,i)=>{const p=point(r);i?c.lineTo(...p):c.moveTo(...p);});c.closePath();c.strokeStyle='#4c5b70';c.lineWidth=8;c.stroke();}
  for(const path of data.pit_reference?.segments||[]){c.beginPath();path.forEach((r,i)=>{const p=point(r);i?c.lineTo(...p):c.moveTo(...p);});c.strokeStyle='#0b1321';c.lineWidth=7;c.stroke();c.strokeStyle='#38dfc8';c.lineWidth=3;c.stroke();}
  if(data.pit_reference)text('PIT LANE · 청록색 참고선',30,600,'#38dfc8',14);
  let count=0;
  for(const d of data.drivers){if(data.participants&&!data.participants[String(phase)]?.includes(d.number))continue;const rows=d.locations;let lo=0,hi=rows.length;while(lo<hi){const m=(lo+hi)>>1;if(rows[m][0]<=now*1000)lo=m+1;else hi=m;}
   const a=rows[lo-1],b=rows[lo];if(!a||now*1000-a[0]>2000||!track.length)continue;
   let r=a.slice(1);if(b&&b[0]-a[0]<=2000){const f=(now*1000-a[0])/(b[0]-a[0]);r=r.map((v,i)=>v+(b[i+1]-v)*f);}
   const [x,y]=point(r);c.beginPath();c.arc(x,y,5,0,Math.PI*2);c.fillStyle=d.color;c.fill();text(d.name,x+7,y-7,d.color,12);count++;
  }
  const best=new Map();for(const r of data.laps){if(r[1]!==phase||r[2]+r[3]>now)continue;const prev=best.get(r[0]);if(!prev||r[3]<prev[3])best.set(r[0],r);}
  const ranks=[...best.values()].sort((a,b)=>a[3]-b[3]);
  text('순위',column.rank,86,'#b7c9df',16);
  text('선수',column.driver,86,'#b7c9df',16);
  right('최고 랩',column.lap,86,'#b7c9df',16);
  right('1위와의 차이',column.gap,86,'#b7c9df',16);
  text('타이어',column.tyre,86,'#b7c9df',16);
  ranks.forEach((r,i)=>{
   const d=data.drivers.find(d=>d.number===r[0]),y=120+i*23;
   const ms=Math.round(r[3]*1000),min=Math.floor(ms/60000),sec=((ms%60000)/1000).toFixed(3).padStart(6,'0');
   text(`P${i+1}`,column.rank,y);
   text(d?.name||String(r[0]),column.driver,y,d?.color);
   right(`${min}:${sec}`,column.lap,y);
   right(i?`+${(r[3]-ranks[0][3]).toFixed(3)} s`:'기준 기록',column.gap,y,'#b7c9df');
   const tyre=tyres[r[5]];
   if(tyre){c.beginPath();c.arc(column.tyre+7,y-5,5,0,Math.PI*2);c.strokeStyle=tyre[1];c.lineWidth=2;c.stroke();}
   text(tyre?.[0]||'미확인',column.tyre+20,y,tyre?.[1]||'#b7c9df',16);
  });
  if(!ranks.length)text('아직 완료된 유효 랩이 없습니다.',560,130,'#b7c9df');
  $('.q-status').textContent=`${phaseName} · 위치 자료 표시 ${count}명 · 유효 랩 기록 ${ranks.length}명`;
  $('.q-clock').textContent=new Date((data.start+now)*1000).toISOString().slice(11,19)+' UTC';$('.q-seek').value=Math.round((now-start)/(end-start)*1000);canvas.dataset.phase=phase;canvas.dataset.time=now;
 }
 function choose(){phase=Number($('.q-phase').value);const window=data.phases.find(p=>p[0]===phase);if(!window)return;[ ,start,end]=window;now=start;playing=true;$('.q-play').textContent='일시정지';draw();}
 $('.q-phase').onchange=choose;$('.q-seek').oninput=()=>{now=start+Number($('.q-seek').value)/1000*(end-start);draw();};$('.q-play').onclick=()=>{playing=!playing;$('.q-play').textContent=playing?'일시정지':'재생';};
 function tick(t){if(!root.isConnected)return;const dt=Math.min((t-last)/1000,.1);last=t;if(playing){now+=dt*Number($('.q-rate').value);if(now>end)now=start;draw();}requestAnimationFrame(tick);}
 $('.q-phase').value=String(data.phases[0][0]);choose();requestAnimationFrame(tick);
}catch(e){root.querySelector('.q-status').textContent='서킷 위치 자료를 불러오지 못했습니다.';console.error(e);}})();})();
