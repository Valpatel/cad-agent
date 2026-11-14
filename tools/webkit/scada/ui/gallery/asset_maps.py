"""Build bounded, browsable Markdown indexes for generated image owners."""
import html
from pathlib import PurePosixPath
from posixpath import relpath
from gallery_maps import folder_map_svg


def asset_maps(entries, owner, title, labels=None):
    """Return README bytes; every directory gets a map and relative thumbnails."""
    labels = labels or {}
    directories = {owner}
    for entry in entries:
        directory = str(PurePosixPath(entry['path']).parent)
        assert directory == owner or directory.startswith(owner + '/')
        while directory.startswith(owner):
            directories.add(directory)
            directory = str(PurePosixPath(directory).parent)
    map_path = owner + '/gallery-map.svg'
    rows = ([('family / equipment /', 'Default and variant SVGs')] if owner.endswith('/symbols') else
            [('state group /', 'Equipment state SVGs')] if owner.endswith('/states') else
            [('equipment / family / type /', 'Default and variant JPEGs'), ('states / · workspace /', 'State and UI previews')])
    rows.append(('README.md', 'Local preview and parent links'))
    outputs = {map_path: folder_map_svg(owner + '/', rows,
        'Generated library images are grouped into related folders, each with a linked preview index.').encode()}
    for directory in sorted(directories):
        here = PurePosixPath(directory)
        name = title if directory == owner else labels.get(here.name, here.name.replace('-', ' ').title())
        children = sorted(child for child in directories if str(PurePosixPath(child).parent) == directory)
        direct = [entry for entry in entries if str(PurePosixPath(entry['path']).parent) == directory]
        parent = '../README.md'
        lines = [f'# {name}', '',
                 f'[Parent map]({parent}) · [Package owner]({relpath("README.md", directory)}) · [Image gallery]({relpath("img/README.md", directory)})', '',
                 'Generated previews from canonical equipment artwork and supplied illustrative state. Images do not run a process model. Open a preview for its full size.', '',
                 f'![{title} folder map]({relpath(map_path, directory)})', '']
        if directory == owner:
            lines += ['| Map | Purpose |', '| --- | --- |', '| [gallery-map.svg](gallery-map.svg) | Shared ownership map for this generated gallery. |', '']
        if children:
            lines += ['| Folder | Previews | Example |', '| --- | ---: | --- |']
            for child in children:
                rows = [entry for entry in entries if entry['path'].startswith(child + '/')]
                child_name = PurePosixPath(child).name
                image = relpath(rows[0]['path'], directory)
                label = html.escape(labels.get(child_name, child_name.replace('-', ' ').title()))
                lines.append(f'| [{label}]({child_name}/README.md) | {len(rows)} | <a href="{image}"><img src="{image}" width="160" alt="{label} preview"></a> |')
            lines.append('')
        if direct:
            lines += ['| File | Preview | Equipment and supplied state |', '| --- | --- | --- |']
            for entry in direct:
                filename = PurePosixPath(entry['path']).name
                label = entry.get('label', entry.get('id', entry.get('type', filename)))
                if entry.get('variantLabel'):
                    label += ' — ' + entry['variantLabel']
                details = html.escape(label).replace('|', '&#124;')
                state = entry.get('stateLabel', entry.get('description', 'Fixed illustrative preview'))
                details += '<br>' + html.escape(state).replace('|', '&#124;')
                if entry.get('type'):
                    details += '<br>`' + entry['type'] + '`'
                if entry.get('variant'):
                    details += ' / `' + entry['variant'] + '`'
                fields = ', '.join('`' + item['key'] + '`' for item in entry.get('stateFields', []))
                if fields:
                    details += '<br>Editable fields: ' + fields
                lines.append(f'| [{filename}]({filename}) | <a href="{filename}"><img src="{filename}" width="240" alt="{html.escape(label, quote=True)}"></a> | {details} |')
            lines.append('')
        outputs[directory + '/README.md'] = ('\n'.join(lines).rstrip() + '\n').encode()
    return outputs


def gallery_outputs(manifest, categories):
    files = {}
    lines = ['# SCADA UI image gallery', '', '[Package owner](../README.md) · [Equipment map](symbols/README.md) · [Interactive example](../examples/components/index.html) · [State examples](states/README.md) · [UI snapshots](thumbnails/README.md)', '',
             'Each library owns its own `img/` directory. This package owns equipment artwork, visual states and viewer/workspace previews. [Simulation scenario previews](../../sim/img/README.md) belong to the separate model package.', '',
             '![UI image folder map](gallery-map.svg)', '',
             f"The catalog contains {len(manifest['symbols'])} generated SVG previews. SVG images contain the canonical equipment artwork, native SVG text/readouts and inline CSS animation; no scripts, external styles, fonts or images. GitHub and other Markdown renderers can display them using ordinary relative image links. Animation support depends on the renderer; the first frame remains useful. The live examples provide interactive state controls.", '',
             'All displayed values and selected states are illustrative, editable rendering inputs. An animated picture is not a process model. Read [the style guide](../STYLE_GUIDE.md) and [contribution guide](../CONTRIBUTING.md) before adding assets.', '',
             '| Folder | Contents and use |', '| --- | --- |',
             '| [gallery-map.svg](gallery-map.svg) | Compact ownership map for UI imagery. |',
             '| [symbols/](symbols/README.md) | Every default type and declared variant, grouped by equipment family. |',
             f"| [states/](states/README.md) | {len(manifest['states'])} illustrative comparisons for motion, availability, damage and retained inventory. |",
             '| [thumbnails/](thumbnails/README.md) | Static equipment, variant, state and reusable UI captures. |', '',
             'Generate SVGs and these maps with `npm --prefix tools/webkit/scada run gallery:generate`; verify with `npm --prefix tools/webkit/scada run gallery:check`. See the [export contract](../docs/GALLERY_EXPORT.md) and [gallery manifest](../metadata/gallery.json) for provenance and checks.', '',
             '| Family | Previews | Sample |', '| --- | --- | --- |']
    labels = {category['id']: category['label'] for category in categories}
    labels.update({row['type']: row['label'] for row in manifest['symbols'] if not row['variant']})
    for category in categories:
        assets = [row for row in manifest['symbols'] if row['category'] == category['id']]
        if not assets:
            continue
        preview = assets[0]['path'].removeprefix('img/')
        label = html.escape(category['label'])
        lines.append(f'| [{label}](symbols/{category["id"]}/README.md) | {len(assets)} | <img src="{preview}" alt="{label} example" width="160"> |')
    files['img/gallery-map.svg'] = folder_map_svg('scada/ui/img/', [('symbols/', 'Animated equipment SVGs'), ('states/', 'Illustrative state comparisons'), ('thumbnails/', 'Equipment and workspace JPEGs')], 'UI images are owned by the symbol, state and thumbnail galleries. Simulation previews belong to the sibling model library.').encode()
    files['img/README.md'] = ('\n'.join(lines) + '\n').encode()
    files.update(asset_maps(manifest['symbols'], 'img/symbols', 'Equipment previews', labels))
    files.update(asset_maps(manifest['states'], 'img/states', 'Visual state examples', labels))
    return files
