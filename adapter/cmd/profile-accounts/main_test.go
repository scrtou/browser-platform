package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"browser-platform/adapter/internal/access"
)

func configuration(t *testing.T) (string, string) {
	t.Helper()
	dir := t.TempDir()
	if err := os.Chmod(dir, 0o700); err != nil {
		t.Fatal(err)
	}
	users, config := filepath.Join(dir, "users.json"), filepath.Join(dir, "config.json")
	value := map[string]any{
		"listen_address": "127.0.0.1:8080", "public_base_url": "https://entry.test", "state_file": "state.json",
		"sealskin": map[string]any{"api_base_url": "https://127.0.0.1:8443", "public_session_base_url": "https://session.test",
			"username": "qa", "server_public_key_file": "server.pem", "client_private_key_file": "client.pem", "lifecycle_enabled": true},
		"access": map[string]any{"users_file": users, "session_upstream_url": "https://127.0.0.1:8443",
			"session_ca_file": "ca.pem", "session_tls_name": "session.test"},
		"profiles": []map[string]string{{"id": "personal"}, {"id": "work"}},
	}
	raw, _ := json.Marshal(value)
	if err := os.WriteFile(config, raw, 0o600); err != nil {
		t.Fatal(err)
	}
	return config, users
}

func TestAccountChangesAreExplicitPrivateAndRetainOtherUsers(t *testing.T) {
	config, path := configuration(t)
	password := "synthetic-cli-password-51e9"
	put := []string{"put", "--config", config, "--user", "alice", "--profiles", "personal"}
	if err := run(put, strings.NewReader(password+"\n")); err != nil {
		t.Fatal(err)
	}
	original, _ := os.ReadFile(path)
	if strings.Contains(string(original), password) {
		t.Fatal("plaintext password persisted")
	}
	if err := run(put, strings.NewReader("replacement-password")); err == nil {
		t.Fatal("implicit replacement allowed")
	}
	after, _ := os.ReadFile(path)
	if string(original) != string(after) {
		t.Fatal("denied replacement modified registry")
	}
	var wg sync.WaitGroup
	failures := make(chan error, 2)
	for _, name := range []string{"bob", "carol"} {
		wg.Add(1)
		go func(name string) {
			defer wg.Done()
			failures <- run([]string{"put", "--config", config, "--user", name, "--profiles", "work"}, strings.NewReader(password))
		}(name)
	}
	wg.Wait()
	close(failures)
	for err := range failures {
		if err != nil {
			t.Fatal(err)
		}
	}
	if err := run([]string{"disable", "--config", config, "--user", "alice"}, strings.NewReader("")); err != nil {
		t.Fatal(err)
	}
	registry, _, err := access.ReadRegistry(path, map[string]bool{"personal": true, "work": true})
	if err != nil || len(registry.Users) != 3 || !registry.Users[0].Disabled {
		t.Fatal("concurrent updates lost accounts or disable state")
	}
	if err := run(append(put, "--replace"), strings.NewReader("different-test-password")); err != nil {
		t.Fatal(err)
	}
	if err := run([]string{"check", "--config", config}, strings.NewReader("")); err != nil {
		t.Fatal(err)
	}
}

func TestInvalidGrantPasswordAndArgumentsDoNotCreateAccounts(t *testing.T) {
	config, users := configuration(t)
	for _, entry := range []struct {
		args     []string
		password string
	}{
		{[]string{"put", "--config", config, "--user", "alice", "--profiles", "unknown"}, "valid-test-password"},
		{[]string{"put", "--config", config, "--user", "alice", "--profiles", "personal"}, "short"},
		{[]string{"put", "--config", config, "--user", "alice", "--profiles", "personal"}, "line-one-test\nline-two"},
		{[]string{"put", "--config", config, "--password", "synthetic-private-argument"}, ""},
	} {
		err := run(entry.args, strings.NewReader(entry.password))
		if err == nil || strings.Contains(err.Error(), "synthetic-private-argument") {
			t.Fatal("invalid input was accepted or echoed")
		}
		if _, err := os.Stat(users); !os.IsNotExist(err) {
			t.Fatal("invalid input created accounts")
		}
	}
}
