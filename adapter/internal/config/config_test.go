package config

import (
	"os"
	"testing"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/profile"
)

func TestValidateRejectsRemoteListenWithoutOptIn(t *testing.T) {
	cfg := validConfig()
	cfg.ListenAddress = "0.0.0.0:8080"
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected remote listen to require explicit opt-in")
	}
	cfg.AllowRemoteListen = true
	if err := cfg.Validate(); err != nil {
		t.Fatalf("explicit remote listen rejected: %v", err)
	}
}

func TestAccessRequiresPrivateVerifiedControlAPI(t *testing.T) {
	cfg := validConfig()
	cfg.SealSkin.LifecycleEnabled = true
	cfg.SealSkin.APIBaseURL = "https://127.0.0.1:8443"
	cfg.Access = &access.Config{UsersFile: "/private/users.json", SessionCAFile: "/private/ca.pem",
		SessionTLSName: "session.test", SessionUpstreamURL: cfg.SealSkin.APIBaseURL}
	if err := cfg.Validate(); err != nil {
		t.Fatal(err)
	}
	cfg.SealSkin.APIBaseURL = cfg.SealSkin.PublicSessionBaseURL
	if cfg.Validate() == nil {
		t.Fatal("public control API bypass accepted")
	}
	cfg.SealSkin.APIBaseURL = cfg.Access.SessionUpstreamURL
	cfg.SealSkin.AllowUnencryptedHTTP = true
	if cfg.Validate() == nil {
		t.Fatal("unencrypted control API accepted")
	}
}

func TestValidateRequiresHTTPSPublicURLs(t *testing.T) {
	cfg := validConfig()
	cfg.PublicBaseURL = "http://adapter.example"
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected HTTP public URL rejection")
	}
	cfg = validConfig()
	cfg.SealSkin.PublicSessionBaseURL = "https://sessions.example/?bad=1"
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected session base query rejection")
	}
}

func TestProfileLabelIsOptionalAndValidated(t *testing.T) {
	cfg := validConfig()
	cfg.Profiles = []profile.Definition{{ID: "personal", Label: "个人 · 台北", ApplicationID: "app", HomeName: "personal", StartURL: "https://example.com/"}}
	if err := cfg.Validate(); err != nil {
		t.Fatalf("labelled profile rejected: %v", err)
	}
	// Definition-level validation runs when the profile service starts; the
	// config layer only carries the field through unknown-field-strict decoding.
	raw := `{"listen_address":"127.0.0.1:8080","public_base_url":"https://adapter.example","state_file":"state.json",` +
		`"sealskin":{"api_base_url":"https://api.example","public_session_base_url":"https://sessions.example","username":"adapter",` +
		`"server_public_key_file":"server.pem","client_private_key_file":"client.pem"},` +
		`"profiles":[{"id":"personal","label":"Personal","application_id":"app","home_name":"personal","start_url":"https://example.com/"}]}`
	path := t.TempDir() + "/config.json"
	if err := os.WriteFile(path, []byte(raw), 0o600); err != nil {
		t.Fatal(err)
	}
	loaded, err := Load(path)
	if err != nil || loaded.Profiles[0].Label != "Personal" {
		t.Fatalf("label not loaded: %+v err=%v", loaded.Profiles, err)
	}
}

func validConfig() Config {
	return Config{
		ListenAddress: "127.0.0.1:8080", PublicBaseURL: "https://adapter.example",
		StateFile: "/tmp/state.json",
		SealSkin: SealSkin{
			APIBaseURL: "https://api.example", PublicSessionBaseURL: "https://sessions.example",
			Username: "adapter", ServerPublicKeyFile: "/tmp/server.pem", ClientPrivateKeyFile: "/tmp/client.pem",
		},
		Profiles: []profile.Definition{{ID: "personal"}},
	}
}
