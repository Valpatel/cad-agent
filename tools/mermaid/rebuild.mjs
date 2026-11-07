/** Rebuild the existing Mermaid11 browser API with fixed, locked sanitizer/math dependencies. */
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile,writeFile,readdir} from 'node:fs/promises';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

assert.equal(Number(process.versions.node.split('.')[0]),22,'Use Node22 and npm ci --ignore-scripts first');
assert(process.argv.length===3&&['--check','--write'].includes(process.argv[2]),'Choose --check or --write');
const here=path.dirname(fileURLToPath(import.meta.url)),repo=path.resolve(here,'../..');
const vendor=path.join(repo,'software/cadagent/webkit/vendor/mermaid');
const read=file=>readFile(path.join(here,file));
const json=async file=>JSON.parse(await read(file));
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const serialized=data=>Buffer.from(JSON.stringify(data,null,2)+'\n');
const manifest=await json('package.json'),lock=await json('package-lock.json');
assert.deepEqual(manifest.dependencies,{mermaid:'11.17.2',esbuild:'0.28.2'});
assert.deepEqual(manifest.overrides,{dompurify:'3.4.17',katex:'0.18.10'});
assert.deepEqual(lock.packages[''].dependencies,manifest.dependencies);
const require=createRequire(import.meta.url),compiler=await json('node_modules/esbuild/package.json');
const platform=`${process.platform}-${process.arch}`,binaryMember=process.platform==='win32'?'esbuild.exe':'bin/esbuild';
const binary=require.resolve(`@esbuild/${platform}/${binaryMember}`);
assert.equal(compiler.version,manifest.dependencies.esbuild);
assert.equal(hash(await readFile(binary)),compiler['esbuild.binaryHashes'][`@esbuild/${platform}/${binaryMember}`],
 'The compiler binary must match its pinned package hash; do not run an install hook to repair it');
process.env.ESBUILD_BINARY_PATH=binary;
const esbuild=await import('esbuild');assert.equal(esbuild.version,compiler.version);
const entry="import mermaid from 'mermaid'; globalThis.mermaid=mermaid;";
const options={bundle:true,minify:true,keepNames:true,format:'iife',platform:'browser',
 external:['require','fs','path'],legalComments:'eof',write:false,metafile:true};
const result=await esbuild.build({...options,absWorkingDir:here,stdin:{contents:entry,resolveDir:here,
 sourcefile:'mermaid-entry.mjs',loader:'js'}});
assert.equal(result.outputFiles.length,1);const bundle=Buffer.from(result.outputFiles[0].contents);
const output=Object.values(result.metafile.outputs);assert.equal(output.length,1);
assert.deepEqual(output[0].imports,[],'The shipped single-file renderer must not import external resources');
const packages=new Map(),inputs=[];
for(const [source,emission] of Object.entries(output[0].inputs).sort(([a],[b])=>a<b?-1:a>b?1:0)){
 if(!emission.bytesInOutput)continue;
 if(source==='mermaid-entry.mjs'){inputs.push({path:source,sha256:hash(entry),bytesInOutput:emission.bytesInOutput});continue;}
 assert(source.startsWith('node_modules/')&&!source.split('/').includes('..'),'Unexpected compiler input');
 inputs.push({path:source,sha256:hash(await read(source)),bytesInOutput:emission.bytesInOutput});
 let directory=path.dirname(source),pkg;
 while(directory.startsWith('node_modules/')){
  try{pkg=await json(directory+'/package.json');}catch(e){if(e.code!=='ENOENT')throw e;}
  if(pkg?.name&&pkg.version)break;
  directory=path.dirname(directory);pkg=undefined;
 }
 assert(pkg?.name&&pkg.version,'Every emitted input must have a package owner');
 if(packages.has(directory))continue;
 const pinned=lock.packages[directory];assert(pinned&&pinned.version===pkg.version);
 assert(pinned.resolved.startsWith('https://registry.npmjs.org/')&&pinned.integrity.startsWith('sha512-'));
 const names=(await readdir(path.join(here,directory))).filter(n=>/^(licen[sc]e|copying|notice)/i.test(n)).sort();
 const licences=[];
 for(const name of names){
  const rel=directory+'/'+name;let text;
  try{text=await read(rel);}catch(e){if(e.code==='EISDIR')continue;throw e;}
  licences.push({path:rel,sha256:hash(text),text:text.toString()});
 }
 // fastdom's pinned npm archive puts its complete MIT licence at the end of README.md.
 if(!licences.length&&pkg.name==='fastdom'){
  const rel=directory+'/README.md',text=(await read(rel)).toString();
  const start=text.indexOf('## License\n');assert(start>=0&&text.slice(start).includes('Permission is hereby granted'));
  licences.push({path:rel,sha256:hash(text),text:text.slice(start)});
 }
 assert(licences.length,`No licence text for ${pkg.name}@${pkg.version}`);
 packages.set(directory,{name:pkg.name,version:pkg.version,licence:pkg.license??null,
  resolved:pinned.resolved,integrity:pinned.integrity,licences});
}
assert.equal(packages.get('node_modules/dompurify')?.version,'3.4.17');
assert.equal(packages.get('node_modules/katex')?.version,'0.18.10');
assert(![...packages.values()].some(p=>p.name==='elkjs'),'Do not add ELK through a dependency refresh');
assert(bundle.includes(Buffer.from('DOMPurify 3.4.17'))&&bundle.includes(Buffer.from('"0.18.10"')));
const sorted=[...packages.entries()].sort(([a],[b])=>a<b?-1:a>b?1:0);
const notices=Buffer.from('Licences of packages emitted into the derived Mermaid11 browser bundle.\n'+
 sorted.map(([directory,p])=>`\n=== ${p.name}@${p.version} (${directory}) ===\n${p.resolved}\n`+
  p.licences.map(l=>`\n--- ${l.path} ---\n${l.text.trimEnd()}\n`).join('')).join(''));
