"""Build LED-ready logo data from the cited source files (build-time Pillow).

Usage: python tools/build_airline_logos.py AC.png WestJet.png > /tmp/logos.json
The runtime uses only the generated palette/rows, without image dependencies.
"""
import json
import sys
import hashlib
from pathlib import Path

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


ac_path, wj_path = map(Path, sys.argv[1:])
ac = Image.open(ac_path)
wj = Image.open(wj_path).convert('RGBA')
# The official horizontal lockup places the leaf to the right of the wordmark.
wj = wj.crop((round(wj.width * .79), 0, wj.width, wj.height))
logos = {'aircanada': encode(ac), 'westjet': encode(wj)}
for name, source in [('aircanada', ac_path), ('westjet', wj_path)]:
    logos[name]['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
print(json.dumps(logos, indent=2))
