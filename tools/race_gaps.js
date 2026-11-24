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
  c.fillStyle='#0b1321';c.fillRect(0,0,1280,600);label('서킷 위치 · 시간별 재생',30,38,'#6deac9',24);label('가로 시간 간격 · 앞차와 간격(s)',540,38,'#6deac9',24);
  if(track.length){c.beginPath();track.forEach((r,i)=>{const p=point(r);i?c.lineTo(...p):c.moveTo(...p);});c.closePath();c.strokeStyle='#4c5b70';c.lineWidth=9;c.stroke();}
  const active=[];
  for(const d of data.drivers){
   const pos=at(d.positions,now*1000)?.r[1],g=at(d.gaps,now*1000,10000)?.r,loc=at(d.locations,now*1000,2000);
   if(loc){let r=loc.r.slice(1),next=loc.next;if(next&&next[0]-loc.r[0]<=2000){const f=(now*1000-loc.r[0])/(next[0]-loc.r[0]);r=r.map((v,i)=>v+(next[i+1]-v)*f);}const [x,y]=point(r);c.beginPath();c.arc(x,y,5,0,Math.PI*2);c.fillStyle=d.color;c.fill();label(d.name,x+7,y-6,d.color,12);}
   if(pos&&(g||pos===1))active.push({d,pos,g:pos===1?[now*1000,null,0]:g});
  }
  active.sort((a,b)=>a.pos-b.pos||a.d.number-b.d.number);
  const maxGap=Math.max(10,...active.map(x=>typeof x.g[2]==='number'?Math.max(0,x.g[2]):0));
  const left=565,right=1230,y0=125;
  c.strokeStyle='#65758c';c.lineWidth=3;c.beginPath();c.moveTo(left,y0);c.lineTo(right,y0);c.stroke();
  const ruler=v=>Math.log1p(v)/Math.log1p(maxGap);
  for(let i=0;i<=4;i++){const x=left+i/4*(right-left);label(`${Math.expm1(Math.log1p(maxGap)*i/4).toFixed(1)} s`,x-12,y0-16,'#b7c9df',13);}
  const annotations=[];
  active.forEach(({d,pos,g},i)=>{
   const numeric=typeof g[2]==='number'&&g[2]>=0;const targetX=numeric?left+ruler(g[2])*(right-left):right;
   const x=(easedX.get(d.number)??targetX)*.85+targetX*.15;easedX.set(d.number,x);
   const target=180+i*17.5,old=eased.get(d.number)??target,y=old+(target-old)*.15;eased.set(d.number,y);
   c.strokeStyle=d.color;c.lineWidth=1;c.beginPath();c.moveTo(x,y0);c.lineTo(x,y-8);c.lineTo(left,y-8);c.stroke();
   c.beginPath();c.arc(x,y0,5,0,Math.PI*2);c.fillStyle=d.color;c.fill();
   annotations.push({d,pos,g,y});
  });
  for(const {d,pos,g,y} of annotations){c.fillStyle='#0b1321';c.fillRect(left,y-14,280,18);label(`P${pos}  ${d.name}   ${gap(g,pos===1)}`,left+4,y,d.color,15);}
  label('가로 눈금: 큰 시간차를 압축해 표시',540,570,'#b7c9df',14);
  const clock=new Date((data.start+now)*1000).toISOString().slice(11,19);$('gap-clock').textContent=clock+' UTC';seek.value=Math.round(now/(data.end-data.start)*1000);canvas.dataset.time=now;
  $('gap-status').textContent=active.length?`같은 시각 위치·간격 기록 · ${clock} UTC`:'현재 시각의 위치·간격 기록을 기다리는 구간입니다.';
 }
 seek.oninput=()=>{now=Number(seek.value)/1000*(data.end-data.start);eased.clear();easedX.clear();draw();};
 $('gap-play').onclick=()=>{playing=!playing;$('gap-play').textContent=playing?'일시정지':'재생';};
 function tick(t){if(!canvas.isConnected)return;const dt=Math.min((t-last)/1000,.1);last=t;if(playing){now+=dt*Number($('gap-rate').value);if(now>data.end-data.start)now=0;draw();}requestAnimationFrame(tick);}
 draw();requestAnimationFrame(tick);
}catch(e){document.getElementById('gap-status').textContent='레이스 위치 재생을 불러오지 못했습니다.';console.error(e);}})();
