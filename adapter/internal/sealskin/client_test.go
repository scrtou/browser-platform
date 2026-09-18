package sealskin

import (
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

type fakeSealSkinServer struct {
	mu                sync.Mutex
	serverPrivate     *rsa.PrivateKey
	clientPublic      *rsa.PublicKey
	sessionID         string
	sessionKey        []byte
	homes             []string
	sessions          []Session
	launchBody        LaunchURLRequest
	launchIdempotency string
	installedApps     []map[string]any
	installKey        string
	deleteAppKey      string
	deletedApp        string
	archiveKey        string
	archiveHome       string
	archiveName       string
	secretImport      ProxySecretImportRequest
	secretImportKey   string
	probeRequest      ProxyProbeRequest
	probeResult       ProxyProbeResult
	policyAppend      NetworkPolicyAppendRequest
	policyAppendKey   string
	revokeBody        RevokeSecretRequest
	revokeKey         string
	runtime           any
	health            any
	healthQueries     []string
	coherence         any
	coherenceBodies   []StopProfileRequest
	coherenceKeys     []string
	coherencePaths    []string
	stopBody          StopProfileRequest
	stopIdempotency   string
	handshakes        int
	tamperSignature   bool
	expireListOnce    bool
}

func (f *fakeSealSkinServer) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	switch request.URL.Path {
	case "/api/handshake/initiate":
		f.handshakes++
		nonce := make([]byte, 32)
		_, _ = rand.Read(nonce)
		digest := sha256.Sum256(nonce)
		signature, _ := rsa.SignPSS(rand.Reader, f.serverPrivate, crypto.SHA256, digest[:], &rsa.PSSOptions{SaltLength: 32})
		if f.tamperSignature {
			signature[0] ^= 0xff
		}
		writeJSON(writer, http.StatusOK, map[string]string{
			"nonce":     base64.StdEncoding.EncodeToString(nonce),
			"signature": base64.StdEncoding.EncodeToString(signature),
		})
		return
	case "/api/handshake/exchange":
		var body struct {
			EncryptedSessionKey string `json:"encrypted_session_key"`
		}
		if json.NewDecoder(request.Body).Decode(&body) != nil {
			http.Error(writer, "bad body", http.StatusBadRequest)
			return
		}
		wrapped, _ := base64.StdEncoding.DecodeString(body.EncryptedSessionKey)
		key, err := rsa.DecryptOAEP(sha256.New(), rand.Reader, f.serverPrivate, wrapped, nil)
		if err != nil {
			http.Error(writer, "bad key", http.StatusBadRequest)
			return
		}
		f.sessionID = fmt.Sprintf("crypto-%d", f.handshakes)
		f.sessionKey = key
		writeJSON(writer, http.StatusOK, map[string]string{"session_id": f.sessionID})
		return
	}

	if request.Header.Get("X-Session-ID") != f.sessionID || f.sessionID == "" {
		writeJSON(writer, http.StatusBadRequest, map[string]string{"detail": "Secure session required. Encryption key missing or invalid."})
		return
	}
	if f.expireListOnce && request.Method == http.MethodGet && request.URL.Path == "/api/sessions" {
		f.expireListOnce = false
		f.sessionID = "expired"
		writeJSON(writer, http.StatusBadRequest, map[string]string{"detail": "Secure session required. Encryption key missing or invalid."})
		return
	}
	if err := verifyTestJWT(request.Header.Get("Authorization"), f.clientPublic); err != nil {
		f.writeEncrypted(writer, http.StatusUnauthorized, map[string]string{"detail": err.Error()})
		return
	}

	var plain []byte
	if request.Body != nil {
		raw, _ := io.ReadAll(request.Body)
		if len(raw) > 0 {
			var envelope encryptedPayload
			if json.Unmarshal(raw, &envelope) != nil {
				f.writeEncrypted(writer, http.StatusBadRequest, map[string]string{"detail": "bad envelope"})
				return
			}
			var err error
			plain, err = decrypt(f.sessionKey, envelope)
			if err != nil {
				f.writeEncrypted(writer, http.StatusBadRequest, map[string]string{"detail": "Failed to decrypt request"})
				return
			}
		}
	}

	switch {
	case request.Method == http.MethodPost && (request.URL.Path == "/api/profile-runtime/personal/coherence/access" || request.URL.Path == "/api/profile-runtime/personal/coherence/probe"):
		var body StopProfileRequest
		key := request.Header.Get("X-Idempotency-Key")
		if json.Unmarshal(plain, &body) != nil || key == "" {
			f.writeEncrypted(writer, http.StatusBadRequest, map[string]string{"detail": "invalid coherence request"})
			return
		}
		f.coherenceBodies = append(f.coherenceBodies, body)
		f.coherenceKeys = append(f.coherenceKeys, key)
		f.coherencePaths = append(f.coherencePaths, request.URL.Path)
		f.writeEncrypted(writer, http.StatusOK, f.coherence)
	case request.Method == http.MethodGet && request.URL.Path == "/api/profile-runtime/personal/health":
		f.healthQueries = append(f.healthQueries, request.URL.RawQuery)
		f.writeEncrypted(writer, http.StatusOK, f.health)
	case request.Method == http.MethodGet && request.URL.Path == "/api/profile-runtime/personal":
		f.writeEncrypted(writer, http.StatusOK, f.runtime)
	case request.Method == http.MethodPost && request.URL.Path == "/api/profile-runtime/personal/stop":
		if err := json.Unmarshal(plain, &f.stopBody); err != nil {
			f.writeEncrypted(writer, http.StatusUnprocessableEntity, map[string]string{"detail": "bad stop"})
			return
		}
		f.stopIdempotency = request.Header.Get("X-Idempotency-Key")
		writer.WriteHeader(http.StatusNoContent)
	case request.Method == http.MethodGet && request.URL.Path == "/api/admin/apps/installed":
		f.writeEncrypted(writer, http.StatusOK, f.installedApps)
	case request.Method == http.MethodPost && request.URL.Path == "/api/admin/apps/installed":
		var app map[string]any
		if json.Unmarshal(plain, &app) != nil {
			f.writeEncrypted(writer, http.StatusUnprocessableEntity, map[string]string{"detail": "invalid app"})
			return
		}
		for _, current := range f.installedApps {
			if current["id"] == app["id"] {
				f.writeEncrypted(writer, http.StatusConflict, map[string]string{"detail": "app already exists"})
				return
			}
		}
		f.installKey = request.Header.Get("X-Idempotency-Key")
		f.installedApps = append(f.installedApps, app)
		f.writeEncrypted(writer, http.StatusCreated, app)
	case request.Method == http.MethodDelete && strings.HasPrefix(request.URL.Path, "/api/admin/apps/installed/"):
		f.deletedApp = strings.TrimPrefix(request.URL.Path, "/api/admin/apps/installed/")
		f.deleteAppKey = request.Header.Get("X-Idempotency-Key")
		writer.WriteHeader(http.StatusNoContent)
	case request.Method == http.MethodPost && strings.HasPrefix(request.URL.Path, "/api/homedirs/") && strings.HasSuffix(request.URL.Path, "/archive"):
		var body struct {
			ArchiveName string `json:"archive_name"`
		}
		if json.Unmarshal(plain, &body) != nil {
			f.writeEncrypted(writer, http.StatusUnprocessableEntity, map[string]string{"detail": "invalid archive"})
			return
		}
		f.archiveHome = strings.TrimSuffix(strings.TrimPrefix(request.URL.Path, "/api/homedirs/"), "/archive")
		f.archiveName, f.archiveKey = body.ArchiveName, request.Header.Get("X-Idempotency-Key")
		writer.WriteHeader(http.StatusNoContent)
	case request.Method == http.MethodPost && request.URL.Path == "/api/admin/environment-management/proxy-secrets":
		if json.Unmarshal(plain, &f.secretImport) != nil || request.Header.Get("X-Idempotency-Key") == "" {
			f.writeEncrypted(writer, http.StatusUnprocessableEntity, map[string]string{"detail": "SECRET_IMPORT_REQUEST_INVALID"})
			return
		}
		f.secretImportKey = request.Header.Get("X-Idempotency-Key")
		version := fmt.Sprint(f.secretImport.SecretVersion)
		f.writeEncrypted(writer, http.StatusCreated, ProxySecretRefs{UsernameSecretRef: "secret://" + f.secretImport.SecretID + "/username/" + version,
			PasswordSecretRef: "secret://" + f.secretImport.SecretID + "/password/" + version})
	case request.Method == http.MethodPost && request.URL.Path == "/api/admin/environment-management/proxy-probe":
		if json.Unmarshal(plain, &f.probeRequest) != nil {
			f.writeEncrypted(writer, http.StatusUnprocessableEntity, map[string]string{"detail": "PROXY_PROBE_REQUEST_INVALID"})
			return
		}
		f.writeEncrypted(writer, http.StatusOK, f.probeResult)
	case request.Method == http.MethodPost && request.URL.Path == "/api/admin/environment-management/network-policies":
		if json.Unmarshal(plain, &f.policyAppend) != nil || request.Header.Get("X-Idempotency-Key") == "" {
			f.writeEncrypted(writer, http.StatusUnprocessableEntity, map[string]string{"detail": "NETWORK_POLICY_INVALID"})
			return
		}
		f.policyAppendKey = request.Header.Get("X-Idempotency-Key")
		digest := sha256.Sum256(plain)
		f.writeEncrypted(writer, http.StatusCreated, NetworkPolicyAppendResponse{PolicyID: f.policyAppend.PolicyID, PolicySHA256: hex.EncodeToString(digest[:]), Created: true})
	case request.Method == http.MethodPost && request.URL.Path == "/api/admin/profile-secrets/revoke":
		if json.Unmarshal(plain, &f.revokeBody) != nil {
			f.writeEncrypted(writer, http.StatusUnprocessableEntity, map[string]string{"detail": "SECRET_REVOKE_REQUEST_INVALID"})
			return
		}
		f.revokeKey = request.Header.Get("X-Idempotency-Key")
		f.writeEncrypted(writer, http.StatusOK, RevokeSecretResult{Revoked: true, EgressBlocked: true, CleanupComplete: true, SecretID: "proxy-a", SecretVersion: 1})
	case request.Method == http.MethodGet && request.URL.Path == "/api/sessions":
		f.writeEncrypted(writer, http.StatusOK, f.sessions)
	case request.Method == http.MethodPost && request.URL.Path == "/api/launch/url":
		if request.Header.Get("X-Idempotency-Key") == "" {
			f.writeEncrypted(writer, http.StatusBadRequest, map[string]string{"detail": "missing idempotency"})
			return
		}
		if err := json.Unmarshal(plain, &f.launchBody); err != nil {
			f.writeEncrypted(writer, http.StatusUnprocessableEntity, map[string]string{"detail": "bad launch"})
			return
		}
		f.launchIdempotency = request.Header.Get("X-Idempotency-Key")
		session := Session{
			SessionID: "browser-1", AppID: f.launchBody.ApplicationID, AppName: "Firefox",
			SessionURL:    "/browser-1/?access_token=secret",
			LaunchContext: &LaunchContext{Type: "url", Value: f.launchBody.URL},
		}
		f.sessions = append(f.sessions, session)
		f.writeEncrypted(writer, http.StatusOK, LaunchResponse{SessionID: session.SessionID, SessionURL: session.SessionURL})
	case request.Method == http.MethodGet && request.URL.Path == "/api/homedirs":
		f.writeEncrypted(writer, http.StatusOK, HomeDirectories{HomeDirs: f.homes})
	case request.Method == http.MethodPost && request.URL.Path == "/api/homedirs":
		var body struct {
			HomeName string `json:"home_name"`
		}
		_ = json.Unmarshal(plain, &body)
		f.homes = append(f.homes, body.HomeName)
		f.writeEncrypted(writer, http.StatusCreated, map[string]string{"status": "success", "home_name": body.HomeName})
	case request.Method == http.MethodDelete && strings.HasPrefix(request.URL.Path, "/api/sessions/"):
		writer.WriteHeader(http.StatusNoContent)
	default:
		f.writeEncrypted(writer, http.StatusNotFound, map[string]string{"detail": "not found"})
	}
}

