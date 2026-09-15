// Package state provides a small durable control-plane journal. SealSkin keeps
// its own runtime state; this journal records only the adapter's ownership and
// reconciliation metadata.
package state

import (
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

const fileVersion = 1

type Status string

func (s Status) String() string { return string(s) }

const (
	StatusLaunching Status = "launching"
	StatusRunning   Status = "running"
	StatusStopping  Status = "stopping"
	StatusStopped   Status = "stopped"
	StatusFailed    Status = "failed"
	StatusUnknown   Status = "unknown"
)

type Binding struct {
	ProfileID            string     `json:"profile_id"`
	Status               Status     `json:"status"`
	SessionID            string     `json:"session_id,omitempty"`
	OperationID          string     `json:"operation_id"`
	IdempotencyKey       string     `json:"idempotency_key"`
	BootstrapURL         string     `json:"bootstrap_url"`
	HomeName             string     `json:"home_name,omitempty"`
	ApplicationID        string     `json:"application_id,omitempty"`
	NetworkPolicyID      string     `json:"network_policy_id,omitempty"`
	NetworkPolicySHA256  string     `json:"network_policy_sha256,omitempty"`
	StopOperationID      string     `json:"stop_operation_id,omitempty"`
	StopIdempotencyKey   string     `json:"stop_idempotency_key,omitempty"`
	ResumeIdempotencyKey string     `json:"resume_idempotency_key,omitempty"`
	IdleSince            *time.Time `json:"idle_since,omitempty"`
	LastError            string     `json:"last_error,omitempty"`
	UpdatedAt            time.Time  `json:"updated_at"`
}

type fileData struct {
	Version  int                `json:"version"`
	Bindings map[string]Binding `json:"bindings"`
}

type Store struct {
	path string
	now  func() time.Time
}

func NewStore(path string) (*Store, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return nil, errors.New("state file path is required")
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, fmt.Errorf("create state directory: %w", err)
	}
	return &Store{path: path, now: time.Now}, nil
}

func (s *Store) Get(profileID string) (Binding, bool, error) {
	var binding Binding
	var found bool
	err := s.withLock(false, func() error {
		data, err := s.read()
		if err != nil {
			return err
		}
		binding, found = data.Bindings[profileID]
		return nil
	})
	return binding, found, err
}

func (s *Store) All() (map[string]Binding, error) {
	result := make(map[string]Binding)
	err := s.withLock(false, func() error {
		data, err := s.read()
		if err != nil {
			return err
		}
		for id, binding := range data.Bindings {
			result[id] = binding
		}
		return nil
	})
	return result, err
}

// Update serializes changes across processes with flock and commits with an
// fsync + atomic rename. A nil replacement deletes the binding.
func (s *Store) Update(profileID string, change func(current *Binding) (*Binding, error)) error {
	if strings.TrimSpace(profileID) == "" {
		return errors.New("profile ID is required")
	}
	return s.withLock(true, func() error {
		data, err := s.read()
		if err != nil {
			return err
		}
		var current *Binding
		if value, ok := data.Bindings[profileID]; ok {
			copy := value
			current = &copy
		}
		replacement, err := change(current)
		if err != nil {
			return err
		}
		if replacement == nil {
			delete(data.Bindings, profileID)
		} else {
			replacement.ProfileID = profileID
			replacement.UpdatedAt = s.now().UTC()
			if err := validateBinding(*replacement); err != nil {
				return err
			}
			data.Bindings[profileID] = *replacement
		}
		return s.write(data)
	})
}

func (s *Store) withLock(exclusive bool, operation func() error) error {
	lockFile, err := os.OpenFile(s.path+".lock", os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return fmt.Errorf("open state lock: %w", err)
	}
	defer lockFile.Close()
	mode := syscall.LOCK_SH
	if exclusive {
		mode = syscall.LOCK_EX
	}
	if err := syscall.Flock(int(lockFile.Fd()), mode); err != nil {
		return fmt.Errorf("lock state: %w", err)
	}
	defer syscall.Flock(int(lockFile.Fd()), syscall.LOCK_UN) //nolint:errcheck
	return operation()
}

