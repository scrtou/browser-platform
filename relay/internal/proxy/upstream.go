package proxy

import (
	"context"
	"crypto/tls"
	"errors"
	"net"
	"strconv"
	"strings"
	"time"
)

const (
	protocolSOCKS5 = "socks5"
	protocolHTTP   = "http"
	protocolHTTPS  = "https"
	authNone       = "none"
	authUserPass   = "username_password"
	authBasic      = "basic"
)

func supportedAuth(protocol, auth string) bool {
	switch protocol {
	case protocolSOCKS5:
		return auth == authNone || auth == authUserPass
	case protocolHTTP, protocolHTTPS:
		return auth == authNone || auth == authBasic
	default:
		return false
	}
}

func validHost(host string) bool {
	return net.ParseIP(host) != nil || validDNSName(host)
}

// Worker domains are already ASCII/IDNA. No local DNS lookup is performed.
func validDNSName(host string) bool {
	if len(host) == 0 || len(host) > 253 {
		return false
	}
	for _, label := range strings.Split(strings.TrimSuffix(host, "."), ".") {
		if len(label) == 0 || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return false
		}
		for _, c := range []byte(label) {
			if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '-') {
				return false
			}
		}
	}
	return true
}

func (r request) authority() (string, error) {
	var host string
	switch {
	case r.atyp == 1 && len(r.addr) == net.IPv4len:
		host = net.IP(r.addr).String()
	case r.atyp == 4 && len(r.addr) == net.IPv6len:
		host = net.IP(r.addr).String()
	case r.atyp == 3 && len(r.addr) > 1 && int(r.addr[0]) == len(r.addr)-1:
		host = string(r.addr[1:])
		if !validDNSName(host) {
			return "", errors.New("invalid target domain")
		}
	default:
		return "", errors.New("invalid target address")
	}
	if r.port == 0 {
		return "", errors.New("invalid target port")
	}
	return net.JoinHostPort(host, strconv.Itoa(int(r.port))), nil
}

func (s *Server) dialUpstream(parent context.Context, req request) (net.Conn, error) {
	if s.cfg.Mode == "direct" {
		return s.dialDirect(parent, req)
	}
	authority, err := req.authority()
	if err != nil {
		return nil, err
	}
	if !supportedAuth(s.cfg.UpstreamProtocol, s.cfg.UpstreamAuth) {
		return nil, errUnsupportedAuth
	}
	ctx, cancel := context.WithTimeout(parent, s.cfg.DialTimeout)
	defer cancel()
	conn, err := (&net.Dialer{}).DialContext(ctx, "tcp", s.cfg.UpstreamAddress)
	if err != nil {
		return nil, err
	}
	raw := conn
	success := false
	stopClose := context.AfterFunc(ctx, func() { _ = raw.Close() })
	defer func() {
		stopClose()
		if !success {
			_ = raw.Close()
		}
	}()
	deadline, _ := ctx.Deadline()
	if err := conn.SetDeadline(deadline); err != nil {
		return nil, err
	}
	if s.cfg.UpstreamProtocol == protocolHTTPS {
		if s.cfg.UpstreamTLS == nil || s.cfg.UpstreamTLS.InsecureSkipVerify ||
			s.cfg.UpstreamTLS.ServerName == "" || s.cfg.UpstreamTLS.MinVersion < tls.VersionTLS12 {
			return nil, errUpstreamTLS
		}
		secure := tls.Client(conn, s.cfg.UpstreamTLS.Clone())
		if err := secure.HandshakeContext(ctx); err != nil {
			if ctx.Err() != nil {
				return nil, ctx.Err()
			}
			var ne net.Error
			if errors.As(err, &ne) && ne.Timeout() {
				return nil, err
			}
			return nil, errUpstreamTLS
		}
		conn = secure
	}
	if s.cfg.UpstreamProtocol == protocolSOCKS5 {
		err = s.connectSOCKS5(conn, req)
	} else {
		conn, err = s.connectHTTP(conn, authority)
	}
	if err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, err
	}
	if ctx.Err() != nil {
		return nil, ctx.Err()
	}
	if err := conn.SetDeadline(time.Time{}); err != nil {
		return nil, err
	}
	success = true
	return conn, nil
}
