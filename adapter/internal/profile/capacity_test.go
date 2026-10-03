package profile

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"browser-platform/adapter/internal/state"
)

func TestCapacityMachineSizing(t *testing.T) {
	for _, tc := range []struct {
		name                      string
		cpu                       int
		memory, disk              int64
		active, concurrent, floor int
	}{
		{"too-small", 1, 512, 20 * 1024, 0, 1, 4096},
		{"small", 2, 4096, 40 * 1024, 2, 1, 4096},
		{"current", 4, 5924, 99 * 1024, 4, 1, 4096},
		{"larger", 16, 32 * 1024, 1024 * 1024, 16, 4, 16384},
		{"cpu-bound", 2, 64 * 1024, 500 * 1024, 2, 1, 10240},
		{"memory-bound", 32, 8192, 100 * 1024, 5, 1, 4096},
	} {
		t.Run(tc.name, func(t *testing.T) {
			l := Limits{Auto: true, StoragePath: "/qa", resources: func(string) (HostResources, error) {
				return HostResources{tc.cpu, tc.memory, tc.memory, tc.disk, tc.disk}, nil
			}}
			r, err := l.InspectCapacity()
			if err != nil || r.MaxActiveProfiles != tc.active || r.MaxConcurrentLaunches != tc.concurrent || r.MinFreeDiskMiB != tc.floor {
				t.Fatalf("report=%+v err=%v", r, err)
			}
		})
	}
	l := Limits{Auto: true, StoragePath: "/qa", MaxActiveProfiles: 7, MaxConcurrentLaunch: 2,
		MinFreeDiskMiB: 9000, MemoryPerProfileMiB: 2048, MemoryReserveMiB: 3000,
		resources: func(string) (HostResources, error) { return HostResources{16, 32768, 20000, 102400, 10000}, nil }}
	r, err := l.InspectCapacity()
	if err != nil || r.MaxActiveProfiles != 7 || r.MaxConcurrentLaunches != 2 || r.MinFreeDiskMiB != 9000 || r.MemoryPerProfileMiB != 2048 || r.MemoryReserveMiB != 3000 {
		t.Fatalf("overrides: %+v %v", r, err)
	}
	r, err = (Limits{}).InspectCapacity()
	if err != nil || r.Mode != "manual" || r.MaxActiveProfiles != 0 || r.Resources != nil {
		t.Fatalf("legacy disabled: %+v %v", r, err)
	}
}

func TestCapacityMemoryParser(t *testing.T) {
	total, available, err := parseMemoryInfo("MemTotal: 6066884 kB\nSwapFree: 0 kB\nMemAvailable: 3505236 kB\n")
	if err != nil || total != 5924 || available != 3423 {
		t.Fatalf("%d %d %v", total, available, err)
	}
	for _, data := range []string{"", "MemTotal: 4096000 kB", "MemTotal: -1 kB\nMemAvailable: 0 kB", "MemTotal: 1024 MB\nMemAvailable: 0 kB", "MemTotal: 1024 kB\nMemAvailable: 2048 kB", "MemTotal: x kB\nMemAvailable: 0 kB"} {
		if _, _, err := parseMemoryInfo(data); err == nil {
			t.Fatalf("accepted %q", data)
		}
	}
}

func TestCapacityAutoPressureReuseAndRecovery(t *testing.T) {
	fake := &lifecycleFake{snapshot: emptyRuntime()}
	st, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	host := HostResources{4, 5924, 3400, 100 * 1024, 5000}
	var probeErr error
	l := Limits{Auto: true, StoragePath: "/qa", resources: func(string) (HostResources, error) { return host, probeErr }}
	svc, err := NewService(fake, st, "https://adapter.example", []Definition{
		{ID: "personal", ApplicationID: "firefox", HomeName: "personal", StartURL: "https://example.com"},
		{ID: "work", ApplicationID: "firefox", HomeName: "work", StartURL: "https://example.com"},
	}, WithLifecycle(fake), WithLimits(l))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := svc.Ensure(context.Background(), "personal"); err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		name, code             string
		available, total, free int64
		unknown                bool
	}{
		{"memory", "CAPACITY_MEMORY", 2000, 5924, 5000, false},
		{"disk", "CAPACITY_DISK", 3400, 5924, 100, false},
		{"zero-slots", "CAPACITY_ACTIVE_PROFILES", 512, 512, 5000, false},
		{"unknown", "CAPACITY_RESOURCES_UNKNOWN", 3400, 5924, 5000, true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			host.AvailableMemoryMiB, host.TotalMemoryMiB, host.FreeDiskMiB = tc.available, tc.total, tc.free
			probeErr = nil
			if tc.unknown {
				probeErr = errors.New("unavailable")
			}
			var cap *CapacityError
			if _, err := svc.Ensure(context.Background(), "work"); !errors.As(err, &cap) || cap.Code != tc.code {
				t.Fatalf("%v", err)
			}
			if _, found, _ := st.Get("work"); found || fake.launches != 1 {
				t.Fatal("refused launch changed state")
			}
			if _, err := svc.Ensure(context.Background(), "personal"); err != nil || fake.launches != 1 {
				t.Fatalf("reuse: %v", err)
			}
		})
	}
	probeErr = nil
	host = HostResources{16, 32768, 20000, 102400, 5000}
	if _, err := svc.Ensure(context.Background(), "work"); err != nil {
		t.Fatalf("resources recovered: %v", err)
	}
	if err := func() error { _, e := svc.Stop(context.Background(), "work"); return e }(); err != nil {
		t.Fatal(err)
	}
	if _, err := svc.Ensure(context.Background(), "work"); err != nil {
		t.Fatalf("budget not released: %v", err)
	}
}

func TestCapacityAutoConcurrentMemoryReservation(t *testing.T) {
	const callers = 12
	fake := &capacityOrchestrator{entered: make(chan struct{}, callers), finish: make(chan struct{})}
	st, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	defs := make([]Definition, callers)
	for i := range defs {
		id := fmt.Sprintf("auto-%d", i)
		defs[i] = Definition{ID: id, ApplicationID: "firefox", HomeName: id, StartURL: "https://example.com"}
	}
	l := Limits{Auto: true, StoragePath: "/qa", MaxConcurrentLaunch: 12, resources: func(string) (HostResources, error) {
		// 6553 MiB reserve + 2*1152 MiB leaves room for precisely two starts.
		return HostResources{16, 32768, 8857, 102400, 10000}, nil
	}}
	svc, err := NewService(fake, st, "https://adapter.example", defs, WithLimits(l))
	if err != nil {
		t.Fatal(err)
	}
	results := make(chan error, callers)
	var wg sync.WaitGroup
	for _, d := range defs {
		wg.Add(1)
		go func(id string) { defer wg.Done(); _, e := svc.Ensure(context.Background(), id); results <- e }(d.ID)
	}
	defer func() { close(fake.finish); wg.Wait() }()
	for range callers - 2 {
		select {
		case err := <-results:
			var cap *CapacityError
			if !errors.As(err, &cap) || cap.Code != "CAPACITY_MEMORY" {
				t.Fatalf("%v", err)
			}
		case <-time.After(3 * time.Second):
			t.Fatal("memory reservations did not refuse excess callers")
		}
	}
	bindings, _ := st.All()
	if len(bindings) != 2 {
		t.Fatalf("admitted %d", len(bindings))
	}
}
