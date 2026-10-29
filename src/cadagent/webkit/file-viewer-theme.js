/** UI tokens and the corresponding 3D stage palette, scoped to one viewer. */
const colors=['background','canvas','surface','text','muted','border','control','controlHover','controlText','focus','error','accent','grid','glow'];
const variable=name=>'--file-'+name.replace(/[A-Z]/g,c=>'-'+c.toLowerCase());
export function normalizeFileTheme(value='dark'){
  const theme=typeof value==='string'?{mode:value}:value;
  if(!theme||typeof theme!=='object'||Array.isArray(theme))throw new TypeError('Viewer theme must be a mode or theme object');
  if(Object.keys(theme).some(key=>!['mode','colors','fontFamily'].includes(key)))throw new TypeError('Unknown viewer theme option');
  const mode=theme.mode??'dark';
  if(!['dark','light','auto'].includes(mode))throw new TypeError('Viewer theme mode must be dark, light or auto');
  const overrides=theme.colors??{};
  if(!overrides||typeof overrides!=='object'||Array.isArray(overrides))throw new TypeError('Viewer theme colors must be an object');
  for(const [name,color] of Object.entries(overrides)){
    if(!colors.includes(name)||typeof color!=='string'||!/^#[\da-f]{6}$/i.test(color))throw new TypeError('Viewer colors use known token names and six-digit hex values');
  }
  if(theme.fontFamily!==undefined&&(typeof theme.fontFamily!=='string'||!theme.fontFamily.trim()))throw new TypeError('Viewer fontFamily must be a nonempty CSS font-family');
  return{mode,colors:{...overrides},fontFamily:theme.fontFamily};
}

export function mountFileTheme(root,stage,initial='dark'){
  const media=matchMedia('(prefers-color-scheme: dark)');
  let theme,disposed=false;
  function apply(){
    root.dataset.fileTheme=theme.mode==='auto'?(media.matches?'dark':'light'):theme.mode;
    const css=getComputedStyle(root),read=name=>css.getPropertyValue(variable(name)).trim();
    stage.setPalette({accent:read('accent'),grid:read('grid'),glow:read('glow'),background:read('canvas')});
  }
  function set(value){
    if(disposed)return;
    const next=normalizeFileTheme(value);
    // Validate before mutating so a bad update leaves the existing theme intact.
    if(next.fontFamily&&!CSS.supports('font-family',next.fontFamily))throw new TypeError('Invalid viewer fontFamily');
    for(const name of colors)root.style.removeProperty(variable(name));
    root.style.removeProperty('--file-font');
    for(const [name,color] of Object.entries(next.colors))root.style.setProperty(variable(name),color);
    if(next.fontFamily)root.style.setProperty('--file-font',next.fontFamily);
    theme=next;apply();
  }
  const changed=()=>{if(theme.mode==='auto')apply();};
  media.addEventListener('change',changed);
  try{set(initial);}catch(error){media.removeEventListener('change',changed);throw error;}
  return{set,dispose(){disposed=true;media.removeEventListener('change',changed);}};
}
