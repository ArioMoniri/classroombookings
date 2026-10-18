# Local model host (vLLM or Ollama) for SmartSched AI

HB-16. This runbook covers serving the AI features from a model inside the institution, through an
OpenAI-compatible server. The features are the helper ("Yardımcı"), chat, rules, intake, council vision and explain.
Nothing leaves the institution's network. SmartSched talks to the server through its `openai_compatible` provider
with the explicit local opt-in (`allow_local`, HB-13). The provider finds out what each model can do when you sync and
test it (HB-12).

Background and the model matrix: [docs/research/2026-10-17-ai-helper-architecture.md](../research/2026-10-17-ai-helper-architecture.md)
§2.8 and §5.8.

**No LLM on the 8 GB pod.** The pod already gives 4 GB to the backend and 2 GB to PostgreSQL, and the backend runs the
solver. A 9B model on 4 shared CPU cores answers a multi-step helper turn in minutes. Use a separate GPU host on the
institution network. Only the feature index and the BM25 search run on the pod. They need no model.

## 1. Sizing

| Size | GPU | Model (example) | Context | Concurrent helper users |
|---|---|---|---|---|
| Small (pilot) | 1× 16 GB (RTX 4080 / A4000 class) | Qwen3.5-9B Q4 (`qwen3.5:9b` on Ollama, `Qwen/Qwen3.5-9B` on vLLM) | 16–32k | 1–3 |
| **Recommended** | 1× 24 GB (RTX 4090 / L4 / A5000 / A10) | **Qwen3-14B Q4** (`qwen3:14b`, benched for the helper) or Gemma 4 26B-A4B (`gemma4:26b`) | 16–32k | 5–10 |
| Large (faculty-wide) | 1× 48 GB (L40S / A6000) | Qwen3-32B or Gemma 4 31B at Q8 / FP8 | 32k+ | 10+ |

- The helper needs a model that can call tools and has a context of at least 8k tokens. Chat needs 16k or more.
  Pick one of the models above. Turkish-only fine-tunes (Kumru, Trendyol LLM, Cosmos) have no reliable tool calling,
  so use them for **explain** only.
- Memory rule of thumb: Q4 weights take about 0.6–0.7 GB per billion parameters, and 16k of context adds 1–2 GB on
  top. The HB-17 bench publishes measured numbers in `docs/testing/ai/2026-10-local-models.md`.
- Use **vLLM** for a shared service. It enforces strict tool schemas and supports named tool choice and batching.
  **Ollama** is fine for a pilot.
- **Which model for the helper (HB-17 re-bench, 2026-10-18, one 24 GB A10, Ollama, 16k context):** recommend
  **`qwen3:14b` (Q4, 24 GB GPU)**. It reached the booking confirm card 10/10, made 0 writes without a click and
  scored 35/40 overall, at p50 ≈ 10 s / p95 ≈ 29 s per AI turn. Use `qwen2.5:14b-instruct` only where "where is it"
  speed matters more than bookings (p50 3.5 s / p95 6.5 s, but 3/10 bookings and 28/40 overall). Details:
  `docs/testing/hb-17-local-bench-2026-10-18.md`, "Re-bench after HB-E".

## 2. vLLM on the GPU host (recommended)

The NVIDIA driver and the NVIDIA Container Toolkit must be installed. Pin the image by digest, as `deploy/pins.py`
does for the stack: `vllm/vllm-openai:v0.31.0@sha256:c1c9f6fd5c109ba7f0546a59f5b2f15fb87f64c77782e90a27b648b42a8e67c3`.

```sh
# a random key; SmartSched stores it write-only (Yapay zekâ › Sağlayıcılar › OpenAI uyumlu › Anahtar)
openssl rand -hex 24 > /etc/smartsched-llm.key
docker run -d --name vllm --restart unless-stopped --gpus all --ipc=host \
  -p 10.0.5.30:8000:8000 \
  -v /srv/hf-cache:/root/.cache/huggingface \
  vllm/vllm-openai:v0.31.0@sha256:c1c9f6fd5c109ba7f0546a59f5b2f15fb87f64c77782e90a27b648b42a8e67c3 \
  --model Qwen/Qwen3.5-9B \
  --served-model-name qwen3.5-9b \
  --max-model-len 32768 \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --api-key "$(cat /etc/smartsched-llm.key)"
```