func (f *fakeSealSkinServer) writeEncrypted(writer http.ResponseWriter, status int, value any) {
	plain, _ := json.Marshal(value)
	envelope, _ := encrypt(f.sessionKey, plain)
	writeJSON(writer, status, envelope)
}

func TestClientMatchesSealSkinProtocol(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	fake := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey}
	server := httptest.NewServer(fake)
	defer server.Close()
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, server.Client())

	ctx := context.Background()
	homes, err := client.ListHomeDirectories(ctx)
	if err != nil || len(homes) != 0 {
		t.Fatalf("initial homes=%v err=%v", homes, err)
	}
	if err := client.CreateHomeDirectory(ctx, "personal", "home-operation"); err != nil {
		t.Fatal(err)
	}
	homes, err = client.ListHomeDirectories(ctx)
	if err != nil || len(homes) != 1 || homes[0] != "personal" {
		t.Fatalf("homes=%v err=%v", homes, err)
	}
	launch, err := client.LaunchURL(ctx, LaunchURLRequest{
		URL: "https://adapter.example/bootstrap/personal/op", ApplicationID: "firefox",
		HomeName: "personal", WaylandMode: true,
		ProfileID: "personal", OperationID: strings.Repeat("a", 32),
	}, "launch-operation")
	if err != nil {
		t.Fatal(err)
	}
	if launch.SessionID != "browser-1" {
		t.Fatalf("launch=%+v", launch)
	}
	sessions, err := client.ListSessions(ctx)
	if err != nil || len(sessions) != 1 || sessions[0].LaunchContext.Value != "https://adapter.example/bootstrap/personal/op" {
		t.Fatalf("sessions=%+v err=%v", sessions, err)
	}
	if err := client.StopSession(ctx, "browser-1", "stop-operation"); err != nil {
		t.Fatal(err)
	}

	fake.mu.Lock()
	defer fake.mu.Unlock()
	if fake.launchBody.HomeName != "personal" || fake.launchIdempotency != "launch-operation" ||
		fake.launchBody.ProfileID != "personal" || fake.launchBody.OperationID != strings.Repeat("a", 32) {
		t.Fatalf("launch request=%+v idempotency=%q", fake.launchBody, fake.launchIdempotency)
	}
}

