package config

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"browser-platform/adapter/internal/profile"
)

func TestCapacityConfiguration(t *testing.T) {
	for _, tc := range []struct {
		name   string
		limits profile.Limits
		valid  bool
	}{
		{"legacy-disabled", profile.Limits{}, true},
		{"manual", profile.Limits{MaxActiveProfiles: 4}, true},
		{"auto", profile.Limits{Auto: true, StoragePath: "storage"}, true},
		{"missing-path", profile.Limits{Auto: true}, false},
		{"negative-budget", profile.Limits{Auto: true, StoragePath: "storage", MemoryPerProfileMiB: -1}, false},
		{"negative-reserve", profile.Limits{Auto: true, StoragePath: "storage", MemoryReserveMiB: -1}, false},
		{"ignored-budget", profile.Limits{MemoryPerProfileMiB: 1024}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			cfg := validConfig()
			cfg.Limits = tc.limits
			if (cfg.Validate() == nil) != tc.valid {
				t.Fatal("unexpected validation")
			}
		})
	}
	cfg := validConfig()
	cfg.Limits = profile.Limits{Auto: true, StoragePath: "storage", MaxActiveProfiles: 6, MemoryPerProfileMiB: 1536, MemoryReserveMiB: 2048}
	dir := t.TempDir()
	file := filepath.Join(dir, "config.json")
	data, err := json.Marshal(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(file, data, 0600); err != nil {
		t.Fatal(err)
	}
	loaded, err := Load(file)
	if err != nil {
		t.Fatal(err)
	}
	if !loaded.Limits.Auto || loaded.Limits.StoragePath != filepath.Join(dir, "storage") || loaded.Limits.MemoryPerProfileMiB != 1536 || loaded.Limits.MemoryReserveMiB != 2048 || loaded.Limits.MaxActiveProfiles != 6 {
		t.Fatalf("incorrect limits: %+v", loaded.Limits)
	}
}
