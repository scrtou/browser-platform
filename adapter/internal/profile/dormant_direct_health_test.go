package profile

import (
	"browser-platform/adapter/internal/sealskin"
	"context"
	"testing"
)

func TestDirectDormantRecoveryPrecedesExpectedStoppedGuard(t *testing.T) {
	for _, mode := range []string{"dormant", "live-worker", "missing-allocation", "foreign-worker"} {
		t.Run(mode, func(t *testing.T) {
			service, fake := managedHealthService(t)
			if mode != "live-worker" {
				fake.snapshot.Workers[0].Status = "exited"
			}
			if mode == "missing-allocation" {
				fake.snapshot.Resources = fake.snapshot.Resources[:len(fake.snapshot.Resources)-1]
			}
			if mode == "foreign-worker" {
				fake.snapshot.Workers[0].Owned = false
			}
			fake.observeHook = func(h *sealskin.HomeHealth) {
				h.Network.Mode = "direct"
				h.Network.Guard.Container = "exited"
				if mode != "live-worker" {
					h.Workers[0].Status = "exited"
				}
			}
			report, err := service.Health(context.Background(), "personal", HealthOptions{})
			if err != nil {
				t.Fatal(err)
			}
			if report.Recovery == nil || report.Overall == OverallHealthy {
				t.Fatalf("invalid health: %+v", report)
			}
			if mode == "dormant" {
				if report.Recovery.Blocking || report.Recovery.Code != "WORKER_DORMANT" {
					t.Fatalf("ordered resume blocked: %+v", report.Recovery)
				}
				if check(t, report, "egress").Code != "DIRECT_GUARD_NOT_RUNNING" {
					t.Fatal("stopped guard hidden")
				}
			} else if mode == "foreign-worker" {
				if report.Recovery.Code != "OWNERSHIP_UNPROVEN" {
					t.Fatal("foreign ownership accepted")
				}
			} else if !report.Recovery.Blocking || report.Recovery.Code != "DIRECT_GUARD_NOT_RUNNING" {
				t.Fatalf("unsafe runtime unblocked: %+v", report.Recovery)
			}
			if fake.resumeCalls != 0 || fake.stopCalls != 0 || fake.launches != 1 {
				t.Fatal("health performed a lifecycle mutation")
			}
		})
	}
}
