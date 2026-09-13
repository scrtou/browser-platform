package sealskin

import (
	"bytes"
	"context"
	"crypto"
	"crypto/aes"
	"crypto/cipher"
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
	"net/url"
	"strings"
	"sync"
	"time"
)

const maxResponseBytes = 2 << 20

type Config struct {
	BaseURL              string
	Username             string
	ServerPublicKeyPEM   []byte
	ClientPrivateKeyPEM  []byte
	HTTPClient           *http.Client
	AllowUnencryptedHTTP bool
	Now                  func() time.Time
}

// Client implements SealSkin's signed-handshake and AES-256-GCM API protocol.
// Requests are serialized so a session reset cannot race with an in-flight
// request using the old key.
type Client struct {
	baseURL       *url.URL
	username      string
	serverPublic  *rsa.PublicKey
	clientPrivate *rsa.PrivateKey
	httpClient    *http.Client
	now           func() time.Time

	mu         sync.Mutex
	sessionID  string
	sessionKey []byte
}

type encryptedPayload struct {
	IV         string `json:"iv"`
	Ciphertext string `json:"ciphertext"`
}

func NewClient(cfg Config) (*Client, error) {
	base, err := url.Parse(cfg.BaseURL)
	if err != nil || base.Scheme == "" || base.Host == "" {
		return nil, fmt.Errorf("invalid SealSkin base URL %q", cfg.BaseURL)
	}
	if base.Scheme != "https" && !(cfg.AllowUnencryptedHTTP && base.Scheme == "http") {
		return nil, errors.New("SealSkin base URL must use HTTPS (set allow_unencrypted_http only for an isolated PoC)")
	}
	if base.RawQuery != "" || base.Fragment != "" {
		return nil, errors.New("SealSkin base URL must not contain a query or fragment")
	}
	if base.User != nil {
		return nil, errors.New("SealSkin base URL must not contain user credentials")
	}
	base.Path = strings.TrimRight(base.Path, "/")

	serverPublic, err := parseRSAPublicKey(cfg.ServerPublicKeyPEM)
	if err != nil {
		return nil, fmt.Errorf("parse SealSkin server public key: %w", err)
	}
	clientPrivate, err := parseRSAPrivateKey(cfg.ClientPrivateKeyPEM)
	if err != nil {
		return nil, fmt.Errorf("parse SealSkin client private key: %w", err)
	}
	if serverPublic.N.BitLen() < 2048 || clientPrivate.N.BitLen() < 2048 {
		return nil, errors.New("SealSkin RSA keys must be at least 2048 bits")
	}
	if strings.TrimSpace(cfg.Username) == "" {
		return nil, errors.New("SealSkin username is required")
	}
	httpClient := cfg.HTTPClient
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 45 * time.Second}
	}
	now := cfg.Now
	if now == nil {
		now = time.Now
	}
	return &Client{
		baseURL: base, username: cfg.Username, serverPublic: serverPublic,
		clientPrivate: clientPrivate, httpClient: httpClient, now: now,
	}, nil
}

func (c *Client) ListSessions(ctx context.Context) ([]Session, error) {
	var sessions []Session
	if err := c.secure(ctx, http.MethodGet, "/api/sessions", nil, "", &sessions); err != nil {
		return nil, err
	}
	return sessions, nil
}

func (c *Client) LaunchURL(ctx context.Context, req LaunchURLRequest, idempotencyKey string) (LaunchResponse, error) {
	var response LaunchResponse
	if strings.TrimSpace(idempotencyKey) == "" {
		return response, errors.New("launch requires a durable idempotency key")
	}
	err := c.secure(ctx, http.MethodPost, "/api/launch/url", req, idempotencyKey, &response)
	return response, err
}

func (c *Client) StopSession(ctx context.Context, sessionID, idempotencyKey string) error {
	if strings.TrimSpace(idempotencyKey) == "" {
		return errors.New("stop requires a durable idempotency key")
	}
	if strings.Contains(sessionID, "/") || strings.TrimSpace(sessionID) == "" {
		return errors.New("invalid SealSkin session ID")
	}
	return c.secure(ctx, http.MethodDelete, "/api/sessions/"+url.PathEscape(sessionID), nil, idempotencyKey, nil)
}

func (c *Client) ListHomeDirectories(ctx context.Context) ([]string, error) {
	var response HomeDirectories
	if err := c.secure(ctx, http.MethodGet, "/api/homedirs", nil, "", &response); err != nil {
		return nil, err
	}
	return response.HomeDirs, nil
}

