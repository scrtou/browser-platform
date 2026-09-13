package proxy

import (
	"os"
	"path/filepath"
	"testing"
)

func TestResolveRequiresPairedSecrets(t *testing.T) {
	dir := t.TempDir()
	username := filepath.Join(dir, "username")
	if err := os.WriteFile(username, []byte("user"), 0600); err != nil {
		t.Fatal(err)
	}
	_, err := (Config{ListenAddress: "127.0.0.1:19080", UpstreamHost: "proxy", UpstreamPort: 1, UsernameFile: username}).Resolve(dir)
	if err == nil {
		t.Fatal("expected paired secret error")
	}
}

func TestResolveRejectsWeakSecretMode(t *testing.T) {
	dir := t.TempDir()
	for _, name := range []string{"username", "password"} {
		if err := os.WriteFile(filepath.Join(dir, name), []byte("x"), 0640); err != nil {
			t.Fatal(err)
		}
	}
	_, err := (Config{ListenAddress: "127.0.0.1:19080", UpstreamHost: "proxy", UpstreamPort: 1, UsernameFile: "username", PasswordFile: "password"}).Resolve(dir)
	if err == nil {
		t.Fatal("expected weak mode error")
	}
}

func TestResolveRejectsEmptyConfiguredSecrets(t *testing.T) {
	dir := t.TempDir()
	for _, name := range []string{"username", "password"} {
		if err := os.WriteFile(filepath.Join(dir, name), []byte("\n"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	_, err := (Config{
		ListenAddress: "127.0.0.1:19080", UpstreamHost: "proxy", UpstreamPort: 1,
		UsernameFile: "username", PasswordFile: "password",
	}).Resolve(dir)
	if err == nil {
		t.Fatal("expected empty secret error")
	}
}

func TestResolveRequiresCIDRForNonLoopbackListen(t *testing.T) {
	_, err := (Config{ListenAddress: "0.0.0.0:19080", UpstreamHost: "proxy", UpstreamPort: 1}).Resolve(t.TempDir())
	if err == nil {
		t.Fatal("expected non-loopback listen to require client_cidrs")
	}
	if _, err := (Config{
		ListenAddress: "0.0.0.0:19080", UpstreamHost: "proxy", UpstreamPort: 1,
		ClientCIDRs: []string{"172.18.0.3/32"},
	}).Resolve(t.TempDir()); err != nil {
		t.Fatalf("explicit client CIDR rejected: %v", err)
	}
}

func TestResolveRejectsUpstreamURLOrEmbeddedPort(t *testing.T) {
	for _, host := range []string{"socks5://proxy.example", "user@proxy.example", "proxy.example:1080"} {
		_, err := (Config{ListenAddress: "127.0.0.1:19080", UpstreamHost: host, UpstreamPort: 1080}).Resolve(t.TempDir())
		if err == nil {
			t.Fatalf("upstream host %q accepted", host)
		}
	}
}
