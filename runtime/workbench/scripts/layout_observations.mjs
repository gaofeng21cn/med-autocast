// Geometry locates review work; it does not decide paper ownership or approve artwork.
const intersects=(a,b)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
const contains=(outer,inner,pad=0)=>inner.x>=outer.x+pad&&inner.y>=outer.y+pad&&inner.x+inner.w<=outer.x+outer.w-pad&&inner.y+inner.h<=outer.y+outer.h-pad;
export function observeLayout(layout, width, height) {
  const findings=[];
  if (!layout) return [{kind:'layout_unreported',blocks_stage_progress:false}];
  const text=Array.isArray(layout.text)?layout.text:[];
  const subjects=Array.isArray(layout.subjects)?layout.subjects:[];
  const regions=Array.isArray(layout.textRegions)?layout.textRegions:[];
  const debt=(kind,a,b,extra={})=>findings.push({kind,element:a.name||'unnamed',other:b?.name||null,
    rect:a,blocks_stage_progress:false,semantic_review_required:true,...extra});
  for(const r of regions) {
    if(!r.fits)debt('text_region_overflow',r.ink,r.region,{
      owner:r.owner||null,placement:r.placement,local_region:r.local_region,
      local_ink:r.local_ink,overflow:r.overflow,font_size:r.size,lines:r.lines,
      evidence_basis:'explicit_local_text_region_and_actual_font_metrics'});
  }
  for(const a of text) {
    if(a.x<0||a.y<0||a.x+a.w>width||a.y+a.h>height) debt('text_outside_canvas',a);
    if(layout.subtitle&&intersects(a,layout.subtitle)) debt('text_subtitle_intersection',a,layout.subtitle);
    for(const b of subjects) if(intersects(a,b)) {
      debt('text_subject_intersection',a,b);
      // Legacy drawing has no declared text owner. A partial overlap can be an
      // annotation colliding with a person, a title spilling off its paper, or
      // an intentional hanging caption. Do not invent an owner or "pass".
      if(!contains(b,a))debt('unbound_text_subject_partial_overlap',a,b,{
        evidence_basis:'screen_bounding_boxes_only',other_rect:b,
        action:'结合原尺寸帧确认纸上文字、独立标注或误压主体，再局部返修'});
    }
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
