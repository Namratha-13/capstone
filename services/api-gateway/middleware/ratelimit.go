package middleware

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

// RateLimiter provides per-API-key rate limiting using Redis token bucket.
type RateLimiter struct {
	client *redis.Client
	rps    int
	burst  int
}

// NewRateLimiter creates a Redis-backed rate limiter.
// If Redis is unavailable, it falls back to an in-memory limiter.
func NewRateLimiter(redisAddr string, rps, burst int) *RateLimiter {
	client := redis.NewClient(&redis.Options{
		Addr:         redisAddr,
		ReadTimeout:  2 * time.Second,
		WriteTimeout: 2 * time.Second,
		DialTimeout:  2 * time.Second,
	})

	// Test connection
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		log.Printf("[ratelimit] Redis unavailable (%s), using in-memory fallback", err)
		return &RateLimiter{client: nil, rps: rps, burst: burst}
	}

	log.Printf("[ratelimit] Redis connected at %s (rps=%d, burst=%d)", redisAddr, rps, burst)
	return &RateLimiter{client: client, rps: rps, burst: burst}
}

// inMemoryBuckets is a simple fallback when Redis is not available.
var (
	inMemBuckets   = make(map[string]*tokenBucket)
	inMemBucketsMu sync.Mutex
)

type tokenBucket struct {
	tokens     float64
	maxTokens  float64
	refillRate float64
	lastRefill time.Time
}

func (b *tokenBucket) allow() bool {
	now := time.Now()
	elapsed := now.Sub(b.lastRefill).Seconds()
	b.tokens = min(b.maxTokens, b.tokens+elapsed*b.refillRate)
	b.lastRefill = now

	if b.tokens >= 1 {
		b.tokens--
		return true
	}
	return false
}

func min(a, b float64) float64 {
	if a < b {
		return a
	}
	return b
}

// Allow checks whether a request from the given key is allowed.
func (rl *RateLimiter) Allow(ctx context.Context, key string) (bool, error) {
	if rl.client == nil {
		return rl.allowInMemory(key), nil
	}
	return rl.allowRedis(ctx, key)
}

func (rl *RateLimiter) allowInMemory(key string) bool {
	inMemBucketsMu.Lock()
	defer inMemBucketsMu.Unlock()

	bucket, ok := inMemBuckets[key]
	if !ok {
		bucket = &tokenBucket{
			tokens:     float64(rl.burst),
			maxTokens:  float64(rl.burst),
			refillRate: float64(rl.rps),
			lastRefill: time.Now(),
		}
		inMemBuckets[key] = bucket
	}

	return bucket.allow()
}

func (rl *RateLimiter) allowRedis(ctx context.Context, key string) (bool, error) {
	redisKey := fmt.Sprintf("ratelimit:%s", key)

	// Use a simple sliding window counter
	now := time.Now().Unix()
	windowKey := fmt.Sprintf("%s:%d", redisKey, now)

	pipe := rl.client.Pipeline()
	incr := pipe.Incr(ctx, windowKey)
	pipe.Expire(ctx, windowKey, 2*time.Second)
	_, err := pipe.Exec(ctx)
	if err != nil {
		log.Printf("[ratelimit] Redis error: %s, allowing request", err)
		return true, nil // Fail open
	}

	count := incr.Val()
	return count <= int64(rl.rps), nil
}

// Middleware returns an HTTP middleware that rate-limits per API key.
func (rl *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Extract API key from Authorization header
		auth := r.Header.Get("Authorization")
		key := "anonymous"
		if strings.HasPrefix(auth, "Bearer ") {
			token := strings.TrimPrefix(auth, "Bearer ")
			if len(token) >= 8 {
				key = token[:8] // Use prefix as rate limit key
			}
		}

		allowed, err := rl.Allow(r.Context(), key)
		if err != nil {
			log.Printf("[ratelimit] error: %s", err)
			// Fail open
			next.ServeHTTP(w, r)
			return
		}

		if !allowed {
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("Retry-After", "1")
			w.WriteHeader(http.StatusTooManyRequests)
			w.Write([]byte(`{"detail":"Rate limit exceeded. Please retry after 1 second."}`))
			return
		}

		next.ServeHTTP(w, r)
	})
}