func TestInstallAppPreservesDefinitionAndRejectsDuplicate(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	fake := &fakeSealSkinServer{
		serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey,
		installedApps: []map[string]any{{"id": "firefox-personal"}},
	}
	server := httptest.NewServer(fake)
	defer server.Close()
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, server.Client())
	definition := map[string]any{
		"id": "camoufox-personal-r3", "source": "SealSkin Apps", "auto_update": false,
		"provider_config": map[string]any{
			"image":                       "sha256:" + strings.Repeat("a", 64),
			"custom_autostart_script_b64": "ZXhlYyAvdGVzdAo=",
			"docker_overrides": map[string]any{"mounts": []any{
				map[string]any{"Type": "bind", "Source": "/artifacts/frozen.json", "Target": "/run/environment.json", "ReadOnly": true},
			}},
		},
	}
	if err := client.InstallApp(context.Background(), definition, ""); err == nil {
		t.Fatal("installation without an idempotency key was accepted")
	}
	if err := client.InstallApp(context.Background(), definition, "install-camoufox-r3"); err != nil {
		t.Fatal(err)
	}
	err := client.InstallApp(context.Background(), definition, "duplicate-camoufox-r3")
	var apiErr *APIError
	if !errors.As(err, &apiErr) || apiErr.StatusCode != http.StatusConflict {
		t.Fatalf("expected duplicate conflict, got %v", err)
	}
	apps, err := client.ListInstalledApps(context.Background())
	if err != nil || len(apps) != 2 || apps[0].ID != "firefox-personal" {
		t.Fatalf("installed app identities changed: %v", err)
	}
	wanted, _ := json.Marshal(definition)
	fake.mu.Lock()
	defer fake.mu.Unlock()
	actual, _ := json.Marshal(fake.installedApps[1])
	if string(actual) != string(wanted) || fake.installKey != "install-camoufox-r3" {
		t.Fatal("encrypted installation did not preserve the full definition or idempotency key")
	}
}

