// Command sealskin-configure-proxy-app binds an installed SealSkin app to a
// proxy-only Worker image and an internal per-Profile Docker network.
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

type adminConfig struct {
	ServerEndpoint  string `json:"server_endpoint"`
	APIPort         int    `json:"api_port"`
	Username        string `json:"username"`
	PrivateKey      string `json:"private_key"`
	ServerPublicKey string `json:"server_public_key"`
}

func main() {
	adminPath := flag.String("admin-config", "", "path to SealSkin admin.json")
	apiBaseURL := flag.String("api-base-url", "", "reachable SealSkin API base URL")
	appID := flag.String("app-id", "", "installed SealSkin application ID")
	image := flag.String("image", "", "local proxy Worker image reference")
	network := flag.String("network", "", "internal Profile Docker network")
	locale := flag.String("locale", "", "optional BCP 47 browser locale")
	languages := flag.String("languages", "", "optional comma-separated browser languages")
	environmentID := flag.String("environment-id", "", "optional immutable environment identifier")
	artifactSHA256 := flag.String("artifact-sha256", "", "optional environment artifact SHA-256")
	screenWidth := flag.Int("screen-width", 0, "optional fixed display width")
	screenHeight := flag.Int("screen-height", 0, "optional fixed display height")
	flag.Parse()
	if err := configure(
		*adminPath, *apiBaseURL, *appID, *image, *network,
		*locale, *languages, *environmentID, *artifactSHA256, *screenWidth, *screenHeight,
	); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func configure(
	adminPath, apiBaseURL, appID, image, network string,
	locale, languages, environmentID, artifactSHA256 string,
	screenWidth, screenHeight int,
) error {
	for name, value := range map[string]string{
		"admin-config": adminPath,
		"api-base-url": apiBaseURL,
		"app-id":       appID,
		"image":        image,
		"network":      network,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%s is required", name)
		}
	}
	info, err := os.Stat(adminPath)
	if err != nil {
		return fmt.Errorf("inspect admin config: %w", err)
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
		return errors.New("admin config must be a regular file unreadable by group and others")
	}
	raw, err := os.ReadFile(adminPath)
	if err != nil {
		return fmt.Errorf("read admin config: %w", err)
	}
	var admin adminConfig
	if err := json.Unmarshal(raw, &admin); err != nil {
		return fmt.Errorf("decode admin config: %w", err)
	}
	client, err := sealskin.NewClient(sealskin.Config{
		BaseURL:              apiBaseURL,
		Username:             admin.Username,
		ServerPublicKeyPEM:   []byte(admin.ServerPublicKey),
		ClientPrivateKeyPEM:  []byte(admin.PrivateKey),
		AllowUnencryptedHTTP: strings.HasPrefix(apiBaseURL, "http://127.0.0.1:"),
	})
	if err != nil {
		return err
	}
	if (screenWidth == 0) != (screenHeight == 0) {
		return errors.New("screen-width and screen-height must both be set or both be zero")
	}
	if screenWidth != 0 && (screenWidth < 640 || screenWidth > 3840 || screenHeight < 480 || screenHeight > 2160) {
		return errors.New("screen dimensions are outside the supported range")
	}
	apps, err := client.ListInstalledApps(context.Background())
	if err != nil {
		return fmt.Errorf("list installed SealSkin apps: %w", err)
	}
	var current *sealskin.InstalledApp
	for index := range apps {
		if apps[index].ID == appID {
			current = &apps[index]
			break
		}
	}
	if current == nil {
		return fmt.Errorf("SealSkin app %q is not installed", appID)
	}
	env := append([]sealskin.EnvVar(nil), current.ProviderConfig.Env...)
	env = setEnv(env, "BROWSER_PLATFORM_LOCALE", strings.TrimSpace(locale))
	env = setEnv(env, "BROWSER_PLATFORM_LANGUAGES", strings.TrimSpace(languages))
	env = setEnv(env, "BROWSER_PLATFORM_ENVIRONMENT_ID", strings.TrimSpace(environmentID))
	artifactSHA256 = strings.TrimSpace(artifactSHA256)
	if artifactSHA256 != "" {
		if len(artifactSHA256) != 64 || strings.IndexFunc(artifactSHA256, func(r rune) bool {
			return !strings.ContainsRune("0123456789abcdef", r)
		}) != -1 {
			return errors.New("artifact-sha256 must contain 64 lowercase hexadecimal characters")
		}
		env = setEnv(env, "BROWSER_PLATFORM_ARTIFACT_SHA256", artifactSHA256)
	}
	if screenWidth != 0 {
		env = setEnv(env, "SELKIES_MANUAL_RESOLUTION", "true")
		env = setEnv(env, "SELKIES_MANUAL_WIDTH", fmt.Sprint(screenWidth))
		env = setEnv(env, "SELKIES_MANUAL_HEIGHT", fmt.Sprint(screenHeight))
	}
	patch := map[string]any{
		"provider_config": map[string]any{
			"image": image,
			"env":   env,
			"docker_overrides": map[string]any{
				"network": network,
			},
		},
	}
	operationID := fmt.Sprintf("configure-proxy-app-%s-%d", appID, time.Now().Unix())
	if err := client.PatchInstalledApp(context.Background(), appID, patch, operationID); err != nil {
		return fmt.Errorf("configure SealSkin proxy app: %w", err)
	}
	fmt.Printf("configured SealSkin app %q for internal network %q\n", appID, network)
	return nil
}

func setEnv(values []sealskin.EnvVar, name, value string) []sealskin.EnvVar {
	if value == "" {
		return values
	}
	for index := range values {
		if values[index].Name == name {
			values[index].Value = value
			return values
		}
	}
	return append(values, sealskin.EnvVar{Name: name, Value: value})
}
