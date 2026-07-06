// Package handlers provides HTTP request handlers for the API gateway.
package handlers

import (
	"encoding/json"
	"net/http"
)

// HealthResponse is the JSON response for the health check endpoint.
type HealthResponse struct {
	Status  string `json:"status"`
	Service string `json:"service"`
}

// Healthz returns a simple health check response.
func Healthz(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(HealthResponse{
		Status:  "ok",
		Service: "api-gateway",
	})
}
