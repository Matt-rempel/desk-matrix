# Contributing

This is a small Raspberry Pi project shared through a private GitHub
repository. Please keep changes easy to test on the 32×16 panel.

1. Pull the latest `main`, create a descriptive branch, and make your change.
2. Run `python3 -m unittest discover -s . -p 'test_*.py'` and `sh -n install.sh`.
3. Open a pull request to `main` describing what changed and what was tested
   on a real Pi and panel. Review the change together before merging.
4. On each Pi, run `git pull --ff-only` and `sh install.sh` to receive merged
   changes. Each Pi keeps its own settings and pairing key.

Never commit `/var/lib/flightboard`, a pairing link, Tailscale credentials,
SSH keys, screenshots containing keys, or a `.venv` directory. If a feature
uses a third-party API, document its source, update interval, and any usage
limits. Include a short on-panel example for new display modes so readability
on 32×16 can be reviewed before deployment.
