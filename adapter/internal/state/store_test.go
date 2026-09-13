package state

import (
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"testing"
)

func TestStorePersistsAndSerializesUpdates(t *testing.T) {
	path := filepath.Join(t.TempDir(), "nested", "state.json")
	store, err := NewStore(path)
	if err != nil {
		t.Fatal(err)
	}
	initial := Binding{Status: StatusLaunching, OperationID: "op-1", IdempotencyKey: "idem-1", BootstrapURL: "https://adapter/bootstrap/p/op-1"}
	if err := store.Update("personal", func(current *Binding) (*Binding, error) {
		if current != nil {
			t.Fatal("unexpected existing binding")
		}
		return &initial, nil
	}); err != nil {
		t.Fatal(err)
	}

	const workers = 12
	var group sync.WaitGroup
	group.Add(workers)
	for range workers {
		go func() {
			defer group.Done()
			if err := store.Update("personal", func(current *Binding) (*Binding, error) {
				if current == nil {
					return nil, errors.New("binding disappeared")
				}
				current.LastError += "x"
				return current, nil
			}); err != nil {
				t.Errorf("update: %v", err)
			}
		}()
	}
	group.Wait()

	reopened, err := NewStore(path)
	if err != nil {
		t.Fatal(err)
	}
	binding, ok, err := reopened.Get("personal")
	if err != nil {
		t.Fatal(err)
	}
	if !ok || len(binding.LastError) != workers {
		t.Fatalf("lost update: found=%v value=%+v", ok, binding)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o600 {
		t.Fatalf("state mode = %o, want 600", info.Mode().Perm())
	}
}

func TestStoreRejectsCorruptState(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	if err := os.WriteFile(path, []byte(`{"version":1,"bindings":{"p":{"profile_id":"different"}}}`), 0o600); err != nil {
		t.Fatal(err)
	}
	store, err := NewStore(path)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := store.Get("p"); err == nil {
		t.Fatal("expected corrupt state to be rejected")
	}
}

func TestStoreSerializesAcrossProcesses(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	store, err := NewStore(path)
	if err != nil {
		t.Fatal(err)
	}
	initial := Binding{Status: StatusLaunching, OperationID: "op-1", IdempotencyKey: "idem-1", BootstrapURL: "https://adapter/bootstrap/p/op-1"}
	if err := store.Update("personal", func(*Binding) (*Binding, error) { return &initial, nil }); err != nil {
		t.Fatal(err)
	}
	executable, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	const workers = 10
	commands := make([]*exec.Cmd, workers)
	for index := range workers {
		command := exec.Command(executable, "-test.run=^TestStoreProcessHelper$")
		command.Env = append(os.Environ(), "BROWSER_PLATFORM_STATE_HELPER="+path)
		if err := command.Start(); err != nil {
			t.Fatal(err)
		}
		commands[index] = command
	}
	for _, command := range commands {
		if err := command.Wait(); err != nil {
			t.Fatalf("state helper: %v", err)
		}
	}
	binding, found, err := store.Get("personal")
	if err != nil || !found {
		t.Fatalf("binding found=%v err=%v", found, err)
	}
	if len(binding.LastError) != workers {
		t.Fatalf("cross-process updates=%d, want %d", len(binding.LastError), workers)
	}
}

func TestStoreProcessHelper(t *testing.T) {
	path := os.Getenv("BROWSER_PLATFORM_STATE_HELPER")
	if path == "" {
		return
	}
	store, err := NewStore(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := store.Update("personal", func(current *Binding) (*Binding, error) {
		if current == nil {
			return nil, errors.New("binding disappeared")
		}
		current.LastError += "x"
		return current, nil
	}); err != nil {
		t.Fatal(err)
	}
}
