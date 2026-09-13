// Command sealskin-install-app installs a separate application from a reviewed
// JSON definition. Existing application IDs are never overwritten.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"strings"
	"time"

	"browser-platform/adapter/internal/sealskin"
)

func main() {
	adminPath := flag.String("admin-config", "", "path to SealSkin admin.json")
	apiBaseURL := flag.String("api-base-url", "", "reachable SealSkin API base URL")
	definitionPath := flag.String("definition", "", "path to the complete installed-app JSON definition")
	flag.Parse()
	if err := run(*adminPath, *apiBaseURL, *definitionPath); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(adminPath, apiBaseURL, definitionPath string) error {
	if adminPath == "" || apiBaseURL == "" || definitionPath == "" {
		return errors.New("admin-config, api-base-url and definition are required")
	}
	raw, err := os.ReadFile(definitionPath)
	if err != nil {
		return errors.New("read application definition")
	}
	var definition map[string]any
	if err := json.Unmarshal(raw, &definition); err != nil {
		return errors.New("invalid application JSON")
	}
	appID, _ := definition["id"].(string)
	if strings.TrimSpace(appID) == "" || strings.Contains(appID, "/") {
		return errors.New("invalid application ID")
	}
	info, err := os.Stat(adminPath)
	if err != nil {
		return errors.New("inspect admin config")
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
		return errors.New("admin config must be a regular file unreadable by group and others")
	}
	raw, err = os.ReadFile(adminPath)
	if err != nil {
		return errors.New("read admin config")
	}
	defer clear(raw)
	var admin struct {
		Username        string `json:"username"`
		PrivateKey      string `json:"private_key"`
		ServerPublicKey string `json:"server_public_key"`
	}
	if err := json.Unmarshal(raw, &admin); err != nil {
		return errors.New("invalid admin config")
	}
	privateKey := []byte(admin.PrivateKey)
	defer clear(privateKey)
	client, err := sealskin.NewClient(sealskin.Config{
		BaseURL: apiBaseURL, Username: admin.Username,
		ServerPublicKeyPEM: []byte(admin.ServerPublicKey), ClientPrivateKeyPEM: privateKey,
		AllowUnencryptedHTTP: strings.HasPrefix(apiBaseURL, "http://127.0.0.1:"),
	})
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
	defer cancel()
	apps, err := client.ListInstalledApps(ctx)
	if err != nil {
		return fmt.Errorf("list installed apps: %w", err)
	}
	for _, app := range apps {
		if app.ID == appID {
			return fmt.Errorf("application %q already exists; refusing to overwrite", appID)
		}
	}
	if err := client.InstallApp(ctx, definition, "install-app-"+appID); err != nil {
		return fmt.Errorf("install application: %w", err)
	}
	fmt.Printf("installed_application_id=%s\n", appID)
	return nil
}
