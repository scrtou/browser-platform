package proxy

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/netip"
	"strconv"
)

type endpointLease struct {
	Version      int    `json:"version"`
	LeaseID      string `json:"lease_id"`
	Revision     uint64 `json:"revision"`
	UpstreamIP   string `json:"upstream_ip"`
	UpstreamPort int    `json:"upstream_port"`
}

func canonicalLeaseID(value string) bool {
	if len(value) != 64 {
		return false
	}
	decoded, err := hex.DecodeString(value)
	return err == nil && hex.EncodeToString(decoded) == value
}

func readEndpointLease(path, id string, port int) (endpointLease, error) {
	var value endpointLease
	if !canonicalLeaseID(id) || port < 1 || port > 65535 {
		return value, errEndpointLease
	}
	raw, err := readRegularFile("", path, 4096, false)
	if err != nil {
		return value, errEndpointLease
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&value); err != nil {
		return endpointLease{}, errEndpointLease
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return endpointLease{}, errEndpointLease
	}
	address, err := netip.ParseAddr(value.UpstreamIP)
	if err != nil || !address.Is4() || !address.IsGlobalUnicast() || address.IsLoopback() ||
		address.IsUnspecified() || address.IsMulticast() || value.Version != 1 || value.LeaseID != id ||
		value.Revision == 0 || value.UpstreamPort != port {
		return endpointLease{}, errEndpointLease
	}
	return value, nil
}

func validEndpointLease(path, id string, port int) bool {
	_, err := readEndpointLease(path, id, port)
	return err == nil
}

func (s *Server) currentUpstreamAddress() (string, error) {
	if s.cfg.EndpointLeaseFile == "" {
		return s.cfg.UpstreamAddress, nil
	}
	lease, err := readEndpointLease(s.cfg.EndpointLeaseFile, s.cfg.EndpointLeaseID, upstreamPort(s.cfg.UpstreamAddress))
	if err != nil {
		return "", err
	}
	return net.JoinHostPort(lease.UpstreamIP, strconv.Itoa(lease.UpstreamPort)), nil
}

func upstreamPort(address string) int {
	_, value, err := net.SplitHostPort(address)
	if err != nil {
		return 0
	}
	port, err := strconv.Atoi(value)
	if err != nil {
		return 0
	}
	return port
}