func TestAdminClientDeletesApplicationAndArchivesHome(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	fake := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey}
	server := httptest.NewServer(fake)
	defer server.Close()
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, server.Client())
	if err := client.DeleteInstalledApp(context.Background(), "app-personal", ""); err == nil {
		t.Fatal("application deletion without idempotency was accepted")
	}
	if err := client.DeleteInstalledApp(context.Background(), "app-personal", "delete-app-1"); err != nil {
		t.Fatal(err)
	}
	if err := client.ArchiveHomeDirectory(context.Background(), "personal", ArchiveHomeRequest{ArchiveName: "archive-personal-1", ProfileID: "personal", ProfileRevision: 2, ApplicationID: "app-personal", EnvironmentArtifactID: "env-r9", Actor: "root"}, "archive-home-1"); err != nil {
		t.Fatal(err)
	}
	fake.mu.Lock()
	defer fake.mu.Unlock()
	if fake.deletedApp != "app-personal" || fake.deleteAppKey != "delete-app-1" || fake.archiveHome != "personal" || fake.archiveName != "archive-personal-1" || fake.archiveKey != "archive-home-1" {
		t.Fatalf("admin mutations: app=%q appKey=%q home=%q archive=%q archiveKey=%q", fake.deletedApp, fake.deleteAppKey, fake.archiveHome, fake.archiveName, fake.archiveKey)
	}
}

