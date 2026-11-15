import type { ActingProfile, Beat, Rect, ShotContext } from './types';

export function resolveActingCue(beat: Beat, localTime: number, actorId: string) {
  if (!Number.isFinite(localTime)) throw Error('表演采样时间无效');
  const cues = (beat.performance || []).filter(cue => cue.actor_id === actorId).map((cue, order) => {
    const raw = cue.event === 'start' ? 0 : beat.events[cue.event];
    if (!Number.isFinite(raw)) throw Error(`表演事件不存在 ${beat.id}.${cue.event}`);
    const time = Number(raw) + (cue.offset ?? 0);
    if (!cue.asset_id || !cue.pose || !Number.isFinite(time) || time < 0 || time >= beat.end - beat.start) {
      throw Error(`表演提示无效 ${beat.id}.${cue.event}`);
    }
    return {cue, order, time};
  }).sort((a,b) => a.time-b.time || a.order-b.order);
  if (!cues.length || localTime < cues[0].time) return undefined;
  let index=0;
  for (let i=1;i<cues.length;i++) if(cues[i].time<=localTime) index=i; else break;
  const current=cues[index], prior=index>0?cues[index-1]:undefined;
  return {
    cue:current.cue, previous:prior?.cue,
    cueTime:current.time, nextTime:cues[index+1]?.time,
    elapsed:Math.max(0,localTime-current.time),
    previousElapsed:prior?Math.max(0,current.time-prior.time):undefined,
  };
}

export function actingFrame(profile: ActingProfile, pose: string, elapsed: number): number {
  const row=profile.poses[pose], cells=profile.grid.columns*profile.grid.rows;
  if (!row || !row.frames.length || row.frames.length!==row.keys.length || row.keys[0]!==0 ||
      !row.keys.every((key,i)=>Number.isFinite(key) && (i===0 || key>row.keys[i-1])) ||
      !row.frames.every(frame=>Number.isInteger(frame) && frame>=0 && frame<cells)) {
    throw Error(`表演姿态没有有效画格时序: ${profile.actor_id}.${pose}`);
  }
  let index=0;
  for(let i=1;i<row.keys.length;i++) if(elapsed>=row.keys[i]) index=i; else break;
  return row.frames[index];
}

export function actingSourceRect(profile: ActingProfile, width: number, height: number, frame: number): [number,number,number,number] {
  const {columns,rows,gutter=0}=profile.grid, cellW=width/columns, cellH=height/rows;
  if(!Number.isInteger(columns)||!Number.isInteger(rows)||columns<1||rows<1||!Number.isFinite(gutter)||gutter<0||
     cellW<=gutter*2||cellH<=gutter*2||!Number.isInteger(frame)||frame<0||frame>=columns*rows) throw Error(`表演画格越界: ${profile.actor_id}#${frame}`);
  return [(frame%columns)*cellW+gutter,Math.floor(frame/columns)*cellH+gutter,cellW-gutter*2,cellH-gutter*2];
}

export function renderActor(ctx: ShotContext, actorId: string, destination?: Rect) {
  const resolved=resolveActingCue(ctx.beat,ctx.t,actorId);
  if(!resolved) return;
  const profile=ctx.actingProfiles[resolved.cue.asset_id], image=ctx.stage.images[resolved.cue.asset_id];
  if(!profile||profile.actor_id!==actorId) throw Error(`表演 profile 与身份不匹配: ${actorId}/${resolved.cue.asset_id}`);
  if(!image) throw Error(`表演素材未加载: ${resolved.cue.asset_id}`);
  const frame=actingFrame(profile,resolved.cue.pose,resolved.elapsed);
  const rect=actingSourceRect(profile,image.width,image.height,frame), b=destination||profile.destination;
  if(![b.x,b.y,b.w,b.h].every(Number.isFinite)||b.w<=0||b.h<=0) throw Error('表演显示区域无效');
  ctx.stage.g.drawImage(image,...rect,b.x,b.y,b.w,b.h);
  ctx.stage.bounds({...b,name:`${actorId}:${resolved.cue.pose}:frame-${frame}`});
  ctx.performanceStates.push({actor_id:actorId,asset_id:resolved.cue.asset_id,event:resolved.cue.event,pose:resolved.cue.pose,
    previous_pose:resolved.previous?.pose,transition:1,elapsed:resolved.elapsed,previous_elapsed:resolved.previousElapsed,
    frame,source_rect:rect,composition:profile.composition});
}
