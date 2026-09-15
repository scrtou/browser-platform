package proxy

import (
	"bufio"
	"bytes"
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/binary"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"math/big"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type testLog struct {
	sync.Mutex
	bytes.Buffer
}

func (b *testLog) Write(p []byte) (int, error) { b.Lock(); defer b.Unlock(); return b.Buffer.Write(p) }
func (b *testLog) text() string                { b.Lock(); defer b.Unlock(); return b.Buffer.String() }

func proxyCertificate(t *testing.T) (tls.Certificate, []byte) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	root := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "Relay QA CA"},
		NotBefore: time.Now().Add(-time.Hour), NotAfter: time.Now().Add(time.Hour), IsCA: true,
		BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature}
	rootDER, err := x509.CreateCertificate(rand.Reader, root, root, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	leafKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	leaf := &x509.Certificate{SerialNumber: big.NewInt(2), DNSNames: []string{"proxy.test"},
		NotBefore: root.NotBefore, NotAfter: root.NotAfter, KeyUsage: x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}
	leafDER, err := x509.CreateCertificate(rand.Reader, leaf, root, &leafKey.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	return tls.Certificate{Certificate: [][]byte{leafDER, rootDER}, PrivateKey: leafKey}, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: rootDER})
}

func testPeer(t *testing.T, tlsConfig *tls.Config, handler func(net.Conn)) string {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	if tlsConfig != nil {
		listener = tls.NewListener(listener, tlsConfig)
	}
	var peers sync.WaitGroup
	done := make(chan struct{})
	go func() {
		defer close(done)
		for {
			conn, err := listener.Accept()
			if err != nil {
				return
			}
			peers.Add(1)
			go func() {
				defer peers.Done()
				defer conn.Close()
				stop := context.AfterFunc(t.Context(), func() { _ = conn.Close() })
				defer stop()
				_ = conn.SetDeadline(time.Now().Add(3 * time.Second))
				handler(conn)
			}()
		}
	}()
	t.Cleanup(func() { _ = listener.Close(); <-done; peers.Wait() })
	return listener.Addr().String()
}

func testRuntime(t *testing.T, address, protocol, auth string, ca []byte) RuntimeConfig {
	t.Helper()
	dir := t.TempDir()
	host, portText, err := net.SplitHostPort(address)
	if err != nil {
		t.Fatal(err)
	}
	port, err := strconv.Atoi(portText)
	if err != nil {
		t.Fatal(err)
	}
	c := Config{ListenAddress: "127.0.0.1:1080", UpstreamHost: host, UpstreamPort: port,
		UpstreamProtocol: protocol, UpstreamAuth: auth}
	if auth != authNone {
		for name, value := range map[string]string{"username": " qa-user ", "password": " qa-password:繁體😀 "} {
			if err := os.WriteFile(filepath.Join(dir, name), []byte(value+"\n"), 0600); err != nil {
				t.Fatal(err)
			}
		}
		c.UsernameFile, c.PasswordFile = "username", "password"
	}
	if protocol == protocolHTTPS {
		c.UpstreamTLSServerName = "proxy.test"
		if ca != nil {
			if err := os.WriteFile(filepath.Join(dir, "ca.pem"), ca, 0600); err != nil {
				t.Fatal(err)
			}
			c.UpstreamTLSCAFile = "ca.pem"
		}
	}
	runtime, err := c.Resolve(dir)
	if err != nil {
		t.Fatal(err)
	}
	runtime.DialTimeout = time.Second
	runtime.IdleTimeout = 2 * time.Second
	return runtime
}

func testRelay(t *testing.T, cfg RuntimeConfig) (string, func(), *testLog) {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	output := new(testLog)
	done := make(chan error, 1)
	go func() {
		done <- NewServer(cfg, slog.New(slog.NewJSONHandler(output, nil))).ServeListener(ctx, listener)
	}()
	var once sync.Once
	stop := func() {
		once.Do(func() {
			cancel()
			if err := <-done; err != nil {
				t.Error(err)
			}
		})
	}
	t.Cleanup(stop)
	return listener.Addr().String(), stop, output
}

func domainRequest(host string, port uint16) request {
	return request{atyp: 3, addr: append([]byte{byte(len(host))}, []byte(host)...), port: port}
}

