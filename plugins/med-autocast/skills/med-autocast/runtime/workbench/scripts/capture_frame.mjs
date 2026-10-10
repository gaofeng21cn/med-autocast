// Fast native Canvas capture where CSS and backing-store dimensions agree.
// DOM/SVG, transformed or styled canvases keep the browser screenshot path.
export async function captureFilm(page, width, height, output) {
  const data = await page.evaluate(({width, height}) => {
    const element = document.querySelector('#film');
    if (!(element instanceof HTMLCanvasElement) || devicePixelRatio !== 1) return null;
    const style = getComputedStyle(element), box = element.getBoundingClientRect();
    if (element.width !== width || element.height !== height ||
        Math.abs(box.width-width) > .01 || Math.abs(box.height-height) > .01 ||
        style.opacity !== '1' || style.transform !== 'none' || style.filter !== 'none' ||
        style.mixBlendMode !== 'normal' || style.boxShadow !== 'none' ||
        ['borderTopWidth','borderLeftWidth','borderRightWidth','borderBottomWidth',
         'paddingTop','paddingLeft','paddingRight','paddingBottom'].some(k => parseFloat(style[k]) > 0) ||
        style.borderRadius !== '0px') return null;
    for (let parent=element.parentElement;parent;parent=parent.parentElement) {
      const s=getComputedStyle(parent);
      if(s.opacity!=='1'||s.transform!=='none'||s.filter!=='none'||s.perspective!=='none'||s.mixBlendMode!=='normal') return null;
    }
    // DOM overlays must remain visible in the exported frame.
    for (const other of document.querySelectorAll('body *')) {
      if(other===element||other.contains(element)) continue;
      const s=getComputedStyle(other);
      if(s.display==='none'||s.visibility!=='visible'||s.opacity==='0') continue;
      const b=other.getBoundingClientRect();
      if(b.width>0&&b.height>0&&b.left<box.right&&b.right>box.left&&b.top<box.bottom&&b.bottom>box.top) return null;
    }
    // Only fully opaque Canvas 2D frames qualify. Tainted or WebGL canvases
    // fall back to Chromium rather than failing an otherwise usable renderer.
    try {
      const ctx = element.getContext('2d');
      if (!ctx) return null;
      const pixels = ctx.getImageData(0,0,width,height).data;
      for (let i=3;i<pixels.length;i+=4) if (pixels[i] !== 255) return null;
      return element.toDataURL('image/png').split(',')[1];
    } catch { return null; }
  }, {width,height});
  const png = data ? Buffer.from(data,'base64') : await page.locator('#film').screenshot({type:'png'});
  if (output) {
    const fs = await import('node:fs/promises');
    await fs.writeFile(output,png);
  }
  return png;
}
