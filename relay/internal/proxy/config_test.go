package proxy

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
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

func TestResolveAuthenticationMatrix(t *testing.T) {
	dir := t.TempDir()
	for _, name := range []string{"username", "password"} {
		if err := os.WriteFile(filepath.Join(dir, name), []byte(" value \n"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	for _, protocol := range []string{"", "socks5", "http", "https", "direct", "socks4"} {
		for _, auth := range []string{"", "none", "username_password", "basic", "digest", "ntlm", "kerberos", "client_certificate"} {
			for _, credentials := range []bool{false, true} {
				c := Config{ListenAddress: "127.0.0.1:1080", UpstreamHost: "proxy.test", UpstreamPort: 443,
					UpstreamProtocol: protocol, UpstreamAuth: auth}
				if credentials {
					c.UsernameFile, c.PasswordFile = "username", "password"
				}
				valid := protocol == "" && auth == "" ||
					(protocol == "socks5" || protocol == "http" || protocol == "https") && auth == "none" && !credentials ||
					protocol == "socks5" && auth == "username_password" && credentials ||
					(protocol == "http" || protocol == "https") && auth == "basic" && credentials
				runtime, err := c.Resolve(dir)
				if valid && err != nil || !valid && !errors.Is(err, errUnsupportedAuth) {
					t.Errorf("protocol=%q auth=%q credentials=%v valid=%v err=%v", protocol, auth, credentials, valid, err)
				}
				if valid && credentials && (runtime.Username != " value " || runtime.Password != " value ") {
					t.Error("credential spaces changed")
				}
			}
		}
	}
}

func TestSecretFileBytesAndBoundaries(t *testing.T) {
	for _, tc := range []struct {
		name, input, want string
		valid             bool
	}{
		{"spaces", " value ", " value ", true},
		{"lf", " value \n", " value ", true},
		{"crlf", " value \r\n", " value ", true},
		{"unicode", "繁體😀", "繁體😀", true},
		{"limit", strings.Repeat("x", 4096) + "\r\n", strings.Repeat("x", 4096), true},
		{"too_large", strings.Repeat("x", 4097), "", false},
		{"multiline", "value\n\r\n", "", false},
		{"cr", "value\r", "", false},
		{"nul", "value\x00", "", false},
		{"tab", "value\t", "", false},
		{"invalid_utf8", "value\xff", "", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			dir := t.TempDir()
			if err := os.WriteFile(filepath.Join(dir, "value"), []byte(tc.input), 0600); err != nil {
				t.Fatal(err)
			}
			got, err := readSecret(dir, "value")
			if (err == nil) != tc.valid || err == nil && got != tc.want {
				t.Fatal("secret byte contract violated")
			}
		})
	}
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "value"), []byte("secret"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(dir, "value"), filepath.Join(dir, "link")); err != nil {
		t.Fatal(err)
	}
	if _, err := readSecret(dir, "link"); err == nil {
		t.Fatal("secret symlink accepted")
	}
	if _, err := readSecret(dir, "."); err == nil {
		t.Fatal("secret directory accepted")
	}
}

func TestResolveCredentialProtocolLimits(t *testing.T) {
	for _, tc := range []struct {
		protocol, auth, username, password string
		valid                              bool
	}{
		{"socks5", "username_password", strings.Repeat("x", 255), "p", true},
		{"socks5", "username_password", strings.Repeat("x", 256), "p", false},
		{"socks5", "username_password", "u", strings.Repeat("界", 86), false},
		{"http", "basic", strings.Repeat("x", 256), "p", true},
		{"http", "basic", "u:v", "p", false},
		{"https", "basic", "u", "p:v", true},
	} {
		dir := t.TempDir()
		for name, value := range map[string]string{"username": tc.username, "password": tc.password} {
			if err := os.WriteFile(filepath.Join(dir, name), []byte(value), 0600); err != nil {
				t.Fatal(err)
			}
		}
		_, err := (Config{ListenAddress: "127.0.0.1:1080", UpstreamHost: "proxy.test", UpstreamPort: 443,
			UpstreamProtocol: tc.protocol, UpstreamAuth: tc.auth, UsernameFile: "username", PasswordFile: "password"}).Resolve(dir)
		if (err == nil) != tc.valid {
			t.Errorf("credential limits: protocol=%s valid=%v err=%v", tc.protocol, tc.valid, err)
		}
	}
}

func TestTLSOptionsCannotBeIgnored(t *testing.T) {
	base := Config{ListenAddress: "127.0.0.1:1080", UpstreamHost: "proxy.test", UpstreamPort: 443, UpstreamProtocol: "https", UpstreamAuth: "none"}
	for _, field := range []string{"tls_name", "tls_ca", "insecure"} {
		c := base
		switch field {
		case "tls_name":
			c.UpstreamTLSServerName = "https://proxy.test"
		case "tls_ca":
			c.UpstreamTLSCAFile = "missing.pem"
		case "insecure":
			c.UpstreamProtocol = "http"
			c.UpstreamTLSServerName = "proxy.test"
		}
		if _, err := c.Resolve(t.TempDir()); err == nil {
			t.Fatalf("invalid TLS option %s accepted", field)
		}
	}
	for _, host := range []string{"proxy\r\n.test", "a..b", "-proxy.test", "proxy.test/", "[::1]", "::1%eth0", strings.Repeat("a", 64) + ".test"} {
		c := base
		c.UpstreamHost = host
		if _, err := c.Resolve(t.TempDir()); err == nil {
			t.Fatal("invalid host accepted")
		}
	}
}

func TestParseConfigRejectsAmbiguityAndSecrets(t *testing.T) {
	for _, raw := range []string{
		`{"upstream_auth":"none","upstream_auth":"basic"}`,
		`{"upstream_auth":"none","Upstream_Auth":"basic"}`,
		`{"password":"private-test-value"}`,
		`{"upstream_auth":null}`,
		`{"upstream_tls_skip_verify":true}`,
		`{"upstream_port":443.5}`,
		`{} {}`, `null`, `[]`,
		`{"upstream_host":"` + strings.Repeat("x", 65536) + `"}`,
	} {
		if _, err := ParseConfig([]byte(raw)); err == nil {
			t.Fatal("ambiguous or unsafe config accepted")
		}
	}
	if _, err := ParseConfig([]byte(`{"upstream_protocol":"https","upstream_auth":"none","upstream_port":443}`)); err != nil {
		t.Fatal(err)
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