func clientConnect(address string, req request) (net.Conn, byte, error) {
	conn, err := net.DialTimeout("tcp", address, time.Second)
	if err != nil {
		return nil, 0, err
	}
	_ = conn.SetDeadline(time.Now().Add(3 * time.Second))
	if err := writeAll(conn, []byte{5, 1, 0}); err != nil {
		conn.Close()
		return nil, 0, err
	}
	greeting, err := readFixed(conn, 2)
	if err != nil || !bytes.Equal(greeting, []byte{5, 0}) {
		conn.Close()
		return nil, 0, errors.New("client greeting failed")
	}
	message := append([]byte{5, 1, 0, req.atyp}, req.addr...)
	message = binary.BigEndian.AppendUint16(message, req.port)
	if err := writeAll(conn, message); err != nil {
		conn.Close()
		return nil, 0, err
	}
	reply, err := readFixed(conn, 10)
	if err != nil {
		conn.Close()
		return nil, 0, err
	}
	return conn, reply[1], nil
}

// The test peer independently decodes the real upstream wire protocol.
func peerRequest(conn net.Conn, protocol, auth string) (string, error) {
	if protocol != protocolSOCKS5 {
		req, err := http.ReadRequest(bufio.NewReader(conn))
		if err != nil {
			return "", err
		}
		if req.Method != "CONNECT" || req.Host != req.RequestURI || req.Header.Get("Authorization") != "" {
			return "", errors.New("CONNECT authority or header mismatch")
		}
		want := ""
		if auth == authBasic {
			want = "Basic " + base64.StdEncoding.EncodeToString([]byte(" qa-user : qa-password:繁體😀 "))
		}
		if req.Header.Get("Proxy-Authorization") != want {
			return "", errors.New("Basic credential bytes differ")
		}
		return req.Host, nil
	}
	method := byte(noAuth)
	if auth == authUserPass {
		method = userPassAuth
	}
	greeting, err := readFixed(conn, 3)
	if err != nil {
		return "", err
	}
	if !bytes.Equal(greeting, []byte{5, 1, method}) {
		return "", errors.New("SOCKS authentication offer differs")
	}
	if err := writeAll(conn, []byte{5, method}); err != nil {
		return "", err
	}
	if method == userPassAuth {
		head, err := readFixed(conn, 2)
		if err != nil {
			return "", err
		}
		user, err := readFixed(conn, int(head[1]))
		if err != nil {
			return "", err
		}
		length, err := readByte(conn)
		if err != nil {
			return "", err
		}
		password, err := readFixed(conn, int(length))
		if err != nil {
			return "", err
		}
		if head[0] != 1 || string(user) != " qa-user " || string(password) != " qa-password:繁體😀 " {
			return "", errors.New("SOCKS credential bytes differ")
		}
		if err := writeAll(conn, []byte{1, 0}); err != nil {
			return "", err
		}
	}
	head, err := readFixed(conn, 4)
	if err != nil {
		return "", err
	}
	if !bytes.Equal(head[:3], []byte{5, 1, 0}) {
		return "", errors.New("SOCKS request invalid")
	}
	var host string
	switch head[3] {
	case 1, 4:
		size := 4
		if head[3] == 4 {
			size = 16
		}
		raw, err := readFixed(conn, size)
		if err != nil {
			return "", err
		}
		host = net.IP(raw).String()
	case 3:
		length, err := readByte(conn)
		if err != nil {
			return "", err
		}
		raw, err := readFixed(conn, int(length))
		if err != nil {
			return "", err
		}
		host = string(raw)
	default:
		return "", errors.New("SOCKS request address invalid")
	}
	port, err := readFixed(conn, 2)
	if err != nil {
		return "", err
	}
	return net.JoinHostPort(host, strconv.Itoa(int(binary.BigEndian.Uint16(port)))), nil
}

func peerSuccess(conn net.Conn, protocol string, payload []byte) error {
	head := []byte("HTTP/1.1 200 Connection established\r\n\r\n")
	if protocol == protocolSOCKS5 {
		head = []byte{5, 0, 0, 1, 0, 0, 0, 0, 0, 0}
	}
	return writeAll(conn, append(head, payload...))
}

