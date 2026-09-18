package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"log"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/config"
	"browser-platform/adapter/internal/control"
	"browser-platform/adapter/internal/httpapi"
	"browser-platform/adapter/internal/profile"
	"browser-platform/adapter/internal/safelog"
	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
)

func main() {
	configPath := flag.String("config", "config.json", "path to adapter configuration")
	resetProfile := flag.String("reset-profile", "", "mark one launching/unknown/failed Profile as stopped after operator inspection")
	stopProfile := flag.String("stop-profile", "", "ask the running adapter to stop a Profile and verify removal")
	reconcileProfile := flag.String("reconcile-profile", "", "ask the running adapter to reconcile a Profile or resume its pending stop")
	resumeProfile := flag.String("resume-profile", "", "ask the running adapter to resume a dormant generation in order (Relay, Guard, probe, Worker); never creates")
	inspectProfile := flag.String("inspect-profile", "", "inspect a Profile through the running adapter's private control socket")
	healthProfile := flag.String("health-profile", "", "read a Profile's runtime health report through the private control socket")
	probeProfile := flag.String("probe-profile", "", "force a fresh runtime health probe (at most once per 10 seconds) through the private control socket")
	coherenceProfile := flag.String("coherence-profile", "", "sample browser environment and network coherence for an existing generation through the private control socket")
	flag.Parse()

	logger := safelog.Logger(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	action, target := "", ""
	for name, value := range map[string]string{"reset": *resetProfile, "stop": *stopProfile, "reconcile": *reconcileProfile, "inspect": *inspectProfile,
		"resume": *resumeProfile, "health": *healthProfile, "probe": *probeProfile, "coherence": *coherenceProfile} {
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
		if action == "coherence" {
			report, err := control.CoherenceCommand(context.Background(), cfg.ControlSocket, target)
			if err != nil {
				return err
			}
			encoder := json.NewEncoder(os.Stdout)
			encoder.SetIndent("", "  ")
			return encoder.Encode(report)
		}
		if action == "health" || action == "probe" {
			report, err := control.HealthCommand(context.Background(), cfg.ControlSocket, action, target)
			if err != nil {
				return err
			}
			encoder := json.NewEncoder(os.Stdout)
			encoder.SetIndent("", "  ")
			return encoder.Encode(report)
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
	var transport http.RoundTripper
	if cfg.Access != nil {
		transport, err = access.SessionTransport(*cfg.Access)
		if err != nil {
			return err
		}
	}
	client, err := sealskin.NewClient(sealskin.Config{
		BaseURL: cfg.SealSkin.APIBaseURL, Username: cfg.SealSkin.Username,
		ServerPublicKeyPEM: serverPublicKey, ClientPrivateKeyPEM: clientPrivateKey,
		AllowUnencryptedHTTP: cfg.SealSkin.AllowUnencryptedHTTP,
		Transport:            transport,
	})
	clear(clientPrivateKey)
	if err != nil {
		return err
	}
	store, err := state.NewStore(cfg.StateFile)
	if err != nil {
		return err
	}
	options := []profile.Option{profile.WithLimits(cfg.Limits)}
	if cfg.SealSkin.LifecycleEnabled {
		options = append(options, profile.WithLifecycle(client))
	}
	if cfg.ProfileDirectory != "" {
		options = append(options, profile.WithDirectory(cfg.ProfileDirectory))
	}
	if cfg.EnvironmentCatalog != "" {
		catalog, catalogErr := profile.NewFileEnvironmentCatalog(cfg.EnvironmentCatalog)
		if catalogErr != nil {
			return catalogErr
		}
		adminInfo, statErr := os.Stat(cfg.SealSkinAdmin.ClientPrivateKeyFile)
		if statErr != nil || !adminInfo.Mode().IsRegular() || adminInfo.Mode().Perm()&0o077 != 0 {
			return errors.New("SealSkin administrator private key must be a private regular file")
		}
		adminPrivateKey, readErr := os.ReadFile(cfg.SealSkinAdmin.ClientPrivateKeyFile)
		if readErr != nil {
			return errors.New("read SealSkin administrator private key")
		}
		adminClient, clientErr := sealskin.NewClient(sealskin.Config{
			BaseURL: cfg.SealSkin.APIBaseURL, Username: cfg.SealSkinAdmin.Username,
			ServerPublicKeyPEM: serverPublicKey, ClientPrivateKeyPEM: adminPrivateKey,
			AllowUnencryptedHTTP: cfg.SealSkin.AllowUnencryptedHTTP, Transport: transport,
		})
		clear(adminPrivateKey)
		if clientErr != nil {
			return clientErr
		}
		options = append(options, profile.WithEnvironmentCatalog(catalog), profile.WithAdminOrchestrator(adminClient), profile.WithHomeArchiver(client))
		if cfg.ProxyTemplate != nil {
			options = append(options, profile.WithProxyTemplate(*cfg.ProxyTemplate))
		}
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

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	var httpOptions []httpapi.Option
	if cfg.Access != nil {
		gateway, err := access.New(ctx, *cfg.Access, cfg.PublicBaseURL, cfg.SealSkin.PublicSessionBaseURL, profiles, profiles.CheckDisplaySession, logger)
		if err != nil {
			return err
		}
		httpOptions = append(httpOptions, httpapi.WithAccess(gateway))
	}
	healthUI := httpapi.HealthUI{EntryHint: cfg.SealSkin.LifecycleEnabled && cfg.Health.EntryHintEnabled(), EntryWait: cfg.Health.EntryWait()}
	handler := httpapi.New(profiles, client.ListSessions, cfg.PublicBaseURL, cfg.SealSkin.PublicSessionBaseURL, logger, healthUI, httpOptions...)
	httpServer := &http.Server{
		Addr: cfg.ListenAddress, Handler: handler,
		ErrorLog: log.New(safelog.ServerErrors{Logger: logger}, "", 0), MaxHeaderBytes: 64 << 10,
		ReadHeaderTimeout: 10 * time.Second, ReadTimeout: 30 * time.Second,
		// An entry POST may resume a dormant generation in order before redirecting.
		WriteTimeout: sealskin.LongOperationTimeout + 15*time.Second, IdleTimeout: 120 * time.Second,
	}
	var controlServer *http.Server
	if cfg.SealSkin.LifecycleEnabled {
		// After a host boot the control service may still be starting; wait a
		// bounded time so startup reconciliation (including dormant-generation
		// resume) runs once SealSkin answers instead of failing immediately.
		waitCtx, cancelWait := context.WithTimeout(ctx, cfg.Startup.ControlWait())
		if err := waitForControlPlane(waitCtx, client.ListSessions, logger); err != nil {
			logger.Warn("SealSkin control plane not ready before startup reconciliation", "error", err)
		}
		cancelWait()
		for _, definition := range cfg.Profiles {
			recoverCtx, cancel := context.WithTimeout(ctx, sealskin.LongOperationTimeout+15*time.Second)
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
		controlServer = &http.Server{Handler: control.Handler(profiles), ErrorLog: log.New(safelog.ServerErrors{Logger: logger}, "", 0), ReadHeaderTimeout: 5 * time.Second,
			ReadTimeout: 10 * time.Second, WriteTimeout: control.CommandTimeout + 15*time.Second, IdleTimeout: 30 * time.Second}
		go func() {
			if err := controlServer.Serve(listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
				logger.Error("adapter control listener failed", "error", err)
				stop()
			}
		}()
		if interval := cfg.Health.SampleInterval(); interval > 0 {
			last := make(map[string]profile.Overall)
			lastIdle := make(map[string]string)
			go profiles.SampleHealth(ctx, interval, func(report profile.HealthReport) {
				if last[report.ProfileID] != report.Overall {
					code := ""
					if report.Recovery != nil {
						code = report.Recovery.Code
					}
					logger.Info("profile health changed", "profile", report.ProfileID, "overall", report.Overall, "code", code)
					last[report.ProfileID] = report.Overall
				}
				idleCtx, cancel := context.WithTimeout(ctx, 90*time.Second)
				decision := profiles.ApplyIdle(idleCtx, report, logger)
				cancel()
				if decision.Action != "off" && lastIdle[report.ProfileID] != decision.Action {
					logger.Info("idle policy", "profile", report.ProfileID, "action", decision.Action, "remaining", decision.Remaining.Round(time.Second).String())
					lastIdle[report.ProfileID] = decision.Action
				}
			})
		}
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

// waitForControlPlane polls the read-only session list until it answers or
// the bounded wait ends. It never launches anything.
func waitForControlPlane(ctx context.Context, list func(context.Context) ([]sealskin.Session, error), logger *slog.Logger) error {
	attempt := 0
	for {
		attemptCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
		_, err := list(attemptCtx)
		cancel()
		if err == nil {
			if attempt > 0 {
				logger.Info("SealSkin control plane became ready", "attempts", attempt+1)
			}
			return nil
		}
		attempt++
		select {
		case <-ctx.Done():
			return err
		case <-time.After(2 * time.Second):
		}
	}
}