func (c *Client) CreateHomeDirectory(ctx context.Context, homeName, idempotencyKey string) error {
	if strings.TrimSpace(idempotencyKey) == "" {
		return errors.New("home creation requires a durable idempotency key")
	}
	body := struct {
		HomeName string `json:"home_name"`
	}{HomeName: homeName}
	return c.secure(ctx, http.MethodPost, "/api/homedirs", body, idempotencyKey, nil)
}

func (c *Client) CreateUser(ctx context.Context, request CreateUserRequest, idempotencyKey string) (CreateUserResponse, error) {
	var response CreateUserResponse
	if strings.TrimSpace(idempotencyKey) == "" {
		return response, errors.New("user creation requires a durable idempotency key")
	}
	err := c.secure(ctx, http.MethodPost, "/api/admin/users", request, idempotencyKey, &response)
	return response, err
}

func (c *Client) ListInstalledApps(ctx context.Context) ([]InstalledApp, error) {
	var apps []InstalledApp
	if err := c.secure(ctx, http.MethodGet, "/api/admin/apps/installed", nil, "", &apps); err != nil {
		return nil, err
	}
	return apps, nil
}

// InstallApp creates a separate administrator-owned application definition.
// The full upstream definition is retained; InstalledApp only models the
// fields needed when inspecting or partially updating existing applications.
func (c *Client) InstallApp(ctx context.Context, definition map[string]any, idempotencyKey string) error {
	appID, _ := definition["id"].(string)
	if strings.TrimSpace(appID) == "" || strings.Contains(appID, "/") {
		return errors.New("invalid SealSkin application ID")
	}
	if strings.TrimSpace(idempotencyKey) == "" {
		return errors.New("application installation requires a durable idempotency key")
	}
	var response InstalledApp
	return c.secure(ctx, http.MethodPost, "/api/admin/apps/installed", definition, idempotencyKey, &response)
}

// PatchInstalledApp applies an administrator-owned partial app update. It is
// intentionally kept out of the long-running Profile adapter workflow; local
// provisioning commands use it with the one-time administrator key.
func (c *Client) PatchInstalledApp(ctx context.Context, appID string, patch map[string]any, idempotencyKey string) error {
	appID = strings.TrimSpace(appID)
	if appID == "" || strings.Contains(appID, "/") {
		return errors.New("invalid SealSkin application ID")
	}
	if len(patch) == 0 {
		return errors.New("application patch must not be empty")
	}
	if strings.TrimSpace(idempotencyKey) == "" {
		return errors.New("application patch requires a durable idempotency key")
	}
	var response map[string]any
	return c.secure(
		ctx,
		http.MethodPatch,
		"/api/admin/apps/installed/"+url.PathEscape(appID),
		patch,
		idempotencyKey,
		&response,
	)
}

func (c *Client) secure(ctx context.Context, method, path string, body any, idempotencyKey string, out any) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	for attempt := 0; attempt < 2; attempt++ {
		if c.sessionID == "" {
			if err := c.handshakeLocked(ctx); err != nil {
				return err
			}
		}
		err, sessionInvalid := c.secureAttemptLocked(ctx, method, path, body, idempotencyKey, out)
		if !sessionInvalid || attempt == 1 {
			return err
		}
		c.sessionID = ""
		clear(c.sessionKey)
		c.sessionKey = nil
	}
	return errors.New("unreachable SealSkin retry state")
}

func (c *Client) secureAttemptLocked(ctx context.Context, method, path string, body any, idempotencyKey string, out any) (error, bool) {
	var requestBody io.Reader
	if body != nil {
		plain, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("encode SealSkin request: %w", err), false
		}
		envelope, err := encrypt(c.sessionKey, plain)
		if err != nil {
			return err, false
		}
		encoded, err := json.Marshal(envelope)
		if err != nil {
			return err, false
		}
		requestBody = bytes.NewReader(encoded)
	}

	req, err := http.NewRequestWithContext(ctx, method, c.endpoint(path), requestBody)
	if err != nil {
		return err, false
	}
	token, err := c.jwt()
	if err != nil {
		return err, false
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("X-Session-ID", c.sessionID)
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if method != http.MethodGet {
		if strings.TrimSpace(idempotencyKey) == "" {
			return errors.New("mutating SealSkin request requires an idempotency key"), false
		}
		req.Header.Set("X-Idempotency-Key", idempotencyKey)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		if method != http.MethodGet {
			return &AmbiguousMutationError{Operation: method + " " + path, Cause: err}, false
		}
		return fmt.Errorf("call SealSkin: %w", err), false
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, maxResponseBytes+1))
	if err != nil {
		if method != http.MethodGet {
			return &AmbiguousMutationError{Operation: method + " " + path, Cause: err}, false
		}
		return fmt.Errorf("read SealSkin response: %w", err), false
	}
	if len(raw) > maxResponseBytes {
		return errors.New("SealSkin response exceeds 2 MiB"), false
	}
	if resp.StatusCode == http.StatusNoContent || len(raw) == 0 {
		if resp.StatusCode >= 200 && resp.StatusCode < 300 {
			return nil, false
		}
		return &APIError{StatusCode: resp.StatusCode}, false
	}

	plain, encrypted, err := c.decodeResponseLocked(raw)
	if err != nil {
		return fmt.Errorf("decode SealSkin response: %w", err), false
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		detail := responseDetail(plain)
		apiErr := &APIError{StatusCode: resp.StatusCode, Detail: detail}
		invalid := resp.StatusCode == http.StatusBadRequest && isCryptoSessionError(detail)
		if !encrypted && resp.StatusCode == http.StatusBadRequest && strings.Contains(detail, "Secure session required") {
			invalid = true
		}
		return apiErr, invalid
	}
	if !encrypted {
		return errors.New("SealSkin returned an unencrypted success response"), false
	}
	if out == nil {
		return nil, false
	}
	if err := json.Unmarshal(plain, out); err != nil {
		return fmt.Errorf("decode SealSkin JSON: %w", err), false
	}
	return nil, false
}

