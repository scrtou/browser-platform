package state

import (
	"fmt"
	"os"
	"path/filepath"
	"syscall"
)

// LockService prevents two adapter processes from owning the same journal.
// Close the returned file only after both HTTP listeners have shut down.
func LockService(path string) (*os.File, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, err
	}
	file, err := os.OpenFile(path+".service.lock", os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, err
	}
	if err := syscall.Flock(int(file.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		file.Close()
		return nil, fmt.Errorf("another adapter owns this state file: %w", err)
	}
	return file, nil
}
