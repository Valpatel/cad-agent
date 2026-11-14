"""Export package-owned SVG previews from canonical artwork, with no live model.

Generation uses Chromium's native selectors and animation styles, and original
CSS source slices. --check is read-only and requires no browser. Every output is
owned by img/symbols, img/states, their indexes, or metadata/gallery.json.
"""
from pathlib import Path
import sys
sys.path.insert(0, str((Path(__file__).resolve().parent / '..').resolve()))
from scada_paths import REPO, UI
import argparse
import hashlib
import json
import shutil
import subprocess

PACKAGE = UI
TOOLS = Path(__file__).resolve().parent / 'gallery'
sys.path.insert(0, str(TOOLS))
from asset_maps import gallery_outputs
from renderer import render_gallery

FORMAT = 'scada-ui-svg-gallery'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_hashes():
    # Prose maps cannot affect artwork. Keep all other source inputs covered,
    # including any future local image/font assets introduced by the renderer.
    paths = [p for p in (PACKAGE / 'src').rglob('*') if p.is_file() and p.suffix != '.md']
    paths += [REPO / 'tools/webkit/scada/scada_paths.py', REPO / 'tools/webkit/scada/paths.mjs'] + [p for p in TOOLS.rglob('*') if p.is_file() and p.suffix in ('.mjs', '.json', '.py') and p.name != 'asset_maps.py']
    return {str(p.relative_to(REPO)): sha(p.read_bytes()) for p in sorted(paths)}


def categories():
    script = "import {SCADA_CATEGORIES} from './src/symbols/index.mjs'; console.log(JSON.stringify(SCADA_CATEGORIES))"
    return json.loads(subprocess.check_output(['node', '--input-type=module', '-e', script], cwd=PACKAGE))


def check(root):
    manifest = json.loads((root / 'metadata/gallery.json').read_text())
    if manifest['format'] != FORMAT or manifest['version'] != 1:
        raise RuntimeError('Unsupported gallery manifest')
    if manifest['source_hashes'] != source_hashes():
        raise RuntimeError('Gallery source changed; regenerate with npm --prefix tools/webkit/scada run gallery:generate')
    inventory = json.loads(subprocess.check_output(['node', str(TOOLS / 'inventory.mjs')], cwd=PACKAGE))
    expected_symbols = [row for row in inventory if row['sample'] is None]
    expected_states = [row for row in inventory if row['sample'] is not None]
    for group, rows in [('symbols', expected_symbols), ('states', expected_states)]:
        actual_rows = manifest[group]
        if len(actual_rows) != len(rows):
            raise RuntimeError('Gallery manifest catalog coverage changed: ' + group)
        for expected_row, actual_row in zip(rows, actual_rows):
            if any(actual_row.get(key) != value for key, value in expected_row.items()):
                raise RuntimeError('Gallery manifest state/catalog mismatch: ' + expected_row['path'])
            data = (root / expected_row['path']).read_bytes()
            if actual_row['sha256'] != sha(data) or actual_row['bytes'] != len(data):
                raise RuntimeError('Gallery image record differs from its output: ' + expected_row['path'])
    expected = set(manifest['outputs'])
    actual = {str(p.relative_to(root)) for owner in ['img/symbols', 'img/states'] for p in (root / owner).rglob('*') if p.is_file()}
    actual.update(['img/README.md', 'img/gallery-map.svg'])
    if expected != actual:
        raise RuntimeError(f'Gallery output paths differ: {sorted(expected ^ actual)}')
    for name, digest in manifest['outputs'].items():
        if sha((root / name).read_bytes()) != digest:
            raise RuntimeError(f'Gallery output changed: {name}')
    for name, data in gallery_outputs(manifest, categories()).items():
        if (root / name).read_bytes() != data:
            raise RuntimeError('Gallery map changed; regenerate: ' + name)
    print(json.dumps({'checked': len(expected), 'symbols': len(manifest['symbols']), 'states': len(manifest['states'])}))


def generate(target):
    files, manifest = render_gallery(source_hashes())
    files.update(gallery_outputs(manifest, categories()))
    manifest['outputs'] = {name: sha(data) for name, data in sorted(files.items())}
    # Preflight completely before replacing any owned output. Never prune sibling captures.
    if manifest['source_hashes'] != source_hashes():
        raise RuntimeError('Gallery source changed during generation; no outputs were replaced')
    for candidate in [target, *target.parents]:
        if candidate.is_symlink():
            raise RuntimeError('Symlink in gallery output root: ' + str(candidate))
    # Validate all paths before pruning any managed subtree. A capture directory
    # or a symlink must never redirect this writer into another output owner.
    for name in [*files, 'metadata/gallery.json', 'img/symbols', 'img/states']:
        relative = Path(name)
        if name not in ['img/README.md', 'img/gallery-map.svg', 'metadata/gallery.json', 'img/symbols', 'img/states'] and not name.startswith(('img/symbols/', 'img/states/')):
            raise RuntimeError('Output outside gallery ownership: ' + name)
        if relative.is_absolute() or '..' in relative.parts:
            raise RuntimeError('Invalid gallery output path: ' + name)
        path = target / relative
        for candidate in [path, *path.parents]:
            if candidate == target:
                break
            if candidate.is_symlink():
                raise RuntimeError('Symlink in gallery output path: ' + str(candidate))
    for directory in [target, target / 'img', target / 'metadata', target / 'img/symbols', target / 'img/states']:
        if directory.exists() and not directory.is_dir():
            raise RuntimeError('File blocks gallery output directory: ' + str(directory))
    for name in ['img/README.md', 'img/gallery-map.svg', 'metadata/gallery.json']:
        path = target / name
        if path.exists() and not path.is_file():
            raise RuntimeError('Directory blocks gallery output file: ' + str(path))
    target.mkdir(parents=True, exist_ok=True)
    for owner in ['img/symbols', 'img/states']:
        path = target / owner
        if path.exists():
            shutil.rmtree(path)
    for name, data in files.items():
        path = target / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    (target / 'metadata').mkdir(exist_ok=True)
    (target / 'metadata/gallery.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'symbols': len(manifest['symbols']), 'states': len(manifest['states']), 'decoded': manifest['image_decode_count'], 'svg_bytes': sum(a['bytes'] for a in manifest['symbols'] + manifest['states'])}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only source and generated-output hash verification; no browser required')
    parser.add_argument('--output', type=Path, default=PACKAGE, help='Package-shaped output root (use work/ for a study)')
    args = parser.parse_args()
    if args.check:
        check(args.output.resolve())
    else:
        generate(args.output.absolute())
