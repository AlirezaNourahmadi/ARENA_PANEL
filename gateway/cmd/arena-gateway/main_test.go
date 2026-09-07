package main

import (
	"net/http/httptest"
	"testing"
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
