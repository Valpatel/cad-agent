"""Build bounded, browsable Markdown indexes for generated image owners."""
from collections import defaultdict
import html
from pathlib import PurePosixPath
from posixpath import relpath


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
    outputs = {}
    for directory in sorted(directories):
        here = PurePosixPath(directory)
        name = title if directory == owner else labels.get(here.name, here.name.replace('-', ' ').title())
        children = sorted(child for child in directories if str(PurePosixPath(child).parent) == directory)
        direct = [entry for entry in entries if str(PurePosixPath(entry['path']).parent) == directory]
        parent = '../README.md'
        lines = [f'# {name}', '',
                 f'[Parent map]({parent}) · [Package owner]({relpath("README.md", directory)}) · [Image gallery]({relpath("img/README.md", directory)})', '',
                 'Generated previews from canonical equipment artwork and supplied illustrative state. Images do not run a process model. Open a preview for its full size.', '',
                 '```mermaid', 'flowchart LR', '  Source["Library artwork"] --> Preview["Generated images"]', '  Preview --> Browse["Browsable folder maps"]', '```', '']
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
