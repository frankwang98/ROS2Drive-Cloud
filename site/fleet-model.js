// Pure projection: missing or stale telemetry is unknown, never a healthy zero.
export function projectFleet(snapshot, available=true){
 const now=Number(snapshot.server_time), rows=(snapshot.robots||[]).map(s=>{
  const r=s.robot||{},t=s.typed||{},fresh=e=>available&&e&&Number.isFinite(now)&&now-Number(e.received_at??e.ts)<5;
  const rt=fresh(t.runtime_status)?t.runtime_status.payload:null, fault=fresh(t.fault)?t.fault.payload:null;
  const odom=r.telemetry?.['sdc/odometry'], p=fresh(odom)?odom.value?.pose:null;
  const pose=p&&Number.isFinite(p.x)&&Number.isFinite(p.y)?p:null;
  const progress=rt&&Number.isFinite(rt.mission_progress)?Math.min(100,Math.max(0,rt.mission_progress*100)):null;
  return {id:r.robot_id,connection:available?r.connection?.state||'UNKNOWN':'UNAVAILABLE',runtime:rt?.runtime_state||'STALE',mission:rt?.mission_state||'UNKNOWN',missionId:rt?.mission_id||'',progress,pose,trail:pose?r.trail||[]:[],trajectory:fresh(t.trajectory)&&t.trajectory.payload?.valid?t.trajectory.payload.points||[]:[],faults:fault?(fault.faults||[]).filter(x=>x.active):[],faultKnown:!!fault,age:r.connection?.last_seen?Math.max(0,now-r.connection.last_seen):null};
 });
 return {rows,total:rows.length,online:rows.filter(r=>r.connection==='ONLINE').length,offline:rows.filter(r=>r.connection==='OFFLINE').length,running:rows.filter(r=>r.connection==='ONLINE'&&['EXECUTING','RUNNING','ACTIVE'].includes(r.mission)).length,faults:rows.reduce((n,r)=>n+r.faults.length,0),unknown:rows.filter(r=>!r.faultKnown).length};
}
export function demoFleet(){const now=Date.now()/1000;return {server_time:now,robots:Array.from({length:6},(_,i)=>{const offline=i===5,a=now/15+i;return {server_time:now,robot:{robot_id:`demo-car${i+1}`,connection:{state:offline?'OFFLINE':'ONLINE',last_seen:now-(offline?25:0)},telemetry:{'sdc/odometry':{received_at:now-(offline?25:0),value:{pose:{x:Math.cos(a)*40,y:Math.sin(a)*25,yaw:a}}}},trail:Array.from({length:40},(_,j)=>[Math.cos(a-(39-j)/20)*40,Math.sin(a-(39-j)/20)*25])},typed:{runtime_status:{received_at:now-(offline?25:0),payload:{runtime_state:i===4?'ESTOP':'RUNNING',mission_state:i===4?'PAUSED':'EXECUTING',mission_id:`demo-mission-${i+1}`,mission_progress:(now/90+i/6)%1}},fault:{received_at:now-(offline?25:0),payload:{faults:i===4?[{code:'DEMO_ESTOP',severity:2,message:'演示：软件急停已激活',active:true}]:[]}}}};})};}
