"""Deterministic screenshots of actual browser-rendered animation frames.

Used only in capture documents. Production artwork and application files are
never changed; sampled computed styles replace compositor animation machinery.
"""

def fitted_camera_coverage(page, selector, expected_ids=None, expected_world=None):
    """Check geometric coverage before a fitted thumbnail; this is not readability QA.

    Record inner viewport bounds rather than scrollWidth: clipping can conceal an
    unfitted world without producing a scrollbar. Effects outside DOM rectangles
    still need visual inspection.
    """
    report = page.locator(selector).evaluate('''root => {
      const viewport=root.querySelector('[data-scada-scroll]'),canvas=viewport?.querySelector('[data-scada-canvas]');
      if(!viewport || !canvas)throw new Error('A fitted camera viewport and canvas are required.');
      const outer=viewport.getBoundingClientRect(),left=outer.left+viewport.clientLeft,top=outer.top+viewport.clientTop;
      const width=viewport.clientWidth,height=viewport.clientHeight,tolerance=1.5;
      const relative=element=>{const r=element.getBoundingClientRect();return {x:r.left-left,y:r.top-top,width:r.width,height:r.height};};
      const overflow=r=>Math.max(0,-r.x,-r.y,r.x+r.width-width,r.y+r.height-height);
      const intersects=(a,b)=>a.x<b.x+b.width && a.x+a.width>b.x && a.y<b.y+b.height && a.y+a.height>b.y;
      const equipment=[...viewport.querySelectorAll('[data-scada-equipment]')].map(element=>({id:element.dataset.scadaEquipment,rect:relative(element),labels:[...element.querySelectorAll('.scada-viewer-equipment-label,.scada-viewer-equipment-status')].map(relative)}));
      const controls=[...viewport.querySelectorAll('[data-scada-camera-controls]')].map(relative);
      const world={width:Number(canvas.dataset.scadaWidth),height:Number(canvas.dataset.scadaHeight)},layout={width:canvas.offsetWidth,height:canvas.offsetHeight},rect=relative(canvas);
      const camera={x:Number(viewport.dataset.cameraX),y:Number(viewport.dataset.cameraY),zoom:Number(viewport.dataset.cameraZoom),fitted:viewport.dataset.cameraFitted==='true'};
      return {worldSize:world,layoutSize:layout,viewportSize:{width,height},camera,canvasRect:rect,
        finite:width>0 && height>0 && world.width>0 && world.height>0 && camera.zoom>0 && Object.values(camera).every(value=>typeof value==='boolean'||Number.isFinite(value)),
        layoutMatchesWorld:Math.abs(layout.width-world.width)<=tolerance && Math.abs(layout.height-world.height)<=tolerance,
        dimensionsMatchScale:Math.abs(rect.width-world.width*camera.zoom)<=tolerance && Math.abs(rect.height-world.height*camera.zoom)<=tolerance,
        canvasOverflowPx:overflow(rect),renderedIds:equipment.map(item=>item.id).sort(),
        clippedIds:equipment.filter(item=>item.rect.width<=0||item.rect.height<=0||overflow(item.rect)>tolerance).map(item=>item.id),
        clippedLabelIds:equipment.filter(item=>item.labels.some(label=>overflow(label)>tolerance)).map(item=>item.id),
        controlOverlapIds:equipment.filter(item=>controls.some(control=>intersects(item.rect,control)||item.labels.some(label=>intersects(label,control)))).map(item=>item.id),
        maxOverflowPx:Math.max(overflow(rect),...equipment.flatMap(item=>[overflow(item.rect),...item.labels.map(overflow)]),0)};
    }''')
    if expected_ids is not None:
        report['expectedIds'] = sorted(expected_ids)
        assert report['renderedIds'] == report['expectedIds'], report
    if expected_world is not None:
        assert report['worldSize'] == {key: expected_world[key] for key in ('width', 'height')}, report
    assert report['finite'] and report['camera']['fitted'] and report['layoutMatchesWorld'] and report['dimensionsMatchScale'], report
    assert report['renderedIds'] and report['canvasOverflowPx'] <= 1.5, report
    assert not report['clippedIds'] and not report['clippedLabelIds'] and not report['controlOverlapIds'], report
    return report


def freeze_animation_frame(page, frame_ms=1200):
    page.evaluate('''async frame => {
      await document.fonts.ready;
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      const animations=document.getAnimations();
      for(const animation of animations) animation.pause();
      await Promise.all(animations.map(animation=>animation.ready));
      for(const animation of animations) animation.currentTime=frame;
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      // Bake the actual sampled styles into this temporary capture document.
      // A paused compositor animation can still rasterize an adjacent frame;
      // removing animation machinery after sampling makes the PNG reproducible.
      const frozen=new Map();
      for(const animation of animations){
        const target=animation.effect?.target;if(!target)continue;
        const computed=getComputedStyle(target),properties=frozen.get(target)??new Map();
        for(const keyframe of animation.effect.getKeyframes()){
          for(const property of Object.keys(keyframe)){
            if(['offset','computedOffset','easing','composite'].includes(property))continue;
            const cssName=property.replace(/[A-Z]/g,letter=>'-'+letter.toLowerCase());
            properties.set(cssName,computed.getPropertyValue(cssName));
          }
        }
        frozen.set(target,properties);
      }
      for(const animation of animations)animation.cancel();
      for(const [target,properties] of frozen){
        target.style.setProperty('animation','none','important');
        for(const [property,value] of properties)target.style.setProperty(property,value,'important');
      }
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    }''', frame_ms)
