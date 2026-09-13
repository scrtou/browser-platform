package sealskin

import (
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/base64"
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
	runtime           any
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
