package limiter

import (
	"context"
	"testing"
	"time"
)

func TestUnlimitedReturnsImmediately(t *testing.T) {
	bucket := New(0)
	start := time.Now()
	if err := bucket.Wait(context.Background(), 1_000_000); err != nil {
		t.Fatal(err)
	}
	if time.Since(start) > 20*time.Millisecond {
		t.Fatal("unlimited bucket unexpectedly waited")
	}
}

func TestRegistrySharesBucketPerUser(t *testing.T) {
	registry := NewRegistry()
	first := registry.ForUser("user", 100)
	second := registry.ForUser("user", 200)
	if first != second {
		t.Fatal("expected one shared bucket per user")
	}
}

func TestWaitHandlesChunkLargerThanRate(t *testing.T) {
	bucket := New(1_000)
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	if err := bucket.Wait(ctx, 1_001); err != nil {
		t.Fatalf("chunk larger than one second of tokens never completed: %v", err)
	}
}