const build={producer:'tools/mermaid/rebuild.mjs',producer_sha256:hash(await read('rebuild.mjs')),
 package_lock_sha256:hash(await read('package-lock.json')),compiler:esbuild.version,entry,options,
 bundle_sha256:hash(bundle),metafile_sha256:hash(serialized(result.metafile)),inputs,
 packages:Object.fromEntries(sorted.map(([directory,p])=>[directory,{...p,
  licences:p.licences.map(({text,...record})=>record)}]))};
const record=serialized(build),receipt=JSON.parse(await readFile(path.join(vendor,'SOURCE.json')));
const upstream=await read('node_modules/mermaid/dist/mermaid.min.js');
assert.equal(hash(upstream),'581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8');
assert.equal(receipt.version,manifest.dependencies.mermaid);
assert.equal(receipt.npm_integrity,lock.packages['node_modules/mermaid'].integrity);
assert.equal(hash(await read('node_modules/mermaid/LICENSE')),receipt.files.LICENSE);
receipt.files={...receipt.files,'mermaid.min.js':hash(bundle),'BUILD.json':hash(record),'THIRD-PARTY-LICENSES.txt':hash(notices)};
receipt.patched={'mermaid.min.js':{upstream_sha256:hash(upstream),change:'Rebuilt from the official npm core entry with the locked fixed DOMPurify/KaTeX dependencies; no minified source editing. Producer and all emitted input/package/licence hashes are recorded in BUILD.json.'}};
receipt.rebuild={producer:'tools/mermaid/rebuild.mjs',lock:'tools/mermaid/package-lock.json',record:'BUILD.json'};
receipt.bundled={dompurify:'3.4.17',katex:'0.18.10',note:'These are actual emitted library versions, checked with the compiler input map and version markers. The existing strict renderer sanitizes labels and final SVG strings. Its default configuration does not request SAFE_FOR_TEMPLATES, IN_PLACE, DOM-returning output or an XHTML parser, and it does not supply attached-shadow DOM nodes or evaluate templates; the reported nondefault DOMPurify advisory paths are not exercised by this checked consumer. Other consumers/configurations are not qualified by that inspection. Mermaid uses KaTeX for mathematical labels, then sanitizes its output; no pre-existing prototype-pollution condition is asserted absent. Both libraries are updated rather than accepting their advisories. KaTeX0.18.11 is deliberately excluded because its registry metadata declares accidental breaking changes. The locked derived build preserves Mermaid11, adds no ELK and retains all emitted dependency notices.'};
const generated={'mermaid.min.js':bundle,'BUILD.json':record,'THIRD-PARTY-LICENSES.txt':notices,'SOURCE.json':serialized(receipt)};
for(const [name,bytes] of Object.entries(generated)){
 if(process.argv[2]==='--write')await writeFile(path.join(vendor,name),bytes);
 else assert.deepEqual(await readFile(path.join(vendor,name)),Buffer.from(bytes),`Rebuild differs: ${name}`);
}
console.log(`Mermaid11 fixed-dependency bundle ${process.argv[2]}: ${bundle.length} bytes, ${hash(bundle)}, ${packages.size} emitted packages`);
