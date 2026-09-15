package profile

import (
	"context"
	"testing"

	"browser-platform/adapter/internal/sealskin"
)

func TestDirectHealthRequiresCurrentEgressEvidence(t *testing.T) {
	for name, tc := range map[string]struct {
		change func(*sealskin.NetworkHealth)
		code   string
		status CheckStatus
	}{
		"ready":             {func(*sealskin.NetworkHealth) {}, "DIRECT_OK", CheckPass},
		"no probe":          {func(n *sealskin.NetworkHealth) { n.Upstream = nil }, "DIRECT_PROBE_NOT_RUN", CheckUnknown},
		"probe unavailable": {func(n *sealskin.NetworkHealth) { n.Upstream.Status = "unknown" }, "DIRECT_PROBE_UNKNOWN", CheckUnknown},
		"gateway stopped":   {func(n *sealskin.NetworkHealth) { n.Relay.Status = "fail" }, "DIRECT_GATEWAY_UNAVAILABLE", CheckFail},
		"guard stopped":     {func(n *sealskin.NetworkHealth) { n.Guard.Container = "exited" }, "DIRECT_GUARD_NOT_RUNNING", CheckFail},
		"namespace unknown": {func(n *sealskin.NetworkHealth) { n.WorkerNamespace = nil }, "DIRECT_NAMESPACE_UNOBSERVED", CheckUnknown},
		"namespace changed": {func(n *sealskin.NetworkHealth) { value := false; n.WorkerNamespace = &value }, "DIRECT_NAMESPACE_CHANGED", CheckFail},
		"host evidence":     {func(n *sealskin.NetworkHealth) { n.Code = "DIRECT_HOST_EVIDENCE_CHANGED" }, "DIRECT_HOST_EVIDENCE_CHANGED", CheckUnknown},
		"wrong revision":    {func(n *sealskin.NetworkHealth) { n.PolicySHA256 = "other" }, "DIRECT_BINDING_CHANGED", CheckUnknown},
	} {
		t.Run(name, func(t *testing.T) {
			service, fake := managedHealthService(t)
			fake.observeHook = func(h *sealskin.HomeHealth) {
				h.Network.Mode = "direct"
				tc.change(h.Network)
			}
			report, err := service.Health(context.Background(), "personal", HealthOptions{})
			if err != nil {
				t.Fatal(err)
			}
			if report.NetworkMode != "direct" || check(t, report, "proxy").Status != CheckNotApplicable {
				t.Fatalf("DIRECT mislabeled as upstream proxy: %+v", report)
			}
			egress := check(t, report, "egress")
			if !egress.Required || egress.Code != tc.code || egress.Status != tc.status {
				t.Fatalf("egress=%+v", egress)
			}
			if tc.status != CheckPass && report.Overall == OverallHealthy || fake.stopCalls != 0 || fake.launches != 1 {
				t.Fatal("missing evidence became healthy or health changed lifecycle")
			}
		})
	}
}