- `--enable-auto-tool-choice --tool-call-parser <parser>` are required. Without them vLLM rejects every request that
  carries tools, so the helper falls back to index mode and chat fails. The parser depends on the model family. Use
  the flags on the model card: `qwen3_coder` for Qwen3.5, `hermes` for Qwen3 / Qwen2.5, and the Gemma 4 card's
  parser for Gemma 4.
- Bind the port to the host's **internal** address (`-p 10.0.5.30:8000:8000`), not `0.0.0.0`.
- The first start downloads the weights into `/srv/hf-cache`. Do the download in a maintenance window, never from
  SmartSched.
- Check: `curl -s -H "Authorization: Bearer $(cat /etc/smartsched-llm.key)" http://10.0.5.30:8000/v1/models` lists
  `qwen3.5-9b` with `max_model_len` 32768.

## 3. Ollama (pilot)

### On the GPU host

```sh
docker run -d --name ollama --restart unless-stopped --gpus all \
  -p 10.0.5.30:11434:11434 -v /srv/ollama:/root/.ollama \
  -e OLLAMA_CONTEXT_LENGTH=16384 -e OLLAMA_HOST=0.0.0.0:11434 \
  ollama/ollama:0.40.6@sha256:265409e1d931028a8f7d5a32bcbafddd7bffbc6cc629d77efe9560adf692a5e7
docker exec ollama ollama pull qwen3.5:9b
```

Without Docker there are two cases (HB-17 bench and re-bench, 2026-10-18):

- **The CLI runs as root** (cloud-init `runcmd`, a root shell script): **export `HOME=/root` before the first
  `ollama` command**. cloud-init runs `runcmd` without `$HOME`, and the `ollama` CLI then panics before it starts.

  ```sh
  # cloud-init runcmd (runs as root, without $HOME)
  export HOME=/root OLLAMA_CONTEXT_LENGTH=16384 OLLAMA_HOST=127.0.0.1:11434
  ollama serve &
  ollama pull qwen3:14b
  ```

