package access

import (
	"errors"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
)

const (
	RoleAdmin = "admin"
	RoleUser  = "user"
)

var (
	ErrLastAdmin       = errors.New("the last enabled administrator cannot be disabled or demoted")
	ErrAccountExists   = errors.New("account already exists")
	ErrAccountNotFound = errors.New("account not found")
	ErrUnknownProfile  = errors.New("grant contains an unknown Profile")
)

// EffectiveRole maps the persisted role to one of the two known roles; every
// version 1 account and every empty role is an ordinary entry account.
func (a Account) EffectiveRole() string {
	if a.Role == RoleAdmin {
		return RoleAdmin
	}
	return RoleUser
}

// AccountStore serializes registry changes across the CLI and the running
// gateway with the registry's lock file, and applies the invariants that a
// bare WriteRegistry does not know about (last administrator, known Profiles).
type AccountStore struct {
	path     string
	profiles func() map[string]bool
}

// NewAccountStore binds a private registry file. profiles reports the Profile
// IDs that may be granted; nil accepts any grant already in the file.
func NewAccountStore(path string, profiles func() map[string]bool) *AccountStore {
	return &AccountStore{path: path, profiles: profiles}
}

func (s *AccountStore) known() map[string]bool {
	if s.profiles == nil {
		return nil
	}
	return s.profiles()
}

// Mutate loads the registry under the lock, applies change and writes the
// result atomically. A missing registry is created only when allowCreate is
// set, so an accidental path never becomes a new empty account table.
func (s *AccountStore) Mutate(allowCreate bool, change func(*Registry) error) error {
	known := s.known()
	return s.mutate(allowCreate, known, known, change)
}

// mutate permits a narrowly broader set while loading than it permits in the
// final registry. This is used only to remove a Profile grant after the
// authoritative Profile directory has stopped advertising that Profile.
func (s *AccountStore) mutate(allowCreate bool, readProfiles, finalProfiles map[string]bool, change func(*Registry) error) error {
	parent, err := os.Lstat(filepath.Dir(s.path))
	if err != nil || !parent.IsDir() || parent.Mode().Perm()&0o077 != 0 {
		return errors.New("create the account directory with mode 0700 before use")
	}
	lock, err := os.OpenFile(s.path+".lock", os.O_CREATE|os.O_RDWR|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0o600)
	if err != nil {
		return errors.New("account registry lock unavailable")
	}
	defer lock.Close()
	info, err := lock.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
		return errors.New("unsafe account registry lock")
	}
	if owner, ok := info.Sys().(*syscall.Stat_t); !ok || owner.Nlink != 1 || owner.Uid != uint32(os.Geteuid()) {
		return errors.New("unsafe account registry lock ownership")
	}
	if syscall.Flock(int(lock.Fd()), syscall.LOCK_EX) != nil {
		return errors.New("account registry lock failed")
	}
	defer syscall.Flock(int(lock.Fd()), syscall.LOCK_UN) //nolint:errcheck
	registry := Registry{Version: 1}
	if _, err := os.Lstat(s.path); err == nil {
		registry, _, err = ReadRegistry(s.path, readProfiles)
		if err != nil {
			return err
		}
	} else if !errors.Is(err, os.ErrNotExist) || !allowCreate {
		return errors.New("account registry unavailable")
	}
	if err := change(&registry); err != nil {
		return err
	}
	registry.Version = registryVersion(registry)
	if err := validateRegistry(registry, finalProfiles); err != nil {
		return err
	}
	return WriteRegistry(s.path, registry)
}

func findAccount(registry *Registry, id string) int {
	for i, account := range registry.Users {
		if account.ID == id {
			return i
		}
	}
	return -1
}

func enabledAdmins(registry Registry) int {
	count := 0
	for _, account := range registry.Users {
		if !account.Disabled && account.EffectiveRole() == RoleAdmin {
			count++
		}
	}
	return count
}

func normalizeGrants(grants []string, known map[string]bool) ([]string, error) {
	seen := make(map[string]bool, len(grants))
	var result []string
	for _, grant := range grants {
		grant = strings.TrimSpace(grant)
		if grant == "" || seen[grant] {
			continue
		}
		if known != nil && !known[grant] {
			return nil, ErrUnknownProfile
		}
		seen[grant] = true
		result = append(result, grant)
	}
	sort.Strings(result)
	return result, nil
}