func TestRelayProtocolAuthenticationMatrix(t *testing.T) {
	for _, protocol := range []string{protocolSOCKS5, protocolHTTP, protocolHTTPS} {
		auths := []string{authNone, authBasic}
		if protocol == protocolSOCKS5 {
			auths[1] = authUserPass
		}
		for _, auth := range auths {
			t.Run(protocol+"/"+auth, func(t *testing.T) {
				var tc *tls.Config
				var ca []byte
				if protocol == protocolHTTPS {
					cert, root := proxyCertificate(t)
					ca = root
					tc = &tls.Config{Certificates: []tls.Certificate{cert}, MinVersion: tls.VersionTLS12}
				}
				seen := make(chan string, 3)
				banner := bytes.Repeat([]byte("tunnel-payload"), 6000) // Exceeds the header limit and arrives in the response write.
				peer := testPeer(t, tc, func(conn net.Conn) {
					authority, err := peerRequest(conn, protocol, auth)
					if err != nil {
						t.Error(err)
						return
					}
					seen <- authority
					if err := peerSuccess(conn, protocol, banner); err != nil {
						t.Error(err)
						return
					}
					value, err := readFixed(conn, 4)
					if err != nil {
						t.Error(err)
						return
					}
					if string(value) != "ping" {
						t.Error("tunnel request changed")
						return
					}
					if err := writeAll(conn, []byte("pong")); err != nil {
						t.Error(err)
					}
				})
				relay, _, logs := testRelay(t, testRuntime(t, peer, protocol, auth, ca))
				for _, req := range []request{domainRequest("xn--bcher-kva.test.", 80), {atyp: 1, addr: []byte{192, 0, 2, 25}, port: 443}, {atyp: 4, addr: net.ParseIP("2001:db8::25").To16(), port: 8080}} {
					conn, reply, err := clientConnect(relay, req)
					if err != nil {
						t.Fatal(err)
					}
					if reply != replySucceeded {
						conn.Close()
						t.Fatalf("upstream handshake failed: %d", reply)
					}
					got, err := readFixed(conn, len(banner))
					if err != nil || !bytes.Equal(got, banner) {
						conn.Close()
						t.Fatal("prefetched/large tunnel payload lost")
					}
					if err := writeAll(conn, []byte("ping")); err != nil {
						t.Fatal(err)
					}
					got, err = readFixed(conn, 4)
					conn.Close()
					if err != nil || string(got) != "pong" {
						t.Fatal("tunnel response changed")
					}
					want, _ := req.authority()
					if <-seen != want {
						t.Fatal("target authority changed or resolved locally")
					}
				}
				if logs.text() != "" {
					t.Fatal("successful tunnels unexpectedly logged")
				}
			})
		}
	}
}

func TestHTTPFailuresAreBoundedAndRedacted(t *testing.T) {
	for _, tc := range []struct{ name, response, code string }{
		{"authentication", "HTTP/1.1 407 Proxy authentication required\r\nProxy-Authenticate: Basic realm=private-test-secret\r\n\r\n", "UPSTREAM_AUTH_FAILED"},
		{"redirect", "HTTP/1.1 302 Redirect\r\nLocation: http://private-test-secret/\r\n\r\n", "UPSTREAM_PROTOCOL_INVALID"},
		{"malformed", "private-test-secret\r\n\r\n", "UPSTREAM_PROTOCOL_INVALID"},
		{"http2", "HTTP/2.0 200 OK\r\n\r\n", "UPSTREAM_PROTOCOL_INVALID"},
		{"oversize", "HTTP/1.1 200 OK\r\nX-Private: " + strings.Repeat("s", maxConnectHeaders) + "\r\n\r\n", "UPSTREAM_PROTOCOL_INVALID"},
		{"incomplete", "HTTP/1.1 200 OK\r\nX-Private: private-test-secret", "UPSTREAM_PROTOCOL_INVALID"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			peer := testPeer(t, nil, func(conn net.Conn) {
				if _, err := peerRequest(conn, protocolHTTP, authBasic); err != nil {
					t.Error(err)
					return
				}
				_ = writeAll(conn, []byte(tc.response))
			})
			relay, stop, logs := testRelay(t, testRuntime(t, peer, protocolHTTP, authBasic, nil))
			conn, reply, err := clientConnect(relay, domainRequest("target.test", 443))
			if err != nil {
				t.Fatal(err)
			}
			conn.Close()
			if reply == replySucceeded {
				t.Fatal("invalid response created a tunnel")
			}
			stop()
			text := logs.text()
			if !strings.Contains(text, tc.code) {
				t.Fatal("missing stable error code")
			}
			for _, secret := range []string{"private-test-secret", "qa-user", "qa-password", "target.test", "Proxy-Authenticate"} {
				if strings.Contains(text, secret) {
					t.Fatal("upstream data leaked into logs")
				}
			}
		})
	}
}

