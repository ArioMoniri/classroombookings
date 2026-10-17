# Design specs v3 (wave 3, 2026-10-17)

Lane W3-DES. Each spec has user goals, references with licences, information hierarchy, components from
`smartsched/frontend/src/components/ui`, Turkish-first copy with keys, phone + desktop wireframes, motion rows per
`docs/design/v2/motion.md`, accessibility notes and acceptance checks.

| Spec | Builder lane | Route | Wireframes |
|---|---|---|---|
| [quick-reserve.md](quick-reserve.md) | W3-SLOT | `/reserve` | `wireframes/quick-reserve-{390,390-receipt,1440,states}.svg` |
| [slot-display.md](slot-display.md) | W3-SLOT | `/settings?tab=slots` + every booking surface | `wireframes/slot-display-{1440,390,matrix}.svg` |
| [ai-admin.md](ai-admin.md) | W3-AI | `/admin/ai` | `wireframes/ai-admin-{usage-1440,providers-1440,390,banners}.svg` |
| [ops-panel.md](ops-panel.md) | W3-OPS | `/admin/ops` | `wireframes/ops-{status-1440,errors-logs-1440,390}.svg` |

Wireframes are generated: `python3 -I wireframes/src/<qr|sd|ai|ops>.py wireframes` from inside `wireframes/src`
(`wf.py` is the shared kit). Purple text in a wireframe is an annotation, not UI copy. Model ids and numbers in the
wireframes are illustrative.

Motion rows in these specs are to be copied into `docs/design/v2/motion.md` (new §3.14 quick reserve, §3.15 slot
display, §3.16 AI admin, §3.17 ops) by whoever owns that file when the surfaces ship; W3-DES writes only under
`docs/design/v3/`.
