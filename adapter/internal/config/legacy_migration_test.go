package config

import "testing"

func TestLegacyMigrationConfigurationRequiresProtectedManagement(t *testing.T) {
	cfg := validConfig()
	cfg.LegacyNetworkMigrations = "/private/migrations.json"
	if cfg.Validate() == nil {
		t.Fatal("legacy migration without authenticated management dependencies accepted")
	}
}
