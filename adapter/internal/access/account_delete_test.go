package access

import (
	"errors"
	"os"
	"path/filepath"
	"sync"
	"testing"
)

func TestAccountDeletionPreservesOneAdminUnderConcurrentRequests(t *testing.T) {
	root := t.TempDir()
	if err := os.Chmod(root, 0700); err != nil {
		t.Fatal(err)
	}
	store := NewAccountStore(filepath.Join(root, "accounts.json"), nil)
	for _, id := range []string{"one", "two"} {
		if err := store.Put(id, testPassword, RoleAdmin, nil, false); err != nil {
			t.Fatal(err)
		}
	}
	var wg sync.WaitGroup
	results := make(chan error, 2)
	for _, id := range []string{"one", "two"} {
		wg.Add(1)
		go func(id string) { defer wg.Done(); results <- store.Delete(id) }(id)
	}
	wg.Wait()
	close(results)
	deleted, protected := 0, 0
	for err := range results {
		if err == nil {
			deleted++
		} else if errors.Is(err, ErrLastAdmin) {
			protected++
		} else {
			t.Fatal(err)
		}
	}
	if deleted != 1 || protected != 1 {
		t.Fatal(deleted, protected)
	}
	rows, err := store.Snapshot()
	if err != nil || len(rows) != 1 {
		t.Fatal(rows, err)
	}
	if err := store.Delete("missing"); !errors.Is(err, ErrAccountNotFound) {
		t.Fatal(err)
	}
}
func TestDeletedAccountLosesLoginAndDisplayOnlyForThatAccount(t *testing.T) {
	f := newFixture(t)
	alice, _, aliceDisplay := f.display(t, "alice", "personal")
	if err := f.g.Accounts().Put("deletable", testPassword, RoleUser, []string{"personal"}, false); err != nil {
		t.Fatal(err)
	}
	if err := f.g.Reload(); err != nil {
		t.Fatal(err)
	}
	target, _, targetDisplay := f.display(t, "deletable", "personal")
	if err := f.g.Accounts().Delete("deletable"); err != nil {
		t.Fatal(err)
	}
	if err := f.g.Reload(); err != nil {
		t.Fatal(err)
	}
	if request(f.handler, "GET", "https://session.test/"+personalSession+"/", nil, targetDisplay).Code != 401 {
		t.Fatal("deleted display survived")
	}
	if request(f.handler, "GET", "https://entry.test/browser/personal/", nil, target).Code != 303 {
		t.Fatal("deleted login survived")
	}
	if request(f.handler, "GET", "https://session.test/"+personalSession+"/", nil, aliceDisplay).Code != 200 {
		t.Fatal("other display revoked")
	}
	if request(f.handler, "GET", "https://entry.test/browser/personal/", nil, alice).Code != 200 {
		t.Fatal("other login revoked")
	}
}
