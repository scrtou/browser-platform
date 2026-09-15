package proxy

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/netip"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func nativeDirectConfig(t *testing.T) Config {
	t.Helper()
	const path = "/proc/self/net/fib_trie"
	hosts, err := hostPublicIPv4(path)
	if err != nil {
		t.Skip("routed native IPv4 host is required for the procfs integration test")
	}
	return Config{Mode: "direct", ListenAddress: "127.0.0.1:0", ApprovedResolverID: "qa-resolver",
		ApprovedResolverIP: "1.1.1.1", HostIPv4File: path, HostIPv4Snapshot: hosts, DialTimeoutSeconds: 1}
}

func TestDirectConfigurationIsExplicitAndRejectsMixedOptions(t *testing.T) {
	cfg := nativeDirectConfig(t)
	runtime, err := cfg.Resolve("")
	if err != nil || runtime.Mode != "direct" || runtime.UpstreamAddress != "" || runtime.Username != "" ||
		runtime.ApprovedResolverIP != cfg.ApprovedResolverIP {
		t.Fatalf("DIRECT config: %+v %v", runtime, err)
	}
	for name, change := range map[string]func(*Config){
		"implicit":                func(c *Config) { c.Mode = "" },
		"invalid mode":            func(c *Config) { c.Mode = "auto" },
		"upstream":                func(c *Config) { c.UpstreamHost, c.UpstreamPort = "proxy.invalid", 443 },
		"protocol":                func(c *Config) { c.UpstreamProtocol = "socks5" },
		"credential":              func(c *Config) { c.PasswordFile = "private" },
		"lease":                   func(c *Config) { c.CredentialLeaseFile = "private" },
		"resolver hostname":       func(c *Config) { c.ApprovedResolverIP = "dns.invalid" },
		"resolver loopback":       func(c *Config) { c.ApprovedResolverIP = "127.0.0.1" },
		"resolver metadata":       func(c *Config) { c.ApprovedResolverIP = "169.254.169.254" },
		"resolver IPv6":           func(c *Config) { c.ApprovedResolverIP = "2606:4700:4700::1111" },
		"no resolver identity":    func(c *Config) { c.ApprovedResolverID = "" },
		"no host file":            func(c *Config) { c.HostIPv4File = "" },
		"no host snapshot":        func(c *Config) { c.HostIPv4Snapshot = nil },
		"different host snapshot": func(c *Config) { c.HostIPv4Snapshot = []string{"8.8.8.9"} },
	} {
		t.Run(name, func(t *testing.T) {
			value := cfg
			change(&value)
			if _, err := value.Resolve(""); err == nil {
				t.Fatal("invalid DIRECT configuration accepted")
			}
		})
	}
}

func TestDirectHostEvidenceRequiresProcfsAndLocalAddresses(t *testing.T) {
	fixture := "Main:\n  |-- 127.0.0.1\n      /32 host LOCAL\n  |-- 8.8.8.9\n      /32 host LOCAL\n  |-- 10.0.0.1\n      /32 host LOCAL\n"
	addresses, err := parseHostPublicIPv4(fixture)
	if err != nil || !reflect.DeepEqual(addresses, []string{"8.8.8.9"}) {
		t.Fatalf("host evidence: %v %v", addresses, err)
	}
	for _, raw := range []string{"", strings.ReplaceAll(fixture, "host LOCAL", "link UNICAST"),
		strings.ReplaceAll(fixture, "8.8.8.9", "192.168.1.1"), strings.ReplaceAll(fixture, "127.0.0.1", "broken"),
		"Main:\n /32 host LOCAL\n"} {
		if _, err := parseHostPublicIPv4(raw); err == nil {
			t.Fatal("incomplete host evidence accepted")
		}
	}
	path := filepath.Join(t.TempDir(), "fib_trie")
	if err := os.WriteFile(path, []byte(fixture), 0444); err != nil {
		t.Fatal(err)
	}
	if _, err := hostPublicIPv4(path); err == nil {
		t.Fatal("static ordinary file accepted instead of live procfs")
	}
}

