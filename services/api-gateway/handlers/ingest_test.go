package handlers

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// ── Health endpoint tests ────────────────────────────────

func TestHealthz(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rec := httptest.NewRecorder()

	Healthz(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}

	var resp HealthResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %s", err)
	}

	if resp.Status != "ok" {
		t.Errorf("expected status=ok, got %s", resp.Status)
	}
	if resp.Service != "api-gateway" {
		t.Errorf("expected service=api-gateway, got %s", resp.Service)
	}
}

// ── Ingest handler tests ─────────────────────────────────

func TestHandleIngest_MethodNotAllowed(t *testing.T) {
	h := NewIngestHandler("http://localhost:8001")
	req := httptest.NewRequest(http.MethodGet, "/v1/traces", nil)
	rec := httptest.NewRecorder()

	h.HandleIngest(rec, req)

	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", rec.Code)
	}
}

func TestHandleIngest_InvalidJSON(t *testing.T) {
	h := NewIngestHandler("http://localhost:8001")
	body := strings.NewReader(`{invalid json}`)
	req := httptest.NewRequest(http.MethodPost, "/v1/traces", body)
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	h.HandleIngest(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestHandleIngest_MissingModel(t *testing.T) {
	h := NewIngestHandler("http://localhost:8001")
	payload := `{"prompt":"hello","response":"world","input_tokens":5,"output_tokens":3,"latency_ms":100}`
	req := httptest.NewRequest(http.MethodPost, "/v1/traces", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	h.HandleIngest(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "model") {
		t.Errorf("expected error about 'model' field, got: %s", rec.Body.String())
	}
}

func TestHandleIngest_NegativeTokens(t *testing.T) {
	h := NewIngestHandler("http://localhost:8001")
	payload := `{"model":"gpt-4o","prompt":"hello","response":"world","input_tokens":-1,"output_tokens":3,"latency_ms":100}`
	req := httptest.NewRequest(http.MethodPost, "/v1/traces", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	h.HandleIngest(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestHandleIngest_InvalidStatus(t *testing.T) {
	h := NewIngestHandler("http://localhost:8001")
	payload := `{"model":"gpt-4o","prompt":"hello","response":"world","input_tokens":5,"output_tokens":3,"latency_ms":100,"status":"unknown"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/traces", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	h.HandleIngest(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestHandleIngest_ValidPayload_ProxiesToIngestAPI(t *testing.T) {
	// Create a mock Ingest API
	mockIngest := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		w.Write([]byte(`{"trace_id":"test-uuid-123","status":"accepted","message":"Trace event accepted for processing"}`))
	}))
	defer mockIngest.Close()

	h := NewIngestHandler(mockIngest.URL)
	payload := `{"model":"gpt-4o","prompt":"hello","response":"world","input_tokens":5,"output_tokens":3,"latency_ms":100,"status":"success"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/traces", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer obs_testkey123")
	rec := httptest.NewRecorder()

	h.HandleIngest(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d | body: %s", rec.Code, rec.Body.String())
	}

	var resp map[string]interface{}
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("failed to decode response: %s", err)
	}

	if resp["trace_id"] != "test-uuid-123" {
		t.Errorf("expected trace_id=test-uuid-123, got %v", resp["trace_id"])
	}
	if resp["status"] != "accepted" {
		t.Errorf("expected status=accepted, got %v", resp["status"])
	}
}

func TestHandleIngest_IngestAPIDown(t *testing.T) {
	// Point to a non-existent server
	h := NewIngestHandler("http://localhost:1")
	payload := `{"model":"gpt-4o","prompt":"hello","response":"world","input_tokens":5,"output_tokens":3,"latency_ms":100,"status":"success"}`
	req := httptest.NewRequest(http.MethodPost, "/v1/traces", strings.NewReader(payload))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	h.HandleIngest(rec, req)

	if rec.Code != http.StatusBadGateway {
		t.Fatalf("expected 502, got %d", rec.Code)
	}
}

// ── Validation tests ─────────────────────────────────────

func TestTraceRequestValidation(t *testing.T) {
	tests := []struct {
		name    string
		trace   traceRequest
		wantErr bool
	}{
		{
			name:    "valid success trace",
			trace:   traceRequest{Model: "gpt-4o", Prompt: "hi", Response: "hello", InputTokens: 5, OutputTokens: 3, LatencyMs: 100, Status: "success"},
			wantErr: false,
		},
		{
			name:    "valid error trace without response",
			trace:   traceRequest{Model: "gpt-4o", Prompt: "hi", Response: "", InputTokens: 0, OutputTokens: 0, LatencyMs: 50, Status: "error"},
			wantErr: false,
		},
		{
			name:    "missing model",
			trace:   traceRequest{Model: "", Prompt: "hi", Response: "hello", InputTokens: 5, OutputTokens: 3, LatencyMs: 100},
			wantErr: true,
		},
		{
			name:    "missing prompt",
			trace:   traceRequest{Model: "gpt-4o", Prompt: "", Response: "hello", InputTokens: 5, OutputTokens: 3, LatencyMs: 100},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.trace.validate()
			if (err != nil) != tt.wantErr {
				t.Errorf("validate() error = %v, wantErr = %v", err, tt.wantErr)
			}
		})
	}
}
