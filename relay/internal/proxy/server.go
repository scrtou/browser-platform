package proxy

import (
	"context"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"time"
)

const (
	version5       = 0x05
	noAuth         = 0x00
	userPassAuth   = 0x02
	commandConnect = 0x01
	replySucceeded = 0x00
	replyGeneral   = 0x01
	replyDenied    = 0x02
	replyNetwork   = 0x03
	replyHost      = 0x04
	replyCommand   = 0x07
	replyAddress   = 0x08
)

type Server struct {
	cfg    RuntimeConfig
	logger *slog.Logger
}

func NewServer(cfg RuntimeConfig, logger *slog.Logger) *Server {
	if logger == nil {
		logger = slog.Default()
	}
	return &Server{cfg: cfg, logger: logger}
}

func (s *Server) Serve(ctx context.Context) error {
	listener, err := net.Listen("tcp", s.cfg.ListenAddress)
	if err != nil {
		return fmt.Errorf("listen relay: %w", err)
	}
	return s.ServeListener(ctx, listener)
}

func (s *Server) ServeListener(ctx context.Context, listener net.Listener) error {
	defer listener.Close()
	go func() {
		<-ctx.Done()
		_ = listener.Close()
	}()
	for {
		conn, err := listener.Accept()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			if errors.Is(err, net.ErrClosed) {
				return nil
			}
			s.logger.Error("relay accept failed", "error_code", "ACCEPT_FAILED")
			continue
		}
		if !s.allowed(conn.RemoteAddr()) {
			s.logger.Warn("relay client denied", "error_code", "CLIENT_NOT_ALLOWED")
			_ = conn.Close()
			continue
		}
		go s.handle(conn)
	}
}

func (s *Server) allowed(address net.Addr) bool {
	if len(s.cfg.AllowedClients) == 0 {
		return true
	}
	tcp, ok := address.(*net.TCPAddr)
	if !ok {
		return false
	}
	for _, network := range s.cfg.AllowedClients {
		if network.Contains(tcp.IP) {
			return true
		}
	}
	return false
}

func (s *Server) handle(client net.Conn) {
	defer client.Close()
	_ = client.SetDeadline(time.Now().Add(s.cfg.DialTimeout))
	request, err := readRequest(client)
	if err != nil {
		return
	}
	upstream, err := s.dialUpstream(request)
	if err != nil {
		_ = writeReply(client, replyGeneral)
		s.logger.Warn("upstream connect failed", "error_code", safeErrorCode(err))
		return
	}
	defer upstream.Close()
	if err := writeReply(client, replySucceeded); err != nil {
		return
	}
	_ = client.SetDeadline(time.Time{})
	_ = upstream.SetDeadline(time.Time{})
	copyBidirectional(client, upstream, s.cfg.IdleTimeout)
}

type request struct {
	atyp byte
	addr []byte
	port uint16
}

func readRequest(conn net.Conn) (request, error) {
	version, err := readByte(conn)
	if err != nil || version != version5 {
		return request{}, errors.New("invalid SOCKS version")
	}
	nmethods, err := readByte(conn)
	if err != nil {
		return request{}, err
	}
	methods := make([]byte, nmethods)
	if _, err := io.ReadFull(conn, methods); err != nil {
		return request{}, err
	}
	selected := byte(0xff)
	for _, method := range methods {
		if method == noAuth {
			selected = noAuth
			break
		}
	}
	if _, err := conn.Write([]byte{version5, selected}); err != nil {
		return request{}, err
	}
	if selected == 0xff {
		return request{}, errors.New("client authentication unsupported")
	}
	header := make([]byte, 4)
	if _, err := io.ReadFull(conn, header); err != nil {
		return request{}, err
	}
	if header[0] != version5 || header[1] != commandConnect || header[2] != 0 {
		_ = writeReply(conn, replyCommand)
		return request{}, errors.New("SOCKS command unsupported")
	}
	var addr []byte
	switch header[3] {
	case 1:
		addr = make([]byte, 4)
		if _, err := io.ReadFull(conn, addr); err != nil {
			return request{}, err
		}
	case 3:
		length, err := readByte(conn)
		if err != nil || length == 0 {
			_ = writeReply(conn, replyAddress)
			return request{}, errors.New("invalid domain")
		}
		domain := make([]byte, int(length))
		if _, err := io.ReadFull(conn, domain); err != nil {
			return request{}, err
		}
		addr = append([]byte{length}, domain...)
	case 4:
		addr = make([]byte, 16)
		if _, err := io.ReadFull(conn, addr); err != nil {
			return request{}, err
		}
	default:
		_ = writeReply(conn, replyAddress)
		return request{}, errors.New("address type unsupported")
	}
	portBytes := make([]byte, 2)
	if _, err := io.ReadFull(conn, portBytes); err != nil {
		return request{}, err
	}
	return request{atyp: header[3], addr: addr, port: binary.BigEndian.Uint16(portBytes)}, nil
}

