/**
 * Anthropic interceptor — wraps the Anthropic Node SDK to auto-capture traces.
 *
 * Monkey-patches `messages.create` on any Anthropic instance.
 */

const { TraceEvent } = require("../models");

/**
 * Format Anthropic messages into a readable string.
 * @param {Array} messages
 * @param {string} [system=""]
 * @returns {string}
 */
function formatMessages(messages, system = "") {
  const parts = [];
  if (system) {
    parts.push(`[system] ${system}`);
  }
  if (!messages || !Array.isArray(messages)) return parts.join("\n");

  for (const msg of messages) {
    const role = msg.role || "unknown";
    let content = msg.content || "";

    // Anthropic supports structured content blocks
    if (Array.isArray(content)) {
      content = content
        .filter((block) => block.type === "text")
        .map((block) => block.text || "")
        .join("\n");
    }

    parts.push(`[${role}] ${content}`);
  }

  return parts.join("\n");
}

/**
 * Patch an Anthropic client instance to intercept message creation.
 * @param {Object} anthropicClient - An Anthropic client instance
 * @param {import('../client').ObserveAIClient} observeClient - The ObserveAI client
 * @returns {Function} unpatch function
 */
function patchAnthropic(anthropicClient, observeClient) {
  if (!anthropicClient || !anthropicClient.messages) {
    return () => {};
  }

  const original = anthropicClient.messages.create.bind(
    anthropicClient.messages
  );

  anthropicClient.messages.create = async function (params, ...rest) {
    const start = performance.now();

    try {
      const result = await original(params, ...rest);
      const latencyMs = Math.round(performance.now() - start);

      // Extract response text from content blocks
      let responseText = "";
      if (result.content && Array.isArray(result.content)) {
        responseText = result.content
          .filter((block) => block.type === "text")
          .map((block) => block.text || "")
          .join("\n");
      }

      // Extract tokens
      const inputTokens = result.usage?.input_tokens || 0;
      const outputTokens = result.usage?.output_tokens || 0;

      const event = new TraceEvent({
        model: params.model || "unknown",
        prompt: formatMessages(params.messages, params.system),
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
        prompt: formatMessages(params.messages, params.system),
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
    anthropicClient.messages.create = original;
  };
}

module.exports = { patchAnthropic, formatMessages };
