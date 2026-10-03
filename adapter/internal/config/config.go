package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
)

type SealSkin struct {
	APIBaseURL           string `json:"api_base_url"`
	PublicSessionBaseURL string `json:"public_session_base_url"`
	Username             string `json:"username"`
	ServerPublicKeyFile  string `json:"server_public_key_file"`
	ClientPrivateKeyFile string `json:"client_private_key_file"`
	AllowUnencryptedHTTP bool   `json:"allow_unencrypted_http"`
	LifecycleEnabled     bool   `json:"lifecycle_enabled"`
}

// SealSkinAdmin is the separate identity allowed to install/delete
// applications and archive Homes. It shares the verified private endpoint
// and server identity with SealSkin but never owns launches or lifecycle.
type SealSkinAdmin struct {
	Username             string `json:"username"`
	ClientPrivateKeyFile string `json:"client_private_key_file"`
}

// Health tunes the read-only runtime health reports. Omitted fields use the
// defaults; sample_interval_seconds 0 disables background sampling.
type Health struct {
	SampleIntervalSeconds *int  `json:"sample_interval_seconds,omitempty"`
	EntryHint             *bool `json:"entry_hint,omitempty"`
	EntryWaitSeconds      *int  `json:"entry_wait_seconds,omitempty"`
}

const (
	DefaultHealthSampleIntervalSeconds = 60
	DefaultHealthEntryWaitSeconds      = 3
)

func (h Health) SampleInterval() time.Duration {
	if h.SampleIntervalSeconds == nil {
		return DefaultHealthSampleIntervalSeconds * time.Second
	}
	return time.Duration(*h.SampleIntervalSeconds) * time.Second
}

func (h Health) EntryHintEnabled() bool {
	return h.EntryHint == nil || *h.EntryHint
}

func (h Health) EntryWait() time.Duration {
	if h.EntryWaitSeconds == nil {
		return DefaultHealthEntryWaitSeconds * time.Second
	}
	return time.Duration(*h.EntryWaitSeconds) * time.Second
}

// Startup tunes boot-time behaviour. control_wait_seconds bounds how long the
// adapter waits for the SealSkin control plane before startup reconciliation.
type Startup struct {
	ControlWaitSeconds *int `json:"control_wait_seconds,omitempty"`
}

const DefaultStartupControlWaitSeconds = 120

func (s Startup) ControlWait() time.Duration {
	if s.ControlWaitSeconds == nil {
		return DefaultStartupControlWaitSeconds * time.Second
	}
	return time.Duration(*s.ControlWaitSeconds) * time.Second
}

type Config struct {
	ListenAddress     string `json:"listen_address"`
	AllowRemoteListen bool   `json:"allow_remote_listen"`
	PublicBaseURL     string `json:"public_base_url"`
	StateFile         string `json:"state_file"`
	ControlSocket     string `json:"control_socket,omitempty"`
	// ProfileDirectory persists browser definitions so the management
	// surface can change them; the configured profiles seed its first import.
	ProfileDirectory   string `json:"profile_directory,omitempty"`
	EnvironmentCatalog string `json:"environment_catalog,omitempty"`
	// TemplateCatalog is R7D's explicit browser/display compatibility directory.
	// It depends on environment_catalog for immutable fingerprint artifacts.
	TemplateCatalog         string `json:"template_catalog,omitempty"`
	LegacyNetworkMigrations string `json:"legacy_network_migrations,omitempty"`
	// NetworkProfileCatalog is R7C's independent unified proxy directory.
	NetworkProfileCatalog string `json:"network_profile_catalog,omitempty"`
	// ProxyTemplate enables R6D proxy drafts: the fixed owner, Relay/probe
	// image digests and approved probe URL every generated policy shares.
	ProxyTemplate *profile.ProxyTemplate `json:"proxy_template,omitempty"`
	// DirectTemplate enables server-side materialization of controlled DIRECT
	// policies for R7E browser creation and switching.
	DirectTemplate *profile.DirectTemplate `json:"direct_template,omitempty"`
	// EnvironmentJobSpool is the private directory shared with the host-side
	// custom fingerprint job runner (R6E); it requires environment_catalog.
	EnvironmentJobSpool string               `json:"environment_job_spool,omitempty"`
	SealSkin            SealSkin             `json:"sealskin"`
	SealSkinAdmin       *SealSkinAdmin       `json:"sealskin_admin,omitempty"`
	Health              Health               `json:"health"`
	Startup             Startup              `json:"startup"`
	Access              *access.Config       `json:"access,omitempty"`
	Limits              profile.Limits       `json:"limits"`
	Profiles            []profile.Definition `json:"profiles"`
}