func (c *Client) handshakeLocked(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpoint("/api/handshake/initiate"), nil)
	if err != nil {
		return err
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("initiate SealSkin handshake: %w", err)
	}
	var init struct {
		Nonce     string `json:"nonce"`
		Signature string `json:"signature"`
	}
	if err := decodePlainResponse(resp, &init); err != nil {
		return fmt.Errorf("initiate SealSkin handshake: %w", err)
	}
	nonce, err := base64.StdEncoding.DecodeString(init.Nonce)
	if err != nil {
		return errors.New("SealSkin handshake returned an invalid nonce")
	}
	signature, err := base64.StdEncoding.DecodeString(init.Signature)
	if err != nil {
		return errors.New("SealSkin handshake returned an invalid signature")
	}
	digest := sha256.Sum256(nonce)
	if err := rsa.VerifyPSS(c.serverPublic, crypto.SHA256, digest[:], signature, &rsa.PSSOptions{SaltLength: 32, Hash: crypto.SHA256}); err != nil {
		return errors.New("SealSkin server signature verification failed")
	}

	key := make([]byte, 32)
	if _, err := rand.Read(key); err != nil {
		return fmt.Errorf("generate SealSkin session key: %w", err)
	}
	wrapped, err := rsa.EncryptOAEP(sha256.New(), rand.Reader, c.serverPublic, key, nil)
	if err != nil {
		clear(key)
		return fmt.Errorf("wrap SealSkin session key: %w", err)
	}
	exchangeBody, err := json.Marshal(map[string]string{"encrypted_session_key": base64.StdEncoding.EncodeToString(wrapped)})
	if err != nil {
		clear(key)
		return err
	}
	exchangeReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.endpoint("/api/handshake/exchange"), bytes.NewReader(exchangeBody))
	if err != nil {
		clear(key)
		return err
	}
	exchangeReq.Header.Set("Content-Type", "application/json")
	exchangeResp, err := c.httpClient.Do(exchangeReq)
	if err != nil {
		clear(key)
		return fmt.Errorf("exchange SealSkin session key: %w", err)
	}
	var exchange struct {
		SessionID string `json:"session_id"`
	}
	if err := decodePlainResponse(exchangeResp, &exchange); err != nil {
		clear(key)
		return fmt.Errorf("exchange SealSkin session key: %w", err)
	}
	if strings.TrimSpace(exchange.SessionID) == "" {
		clear(key)
		return errors.New("SealSkin handshake returned an empty session ID")
	}
	c.sessionID = exchange.SessionID
	c.sessionKey = key
	return nil
}

func (c *Client) decodeResponseLocked(raw []byte) ([]byte, bool, error) {
	var envelope encryptedPayload
	if err := json.Unmarshal(raw, &envelope); err == nil && envelope.IV != "" && envelope.Ciphertext != "" {
		plain, err := decrypt(c.sessionKey, envelope)
		return plain, true, err
	}
	return raw, false, nil
}

func (c *Client) jwt() (string, error) {
	now := c.now().Unix()
	header, _ := json.Marshal(map[string]string{"alg": "RS256", "typ": "JWT"})
	payload, _ := json.Marshal(map[string]any{"iat": now, "exp": now + 300, "sub": c.username})
	encode := base64.RawURLEncoding.EncodeToString
	signingInput := encode(header) + "." + encode(payload)
	digest := sha256.Sum256([]byte(signingInput))
	signature, err := rsa.SignPKCS1v15(rand.Reader, c.clientPrivate, crypto.SHA256, digest[:])
	if err != nil {
		return "", fmt.Errorf("sign SealSkin JWT: %w", err)
	}
	return signingInput + "." + encode(signature), nil
}

