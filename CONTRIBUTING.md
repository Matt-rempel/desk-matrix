# Contributing

Desk Matrix is a small Raspberry Pi project shared through a public GitHub
repository. Please keep changes easy to test on the 32×16 panel. Anyone can
clone it; pushing a branch requires write access or a fork.

1. Pull the latest `main`, create a descriptive branch, and make your change.
2. Run `python3 -m unittest discover -s . -p 'test_*.py'` and `sh -n install.sh`.
   Tests live beside each module as `test_<module>.py` and use only the
   standard library; add or update them with your change. The Pi runs
   Python 3.11, so avoid newer syntax and APIs.
3. Open a pull request to `main` describing what changed and what was tested
   on a real Pi and panel. Review the change together before merging.
4. On each Pi, run `git pull --ff-only` and `sh install.sh` to receive merged
   changes. Each Pi keeps its own settings and pairing key.

Never commit `/var/lib/flightboard`, a pairing link, Tailscale credentials,
SSH keys, screenshots containing keys, or a `.venv` directory. If a feature
uses a third-party API, document its source, update interval, and any usage
limits, and fetch it in `providers.py` (off the display thread, with a
timeout and the last good value kept).

To add a built-in screen, add it to `BUILTIN_SCREENS` in `catalog.py` (a
layout and one block per slot) and list it in a shelf in `SHELVES`. A new
kind of content is a block: declare it with its options in `BLOCKS` and draw
it in `blocks.py`. Missing data must show a placeholder, never raise. Paste
the screen's ASCII preview into the pull request so readability on 32×16 can
be reviewed before deployment:

```sh
python3 blocks.py <screen id>
```

The settings page in `web/` is plain JavaScript modules and CSS served under a
strict Content-Security-Policy: no inline scripts or `style` attributes, and
no external fonts or CDNs. `docs/REDESIGN_PLAN.md` describes the screen,
library and API formats.
