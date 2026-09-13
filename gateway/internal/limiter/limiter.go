package limiter

import (
	"context"
	"sync"
	"time"
)

type Bucket struct {
	mu     sync.Mutex
	rate   int64
	tokens float64
	last   time.Time
}

func New(rate int64) *Bucket {
	now := time.Now()
	return &Bucket{rate: rate, tokens: float64(rate), last: now}
}

func (b *Bucket) SetRate(rate int64) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.refill(time.Now())
	b.rate = rate
	if rate == 0 {
		b.tokens = 0
	} else if b.tokens > float64(rate) {
		b.tokens = float64(rate)
	}
}

func (b *Bucket) Wait(ctx context.Context, bytes int) error {
	if bytes <= 0 {
		return nil
	}
	remaining := int64(bytes)
	for remaining > 0 {
		b.mu.Lock()
		now := time.Now()
		b.refill(now)
		if b.rate <= 0 {
			b.mu.Unlock()
			return nil
		}
		request := remaining
		if request > b.rate {
			request = b.rate
		}
		if b.tokens >= float64(request) {
			b.tokens -= float64(request)
			remaining -= request
			b.mu.Unlock()
			continue
		}
		missing := float64(request) - b.tokens
		wait := time.Duration(missing / float64(b.rate) * float64(time.Second))
		if wait < time.Millisecond {
			wait = time.Millisecond
		}
		b.mu.Unlock()
		timer := time.NewTimer(wait)
		select {
		case <-ctx.Done():
			timer.Stop()
			return ctx.Err()
		case <-timer.C:
		}
	}
	return nil
}

func (b *Bucket) refill(now time.Time) {
	if b.last.IsZero() {
		b.last = now
	}
	if b.rate > 0 {
		b.tokens += now.Sub(b.last).Seconds() * float64(b.rate)
		if b.tokens > float64(b.rate) {
			b.tokens = float64(b.rate)
		}
	}
	b.last = now
}

type Registry struct {
	mu      sync.Mutex
	buckets map[string]*Bucket
}

func NewRegistry() *Registry {
	return &Registry{buckets: make(map[string]*Bucket)}
}

func (r *Registry) ForUser(userID string, rate int64) *Bucket {
	r.mu.Lock()
	defer r.mu.Unlock()
	bucket, ok := r.buckets[userID]
	if !ok {
		bucket = New(rate)
		r.buckets[userID] = bucket
	} else {
		bucket.SetRate(rate)
	}
	return bucket
}
