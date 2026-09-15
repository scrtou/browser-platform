package proxy

import (
	"bytes"
	"context"
	"encoding/hex"
	"errors"
	"time"
)

var errCredentialLease = errors.New("credential lease unavailable or revoked")

const credentialLeaseInterval = 100 * time.Millisecond

// The generation directory is a read-only tmpfs bind from the controller.
// Checking its child by name observes atomic lease replacement and deletion,
// unlike bind-mounting a single file inode. Any read/format error is terminal.
func validLease(path, id string) bool {
	if len(id) != 64 {
		return false
	}
	decoded, err := hex.DecodeString(id)
	if err != nil || hex.EncodeToString(decoded) != id {
		return false
	}
	value, err := readRegularFile("", path, 128, true)
	return err == nil && bytes.Equal(value, []byte("active:"+id+"\n"))
}

func (s *Server) watchCredentialLease(ctx context.Context, cancel context.CancelFunc, done chan<- struct{}) {
	defer close(done)
	ticker := time.NewTicker(credentialLeaseInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if !validLease(s.cfg.CredentialLeaseFile, s.cfg.CredentialLeaseID) {
				s.logger.Warn("credential lease ended", "error_code", "CREDENTIAL_LEASE_REVOKED")
				cancel()
				return
			}
		}
	}
}
