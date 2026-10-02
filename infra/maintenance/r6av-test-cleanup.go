// This one-shot operator is compiled into a separate copy of the verified
// Adapter entrypoint. It must run under that entrypoint's exclusive service
// lock, with the public Adapter and runner stopped. It is not an HTTP endpoint.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"time"

	"browser-platform/adapter/internal/access"
	"browser-platform/adapter/internal/config"
	"browser-platform/adapter/internal/profile"
)

func r6avCleanup(cfg config.Config, service *profile.Service, mode string) error {
	if mode != "inspect" && mode != "apply" {
		return errors.New("invalid R6AV cleanup mode")
	}
	if cfg.Access == nil {
		return errors.New("account configuration required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Minute)
	defer cancel()
	approved := map[string]bool{"personal": true, "work": true, "browser-29cbe71eb72b": true, "browser-a5cdb0c0145b": true}
	fingerprints := map[string]bool{"fp-fc7678fd15a32f01": true, "fp-5abe75df16ead7dd": true}
	displays := map[string]bool{"display-f7f83905b6bbaa1d": true, "display-015a5dc4cb20ef09": true}
	records := service.Records()
	for _, record := range records {
		if !approved[record.ID] || record.PendingTemplate != nil || record.PendingMigration != nil || (record.Status != profile.RecordReady && record.Status != profile.RecordDeleting) {
			return errors.New("unapproved or unfinished browser operation")
		}
	}
	sources, err := service.TemplateSources()
	if err != nil {
		return err
	}
	for _, source := range sources.Fingerprints {
		if !fingerprints[source.ID] {
			return errors.New("unapproved fingerprint")
		}
	}
	for _, source := range sources.Displays {
		if !source.Builtin && !displays[source.ID] {
			return errors.New("unapproved display")
		}
	}
	networks, err := service.NetworkProfiles()
	if err != nil {
		return err
	}
	for _, network := range networks {
		if (network.ID != "tw" && network.ID != "personal-tw-socks") || network.Revision != 1 {
			return errors.New("unapproved proxy revision")
		}
	}
	jobs, err := service.EnvironmentJobs()
	if err != nil {
		return err
	}
	if len(jobs) > 3 {
		return errors.New("new jobs appeared")
	}
	for _, job := range jobs {
		if job.Status != "accepted" && job.Status != "failed" {
			return errors.New("unfinished job")
		}
	}
	combinations, err := service.CompatibleTemplates(ctx)
	if err != nil {
		return err
	}
	if len(combinations) > 14 {
		return errors.New("new combinations appeared")
	}
	known := func() map[string]bool {
		result := map[string]bool{}
		for _, record := range service.Records() {
			result[record.ID] = true
		}
		return result
	}
	registry, _, err := access.ReadRegistry(cfg.Access.UsersFile, known())
	if err != nil {
		return err
	}
	if !registry.SetupRequired && (len(registry.Users) != 1 || registry.Users[0].ID != "owner" || registry.Users[0].EffectiveRole() != access.RoleAdmin) {
		return errors.New("account scope changed")
	}
	if mode == "inspect" {
		return json.NewEncoder(os.Stdout).Encode(map[string]any{"mode": mode, "browsers": len(records), "fingerprints": len(sources.Fingerprints), "displays": len(sources.Displays), "networks": len(networks), "jobs": len(jobs), "combinations": len(combinations), "setup_required": registry.SetupRequired})
	}
	accounts := access.NewAccountStore(cfg.Access.UsersFile, known)
	const actor = "r6av-maintenance"
	for _, record := range records {
		if err := accounts.RemoveProfileGrants(record.ID); err != nil {
			return err
		}
		if err := service.DeleteBrowser(ctx, record.ID, actor, "r6av-delete-"+record.ID); err != nil {
			return fmt.Errorf("delete %s: %w", record.ID, err)
		}
		fmt.Println("PASS normal browser archive/delete", record.ID)
	}
	for _, network := range networks {
		if err := service.DeleteNetworkProfile(ctx, network.ID, network.Revision, actor, "r6av-delete-"+network.ID); err != nil {
			return err
		}
		fmt.Println("PASS proxy revision deletion", network.ID)
	}
	for _, combo := range combinations {
		if err := service.DeleteTemplateData(ctx, "combinations", combo.EnvironmentArtifactID, combo.BrowserTemplateID, combo.DisplayTemplateID, actor); err != nil {
			return err
		}
	}
	for id := range fingerprints {
		if err := service.DeleteTemplateData(ctx, "fingerprints", id, "", "", actor); err != nil {
			return err
		}
	}
	for id := range displays {
		if err := service.DeleteTemplateData(ctx, "displays", id, "", "", actor); err != nil {
			return err
		}
	}
	for _, job := range jobs {
		if err := service.DeleteTemplateData(ctx, "jobs", job.ID, "", "", actor); err != nil {
			return err
		}
	}
	if len(service.Records()) != 0 {
		return errors.New("browser deletion incomplete")
	}
	// Explicitly authorized last-account reset is local maintenance only; normal
	// AccountStore.Delete and all web self/last-admin protections remain intact.
	if err := accounts.Mutate(false, func(value *access.Registry) error {
		if value.SetupRequired {
			return nil
		}
		if len(value.Users) != 1 || value.Users[0].ID != "owner" || len(value.Users[0].Profiles) != 0 {
			return errors.New("account scope changed during cleanup")
		}
		*value = access.Registry{Version: 3, Users: []access.Account{}, SetupRequired: true}
		return nil
	}); err != nil {
		return err
	}
	return r6avCleanup(cfg, service, "inspect")
}
