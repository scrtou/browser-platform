package state

import (
	"path/filepath"
	"testing"
)

func TestOnlyOneServiceMayOwnJournal(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	first, err := LockService(path)
	if err != nil {
		t.Fatal(err)
	}
	if second, err := LockService(path); err == nil {
		second.Close()
		t.Fatal("two services acquired the same journal")
	}
	first.Close()
	next, err := LockService(path)
	if err != nil {
		t.Fatalf("closed service did not release ownership: %v", err)
	}
	next.Close()
}
