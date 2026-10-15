# Brand source

Regenerates every file in `docs/images/brand/`, the icons in `smartsched/frontend/public/` and
`smartsched/frontend/src/components/brand/logo.tsx` from one geometry. Run from the repo root:

```bash
python3 -m venv /tmp/brandvenv && /tmp/brandvenv/bin/pip install fonttools uharfbuzz
/tmp/brandvenv/bin/python docs/images/brand/source/brand.py docs/images/brand smartsched/frontend/public smartsched/frontend/src/components/brand/logo.tsx
rm docs/images/brand/.meta.json
node docs/images/brand/source/export.mjs docs/images/brand smartsched/frontend/public
P=smartsched/frontend/public/icons; python3 docs/images/brand/source/ico.py $P/favicon.ico $P/icon-16.png $P/icon-32.png $P/icon-48.png
node docs/images/brand/source/legibility.mjs docs/images/brand docs/images/brand/checks/legibility-16-24-32.png
python3 docs/images/brand/source/contrast.py
```

Needs the Inter Display SemiBold OTF (SIL OFL 1.1) at the path in `brand.py` (`FONT`); the wordmark is outlined
from it, so the shipped SVGs have no font dependency. `export.mjs` uses the frontend's `sharp` (librsvg).
