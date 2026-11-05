# Independence Tests A–G — actual results

Run: `python scripts/independence_test.py` (2026-11-05 14:55 UTC). Raw output with every check's evidence:
[independence_results.json](independence_results.json). **Result: all 7 tests passed.**

Environment: 4 vCPU x86-64, 16.9 GB RAM, **no GPU**, llama-cpp-python 0.3.36. Fresh database and Archive in a temporary
directory; models imported through the API with checksum verification (no download during the test).
Models: chat `qwen2.5-1.5b-instruct-q4_k_m`, eco `qwen2.5-0.5b-instruct-q4_k_m`, embedding `nomic-embed-text-v1.5-q8_0`,
replacement `smollm2-360m-instruct-q8_0`.

How "offline" was achieved: Tests B, D, E and G ran inside a new Linux network namespace (`unshare -n`) in which only
the loopback interface exists. The test first proved that `huggingface.co` and `api.anthropic.com` were unreachable
(connection errors at the OS level, even through the egress proxy), then started the server there.

| Test | Result | What was verified (evidence in the JSON) |
|---|---|---|
| **A — External provider shutdown** | ✅ PASS (41.5 s) | All `ANTHROPIC_*`/`OLLAMA_*` variables removed and no stored credential. `/api/ai/status` reported no mandatory external runtime dependency. G-SUS chat answered from the local 1.5B model ("I am G-SUS, the intelligence orchestrator of Demonkoncernen AB.", 9.6 s); classification ran on the local 0.5B model (label `negative`); schema-constrained extraction returned `{"product": "The Aurora lamp", "price": 49.0}`; a G-sus creative run completed using the local model (1 AI call, $0). Zero external attempts recorded. |
| **B — Offline operation** | ✅ PASS (6.5 s) | Internet unreachable. Offline mode on: every chain listed Anthropic as `excluded_offline` — **with a (fake) Anthropic key deliberately present** to prove there is no silent fallback. Local model answered in Swedish (6.0 s). An agent task (`system.self_evaluate`) succeeded. Memory write + read worked. Model download refused (409). Zero external attempts. |
| **C — Model replacement** | ✅ PASS (23.3 s) | The same `/api/ai/chat` call was served by `qwen2.5-1.5b…` and, after activating a different model family, by `smollm2-360m…`. Classification and a G-sus run still completed on the replacement. Rollback restored the previous models. |
| **D — Local embeddings** | ✅ PASS (0.7 s) | Three documents uploaded offline; every stored vector came from `gguf:nomic-embed-text-v1.5-q8_0`. A semantic query sharing no keywords with the target ("sun-powered light for outdoor sleeping") returned the solar-lantern document first. |
| **E — Agent continuity** | ✅ PASS (30.2 s) | G-sus planned and ran "Evaluate the winter commuter pannier and convene a council" offline: product evaluation, an 8-seat creative council, verification and answer — tasks succeeded for CEO, CFO, brand studio, advertising, the Flare engine/council and many persona agents through the in-process orchestrator. Zero external attempts. |
| **F — Recovery** | ✅ PASS (11.8 s) | Offline mode + ECO profile set, a memory written and a task queued; the server was killed with **SIGKILL** and the task forced to `running` (mid-flight). After restart: settings and active models recovered, the local model reloaded and answered, memory and Archive search intact, and the interrupted task was requeued and **succeeded** (attempt 2). |
| **G — Security** | ✅ PASS (0.6 s) | Anonymous calls to 10 AI/DAEMON/memory/Archive endpoints → 401; forged token → 401; viewer → 403 on chat, settings, credentials, model install; operator → 403 on settings, credentials, model activation. The only listening socket in the namespace was the API on 127.0.0.1 (the model runtime opens none). Security headers present. Six wrong passwords → locked out (429). |

## What these results do and do not mean

* **Do:** Demonkoncernen AB's core AI — generation, classification, structured extraction, embeddings, memory, Archive
  search, multi-agent orchestration — runs on its own hardware with no external service at runtime, survives a crash,
  swaps models behind a stable API, and keeps local services behind authentication.
* **Do not:** the local models are small. Measured on the 12-task benchmark: Qwen2.5 0.5B 10/12, Qwen2.5 1.5B 9/12;
  **both failed every Swedish task**. Independence here means *able to operate without outside providers*, not *as
  capable as frontier models*. See [DAEMON_CORE.md §7](DAEMON_CORE.md).
* **Install-time dependencies remain** (PyPI/npm packages, model weights from Hugging Face or a verified offline copy).
  They are not needed at runtime.
* An earlier run of this script failed Tests A and C because the test asked G-sus about a product that does not exist
  in the demo data — G-sus correctly asked for clarification instead of inventing one. The objective was corrected; the
  run reported above is the first complete run after that fix.

Re-run the tests after any change to routing, models or security: `python scripts/independence_test.py`
(requires the four catalogued models installed — see [INSTALL.md](INSTALL.md)).
