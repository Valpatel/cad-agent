"""Small, self-contained SVG folder maps for generated library galleries."""
import html


def folder_map_svg(folder, rows, description):
    """Draw a compact tree of owned folders at its readable native width (360 px)."""
    escape = lambda value: html.escape(str(value), quote=True)
    height = 76 + len(rows) * 72
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="360" height="{height}" viewBox="0 0 360 {height}" role="img" aria-labelledby="title description">',
             f'<title id="title">{escape(folder)} folder map</title>',
             f'<desc id="description">{escape(description)}</desc>',
             f'<rect x="1" y="1" width="358" height="{height - 2}" rx="12" fill="#fffdf5" stroke="#6f8a80"/>',
             '<g font-family="Arial, sans-serif" fill="#173d3c">',
             f'<text x="24" y="35" font-size="18" font-weight="700">{escape(folder)}</text>',
             f'<path d="M32 53V{height - 30}" fill="none" stroke="#6f8a80" stroke-width="2"/>']
    for index, (name, purpose) in enumerate(rows):
        y = 76 + index * 72
        parts += [f'<path d="M32 {y}H48" stroke="#6f8a80" stroke-width="2"/>',
                  f'<rect x="48" y="{y - 19}" width="288" height="62" rx="7" fill="#eef1e4"/>',
                  f'<text x="61" y="{y + 5}" font-size="20" font-weight="600">{escape(name)}</text>',
                  f'<text x="61" y="{y + 29}" font-size="18">{escape(purpose)}</text>']
    return '\n'.join(parts + ['</g>', '</svg>', ''])
