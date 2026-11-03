"""Build bundled 14px NHL marks from transparent, source-rendered PNGs.

Build-time only: Pillow. Runtime needs no image package or network access.
Render https://assets.nhle.com/logos/nhl/svg/{TEAM}_dark.svg to transparent
512px PNGs named {TEAM}.png, then run:
  python tools/build_nhl_logos.py PNG_DIRECTORY --svg-dir SVG_DIRECTORY > nhl_logos.py
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nhl import TEAMS

SYMBOLS = '0123456789abcdefghijklmnopqrstuvwxyz'

def encode(path):
    image = Image.open(path).convert('RGBA')
    box = image.getchannel('A').point(lambda a: 255 if a > 24 else 0).getbbox()
    if box is None:
        raise ValueError(f'Empty logo: {path}')
    image = image.crop(box)
    image.thumbnail((14, 14), Image.Resampling.LANCZOS)
    rgb = Image.new('RGB', image.size)
    rgb.paste(image, mask=image.getchannel('A'))
    indexed = rgb.quantize(colors=20, dither=Image.Dither.NONE).convert('RGB')
    palette, rows, counts = [], [], {}
    for y in range(indexed.height):
        row = ''
        for x in range(indexed.width):
            color = indexed.getpixel((x, y))
            if max(color) <= 18:
                row += '.'
                continue
            value = '#%02X%02X%02X' % color
            if value not in palette:
                palette.append(value)
            row += SYMBOLS[palette.index(value)]
            counts[color] = counts.get(color, 0) + 1
        rows.append(row)
    choices = [(n * (max(c) - min(c)), c) for c, n in counts.items() if max(c) - min(c) > 45]
    if choices:
        _, c = max(choices)
        factor = max(1, 215 / max(c))
        accent = '#%02X%02X%02X' % tuple(min(255, round(v * factor)) for v in c)
    else:
        accent = '#F4F2EE'
    return {'palette': palette, 'rows': rows, 'color': accent}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('png_dir', type=Path)
    parser.add_argument('--svg-dir', type=Path)
    args = parser.parse_args()
    logos = {}
    for team in TEAMS:
        source = args.png_dir / f'{team}.png'
        value = encode(source)
        value['source_url'] = f'https://assets.nhle.com/logos/nhl/svg/{team}_dark.svg'
        original = args.svg_dir / f'{team}.svg' if args.svg_dir else source
        value['source_sha256'] = hashlib.sha256(original.read_bytes()).hexdigest()
        value['color'] = {'CGY': '#FF554E', 'SJS': '#43DAD5'}.get(team, value['color'])
        logos[team] = value
    print('"""Bundled NHL logo pixels. See docs/NHL_SCOREBOARD.md for sources and rebuilding."""')
    print('LOGOS = ' + json.dumps(logos, indent=2))


if __name__ == '__main__':
    main()
