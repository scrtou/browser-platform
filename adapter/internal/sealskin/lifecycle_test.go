package sealskin

import (
	"context"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"
)

func TestVerifiedLifecycleProtocol(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	want := HomeRuntime{Version: 1, HomeName: "personal",
		NetworkRuntimeVersion: 1, Resources: []RuntimeResource{{ID: "relay-1", Kind: "relay", Owned: true,
			ProfileID: "personal", OperationID: strings.Repeat("a", 32), AppID: "firefox",
			PolicyID: "socks-r1", PolicySHA256: strings.Repeat("c", 64), Status: "running"}},
		Records: []RuntimeRecord{{SessionID: "session-1", AppID: "firefox", ProfileID: "personal",
			OperationID: strings.Repeat("a", 32), InstanceIDs: []string{strings.Repeat("b", 64)}, Phase: "stopping"}},
		Workers: []RuntimeWorker{{InstanceID: strings.Repeat("b", 64), SessionID: "session-1", AppID: "firefox",
			ProfileID: "personal", OperationID: strings.Repeat("a", 32), Status: "running", Owned: true, Managed: true, Recorded: true}}}
	fake := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey, runtime: want}
	server := httptest.NewServer(fake)
	defer server.Close()
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, server.Client())
	got, err := client.InspectHome(context.Background(), "personal")
	if err != nil || !reflect.DeepEqual(got, want) {
		t.Fatalf("inventory=%+v err=%v", got, err)
	}
	request := StopProfileRequest{ProfileID: "personal", OperationID: strings.Repeat("a", 32),
		NetworkPolicyID: "socks-r1", NetworkPolicySHA256: strings.Repeat("c", 64),
		ApplicationID: "firefox", SessionID: "session-1", BootstrapURL: "https://adapter.example/bootstrap/personal/op"}
	if err := client.StopHome(context.Background(), "personal", request, "durable-stop-key"); err != nil {
		t.Fatal(err)
	}
	fake.mu.Lock()
	defer fake.mu.Unlock()
	if fake.stopBody != request || fake.stopIdempotency != "durable-stop-key" {
		t.Fatalf("ownership or idempotency was lost: %+v", fake.stopBody)
	}
}

func TestRuntimeInventoryFailsClosedOnIncompleteResponses(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	fake := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey}
	server := httptest.NewServer(fake)
	defer server.Close()
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, server.Client())
	for _, value := range []any{
		nil,
		map[string]any{"version": 1, "home_name": "personal"},
		HomeRuntime{Version: 1, HomeName: "personal", Records: []RuntimeRecord{}},
		HomeRuntime{Version: 1, HomeName: "personal", Workers: []RuntimeWorker{}},
		HomeRuntime{Version: 2, HomeName: "personal", Records: []RuntimeRecord{}, Workers: []RuntimeWorker{}},
		HomeRuntime{Version: 1, HomeName: "work", Records: []RuntimeRecord{}, Workers: []RuntimeWorker{}},
		HomeRuntime{Version: 1, HomeName: "personal", Records: []RuntimeRecord{}, Workers: []RuntimeWorker{}, NetworkRuntimeVersion: 1},
		HomeRuntime{Version: 1, HomeName: "personal", Records: []RuntimeRecord{}, Workers: []RuntimeWorker{}, NetworkRuntimeVersion: 2, Resources: []RuntimeResource{}},
	} {
		fake.mu.Lock()
		fake.runtime = value
		fake.mu.Unlock()
		if _, err := client.InspectHome(context.Background(), "personal"); err == nil {
			t.Fatalf("accepted incomplete or mismatched inventory: %+v", value)
		}
	}
	fake.mu.Lock()
	fake.runtime = HomeRuntime{Version: 1, HomeName: "personal", Records: []RuntimeRecord{}, Workers: []RuntimeWorker{}}
	fake.mu.Unlock()
	if _, err := client.InspectHome(context.Background(), "personal"); err != nil {
		t.Fatalf("complete empty inventory rejected: %v", err)
	}
}

func TestLifecycleRejectsInvalidLocalInputs(t *testing.T) {
	client := &Client{} // A malformed call must fail before contacting the server.
	for _, home := range []string{"", "cleanroom", "CLEANROOM", "../personal", "personal/work", "個人"} {
		if _, err := client.InspectHome(context.Background(), home); err == nil {
			t.Fatalf("invalid Home accepted: %q", home)
		}
	}
	request := StopProfileRequest{ProfileID: "personal", OperationID: strings.Repeat("a", 32),
		ApplicationID: "firefox", BootstrapURL: "https://adapter.example/bootstrap/personal/op"}
	if err := client.StopHome(context.Background(), "personal", request, ""); err == nil {
		t.Fatal("stop without durable idempotency key accepted")
	}
	request.OperationID = ""
	if err := client.StopHome(context.Background(), "personal", request, "key"); err == nil {
		t.Fatal("stop without launch operation accepted")
	}
}
