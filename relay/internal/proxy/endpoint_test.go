package proxy

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func writeEndpointLease(t *testing.T, path, id, ip string, port int, revision uint64) {
	t.Helper()
	raw, err := json.Marshal(endpointLease{Version: 1, LeaseID: id, Revision: revision, UpstreamIP: ip, UpstreamPort: port})
	if err != nil {
		t.Fatal(err)
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, raw, 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(tmp, path); err != nil {
		t.Fatal(err)
	}
}

func TestEndpointLeaseHotReplacement(t *testing.T) {
	dir := t.TempDir()
	id := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	path := filepath.Join(dir, "endpoint.json")
	writeEndpointLease(t, path, id, "192.0.2.10", 1080, 1)
	cfg := Config{
		ListenAddress: "127.0.0.1:19080", UpstreamHost: "192.0.2.10", UpstreamPort: 1080,
		EndpointLeaseFile: path, EndpointLeaseID: id,
	}
	runtime, err := cfg.Resolve(dir)
	if err != nil {
		t.Fatal(err)
	}
	server := NewServer(runtime, nil)
	if got, err := server.currentUpstreamAddress(); err != nil || got != "192.0.2.10:1080" {
		t.Fatalf("initial endpoint=%q err=%v", got, err)
	}
	writeEndpointLease(t, path, id, "192.0.2.11", 1080, 2)
	if got, err := server.currentUpstreamAddress(); err != nil || got != "192.0.2.11:1080" {
		t.Fatalf("updated endpoint=%q err=%v", got, err)
	}
}

func TestEndpointLeaseFailsClosed(t *testing.T) {
	dir := t.TempDir()
	id := "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	path := filepath.Join(dir, "endpoint.json")
	writeEndpointLease(t, path, id, "192.0.2.10", 1080, 1)
	runtime, err := (Config{
		ListenAddress: "127.0.0.1:19080", UpstreamHost: "192.0.2.10", UpstreamPort: 1080,
		EndpointLeaseFile: path, EndpointLeaseID: id,
	}).Resolve(dir)
	if err != nil {
		t.Fatal(err)
	}
	server := NewServer(runtime, nil)
	for name, raw := range map[string][]byte{
		"missing":  nil,
		"wrong-id": []byte(`{"version":1,"lease_id":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","revision":2,"upstream_ip":"192.0.2.11","upstream_port":1080}`),
		"loopback": []byte(`{"version":1,"lease_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","revision":2,"upstream_ip":"127.0.0.1","upstream_port":1080}`),
		"extra":    []byte(`{"version":1,"lease_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","revision":2,"upstream_ip":"192.0.2.11","upstream_port":1080,"extra":true}`),
	} {
		t.Run(name, func(t *testing.T) {
			if raw == nil {
				if err := os.Remove(path); err != nil {
					t.Fatal(err)
				}
			} else if err := os.WriteFile(path, raw, 0600); err != nil {
				t.Fatal(err)
			}
			if got, err := server.currentUpstreamAddress(); err == nil || got != "" {
				t.Fatalf("endpoint=%q err=%v", got, err)
			}
			writeEndpointLease(t, path, id, "192.0.2.10", 1080, 1)
		})
	}
}

func TestEndpointLeaseConfigRequiresBinding(t *testing.T) {
	dir := t.TempDir()
	id := "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
	path := filepath.Join(dir, "endpoint.json")
	writeEndpointLease(t, path, id, "192.0.2.10", 1080, 1)
	for _, cfg := range []Config{
		{ListenAddress: "127.0.0.1:19080", UpstreamHost: "192.0.2.10", UpstreamPort: 1080, EndpointLeaseFile: path},
		{ListenAddress: "127.0.0.1:19080", UpstreamHost: "192.0.2.10", UpstreamPort: 1080, EndpointLeaseID: id},
	} {
		if _, err := cfg.Resolve(dir); err == nil {
			t.Fatal("unpaired endpoint lease accepted")
		}
	}
}
