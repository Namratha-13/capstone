/**
 * OpenAI interceptor — wraps the OpenAI Node SDK to auto-capture traces.
 *
 * Monkey-patches `chat.completions.create` on any OpenAI instance.
 */

const { TraceEvent } = require("../models");

let _patched = false;

/**
 * Format OpenAI messages array into a readable string.
 * @param {Array} messages
 * @returns {string}
 */
function formatMessages(messages) {
  if (!messages || !Array.isArray(messages)) return "";
  return messages
    .map((msg) => `[${msg.role || "unknown"}] ${msg.content || ""}`)
    .join("\n");
}

/**
 * Patch an OpenAI client instance to intercept chat completions.
 * @param {Object} openaiClient - An OpenAI client instance
 * @param {import('../client').ObserveAIClient} observeClient - The ObserveAI client
 * @returns {Function} unpatch function
 */
function patchOpenAI(openaiClient, observeClient) {
  if (!openaiClient || !openaiClient.chat || !openaiClient.chat.completions) {
    return () => {};
  }

  const original = openaiClient.chat.completions.create.bind(
    openaiClient.chat.completions
  );

  openaiClient.chat.completions.create = async function (params, ...rest) {
    const start = performance.now();
    let status = "success";
    let errorMessage = null;

    try {
      const result = await original(params, ...rest);
      const latencyMs = Math.round(performance.now() - start);

      // Extract response
      let responseText = "";
      if (result.choices && result.choices[0]) {
        responseText = result.choices[0].message?.content || "";
      }

      // Extract tokens
      const inputTokens = result.usage?.prompt_tokens || 0;
      const outputTokens = result.usage?.completion_tokens || 0;

      const event = new TraceEvent({
        model: params.model || "unknown",
        prompt: formatMessages(params.messages),
        response: responseText,
        inputTokens,
        outputTokens,
        latencyMs,
        status: "success",
      });

      observeClient.capture(event);
      return result;
    } catch (err) {
      const latencyMs = Math.round(performance.now() - start);

      const event = new TraceEvent({
        model: params.model || "unknown",
        prompt: formatMessages(params.messages),
        response: "",
        inputTokens: 0,
        outputTokens: 0,
        latencyMs,
        status: "error",
        errorMessage: String(err).slice(0, 2000),
      });

      observeClient.capture(event);
      throw err;
    }
  };

  return function unpatch() {
    openaiClient.chat.completions.create = original;
  };
}

module.exports = { patchOpenAI, formatMessages };
