package proxy

import (
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	ListenAddress      string   `json:"listen_address"`
	UpstreamHost       string   `json:"upstream_host"`
	UpstreamPort       int      `json:"upstream_port"`
	UsernameFile       string   `json:"username_file"`
	PasswordFile       string   `json:"password_file"`
	ClientCIDRs        []string `json:"client_cidrs,omitempty"`
	DialTimeoutSeconds int      `json:"dial_timeout_seconds,omitempty"`
	IdleTimeoutSeconds int      `json:"idle_timeout_seconds,omitempty"`
}

type RuntimeConfig struct {
	ListenAddress   string
	UpstreamAddress string
	Username        string
	Password        string
	AllowedClients  []*net.IPNet
	DialTimeout     time.Duration
	IdleTimeout     time.Duration
}

func (c Config) Resolve(baseDir string) (RuntimeConfig, error) {
	listenAddress := strings.TrimSpace(c.ListenAddress)
	if listenAddress == "" {
		return RuntimeConfig{}, errors.New("listen_address is required")
	}
	listenHost, _, err := net.SplitHostPort(listenAddress)
	if err != nil {
		return RuntimeConfig{}, fmt.Errorf("invalid listen_address: %w", err)
	}
	upstreamHost := strings.TrimSpace(c.UpstreamHost)
	if upstreamHost == "" {
		return RuntimeConfig{}, errors.New("upstream_host is required")
	}
	if strings.ContainsAny(upstreamHost, "/@") || strings.ContainsAny(upstreamHost, " \t\r\n") {
		return RuntimeConfig{}, errors.New("upstream_host must be a host without scheme or credentials")
	}
	if net.ParseIP(upstreamHost) == nil && strings.Contains(upstreamHost, ":") {
		return RuntimeConfig{}, errors.New("upstream_host contains an invalid port or IPv6 address")
	}
	if c.UpstreamPort < 1 || c.UpstreamPort > 65535 {
		return RuntimeConfig{}, errors.New("upstream_port must be between 1 and 65535")
	}
	if c.DialTimeoutSeconds == 0 {
		c.DialTimeoutSeconds = 15
	}
	if c.DialTimeoutSeconds < 1 || c.DialTimeoutSeconds > 60 {
		return RuntimeConfig{}, errors.New("dial_timeout_seconds must be between 1 and 60")
	}
	if c.IdleTimeoutSeconds == 0 {
		c.IdleTimeoutSeconds = 300
	}
	if c.IdleTimeoutSeconds < 10 || c.IdleTimeoutSeconds > 3600 {
		return RuntimeConfig{}, errors.New("idle_timeout_seconds must be between 10 and 3600")
	}
	usernamePath := strings.TrimSpace(c.UsernameFile)
	passwordPath := strings.TrimSpace(c.PasswordFile)
	if (usernamePath == "") != (passwordPath == "") {
		return RuntimeConfig{}, errors.New("username_file and password_file must both be set or both be empty")
	}
	username, err := readSecret(baseDir, usernamePath)
	if err != nil {
		return RuntimeConfig{}, fmt.Errorf("read username secret: %w", err)
	}
	password, err := readSecret(baseDir, passwordPath)
	if err != nil {
		return RuntimeConfig{}, fmt.Errorf("read password secret: %w", err)
	}
	if usernamePath != "" && (username == "" || password == "") {
		return RuntimeConfig{}, errors.New("configured username and password secrets must not be empty")
	}
	allowed, err := parseCIDRs(c.ClientCIDRs)
	if err != nil {
		return RuntimeConfig{}, err
	}
	listenIP := net.ParseIP(listenHost)
	loopback := listenHost == "localhost" || (listenIP != nil && listenIP.IsLoopback())
	if !loopback && len(allowed) == 0 {
		return RuntimeConfig{}, errors.New("client_cidrs is required when listen_address is not loopback")
	}
	return RuntimeConfig{
		ListenAddress:   listenAddress,
		UpstreamAddress: net.JoinHostPort(upstreamHost, strconv.Itoa(c.UpstreamPort)),
		Username:        username, Password: password, AllowedClients: allowed,
		DialTimeout: time.Duration(c.DialTimeoutSeconds) * time.Second,
		IdleTimeout: time.Duration(c.IdleTimeoutSeconds) * time.Second,
	}, nil
}

func readSecret(baseDir, path string) (string, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return "", nil
	}
	if !filepath.IsAbs(path) {
		path = filepath.Join(baseDir, path)
	}
	info, err := os.Stat(path)
	if err != nil {
		return "", err
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
		return "", fmt.Errorf("secret file must be regular and mode 0600 or stricter")
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	value := strings.TrimSpace(string(data))
	if strings.ContainsAny(value, "\r\n") {
		return "", errors.New("secret file must contain one value")
	}
	return value, nil
}

func parseCIDRs(values []string) ([]*net.IPNet, error) {
	result := make([]*net.IPNet, 0, len(values))
	for _, value := range values {
		_, network, err := net.ParseCIDR(strings.TrimSpace(value))
		if err != nil {
			return nil, fmt.Errorf("invalid client CIDR: %w", err)
		}
		result = append(result, network)
	}
	return result, nil
}
