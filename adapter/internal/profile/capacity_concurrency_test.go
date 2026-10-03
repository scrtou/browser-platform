package profile

import (
	"browser-platform/adapter/internal/sealskin"
	"browser-platform/adapter/internal/state"
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type capacityOrchestrator struct {
	fakeOrchestrator
	entered chan struct{}
	finish  chan struct{}
}

func (f *capacityOrchestrator) LaunchURL(ctx context.Context, req sealskin.LaunchURLRequest, key string) (sealskin.LaunchResponse, error) {
	f.entered <- struct{}{}
	<-f.finish
	return f.fakeOrchestrator.LaunchURL(ctx, req, key)
}
func TestCapacityCrossProfileAdmission(t *testing.T) {
	for _, kind := range []string{"active", "concurrent"} {
		t.Run(kind, func(t *testing.T) {
			const callers = 12
			f := &capacityOrchestrator{entered: make(chan struct{}, callers), finish: make(chan struct{})}
			st, err := state.NewStore(filepath.Join(t.TempDir(), "state.json"))
			if err != nil {
				t.Fatal(err)
			}
			defs := make([]Definition, callers)
			for i := range defs {
				id := fmt.Sprintf("capacity-%d", i)
				defs[i] = Definition{ID: id, ApplicationID: "firefox", HomeName: id, StartURL: "https://example.com"}
			}
			var probes atomic.Int32
			firstProbe := make(chan struct{})
			releaseProbe := make(chan struct{})
			lim := Limits{MinFreeDiskMiB: 1, StoragePath: "/", freeDiskMiB: func(string) (int64, error) {
				if probes.Add(1) == 1 {
					close(firstProbe)
				}
				<-releaseProbe
				return 100, nil
			}}
			code := "CAPACITY_ACTIVE_PROFILES"
			if kind == "active" {
				lim.MaxActiveProfiles = 1
			} else {
				lim.MaxConcurrentLaunch = 1
				code = "CAPACITY_CONCURRENT_LAUNCHES"
			}
			svc, err := NewService(f, st, "https://adapter.example", defs, WithLimits(lim))
			if err != nil {
				t.Fatal(err)
			}
			results := make(chan error, callers)
			var wg sync.WaitGroup
			for _, d := range defs {
				wg.Add(1)
				go func(id string) { defer wg.Done(); _, e := svc.Ensure(context.Background(), id); results <- e }(d.ID)
			}
			<-firstProbe
			// Hold admission after capacity reads but before any durable reservation.
			time.Sleep(100 * time.Millisecond)
			close(releaseProbe)
			<-f.entered
			rejected := 0
			deadline := time.NewTimer(2 * time.Second)
			for rejected < callers-1 {
				select {
				case e := <-results:
					var cap *CapacityError
					if !errors.As(e, &cap) || cap.Code != code {
						t.Errorf("expected %s, got %v", code, e)
					}
					rejected++
				case <-deadline.C:
					goto done
				}
			}
		done:
			deadline.Stop()
			bindings, _ := st.All()
			count := len(bindings)
			close(f.finish)
			wg.Wait()
			if rejected != callers-1 || count != 1 || probes.Load() != 1 {
				t.Fatalf("rejected=%d bindings=%d disk probes=%d; want %d/1/1", rejected, count, probes.Load(), callers-1)
			}
			if e := <-results; e != nil {
				t.Fatal(e)
			}
			if len(f.entered) != 0 {
				t.Fatal("extra launch reached controller")
			}
		})
	}
}
