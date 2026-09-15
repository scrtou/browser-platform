package proxy

import (
	"bufio"
	"encoding/base64"
	"errors"
	"fmt"
	"net"
	"net/http"
)

const maxConnectHeaders = 32 * 1024

var errHeadersTooLarge = errors.New("upstream response headers exceed limit")

// Limit only the handshake, then keep using the same reader for tunnel data.
// ReadResponse may prefetch bytes after the empty line in a CONNECT response.
type headerReader struct {
	conn      net.Conn
	remaining int
}

func (r *headerReader) Read(p []byte) (int, error) {
	if r.remaining == 0 {
		return 0, errHeadersTooLarge
	}
	if r.remaining > 0 && len(p) > r.remaining {
		p = p[:r.remaining]
	}
	n, err := r.conn.Read(p)
	if r.remaining > 0 {
		r.remaining -= n
	}
	return n, err
}

type bufferedConn struct {
	net.Conn
	reader *bufio.Reader
}

func (c *bufferedConn) Read(p []byte) (int, error) { return c.reader.Read(p) }

func (s *Server) connectHTTP(conn net.Conn, authority string) (net.Conn, error) {
	message := fmt.Sprintf("CONNECT %s HTTP/1.1\r\nHost: %s\r\n", authority, authority)
	if s.cfg.UpstreamAuth == authBasic {
		credential := base64.StdEncoding.EncodeToString([]byte(s.cfg.Username + ":" + s.cfg.Password))
		message += "Proxy-Authorization: Basic " + credential + "\r\n"
	}
	if err := writeAll(conn, []byte(message+"\r\n")); err != nil {
		return nil, err
	}
	limited := &headerReader{conn: conn, remaining: maxConnectHeaders}
	reader := bufio.NewReader(limited)
	response, err := http.ReadResponse(reader, &http.Request{Method: http.MethodConnect})
	if err != nil {
		var ne net.Error
		if errors.As(err, &ne) && ne.Timeout() {
			return nil, err
		}
		return nil, errUpstreamProtocol
	}
	if response.StatusCode == http.StatusProxyAuthRequired {
		return nil, errUpstreamAuth
	}
	if response.StatusCode != http.StatusOK || response.ProtoMajor != 1 || response.ProtoMinor > 1 {
		return nil, errUpstreamProtocol
	}
	// RFC 9110 CONNECT semantics: after a successful response, framing headers
	// do not describe an HTTP response body. All remaining bytes are the tunnel.
	limited.remaining = -1
	return &bufferedConn{Conn: conn, reader: reader}, nil
}
