package config

import (
	"testing"

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
