package handlers

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"
)

// IngestHandler proxies validated trace requests to the FastAPI Ingest API.
type IngestHandler struct {
	IngestAPIURL string
	HTTPClient   *http.Client
}

// NewIngestHandler creates a new handler with a configured HTTP client.
func NewIngestHandler(ingestURL string) *IngestHandler {
	return &IngestHandler{
		IngestAPIURL: ingestURL,
		HTTPClient: &http.Client{
			Timeout: 10 * time.Second,
		},
	}
}

// traceRequest is used to validate the incoming JSON payload structure.
type traceRequest struct {
	Model        string  `json:"model"`
	Prompt       string  `json:"prompt"`
	Response     string  `json:"response"`
	InputTokens  int     `json:"input_tokens"`
	OutputTokens int     `json:"output_tokens"`
	LatencyMs    int     `json:"latency_ms"`
	Status       string  `json:"status"`
	ErrorMessage *string `json:"error_message,omitempty"`
	SessionID    *string `json:"session_id,omitempty"`
}

// validate checks required fields.
func (t *traceRequest) validate() error {
	if t.Model == "" {
		return fmt.Errorf("field 'model' is required")
	}
	if t.Prompt == "" {
		return fmt.Errorf("field 'prompt' is required")
	}
	if t.Response == "" && t.Status != "error" {
		return fmt.Errorf("field 'response' is required for successful traces")
	}
	if t.InputTokens < 0 {
		return fmt.Errorf("field 'input_tokens' must be >= 0")
	}
	if t.OutputTokens < 0 {
		return fmt.Errorf("field 'output_tokens' must be >= 0")
	}
	if t.LatencyMs < 0 {
		return fmt.Errorf("field 'latency_ms' must be >= 0")
	}
	if t.Status != "" && t.Status != "success" && t.Status != "error" {
		return fmt.Errorf("field 'status' must be 'success' or 'error'")
	}
	return nil
}

// HandleIngest validates the request body and proxies to the Ingest API.
func (h *IngestHandler) HandleIngest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"detail":"Method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	// Read body (limit to 1MB)
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20))
	if err != nil {
		http.Error(w, `{"detail":"Failed to read request body"}`, http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	// Parse and validate
	var trace traceRequest
	if err := json.Unmarshal(body, &trace); err != nil {
		http.Error(w, fmt.Sprintf(`{"detail":"Invalid JSON: %s"}`, err.Error()), http.StatusBadRequest)
		return
	}

	if err := trace.validate(); err != nil {
		http.Error(w, fmt.Sprintf(`{"detail":"Validation error: %s"}`, err.Error()), http.StatusBadRequest)
		return
	}

	// Proxy to Ingest API
	proxyURL := fmt.Sprintf("%s/v1/traces", h.IngestAPIURL)
	proxyReq, err := http.NewRequestWithContext(r.Context(), http.MethodPost, proxyURL, io.NopCloser(
		// Re-use the raw body to preserve exact payload
		newBytesReader(body),
	))
	if err != nil {
		log.Printf("[ingest] proxy request creation failed: %s", err)
		http.Error(w, `{"detail":"Internal gateway error"}`, http.StatusInternalServerError)
		return
	}

	// Forward headers
	proxyReq.Header.Set("Content-Type", "application/json")
	proxyReq.Header.Set("Authorization", r.Header.Get("Authorization"))

	// Execute proxy request
	resp, err := h.HTTPClient.Do(proxyReq)
	if err != nil {
		log.Printf("[ingest] proxy request failed: %s", err)
		http.Error(w, `{"detail":"Ingest API unavailable"}`, http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	// Forward response
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		log.Printf("[ingest] failed to read proxy response: %s", err)
		http.Error(w, `{"detail":"Failed to read upstream response"}`, http.StatusBadGateway)
		return
	}

	// Copy response headers
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	w.Write(respBody)

	log.Printf("[ingest] proxied → %d | model=%s", resp.StatusCode, trace.Model)
}

// bytesReader wraps a byte slice as an io.Reader.
type bytesReader struct {
	data []byte
	pos  int
}

func newBytesReader(data []byte) *bytesReader {
	return &bytesReader{data: data}
}

func (r *bytesReader) Read(p []byte) (n int, err error) {
	if r.pos >= len(r.data) {
		return 0, io.EOF
	}
	n = copy(p, r.data[r.pos:])
	r.pos += n
	return n, nil
}