func TestAdminClientManagesProxyDrafts(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	fake := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey, probeResult: ProxyProbeResult{Status: "failed", Code: "PROXY_AUTH_REJECTED", UpstreamIP: "203.0.113.9"}}
	server := httptest.NewServer(fake)
	defer server.Close()
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, server.Client())
	grant := SecretGrant{Owner: "profile-adapter", Profile: "browser-a", Home: "browser-a-home", App: "app-a"}
	if _, err := client.ImportProxySecret(context.Background(), ProxySecretImportRequest{SecretID: "proxy-browser-a", SecretVersion: 2, Grants: []SecretGrant{grant}, Username: "u", Password: "p"}, ""); err == nil {
		t.Fatal("import without idempotency was accepted")
	}
	if _, err := client.ImportProxySecret(context.Background(), ProxySecretImportRequest{SecretID: "../x", SecretVersion: 2, Grants: []SecretGrant{grant}, Username: "u", Password: "p"}, "import-1"); err == nil {
		t.Fatal("invalid secret ID was accepted")
	}
	refs, err := client.ImportProxySecret(context.Background(), ProxySecretImportRequest{SecretID: "proxy-browser-a", SecretVersion: 2, Grants: []SecretGrant{grant}, Username: "u", Password: "p"}, "import-1")
	if err != nil || refs != (ProxySecretRefs{UsernameSecretRef: "secret://proxy-browser-a/username/2", PasswordSecretRef: "secret://proxy-browser-a/password/2"}) {
		t.Fatalf("import: %+v %v", refs, err)
	}
	result, err := client.ProbeProxyDraft(context.Background(), ProxyProbeRequest{UpstreamHost: "proxy.example", UpstreamPort: 1080, UpstreamProtocol: "socks5", UpstreamAuth: "username_password",
		UsernameSecretRef: refs.UsernameSecretRef, PasswordSecretRef: refs.PasswordSecretRef, Grant: &grant, ProbeURL: "https://probe.example/", ProbeTimeoutSeconds: 10})
	if err != nil || result.Status != "failed" || result.Code != "PROXY_AUTH_REJECTED" {
		t.Fatalf("probe: %+v %v", result, err)
	}
	fake.mu.Lock()
	fake.probeResult = ProxyProbeResult{Status: "weird", Code: "X"}
	fake.mu.Unlock()
	if _, err := client.ProbeProxyDraft(context.Background(), ProxyProbeRequest{UpstreamHost: "proxy.example", UpstreamPort: 1080, UpstreamProtocol: "socks5", UpstreamAuth: "none", ProbeURL: "https://probe.example/", ProbeTimeoutSeconds: 10}); err == nil {
		t.Fatal("invalid probe status was accepted")
	}
	appended, err := client.AppendNetworkPolicy(context.Background(), NetworkPolicyAppendRequest{PolicyID: "browser-a-proxy-r2", Policy: map[string]any{"mode": "proxy_required"}}, "policy-1")
	if err != nil || appended.PolicyID != "browser-a-proxy-r2" || !ValidNetworkPolicyReference(appended.PolicyID, appended.PolicySHA256) || !appended.Created {
		t.Fatalf("append: %+v %v", appended, err)
	}
	if _, err := client.RevokeProfileSecret(context.Background(), refs.PasswordSecretRef, "not-hex"); err == nil {
		t.Fatal("revocation without a hex operation ID was accepted")
	}
	revoked, err := client.RevokeProfileSecret(context.Background(), refs.PasswordSecretRef, strings.Repeat("ab", 16))
	if err != nil || !revoked.Revoked || !revoked.CleanupComplete {
		t.Fatalf("revoke: %+v %v", revoked, err)
	}
	fake.mu.Lock()
	defer fake.mu.Unlock()
	if fake.secretImport.Password != "p" || fake.secretImportKey != "import-1" || fake.probeRequest.Grant == nil || fake.probeRequest.Grant.Home != "browser-a-home" ||
		fake.policyAppendKey != "policy-1" || fake.revokeBody.SecretRef != refs.PasswordSecretRef || fake.revokeKey != strings.Repeat("ab", 16) {
		t.Fatalf("recorded admin calls: import=%+v key=%q probe=%+v policyKey=%q revoke=%+v revokeKey=%q", fake.secretImport, fake.secretImportKey, fake.probeRequest, fake.policyAppendKey, fake.revokeBody, fake.revokeKey)
	}
	for _, reference := range []string{"secret://a/username/1", "secret://a-b_c/password/999999999"} {
		field := "username"
		if strings.Contains(reference, "/password/") {
			field = "password"
		}
		if !ValidSecretReference(reference, field) {
			t.Fatalf("valid reference rejected: %s", reference)
		}
	}
	for _, reference := range []string{"secret://a/username/0", "secret://a/username/01", "secret://a/password/1", "secret://a/username/1/x", "https://a/username/1", "secret://a b/username/1", "secret://a/username/1234567890"} {
		if ValidSecretReference(reference, "username") {
			t.Fatalf("invalid reference accepted: %s", reference)
		}
	}
}

