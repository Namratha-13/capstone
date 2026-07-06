/**
 * Unit tests for the ObserveAI JavaScript SDK.
 */

const { init, TraceEvent } = require("../src/index");
const { ObserveAIClient } = require("../src/client");
const { formatMessages: formatOpenAI } = require("../src/interceptors/openai");
const {
  formatMessages: formatAnthropic,
} = require("../src/interceptors/anthropic");

// ── Init tests ───────────────────────────────────────────

describe("init()", () => {
  test("throws if apiKey is missing", () => {
    expect(() => init({})).toThrow("apiKey is required");
  });

  test("throws if apiKey does not start with obs_", () => {
    expect(() => init({ apiKey: "bad_key" })).toThrow("obs_");
  });

  test("returns capture and shutdown functions", async () => {
    const sdk = init({ apiKey: "obs_test123", enabled: false });
    expect(typeof sdk.capture).toBe("function");
    expect(typeof sdk.shutdown).toBe("function");
    await sdk.shutdown();
  });
});

// ── TraceEvent tests ─────────────────────────────────────

describe("TraceEvent", () => {
  test("toJSON returns correct shape", () => {
    const event = new TraceEvent({
      model: "gpt-4o",
      prompt: "hello",
      response: "world",
      inputTokens: 5,
      outputTokens: 3,
      latencyMs: 100,
    });

    const json = event.toJSON();
    expect(json.model).toBe("gpt-4o");
    expect(json.input_tokens).toBe(5);
    expect(json.output_tokens).toBe(3);
    expect(json.latency_ms).toBe(100);
    expect(json.status).toBe("success");
    expect(json.error_message).toBeUndefined();
    expect(json.session_id).toBeUndefined();
  });

  test("toJSON includes error_message when set", () => {
    const event = new TraceEvent({
      model: "gpt-4o",
      prompt: "hello",
      response: "",
      inputTokens: 0,
      outputTokens: 0,
      latencyMs: 50,
      status: "error",
      errorMessage: "Rate limited",
    });

    const json = event.toJSON();
    expect(json.status).toBe("error");
    expect(json.error_message).toBe("Rate limited");
  });

  test("toJSON includes session_id when set", () => {
    const event = new TraceEvent({
      model: "gpt-4o",
      prompt: "hello",
      response: "world",
      inputTokens: 5,
      outputTokens: 3,
      latencyMs: 100,
      sessionId: "sess_123",
    });

    const json = event.toJSON();
    expect(json.session_id).toBe("sess_123");
  });
});

// ── Client tests ─────────────────────────────────────────

describe("ObserveAIClient", () => {
  test("capture adds to queue when enabled", () => {
    const client = new ObserveAIClient({
      apiKey: "obs_test",
      endpoint: "http://localhost:8001",
      enabled: true,
    });

    const event = new TraceEvent({
      model: "gpt-4o",
      prompt: "test",
      response: "response",
      inputTokens: 10,
      outputTokens: 5,
      latencyMs: 100,
    });

    client.capture(event);
    expect(client._queue.length).toBe(1);
  });

  test("capture is a no-op when disabled", () => {
    const client = new ObserveAIClient({
      apiKey: "obs_test",
      endpoint: "http://localhost:8001",
      enabled: false,
    });

    const event = new TraceEvent({
      model: "gpt-4o",
      prompt: "test",
      response: "response",
      inputTokens: 10,
      outputTokens: 5,
      latencyMs: 100,
    });

    client.capture(event);
    expect(client._queue.length).toBe(0);
  });
});

// ── OpenAI interceptor format tests ──────────────────────

describe("OpenAI formatMessages", () => {
  test("formats messages array", () => {
    const result = formatOpenAI([
      { role: "system", content: "You are helpful" },
      { role: "user", content: "Hello" },
    ]);
    expect(result).toContain("[system] You are helpful");
    expect(result).toContain("[user] Hello");
  });

  test("handles null/empty input", () => {
    expect(formatOpenAI(null)).toBe("");
    expect(formatOpenAI([])).toBe("");
  });
});

// ── Anthropic interceptor format tests ───────────────────

describe("Anthropic formatMessages", () => {
  test("formats messages with system prompt", () => {
    const result = formatAnthropic(
      [{ role: "user", content: "Hello" }],
      "Be concise"
    );
    expect(result).toContain("[system] Be concise");
    expect(result).toContain("[user] Hello");
  });

  test("handles structured content blocks", () => {
    const result = formatAnthropic([
      {
        role: "user",
        content: [{ type: "text", text: "What is this?" }],
      },
    ]);
    expect(result).toContain("What is this?");
  });

  test("handles empty messages", () => {
    expect(formatAnthropic(null)).toBe("");
    expect(formatAnthropic([])).toBe("");
  });
});

// ── OpenAI interceptor patching tests ────────────────────

describe("patchOpenAI", () => {
  const { patchOpenAI } = require("../src/interceptors/openai");

  test("returns noop when client has no chat.completions", () => {
    const unpatch = patchOpenAI({}, new ObserveAIClient({
      apiKey: "obs_test",
      endpoint: "http://localhost:8001",
    }));
    expect(typeof unpatch).toBe("function");
    unpatch(); // Should not throw
  });

  test("patches and unpatches correctly", async () => {
    const mockCreate = jest.fn().mockResolvedValue({
      choices: [{ message: { content: "hi" } }],
      usage: { prompt_tokens: 5, completion_tokens: 3 },
    });

    const fakeClient = {
      chat: {
        completions: {
          create: mockCreate,
        },
      },
    };

    const observeClient = new ObserveAIClient({
      apiKey: "obs_test",
      endpoint: "http://localhost:8001",
    });

    const unpatch = patchOpenAI(fakeClient, observeClient);

    // Call patched version
    const result = await fakeClient.chat.completions.create({
      model: "gpt-4o",
      messages: [{ role: "user", content: "hello" }],
    });

    expect(result.choices[0].message.content).toBe("hi");
    expect(observeClient._queue.length).toBe(1);
    expect(observeClient._queue[0].model).toBe("gpt-4o");

    // Unpatch
    unpatch();
  });
});

// ── Anthropic interceptor patching tests ─────────────────

describe("patchAnthropic", () => {
  const { patchAnthropic } = require("../src/interceptors/anthropic");

  test("returns noop when client has no messages", () => {
    const unpatch = patchAnthropic({}, new ObserveAIClient({
      apiKey: "obs_test",
      endpoint: "http://localhost:8001",
    }));
    expect(typeof unpatch).toBe("function");
    unpatch();
  });

  test("patches and captures anthropic calls", async () => {
    const mockCreate = jest.fn().mockResolvedValue({
      content: [{ type: "text", text: "Hello!" }],
      usage: { input_tokens: 10, output_tokens: 5 },
    });

    const fakeClient = {
      messages: {
        create: mockCreate,
      },
    };

    const observeClient = new ObserveAIClient({
      apiKey: "obs_test",
      endpoint: "http://localhost:8001",
    });

    const unpatch = patchAnthropic(fakeClient, observeClient);

    const result = await fakeClient.messages.create({
      model: "claude-3-5-sonnet",
      messages: [{ role: "user", content: "hi" }],
    });

    expect(result.content[0].text).toBe("Hello!");
    expect(observeClient._queue.length).toBe(1);
    expect(observeClient._queue[0].model).toBe("claude-3-5-sonnet");

    unpatch();
  });
});
