package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/arena-panel/arena/gateway/internal/limiter"
	"github.com/coder/websocket"
)

type config struct {
	listen             string
	apiURL             string
	secret             string
	instance           string
	websocketReadLimit int64
	trustProxyHeaders  bool
	trustedProxyHops   int
	trustCloudflare    bool
}

type gateway struct {
	config config
	client *http.Client
	limits *limiter.Registry
}

type authorizeRequest struct {
	UserID          string `json:"user_id"`
	NodeID          string `json:"node_id"`
	SourceIP        string `json:"source_ip"`
	UserAgent       string `json:"user_agent"`
	GatewayInstance string `json:"gateway_instance"`
}

type authorizeResponse struct {
	SessionID        string `json:"session_id"`
	UpstreamURL      string `json:"upstream_url"`
	SpeedLimitBPS    int64  `json:"speed_limit_bps"`
	HeartbeatSeconds int    `json:"heartbeat_seconds"`
}

type trafficRequest struct {
	SessionID     string `json:"session_id"`
	UplinkDelta   int64  `json:"uplink_delta"`
	DownlinkDelta int64  `json:"downlink_delta"`
	Reason        string `json:"reason,omitempty"`
}

type heartbeatResponse struct {
	Terminate     bool   `json:"terminate"`
	Reason        string `json:"reason"`
	SpeedLimitBPS int64  `json:"speed_limit_bps"`
}

type counters struct {
	uplink   atomic.Int64
	downlink atomic.Int64
}

