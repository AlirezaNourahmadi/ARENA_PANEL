package main

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/arena-panel/arena/gateway/internal/limiter"
	"github.com/coder/websocket"
)

func TestSourceIPUsesTrustedHopFromRight(t *testing.T) {
	g := &gateway{config: config{trustProxyHeaders: true, trustedProxyHops: 1}}
	request := httptest.NewRequest("GET", "http://gateway/edge/node/user", nil)
	request.Header.Set("X-Forwarded-For", "203.0.113.99, 192.0.2.44")
	if actual := g.sourceIP(request); actual != "192.0.2.44" {
		t.Fatalf("expected nearest trusted client address, got %s", actual)
	}
}

func TestIngressClientIPOverridesForwardedChain(t *testing.T) {
	g := &gateway{config: config{trustProxyHeaders: true, trustedProxyHops: 1}}
	request := httptest.NewRequest("GET", "http://gateway/edge/node/user", nil)
	request.Header.Set("X-Arena-Client-IP", "192.0.2.88")
	request.Header.Set("X-Forwarded-For", "203.0.113.99")
	if actual := g.sourceIP(request); actual != "192.0.2.88" {
		t.Fatalf("expected ingress-authenticated address, got %s", actual)
	}
}

func TestCloudflareHeaderRequiresExplicitTrust(t *testing.T) {
	request := httptest.NewRequest("GET", "http://gateway/edge/node/user", nil)
	request.Header.Set("CF-Connecting-IP", "203.0.113.10")
	request.Header.Set("X-Forwarded-For", "192.0.2.20")
	g := &gateway{config: config{trustProxyHeaders: true, trustedProxyHops: 1}}
	if actual := g.sourceIP(request); actual != "192.0.2.20" {
		t.Fatalf("untrusted Cloudflare header was accepted: %s", actual)
	}
	g.config.trustCloudflare = true
	if actual := g.sourceIP(request); actual != "203.0.113.10" {
		t.Fatalf("trusted Cloudflare header was ignored: %s", actual)
	}
}

func TestRelayAllowsLargeWebSocketMessage(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	payload := bytes.Repeat([]byte("a"), 256*1024)

	sourceServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer conn.CloseNow()
		if conn.Write(ctx, websocket.MessageBinary, payload) == nil {
			<-ctx.Done()
		}
	}))

	received := make(chan []byte, 1)
	destinationServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := websocket.Accept(w, r, nil)
		if err != nil {
			return
		}
		defer conn.CloseNow()
		conn.SetReadLimit(int64(len(payload) + 1))
		_, data, err := conn.Read(ctx)
		if err == nil {
			received <- data
			<-ctx.Done()
		}
	}))

	dial := func(serverURL string) *websocket.Conn {
		conn, _, err := websocket.Dial(ctx, "ws"+strings.TrimPrefix(serverURL, "http"), nil)
		if err != nil {
			t.Fatal(err)
		}
		return conn
	}
	source := dial(sourceServer.URL)
	destination := dial(destinationServer.URL)
	defer func() {
		cancel()
		source.CloseNow()
		destination.CloseNow()
		sourceServer.Close()
		destinationServer.Close()
	}()

	var counter atomic.Int64
	errCh := make(chan error, 1)
	go func() {
		errCh <- relay(ctx, destination, source, limiter.New(0), &counter, int64(len(payload)+1))
	}()

	select {
	case data := <-received:
		if !bytes.Equal(data, payload) {
			t.Fatal("relayed payload was corrupted")
		}
		if counter.Load() != int64(len(payload)) {
			t.Fatalf("expected %d counted bytes, got %d", len(payload), counter.Load())
		}
	case err := <-errCh:
		t.Fatalf("relay stopped before delivering the payload: %v", err)
	case <-ctx.Done():
		t.Fatal("timed out waiting for relayed payload")
	}
}
