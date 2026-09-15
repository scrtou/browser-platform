package proxy

import (
	"context"
	"encoding/binary"
	"io"
	"net"
	"net/netip"
	"reflect"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"golang.org/x/net/dns/dnsmessage"
)

func dnsFixture(t *testing.T, reply func(dnsmessage.Message, string) dnsmessage.Message) string {
	t.Helper()
	tcp, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	udp, err := net.ListenPacket("udp4", tcp.Addr().String())
	if err != nil {
		tcp.Close()
		t.Fatal(err)
	}
	encode := func(raw []byte, transport string) []byte {
		var question dnsmessage.Message
		if err := question.Unpack(raw); err != nil {
			t.Error(err)
			return nil
		}
		response := reply(question, transport)
		encoded, err := response.Pack()
		if err != nil {
			t.Error(err)
		}
		return encoded
	}
	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		buf := make([]byte, 65535)
		for {
			n, addr, err := udp.ReadFrom(buf)
			if err != nil {
				return
			}
			_, _ = udp.WriteTo(encode(buf[:n], "udp"), addr)
		}
	}()
	go func() {
		defer wg.Done()
		for {
			conn, err := tcp.Accept()
			if err != nil {
				return
			}
			_ = conn.SetDeadline(time.Now().Add(time.Second))
			var size [2]byte
			if _, err := io.ReadFull(conn, size[:]); err == nil {
				buf := make([]byte, binary.BigEndian.Uint16(size[:]))
				if _, err := io.ReadFull(conn, buf); err == nil {
					answer := encode(buf, "tcp")
					binary.BigEndian.PutUint16(size[:], uint16(len(answer)))
					_ = writeAll(conn, append(size[:], answer...))
				}
			}
			_ = conn.Close()
		}
	}()
	t.Cleanup(func() { udp.Close(); tcp.Close(); wg.Wait() })
	return tcp.Addr().String()
}

func dnsA(name string, ip [4]byte) dnsmessage.Resource {
	return dnsmessage.Resource{Header: dnsmessage.ResourceHeader{Name: dnsmessage.MustNewName(name),
		Type: dnsmessage.TypeA, Class: dnsmessage.ClassINET, TTL: 5}, Body: &dnsmessage.AResource{A: ip}}
}

func dnsCNAME(name, target string) dnsmessage.Resource {
	return dnsmessage.Resource{Header: dnsmessage.ResourceHeader{Name: dnsmessage.MustNewName(name),
		Type: dnsmessage.TypeCNAME, Class: dnsmessage.ClassINET, TTL: 5},
		Body: &dnsmessage.CNAMEResource{CNAME: dnsmessage.MustNewName(target)}}
}

func dnsReply(query dnsmessage.Message) dnsmessage.Message {
	return dnsmessage.Message{Header: dnsmessage.Header{ID: query.ID, Response: true, RecursionAvailable: true},
		Questions: query.Questions}
}

func TestDirectDNSUsesApprovedUDPAndTCPFallback(t *testing.T) {
	var udp, tcp atomic.Int32
	endpoint := dnsFixture(t, func(query dnsmessage.Message, transport string) dnsmessage.Message {
		result := dnsReply(query)
		if transport == "udp" {
			udp.Add(1)
			result.Truncated = true
		} else {
			tcp.Add(1)
			result.Answers = []dnsmessage.Resource{dnsA(query.Questions[0].Name.String(), [4]byte{1, 1, 1, 1})}
		}
		return result
	})
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	addresses, err := lookupDirectIPv4(ctx, endpoint, "public.test")
	if err != nil || !reflect.DeepEqual(addresses, []netip.Addr{netip.MustParseAddr("1.1.1.1")}) || udp.Load() != 1 || tcp.Load() != 1 {
		t.Fatalf("approved resolver result: %v %v udp=%d tcp=%d", addresses, err, udp.Load(), tcp.Load())
	}
}

func TestDirectDNSCNAMEChainsAndMixedAnswers(t *testing.T) {
	for _, inline := range []bool{false, true} {
		t.Run(map[bool]string{false: "new-query", true: "inline"}[inline], func(t *testing.T) {
			endpoint := dnsFixture(t, func(query dnsmessage.Message, _ string) dnsmessage.Message {
				result := dnsReply(query)
				if query.Questions[0].Name.String() == "alias.test." {
					result.Answers = []dnsmessage.Resource{dnsCNAME("alias.test.", "target.test.")}
				}
				if inline || query.Questions[0].Name.String() == "target.test." {
					result.Answers = append(result.Answers, dnsA("target.test.", [4]byte{1, 1, 1, 1}), dnsA("target.test.", [4]byte{10, 0, 0, 1}))
				}
				return result
			})
			ctx, cancel := context.WithTimeout(context.Background(), time.Second)
			defer cancel()
			addresses, err := lookupDirectIPv4(ctx, endpoint, "alias.test")
			if err != nil || len(addresses) != 2 || addresses[1].String() != "10.0.0.1" {
				t.Fatalf("DNS result silently dropped protected address: %v %v", addresses, err)
			}
		})
	}
}

func TestDirectDNSRejectsSpoofedIncompleteAndLoopingReplies(t *testing.T) {
	for name, mutate := range map[string]func(*dnsmessage.Message){
		"id":          func(m *dnsmessage.Message) { m.ID++ },
		"question":    func(m *dnsmessage.Message) { m.Questions[0].Name = dnsmessage.MustNewName("other.test.") },
		"type":        func(m *dnsmessage.Message) { m.Questions[0].Type = dnsmessage.TypeAAAA },
		"query":       func(m *dnsmessage.Message) { m.Response = false },
		"nxdomain":    func(m *dnsmessage.Message) { m.RCode = dnsmessage.RCodeNameError },
		"unrelated":   func(m *dnsmessage.Message) { m.Answers[0].Header.Name = dnsmessage.MustNewName("other.test.") },
		"empty":       func(m *dnsmessage.Message) { m.Answers = nil },
		"loop":        func(m *dnsmessage.Message) { m.Answers = []dnsmessage.Resource{dnsCNAME("localhost.", "localhost.")} },
		"alias-and-A": func(m *dnsmessage.Message) { m.Answers = append(m.Answers, dnsCNAME("localhost.", "other.test.")) },
	} {
		t.Run(name, func(t *testing.T) {
			var queries atomic.Int32
			endpoint := dnsFixture(t, func(query dnsmessage.Message, _ string) dnsmessage.Message {
				queries.Add(1)
				m := dnsReply(query)
				m.Answers = []dnsmessage.Resource{dnsA("localhost.", [4]byte{1, 1, 1, 1})}
				mutate(&m)
				return m
			})
			ctx, cancel := context.WithTimeout(context.Background(), time.Second)
			defer cancel()
			addresses, err := lookupDirectIPv4(ctx, endpoint, "localhost")
			if err == nil || len(addresses) != 0 || queries.Load() != 1 {
				t.Fatalf("invalid DNS reply or system-hosts fallback accepted: %v %v calls=%d", addresses, err, queries.Load())
			}
		})
	}
}

func TestDirectDNSUnavailableIsBoundedWithoutFallback(t *testing.T) {
	listener, err := net.ListenPacket("udp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	started := time.Now()
	if addresses, err := lookupDirectIPv4(ctx, listener.LocalAddr().String(), "example.com"); err == nil || len(addresses) != 0 || time.Since(started) > time.Second {
		t.Fatalf("resolver failure used fallback or exceeded deadline: %v %v", addresses, err)
	}
}
