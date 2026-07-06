/**
 * TraceEvent — represents a single LLM call trace.
 * Matches the Ingest API request schema.
 */

class TraceEvent {
  /**
   * @param {Object} params
   * @param {string} params.model - Model identifier (e.g. "gpt-4o")
   * @param {string} params.prompt - The prompt sent to the LLM
   * @param {string} params.response - The LLM response
   * @param {number} params.inputTokens - Input token count
   * @param {number} params.outputTokens - Output token count
   * @param {number} params.latencyMs - Call latency in milliseconds
   * @param {string} [params.status="success"] - "success" or "error"
   * @param {string|null} [params.errorMessage=null] - Error description
   * @param {string|null} [params.sessionId=null] - Session identifier
   */
  constructor({
    model,
    prompt,
    response,
    inputTokens,
    outputTokens,
    latencyMs,
    status = "success",
    errorMessage = null,
    sessionId = null,
  }) {
    this.model = model;
    this.prompt = prompt;
    this.response = response;
    this.inputTokens = inputTokens;
    this.outputTokens = outputTokens;
    this.latencyMs = latencyMs;
    this.status = status;
    this.errorMessage = errorMessage;
    this.sessionId = sessionId;
  }

  /**
   * Convert to JSON payload matching the Ingest API schema.
   * @returns {Object}
   */
  toJSON() {
    const data = {
      model: this.model,
      prompt: this.prompt,
      response: this.response,
      input_tokens: this.inputTokens,
      output_tokens: this.outputTokens,
      latency_ms: this.latencyMs,
      status: this.status,
    };
    if (this.errorMessage !== null) {
      data.error_message = this.errorMessage;
    }
    if (this.sessionId !== null) {
      data.session_id = this.sessionId;
    }
    return data;
  }
}

module.exports = { TraceEvent };
