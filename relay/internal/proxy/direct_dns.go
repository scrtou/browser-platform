package proxy

import (
	"context"
	"crypto/rand"
	"encoding/binary"
	"io"
	"net"
	"net/netip"
	"strings"

	"golang.org/x/net/dns/dnsmessage"
)

// Query the exact approved endpoint. net.Resolver is intentionally not used:
// even its Go implementation may consult the process's /etc/hosts first.
// Nothing here reads resolv.conf, caches an answer, or falls back to another
// resolver. TCP fallback for a truncated UDP reply uses the same endpoint.
func directDNSQuery(ctx context.Context, endpoint, host string) (dnsmessage.Message, error) {
	var empty dnsmessage.Message
	name, err := dnsmessage.NewName(strings.TrimSuffix(host, ".") + ".")
	if err != nil || !validDNSName(host) {
		return empty, errDirectDNS
	}
	var random [2]byte
	if _, err := rand.Read(random[:]); err != nil {
		return empty, errDirectDNS
	}
	id := binary.BigEndian.Uint16(random[:])
	query := dnsmessage.Message{
		Header:    dnsmessage.Header{ID: id, RecursionDesired: true},
		Questions: []dnsmessage.Question{{Name: name, Type: dnsmessage.TypeA, Class: dnsmessage.ClassINET}},
	}
	raw, err := query.Pack()
	if err != nil {
		return empty, errDirectDNS
	}
	for _, transport := range []string{"udp4", "tcp4"} {
		answer, err := directDNSExchange(ctx, transport, endpoint, raw)
		if err != nil {
			return empty, errDirectDNS
		}
		var message dnsmessage.Message
		if err := message.Unpack(answer); err != nil || !message.Response || message.ID != id ||
			message.OpCode != 0 || len(message.Questions) != 1 ||
			!strings.EqualFold(message.Questions[0].Name.String(), name.String()) ||
			message.Questions[0].Class != dnsmessage.ClassINET || message.Questions[0].Type != dnsmessage.TypeA {
			return empty, errDirectDNS
		}
		if message.Truncated && transport == "udp4" {
			continue
		}
		if message.Truncated || message.RCode != dnsmessage.RCodeSuccess || len(message.Answers) > 64 {
			return empty, errDirectDNS
		}
		return message, nil
	}
	return empty, errDirectDNS
}

func directDNSExchange(ctx context.Context, transport, endpoint string, query []byte) ([]byte, error) {
	conn, err := (&net.Dialer{}).DialContext(ctx, transport, endpoint)
	if err != nil {
		return nil, err
	}
	defer conn.Close()
	stop := context.AfterFunc(ctx, func() { _ = conn.Close() })
	defer stop()
	if deadline, ok := ctx.Deadline(); ok {
		if err := conn.SetDeadline(deadline); err != nil {
			return nil, err
		}
	}
	if transport == "tcp4" {
		packet := make([]byte, len(query)+2)
		binary.BigEndian.PutUint16(packet, uint16(len(query)))
		copy(packet[2:], query)
		if err := writeAll(conn, packet); err != nil {
			return nil, err
		}
		var size [2]byte
		if _, err := io.ReadFull(conn, size[:]); err != nil {
			return nil, err
		}
		n := int(binary.BigEndian.Uint16(size[:]))
		if n < 12 {
			return nil, errDirectDNS
		}
		answer := make([]byte, n)
		_, err := io.ReadFull(conn, answer)
		return answer, err
	}
	if _, err := conn.Write(query); err != nil {
		return nil, err
	}
	answer := make([]byte, 65535)
	n, err := conn.Read(answer)
	return answer[:n], err
}

func lookupDirectIPv4(ctx context.Context, endpoint, host string) ([]netip.Addr, error) {
	current := strings.ToLower(strings.TrimSuffix(host, ".")) + "."
	visited := make(map[string]bool)
	for len(visited) < 8 {
		if visited[current] {
			return nil, errDirectDNS
		}
		message, err := directDNSQuery(ctx, endpoint, current)
		if err != nil {
			return nil, err
		}
		addresses := make(map[string][]netip.Addr)
		aliases := make(map[string]string)
		for _, resource := range message.Answers {
			if resource.Header.Class != dnsmessage.ClassINET {
				return nil, errDirectDNS
			}
			owner := strings.ToLower(resource.Header.Name.String())
			switch value := resource.Body.(type) {
			case *dnsmessage.AResource:
				addresses[owner] = append(addresses[owner], netip.AddrFrom4(value.A))
			case *dnsmessage.CNAMEResource:
				target := strings.ToLower(value.CNAME.String())
				if !validDNSName(target) || aliases[owner] != "" && aliases[owner] != target {
					return nil, errDirectDNS
				}
				aliases[owner] = target
			}
		}
		for len(visited) < 8 {
			if visited[current] || len(addresses[current]) > 0 && aliases[current] != "" {
				return nil, errDirectDNS
			}
			if result := addresses[current]; len(result) > 0 {
				return result, nil
			}
			target := aliases[current]
			if target == "" {
				// An empty answer is NODATA, not permission to use the OS DNS.
				return nil, errDirectDNS
			}
			visited[current] = true
			current = target
			if addresses[current] == nil && aliases[current] == "" {
				break // CNAME target needs a new query to the same resolver.
			}
		}
	}
	return nil, errDirectDNS
}
