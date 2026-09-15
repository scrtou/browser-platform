package proxy

import (
	"io"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestCredentialLeaseClosesExistingTunnelAndListener(t *testing.T) {
	for _, mode := range []string{"replace", "delete", "wrong-generation", "permissions", "symlink"} {
		t.Run(mode, func(t *testing.T) {
			closed := make(chan struct{})
			upstream := testPeer(t, nil, func(conn net.Conn) {
				defer close(closed)
				if _, err := peerRequest(conn, protocolHTTP, authBasic); err != nil {
					t.Error(err)
					return
				}
				if err := peerSuccess(conn, protocolHTTP, nil); err != nil {
					t.Error(err)
					return
				}
				_, _ = io.Copy(conn, conn)
			})
			cfg := testRuntime(t, upstream, protocolHTTP, authBasic, nil)
			id := strings.Repeat("a", 64)
			path := filepath.Join(t.TempDir(), "lease")
			if err := os.WriteFile(path, []byte("active:"+id+"\n"), 0600); err != nil {
				t.Fatal(err)
			}
			cfg.CredentialLeaseFile, cfg.CredentialLeaseID = path, id
			address, stop, log := testRelay(t, cfg)
			conn, reply, err := clientConnect(address, domainRequest("site.test", 443))
			if err != nil || reply != 0 {
				t.Fatalf("connect: %v, reply %d", err, reply)
			}
			defer conn.Close()
			if _, err := conn.Write([]byte("ping")); err != nil {
				t.Fatal(err)
			}
			buf := make([]byte, 4)
			if _, err := io.ReadFull(conn, buf); err != nil || string(buf) != "ping" {
				t.Fatalf("echo: %q, %v", buf, err)
			}
			var mutateErr error
			switch mode {
			case "replace":
				mutateErr = os.WriteFile(path+".new", []byte("revoked\n"), 0600)
				if mutateErr == nil {
					mutateErr = os.Rename(path+".new", path)
				}
			case "delete":
				mutateErr = os.Remove(path)
			case "wrong-generation":
				mutateErr = os.WriteFile(path, []byte("active:"+strings.Repeat("b", 64)+"\n"), 0600)
			case "permissions":
				mutateErr = os.Chmod(path, 0644)
			case "symlink":
				mutateErr = os.Rename(path, path+".target")
				if mutateErr == nil {
					mutateErr = os.Symlink(path+".target", path)
				}
			}
			if mutateErr != nil {
				t.Fatal(mutateErr)
			}
			_ = conn.SetReadDeadline(time.Now().Add(time.Second))
			if n, err := conn.Read(buf); n != 0 || err == nil {
				t.Fatalf("revoked tunnel remained open: n=%d err=%v", n, err)
			} else if timeout, ok := err.(net.Error); ok && timeout.Timeout() {
				t.Fatal("revocation did not close the established connection")
			}
			select {
			case <-closed:
			case <-time.After(time.Second):
				t.Fatal("upstream connection survived revocation")
			}
			if probe, err := net.DialTimeout("tcp", address, 100*time.Millisecond); err == nil {
				probe.Close()
				t.Fatal("revoked listener remained available")
			}
			stop()
			if !strings.Contains(log.text(), "CREDENTIAL_LEASE_REVOKED") || strings.Contains(log.text(), cfg.Password) {
				t.Fatal("missing redacted revocation evidence")
			}
		})
	}
}

func TestCredentialLeaseConfigurationFailsClosed(t *testing.T) {
	dir := t.TempDir()
	for _, name := range []string{"username", "password"} {
		if err := os.WriteFile(filepath.Join(dir, name), []byte("test"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	base := Config{ListenAddress: "127.0.0.1:1080", UpstreamHost: "127.0.0.1", UpstreamPort: 9000,
		UpstreamProtocol: protocolHTTP, UpstreamAuth: authBasic, UsernameFile: "username", PasswordFile: "password",
		CredentialLeaseFile: "lease", CredentialLeaseID: strings.Repeat("a", 64)}
	if _, err := base.Resolve(dir); err == nil {
		t.Fatal("missing lease was accepted")
	}
	if err := os.WriteFile(filepath.Join(dir, "lease"), []byte("active:"+base.CredentialLeaseID+"\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := base.Resolve(dir); err != nil {
		t.Fatal(err)
	}
	base.CredentialLeaseID = ""
	if _, err := base.Resolve(dir); err == nil {
		t.Fatal("unbound lease was accepted")
	}
	base.CredentialLeaseID = strings.Repeat("a", 64)
	base.UpstreamAuth, base.UsernameFile, base.PasswordFile = authNone, "", ""
	if _, err := base.Resolve(dir); err == nil {
		t.Fatal("lease without credential authentication was accepted")
	}
}