func TestClientRejectsTamperedServerSignature(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	fake := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey, tamperSignature: true}
	server := httptest.NewServer(fake)
	defer server.Close()
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, server.Client())
	if _, err := client.ListSessions(context.Background()); err == nil || !strings.Contains(err.Error(), "signature verification failed") {
		t.Fatalf("error=%v", err)
	}
}

func TestClientRehandshakesAfterExplicitExpiredSession(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	fake := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey, expireListOnce: true}
	server := httptest.NewServer(fake)
	defer server.Close()
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, server.Client())
	if _, err := client.ListSessions(context.Background()); err != nil {
		t.Fatal(err)
	}
	fake.mu.Lock()
	defer fake.mu.Unlock()
	if fake.handshakes != 2 {
		t.Fatalf("handshakes=%d, want 2", fake.handshakes)
	}
}

func TestClientClassifiesMutationTransportFailureAsAmbiguous(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	fake := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey}
	server := httptest.NewServer(fake)
	defer server.Close()
	httpClient := server.Client()
	httpClient.Transport = failPathTransport{base: httpClient.Transport, path: "/api/launch/url"}
	client := newTestClient(t, server.URL, serverPrivate, clientPrivate, httpClient)
	_, err := client.LaunchURL(context.Background(), LaunchURLRequest{
		URL: "https://adapter.example/bootstrap/personal/op", ApplicationID: "firefox", HomeName: "personal",
	}, "launch-operation")
	var ambiguous *AmbiguousMutationError
	if !errors.As(err, &ambiguous) {
		t.Fatalf("error=%T %v, want AmbiguousMutationError", err, err)
	}
}

func TestResolveSessionURLPinsOriginAndAddsEmbedded(t *testing.T) {
	resolved, err := ResolveSessionURL("https://sessions.example", "/id/?access_token=secret", true)
	if err != nil {
		t.Fatal(err)
	}
	if resolved != "https://sessions.example/id/?access_token=secret&embedded=true" {
		t.Fatalf("resolved=%q", resolved)
	}
	if _, err := ResolveSessionURL("https://sessions.example", "https://attacker.example/id", false); err == nil {
		t.Fatal("expected cross-origin session URL rejection")
	}
}

type failPathTransport struct {
	base http.RoundTripper
	path string
}

func (f failPathTransport) RoundTrip(request *http.Request) (*http.Response, error) {
	if request.URL.Path == f.path {
		return nil, errors.New("simulated connection reset")
	}
	return f.base.RoundTrip(request)
}

