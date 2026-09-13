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

type Config struct {
	ListenAddress     string               `json:"listen_address"`
	AllowRemoteListen bool                 `json:"allow_remote_listen"`
	PublicBaseURL     string               `json:"public_base_url"`
	StateFile         string               `json:"state_file"`
	ControlSocket     string               `json:"control_socket,omitempty"`
	SealSkin          SealSkin             `json:"sealskin"`
	Profiles          []profile.Definition `json:"profiles"`
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
	if cfg.SealSkin.LifecycleEnabled && cfg.ControlSocket == "" && cfg.StateFile != "" {
		cfg.ControlSocket = cfg.StateFile + ".control.sock"
	}
	cfg.SealSkin.ServerPublicKeyFile = resolvePath(baseDir, cfg.SealSkin.ServerPublicKeyFile)
	cfg.SealSkin.ClientPrivateKeyFile = resolvePath(baseDir, cfg.SealSkin.ClientPrivateKeyFile)
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
	if len(cfg.Profiles) == 0 {
		return errors.New("at least one profile is required")
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