func main() {
	cfg := config{
		listen:             env("ARENA_GATEWAY_LISTEN", ":8081"),
		apiURL:             strings.TrimRight(env("ARENA_API_URL", "http://arena:8000"), "/"),
		secret:             os.Getenv("ARENA_GATEWAY_SECRET"),
		instance:           env("HOSTNAME", "arena-gateway"),
		websocketReadLimit: envInt64("ARENA_GATEWAY_WS_READ_LIMIT_BYTES", 16*1024*1024),
		trustProxyHeaders:  envBool("ARENA_TRUST_PROXY_HEADERS", true),
		trustedProxyHops:   envInt("ARENA_TRUSTED_PROXY_HOPS", 1),
		trustCloudflare:    envBool("ARENA_TRUST_CLOUDFLARE_HEADER", false),
	}
	if len(cfg.secret) < 16 {
		log.Fatal("ARENA_GATEWAY_SECRET must be configured")
	}
	g := &gateway{
		config: cfg,
		client: &http.Client{Timeout: 8 * time.Second},
		limits: limiter.NewRegistry(),
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"status":"ok"}`)
	})
	mux.HandleFunc("/edge/", g.handleWebSocket)
	server := &http.Server{
		Addr:              cfg.listen,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
		IdleTimeout:       90 * time.Second,
	}
	log.Printf("ARENA gateway listening on %s websocket_read_limit=%d", cfg.listen, cfg.websocketReadLimit)
	log.Fatal(server.ListenAndServe())
}

func (g *gateway) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	nodeID, userID, ok := routeIDs(r.URL.Path)
	if !ok {
		http.Error(w, "invalid gateway route", http.StatusNotFound)
		return
	}
	auth, err := g.authorize(r.Context(), authorizeRequest{
		UserID: userID, NodeID: nodeID, SourceIP: g.sourceIP(r),
		UserAgent: r.UserAgent(), GatewayInstance: g.config.instance,
	})
	if err != nil {
		http.Error(w, err.Error(), http.StatusForbidden)
		return
	}

	upstreamHeader := http.Header{}
	upstreamHeader.Set("X-Forwarded-For", g.sourceIP(r))
	upstreamHeader.Set("X-Arena-Session", auth.SessionID)
	upstream, _, err := websocket.Dial(r.Context(), auth.UpstreamURL, &websocket.DialOptions{
		HTTPHeader:      upstreamHeader,
		CompressionMode: websocket.CompressionDisabled,
	})
	if err != nil {
		g.closeSession(context.Background(), auth.SessionID, 0, 0, "upstream_unavailable")
		http.Error(w, "upstream unavailable", http.StatusBadGateway)
		return
	}
	client, err := websocket.Accept(w, r, &websocket.AcceptOptions{
		InsecureSkipVerify: true,
		CompressionMode:    websocket.CompressionDisabled,
	})
	if err != nil {
		upstream.CloseNow()
		g.closeSession(context.Background(), auth.SessionID, 0, 0, "upgrade_failed")
		return
	}
	defer client.CloseNow()
	defer upstream.CloseNow()

	ctx, cancel := context.WithCancel(r.Context())
	defer cancel()
	bucket := g.limits.ForUser(userID, auth.SpeedLimitBPS)
	counts := &counters{}
	heartbeat := auth.HeartbeatSeconds
	if heartbeat < 5 {
		heartbeat = 15
	}
	heartbeatDone := make(chan struct{})
	go func() {
		defer close(heartbeatDone)
		g.heartbeatLoop(ctx, cancel, auth.SessionID, bucket, counts, time.Duration(heartbeat)*time.Second)
	}()

	errCh := make(chan error, 2)
	go func() { errCh <- relay(ctx, upstream, client, bucket, &counts.uplink, g.config.websocketReadLimit) }()
	go func() { errCh <- relay(ctx, client, upstream, bucket, &counts.downlink, g.config.websocketReadLimit) }()
	firstErr := <-errCh
	cancel()
	secondErr := <-errCh
	<-heartbeatDone
	err = firstErr
	if expectedRelayClose(firstErr) && !expectedRelayClose(secondErr) {
		err = secondErr
	}
	reason := "client_closed"
	if !expectedRelayClose(err) {
		reason = "transport_closed"
		log.Printf("session=%s user=%s node=%s relay stopped: %v", auth.SessionID, userID, nodeID, err)
	}
	g.closeSession(
		context.Background(), auth.SessionID,
		counts.uplink.Swap(0), counts.downlink.Swap(0), reason,
	)
}

func expectedRelayClose(err error) bool {
	if err == nil || errors.Is(err, context.Canceled) {
		return true
	}
	status := websocket.CloseStatus(err)
	return status == websocket.StatusNormalClosure || status == websocket.StatusGoingAway
}

func relay(ctx context.Context, dst, src *websocket.Conn, bucket *limiter.Bucket, counter *atomic.Int64, readLimit int64) error {
	src.SetReadLimit(readLimit)
	buffer := make([]byte, 32*1024)
	for {
		messageType, reader, err := src.Reader(ctx)
		if err != nil {
			return err
		}
		writer, err := dst.Writer(ctx, messageType)
		if err != nil {
			return err
		}
		for {
			n, readErr := reader.Read(buffer)
			if n > 0 {
				if err := bucket.Wait(ctx, n); err != nil {
					_ = writer.Close()
					return err
				}
				written, writeErr := writer.Write(buffer[:n])
				counter.Add(int64(written))
				if writeErr != nil {
					_ = writer.Close()
					return writeErr
				}
			}
			if errors.Is(readErr, io.EOF) {
				break
			}
			if readErr != nil {
				_ = writer.Close()
				return readErr
			}
		}
		if err := writer.Close(); err != nil {
			return err
		}
	}
}

func (g *gateway) heartbeatLoop(ctx context.Context, cancel context.CancelFunc, sessionID string, bucket *limiter.Bucket, counts *counters, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	failures := 0
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			payload := trafficRequest{
				SessionID:     sessionID,
				UplinkDelta:   counts.uplink.Swap(0),
				DownlinkDelta: counts.downlink.Swap(0),
			}
			var response heartbeatResponse
			if err := g.post(ctx, "/api/internal/gateway/heartbeat", payload, &response); err != nil {
				counts.uplink.Add(payload.UplinkDelta)
				counts.downlink.Add(payload.DownlinkDelta)
				failures++
				if failures >= 3 {
					cancel()
					return
				}
				continue
			}
			failures = 0
			bucket.SetRate(response.SpeedLimitBPS)
			if response.Terminate {
				cancel()
				return
			}
		}
	}
}

func (g *gateway) authorize(ctx context.Context, payload authorizeRequest) (authorizeResponse, error) {
	var response authorizeResponse
	err := g.post(ctx, "/api/internal/gateway/authorize", payload, &response)
	return response, err
}

func (g *gateway) closeSession(ctx context.Context, sessionID string, up, down int64, reason string) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	_ = g.post(ctx, "/api/internal/gateway/close", trafficRequest{
		SessionID: sessionID, UplinkDelta: up, DownlinkDelta: down, Reason: reason,
	}, nil)
}

func (g *gateway) post(ctx context.Context, path string, payload any, target any) error {
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, g.config.apiURL+path, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Arena-Gateway", g.config.secret)
	resp, err := g.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		limited, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("control plane rejected connection: %s", strings.TrimSpace(string(limited)))
	}
	if target != nil {
		return json.NewDecoder(resp.Body).Decode(target)
	}
	return nil
}

func (g *gateway) sourceIP(r *http.Request) string {
	if g.config.trustProxyHeaders {
		// The bundled Caddy ingress overwrites this header, so client-supplied
		// X-Forwarded-For values cannot influence policy decisions.
		if value := strings.TrimSpace(r.Header.Get("X-Arena-Client-IP")); net.ParseIP(value) != nil {
			return value
		}
		if value := strings.TrimSpace(r.Header.Get("CF-Connecting-IP")); g.config.trustCloudflare && net.ParseIP(value) != nil {
			return value
		}
		forwarded := strings.Split(r.Header.Get("X-Forwarded-For"), ",")
		index := len(forwarded) - g.config.trustedProxyHops
		if index >= 0 && index < len(forwarded) {
			value := strings.TrimSpace(forwarded[index])
			if net.ParseIP(value) != nil {
				return value
			}
		}
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err == nil {
		return host
	}
	return r.RemoteAddr
}

func routeIDs(path string) (string, string, bool) {
	parts := strings.Split(strings.Trim(strings.TrimPrefix(path, "/edge/"), "/"), "/")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return "", "", false
	}
	return parts[0], parts[1], true
}

func env(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func envBool(key string, fallback bool) bool {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseBool(value)
	return err == nil && parsed
}

func envInt(key string, fallback int) int {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil || parsed < 1 {
		return fallback
	}
	return parsed
}

func envInt64(key string, fallback int64) int64 {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.ParseInt(value, 10, 64)
	if err != nil || parsed < 1 {
		return fallback
	}
	return parsed
}
