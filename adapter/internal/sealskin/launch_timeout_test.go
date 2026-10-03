package sealskin

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestLaunchWaitsForOrderedStartupWithoutReplaying(t *testing.T) {
	for _, tc := range []struct {
		name      string
		cancel    bool
		longLimit time.Duration
	}{
		{"long_startup", false, time.Second},
		{"caller_cancel", true, time.Second},
		{"long_budget_expires", false, 40 * time.Millisecond},
	} {
		t.Run(tc.name, func(t *testing.T) {
			serverKey, clientKey := testKeys(t)
			fake := &fakeSealSkinServer{serverPrivate: serverKey, clientPublic: &clientKey.PublicKey}
			var launches atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path == "/api/launch/url" {
					launches.Add(1)
					select {
					case <-time.After(150 * time.Millisecond):
					case <-r.Context().Done():
						return
					}
				}
				fake.ServeHTTP(w, r)
			}))
			defer server.Close()
			client := newTestClient(t, server.URL, serverKey, clientKey, server.Client())
			// Complete the handshake before shortening query timeouts. The delay is
			// on the mutation endpoint after it has received the one launch request.
			if _, err := client.ListSessions(context.Background()); err != nil {
				t.Fatal(err)
			}
			client.httpClient.Timeout = 20 * time.Millisecond
			client.longClient.Timeout = tc.longLimit
			ctx := context.Background()
			if tc.cancel {
				var cancel context.CancelFunc
				ctx, cancel = context.WithTimeout(ctx, 60*time.Millisecond)
				defer cancel()
			}
			result, err := client.LaunchURL(ctx, LaunchURLRequest{URL: "https://entry.example/start", ApplicationID: "firefox", HomeName: "qa"}, "one-durable-operation")
			if tc.cancel || tc.longLimit < 150*time.Millisecond {
				var ambiguous *AmbiguousMutationError
				if !errors.As(err, &ambiguous) {
					t.Fatalf("want ambiguous mutation, got %T %v", err, err)
				}
			} else if err != nil || result.SessionID != "browser-1" {
				t.Fatalf("ordered launch: %v, %v", result, err)
			}
			if n := launches.Load(); n != 1 {
				t.Fatalf("launch sends=%d, want one", n)
			}
			if err == nil {
				fake.mu.Lock()
				defer fake.mu.Unlock()
				if fake.launchIdempotency != "one-durable-operation" {
					t.Fatal("idempotency key changed")
				}
			}
		})
	}
}
