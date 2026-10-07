// Advisory geometry only. These observations do not approve semantics or stop a Stage.
const intersects=(a,b)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
export function observeLayout(layout, width, height) {
  const findings=[];
  if (!layout) return [{kind:'layout_unreported',blocks_stage_progress:false}];
  const text=Array.isArray(layout.text)?layout.text:[];
  const subjects=Array.isArray(layout.subjects)?layout.subjects:[];
  const debt=(kind,a,b)=>findings.push({kind,element:a.name||'unnamed',other:b?.name||null,
    rect:a,blocks_stage_progress:false,semantic_review_required:true});
  for(const a of text) {
    if(a.x<0||a.y<0||a.x+a.w>width||a.y+a.h>height) debt('text_outside_canvas',a);
    if(layout.subtitle&&intersects(a,layout.subtitle)) debt('text_subtitle_intersection',a,layout.subtitle);
    for(const b of subjects) if(intersects(a,b)) debt('text_subject_intersection',a,b);
  }
  for(let i=0;i<text.length;i++)for(let j=i+1;j<text.length;j++)
    if(intersects(text[i],text[j]))debt('text_text_intersection',text[i],text[j]);
  if(layout.subtitle) {
    const a=layout.subtitle;
    if(a.x<0||a.y<0||a.x+a.w>width||a.y+a.h>height)debt('subtitle_outside_canvas',a);
    for(const b of subjects)if(intersects(a,b))debt('subtitle_subject_intersection',a,b);
  }
  return findings;
}
export function observeCues(score) {
  return (score?.cues||[]).map(c=>{
    const duration=Number(c.end)-Number(c.start),text=String(c.text||'');
    return {text,start:c.start,end:c.end,duration,character_count:[...text].length,
      characters_per_second:duration>0?[...text].length/duration:null,
      blocks_stage_progress:false,reading_quality:'not_assessed'};
  });
}