func TestHTTPSValidatesChainNameAndMinimumVersion(t *testing.T) {
	for _, mode := range []string{"valid", "untrusted", "wrong_name", "expired", "tls11"} {
		t.Run(mode, func(t *testing.T) {
			cert, ca := proxyCertificate(t)
			tc := &tls.Config{Certificates: []tls.Certificate{cert}, MinVersion: tls.VersionTLS12}
			if mode == "tls11" {
				tc.MinVersion = tls.VersionTLS10
				tc.MaxVersion = tls.VersionTLS11
			}
			var authenticated atomic.Int32
			peer := testPeer(t, tc, func(conn net.Conn) {
				if _, err := peerRequest(conn, protocolHTTPS, authBasic); err != nil {
					return
				}
				authenticated.Add(1)
				_ = peerSuccess(conn, protocolHTTPS, nil)
			})
			if mode == "untrusted" {
				ca = nil
			}
			cfg := testRuntime(t, peer, protocolHTTPS, authBasic, ca)
			if mode == "wrong_name" {
				cfg.UpstreamTLS.ServerName = "other.test"
			}
			if mode == "expired" {
				cfg.UpstreamTLS.Time = func() time.Time { return time.Now().Add(24 * time.Hour) }
			}
			conn, err := NewServer(cfg, nil).dialUpstream(t.Context(), domainRequest("target.test", 443))
			if mode == "valid" {
				if err != nil {
					t.Fatal(err)
				}
				conn.Close()
				if authenticated.Load() != 1 {
					t.Fatal("valid TLS did not authenticate")
				}
			} else {
				if !errors.Is(err, errUpstreamTLS) {
					if conn != nil {
						conn.Close()
					}
					t.Fatalf("invalid TLS result: %v", err)
				}
				if authenticated.Load() != 0 {
					t.Fatal("credentials sent before TLS verification")
				}
			}
		})
	}
}

func TestInvalidTargetsNeverReachUpstream(t *testing.T) {
	var calls atomic.Int32
	peer := testPeer(t, nil, func(conn net.Conn) { calls.Add(1) })
	for _, protocol := range []string{protocolSOCKS5, protocolHTTP} {
		relay, _, _ := testRelay(t, testRuntime(t, peer, protocol, authNone, nil))
		for _, req := range []request{domainRequest("a\r\nHost: injected", 443), domainRequest("user@target", 443), domainRequest("a b", 443), domainRequest("a\x00b", 443), domainRequest("a..b", 443), domainRequest("a/b", 443), domainRequest("target.test", 0)} {
			conn, reply, err := clientConnect(relay, req)
			if err != nil {
				t.Fatal(err)
			}
			conn.Close()
			if reply != replyAddress {
				t.Fatal("invalid target was not rejected")
			}
		}
	}
	if calls.Load() != 0 {
		t.Fatal("invalid target reached upstream")
	}
}

func TestSOCKSAuthCannotDowngradeOrAcceptWrongVersion(t *testing.T) {
	for _, mode := range []string{"downgrade", "wrong_auth_version", "wrong_credentials", "reserved_reply"} {
		t.Run(mode, func(t *testing.T) {
			peer := testPeer(t, nil, func(conn net.Conn) {
				if mode == "reserved_reply" {
					if _, err := peerRequest(conn, protocolSOCKS5, authUserPass); err != nil {
						t.Error(err)
						return
					}
					_ = writeAll(conn, []byte{5, 0, 1, 1, 0, 0, 0, 0, 0, 0})
					return
				}
				if _, err := readFixed(conn, 3); err != nil {
					t.Error(err)
					return
				}
				if mode == "downgrade" {
					_ = writeAll(conn, []byte{5, 0})
					return
				}
				_ = writeAll(conn, []byte{5, 2})
				head, err := readFixed(conn, 2)
				if err != nil {
					return
				}
				_, _ = readFixed(conn, int(head[1]))
				length, err := readByte(conn)
				if err != nil {
					return
				}
				_, _ = readFixed(conn, int(length))
				if mode == "wrong_auth_version" {
					_ = writeAll(conn, []byte{5, 0})
				} else {
					_ = writeAll(conn, []byte{1, 1})
				}
			})
			cfg := testRuntime(t, peer, protocolSOCKS5, authUserPass, nil)
			conn, err := NewServer(cfg, nil).dialUpstream(t.Context(), domainRequest("target.test", 443))
			if conn != nil {
				conn.Close()
			}
			if err == nil {
				t.Fatal("invalid SOCKS negotiation accepted")
			}
			if mode != "reserved_reply" && !errors.Is(err, errUpstreamAuth) {
				t.Fatal("missing authentication error")
			}
		})
	}
}

