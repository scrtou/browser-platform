package main

import (
	"browser-platform/adapter/internal/access"
	"os"
	"strings"
	"sync"
	"testing"
)

func TestInitCreatesOnlyFirstAdminAndNeverReplaces(t *testing.T) {
	for _, pending := range []bool{false, true} {
		config, path := configuration(t)
		if pending {
			if err := access.WriteRegistry(path, access.Registry{Version: 3, Users: []access.Account{}, SetupRequired: true}); err != nil {
				t.Fatal(err)
			}
		}
		var wg sync.WaitGroup
		errors := make(chan error, 2)
		for _, id := range []string{"first", "second"} {
			wg.Add(1)
			go func(id string) {
				defer wg.Done()
				errors <- run([]string{"init", "--config", config, "--user", id}, strings.NewReader("synthetic-bootstrap-password"))
			}(id)
		}
		wg.Wait()
		close(errors)
		passed := 0
		for err := range errors {
			if err == nil {
				passed++
			}
		}
		if passed != 1 {
			t.Fatalf("concurrent init winners: %d", passed)
		}
		registry, _, err := access.ReadRegistry(path, map[string]bool{})
		if err != nil || registry.SetupRequired || registry.Version != 2 || len(registry.Users) != 1 || registry.Users[0].Role != access.RoleAdmin {
			t.Fatal("invalid initialized state", err)
		}
		before, _ := os.ReadFile(path)
		for _, extra := range [][]string{nil, {"--replace"}, {"--profiles", "personal"}, {"--role", "admin"}} {
			args := append([]string{"init", "--config", config, "--user", "third"}, extra...)
			if err := run(args, strings.NewReader("replacement-bootstrap-password")); err == nil {
				t.Fatal("repeat or invalid init accepted")
			}
		}
		after, _ := os.ReadFile(path)
		if string(before) != string(after) {
			t.Fatal("repeat initialization replaced registry")
		}
	}
}