// Put creates an account or, with replace, replaces its password, grants and
// role and re-enables it. An empty role keeps the existing role on replace
// and means "user" on create.
func (s *AccountStore) Put(id, password, role string, grants []string, replace bool) error {
	if !accountID.MatchString(id) {
		return errors.New("invalid account ID")
	}
	if role != "" && role != RoleAdmin && role != RoleUser {
		return errors.New("role must be admin or user")
	}
	verifier, err := HashPassword(password)
	if err != nil {
		return err
	}
	return s.Mutate(true, func(registry *Registry) error {
		normalized, err := normalizeGrants(grants, s.known())
		if err != nil {
			return err
		}
		index := findAccount(registry, id)
		if index >= 0 && !replace {
			return ErrAccountExists
		}
		account := Account{ID: id, PasswordHash: verifier, Profiles: normalized, Role: role}
		if index >= 0 {
			previous := registry.Users[index]
			if account.Role == "" {
				account.Role = previous.Role
			}
			if previous.EffectiveRole() == RoleAdmin && account.EffectiveRole() != RoleAdmin && !previous.Disabled && enabledAdmins(*registry) <= 1 {
				return ErrLastAdmin
			}
			registry.Users[index] = account
		} else {
			registry.Users = append(registry.Users, account)
		}
		return nil
	})
}

// SetPassword replaces only the password verifier of an existing account.
func (s *AccountStore) SetPassword(id, password string) error {
	verifier, err := HashPassword(password)
	if err != nil {
		return err
	}
	return s.Mutate(false, func(registry *Registry) error {
		index := findAccount(registry, id)
		if index < 0 {
			return ErrAccountNotFound
		}
		registry.Users[index].PasswordHash = verifier
		return nil
	})
}

// SetDisabled enables or disables an account; the last enabled administrator
// stays enabled.
func (s *AccountStore) SetDisabled(id string, disabled bool) error {
	return s.Mutate(false, func(registry *Registry) error {
		index := findAccount(registry, id)
		if index < 0 {
			return ErrAccountNotFound
		}
		account := registry.Users[index]
		if disabled && !account.Disabled && account.EffectiveRole() == RoleAdmin && enabledAdmins(*registry) <= 1 {
			return ErrLastAdmin
		}
		registry.Users[index].Disabled = disabled
		return nil
	})
}

// SetGrants replaces the Profiles an account may open.
func (s *AccountStore) SetGrants(id string, grants []string) error {
	return s.Mutate(false, func(registry *Registry) error {
		normalized, err := normalizeGrants(grants, s.known())
		if err != nil {
			return err
		}
		index := findAccount(registry, id)
		if index < 0 {
			return ErrAccountNotFound
		}
		registry.Users[index].Profiles = normalized
		return nil
	})
}

// RemoveProfileGrants atomically removes one Profile from every account even
// when the Profile directory has already marked it deleted. An ordinary entry
// account whose only grant was the deleted Profile is removed as it can no
// longer satisfy the registry invariant or log into any browser. Administrators
// may remain with no explicit start grants and retain management access.
func (s *AccountStore) RemoveProfileGrants(profileID string) error {
	profileID = strings.TrimSpace(profileID)
	known := s.known()
	if profileID == "" || known == nil {
		return errors.New("Profile grant cleanup requires the authoritative Profile set")
	}
	readable := make(map[string]bool, len(known)+1)
	for id := range known {
		readable[id] = true
	}
	readable[profileID] = true
	return s.mutate(false, readable, known, func(registry *Registry) error {
		users := make([]Account, 0, len(registry.Users))
		for _, account := range registry.Users {
			grants := account.Profiles[:0]
			for _, grant := range account.Profiles {
				if grant != profileID {
					grants = append(grants, grant)
				}
			}
			account.Profiles = grants
			if len(account.Profiles) == 0 && account.EffectiveRole() != RoleAdmin {
				continue
			}
			users = append(users, account)
		}
		registry.Users = users
		return nil
	})
}

// SetRole promotes or demotes an account; the last enabled administrator
// cannot be demoted.
func (s *AccountStore) SetRole(id, role string) error {
	if role != RoleAdmin && role != RoleUser {
		return errors.New("role must be admin or user")
	}
	return s.Mutate(false, func(registry *Registry) error {
		index := findAccount(registry, id)
		if index < 0 {
			return ErrAccountNotFound
		}
		account := registry.Users[index]
		if account.EffectiveRole() == RoleAdmin && role != RoleAdmin && !account.Disabled && enabledAdmins(*registry) <= 1 {
			return ErrLastAdmin
		}
		registry.Users[index].Role = role
		return nil
	})
}

// Snapshot returns the accounts without password verifiers, for listings.
func (s *AccountStore) Snapshot() ([]Account, error) {
	registry, _, err := ReadRegistry(s.path, s.known())
	if err != nil {
		return nil, err
	}
	accounts := make([]Account, 0, len(registry.Users))
	for _, account := range registry.Users {
		account.PasswordHash = ""
		accounts = append(accounts, account)
	}
	sort.Slice(accounts, func(i, j int) bool { return accounts[i].ID < accounts[j].ID })
	return accounts, nil
}