func (c *Client) endpoint(path string) string {
	return strings.TrimRight(c.baseURL.String(), "/") + path
}

func encrypt(key, plain []byte) (encryptedPayload, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return encryptedPayload{}, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return encryptedPayload{}, err
	}
	iv := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(iv); err != nil {
		return encryptedPayload{}, err
	}
	ciphertext := gcm.Seal(nil, iv, plain, nil)
	return encryptedPayload{IV: base64.StdEncoding.EncodeToString(iv), Ciphertext: base64.StdEncoding.EncodeToString(ciphertext)}, nil
}

func decrypt(key []byte, envelope encryptedPayload) ([]byte, error) {
	iv, err := base64.StdEncoding.DecodeString(envelope.IV)
	if err != nil {
		return nil, err
	}
	ciphertext, err := base64.StdEncoding.DecodeString(envelope.Ciphertext)
	if err != nil {
		return nil, err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	return gcm.Open(nil, iv, ciphertext, nil)
}

func decodePlainResponse(resp *http.Response, out any) error {
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, maxResponseBytes+1))
	if err != nil {
		return err
	}
	if len(raw) > maxResponseBytes {
		return errors.New("response exceeds 2 MiB")
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return &APIError{StatusCode: resp.StatusCode, Detail: responseDetail(raw)}
	}
	if err := json.Unmarshal(raw, out); err != nil {
		return err
	}
	return nil
}

func responseDetail(raw []byte) string {
	var body struct {
		Detail any `json:"detail"`
	}
	if json.Unmarshal(raw, &body) == nil && body.Detail != nil {
		switch detail := body.Detail.(type) {
		case string:
			return detail
		default:
			encoded, _ := json.Marshal(detail)
			return string(encoded)
		}
	}
	text := strings.TrimSpace(string(raw))
	if len(text) > 512 {
		text = text[:512]
	}
	return text
}

func isCryptoSessionError(detail string) bool {
	return strings.Contains(detail, "Invalid or missing session ID") ||
		strings.Contains(detail, "Failed to decrypt request") ||
		strings.Contains(detail, "Secure session required")
}

func parseRSAPublicKey(data []byte) (*rsa.PublicKey, error) {
	block, _ := pem.Decode(data)
	if block == nil {
		return nil, errors.New("PEM block not found")
	}
	if parsed, err := x509.ParsePKIXPublicKey(block.Bytes); err == nil {
		key, ok := parsed.(*rsa.PublicKey)
		if !ok {
			return nil, errors.New("public key is not RSA")
		}
		return key, nil
	}
	return x509.ParsePKCS1PublicKey(block.Bytes)
}

func parseRSAPrivateKey(data []byte) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode(data)
	if block == nil {
		return nil, errors.New("PEM block not found")
	}
	if parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes); err == nil {
		key, ok := parsed.(*rsa.PrivateKey)
		if !ok {
			return nil, errors.New("private key is not RSA")
		}
		return key, key.Validate()
	}
	key, err := x509.ParsePKCS1PrivateKey(block.Bytes)
	if err != nil {
		return nil, err
	}
	return key, key.Validate()
}

// ResolveSessionURL converts SealSkin's relative, token-bearing session URL
// into a public URL and refuses an origin switch supplied by the API.
func ResolveSessionURL(publicBase, sessionURL string, embedded bool) (string, error) {
	base, err := url.Parse(publicBase)
	if err != nil || base.Scheme != "https" || base.Host == "" {
		return "", errors.New("SealSkin public session base URL must be absolute HTTPS")
	}
	if base.User != nil {
		return "", errors.New("SealSkin public session base URL must not contain user credentials")
	}
	if base.Path != "" && base.Path != "/" {
		return "", errors.New("SealSkin public session base URL must be an HTTPS origin without a path")
	}
	rel, err := url.Parse(sessionURL)
	if err != nil {
		return "", errors.New("SealSkin returned an invalid session URL")
	}
	resolved := base.ResolveReference(rel)
	if resolved.Scheme != base.Scheme || resolved.Host != base.Host {
		return "", errors.New("SealSkin session URL changed origin")
	}
	if embedded {
		query := resolved.Query()
		query.Set("embedded", "true")
		resolved.RawQuery = query.Encode()
	}
	return resolved.String(), nil
}
