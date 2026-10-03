// Command profile-accounts manages a private local-login registry. Passwords
// are read from stdin, never from arguments, environment variables or output.
package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/config"
	"browser-platform/adapter/internal/profile"
)

func main() {
	if err := run(os.Args[1:], os.Stdin); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Println("Account registry operation completed.")
}

func run(args []string, input io.Reader) error {
	if len(args) == 0 || (args[0] != "init" && args[0] != "put" && args[0] != "disable" && args[0] != "enable" && args[0] != "role" && args[0] != "ungrant-profile" && args[0] != "check") {
		return errors.New("use profile-accounts init|put|disable|enable|role|ungrant-profile|check --config <adapter-config>")
	}
	command := args[0]
	flags := flag.NewFlagSet("profile-accounts", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	configPath := flags.String("config", "", "Adapter config containing access.users_file")
	user := flags.String("user", "", "account ID")
	grants := flags.String("profiles", "", "comma-separated Profile IDs")
	replace := flags.Bool("replace", false, "explicitly replace an existing account and its password/grants")
	role := flags.String("role", "", "account role: admin or user (default user on create, unchanged on replace)")
	profileID := flags.String("profile", "", "deleted Profile ID whose account grants must be removed")
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
	if cfg.ProfileDirectory != "" {
		// The persisted directory is the running Adapter's Profile set; a
		// grant outside it would invalidate the whole table on reload.
		ids, err := profile.DirectoryProfileIDs(cfg.ProfileDirectory)
		if err != nil {
			return fmt.Errorf("read profile directory: %w", err)
		}
		profiles = make(map[string]bool, len(ids))
		for _, id := range ids {
			profiles[id] = true
		}
	}
	known := func() map[string]bool { return profiles }
	store := access.NewAccountStore(cfg.Access.UsersFile, known)
	switch command {
	case "check":
		if *user != "" || *grants != "" || *replace || *role != "" || *profileID != "" {
			return errors.New("check accepts only the configuration path")
		}
		if _, err := os.Lstat(cfg.Access.UsersFile); err != nil {
			return errors.New("account registry unavailable")
		}
		_, _, err := access.ReadRegistry(cfg.Access.UsersFile, known())
		return err
	case "ungrant-profile":
		if *profileID == "" || *user != "" || *grants != "" || *replace || *role != "" {
			return errors.New("ungrant-profile requires one --profile")
		}
		return store.RemoveProfileGrants(*profileID)
	case "disable", "enable":
		if *user == "" || *grants != "" || *replace || *role != "" || *profileID != "" {
			return errors.New(command + " requires one existing account")
		}
		return store.SetDisabled(*user, command == "disable")
	case "role":
		if *user == "" || *grants != "" || *replace || *profileID != "" || (*role != access.RoleAdmin && *role != access.RoleUser) {
			return errors.New("role requires one existing account and --role admin|user")
		}
		return store.SetRole(*user, *role)
	}
	if *user == "" || *profileID != "" {
		return errors.New("put requires --user")
	}
	if command == "init" && (*replace || *role != "" || *grants != "") {
		return errors.New("init accepts only --config and --user")
	}
	var selected []string
	if *grants != "" {
		selected = strings.Split(*grants, ",")
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
	if command == "init" {
		err = store.InitializeAdmin(*user, password)
	} else {
		err = store.Put(*user, password, *role, selected, *replace)
	}
	password = ""
	if errors.Is(err, access.ErrAccountExists) {
		if command == "init" {
			return errors.New("account registry is already initialized")
		}
		return errors.New("account already exists; replacement requires --replace")
	}
	return err
}
