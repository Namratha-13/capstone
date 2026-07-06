/**
 * ObserveAI JavaScript SDK — auto-instrument LLM calls.
 *
 * Usage:
 *   const observeai = require('observeai-sdk');
 *   const { OpenAI } = require('openai');
 *
 *   const client = new OpenAI();
 *   const { shutdown } = observeai.init({
 *     apiKey: 'obs_xxx',
 *     endpoint: 'http://localhost:8001',
 *     openaiClient: client,
 *   });
 *
 *   // All subsequent client.chat.completions.create() calls are auto-instrumented.
 *   // Call shutdown() before process exit to flush pending events.
 */

const { ObserveAIClient } = require("./client");
const { TraceEvent } = require("./models");
const { patchOpenAI } = require("./interceptors/openai");
const { patchAnthropic } = require("./interceptors/anthropic");

/**
 * Initialize the ObserveAI SDK.
 *
 * @param {Object} options
 * @param {string} options.apiKey - ObserveAI API key (starts with obs_)
 * @param {string} [options.endpoint="http://localhost:8001"] - Ingest API URL
 * @param {boolean} [options.enabled=true] - Enable/disable tracing
 * @param {number} [options.flushIntervalMs=1000] - Flush interval in ms
 * @param {number} [options.maxBatchSize=10] - Max events per batch
 * @param {number} [options.timeoutMs=5000] - HTTP timeout in ms
 * @param {Object} [options.openaiClient] - OpenAI client instance to instrument
 * @param {Object} [options.anthropicClient] - Anthropic client instance to instrument
 *
 * @returns {{ capture: Function, shutdown: Function }}
 */
function init(options) {
  const {
    apiKey,
    endpoint = "http://localhost:8001",
    enabled = true,
    flushIntervalMs = 1000,
    maxBatchSize = 10,
    timeoutMs = 5000,
    openaiClient = null,
    anthropicClient = null,
  } = options;

  // Validate
  if (!apiKey) {
    throw new Error("ObserveAI apiKey is required");
  }
  if (!apiKey.startsWith("obs_")) {
    throw new Error("ObserveAI apiKey must start with 'obs_'");
  }

  // Create client
  const client = new ObserveAIClient({
    apiKey,
    endpoint,
    enabled,
    flushIntervalMs,
    maxBatchSize,
    timeoutMs,
  });

  client.start();

  // Install interceptors
  const unpatchers = [];

  if (enabled && openaiClient) {
    const unpatch = patchOpenAI(openaiClient, client);
    unpatchers.push(unpatch);
  }

  if (enabled && anthropicClient) {
    const unpatch = patchAnthropic(anthropicClient, client);
    unpatchers.push(unpatch);
  }

  return {
    /**
     * Manually capture a trace event.
     * @param {TraceEvent} event
     */
    capture(event) {
      client.capture(event);
    },

    /**
     * Flush pending events, remove interceptors, and shut down.
     */
    async shutdown() {
      unpatchers.forEach((fn) => fn());
      await client.shutdown();
    },
  };
}

module.exports = { init, TraceEvent };