- **The packaged `ollama.service`** (the install script's unit, `User=ollama`, with its own home directory): do **not**
  set `HOME=/root` there. The `ollama` user cannot write `/root/.ollama`, and the service then never starts (the
  re-bench lost a launch to this). Give the unit only the two Ollama variables, in a drop-in (`systemctl edit ollama`):

  ```ini
  [Service]
  Environment=OLLAMA_CONTEXT_LENGTH=16384
  Environment=OLLAMA_HOST=127.0.0.1:11434
  ```

  Then `systemctl daemon-reload && systemctl restart ollama`, and pull the model as root with `HOME` set
  (`HOME=/root ollama pull qwen3:14b`) or as the `ollama` user.

### Next to the stack (optional compose profile `ollama`)

`smartsched/deploy/docker-compose.yml` has an `ollama` service. It is **off by default** and starts only with the
profile. It publishes no port: only the backend reaches it, as `http://ollama:11434/v1` on the compose network. Use it
only on a host with a GPU and the memory for it (`OLLAMA_MEMORY`, default `12g`). Never use it on the 8 GB pod.

```sh
cd smartsched/deploy
docker compose --env-file .env --profile ollama config --services   # validates; lists "ollama"
docker compose --env-file .env --profile ollama up -d ollama
docker compose --env-file .env exec ollama ollama pull qwen3.5:9b    # the admin pulls the model, compose never does
```

For the GPU, add your own override file next to `.env` (it is not in the repository) and pass it with
`-f docker-compose.yml -f docker-compose.gpu.yml`:

```yaml
services:
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

- **`OLLAMA_CONTEXT_LENGTH` ≥ 16384** (`.env`, default 16384). Ollama's own default is much smaller and its OpenAI
  endpoint ignores `num_ctx`, so a small context silently cuts the helper's system prompt and tools. SmartSched clamps
  `max_tokens` to the synced context and refuses `context_too_small` before sending (HB-13), but only when the
  context is known.
- **The served window is what `GET /api/ps` shows**, not what `POST /api/show` shows. `/api/show` reports the model's
  maximum (`model_info.<arch>.context_length`, e.g. 32768 for Qwen2.5 14B). `/api/ps` reports `context_length` of a
  *loaded* model, which follows `OLLAMA_CONTEXT_LENGTH` (e.g. 16384). Check it on the host with
  `curl -s http://127.0.0.1:11434/api/ps`. SmartSched reads `/api/ps` at sync and again at the end of the probe, and
  stores the smaller of the two (HB-17 bug 2). If the model was not loaded at sync, the provider card and the route
  show **`context_unverified`** ("bağlam penceresi henüz bilinmiyor") until the probe (Test) has loaded it once.
- Ollama does not support `tool_choice`. SmartSched emulates single-tool features (rules, intake) with a JSON schema
  (HB-13). Multi-tool features (helper, chat) work, but Ollama does not enforce the argument schemas. The server
  validates every argument and the helper falls back to index mode after two bad rounds.

## 4. Firewall: only the backend talks to the model server

On the GPU host, allow the model port from the SmartSched backend host only (here `10.0.5.20`):

```sh
iptables -A INPUT -p tcp --dport 8000  -s 10.0.5.20 -j ACCEPT    # vLLM
iptables -A INPUT -p tcp --dport 11434 -s 10.0.5.20 -j ACCEPT    # Ollama
iptables -A INPUT -p tcp -m multiport --dports 8000,11434 -j DROP
# no route out: the model server needs no internet after the weights are on disk
iptables -A OUTPUT -o eth0 -d 10.0.0.0/8 -j ACCEPT
iptables -A OUTPUT -o eth0 -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -o eth0 -j DROP
```

Persist the rules with your distribution's tooling (`iptables-persistent`, `nftables.service`). The compose
profile needs no rule: the `ollama` service has no published port.

## 5. Register the server in SmartSched

Use the admin panel (**/admin/ai › Sağlayıcılar › OpenAI uyumlu**), or the API with an admin token:

```sh
API=https://smartsched.example.edu.tr/api/v1; H="Authorization: Bearer $ADMIN_TOKEN"
# 1. the server, with the local opt-in ("Yerel sunucu"); base_url must resolve to a private address
curl -sS -X PUT "$API/ai/admin/providers/openai_compatible" -H "$H" -H 'Content-Type: application/json' \
  -d '{"base_url": "http://10.0.5.30:8000/v1", "allow_local": true, "enabled": true,
       "api_key": "'"$(cat /etc/smartsched-llm.key)"'"}'
# 2. sync: lists the models and sniffs their capabilities (tools, tool_choice, json_schema, vision, context)
curl -sS -X POST "$API/ai/admin/providers/openai_compatible/sync" -H "$H"
# 3. probe: three small calls (forced tool + an auto retry, JSON schema, a 32x32 image; at most 512 output tokens
#    each, so a thinking model has room to reason first; a few thousand tokens in total, metered "test")
curl -sS -X POST "$API/ai/admin/providers/openai_compatible/test?probe=true" -H "$H" \
  -H 'Content-Type: application/json' -d '{"model": "qwen3.5-9b"}'
# 4. route the helper (and any other feature) to it; a model without tools is refused (422 model_lacks_capability)
curl -sS -X PUT "$API/ai/admin/routes" -H "$H" -H 'Content-Type: application/json' \
  -d '{"features": {"helper": {"provider": "openai_compatible", "model": "qwen3.5-9b"}}}'
```

For the compose profile, the base URL is `http://ollama:11434/v1` and the model is `qwen3.5:9b`. No key is needed.

- `allow_local` is the explicit opt-in for a loopback or private address. Without it the address guard refuses the
  URL (no SSRF to internal hosts). Plain `http` is accepted only for a local address.
- Sync shows the capabilities per model (`source: provider`). The probe overwrites them with measured values
  (`source: probe`). If a server hides them, an admin can set them per model (audited).
- The probe stores its findings only when at least one call reached the server, so a Test during an outage does not
  block routing. Its forced tool call uses a neutral message, so a server that ignores `tool_choice` (Ollama) shows
  `tool_choice: no`; SmartSched then sends a forced single tool as a JSON schema instead (HB-13).
- A probe call that proves nothing leaves that capability **unknown**, and sync's value stands: a call cut off at
  `max_tokens` with no answer (a thinking model that spent its budget reasoning), a lost connection, a timeout or a
  5xx (HB-F bugs A and D). Only a 4xx or a wrong answer is a "no". Unknown capabilities are left out of the probe's
  result line.
- **A free tunnel may rotate its host name.** A quick tunnel without an account (for example a `trycloudflare.com`
  URL) gets a new random host name on every restart, so the stored base URL stops working without any error on the
  model host. After a tunnel restart, update the base URL (step 1) and sync again; for anything beyond a test, use a
  named tunnel or the internal address. A tunnel host name resolves to a public address, so SmartSched treats it as a
  cloud transfer (section 6).
- Run the probe after the sync on an Ollama server: it loads the model, and its last step reads the served window
  from `/api/ps` (see section 3).
- **/admin/ai › Yardımcı** shows the helper's mode. Once a feature route exists, the person's status chip reads
  **Yerel model**.

Check the walk-through: as an academician with the `ai_personal` consent, ask the helper "Yarın için boş bir salon
bul". The answer must be in Turkish, come with `nav` / `list` cards, and add one `ai_usage` row with feature
`helper` and cost 0.

## 6. KVKK

- With a local route, personal data stays inside the institution. A local route needs **no transfer record**.
  SmartSched decides "local" from the **resolved** address of the base URL (private range or loopback), not from the
  host name (HB-13). A host name that resolves to a public address is treated as a cloud transfer and needs the
  transfer record and basis like any cloud provider.
- The model server is a processing system of the institution. Write it down in the processing inventory (VERBİS),
  including where it runs, who administers it, and that it keeps no prompts. vLLM and Ollama keep no conversation
  history. Do not turn on request logging on vLLM or debug logging on Ollama: both would write prompts to
  the logs.
- The same rules as for cloud routes apply: the redactor, the per-feature consent (`ai_personal` for the helper), the
  quotas (token quotas count; local cost is 0 unless an internal price is set) and the audit log.
- Keep the GPU host patched and inside the institution network (section 4). The model weights' licences (Apache-2.0
  for Qwen3.5, the Gemma terms for Gemma 4) allow this use. Keep a copy of the licence with the deployment record.

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Helper always answers from the index ("Rehber modu") | no `helper` route, `mode: index` in /admin/ai › Yardımcı, or no consent | route the helper (section 5), check the Yardımcı tab, check Profil › Gizlilik |
| `422 model_lacks_capability` when routing | sync / probe found no tool support | use a tool-capable model; for vLLM add `--enable-auto-tool-choice --tool-call-parser …` |
| `context_too_small` | the server's context is smaller than the prompt | raise `--max-model-len` / `OLLAMA_CONTEXT_LENGTH` to ≥ 16384, then sync again |
| `context_unverified` on the provider card or route | Ollama had not loaded the model at sync, so only its maximum is known | run **Test** (probe) once; it loads the model and reads `/api/ps` |
| `ollama` panics in cloud-init (`$HOME is not defined`) | the CLI runs as root without `HOME` | `export HOME=/root` before `ollama` in `runcmd`; never set `HOME=/root` in the packaged `ollama.service` (section 3) |
| `ollama.service` does not start after adding `Environment=HOME=/root` | the unit runs as `User=ollama`, which cannot use `/root` | remove that line; the unit needs only `OLLAMA_CONTEXT_LENGTH` and `OLLAMA_HOST` |
| The provider stops answering after the tunnel restarted | a free tunnel gave the server a new host name | update the base URL and sync again (section 5) |
| `unsafe_url` / address refused | `allow_local` off, or the name resolves to a public address | turn on "Yerel sunucu"; use the internal address |
| Slow first answer | the model loads on the first request | Ollama: `OLLAMA_KEEP_ALIVE` (compose sets 30m); vLLM loads at start |