func Load(path string) (Config, error) {
	var cfg Config
	file, err := os.Open(path)
	if err != nil {
		return cfg, fmt.Errorf("open config: %w", err)
	}
	defer file.Close()
	decoder := json.NewDecoder(io.LimitReader(file, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&cfg); err != nil {
		return cfg, fmt.Errorf("decode config: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return cfg, errors.New("config contains more than one JSON value")
	}
	if cfg.ListenAddress == "" {
		cfg.ListenAddress = "127.0.0.1:8080"
	}
	baseDir, err := filepath.Abs(filepath.Dir(path))
	if err != nil {
		return cfg, err
	}
	cfg.StateFile = resolvePath(baseDir, cfg.StateFile)
	cfg.ControlSocket = resolvePath(baseDir, cfg.ControlSocket)
	cfg.ProfileDirectory = resolvePath(baseDir, cfg.ProfileDirectory)
	cfg.EnvironmentCatalog = resolvePath(baseDir, cfg.EnvironmentCatalog)
	cfg.TemplateCatalog = resolvePath(baseDir, cfg.TemplateCatalog)
	cfg.LegacyNetworkMigrations = resolvePath(baseDir, cfg.LegacyNetworkMigrations)
	cfg.NetworkProfileCatalog = resolvePath(baseDir, cfg.NetworkProfileCatalog)
	cfg.EnvironmentJobSpool = resolvePath(baseDir, cfg.EnvironmentJobSpool)
	if cfg.SealSkin.LifecycleEnabled && cfg.ControlSocket == "" && cfg.StateFile != "" {
		cfg.ControlSocket = cfg.StateFile + ".control.sock"
	}
	cfg.SealSkin.ServerPublicKeyFile = resolvePath(baseDir, cfg.SealSkin.ServerPublicKeyFile)
	cfg.SealSkin.ClientPrivateKeyFile = resolvePath(baseDir, cfg.SealSkin.ClientPrivateKeyFile)
	if cfg.SealSkinAdmin != nil {
		cfg.SealSkinAdmin.ClientPrivateKeyFile = resolvePath(baseDir, cfg.SealSkinAdmin.ClientPrivateKeyFile)
	}
	cfg.Limits.StoragePath = resolvePath(baseDir, cfg.Limits.StoragePath)
	if cfg.Access != nil {
		cfg.Access.UsersFile = resolvePath(baseDir, cfg.Access.UsersFile)
		cfg.Access.SessionCAFile = resolvePath(baseDir, cfg.Access.SessionCAFile)
	}
	if err := cfg.Validate(); err != nil {
		return cfg, err
	}
	return cfg, nil
}

func (cfg Config) Validate() error {
	if cfg.StateFile == "" {
		return errors.New("state_file is required")
	}
	if err := validateListen(cfg.ListenAddress, cfg.AllowRemoteListen); err != nil {
		return err
	}
	if err := absoluteHTTPS("public_base_url", cfg.PublicBaseURL); err != nil {
		return err
	}
	if err := absoluteHTTPS("sealskin.public_session_base_url", cfg.SealSkin.PublicSessionBaseURL); err != nil {
		return err
	}
	if cfg.SealSkin.APIBaseURL == "" || cfg.SealSkin.Username == "" ||
		cfg.SealSkin.ServerPublicKeyFile == "" || cfg.SealSkin.ClientPrivateKeyFile == "" {
		return errors.New("SealSkin API URL, username and both key files are required")
	}
	if len(cfg.Profiles) == 0 && cfg.ProfileDirectory == "" {
		return errors.New("at least one profile is required")
	}
	if cfg.ProfileDirectory != "" && !cfg.SealSkin.LifecycleEnabled {
		return errors.New("profile_directory requires sealskin.lifecycle_enabled")
	}
	if cfg.EnvironmentCatalog != "" && cfg.ProfileDirectory == "" {
		return errors.New("environment_catalog requires profile_directory")
	}
	if cfg.EnvironmentCatalog != "" && (cfg.SealSkinAdmin == nil || cfg.SealSkinAdmin.Username == "" || cfg.SealSkinAdmin.ClientPrivateKeyFile == "") {
		return errors.New("environment_catalog requires a separate sealskin_admin identity")
	}
	if cfg.EnvironmentJobSpool != "" && cfg.EnvironmentCatalog == "" {
		return errors.New("environment_job_spool requires environment_catalog")
	}
	if cfg.TemplateCatalog != "" && cfg.EnvironmentCatalog == "" {
		return errors.New("template_catalog requires environment_catalog")
	}
	if cfg.LegacyNetworkMigrations != "" && (cfg.DirectTemplate == nil || cfg.EnvironmentCatalog == "" || cfg.Access == nil) {
		return errors.New("legacy_network_migrations requires direct_template, environment_catalog and access")
	}
	if cfg.ProxyTemplate != nil {
		if cfg.EnvironmentCatalog == "" {
			return errors.New("proxy_template requires environment_catalog and sealskin_admin")
		}
		if cfg.ProxyTemplate.Owner != cfg.SealSkin.Username {
			return errors.New("proxy_template.owner must equal sealskin.username")
		}
		if err := cfg.ProxyTemplate.Validate(); err != nil {
			return err
		}
	}
	if cfg.DirectTemplate != nil {
		if cfg.EnvironmentCatalog == "" {
			return errors.New("direct_template requires environment_catalog and sealskin_admin")
		}
		if cfg.DirectTemplate.Owner != cfg.SealSkin.Username {
			return errors.New("direct_template.owner must equal sealskin.username")
		}
		if err := cfg.DirectTemplate.Validate(); err != nil {
			return err
		}
	}
	if cfg.NetworkProfileCatalog != "" && cfg.ProxyTemplate == nil {
		return errors.New("network_profile_catalog requires proxy_template")
	}
	if cfg.Access != nil {
		if err := cfg.Access.Validate(); err != nil {
			return err
		}
		if !cfg.SealSkin.LifecycleEnabled || cfg.AllowRemoteListen {
			return errors.New("access requires the verified lifecycle and a loopback listener")
		}
		if cfg.PublicBaseURL == cfg.SealSkin.PublicSessionBaseURL {
			return errors.New("access requires separate entry and Session origins")
		}
		if cfg.SealSkin.AllowUnencryptedHTTP || strings.TrimRight(cfg.SealSkin.APIBaseURL, "/") != strings.TrimRight(cfg.Access.SessionUpstreamURL, "/") {
			return errors.New("access requires the control API to use the same verified private HTTPS listener")
		}
	}
	if interval := cfg.Health.SampleIntervalSeconds; interval != nil && *interval != 0 && (*interval < 10 || *interval > 3600) {
		return errors.New("health.sample_interval_seconds must be 0 or between 10 and 3600")
	}
	if wait := cfg.Health.EntryWaitSeconds; wait != nil && (*wait < 1 || *wait > 30) {
		return errors.New("health.entry_wait_seconds must be between 1 and 30")
	}
	if wait := cfg.Startup.ControlWaitSeconds; wait != nil && (*wait < 0 || *wait > 900) {
		return errors.New("startup.control_wait_seconds must be between 0 and 900")
	}
	if err := cfg.Limits.Validate(); err != nil {
		return err
	}
	for _, definition := range cfg.Profiles {
		if definition.IdlePolicy.Enabled() && !cfg.SealSkin.LifecycleEnabled {
			return errors.New("idle_policy requires sealskin.lifecycle_enabled")
		}
	}
	for _, definition := range cfg.Profiles {
		if (definition.NetworkPolicyID != "" || definition.NetworkPolicySHA256 != "") && !cfg.SealSkin.LifecycleEnabled {
			return errors.New("network policies require sealskin.lifecycle_enabled")
		}
	}
	return nil
}

func validateListen(address string, allowRemote bool) error {
	host, _, err := net.SplitHostPort(address)
	if err != nil {
		return fmt.Errorf("invalid listen_address: %w", err)
	}
	if allowRemote {
		return nil
	}
	if host == "localhost" {
		return nil
	}
	ip := net.ParseIP(host)
	if ip == nil || !ip.IsLoopback() {
		return errors.New("listen_address must be loopback unless allow_remote_listen is explicitly true")
	}
	return nil
}

func absoluteHTTPS(name, value string) error {
	parsed, err := url.Parse(value)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" {
		return fmt.Errorf("%s must be an absolute HTTPS URL", name)
	}
	if parsed.RawQuery != "" || parsed.Fragment != "" {
		return fmt.Errorf("%s must not contain a query or fragment", name)
	}
	if parsed.User != nil {
		return fmt.Errorf("%s must not contain user credentials", name)
	}
	if parsed.Path != "" && parsed.Path != "/" {
		return fmt.Errorf("%s must be an HTTPS origin without a path", name)
	}
	return nil
}

func resolvePath(baseDir, value string) string {
	value = strings.TrimSpace(value)
	if value == "" || filepath.IsAbs(value) {
		return value
	}
	return filepath.Join(baseDir, value)
}
