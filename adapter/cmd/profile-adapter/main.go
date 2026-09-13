package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"browser-platform/adapter/internal/config"
	"browser-platform/adapter/internal/control"
	"browser-platform/adapter/internal/httpapi"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

func main() {
	configPath := flag.String("config", "config.json", "path to adapter configuration")
	resetProfile := flag.String("reset-profile", "", "mark one launching/unknown/failed Profile as stopped after operator inspection")
	stopProfile := flag.String("stop-profile", "", "ask the running adapter to stop a Profile and verify removal")
	reconcileProfile := flag.String("reconcile-profile", "", "ask the running adapter to reconcile a Profile or resume its pending stop")
	inspectProfile := flag.String("inspect-profile", "", "inspect a Profile through the running adapter's private control socket")
	flag.Parse()

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	action, target := "", ""
	for name, value := range map[string]string{"reset": *resetProfile, "stop": *stopProfile, "reconcile": *reconcileProfile, "inspect": *inspectProfile} {
		if value == "" {
			continue
		}
		if action != "" {
			logger.Error("only one Profile command may be supplied")
			os.Exit(1)
		}
		action, target = name, value
	}
	if err := run(*configPath, action, target, logger); err != nil {
		logger.Error("profile adapter stopped", "error", err)
		os.Exit(1)
	}
}

func run(configPath, action, target string, logger *slog.Logger) error {
	cfg, err := config.Load(configPath)
	if err != nil {
		return err
	}
	if action != "" && action != "reset" {
		if !cfg.SealSkin.LifecycleEnabled {
			return profile.ErrLifecycleDisabled
		}
		result, err := control.Command(context.Background(), cfg.ControlSocket, action, target)
		if err != nil {
			return err
		}
		return json.NewEncoder(os.Stdout).Encode(result)
	}
	serviceLock, err := state.LockService(cfg.StateFile)
	if err != nil {
		return err
	}
	defer serviceLock.Close()
	serverPublicKey, err := os.ReadFile(cfg.SealSkin.ServerPublicKeyFile)
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
	clientPrivateKey, err := os.ReadFile(cfg.SealSkin.ClientPrivateKeyFile)
	if err != nil {
		return errors.New("read SealSkin client private key")
	}
	client, err := sealskin.NewClient(sealskin.Config{
		BaseURL: cfg.SealSkin.APIBaseURL, Username: cfg.SealSkin.Username,
		ServerPublicKeyPEM: serverPublicKey, ClientPrivateKeyPEM: clientPrivateKey,
		AllowUnencryptedHTTP: cfg.SealSkin.AllowUnencryptedHTTP,
	})
	clear(clientPrivateKey)
	if err != nil {
		return err
	}
	store, err := state.NewStore(cfg.StateFile)
	if err != nil {
		return err
	}
	var options []profile.Option
	if cfg.SealSkin.LifecycleEnabled {
		options = append(options, profile.WithLifecycle(client))
	}
	profiles, err := profile.NewService(client, store, cfg.PublicBaseURL, cfg.Profiles, options...)
	if err != nil {
		return err
	}
	if action == "reset" {
		if err := profiles.ResetUnknown(target); err != nil {
			return err
		}
		logger.Info("profile state reset after operator inspection", "profile", target)
		return nil
	}

	handler := httpapi.New(profiles, client.ListSessions, cfg.PublicBaseURL, cfg.SealSkin.PublicSessionBaseURL, logger)
	httpServer := &http.Server{
		Addr: cfg.ListenAddress, Handler: handler,
		ReadHeaderTimeout: 10 * time.Second, ReadTimeout: 30 * time.Second,
		WriteTimeout: 60 * time.Second, IdleTimeout: 120 * time.Second,
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	var controlServer *http.Server
	if cfg.SealSkin.LifecycleEnabled {
		for _, definition := range cfg.Profiles {
			recoverCtx, cancel := context.WithTimeout(ctx, 45*time.Second)
			result, recoverErr := profiles.Reconcile(recoverCtx, definition.ID)
			cancel()
			if recoverErr != nil {
				logger.Warn("profile still requires recovery", "profile", definition.ID, "error", recoverErr)
			} else {
				logger.Info("profile runtime reconciled", "profile", definition.ID, "status", result.Status)
			}
		}
		listener, err := control.Listen(cfg.ControlSocket)
		if err != nil {
			return err
		}
		defer listener.Close()
		controlServer = &http.Server{Handler: control.Handler(profiles), ReadHeaderTimeout: 5 * time.Second,
			ReadTimeout: 10 * time.Second, WriteTimeout: 90 * time.Second, IdleTimeout: 30 * time.Second}
		go func() {
			if err := controlServer.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
				logger.Error("adapter control listener failed", "error", err)
				stop()
			}
		}()
	}
	shutdownDone := make(chan struct{})
	go func() {
		defer close(shutdownDone)
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		if err := httpServer.Shutdown(shutdownCtx); err != nil {
			logger.Error("graceful shutdown", "error", err)
			_ = httpServer.Close()
		}
		if controlServer != nil {
			if err := controlServer.Shutdown(shutdownCtx); err != nil {
				logger.Error("control shutdown", "error", err)
				_ = controlServer.Close()
			}
		}
	}()
	logger.Info("profile adapter listening", "address", cfg.ListenAddress)
	serveErr := httpServer.ListenAndServe()
	stop()
	<-shutdownDone
	if serveErr != nil && !errors.Is(serveErr, http.ErrServerClosed) {
		return serveErr
	}
	return nil
}
