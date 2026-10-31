/* ht-helperbot — WebLLM engine worker.
 *
 * The whole WebLLM/TVM engine (model weights, WASM runtime, GPU
 * work) lives in this dedicated module worker, created by
 * helper/ht-helper.js through WebLLM's CreateWebWorkerMLCEngine.
 * A GPU failure, shader-compile error or out-of-memory kill in here
 * can only take this worker down; the page and the helper bot's
 * index answers are unaffected, and the page side falls back to
 * index answers for the rest of the session.
 *
 * The library import is the exact same pinned CDN build the page
 * uses; jsDelivr serves it with Access-Control-Allow-Origin: *, so
 * the cross-origin module import is allowed inside a worker.
 */
import { WebWorkerMLCEngineHandler } from 'https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.79/+esm';

const handler = new WebWorkerMLCEngineHandler();
self.onmessage = (msg) => { handler.onmessage(msg); };