func TestDirectRejectsProtectedAddressesAndEntireMixedAnswer(t *testing.T) {
	s := NewServer(RuntimeConfig{Mode: "direct", HostIPv4Snapshot: []string{"8.8.8.9"}}, nil)
	var calls atomic.Int32
	s.directDial = func(context.Context, string, string) (net.Conn, error) {
		calls.Add(1)
		return nil, errors.New("unexpected dial")
	}
	for _, text := range []string{"0.0.0.0", "10.3.4.5", "100.100.100.200", "127.0.0.1", "169.254.169.254",
		"172.17.0.1", "192.0.0.9", "192.0.2.1", "192.168.1.1", "198.18.0.1", "198.51.100.1",
		"203.0.113.1", "224.0.0.1", "255.255.255.255", "::1", "::ffff:1.1.1.1", "2606:4700::1111", "8.8.8.9"} {
		address := netip.MustParseAddr(text)
		if s.directAddressAllowed(address) {
			t.Fatalf("protected address %s accepted", text)
		}
		_, err := s.dialDirectAddresses(context.Background(), 443, []netip.Addr{netip.MustParseAddr("1.1.1.1"), address})
		if !errors.Is(err, errDirectDenied) || calls.Load() != 0 {
			t.Fatalf("mixed answer attempted a connection: %v", err)
		}
	}
	for _, port := range []uint16{0, 53, 853} {
		if _, err := s.dialDirectAddresses(context.Background(), port, []netip.Addr{netip.MustParseAddr("1.1.1.1")}); !errors.Is(err, errDirectDenied) {
			t.Fatal("DNS/DoT tunnel allowed")
		}
	}
}

func TestDirectDialsNumericAddressWithinOneDeadline(t *testing.T) {
	cfg, err := nativeDirectConfig(t).Resolve("")
	if err != nil {
		t.Fatal(err)
	}
	s := NewServer(cfg, nil)
	s.directDial = func(ctx context.Context, network, address string) (net.Conn, error) {
		deadline, ok := ctx.Deadline()
		if network != "tcp4" || address != "1.1.1.1:443" || !ok || time.Until(deadline) > cfg.DialTimeout {
			t.Errorf("unbounded or nonnumeric connection: %s %s", network, address)
		}
		left, right := net.Pipe()
		_ = right.Close()
		return left, nil
	}
	conn, err := s.dialDirect(context.Background(), request{atyp: 1, addr: []byte{1, 1, 1, 1}, port: 443})
	if err != nil {
		t.Fatal(err)
	}
	_ = conn.Close()
	s.cfg.HostIPv4Snapshot = []string{"8.8.8.9"}
	if _, err := s.dialDirect(context.Background(), request{atyp: 1, addr: []byte{1, 1, 1, 1}, port: 443}); !errors.Is(err, errDirectHostEvidence) {
		t.Fatal("host evidence drift was ignored")
	}
}

func TestDirectHostEvidenceLossClosesExistingTunnel(t *testing.T) {
	cfg := nativeDirectConfig(t)
	process := exec.Command("sleep", "30")
	if err := process.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = process.Process.Kill(); _ = process.Wait() })
	cfg.HostIPv4File = fmt.Sprintf("/proc/%d/net/fib_trie", process.Process.Pid)
	runtime, err := cfg.Resolve("")
	if err != nil {
		t.Fatal(err)
	}
	s := NewServer(runtime, slog.New(slog.NewTextHandler(io.Discard, nil)))
	peers := make(chan net.Conn, 1)
	s.directDial = func(context.Context, string, string) (net.Conn, error) {
		left, right := net.Pipe()
		peers <- right
		return left, nil
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- s.ServeListener(ctx, listener) }()
	client, reply, err := clientConnect(listener.Addr().String(), request{atyp: 1, addr: []byte{1, 1, 1, 1}, port: 443})
	if err != nil || reply != replySucceeded {
		t.Fatalf("DIRECT tunnel not established: %d %v", reply, err)
	}
	defer client.Close()
	peer := <-peers
	defer peer.Close()
	if err := process.Process.Kill(); err != nil {
		t.Fatal(err)
	}
	_ = process.Wait()
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("DIRECT listener retained invalid host evidence")
	}
	_ = client.SetReadDeadline(time.Now().Add(time.Second))
	if _, err := client.Read(make([]byte, 1)); !errors.Is(err, io.EOF) {
		t.Fatalf("existing tunnel remained open: %v", err)
	}
	if conn, err := net.DialTimeout("tcp", listener.Addr().String(), 100*time.Millisecond); err == nil {
		conn.Close()
		t.Fatal("listener remained open")
	}
}
