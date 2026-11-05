# Independence Tests A–G — actual results

Run: `python scripts/independence_test.py`. Latest run: 2026-11-05 21:23 UTC (after the Archive index and the research SSRF guard) — **all 7 tests passed**.
Raw output with every check's evidence: [independence_results.json](independence_results.json); every run, including
failed ones, is kept in [independence_runs/](independence_runs/).

Environment: 4 vCPU x86-64, 16.9 GB RAM, **no GPU**, llama-cpp-python 0.3.36. Fresh database and Archive in a temporary
directory; models imported through the API with checksum verification (no download during the test).
Models: chat `qwen2.5-1.5b-instruct-q4_k_m`, eco `qwen2.5-0.5b-instruct-q4_k_m`, **deep `qwen3-4b-q4_k_m` (reasoning)**,
embedding `nomic-embed-text-v1.5-q8_0`, replacement `smollm2-360m-instruct-q8_0`.

How "offline" was achieved: Tests B, D, E and G ran inside a new Linux network namespace (`unshare -n`) in which only
the loopback interface exists. The test first proved that `huggingface.co` and `api.anthropic.com` were unreachable
(connection errors at the OS level, even through the egress proxy), then started the server there.

| Test | Result | What was verified (evidence in the JSON) |
|---|---|---|
| **A — External provider shutdown** | ✅ PASS (338 s) | All `ANTHROPIC_*`/`OLLAMA_*` variables removed, no stored credential; `/api/ai/status` reported no mandatory external runtime dependency. G-SUS chat answered from the local 1.5B model; classification on the 0.5B model; schema-constrained extraction returned `{"product": "Aurora lamp", "price": 49.0}`. **Deep reasoning** on the local Qwen3 4B with self-consistency (3 samples) on a multi-step margin problem: sample answers −40, 80, 80 → majority **80** (correct), 303 s. A G-sus creative run completed on the local model. Zero external attempts. |
| **B — Offline operation** | ✅ PASS (89 s) | Internet unreachable. Offline mode on, every chain listed Anthropic as `excluded_offline` — **with a (fake) Anthropic key deliberately present**, proving there is no silent fallback. Local chat answered; **deep reasoning offline** (single sample) solved the VAT problem: 240 SEK incl. 25 % VAT → **192** (80 s). An agent task succeeded, memory write + read worked, model download refused (409). Zero external attempts. |
| **C — Model replacement** | ✅ PASS (21 s) | The same `/api/ai/chat` call was served by `qwen2.5-1.5b…` and, after activating a different model family, by `smollm2-360m…`; classification and a G-sus run still worked; rollback restored all four slots. |
| **D — Local embeddings** | ✅ PASS (0.7 s) | Every stored vector came from `gguf:nomic-embed-text-v1.5-q8_0`; a semantic query sharing no keywords with the target found the right document. |
| **E — Agent continuity** | ✅ PASS (22 s) | G-sus planned and ran "Evaluate the winter commuter pannier and convene a council" offline; CEO, CFO, brand studio, advertising, the Flare engine/council and many persona agents succeeded through the in-process orchestrator. Zero external attempts. |
| **F — Recovery** | ✅ PASS (10 s) | Server killed with **SIGKILL** mid-task; after restart settings, all active models (incl. deep), memory and Archive were intact, the local model answered, and the interrupted task was requeued and succeeded. |
| **G — Security** | ✅ PASS (0.6 s) | Anonymous → 401 on 10 endpoints; forged token → 401; viewer and operator → 403 on admin functions; the only listening socket is the API on 127.0.0.1; security headers present; brute-force login locked out (429). |

## Run history (nothing removed)

| Run (UTC) | Result | What happened |
|---|---|---|
| 14:55 | 7/7 passed | Before the deep slot existed (no deep-reasoning checks). `independence_runs/2026-11-05T1455-before-deep-slot.json` |
| 16:59 | A failed, 6/7 | First run with deep-reasoning checks. A's single-sample answer to the margin problem was wrong; the evidence then kept only the first 160 characters. `…T1659-deep-run1-A-failed.json` |
| 17:10 | A failed, 6/7 | Same failure, now with the full answer captured: the model counted the marketplace's 40 SEK cut as *income* and answered **−40**. Identical output to 16:59 — a fresh process starts from the same sampling seed. In a separate process the same prompt was answered correctly (80) twice. `…T1710-deep-run2-A-failed-answer-minus40.json` |
| 17:26 | **7/7 passed** | Test A's deep check switched to **self-consistency** (`samples: 3`), the mode now recommended for answers that matter (decision D-015). The check still requires the exact answer 80. The first sample was again −40; the next two were 80 → majority 80. Test B's deep check stayed single-sample and passed. |

## What these results do and do not mean

* **Do:** Demonkoncernen AB's core AI — generation, classification, structured extraction, **deep multi-step reasoning**,
  embeddings, memory, Archive search, multi-agent orchestration — runs on its own hardware with no external service at
  runtime, survives a crash, swaps models behind a stable API, and keeps local services behind authentication.
* **Do not:** a single answer from the 4B reasoning model can be confidently wrong (measured above). Self-consistency
  raised reliability on that problem; it does not prove correctness. Deep reasoning on this CPU takes ~1–5 minutes per
  sample. Independence means *able to operate without outside providers*, not *as capable as frontier models*.
* **Install-time dependencies remain** (PyPI/npm packages, model weights from Hugging Face or a verified offline copy).
  They are not needed at runtime.
* The 14:55 run is also preceded by a failed run (earlier the same day) in which G-sus correctly asked for clarification
  about a product that did not exist in the demo data; the test objective was corrected.

Re-run after any change to routing, models or security: `python scripts/independence_test.py`
(requires the five catalogued models installed — see [INSTALL.md](INSTALL.md)). Takes ~10 minutes on this CPU.