func newTestClient(t *testing.T, baseURL string, serverPrivate, clientPrivate *rsa.PrivateKey, httpClient *http.Client) *Client {
	t.Helper()
	serverDER, _ := x509.MarshalPKIXPublicKey(&serverPrivate.PublicKey)
	clientDER, _ := x509.MarshalPKCS8PrivateKey(clientPrivate)
	client, err := NewClient(Config{
		BaseURL: baseURL, Username: "tester", HTTPClient: httpClient, AllowUnencryptedHTTP: true,
		ServerPublicKeyPEM:  pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: serverDER}),
		ClientPrivateKeyPEM: pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: clientDER}),
		Now:                 func() time.Time { return time.Unix(2_000_000_000, 0) },
	})
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func testKeys(t *testing.T) (*rsa.PrivateKey, *rsa.PrivateKey) {
	t.Helper()
	serverPrivate, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	clientPrivate, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	return serverPrivate, clientPrivate
}

func verifyTestJWT(header string, public *rsa.PublicKey) error {
	if !strings.HasPrefix(header, "Bearer ") {
		return errors.New("missing bearer token")
	}
	parts := strings.Split(strings.TrimPrefix(header, "Bearer "), ".")
	if len(parts) != 3 {
		return errors.New("invalid JWT")
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return err
	}
	digest := sha256.Sum256([]byte(parts[0] + "." + parts[1]))
	if err := rsa.VerifyPKCS1v15(public, crypto.SHA256, digest[:], signature); err != nil {
		return err
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return err
	}
	var claims struct {
		Subject string `json:"sub"`
		Expiry  int64  `json:"exp"`
	}
	if err := json.Unmarshal(payload, &claims); err != nil {
		return err
	}
	if claims.Subject != "tester" || claims.Expiry != 2_000_000_300 {
		return errors.New("unexpected JWT claims")
	}
	return nil
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(value)
}

func TestObserveHomeIsReadOnlyAndValidated(t *testing.T) {
	serverPrivate, clientPrivate := testKeys(t)
	server := &fakeSealSkinServer{serverPrivate: serverPrivate, clientPublic: &clientPrivate.PublicKey}
	httpServer := httptest.NewServer(server)
	defer httpServer.Close()
	client := newTestClient(t, httpServer.URL, serverPrivate, clientPrivate, httpServer.Client())
	server.mu.Lock()
	server.health = map[string]any{"version": 1, "home_name": "personal", "observed_at": 1.0,
		"runtime": map[string]any{"version": 1, "home_name": "personal", "records": []any{}, "workers": []any{},
			"network_runtime_version": 1, "network_enforcement_version": 1, "resources": []any{}},
		"workers": []any{}, "network": nil}
	server.mu.Unlock()
	health, err := client.ObserveHome(context.Background(), "personal", false)
	if err != nil || health.HomeName != "personal" || health.Network != nil || len(health.Workers) != 0 {
		t.Fatalf("health=%+v err=%v", health, err)
	}
	if _, err := client.ObserveHome(context.Background(), "personal", true); err != nil {
		t.Fatal(err)
	}
	server.mu.Lock()
	queries := append([]string(nil), server.healthQueries...)
	server.health = map[string]any{"version": 2, "home_name": "personal", "runtime": map[string]any{"version": 1, "home_name": "personal", "records": []any{}, "workers": []any{}}, "workers": []any{}}
	server.mu.Unlock()
	if len(queries) != 2 || queries[0] != "" || queries[1] != "upstream=true" {
		t.Fatalf("queries=%v", queries)
	}
	if _, err := client.ObserveHome(context.Background(), "personal", false); err == nil {
		t.Fatal("unsupported health version accepted")
	}
	if _, err := client.ObserveHome(context.Background(), "../personal", false); err == nil {
		t.Fatal("invalid Home name accepted")
	}
	server.mu.Lock()
	server.health = map[string]any{"version": 1, "home_name": "other", "runtime": map[string]any{"version": 1, "home_name": "other", "records": []any{}, "workers": []any{}}, "workers": []any{}}
	server.mu.Unlock()
	if _, err := client.ObserveHome(context.Background(), "personal", false); err == nil {
		t.Fatal("home mismatch accepted")
	}
}