func (s *Store) read() (fileData, error) {
	data := fileData{Version: fileVersion, Bindings: make(map[string]Binding)}
	file, err := os.Open(s.path)
	if errors.Is(err, os.ErrNotExist) {
		return data, nil
	}
	if err != nil {
		return data, fmt.Errorf("open state: %w", err)
	}
	defer file.Close()
	decoder := json.NewDecoder(io.LimitReader(file, 4<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&data); err != nil {
		return data, fmt.Errorf("decode state: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return data, errors.New("state contains trailing data")
	}
	if data.Version != fileVersion {
		return data, fmt.Errorf("unsupported state version %d", data.Version)
	}
	if data.Bindings == nil {
		data.Bindings = make(map[string]Binding)
	}
	for id, binding := range data.Bindings {
		if id != binding.ProfileID {
			return data, fmt.Errorf("state binding key %q does not match profile_id %q", id, binding.ProfileID)
		}
		if err := validateBinding(binding); err != nil {
			return data, fmt.Errorf("invalid state binding %q: %w", id, err)
		}
	}
	return data, nil
}

func (s *Store) write(data fileData) error {
	encoded, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return fmt.Errorf("encode state: %w", err)
	}
	encoded = append(encoded, '\n')
	temp, err := os.CreateTemp(filepath.Dir(s.path), ".profile-state-*")
	if err != nil {
		return fmt.Errorf("create temporary state: %w", err)
	}
	tempName := temp.Name()
	keep := false
	defer func() {
		temp.Close()
		if !keep {
			os.Remove(tempName)
		}
	}()
	if err := temp.Chmod(0o600); err != nil {
		return fmt.Errorf("protect temporary state: %w", err)
	}
	if _, err := temp.Write(encoded); err != nil {
		return fmt.Errorf("write temporary state: %w", err)
	}
	if err := temp.Sync(); err != nil {
		return fmt.Errorf("sync temporary state: %w", err)
	}
	if err := temp.Close(); err != nil {
		return fmt.Errorf("close temporary state: %w", err)
	}
	if err := os.Rename(tempName, s.path); err != nil {
		return fmt.Errorf("commit state: %w", err)
	}
	keep = true
	directory, err := os.Open(filepath.Dir(s.path))
	if err != nil {
		return fmt.Errorf("open state directory: %w", err)
	}
	defer directory.Close()
	if err := directory.Sync(); err != nil {
		return fmt.Errorf("sync state directory: %w", err)
	}
	return nil
}

func validateBinding(binding Binding) error {
	switch binding.Status {
	case StatusLaunching, StatusRunning, StatusStopping, StatusStopped, StatusFailed, StatusUnknown:
	default:
		return fmt.Errorf("invalid status %q", binding.Status)
	}
	if binding.ProfileID == "" || binding.OperationID == "" || binding.IdempotencyKey == "" || binding.BootstrapURL == "" {
		return errors.New("profile_id, operation_id, idempotency_key and bootstrap_url are required")
	}
	if binding.Status == StatusRunning && binding.SessionID == "" {
		return errors.New("running binding requires session_id")
	}
	if (binding.StopOperationID == "") != (binding.StopIdempotencyKey == "") {
		return errors.New("stop_operation_id and stop_idempotency_key must be stored together")
	}
	if (binding.NetworkPolicyID == "") != (binding.NetworkPolicySHA256 == "") {
		return errors.New("network policy id and SHA-256 must be stored together")
	}
	if binding.NetworkPolicyID != "" {
		_, err := hex.DecodeString(binding.NetworkPolicySHA256)
		if err != nil || len(binding.NetworkPolicySHA256) != 64 || strings.ToLower(binding.NetworkPolicySHA256) != binding.NetworkPolicySHA256 {
			return errors.New("invalid network policy SHA-256")
		}
	}
	return nil
}
