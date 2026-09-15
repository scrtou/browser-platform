package proxy

import (
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

type Config struct {
	CoherenceGateFile     string   `json:"coherence_gate_file,omitempty"`
	CoherenceGeneration   string   `json:"coherence_generation,omitempty"`
	CoherenceProbeDomain  string   `json:"coherence_probe_domain,omitempty"`
	CoherenceProbePort    int      `json:"coherence_probe_port,omitempty"`
	Mode                  string   `json:"mode,omitempty"`
	ApprovedResolverID    string   `json:"approved_resolver_id,omitempty"`
	ApprovedResolverIP    string   `json:"approved_resolver_ip,omitempty"`
	HostIPv4File          string   `json:"host_ipv4_file,omitempty"`
	HostIPv4Snapshot      []string `json:"host_ipv4_snapshot,omitempty"`
	ListenAddress         string   `json:"listen_address"`
	UpstreamHost          string   `json:"upstream_host"`
	UpstreamPort          int      `json:"upstream_port"`
	UpstreamProtocol      string   `json:"upstream_protocol,omitempty"`
	UpstreamAuth          string   `json:"upstream_auth,omitempty"`
	UpstreamTLSServerName string   `json:"upstream_tls_server_name,omitempty"`
	UpstreamTLSCAFile     string   `json:"upstream_tls_ca_file,omitempty"`
	UsernameFile          string   `json:"username_file"`
	PasswordFile          string   `json:"password_file"`
	CredentialLeaseFile   string   `json:"credential_lease_file,omitempty"`
	CredentialLeaseID     string   `json:"credential_lease_id,omitempty"`
	ClientCIDRs           []string `json:"client_cidrs,omitempty"`
	DialTimeoutSeconds    int      `json:"dial_timeout_seconds,omitempty"`
	IdleTimeoutSeconds    int      `json:"idle_timeout_seconds,omitempty"`
}

type RuntimeConfig struct {
	CoherenceGateFile    string
	CoherenceGeneration  string
	CoherenceProbeDomain string
	CoherenceProbePort   uint16
	Mode                 string
	ApprovedResolverID   string
	ApprovedResolverIP   string
	HostIPv4File         string
	HostIPv4Snapshot     []string
	ListenAddress        string
	UpstreamAddress      string
	UpstreamProtocol     string
	UpstreamAuth         string
	UpstreamTLS          *tls.Config
	Username             string
	Password             string
	CredentialLeaseFile  string
	CredentialLeaseID    string
	AllowedClients       []*net.IPNet
	DialTimeout          time.Duration
	IdleTimeout          time.Duration
}

// ParseConfig refuses ambiguous credentials/protocol selections, including
// duplicate and case-variant keys that encoding/json otherwise accepts.
func ParseConfig(raw []byte) (Config, error) {
	var cfg Config
	if len(raw) > 64*1024 {
		return cfg, errors.New("config exceeds size limit")
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	token, err := decoder.Token()
	if err != nil || token != json.Delim('{') {
		return cfg, errors.New("config must be an object")
	}
	seen := make(map[string]bool)
	for decoder.More() {
		token, err := decoder.Token()
		if err != nil {
			return cfg, errors.New("invalid config object")
		}
		key, ok := token.(string)
		if !ok || seen[key] || key != strings.ToLower(key) {
			return cfg, errors.New("duplicate or noncanonical config field")
		}
		seen[key] = true
		var value json.RawMessage
		if err := decoder.Decode(&value); err != nil || bytes.Equal(value, []byte("null")) {
			return cfg, errors.New("invalid or null config field")
		}
	}
	if _, err := decoder.Token(); err != nil {
		return cfg, errors.New("invalid config object")
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return cfg, errors.New("config contains more than one JSON value")
	}
	decoder = json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&cfg); err != nil {
		return cfg, errors.New("invalid config fields")
	}
	return cfg, nil
}

func (c Config) Resolve(baseDir string) (RuntimeConfig, error) {
	gate, err := c.resolveCoherenceGate(baseDir)
	if err != nil {
		return RuntimeConfig{}, err
	}
	listenAddress := strings.TrimSpace(c.ListenAddress)
	if listenAddress == "" {
		return RuntimeConfig{}, errors.New("listen_address is required")
	}
	listenHost, _, err := net.SplitHostPort(listenAddress)
	if err != nil {
		return RuntimeConfig{}, fmt.Errorf("invalid listen_address: %w", err)
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
	allowed, err := parseCIDRs(c.ClientCIDRs)
	if err != nil {
		return RuntimeConfig{}, err
	}
	listenIP := net.ParseIP(listenHost)
	loopback := listenHost == "localhost" || (listenIP != nil && listenIP.IsLoopback())
	if !loopback && len(allowed) == 0 {
		return RuntimeConfig{}, errors.New("client_cidrs is required when listen_address is not loopback")
	}
	if c.Mode == "direct" {
		cfg, err := c.resolveDirect(RuntimeConfig{Mode: "direct", ListenAddress: listenAddress, AllowedClients: allowed,
			DialTimeout: time.Duration(c.DialTimeoutSeconds) * time.Second,
			IdleTimeout: time.Duration(c.IdleTimeoutSeconds) * time.Second})
		return gate.apply(cfg), err
	}
	if c.Mode != "" && c.Mode != "proxy_required" || c.ApprovedResolverID != "" || c.ApprovedResolverIP != "" ||
		c.HostIPv4File != "" || len(c.HostIPv4Snapshot) != 0 {
		return RuntimeConfig{}, errors.New("invalid network mode or mixed direct options")
	}
	upstreamHost := strings.TrimSpace(c.UpstreamHost)
	if upstreamHost == "" {
		return RuntimeConfig{}, errors.New("upstream_host is required")
	}
	if !validHost(upstreamHost) {
		return RuntimeConfig{}, errors.New("upstream_host must be a host without scheme or credentials")
	}
	if c.UpstreamPort < 1 || c.UpstreamPort > 65535 {
		return RuntimeConfig{}, errors.New("upstream_port must be between 1 and 65535")
	}
	usernamePath := strings.TrimSpace(c.UsernameFile)
	passwordPath := strings.TrimSpace(c.PasswordFile)
	if (usernamePath == "") != (passwordPath == "") {
		return RuntimeConfig{}, errors.New("username_file and password_file must both be set or both be empty")
	}
	protocol, auth := c.UpstreamProtocol, c.UpstreamAuth
	if protocol == "" && auth == "" {
		// Preserve the original SOCKS5 configuration contract. New protocol
		// selections require an explicit authentication mode.
		protocol, auth = protocolSOCKS5, authNone
		if usernamePath != "" {
			auth = authUserPass
		}
	}
	if !supportedAuth(protocol, auth) || (auth == authNone) != (usernamePath == "") {
		return RuntimeConfig{}, errUnsupportedAuth
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
	if auth == authUserPass && (len(username) > 255 || len(password) > 255) {
		return RuntimeConfig{}, errors.New("SOCKS5 credentials must be at most 255 bytes")
	}
	if auth == authBasic && strings.Contains(username, ":") {
		return RuntimeConfig{}, errors.New("HTTP Basic username must not contain a colon")
	}
	leasePath := c.CredentialLeaseFile
	if leasePath != "" && !filepath.IsAbs(leasePath) {
		leasePath = filepath.Join(baseDir, leasePath)
	}
	if (leasePath == "") != (c.CredentialLeaseID == "") ||
		(leasePath != "" && (auth == authNone || !validLease(leasePath, c.CredentialLeaseID))) {
		return RuntimeConfig{}, errCredentialLease
	}
	var tlsConfig *tls.Config
	if protocol == protocolHTTPS {
		name := c.UpstreamTLSServerName
		if name == "" {
			name = upstreamHost
		}
		if !validHost(name) {
			return RuntimeConfig{}, errors.New("invalid upstream_tls_server_name")
		}
		tlsConfig = &tls.Config{MinVersion: tls.VersionTLS12, ServerName: name, NextProtos: []string{"http/1.1"}}
		if c.UpstreamTLSCAFile != "" {
			pem, err := readRegularFile(baseDir, c.UpstreamTLSCAFile, 1024*1024, false)
			if err != nil {
				return RuntimeConfig{}, errors.New("upstream TLS CA file unavailable or invalid")
			}
			pool := x509.NewCertPool()
			if !pool.AppendCertsFromPEM(pem) {
				return RuntimeConfig{}, errors.New("upstream TLS CA file contains no certificates")
			}
			tlsConfig.RootCAs = pool
		}
	} else if c.UpstreamTLSServerName != "" || c.UpstreamTLSCAFile != "" {
		return RuntimeConfig{}, errors.New("upstream TLS options require HTTPS")
	}
	return gate.apply(RuntimeConfig{
		Mode:             "proxy_required",
		ListenAddress:    listenAddress,
		UpstreamAddress:  net.JoinHostPort(upstreamHost, strconv.Itoa(c.UpstreamPort)),
		UpstreamProtocol: protocol, UpstreamAuth: auth, UpstreamTLS: tlsConfig,
		Username: username, Password: password, AllowedClients: allowed,
		CredentialLeaseFile: leasePath, CredentialLeaseID: c.CredentialLeaseID,
		DialTimeout: time.Duration(c.DialTimeoutSeconds) * time.Second,
		IdleTimeout: time.Duration(c.IdleTimeoutSeconds) * time.Second,
	}), nil
}

func readSecret(baseDir, path string) (string, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return "", nil
	}
	data, err := readRegularFile(baseDir, path, 4098, true)
	if err != nil {
		return "", err
	}
	// A single text-file line ending is optional. Spaces are credential bytes.
	value := string(data)
	if strings.HasSuffix(value, "\r\n") {
		value = strings.TrimSuffix(value, "\r\n")
	} else {
		value = strings.TrimSuffix(value, "\n")
	}
	if len(value) > 4096 || !utf8.ValidString(value) || strings.ContainsFunc(value, func(r rune) bool { return r < 32 || r == 127 }) {
		return "", errors.New("secret file must contain one value")
	}
	return value, nil
}

func readRegularFile(baseDir, path string, limit int64, private bool) ([]byte, error) {
	if !filepath.IsAbs(path) {
		path = filepath.Join(baseDir, path)
	}
	before, err := os.Lstat(path)
	if err != nil || !before.Mode().IsRegular() {
		return nil, errors.New("file must be regular, without a symbolic link")
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, errors.New("file unavailable")
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || !os.SameFile(before, info) ||
		(private && info.Mode().Perm()&0o077 != 0) || info.Size() > limit {
		return nil, errors.New("file type, permissions or size invalid")
	}
	data, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil || int64(len(data)) > limit {
		return nil, errors.New("file unreadable or too large")
	}
	return data, nil
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
