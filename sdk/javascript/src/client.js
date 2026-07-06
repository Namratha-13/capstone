/**
 * HTTP client that sends trace events to the ObserveAI Ingest API.
 * Uses batching with a flush interval for non-blocking operation.
 */

const http = require("http");
const https = require("https");

class ObserveAIClient {
  /**
   * @param {Object} config
   * @param {string} config.apiKey
   * @param {string} config.endpoint
   * @param {number} [config.flushIntervalMs=1000]
   * @param {number} [config.maxBatchSize=10]
   * @param {number} [config.timeoutMs=5000]
   */
  constructor(config) {
    this.apiKey = config.apiKey;
    this.endpoint = config.endpoint;
    this.flushIntervalMs = config.flushIntervalMs || 1000;
    this.maxBatchSize = config.maxBatchSize || 10;
    this.timeoutMs = config.timeoutMs || 5000;
    this.enabled = config.enabled !== false;

    /** @type {import('./models').TraceEvent[]} */
    this._queue = [];
    this._timer = null;
  }

  /** Start the background flush timer. */
  start() {
    if (this._timer) return;
    this._timer = setInterval(() => this._flush(), this.flushIntervalMs);
    // Allow the process to exit even if the timer is running
    if (this._timer.unref) this._timer.unref();
  }

  /**
   * Enqueue a trace event.
   * @param {import('./models').TraceEvent} event
   */
  capture(event) {
    if (!this.enabled) return;
    this._queue.push(event);
    if (this._queue.length >= this.maxBatchSize) {
      this._flush();
    }
  }

  /** Flush remaining events and stop the timer. */
  async shutdown() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
    await this._flush();
  }

  /** @private */
  async _flush() {
    if (this._queue.length === 0) return;

    const batch = this._queue.splice(0, this.maxBatchSize);
    const promises = batch.map((event) => this._send(event));

    try {
      await Promise.allSettled(promises);
    } catch (err) {
      // Swallow errors — SDK should never crash user code
    }
  }

  /**
   * Send a single event to the Ingest API.
   * @private
   * @param {import('./models').TraceEvent} event
   */
  _send(event) {
    return new Promise((resolve, reject) => {
      const payload = JSON.stringify(event.toJSON());
      const url = new URL(`${this.endpoint}/v1/traces`);
      const transport = url.protocol === "https:" ? https : http;

      const options = {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname,
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload),
          Authorization: `Bearer ${this.apiKey}`,
        },
        timeout: this.timeoutMs,
      };

      const req = transport.request(options, (res) => {
        let body = "";
        res.on("data", (chunk) => (body += chunk));
        res.on("end", () => {
          if (res.statusCode === 202) {
            resolve(body);
          } else {
            reject(new Error(`Ingest API returned ${res.statusCode}: ${body.slice(0, 200)}`));
          }
        });
      });

      req.on("error", (err) => reject(err));
      req.on("timeout", () => {
        req.destroy();
        reject(new Error("Request timed out"));
      });

      req.write(payload);
      req.end();
    });
  }
}

module.exports = { ObserveAIClient };
