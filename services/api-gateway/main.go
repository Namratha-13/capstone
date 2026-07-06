// ObserveAI API Gateway — Go HTTP server
//
// Sits in front of the FastAPI Ingest API, providing:
// 1. API key format validation
// 2. Rate limiting (Redis-backed, with in-memory fallback)
// 3. Request payload validation
// 4. Reverse proxy to Ingest API
package main

import (
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/observeai/api-gateway/config"
	"github.com/observeai/api-gateway/handlers"
	"github.com/observeai/api-gateway/middleware"
)

func main() {
	cfg := config.Load()

	// Initialize rate limiter
	rateLimiter := middleware.NewRateLimiter(cfg.RedisAddr, cfg.RateLimitRPS, cfg.RateLimitBurst)

	// Initialize handlers
	ingestHandler := handlers.NewIngestHandler(cfg.IngestAPIURL)

	// Set up routes
	mux := http.NewServeMux()

	// Health check — no auth or rate limiting
	mux.HandleFunc("/healthz", handlers.Healthz)

	// Trace ingestion — auth + rate limiting
	tracesHandler := middleware.Auth(
		rateLimiter.Middleware(
			http.HandlerFunc(ingestHandler.HandleIngest),
		),
	)
	mux.Handle("/v1/traces", tracesHandler)

	// Configure server
	server := &http.Server{
		Addr:         fmt.Sprintf(":%s", cfg.Port),
		Handler:      loggingMiddleware(mux),
		ReadTimeout:  time.Duration(cfg.ReadTimeoutSec) * time.Second,
		WriteTimeout: time.Duration(cfg.WriteTimeoutSec) * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	log.Printf("ObserveAI API Gateway starting on :%s", cfg.Port)
	log.Printf("  → Ingest API: %s", cfg.IngestAPIURL)
	log.Printf("  → Rate limit: %d rps / %d burst", cfg.RateLimitRPS, cfg.RateLimitBurst)

	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("Server failed: %s", err)
	}
}

// loggingMiddleware logs every request with method, path, status, and duration.
func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		sw := &statusWriter{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(sw, r)
		log.Printf("%s %s → %d (%s)", r.Method, r.URL.Path, sw.status, time.Since(start))
	})
}

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) WriteHeader(code int) {
	w.status = code
	w.ResponseWriter.WriteHeader(code)
}
