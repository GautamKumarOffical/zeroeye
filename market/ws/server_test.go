package ws

import (
	"net/http/httptest"
	"testing"
)

func TestCheckOriginAccepted(t *testing.T) {
	check := makeCheckOrigin([]string{"http://localhost:3000", "http://example.com"})
	r := httptest.NewRequest("GET", "/ws", nil)
	r.Header.Set("Origin", "http://localhost:3000")
	if !check(r) {
		t.Error("expected origin http://localhost:3000 to be accepted")
	}
}

func TestCheckOriginRejected(t *testing.T) {
	check := makeCheckOrigin([]string{"http://localhost:3000"})
	r := httptest.NewRequest("GET", "/ws", nil)
	r.Header.Set("Origin", "http://evil.com")
	if check(r) {
		t.Error("expected origin http://evil.com to be rejected")
	}
}

func TestCheckOriginEmptyAllowed(t *testing.T) {
	check := makeCheckOrigin([]string{"http://localhost:3000"})
	r := httptest.NewRequest("GET", "/ws", nil)
	if !check(r) {
		t.Error("request with no Origin header should be accepted")
	}
}

func TestCheckOriginDynamicEnv(t *testing.T) {
	check := makeCheckOrigin([]string{"http://custom-origin.dev"})
	r := httptest.NewRequest("GET", "/ws", nil)
	r.Header.Set("Origin", "http://custom-origin.dev")
	if !check(r) {
		t.Error("expected custom origin to be accepted")
	}
	r2 := httptest.NewRequest("GET", "/ws", nil)
	r2.Header.Set("Origin", "http://other.com")
	if check(r2) {
		t.Error("expected other origin to be rejected")
	}
}

func TestParseAllowedOriginsDefault(t *testing.T) {
	origins := parseAllowedOrigins()
	if len(origins) == 0 {
		t.Error("expected default origins to be non-empty")
	}
	found := false
	for _, o := range origins {
		if o == "http://localhost:3000" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected http://localhost:3000 in default origins")
	}
}
