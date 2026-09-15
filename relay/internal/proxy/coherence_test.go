package proxy

import (
	"encoding/json"
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func writeGate(t *testing.T, path, generation, state string, sequence uint64, lifetime time.Duration) {
	t.Helper()
	now := time.Now()
	raw, err := json.Marshal(gateRecord{1, generation, sequence, state, now.UnixMilli(), now.Add(lifetime).UnixMilli()})
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path+".new", raw, 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(path+".new", path); err != nil {
		t.Fatal(err)
	}
}

func TestCoherenceGateRevokesTunnelsButKeepsObservationPath(t *testing.T) {
	for _, mutation := range []string{"blocked", "deleted", "expired", "wrong-generation", "permissions"} {
		t.Run(mutation, func(t *testing.T) {
			upstream := testPeer(t, nil, func(conn net.Conn) {
				if _, err := peerRequest(conn, protocolHTTP, authNone); err != nil {
					return
				}
				if peerSuccess(conn, protocolHTTP, nil) != nil {
					return
				}
				_, _ = io.Copy(conn, conn)
			})
			cfg := testRuntime(t, upstream, protocolHTTP, authNone, nil)
			path, generation := filepath.Join(t.TempDir(), "gate.json"), strings.Repeat("a", 64)
			cfg.CoherenceGateFile, cfg.CoherenceGeneration = path, generation
			cfg.CoherenceProbeDomain, cfg.CoherenceProbePort = "observe.test", 18443
			writeGate(t, path, generation, "open", 1, time.Minute)
			address, _, _ := testRelay(t, cfg)
			checkDenied := func(req request) {
				t.Helper()
				conn, reply, err := clientConnect(address, req)
				if conn != nil {
					conn.Close()
				}
				if err != nil || reply != replyDenied {
					t.Fatalf("expected gate denial, got %d %v", reply, err)
				}
			}
			// A grant written before Relay startup cannot be replayed.
			checkDenied(domainRequest("site.test", 443))
			for _, host := range []string{"observe.test.attacker.test", "extra.observe.test", strings.Repeat("a", 32) + ".other.test"} {
				checkDenied(domainRequest(host, 18443))
			}
			checkDenied(domainRequest("observe.test", 443))
			writeGate(t, path, generation, "open", 2, time.Minute)
			conn, reply, err := clientConnect(address, domainRequest("site.test", 443))
			if err != nil || reply != replySucceeded {
				t.Fatalf("grant failed: %d %v", reply, err)
			}
			defer conn.Close()
			if _, err := conn.Write([]byte("ping")); err != nil {
				t.Fatal(err)
			}
			buffer := make([]byte, 4)
			if _, err := io.ReadFull(conn, buffer); err != nil || string(buffer) != "ping" {
				t.Fatal("tunnel did not carry bytes")
			}
			switch mutation {
			case "blocked":
				writeGate(t, path, generation, "blocked", 3, time.Minute)
			case "deleted":
				if err := os.Remove(path); err != nil {
					t.Fatal(err)
				}
			case "expired":
				writeGate(t, path, generation, "open", 3, 80*time.Millisecond)
			case "wrong-generation":
				writeGate(t, path, strings.Repeat("b", 64), "open", 3, time.Minute)
			case "permissions":
				if err := os.Chmod(path, 0644); err != nil {
					t.Fatal(err)
				}
			}
			_ = conn.SetReadDeadline(time.Now().Add(2 * time.Second))
			if _, err := conn.Read(buffer); err == nil {
				t.Fatal("tunnel survived closed gate")
			} else if timed, ok := err.(net.Error); ok && timed.Timeout() {
				t.Fatal("gate did not cancel existing connection")
			}
			checkDenied(domainRequest("site.test", 443))
			probe, reply, err := clientConnect(address, domainRequest(strings.Repeat("c", 32)+".observe.test", 18443))
			if probe != nil {
				probe.Close()
			}
			if err != nil || reply != replySucceeded {
				t.Fatalf("probe blocked: %d %v", reply, err)
			}
			writeGate(t, path, generation, "open", 2, time.Minute)
			checkDenied(domainRequest("site.test", 443))
			writeGate(t, path, generation, "open", 4, time.Minute)
			restored, reply, err := clientConnect(address, domainRequest("site.test", 443))
			if restored != nil {
				restored.Close()
			}
			if err != nil || reply != replySucceeded {
				t.Fatalf("new validated grant failed: %d %v", reply, err)
			}
		})
	}
}

func TestCoherenceGateConfigurationAppliesToBothModes(t *testing.T) {
	base := Config{ListenAddress: "127.0.0.1:1080", UpstreamHost: "127.0.0.1", UpstreamPort: 9000,
		CoherenceGateFile: "gate.json", CoherenceGeneration: strings.Repeat("a", 64),
		CoherenceProbeDomain: "observe.test", CoherenceProbePort: 18443}
	if cfg, err := base.Resolve(t.TempDir()); err != nil || cfg.CoherenceGateFile == "" {
		t.Fatalf("valid config: %v", err)
	}
	for _, mode := range []string{"proxy_required", "direct"} {
		bad := base
		bad.Mode, bad.CoherenceGeneration = mode, ""
		if _, err := bad.Resolve(t.TempDir()); err == nil {
			t.Fatal("partial gate accepted in " + mode)
		}
	}
}