func TestHandshakeDeadlineAcrossPhases(t *testing.T) {
	for _, phase := range []string{"tls", "http_headers", "socks_auth", "socks_connect"} {
		t.Run(phase, func(t *testing.T) {
			peer := testPeer(t, nil, func(conn net.Conn) {
				switch phase {
				case "http_headers":
					if _, err := peerRequest(conn, protocolHTTP, authNone); err != nil {
						return
					}
					_ = writeAll(conn, []byte("HTTP/1.1 200 OK\r\n"))
				case "socks_auth":
					if _, err := readFixed(conn, 3); err != nil {
						return
					}
					_ = writeAll(conn, []byte{5, 2})
				case "socks_connect":
					if _, err := peerRequest(conn, protocolSOCKS5, authUserPass); err != nil {
						return
					}
				}
				_, _ = io.Copy(io.Discard, conn)
			})
			protocol, auth := protocolSOCKS5, authUserPass
			if phase == "http_headers" {
				protocol, auth = protocolHTTP, authNone
			}
			if phase == "tls" {
				protocol, auth = protocolHTTPS, authNone
			}
			cfg := testRuntime(t, peer, protocol, auth, nil)
			cfg.DialTimeout = 120 * time.Millisecond
			start := time.Now()
			conn, err := NewServer(cfg, nil).dialUpstream(t.Context(), domainRequest("target.test", 443))
			if conn != nil {
				conn.Close()
			}
			if err == nil {
				t.Fatal("silent handshake succeeded")
			}
			if time.Since(start) > time.Second {
				t.Fatal("handshake exceeded budget")
			}
			if safeErrorCode(err) != "UPSTREAM_TIMEOUT" {
				t.Fatalf("timeout classified as %s", safeErrorCode(err))
			}
		})
	}
}

func TestConcurrentTunnelsAndCancellation(t *testing.T) {
	for _, protocol := range []string{protocolSOCKS5, protocolHTTP, protocolHTTPS} {
		t.Run(protocol, func(t *testing.T) {
			var tc *tls.Config
			var ca []byte
			if protocol == protocolHTTPS {
				cert, root := proxyCertificate(t)
				ca = root
				tc = &tls.Config{Certificates: []tls.Certificate{cert}, MinVersion: tls.VersionTLS12}
			}
			peer := testPeer(t, tc, func(conn net.Conn) {
				if _, err := peerRequest(conn, protocol, authNone); err != nil {
					return
				}
				if err := peerSuccess(conn, protocol, nil); err != nil {
					return
				}
				_, _ = io.Copy(conn, conn)
			})
			relay, stop, _ := testRelay(t, testRuntime(t, peer, protocol, authNone, ca))
			var wg sync.WaitGroup
			clients := make(chan net.Conn, 20)
			for i := 0; i < 20; i++ {
				wg.Add(1)
				go func(i int) {
					defer wg.Done()
					conn, code, err := clientConnect(relay, domainRequest(fmt.Sprintf("target-%d.test", i), 443))
					if err != nil {
						t.Error(err)
						return
					}
					if code != 0 {
						conn.Close()
						t.Error("concurrent tunnel failed")
						return
					}
					if err := writeAll(conn, []byte("ping")); err != nil {
						conn.Close()
						t.Error(err)
						return
					}
					got, err := readFixed(conn, 4)
					if err != nil || string(got) != "ping" {
						conn.Close()
						t.Error("concurrent payload failed")
						return
					}
					clients <- conn
				}(i)
			}
			wg.Wait()
			close(clients)
			start := time.Now()
			stop()
			if time.Since(start) > time.Second {
				t.Fatal("Relay cancellation did not drain connections")
			}
			count := 0
			for conn := range clients {
				count++
				_, err := readFixed(conn, 1)
				conn.Close()
				if err == nil {
					t.Error("cancelled tunnel still open")
				}
			}
			if count != 20 {
				t.Fatalf("only %d tunnels succeeded", count)
			}
		})
	}
}

func TestUnavailableUpstreamsNeverDialTarget(t *testing.T) {
	target, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer target.Close()
	_, portText, _ := net.SplitHostPort(target.Addr().String())
	port, _ := strconv.Atoi(portText)
	dead, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	address := dead.Addr().String()
	dead.Close()
	for _, protocol := range []string{protocolSOCKS5, protocolHTTP, protocolHTTPS} {
		cfg := testRuntime(t, address, protocol, authNone, nil)
		conn, err := NewServer(cfg, nil).dialUpstream(t.Context(), request{atyp: 1, addr: []byte{127, 0, 0, 1}, port: uint16(port)})
		if conn != nil {
			conn.Close()
		}
		if err == nil {
			t.Fatal("offline upstream succeeded")
		}
	}
	_ = target.(*net.TCPListener).SetDeadline(time.Now().Add(50 * time.Millisecond))
	if conn, err := target.Accept(); err == nil {
		conn.Close()
		t.Fatal("Relay connected directly to target")
	}
}
