// Command sealskin-provision creates a least-privilege SealSkin user for the
// Profile adapter. It reads the one-time admin.json locally and never writes
// that administrator private key to adapter state or logs.
package main

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"browser-platform/adapter/internal/sealskin"
)

type adminConfig struct {
	ServerEndpoint  string `json:"server_endpoint"`
	APIPort         int    `json:"api_port"`
	Username        string `json:"username"`
	PrivateKey      string `json:"private_key"`
	ServerPublicKey string `json:"server_public_key"`
}

func main() {
	adminPath := flag.String("admin-config", "", "path to SealSkin admin.json")
	username := flag.String("username", "profile-adapter", "new SealSkin username")
	privatePath := flag.String("private-key", "./secrets/sealskin-client-private.pem", "where to save the generated client private key")
	flag.Parse()
	if err := provision(*adminPath, *username, *privatePath); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func provision(adminPath, username, privatePath string) error {
	if strings.TrimSpace(adminPath) == "" || strings.TrimSpace(username) == "" || strings.TrimSpace(privatePath) == "" {
		return errors.New("admin-config, username and private-key are required")
	}
	info, err := os.Stat(adminPath)
	if err != nil {
		return fmt.Errorf("inspect admin config: %w", err)
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
		return errors.New("admin config must be a regular file unreadable by group and others")
	}
	data, err := os.ReadFile(adminPath)
	if err != nil {
		return fmt.Errorf("read admin config: %w", err)
	}
	var admin adminConfig
	if err := json.Unmarshal(data, &admin); err != nil {
		return fmt.Errorf("decode admin config: %w", err)
	}
	if admin.APIPort == 0 {
		admin.APIPort = 8000
	}
	endpoint := admin.ServerEndpoint
	if !strings.Contains(endpoint, "://") {
		endpoint = "http://" + endpoint + ":" + strconv.Itoa(admin.APIPort)
	}
	adminPrivate, err := pemPrivate(admin.PrivateKey)
	if err != nil {
		return fmt.Errorf("parse admin private key: %w", err)
	}
	serverPublic := []byte(admin.ServerPublicKey)
	client, err := sealskin.NewClient(sealskin.Config{
		BaseURL: endpoint, Username: admin.Username,
		ServerPublicKeyPEM: serverPublic, ClientPrivateKeyPEM: pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: mustPKCS8(adminPrivate)}),
		AllowUnencryptedHTTP: true,
	})
	if err != nil {
		return err
	}
	clientPrivate, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		return fmt.Errorf("generate adapter key: %w", err)
	}
	publicDER, err := x509.MarshalPKIXPublicKey(&clientPrivate.PublicKey)
	if err != nil {
		return err
	}
	privateDER, err := x509.MarshalPKCS8PrivateKey(clientPrivate)
	if err != nil {
		return err
	}
	request := sealskin.CreateUserRequest{
		Username:  username,
		PublicKey: string(pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: publicDER})),
		Settings: sealskin.UserSettings{
			Active: true, Group: "none", PersistentStorage: true,
			PublicSharing: false, HardenContainer: true, HardenOpenbox: false,
			GPU: false, StorageLimit: -1, SessionLimit: 10,
		},
	}
	if _, err := client.CreateUser(context.Background(), request, "provision-"+username); err != nil {
		return fmt.Errorf("create SealSkin adapter user: %w", err)
	}
	if err := writePrivateKey(privatePath, privateDER); err != nil {
		return err
	}
	fmt.Printf("created SealSkin user %q; private key saved to %s\n", username, privatePath)
	return nil
}

func writePrivateKey(path string, der []byte) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("create private key directory: %w", err)
	}
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return fmt.Errorf("create private key file: %w", err)
	}
	defer file.Close()
	if _, err := file.Write(pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: der})); err != nil {
		return fmt.Errorf("write private key: %w", err)
	}
	if err := file.Sync(); err != nil {
		return fmt.Errorf("sync private key: %w", err)
	}
	return nil
}

func pemPrivate(value string) (*rsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(value))
	if block == nil {
		return nil, errors.New("private key PEM block missing")
	}
	parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, err
	}
	key, ok := parsed.(*rsa.PrivateKey)
	if !ok {
		return nil, errors.New("admin private key is not RSA")
	}
	return key, key.Validate()
}

func mustPKCS8(key *rsa.PrivateKey) []byte {
	value, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		panic(err)
	}
	return value
}
