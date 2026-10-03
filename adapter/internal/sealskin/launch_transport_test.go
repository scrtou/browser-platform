package sealskin

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestOrderedLaunchUsesFullBudgetWithVerifiedTLSTransport(t *testing.T) {
	for _, tc := range []struct {
		name   string
		cancel bool
		budget time.Duration
	}{
		{"delayed_headers", false, time.Second}, {"caller_cancel", true, time.Second}, {"total_budget", false, 60 * time.Millisecond},
	} {
		t.Run(tc.name, func(t *testing.T) {
			serverKey, clientKey := testKeys(t)
			fake := &fakeSealSkinServer{serverPrivate: serverKey, clientPublic: &clientKey.PublicKey}
			var slowQuery atomic.Bool
			var launches atomic.Int32
			server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				delayed := r.URL.Path == "/api/sessions" && slowQuery.Load()
				if r.URL.Path == "/api/launch/url" {
					launches.Add(1)
					delayed = true
				}
				if delayed {
					select {
					case <-time.After(200 * time.Millisecond):
					case <-r.Context().Done():
						return
					}
				}
				fake.ServeHTTP(w, r)
			}))
			defer server.Close()
			transport := server.Client().Transport.(*http.Transport).Clone()
			transport.ResponseHeaderTimeout = 40 * time.Millisecond
			transport.TLSClientConfig.MinVersion = tls.VersionTLS12
			defer transport.CloseIdleConnections()
			serverDER, _ := x509.MarshalPKIXPublicKey(&serverKey.PublicKey)
			clientDER, _ := x509.MarshalPKCS8PrivateKey(clientKey)
			client, err := NewClient(Config{BaseURL: server.URL, Username: "tester", Transport: transport,
				ServerPublicKeyPEM:  pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: serverDER}),
				ClientPrivateKeyPEM: pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: clientDER}),
				Now:                 func() time.Time { return time.Unix(2_000_000_000, 0) },
			})
			if err != nil {
				t.Fatal(err)
			}
			if _, err = client.ListSessions(context.Background()); err != nil {
				t.Fatal(err)
			}
			slowQuery.Store(true)
			if _, err = client.ListSessions(context.Background()); err == nil {
				t.Fatal("ordinary query lost its short header deadline")
			}
			slowQuery.Store(false)
			if client.longClient.Timeout != LongOperationTimeout {
				t.Fatal("production total startup budget changed")
			}
			client.longClient.Timeout = tc.budget
			ctx := context.Background()
			if tc.cancel {
				var cancel context.CancelFunc
				ctx, cancel = context.WithTimeout(ctx, 80*time.Millisecond)
				defer cancel()
			}
			result, err := client.LaunchURL(ctx, LaunchURLRequest{URL: "https://entry.example/start", ApplicationID: "firefox", HomeName: "qa"}, "one-tls-launch")
			if tc.cancel || tc.budget < 200*time.Millisecond {
				var ambiguous *AmbiguousMutationError
				if !errors.As(err, &ambiguous) {
					t.Fatalf("canceled mutation must remain ambiguous: %v", err)
				}
			} else if err != nil || result.SessionID != "browser-1" {
				t.Fatalf("long TLS startup was truncated by query transport: %v", err)
			}
			if launches.Load() != 1 {
				t.Fatalf("mutation replayed: %d", launches.Load())
			}
			longTransport, ok := client.longClient.Transport.(*http.Transport)
			if !ok || longTransport == transport {
				t.Fatal("long operation shares the query transport")
			}
			defer longTransport.CloseIdleConnections()
			if client.httpClient.Transport != transport || transport.ResponseHeaderTimeout != 40*time.Millisecond {
				t.Fatal("caller/query transport mutated")
			}
			if longTransport.TLSClientConfig.InsecureSkipVerify || longTransport.TLSClientConfig.RootCAs != transport.TLSClientConfig.RootCAs || longTransport.TLSClientConfig.MinVersion != tls.VersionTLS12 {
				t.Fatal("TLS verification policy changed")
			}
			if err == nil {
				fake.mu.Lock()
				defer fake.mu.Unlock()
				if fake.launchIdempotency != "one-tls-launch" {
					t.Fatal("durable operation key changed")
				}
			}
		})
	}
}
