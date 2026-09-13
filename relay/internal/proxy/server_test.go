package proxy

import (
	"context"
	"encoding/binary"
	"fmt"
	"net"
	"testing"
	"time"
)

func TestServerForwardsAuthenticatedDomainConnect(t *testing.T) {
	upstreamListener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer upstreamListener.Close()

	upstreamDone := make(chan error, 1)
	go func() {
		conn, err := upstreamListener.Accept()
		if err != nil {
			upstreamDone <- err
			return
		}
		defer conn.Close()
		if greeting, err := readFixed(conn, 3); err != nil || string(greeting) != "\x05\x01\x02" {
			upstreamDone <- errUnexpected(greeting, "upstream greeting")
			return
		}
		if _, err := conn.Write([]byte{version5, userPassAuth}); err != nil {
			upstreamDone <- err
			return
		}
		version, err := readByte(conn)
		if err != nil || version != 1 {
			upstreamDone <- errUnexpected([]byte{version}, "auth version")
			return
		}
		usernameLength, err := readByte(conn)
		if err != nil {
			upstreamDone <- err
			return
		}
		username, err := readFixed(conn, int(usernameLength))
		if err != nil {
			upstreamDone <- err
			return
		}
		passwordLength, err := readByte(conn)
		if err != nil {
			upstreamDone <- err
			return
		}
		password, err := readFixed(conn, int(passwordLength))
		if err != nil {
			upstreamDone <- err
			return
		}
		if string(username) != "user" || string(password) != "pass" {
			upstreamDone <- errUnexpected(append(username, password...), "credentials")
			return
		}
		if _, err := conn.Write([]byte{1, 0}); err != nil {
			upstreamDone <- err
			return
		}
		requestHead, err := readFixed(conn, 4)
		if err != nil {
			upstreamDone <- err
			return
		}
		if requestHead[0] != version5 || requestHead[1] != commandConnect || requestHead[3] != 3 {
			upstreamDone <- errUnexpected(requestHead, "connect request")
			return
		}
		length, err := readByte(conn)
		if err != nil {
			upstreamDone <- err
			return
		}
		domain, err := readFixed(conn, int(length))
		if err != nil {
			upstreamDone <- err
			return
		}
		portBytes, err := readFixed(conn, 2)
		if err != nil {
			upstreamDone <- err
			return
		}
		if string(domain) != "target.example" || binary.BigEndian.Uint16(portBytes) != 443 {
			upstreamDone <- errUnexpected(domain, "target")
			return
		}
		if _, err := conn.Write([]byte{version5, replySucceeded, 0, 1, 0, 0, 0, 0, 0, 0}); err != nil {
			upstreamDone <- err
			return
		}
		payload, err := readFixed(conn, 5)
		if err != nil {
			upstreamDone <- err
			return
		}
		if string(payload) != "hello" {
			upstreamDone <- errUnexpected(payload, "payload")
			return
		}
		_, err = conn.Write([]byte("world"))
		upstreamDone <- err
	}()

	relayListener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	runtime := RuntimeConfig{
		UpstreamAddress: upstreamListener.Addr().String(), Username: "user", Password: "pass",
		DialTimeout: time.Second, IdleTimeout: time.Second,
	}
	serveDone := make(chan error, 1)
	go func() { serveDone <- NewServer(runtime, nil).ServeListener(ctx, relayListener) }()

	client, err := net.Dial("tcp", relayListener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	if _, err := client.Write([]byte{version5, 1, noAuth}); err != nil {
		t.Fatal(err)
	}
	if reply, err := readFixed(client, 2); err != nil || string(reply) != "\x05\x00" {
		t.Fatalf("client greeting reply=%x err=%v", reply, err)
	}
	request := append([]byte{version5, commandConnect, 0, 3, byte(len("target.example"))}, []byte("target.example")...)
	request = append(request, 1, 187)
	if _, err := client.Write(request); err != nil {
		t.Fatal(err)
	}
	if reply, err := readFixed(client, 10); err != nil || reply[1] != replySucceeded {
		t.Fatalf("connect reply=%x err=%v", reply, err)
	}
	if _, err := client.Write([]byte("hello")); err != nil {
		t.Fatal(err)
	}
	world, err := readFixed(client, 5)
	if err != nil || string(world) != "world" {
		t.Fatalf("forwarded response=%q err=%v", world, err)
	}
	if err := <-upstreamDone; err != nil {
		t.Fatal(err)
	}
	cancel()
	if err := <-serveDone; err != nil {
		t.Fatal(err)
	}
}

func TestServerReturnsFailureWithoutDirectFallback(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	upstreamAddress := listener.Addr().String()
	listener.Close()

	relayListener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	runtime := RuntimeConfig{UpstreamAddress: upstreamAddress, DialTimeout: 100 * time.Millisecond, IdleTimeout: time.Second}
	serveDone := make(chan error, 1)
	go func() { serveDone <- NewServer(runtime, nil).ServeListener(ctx, relayListener) }()

	client, err := net.Dial("tcp", relayListener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	_, _ = client.Write([]byte{version5, 1, noAuth})
	if _, err := readFixed(client, 2); err != nil {
		t.Fatal(err)
	}
	request := append([]byte{version5, commandConnect, 0, 3, byte(len("target.example"))}, []byte("target.example")...)
	request = append(request, 1, 187)
	_, _ = client.Write(request)
	reply, err := readFixed(client, 10)
	if err != nil {
		t.Fatal(err)
	}
	if reply[1] == replySucceeded {
		t.Fatalf("unexpected successful direct fallback: %x", reply)
	}
	cancel()
	if err := <-serveDone; err != nil {
		t.Fatal(err)
	}
}

func errUnexpected(got []byte, name string) error {
	return fmt.Errorf("unexpected %s bytes: %x", name, got)
}
