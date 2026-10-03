package sealskin

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestInstalledAppDefinitionPreservesResolvedFieldsAndRejectsAmbiguity(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	definition := map[string]any{"id": "work", "name": "Work", "provider_config": map[string]any{
		"image": "sha256:" + strings.Repeat("a", 64), "custom_autostart_script_b64": nil, "env": []any{map[string]any{"name": "KEEP", "value": "same"}}},
		"home_directories": true, "auto_update": false, "image_sha": "volatile", "last_checked_at": "now", "pull_status": "done"}
	fake := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey, installedApps: []map[string]any{definition}}
	server := httptest.NewServer(fake)
	defer server.Close()
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, server.Client())
	app, err := client.InstalledAppDefinition(context.Background(), "work")
	if err != nil {
		t.Fatal(err)
	}
	wanted := map[string]any{}
	for key, value := range definition {
		if key != "image_sha" && key != "last_checked_at" && key != "pull_status" {
			wanted[key] = value
		}
	}
	actualJSON, _ := json.Marshal(app)
	expectedJSON, _ := json.Marshal(wanted)
	if string(actualJSON) != string(expectedJSON) {
		t.Fatal("resolved application fields were lost or observations retained")
	}
	if _, err = client.InstalledAppDefinition(context.Background(), "missing"); err == nil {
		t.Fatal("missing application accepted")
	}
	fake.mu.Lock()
	fake.installedApps = append(fake.installedApps, definition)
	fake.mu.Unlock()
	if _, err = client.InstalledAppDefinition(context.Background(), "work"); err == nil {
		t.Fatal("duplicate identity accepted")
	}
}
