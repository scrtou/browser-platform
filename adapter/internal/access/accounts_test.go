package access

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRegistryVersionsRolesAndLastAdministrator(t *testing.T) {
	dir := t.TempDir()
	if err := os.Chmod(dir, 0o700); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "users.json")
	store := NewAccountStore(path, func() map[string]bool { return map[string]bool{"personal": true, "work": true} })
	if err := store.Put("alice", testPassword, "", []string{"personal"}, false); err != nil {
		t.Fatal(err)
	}
	raw, _ := os.ReadFile(path)
	if !strings.Contains(string(raw), `"version": 1`) || strings.Contains(string(raw), `"role"`) {
		t.Fatalf("a role-less table must stay at version 1 for older binaries: %s", raw)
	}
	if err := store.Put("root", testPassword, RoleAdmin, nil, false); err != nil {
		t.Fatalf("administrator without grants rejected: %v", err)
	}
	raw, _ = os.ReadFile(path)
	if !strings.Contains(string(raw), `"version": 2`) || !strings.Contains(string(raw), `"role": "admin"`) {
		t.Fatalf("roles must promote the table to version 2: %s", raw)
	}
	if err := store.Put("bob", testPassword, "", nil, false); err == nil {
		t.Fatal("entry account without any grant accepted")
	}
	if err := store.Put("bob", testPassword, "", []string{"missing"}, false); err != ErrUnknownProfile {
		t.Fatalf("unknown grant: %v", err)
	}
	if err := store.Put("bob", testPassword, "owner", []string{"work"}, false); err == nil {
		t.Fatal("unknown role accepted")
	}
	if err := store.Put("alice", testPassword, "", []string{"work"}, false); err != ErrAccountExists {
		t.Fatalf("implicit replace: %v", err)
	}
	if err := store.SetRole("root", RoleUser); err != ErrLastAdmin {
		t.Fatalf("last admin demoted: %v", err)
	}
	if err := store.SetDisabled("root", true); err != ErrLastAdmin {
		t.Fatalf("last admin disabled: %v", err)
	}
	if err := store.Put("root", testPassword, "", []string{"personal"}, true); err != nil {
		t.Fatalf("replace without role must keep the role: %v", err)
	}
	registry, _, err := ReadRegistry(path, nil)
	if err != nil || len(registry.Users) != 2 {
		t.Fatalf("registry: %+v %v", registry, err)
	}
	for _, account := range registry.Users {
		if account.ID == "root" && (account.EffectiveRole() != RoleAdmin || strings.Join(account.Profiles, ",") != "personal") {
			t.Fatalf("replace changed the role or lost grants: %+v", account)
		}
	}
	if err := store.Put("root", testPassword, RoleUser, []string{"personal"}, true); err != ErrLastAdmin {
		t.Fatalf("replace demoting the last admin: %v", err)
	}
	if err := store.Put("second", testPassword, RoleAdmin, nil, false); err != nil {
		t.Fatal(err)
	}
	if err := store.SetRole("root", RoleUser); err != nil {
		t.Fatalf("demote with another admin present: %v", err)
	}
	if err := store.SetDisabled("second", true); err != ErrLastAdmin {
		t.Fatal("the remaining admin was disabled")
	}
	if err := store.SetPassword("nobody", testPassword); err != ErrAccountNotFound {
		t.Fatalf("missing account: %v", err)
	}
	snapshot, err := store.Snapshot()
	if err != nil || len(snapshot) != 3 {
		t.Fatalf("snapshot: %+v %v", snapshot, err)
	}
	for _, account := range snapshot {
		if account.PasswordHash != "" {
			t.Fatal("snapshot exposes verifiers")
		}
	}
	// A version 1 file that already carries a role is rejected, as is a bad role.
	bad := Registry{Version: 1, Users: []Account{{ID: "x", PasswordHash: testVerifier(t), Profiles: []string{"personal"}, Role: RoleAdmin}}}
	if validateRegistry(bad, nil) == nil {
		t.Fatal("version 1 with roles accepted")
	}
	bad = Registry{Version: 2, Users: []Account{{ID: "x", PasswordHash: testVerifier(t), Profiles: []string{"personal"}, Role: "root"}}}
	if validateRegistry(bad, nil) == nil {
		t.Fatal("unknown role accepted")
	}
	if store2 := NewAccountStore(filepath.Join(dir, "missing.json"), nil); store2.SetPassword("alice", testPassword) == nil {
		t.Fatal("mutating a missing registry created it")
	}
}
