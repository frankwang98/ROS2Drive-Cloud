// HTTP read model; Gateway remains the only ROS/MQTT translation boundary.
// Requests acknowledge publication only. Runtime/Mission displays come from telemetry.
export class LiveAdapter {
 constructor(baseURL, robotId, scenes, onEvent) {
  const url=new URL(baseURL, location.href);
  if(!['http:','https:'].includes(url.protocol))throw Error('后端地址必须是 HTTP 或 HTTPS');
  if(location.protocol==='https:'&&url.protocol!=='https:')throw Error('Pages 为 HTTPS，请使用 HTTPS 后端；本地联调可从后端 /dashboard 打开');
  this.baseURL=url.href.replace(/\/$/,'');this.robotId=robotId;this.scenes=scenes;this.sceneId='mining_haul';this.onEvent=onEvent;this.data=null;this.online=false;this.lastPoll=0;this.busy=false;this.disposed=false;this.state={sceneId:this.sceneId,completed:0,vehicles:[this.empty()]};
 }
 empty(){return{id:this.robotId,state:'UNKNOWN',mission:'UNKNOWN',stage:'UNKNOWN',payload:'UNKNOWN',missionId:null,x:0,y:0,yaw:0,speed:0,progress:0,connection:'OFFLINE',poseValid:false,recoveryReady:false,recoveryRequired:false};}
 get scene(){return this.scenes[this.sceneId];}
 get vehicles(){return this.state.vehicles;}
 async request(path,body){const res=await fetch(`${this.baseURL}${path}`,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(6000)});if(!res.ok)throw Error(`后端 ${res.status}: ${(await res.text()).slice(0,140)}`);return res.json();}
 path(suffix){return `/api/v2/robots/${encodeURIComponent(this.robotId)}/${suffix}`;}
 async tick(){if(this.disposed||this.busy||Date.now()-this.lastPoll<1000)return;this.busy=true;this.lastPoll=Date.now();try{const data=await this.request(this.path('snapshot'));if(this.disposed)return;this.data=data;this.online=true;this.project(data);}catch(e){if(!this.disposed){if(this.online)this.onEvent(this.robotId,'CONNECTION',e.message);this.online=false;this.state.vehicles[0].connection='OFFLINE';}}finally{this.busy=false;}}
 project(data){const r=data.robot,t=data.typed,rt=t.runtime_status?.payload||{},control=t.control?.payload||{},feedback=t.mission_feedback?.payload||{};
  const age=entry=>entry?data.server_time-(entry.received_at||entry.ts):Infinity;
  const runtimeFresh=age(t.runtime_status)<5;
  const odom=r.telemetry?.['sdc/odometry'];const pose=odom?.value?.pose;
  const poseFresh=odom&&data.server_time-(odom.received_at||odom.ts)<5;
  const v=this.empty();Object.assign(v,{state:runtimeFresh?rt.runtime_state:'STALE',mission:runtimeFresh?(rt.mission_state||'UNKNOWN'):'UNKNOWN',stage:runtimeFresh?(rt.mission_state||'UNKNOWN'):'UNKNOWN',missionId:rt.mission_id||null,progress:runtimeFresh?Math.max(0,Math.min(100,(rt.mission_progress||0)*100)):0,speed:poseFresh?(odom.value.velocity?.linear||0):null,connection:r.connection.state,poseValid:!!poseFresh,recoveryReady:runtimeFresh&&!!rt.recovery_ready,recoveryRequired:runtimeFresh&&!!rt.recovery_required});
  if(poseFresh)Object.assign(v,{x:pose.x,y:pose.y,yaw:pose.yaw});
  this.state={sceneId:this.sceneId,completed:0,vehicles:[v],faults:t.fault?.payload?.faults||[]};
 }
 snapshot(){return this.state;}
 changeScene(id){this.sceneId=id;this.state.sceneId=id;}
 async dispatch(){const missionId=`cloud-${Date.now()}-${crypto.randomUUID().slice(0,8)}`,s=this.scene;
  const route=s.route.map((p,i)=>{const q=s.route[Math.min(i+1,s.route.length-1)],prev=s.route[Math.max(0,i-1)];return{x:p.x,y:p.y,theta:Math.atan2(q.y-prev.y,q.x-prev.x)};});
  const res=await this.request(this.path('missions'),{mission_id:missionId,mission_type:1,route,speed_limit:s.speed,goal_tolerance:.9,timeout_s:s.closed?0:600,allow_preempt:true});
  this.onEvent(this.robotId,res.status,`${missionId} · 请求状态`);return `任务请求 ${res.status}；是否接受以车端状态为准`;
 }
 async pause(){const paused=this.state.vehicles[0].mission==='PAUSED';const res=await this.request(`/api/v1/robots/${encodeURIComponent(this.robotId)}/commands`,{action:'set_paused',value:!paused});return `暂停/恢复请求 ${res.status||res.error}`;}
 async cancel(){const id=this.state.vehicles[0].missionId;if(!id)return '车端尚未报告任务 ID';const res=await this.request(this.path(`missions/${encodeURIComponent(id)}/cancel`),{});return `取消请求 ${res.status}`;}
 async estop(){const active=this.state.vehicles[0].state==='ESTOP';const res=await this.request(this.path('emergency-stop'),{value:!active});return active?`清除急停请求 ${res.status}；仍需车端确认安全恢复`:`急停请求 ${res.status}`;}
 async recovery(){const res=await this.request(`/api/v1/robots/${encodeURIComponent(this.robotId)}/commands`,{action:'acknowledge_recovery'});return `安全恢复确认 ${res.status||res.error}`;}
 dispose(){this.disposed=true;}
}
