// Package access owns short-lived end-user login and display authorization.
// It never creates, resumes or stops a browser generation.
package access

import (
	"bytes"
	"crypto/pbkdf2"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
)

const passwordIterations = 600000

var accountID = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{0,31}$`)

type Account struct {
	ID           string   `json:"id"`
	PasswordHash string   `json:"password_hash"`
	Profiles     []string `json:"profiles"`
	Disabled     bool     `json:"disabled,omitempty"`
}

type Registry struct {
	Version int       `json:"version"`
	Users   []Account `json:"users"`
}

func HashPassword(password string) (string, error) {
	if len(password) < 12 || len(password) > 256 {
		return "", errors.New("password must contain between 12 and 256 bytes")
	}
	salt := make([]byte, 16)
	if _, err := rand.Read(salt); err != nil {
		return "", errors.New("password salt unavailable")
	}
	derived, err := pbkdf2.Key(sha256.New, password, salt, passwordIterations, 32)
	if err != nil {
		return "", errors.New("password derivation unavailable")
	}
	defer clear(derived)
	return "pbkdf2-sha256$600000$" + base64.RawStdEncoding.EncodeToString(salt) + "$" + base64.RawStdEncoding.EncodeToString(derived), nil
}

func decodePassword(value string) ([]byte, []byte, bool) {
	parts := strings.Split(value, "$")
	if len(parts) != 4 || parts[0] != "pbkdf2-sha256" || parts[1] != "600000" {
		return nil, nil, false
	}
	salt, err1 := base64.RawStdEncoding.Strict().DecodeString(parts[2])
	digest, err2 := base64.RawStdEncoding.Strict().DecodeString(parts[3])
	return salt, digest, err1 == nil && err2 == nil && len(salt) == 16 && len(digest) == 32
}

func checkPassword(encoded, password string) bool {
	salt, expected, ok := decodePassword(encoded)
	if !ok {
		// Unknown accounts still perform the same work as a real verifier.
		salt, expected = make([]byte, 16), make([]byte, 32)
	}
	actual, err := pbkdf2.Key(sha256.New, password, salt, passwordIterations, 32)
	defer clear(actual)
	return err == nil && subtle.ConstantTimeCompare(actual, expected) == 1 && ok
}

func validateRegistry(registry Registry, profiles map[string]bool) error {
	if registry.Version != 1 || len(registry.Users) == 0 || len(registry.Users) > 64 {
		return errors.New("invalid access account registry")
	}
	seen := make(map[string]bool)
	for _, user := range registry.Users {
		if !accountID.MatchString(user.ID) || seen[user.ID] || len(user.Profiles) == 0 || len(user.Profiles) > 128 {
			return errors.New("invalid or duplicate access account")
		}
		seen[user.ID] = true
		if _, _, ok := decodePassword(user.PasswordHash); !ok {
			return errors.New("invalid access password verifier")
		}
		grants := make(map[string]bool)
		for _, profile := range user.Profiles {
			if profile == "" || grants[profile] || (profiles != nil && !profiles[profile]) {
				return errors.New("invalid access Profile grant")
			}
			grants[profile] = true
		}
	}
	return nil
}

// ReadRegistry refuses a symlink, permissive file, extra JSON or unbounded
// registry. Its digest is a revision, never a password verifier in logs.
func ReadRegistry(path string, profiles map[string]bool) (Registry, [32]byte, error) {
	var registry Registry
	var digest [32]byte
	file, err := os.OpenFile(path, os.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if err != nil {
		return registry, digest, errors.New("access account file unavailable")
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 || info.Size() > 1<<20 {
		return registry, digest, errors.New("access account file must be private and regular")
	}
	if stat, ok := info.Sys().(*syscall.Stat_t); !ok || stat.Nlink != 1 || stat.Uid != uint32(os.Geteuid()) {
		return registry, digest, errors.New("access account file ownership is invalid")
	}
	raw, err := io.ReadAll(io.LimitReader(file, (1<<20)+1))
	if err != nil || len(raw) > 1<<20 {
		return registry, digest, errors.New("access account file cannot be read")
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&registry) != nil {
		return Registry{}, digest, errors.New("access account file is invalid")
	}
	var extra any
	if !errors.Is(decoder.Decode(&extra), io.EOF) {
		return Registry{}, digest, errors.New("access account file has trailing data")
	}
	if err := validateRegistry(registry, profiles); err != nil {
		return Registry{}, digest, err
	}
	return registry, sha256.Sum256(raw), nil
}

// WriteRegistry atomically replaces only an explicitly chosen private file.
// The command calling it is responsible for explicit account replacement.
func WriteRegistry(path string, registry Registry) error {
	if err := validateRegistry(registry, nil); err != nil {
		return err
	}
	parent := filepath.Dir(path)
	info, err := os.Lstat(parent)
	if err != nil || !info.IsDir() || info.Mode().Perm()&0o077 != 0 {
		return errors.New("access account directory must already exist with private permissions")
	}
	if owner, ok := info.Sys().(*syscall.Stat_t); !ok || owner.Uid != uint32(os.Geteuid()) {
		return errors.New("access account directory ownership is invalid")
	}
	if info, err := os.Lstat(path); err == nil && (!info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0) {
		return errors.New("refusing to replace a non-private account file")
	} else if err != nil && !errors.Is(err, os.ErrNotExist) {
		return errors.New("cannot inspect account destination")
	}
	raw, err := json.MarshalIndent(registry, "", "  ")
	if err != nil {
		return errors.New("cannot encode account registry")
	}
	file, err := os.CreateTemp(parent, ".access-accounts-*")
	if err != nil {
		return errors.New("cannot stage account registry")
	}
	defer os.Remove(file.Name())
	if _, err = file.Write(append(raw, '\n')); err == nil {
		err = file.Sync()
	}
	closeErr := file.Close()
	if err != nil || closeErr != nil || os.Rename(file.Name(), path) != nil {
		return errors.New("cannot persist account registry")
	}
	dir, err := os.Open(parent)
	if err != nil {
		return errors.New("cannot sync account directory")
	}
	defer dir.Close()
	return dir.Sync()
}
