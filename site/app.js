import {LiveAdapter} from "./live-adapter.js";
// Scenario geometry is adapted from ROS2Drive/src/scenario at 2026-09-30.
// Mock kinematics only: no ROS connection, collision avoidance or controller evaluation.
const $ = id => document.getElementById(id);
const route = points => points.map(([x,y]) => ({x,y}));
const mining = route([[-42,-22],[-38,-20],[-34,-18],[-30,-16],[-24,-13],[-16,-10],[-8,-7],[0,-3],[8,2],[16,8],[19,11],[20,15],[18,19],[14,22],[9,24]]);
const port = route([[-28,-14],[-22,-14],[-16,-14],[-10,-14],[-8.5,-13.7],[-7.3,-12.8],[-6.5,-11.5],[-6,-9],[-6,-5],[-5.6,-3],[-4.5,-1.3],[-3,0],[0,1],[4,2],[8,3.5],[11,5.5],[14,7],[14.8,8],[15,9.5],[14.5,11],[13,12],[11,12],[9.5,11.5],[8.5,10],[8,8],[8,5],[8,2],[8,-2],[7.5,-4],[6,-5.5],[4,-6],[0,-6],[-4,-7],[-8,-9],[-11,-11],[-14,-14],[-16,-17],[-20,-18],[-28,-18]]);
const farm=[];
for(let row=0;row<6;row++){
  const y=-12.5+row*5, right=row%2===0;
  farm.push(...route(right?[[-18,y],[0,y],[18,y]]:[[18,y],[0,y],[-18,y]]));
  if(row<5) farm.push(...route(right?[[20,y+.73],[20.5,y+2.5],[20,y+4.27],[18,y+5]]:[[-20,y+.73],[-20.5,y+2.5],[-20,y+4.27],[-18,y+5]]));
}
farm.push(...route([[-16,13],[-8,15],[0,15]]));
const ring=Array.from({length:161},(_,i)=>({x:24.5*Math.cos(i/160*Math.PI*2),y:24.5*Math.sin(i/160*Math.PI*2)}));
export const scenes={
 mining_haul:{name:'矿区运输',profile:'MiningHaul',route:mining,speed:1.5,load:3,dump:9,stages:['TRANSIT','LOAD','HAUL','DUMP','RETURN','PARK'],note:'运输起点 → 装载区 → 卸载区 → 停车区。限速 1.5 m/s；装卸各停留 3 秒（演示时间）。路线高程不参与本页二维运动。',file:'mining_haul_scenario.cpp'},
 port_transport:{name:'港口运输',profile:'PortTransport',route:port,speed:1.2,load:3,dump:16,stages:['TRANSIT','LOAD','HAUL','DUMP','RETURN','PARK'],note:'堆场 → 闸口 → 岸桥 → 回场通道 → 停车区。限速 1.2 m/s；采用车端参考路线，未模拟交叉口调度或吊机联动。',file:'port_transport_scenario.cpp'},
 agriculture_route:{name:'农业作业',profile:'AgricultureRoute',route:farm,speed:1,stages:['TRANSIT','COVERAGE','PARK'],note:'六条作业行、5 m 行距、交替方向与地头掉头。限速 1.0 m/s；本页演示场景参考路线，未调用车端 CoveragePathPlanner。',file:'agriculture_route_scenario.cpp'},
 ring_demo:{name:'环道教学',profile:'RingDemo',route:ring,speed:2,closed:true,stages:['FOLLOW_ROUTE'],note:'半径 24.5 m 的内侧车道循环任务。标出车端三个基准障碍物位置；动画仅沿参考线运动，不模拟避障。演示限速 2.0 m/s。',file:'ring_scenario.cpp'}
};
for(const s of Object.values(scenes)){
 s.distances=[0];for(let i=1;i<s.route.length;i++)s.distances.push(s.distances[i-1]+Math.hypot(s.route[i].x-s.route[i-1].x,s.route[i].y-s.route[i-1].y));
 s.length=s.distances.at(-1);
}
export function poseAt(scene,distance){
 const d=Math.max(0,Math.min(distance,scene.length));let i=1;
 while(i<scene.route.length-1&&scene.distances[i]<d)i++;
 const a=scene.route[i-1],b=scene.route[i],len=scene.distances[i]-scene.distances[i-1],t=len?(d-scene.distances[i-1])/len:0;
 return {x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t,yaw:Math.atan2(b.y-a.y,b.x-a.x)};
}
export class MockAdapter{
 constructor(onEvent=()=>{}){this.onEvent=onEvent;this.sequence=0;this.completed=0;this.changeScene('mining_haul');}
 changeScene(id){if(!scenes[id])throw Error('Unknown scenario');this.sceneId=id;this.vehicles=Array.from({length:3},(_,i)=>({id:`CAR-0${i+1}`,state:'READY',mission:'IDLE',distance:0,hold:0,stage:scenes[id].stages[0],payload:'EMPTY',loadDone:false,dumpDone:false,missionId:null}));this.onEvent('SYSTEM','SCENARIO',`切换 ${scenes[id].name}，重置模拟车辆`);}
 dispatch(id){const v=this.vehicle(id);if(v.state==='ESTOP')return '请先复位模拟急停';if(['ACTIVE','PAUSED'].includes(v.mission))return '车辆已有任务，请先完成或取消';Object.assign(v,{state:'RUNNING',mission:'ACTIVE',distance:0,hold:0,stage:this.scene.stages[0],payload:'EMPTY',loadDone:false,dumpDone:false,missionId:`demo-${this.sceneId}-${++this.sequence}`});this.onEvent(id,'ACCEPTED',`任务 ${v.missionId} 已接受 · FollowRoute`);return '模拟车端已接受任务';}
 pause(id){const v=this.vehicle(id);if(v.state==='ESTOP')return '急停状态无法恢复任务';if(v.mission==='ACTIVE'){v.mission='PAUSED';v.state='PAUSED';this.onEvent(id,'PAUSED','任务暂停');return '任务已暂停';}if(v.mission==='PAUSED'){v.mission='ACTIVE';v.state='RUNNING';this.onEvent(id,'RESUMED','任务恢复');return '任务已恢复';}return '当前无可暂停任务';}
 cancel(id){const v=this.vehicle(id);if(!['ACTIVE','PAUSED'].includes(v.mission))return '当前无可取消任务';v.mission='CANCELED';v.hold=0;if(v.state!=='ESTOP')v.state='READY';this.onEvent(id,'CANCELED','任务已取消');return '任务已取消';}
 estop(id){const v=this.vehicle(id);if(v.state==='ESTOP'){v.state=v.mission==='PAUSED'?'PAUSED':'READY';this.onEvent(id,'RECOVERY','模拟急停复位，任务仍需手动恢复');return '急停已复位，请手动恢复任务';}v.state='ESTOP';if(v.mission==='ACTIVE')v.mission='PAUSED';this.onEvent(id,'ESTOP','模拟软件急停 · 控制速度归零');return '模拟急停已锁存';}
 vehicle(id){const v=this.vehicles.find(v=>v.id===id);if(!v)throw Error('Unknown vehicle');return v;}
 get scene(){return scenes[this.sceneId];}
 tick(dt){for(const v of this.vehicles){if(v.mission!=='ACTIVE'||v.state!=='RUNNING')continue;const s=this.scene;
  if(v.hold>0){v.hold=Math.max(0,v.hold-dt);if(v.hold===0){v.stage=v.loadDone&&!v.dumpDone?'HAUL':'RETURN';v.payload=v.dumpDone?'EMPTY':'LOADED';this.onEvent(v.id,'STAGE',`${v.stage} · ${v.payload}`);}continue;}
  let next=v.distance+s.speed*dt;
  const stop=(index,key,phase)=>{if(index===undefined||v[key]||next<s.distances[index])return false;v.distance=s.distances[index];v[key]=true;v.hold=3;v.stage=phase;this.onEvent(v.id,'STAGE',`${phase} · 停留 3 秒`);return true;};
  if(stop(s.load,'loadDone','LOAD')||stop(s.dump,'dumpDone','DUMP'))continue;
  if(next>=s.length){if(s.closed){v.distance=next%s.length;this.onEvent(v.id,'LAP','完成一圈，循环任务继续');}else{v.distance=s.length;v.stage='PARK';v.mission='SUCCEEDED';v.state='READY';this.completed++;this.onEvent(v.id,'SUCCEEDED','到达停车区，任务完成');}}else{v.distance=next;if(this.sceneId==='agriculture_route')v.stage='COVERAGE';}
 }}
 snapshot(){return{sceneId:this.sceneId,completed:this.completed,vehicles:this.vehicles.map(v=>({...v,...poseAt(this.scene,v.distance),speed:v.state==='RUNNING'&&v.mission==='ACTIVE'&&!v.hold?this.scene.speed:0,progress:v.distance/this.scene.length*100,updatedAt:Date.now()}))};}
}
// Mock and live adapters share operations and the snapshot contract.
// Browser MQTT/ROS integration and credentials are deliberately absent.
if(typeof document!=='undefined'){
 let selected='CAR-01',logs=[],mapProject;
 let adapter=new MockAdapter(log);
 let liveMode=false;
 function log(id,type,message){logs.unshift({time:new Date().toLocaleTimeString('zh-CN',{hour12:false}),id,type,message});logs=logs.slice(0,80);renderLogs();}
 function renderLogs(){if(!$('logs'))return;$('logs').replaceChildren(...logs.map(l=>{const tr=document.createElement('tr');for(const value of [l.time,l.id,l.type,l.message]){const td=document.createElement('td');td.textContent=value;tr.append(td);}return tr;}));}
 function svg(tag,attrs,parent,text){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text)e.textContent=text;parent.append(e);return e;}
 function buildMap(){const s=adapter.scene,points=s.route;
  const minX=Math.min(...points.map(p=>p.x)),maxX=Math.max(...points.map(p=>p.x)),minY=Math.min(...points.map(p=>p.y)),maxY=Math.max(...points.map(p=>p.y));
  const scale=Math.min(570/(maxX-minX||1),320/(maxY-minY||1)),cx=(minX+maxX)/2,cy=(minY+maxY)/2;
  mapProject=p=>({x:380+(p.x-cx)*scale,y:255-(p.y-cy)*scale});
  for(const id of ['terrain','roads','stations','vehicles'])$(id).replaceChildren();
  const d=points.map((p,i)=>{const q=mapProject(p);return `${i?'L':'M'}${q.x.toFixed(2)},${q.y.toFixed(2)}`;}).join(' ');
  if(adapter.sceneId==='agriculture_route'){const a=mapProject({x:-18,y:12.5}),b=mapProject({x:18,y:-12.5});svg('rect',{x:a.x,y:a.y,width:b.x-a.x,height:b.y-a.y,rx:8,fill:'#17372e',stroke:'#315c48'},$('terrain'));}
  svg('path',{d,fill:'none',stroke:'#243f53','stroke-width':26,'stroke-linejoin':'round','stroke-linecap':'round'},$('roads'));
  svg('path',{d,fill:'none',stroke:'#64849b','stroke-width':1.5,'stroke-dasharray':'5 6'},$('roads'));
  svg('path',{d,fill:'none',stroke:'#5be3b1','stroke-width':2,opacity:.7},$('roads'));
  const marks=s.closed?[[0,'循环起点']]:[[0,'起点'],...(s.load!==undefined?[[s.load,adapter.sceneId==='port_transport'?'堆场 / LOAD':'装载区 / LOAD'],[s.dump,adapter.sceneId==='port_transport'?'岸桥 / DUMP':'卸载区 / DUMP']]:[]),[points.length-1,'停车区 / PARK']];
  for(const [i,label] of marks){const p=mapProject(points[i]);svg('circle',{cx:p.x,cy:p.y,r:5,fill:'#ffcb75',stroke:'#111f2e','stroke-width':2},$('stations'));svg('text',{x:p.x+10,y:p.y-12,class:'station-label'},$('stations'),label);}
  if(s.closed)for(const a of [.85,3,5.15]){const p=mapProject({x:24.5*Math.cos(a),y:24.5*Math.sin(a)});svg('rect',{x:p.x-5,y:p.y-5,width:10,height:10,rx:2,fill:'#ffcb75'},$('stations'));}
  svg('text',{x:24,y:485,class:'map-text'},$('terrain'),`${s.profile} / FollowRoute`);
  $('sceneTitle').textContent=s.name;$('sceneId').textContent=adapter.sceneId;$('mapCaption').textContent=`${s.name} · 参考路线`;$('sceneNote').textContent=s.note;$('source').href=`https://github.com/frankwang98/ROS2Drive/blob/main/src/scenario/${s.file}`;
  $('fleet').replaceChildren(...adapter.vehicles.map(v=>{const b=document.createElement('button');b.className='vehicle';b.id=`fleet-${v.id}`;b.innerHTML=`<span class="vehicle-top"><b></b><span class="vehicle-status"></span></span><small></small>`;b.querySelector('b').textContent=v.id;b.onclick=()=>{selected=v.id;$('feedback').textContent=liveMode?'操作将发送到所连接车辆。':'操作仅作用于模拟车辆。';render();};return b;}));
  for(const v of adapter.vehicles){const g=svg('g',{id:`map-${v.id}`},$('vehicles'));svg('circle',{r:17,fill:'#5be3b1',opacity:.12},g);svg('g',{class:'car-body'},g);svg('text',{x:14,y:-15,class:'vehicle-label'},g,v.id);}
 }
 function render(){const snap=adapter.snapshot(),v=snap.vehicles.find(v=>v.id===selected);
  $('clock').textContent=new Date().toLocaleTimeString('zh-CN',{hour12:false});$('active').textContent=String(snap.vehicles.filter(v=>v.mission==='ACTIVE').length).padStart(2,'0');$('completed').textContent=String(snap.completed).padStart(2,'0');$('faults').textContent=String(snap.vehicles.filter(v=>v.state==='ESTOP').length).padStart(2,'0');
  for(const car of snap.vehicles){const b=$(`fleet-${car.id}`);b.classList.toggle('selected',car.id===selected);b.setAttribute('aria-pressed',car.id===selected);b.querySelector('.vehicle-status').textContent=car.state;b.querySelector('.vehicle-status').classList.toggle('fault',car.state==='ESTOP');b.querySelector('small').textContent=`${car.mission} · ${Number.isFinite(car.speed)?car.speed.toFixed(1):'—'} m/s`;
   const p=mapProject(car),g=$(`map-${car.id}`),color=car.state==='ESTOP'?'#ff9292':car.id===selected?'#5be3b1':'#7faeff';
   // Initial co-located cars get a small screen offset; telemetry remains unmodified.
   const offset=car.distance===0?(Number(car.id.at(-1))-1)*13:0;
   g.style.display=car.poseValid===false?'none':'';
   g.setAttribute('transform',`translate(${p.x},${p.y+offset})`);const body=g.querySelector('.car-body');body.replaceChildren();body.setAttribute('transform',`rotate(${-car.yaw*180/Math.PI})`);svg('rect',{x:-10,y:-5,width:20,height:10,rx:3,fill:color,stroke:'#0b1521','stroke-width':2},body);svg('path',{d:'M3 -3 L7 0 L3 3',fill:'none',stroke:'#12352d','stroke-width':1.5},body);
  }
  $('vehicleTitle').textContent=v.id;$('runtime').textContent=v.state;$('speed').textContent=Number.isFinite(v.speed)?v.speed.toFixed(1):'—';$('position').textContent=v.poseValid===false?'—':`${v.x.toFixed(1)} / ${v.y.toFixed(1)} m`;$('heading').textContent=v.poseValid===false?'—':`${(v.yaw*180/Math.PI).toFixed(1)}°`;$('payload').textContent=v.payload;$('missionState').textContent=v.mission;$('missionName').textContent=`${adapter.scene.name} · FollowRoute`;$('phase').textContent=v.stage;$('percent').textContent=`${Math.floor(v.progress)}%`;$('progress').value=v.progress;$('missionId').textContent=v.missionId||'尚未下发任务';
  $('stages').replaceChildren(...adapter.scene.stages.map(t=>{const e=document.createElement('span');e.textContent=t;e.className=t===v.stage?'current':'';return e;}));
  $('dispatch').disabled=['ACTIVE','PAUSED'].includes(v.mission)||v.state==='ESTOP';$('pause').disabled=!['ACTIVE','PAUSED'].includes(v.mission)||v.state==='ESTOP';$('pause').textContent=v.mission==='PAUSED'?'恢复':'暂停';$('cancel').disabled=!['ACTIVE','PAUSED'].includes(v.mission);$('estop').textContent=v.state==='ESTOP'?(liveMode?'清除急停请求':'复位急停'):(liveMode?'请求软件急停':'模拟急停');
  $('connectionState').textContent=liveMode?v.connection:'模拟在线';$('total').textContent=String(snap.vehicles.length).padStart(2,'0');$('recovery').hidden=!liveMode;$('recovery').disabled=!v.recoveryReady;
  document.querySelector('.live').textContent=liveMode?(adapter.online?'后端已连接 · 车端状态':'后端连接中断'):'前端仿真运行中';
  if(liveMode){for(const id of ['dispatch','pause','cancel'])$(id).disabled ||= !adapter.online||['STALE','UNKNOWN'].includes(v.state);$('recovery').disabled ||= !adapter.online;$('faults').textContent=String((snap.faults||[]).filter(f=>f.active).length).padStart(2,'0');$('completed').textContent='—';$('rate').disabled=true;}else $('rate').disabled=false;
 }
 for(const name of ['dispatch','pause','cancel','estop'])$(name).onclick=async()=>{try{$('feedback').textContent=await adapter[name](selected);}catch(e){$('feedback').textContent=e.message;}render();};
 $('scene').onchange=e=>{adapter.changeScene(e.target.value);selected=adapter.vehicles[0].id;buildMap();$('feedback').textContent='场景已切换，点击下发任务开始。';render();};
 $('recovery').onclick=async()=>{try{$('feedback').textContent=await adapter.recovery();}catch(e){$('feedback').textContent=e.message;}};
 $('dataMode').onchange=()=>{const live=$('dataMode').value==='live';for(const id of ['apiLabel','robotLabel','connectBackend'])$(id).hidden=!live;if(!live){adapter.dispose?.();liveMode=false;adapter=new MockAdapter(log);selected='CAR-01';$('scene').value=adapter.sceneId;buildMap();adapter.dispatch(selected);document.querySelector('.demo').textContent='演示模式 · 模拟数据';$('connectionFeedback').textContent='无需后端 · 操作仅影响演示车辆';render();}};
 if(location.hostname==='localhost'||location.hostname==='127.0.0.1')$('apiURL').value=location.origin;
 $('connectBackend').onclick=async()=>{try{const next=new LiveAdapter($('apiURL').value.trim(),$('robotId').value.trim(),scenes,log);await next.tick();if(!next.online)throw Error('连接失败，请检查地址、HTTPS 和后端跨域设置');adapter.dispose?.();adapter=next;liveMode=true;selected=next.robotId;$('scene').value=next.sceneId;buildMap();document.querySelector('.demo').textContent='后端连接 · 车端数据';$('connectionFeedback').textContent='已连接 · 场景选择仅决定下发路线，不会切换车端地图';render();}catch(e){$('connectionFeedback').textContent=e.message;}};
 $('clear').onclick=()=>{logs=[];renderLogs();};
 buildMap();adapter.dispatch('CAR-01');render();
 let previous=performance.now();setInterval(()=>{const now=performance.now();adapter.tick(Math.min((now-previous)/1000,.5)*Number($('rate').value));previous=now;render();},100);
}

