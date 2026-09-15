package proxy

import (
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"net"
	"net/netip"
	"path/filepath"
	"reflect"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
)

//go:embed direct-denied-ipv4.json
var directDeniedJSON []byte

var directDeniedPrefixes = func() []netip.Prefix {
	var values []string
	if err := json.Unmarshal(directDeniedJSON, &values); err != nil {
		panic("invalid built-in DIRECT address policy")
	}
	var result []netip.Prefix
	for _, value := range values {
		result = append(result, netip.MustParsePrefix(value))
	}
	return result
}()

var (
	errDirectDenied       = errors.New("DIRECT target denied")
	errDirectDNS          = errors.New("approved resolver lookup failed")
	errDirectHostEvidence = errors.New("host address evidence unavailable or changed")
	resolverIDPattern     = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,62}$`)
)

func directPublicIPv4(address netip.Addr) bool {
	if !address.Is4() || !address.IsGlobalUnicast() {
		return false
	}
	for _, prefix := range directDeniedPrefixes {
		if prefix.Contains(address) {
			return false
		}
	}
	return true
}

func (c Config) resolveDirect(runtime RuntimeConfig) (RuntimeConfig, error) {
	if c.UpstreamHost != "" || c.UpstreamPort != 0 || c.UpstreamProtocol != "" || c.UpstreamAuth != "" ||
		c.UpstreamTLSServerName != "" || c.UpstreamTLSCAFile != "" || c.UsernameFile != "" || c.PasswordFile != "" ||
		c.CredentialLeaseFile != "" || c.CredentialLeaseID != "" {
		return RuntimeConfig{}, errors.New("DIRECT must not contain upstream or credential fields")
	}
	resolver, err := netip.ParseAddr(c.ApprovedResolverIP)
	if err != nil || !resolver.Is4() || !resolver.IsGlobalUnicast() || resolver.IsLoopback() || resolver.IsLinkLocalUnicast() ||
		!resolverIDPattern.MatchString(c.ApprovedResolverID) {
		return RuntimeConfig{}, errors.New("DIRECT requires a named numeric IPv4 resolver")
	}
	if !filepath.IsAbs(c.HostIPv4File) || len(c.HostIPv4Snapshot) == 0 || len(c.HostIPv4Snapshot) > 64 {
		return RuntimeConfig{}, errDirectHostEvidence
	}
	runtime.ApprovedResolverID, runtime.ApprovedResolverIP = c.ApprovedResolverID, resolver.String()
	runtime.HostIPv4File = c.HostIPv4File
	runtime.HostIPv4Snapshot = append([]string(nil), c.HostIPv4Snapshot...)
	seen := make(map[string]bool)
	for _, value := range runtime.HostIPv4Snapshot {
		ip, err := netip.ParseAddr(value)
		if err != nil || !directPublicIPv4(ip) || ip.String() != value || seen[value] {
			return RuntimeConfig{}, errDirectHostEvidence
		}
		seen[value] = true
	}
	sort.Strings(runtime.HostIPv4Snapshot)
	if !(&Server{cfg: runtime}).directHostEvidenceValid() {
		return RuntimeConfig{}, errDirectHostEvidence
	}
	return runtime, nil
}

// A procfs bind stays live across address changes. The controller verifies the
// mount source is exactly the host's /proc/1/net/fib_trie and read-only. A plain
// snapshot file, the container's own namespace, and NAT-only hosts are not an
// accepted substitute for this version's routed-host contract.
func hostPublicIPv4(path string) ([]string, error) {
	var fs syscall.Statfs_t
	if syscall.Statfs(path, &fs) != nil || fs.Type != 0x9fa0 { // PROC_SUPER_MAGIC
		return nil, errDirectHostEvidence
	}
	raw, err := readRegularFile("", path, 1024*1024, false)
	if err != nil {
		return nil, errDirectHostEvidence
	}
	return parseHostPublicIPv4(string(raw))
}

func parseHostPublicIPv4(raw string) ([]string, error) {
	seen := make(map[string]bool)
	var previous netip.Addr
	loopback, table := false, false
	for _, line := range strings.Split(raw, "\n") {
		line = strings.TrimSpace(line)
		if line == "Main:" || line == "Local:" {
			table = true
			previous = netip.Addr{}
		}
		if strings.HasPrefix(line, "|-- ") {
			address, err := netip.ParseAddr(strings.TrimSpace(strings.TrimPrefix(line, "|-- ")))
			if err != nil || !address.Is4() {
				return nil, errDirectHostEvidence
			}
			previous = address
		} else if line == "/32 host LOCAL" {
			if !table || !previous.IsValid() {
				return nil, errDirectHostEvidence
			}
			if previous.IsLoopback() {
				loopback = true
			}
			if directPublicIPv4(previous) {
				seen[previous.String()] = true
			}
		}
	}
	if !loopback || len(seen) == 0 || len(seen) > 64 {
		return nil, errDirectHostEvidence
	}
	result := make([]string, 0, len(seen))
	for address := range seen {
		result = append(result, address)
	}
	sort.Strings(result)
	return result, nil
}

func (s *Server) directHostEvidenceValid() bool {
	actual, err := hostPublicIPv4(s.cfg.HostIPv4File)
	return err == nil && reflect.DeepEqual(actual, s.cfg.HostIPv4Snapshot)
}

func (s *Server) watchDirectHostEvidence(ctx context.Context, cancel context.CancelFunc, done chan<- struct{}) {
	defer close(done)
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if !s.directHostEvidenceValid() {
				s.logger.Warn("DIRECT host address evidence ended", "error_code", "DIRECT_HOST_EVIDENCE_UNAVAILABLE")
				cancel()
				return
			}
		}
	}
}

func (s *Server) directAddressAllowed(address netip.Addr) bool {
	if !directPublicIPv4(address) {
		return false
	}
	for _, host := range s.cfg.HostIPv4Snapshot {
		if address.String() == host {
			return false
		}
	}
	return true
}

func (s *Server) dialDirect(parent context.Context, req request) (net.Conn, error) {
	authority, err := req.authority()
	if err != nil || req.atyp == 4 || req.port == 53 || req.port == 853 {
		return nil, errDirectDenied
	}
	if !s.directHostEvidenceValid() {
		return nil, errDirectHostEvidence
	}
	host, _, _ := net.SplitHostPort(authority)
	ctx, cancel := context.WithTimeout(parent, s.cfg.DialTimeout)
	defer cancel()
	var addresses []netip.Addr
	if numeric, parseErr := netip.ParseAddr(host); parseErr == nil {
		addresses = []netip.Addr{numeric}
	} else {
		addresses, err = lookupDirectIPv4(ctx, net.JoinHostPort(s.cfg.ApprovedResolverIP, "53"), host)
		if err != nil {
			return nil, errDirectDNS
		}
	}
	if len(addresses) == 0 {
		return nil, errDirectDNS
	}
	return s.dialDirectAddresses(ctx, req.port, addresses)
}

func (s *Server) dialDirectAddresses(ctx context.Context, port uint16, addresses []netip.Addr) (net.Conn, error) {
	if len(addresses) == 0 || port == 0 || port == 53 || port == 853 {
		return nil, errDirectDenied
	}
	// Validate the complete result before dialing any member. A mixed public /
	// protected answer is rejected, including CNAME and DNS rebinding results.
	var err error
	for _, address := range addresses {
		if !s.directAddressAllowed(address) {
			return nil, errDirectDenied
		}
	}
	for _, address := range addresses {
		if !s.directHostEvidenceValid() {
			return nil, errDirectHostEvidence
		}
		var conn net.Conn
		conn, err = s.directDial(ctx, "tcp4", net.JoinHostPort(address.String(), strconv.Itoa(int(port))))
		if err == nil {
			return conn, nil
		}
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
	}
	return nil, err
}
