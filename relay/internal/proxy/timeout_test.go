package proxy

import (
	"context"
	"errors"
	"io"
	"net"
	"testing"
	"time"
)

// A successful TCP connect is not a usable upstream. A silent peer must lose
// the connection within the configured handshake budget, without waiting for
// the Worker to disconnect or the entire Relay process to stop.
func TestServerBoundsSilentUpstream(t *testing.T) {
	upstream, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer upstream.Close()
	closed := make(chan error, 1)
	go func() {
		conn, err := upstream.Accept()
		if err != nil {
			closed <- err
			return
		}
		defer conn.Close()
		_ = conn.SetDeadline(time.Now().Add(time.Second))
		if _, err := readFixed(conn, 3); err != nil {
			closed <- err
			return
		}
		_, err = readFixed(conn, 1)
		closed <- err
	}()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() {
		done <- NewServer(RuntimeConfig{UpstreamAddress: upstream.Addr().String(),
			DialTimeout: 100 * time.Millisecond, IdleTimeout: time.Second}, nil).ServeListener(ctx, listener)
	}()
	client, err := net.Dial("tcp", listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	_ = client.SetDeadline(time.Now().Add(2 * time.Second))
	if err := writeAll(client, []byte{5, 1, 0}); err != nil {
		t.Fatal(err)
	}
	if _, err := readFixed(client, 2); err != nil {
		t.Fatal(err)
	}
	if err := writeAll(client, []byte{5, 1, 0, 1, 192, 0, 2, 1, 1, 187}); err != nil {
		t.Fatal(err)
	}
	if err := <-closed; !errors.Is(err, io.EOF) {
		t.Errorf("silent upstream was not closed within handshake budget: %v", err)
	}
	cancel()
	if err := <-done; err != nil {
		t.Fatal(err)
	}
}
