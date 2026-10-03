package config

import (
	"os"
	"strings"
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

func TestProfileDirectoryAllowsEmptySeedButNeedsLifecycle(t *testing.T) {
	cfg := validConfig()
	cfg.Profiles = nil
	if cfg.Validate() == nil {
		t.Fatal("no profiles and no directory accepted")
	}
	cfg.ProfileDirectory = "/private/profiles.json"
	if cfg.Validate() == nil {
		t.Fatal("directory without lifecycle accepted")
	}
	cfg.SealSkin.LifecycleEnabled = true
	if err := cfg.Validate(); err != nil {
		t.Fatalf("directory with lifecycle rejected: %v", err)
	}
}

func TestEnvironmentCatalogRequiresSeparateAdministratorIdentity(t *testing.T) {
	cfg := validConfig()
	cfg.SealSkin.LifecycleEnabled = true
	cfg.ProfileDirectory = "/private/profiles.json"
	cfg.EnvironmentCatalog = "/private/environment-catalog.json"
	if err := cfg.Validate(); err == nil {
		t.Fatal("catalog without an administrator identity was accepted")
	}
	cfg.SealSkinAdmin = &SealSkinAdmin{Username: "profile-admin", ClientPrivateKeyFile: "/private/admin.pem"}
	if err := cfg.Validate(); err != nil {
		t.Fatalf("separate administrator identity rejected: %v", err)
	}
}

func TestTemplateCatalogRequiresEnvironmentCatalog(t *testing.T) {
	cfg := validConfig()
	cfg.TemplateCatalog = "/private/templates.json"
	if cfg.Validate() == nil {
		t.Fatal("template catalog without environment catalog accepted")
	}
	cfg.SealSkin.LifecycleEnabled = true
	cfg.ProfileDirectory = "/private/profiles.json"
	cfg.EnvironmentCatalog = "/private/environment-catalog.json"
	cfg.SealSkinAdmin = &SealSkinAdmin{Username: "profile-admin", ClientPrivateKeyFile: "/private/admin.pem"}
	if err := cfg.Validate(); err != nil {
		t.Fatalf("template catalog with environment catalog rejected: %v", err)
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

func TestProxyTemplateRequiresCatalogAdminAndLaunchOwner(t *testing.T) {
	cfg := validConfig()
	cfg.SealSkin.LifecycleEnabled = true
	cfg.ProxyTemplate = &profile.ProxyTemplate{Owner: cfg.SealSkin.Username, RelayImage: "sha256:" + strings.Repeat("1", 64), ProbeImage: "sha256:" + strings.Repeat("2", 64), ProbeURL: "https://probe.example/"}
	if cfg.Validate() == nil {
		t.Fatal("proxy template without environment catalog accepted")
	}
	cfg.ProfileDirectory, cfg.EnvironmentCatalog = "/private/profiles.json", "/private/catalog.json"
	cfg.SealSkinAdmin = &SealSkinAdmin{Username: "profile-admin", ClientPrivateKeyFile: "/private/admin.pem"}
	if err := cfg.Validate(); err != nil {
		t.Fatal(err)
	}
	cfg.ProxyTemplate.Owner = "profile-admin"
	if cfg.Validate() == nil {
		t.Fatal("proxy template owner other than the launch identity accepted")
	}
	cfg.ProxyTemplate.Owner = cfg.SealSkin.Username
	cfg.ProxyTemplate.RelayImage = "relay:latest"
	if cfg.Validate() == nil {
		t.Fatal("proxy template with a tag instead of a digest accepted")
	}
}

func TestNetworkProfileCatalogRequiresProxyTemplate(t *testing.T) {
	cfg := validConfig()
	cfg.SealSkin.LifecycleEnabled = true
	cfg.ProfileDirectory, cfg.EnvironmentCatalog = "/private/profiles.json", "/private/catalog.json"
	cfg.SealSkinAdmin = &SealSkinAdmin{Username: "profile-admin", ClientPrivateKeyFile: "/private/admin.pem"}
	cfg.NetworkProfileCatalog = "/private/network_profiles.json"
	if cfg.Validate() == nil {
		t.Fatal("network profile catalog without proxy template accepted")
	}
	cfg.ProxyTemplate = &profile.ProxyTemplate{Owner: cfg.SealSkin.Username, RelayImage: "sha256:" + strings.Repeat("1", 64), ProbeImage: "sha256:" + strings.Repeat("2", 64), ProbeURL: "https://probe.example/"}
	if err := cfg.Validate(); err != nil {
		t.Fatalf("network profile catalog with complete dependencies rejected: %v", err)
	}
}

func TestDirectTemplateRequiresCatalogAdminAndLaunchOwner(t *testing.T) {
	cfg := validConfig()
	cfg.SealSkin.LifecycleEnabled = true
	cfg.DirectTemplate = &profile.DirectTemplate{Owner: cfg.SealSkin.Username, ApprovedResolverID: "cloudflare-r7e", ApprovedResolverIP: "1.1.1.1", RelayImage: "sha256:" + strings.Repeat("1", 64), ProbeImage: "sha256:" + strings.Repeat("2", 64), ProbeURL: "https://probe.example/"}
	if cfg.Validate() == nil {
		t.Fatal("direct template without environment catalog accepted")
	}
	cfg.ProfileDirectory, cfg.EnvironmentCatalog = "/private/profiles.json", "/private/catalog.json"
	cfg.SealSkinAdmin = &SealSkinAdmin{Username: "profile-admin", ClientPrivateKeyFile: "/private/admin.pem"}
	if err := cfg.Validate(); err != nil {
		t.Fatal(err)
	}
	cfg.DirectTemplate.Owner = "profile-admin"
	if cfg.Validate() == nil {
		t.Fatal("direct template owner other than the launch identity accepted")
	}
	cfg.DirectTemplate.Owner = cfg.SealSkin.Username
	cfg.DirectTemplate.ApprovedResolverIP = "127.0.0.1"
	if cfg.Validate() == nil {
		t.Fatal("loopback DIRECT resolver accepted")
	}
}
