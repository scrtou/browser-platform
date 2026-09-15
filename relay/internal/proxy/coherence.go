package proxy

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

var errCoherenceGate = errors.New("invalid coherence gate configuration")

type coherenceOptions struct {
	file, generation, domain string
	port                     uint16
}

func (c Config) resolveCoherenceGate(baseDir string) (coherenceOptions, error) {
	if c.CoherenceGateFile == "" && c.CoherenceGeneration == "" && c.CoherenceProbeDomain == "" && c.CoherenceProbePort == 0 {
		return coherenceOptions{}, nil
	}
	domain := c.CoherenceProbeDomain
	if c.CoherenceGateFile == "" || !canonicalHex(c.CoherenceGeneration, 64) ||
		!validHost(domain) || domain != strings.ToLower(domain) || !strings.Contains(domain, ".") ||
		strings.HasSuffix(domain, ".") || net.ParseIP(domain) != nil || c.CoherenceProbePort < 1 || c.CoherenceProbePort > 65535 {
		return coherenceOptions{}, errCoherenceGate
	}
	path := c.CoherenceGateFile
	if !filepath.IsAbs(path) {
		path = filepath.Join(baseDir, path)
	}
	return coherenceOptions{path, c.CoherenceGeneration, domain, uint16(c.CoherenceProbePort)}, nil
}

func (c coherenceOptions) apply(r RuntimeConfig) RuntimeConfig {
	r.CoherenceGateFile, r.CoherenceGeneration = c.file, c.generation
	r.CoherenceProbeDomain, r.CoherenceProbePort = c.domain, c.port
	return r
}

func canonicalHex(value string, size int) bool {
	if len(value) != size {
		return false
	}
	decoded, err := hex.DecodeString(value)
	return err == nil && hex.EncodeToString(decoded) == value
}

type gateRecord struct {
	Version    int    `json:"version"`
	Generation string `json:"generation"`
	Sequence   uint64 `json:"sequence"`
	State      string `json:"state"`
	IssuedMS   int64  `json:"issued_ms"`
	ExpiresMS  int64  `json:"expires_ms"`
}

// A separate directory bind lets every lookup observe atomic replacement.
// A missing/invalid/expired file permits only the fixed observation service.
func readGate(path, generation string) (gateRecord, [32]byte, bool) {
	var record gateRecord
	raw, err := readRegularFile("", path, 4096, true)
	if err != nil {
		return record, [32]byte{}, false
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	first, err := decoder.Token()
	if err != nil || first != json.Delim('{') {
		return record, [32]byte{}, false
	}
	keys := make(map[string]bool)
	for decoder.More() {
		token, err := decoder.Token()
		if err != nil {
			return record, [32]byte{}, false
		}
		key, ok := token.(string)
		if !ok || keys[key] || key != strings.ToLower(key) {
			return record, [32]byte{}, false
		}
		keys[key] = true
		var value json.RawMessage
		if decoder.Decode(&value) != nil || bytes.Equal(value, []byte("null")) {
			return record, [32]byte{}, false
		}
	}
	decoder = json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&record) != nil {
		return record, [32]byte{}, false
	}
	var extra any
	if !errors.Is(decoder.Decode(&extra), io.EOF) || len(keys) != 6 || record.Version != 1 ||
		record.Generation != generation || record.Sequence == 0 ||
		(record.State != "open" && record.State != "probe" && record.State != "blocked") ||
		record.IssuedMS <= 0 || record.ExpiresMS <= record.IssuedMS || record.ExpiresMS-record.IssuedMS > 60000 {
		return record, [32]byte{}, false
	}
	return record, sha256.Sum256(raw), true
}

type coherenceGate struct {
	mu          sync.Mutex
	sequence    uint64
	floor       uint64
	hash        [32]byte
	deadline    time.Time
	allowed     bool
	connections map[net.Conn]context.CancelFunc
}

func (s *Server) startCoherenceGate(ctx context.Context) func() {
	if s.cfg.CoherenceGateFile == "" {
		return func() {}
	}
	record, _, valid := readGate(s.cfg.CoherenceGateFile, s.cfg.CoherenceGeneration)
	s.gate.mu.Lock()
	s.gate.connections = make(map[net.Conn]context.CancelFunc)
	// An open file from before this Relay start cannot authorize a new listener.
	if valid {
		s.gate.floor, s.gate.sequence = record.Sequence, record.Sequence
	}
	s.gate.mu.Unlock()
	done := make(chan struct{})
	ctx, cancel := context.WithCancel(ctx)
	go func() {
		defer close(done)
		ticker := time.NewTicker(100 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				s.refreshCoherenceGate()
			}
		}
	}()
	return func() { cancel(); <-done }
}

func (s *Server) refreshCoherenceGate() {
	record, hash, valid := readGate(s.cfg.CoherenceGateFile, s.cfg.CoherenceGeneration)
	now := time.Now()
	s.gate.mu.Lock()
	g := &s.gate
	allowed := false
	if valid && record.Sequence > g.floor && record.Sequence >= g.sequence {
		if record.Sequence > g.sequence {
			g.sequence, g.hash = record.Sequence, hash
			// The monotonic component caps a grant even if wall time moves back.
			g.deadline = now.Add(time.Duration(record.ExpiresMS-now.UnixMilli()) * time.Millisecond)
		}
		allowed = hash == g.hash && record.State == "open" && now.UnixMilli() >= record.IssuedMS &&
			now.UnixMilli() < record.ExpiresMS && now.Before(g.deadline)
	}
	if !allowed {
		// Restoring a deleted/corrupt/expired grant is not a renewal.
		g.floor = g.sequence
	}
	g.allowed = allowed
	var cancel []context.CancelFunc
	if !allowed {
		for _, close := range g.connections {
			cancel = append(cancel, close)
		}
	}
	s.gate.mu.Unlock()
	for _, close := range cancel {
		close()
	}
}

func (s *Server) coherenceProbe(req request) bool {
	if req.atyp != 3 || req.port != s.cfg.CoherenceProbePort {
		return false
	}
	host := string(req.addr[1:])
	domain := s.cfg.CoherenceProbeDomain
	if host == domain {
		return true
	}
	nonce, suffix, ok := strings.Cut(host, ".")
	return ok && suffix == domain && canonicalHex(nonce, 32)
}

// Register before dialing so a closing gate also cancels handshakes in flight.
func (s *Server) authorizeCoherence(ctx context.Context, req request, client net.Conn) (context.Context, func(), bool) {
	if s.cfg.CoherenceGateFile == "" || s.coherenceProbe(req) {
		return ctx, func() {}, true
	}
	s.refreshCoherenceGate()
	s.gate.mu.Lock()
	if !s.gate.allowed || !time.Now().Before(s.gate.deadline) {
		s.gate.mu.Unlock()
		return ctx, func() {}, false
	}
	ctx, cancel := context.WithCancel(ctx)
	s.gate.connections[client] = cancel
	s.gate.mu.Unlock()
	return ctx, func() {
		cancel()
		s.gate.mu.Lock()
		delete(s.gate.connections, client)
		s.gate.mu.Unlock()
	}, true
}
