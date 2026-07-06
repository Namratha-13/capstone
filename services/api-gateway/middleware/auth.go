// Package middleware provides HTTP middleware for the API gateway.
package middleware

import (
	"log"
	"net/http"
	"strings"
)

// Auth validates the Authorization header format.
// Full key validation is delegated to the downstream Ingest API.
// The gateway only checks that a Bearer token with the obs_ prefix is present.
func Auth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		auth := r.Header.Get("Authorization")
		if auth == "" {
			http.Error(w, `{"detail":"Missing Authorization header"}`, http.StatusUnauthorized)
			return
		}

		if !strings.HasPrefix(auth, "Bearer ") {
			http.Error(w, `{"detail":"Malformed Authorization header. Expected: Bearer obs_xxx"}`, http.StatusUnauthorized)
			return
		}

		token := strings.TrimPrefix(auth, "Bearer ")
		token = strings.TrimSpace(token)

		if !strings.HasPrefix(token, "obs_") {
			http.Error(w, `{"detail":"Invalid API key format. Keys must start with obs_"}`, http.StatusUnauthorized)
			return
		}

		if len(token) < 8 {
			http.Error(w, `{"detail":"API key too short"}`, http.StatusUnauthorized)
			return
		}

		log.Printf("[auth] key=%s… validated", token[:8])
		next.ServeHTTP(w, r)
	})
}
