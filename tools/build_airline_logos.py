"""Build LED-ready logo data from the cited source files (build-time Pillow).

Usage: python tools/build_airline_logos.py AC.png WestJet.png > /tmp/logos.json
Additional square/standalone marks: --extra united United.png
The runtime uses only the generated palette/rows, without image dependencies.
"""
import json
import argparse
import hashlib
from pathlib import Path
import re

from PIL import Image


def encode(image):
    image = image.convert('RGBA')
    # Ignore nearly invisible background-removal residue when finding the mark.
    image = image.crop(image.getchannel('A').point(lambda a: 255 if a >= 64 else 0).getbbox())
    image.thumbnail((22, 22), Image.Resampling.LANCZOS)
    background = Image.new('RGB', image.size)
    background.paste(image, mask=image.getchannel('A'))
    indexed = background.quantize(colors=16, dither=Image.Dither.NONE)
    palette = indexed.getpalette()
    colors, rows = [], []
    for y in range(indexed.height):
        row = ''
        for x in range(indexed.width):
            index = indexed.getpixel((x, y))
            rgb = tuple(palette[index * 3:index * 3 + 3])
            if max(rgb) < 12:
                row += '.'
            else:
                color = '#%02X%02X%02X' % rgb
                if color not in colors:
                    colors.append(color)
                row += format(colors.index(color), 'x')
        rows.append(row)
    return {'palette': colors, 'rows': rows}


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('aircanada', type=Path)
parser.add_argument('westjet', type=Path)
parser.add_argument('--extra', nargs=2, action='append', default=[], metavar=('NAME', 'PNG'))
args = parser.parse_args()
sources = {'aircanada': args.aircanada, 'westjet': args.westjet}
for name, path in args.extra:
    if not re.fullmatch(r'[a-z][a-z0-9_]*', name) or name in sources:
        parser.error('Extra logos need unique lowercase identifiers')
    sources[name] = Path(path)
logos = {}
for name, source in sources.items():
    image = Image.open(source).convert('RGBA')
    if name == 'westjet':
        # The official horizontal lockup places the leaf right of the wordmark.
        image = image.crop((round(image.width * .79), 0, image.width, image.height))
    logos[name] = encode(image)
    logos[name]['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
print(json.dumps(logos, indent=2))
