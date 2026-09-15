// Command profile-accounts manages a private local-login registry. Passwords
// are read from stdin, never from arguments, environment variables or output.
package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/config"
)

func main() {
	if err := run(os.Args[1:], os.Stdin); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println("Account registry operation completed.")
}

func run(args []string, input io.Reader) error {
	if len(args) == 0 || (args[0] != "put" && args[0] != "disable" && args[0] != "check") {
		return errors.New("use profile-accounts put|disable|check --config <adapter-config>")
	}
	command := args[0]
	flags := flag.NewFlagSet("profile-accounts", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	configPath := flags.String("config", "", "Adapter config containing access.users_file")
	user := flags.String("user", "", "account ID")
	grants := flags.String("profiles", "", "comma-separated Profile IDs")
	replace := flags.Bool("replace", false, "explicitly replace an existing account and its password/grants")
	if flags.Parse(args[1:]) != nil || flags.NArg() != 0 || *configPath == "" {
		return errors.New("invalid account command arguments")
	}
	cfg, err := config.Load(*configPath)
	if err != nil || cfg.Access == nil {
		return errors.New("valid Adapter access configuration is required")
	}
	profiles := make(map[string]bool)
	for _, profile := range cfg.Profiles {
		profiles[profile.ID] = true
	}
	path := cfg.Access.UsersFile
	parent, err := os.Lstat(filepath.Dir(path))
	if err != nil || !parent.IsDir() || parent.Mode().Perm()&0o077 != 0 {
		return errors.New("create the account directory with mode 0700 before use")
	}
	lock, err := os.OpenFile(path+".lock", os.O_CREATE|os.O_RDWR|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0o600)
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
	registry := access.Registry{Version: 1}
	if _, err := os.Lstat(path); err == nil {
		registry, _, err = access.ReadRegistry(path, profiles)
		if err != nil {
			return err
		}
	} else if !errors.Is(err, os.ErrNotExist) || command != "put" {
		return errors.New("account registry unavailable")
	}
	if command == "check" {
		if *user != "" || *grants != "" || *replace {
			return errors.New("check accepts only the configuration path")
		}
		return nil
	}
	index := -1
	for i, account := range registry.Users {
		if account.ID == *user {
			index = i
		}
	}
	if command == "disable" {
		if index < 0 || *grants != "" || *replace {
			return errors.New("disable requires one existing account")
		}
		registry.Users[index].Disabled = true
	} else {
		if index >= 0 && !*replace {
			return errors.New("account already exists; replacement requires --replace")
		}
		selected := strings.Split(*grants, ",")
		for _, profile := range selected {
			if !profiles[profile] {
				return errors.New("grant contains an unknown Profile")
			}
		}
		raw, err := io.ReadAll(io.LimitReader(input, 259))
		defer clear(raw)
		if err != nil || len(raw) > 258 {
			return errors.New("password input is unavailable or too long")
		}
		password := strings.TrimSuffix(strings.TrimSuffix(string(raw), "\n"), "\r")
		if strings.ContainsAny(password, "\r\n") {
			return errors.New("password input must contain a single line")
		}
		verifier, err := access.HashPassword(password)
		password = ""
		if err != nil {
			return err
		}
		account := access.Account{ID: *user, PasswordHash: verifier, Profiles: selected}
		if index < 0 {
			registry.Users = append(registry.Users, account)
		} else {
			registry.Users[index] = account
		}
	}
	return access.WriteRegistry(path, registry)
}
