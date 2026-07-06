// Package config provides configuration from environment variables.
package config

import (
	"os"
	"strconv"
)

// Config holds all gateway configuration.
type Config struct {
	Port           string
	IngestAPIURL   string
	RedisAddr      string
	RateLimitRPS   int
	RateLimitBurst int
	ReadTimeoutSec int
	WriteTimeoutSec int
}

// Load reads configuration from environment variables with sensible defaults.
func Load() *Config {
	return &Config{
		Port:            getEnv("GATEWAY_PORT", "3000"),
		IngestAPIURL:    getEnv("INGEST_API_URL", "http://localhost:8001"),
		RedisAddr:       getEnv("REDIS_HOST", "localhost") + ":" + getEnv("REDIS_PORT", "6379"),
		RateLimitRPS:    getEnvInt("RATE_LIMIT_RPS", 100),
		RateLimitBurst:  getEnvInt("RATE_LIMIT_BURST", 200),
		ReadTimeoutSec:  getEnvInt("READ_TIMEOUT_SEC", 10),
		WriteTimeoutSec: getEnvInt("WRITE_TIMEOUT_SEC", 10),
	}
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getEnvInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return fallback
}