func (s *Server) dialUpstream(req request) (net.Conn, error) {
	dialer := net.Dialer{Timeout: s.cfg.DialTimeout}
	conn, err := dialer.Dial("tcp", s.cfg.UpstreamAddress)
	if err != nil {
		return nil, err
	}
	ok := false
	defer func() {
		if !ok {
			_ = conn.Close()
		}
	}()
	methods := []byte{noAuth}
	if s.cfg.Username != "" {
		methods = []byte{userPassAuth}
	}
	greeting := append([]byte{version5, byte(len(methods))}, methods...)
	if err := writeAll(conn, greeting); err != nil {
		return nil, err
	}
	selected, err := readFixed(conn, 2)
	if err != nil || selected[0] != version5 {
		return nil, errors.New("upstream greeting invalid")
	}
	if s.cfg.Username != "" && selected[1] == userPassAuth {
		if err := writeUserPass(conn, s.cfg.Username, s.cfg.Password); err != nil {
			return nil, err
		}
	} else if s.cfg.Username == "" && selected[1] == noAuth {
		// continue
	} else {
		return nil, errors.New("upstream authentication method rejected")
	}
	message := []byte{version5, commandConnect, 0, req.atyp}
	message = append(message, req.addr...)
	var port [2]byte
	binary.BigEndian.PutUint16(port[:], req.port)
	message = append(message, port[:]...)
	if err := writeAll(conn, message); err != nil {
		return nil, err
	}
	reply, err := readReply(conn)
	if err != nil {
		return nil, err
	}
	if reply[1] != replySucceeded {
		return nil, fmt.Errorf("upstream SOCKS reply %d", reply[1])
	}
	ok = true
	return conn, nil
}

func writeUserPass(conn net.Conn, username, password string) error {
	if len(username) > 255 || len(password) > 255 {
		return errors.New("upstream credential too long")
	}
	message := []byte{1, byte(len(username))}
	message = append(message, username...)
	message = append(message, byte(len(password)))
	message = append(message, password...)
	if err := writeAll(conn, message); err != nil {
		return err
	}
	reply, err := readFixed(conn, 2)
	if err != nil || reply[1] != 0 {
		return errUpstreamAuth
	}
	return nil
}

func readReply(conn net.Conn) ([]byte, error) {
	head, err := readFixed(conn, 4)
	if err != nil || head[0] != version5 {
		return nil, errors.New("upstream reply invalid")
	}
	var tail []byte
	switch head[3] {
	case 1:
		tail = make([]byte, 6)
	case 3:
		length, err := readByte(conn)
		if err != nil {
			return nil, err
		}
		tail = make([]byte, int(length)+3)
		tail[0] = length
		if _, err := io.ReadFull(conn, tail[1:]); err != nil {
			return nil, err
		}
		return append(head, tail...), nil
	case 4:
		tail = make([]byte, 18)
	default:
		return nil, errors.New("upstream reply address unsupported")
	}
	if _, err := io.ReadFull(conn, tail); err != nil {
		return nil, err
	}
	return append(head, tail...), nil
}

func writeReply(conn net.Conn, code byte) error {
	return writeAll(conn, []byte{version5, code, 0, 1, 0, 0, 0, 0, 0, 0})
}

func readByte(conn net.Conn) (byte, error) {
	var one [1]byte
	_, err := io.ReadFull(conn, one[:])
	return one[0], err
}

func readFixed(conn net.Conn, size int) ([]byte, error) {
	data := make([]byte, size)
	_, err := io.ReadFull(conn, data)
	return data, err
}

func writeAll(conn net.Conn, data []byte) error {
	for len(data) > 0 {
		n, err := conn.Write(data)
		if err != nil {
			return err
		}
		if n == 0 {
			return io.ErrShortWrite
		}
		data = data[n:]
	}
	return nil
}

func copyBidirectional(left, right net.Conn, idle time.Duration) {
	done := make(chan struct{}, 2)
	pump := func(dst, src net.Conn) {
		defer func() { done <- struct{}{} }()
		buffer := make([]byte, 32*1024)
		for {
			_ = src.SetReadDeadline(time.Now().Add(idle))
			n, err := src.Read(buffer)
			if n > 0 {
				_ = dst.SetWriteDeadline(time.Now().Add(idle))
				if _, writeErr := dst.Write(buffer[:n]); writeErr != nil {
					return
				}
			}
			if err != nil {
				return
			}
		}
	}
	go pump(left, right)
	go pump(right, left)
	<-done
	_ = left.SetDeadline(time.Now())
	_ = right.SetDeadline(time.Now())
	<-done
}

func safeErrorCode(err error) string {
	if err == nil {
		return ""
	}
	switch {
	case errors.Is(err, errUpstreamAuth):
		return "UPSTREAM_AUTH_FAILED"
	default:
		return "UPSTREAM_UNREACHABLE"
	}
}

var errUpstreamAuth = errors.New("upstream credentials rejected")
