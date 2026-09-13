// Command sealskin-smoke-session launches a temporary cleanroom session for
// deployment inspection and stops it automatically when the hold time ends.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"browser-platform/adapter/internal/config"
	"browser-platform/adapter/internal/sealskin"
)

func main() {
	configPath := flag.String("config", "config.json", "path to adapter configuration")
	appID := flag.String("app-id", "", "installed SealSkin application ID")
	profileID := flag.String("profile-id", "", "profile whose app and environment settings to use")
	pageURL := flag.String("url", "https://example.com/", "page to open")
	hold := flag.Duration("hold", time.Minute, "time to keep the smoke session alive")
	language := flag.String("language", "en_US.UTF-8", "desktop locale in app-id mode")
	timezone := flag.String("timezone", "Etc/UTC", "timezone in app-id mode")
	wayland := flag.Bool("wayland", true, "use Wayland in app-id mode; false selects X11")
	sessionFile := flag.String("session-file", "", "optional new 0600 file for automated Session URL consumption; removed on exit")
	flag.Parse()
	if err := run(*configPath, *appID, *profileID, *pageURL, *hold, *language, *timezone, *wayland, *sessionFile); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(configPath, appID, profileID, pageURL string, hold time.Duration, desktopLanguage, desktopTimezone string, waylandMode bool, sessionFile string) (resultErr error) {
	if strings.TrimSpace(appID) == "" && strings.TrimSpace(profileID) == "" {
		return errors.New("app-id or profile-id is required")
	}
	if strings.TrimSpace(appID) != "" && strings.TrimSpace(profileID) != "" {
		return errors.New("app-id and profile-id are mutually exclusive")
	}
	if hold < time.Second || hold > 10*time.Minute {
		return errors.New("hold must be between 1s and 10m")
	}
	cfg, err := config.Load(configPath)
	if err != nil {
		return err
	}
	var language, timezone *string
	if profileID != "" {
		found := false
		for _, definition := range cfg.Profiles {
			if definition.ID == profileID {
				appID = definition.ApplicationID
				language = definition.Language
				timezone = definition.Timezone
				waylandMode = definition.WaylandMode
				found = true
				break
			}
		}
		if !found {
			return fmt.Errorf("profile %q is not configured", profileID)
		}
	} else {
		language = stringPointer(desktopLanguage)
		timezone = stringPointer(desktopTimezone)
	}
	serverPublic, err := os.ReadFile(cfg.SealSkin.ServerPublicKeyFile)
	if err != nil {
		return errors.New("read SealSkin server public key")
	}
	privateInfo, err := os.Stat(cfg.SealSkin.ClientPrivateKeyFile)
	if err != nil {
		return errors.New("inspect SealSkin client private key")
	}
	if !privateInfo.Mode().IsRegular() || privateInfo.Mode().Perm()&0o077 != 0 {
		return errors.New("SealSkin client private key must be a regular file unreadable by group and others")
	}
	clientPrivate, err := os.ReadFile(cfg.SealSkin.ClientPrivateKeyFile)
	if err != nil {
		return errors.New("read SealSkin client private key")
	}
	client, err := sealskin.NewClient(sealskin.Config{
		BaseURL: cfg.SealSkin.APIBaseURL, Username: cfg.SealSkin.Username,
		ServerPublicKeyPEM: serverPublic, ClientPrivateKeyPEM: clientPrivate,
		AllowUnencryptedHTTP: cfg.SealSkin.AllowUnencryptedHTTP,
	})
	clear(clientPrivate)
	if err != nil {
		return err
	}
	operationID := fmt.Sprintf("smoke-launch-%d", time.Now().UnixNano())
	response, err := client.LaunchURL(context.Background(), sealskin.LaunchURLRequest{
		URL: pageURL, ApplicationID: appID, HomeName: "cleanroom",
		Language: language, Timezone: timezone, WaylandMode: waylandMode,
	}, operationID)
	if err != nil {
		return fmt.Errorf("launch smoke session: %w", err)
	}
	fmt.Printf("smoke_session_id=%s\n", response.SessionID)
	defer func() {
		stopCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		if err := client.StopSession(stopCtx, response.SessionID, "smoke-stop-"+response.SessionID); err != nil {
			resultErr = errors.Join(resultErr, fmt.Errorf("stop smoke session: %w", err))
		} else {
			fmt.Println("smoke_session_stop_requested=true")
		}
	}()
	if sessionFile != "" {
		file, err := os.OpenFile(sessionFile, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
		if err != nil {
			return errors.New("create private smoke session file")
		}
		defer os.Remove(sessionFile)
		writeErr := json.NewEncoder(file).Encode(response)
		closeErr := file.Close()
		if writeErr != nil || closeErr != nil {
			return errors.New("write private smoke session file")
		}
	}

	waitCtx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	timer := time.NewTimer(hold)
	select {
	case <-waitCtx.Done():
	case <-timer.C:
	}
	if !timer.Stop() {
		select {
		case <-timer.C:
		default:
		}
	}
	return nil
}

func stringPointer(value string) *string { return &value }
