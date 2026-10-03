package profile

import (
	"errors"
	"os"
	"runtime"
	"strconv"
	"strings"
	"syscall"
)

// HostResources describes the local Linux machine hosting both the adapter
// and Docker workers. Adapter-only cgroup limits do not bound sibling workers.
type HostResources struct {
	CPUs               int   `json:"cpus"`
	TotalMemoryMiB     int64 `json:"total_memory_mib"`
	AvailableMemoryMiB int64 `json:"available_memory_mib"`
	TotalDiskMiB       int64 `json:"total_disk_mib"`
	FreeDiskMiB        int64 `json:"free_disk_mib"`
}

type CapacityReport struct {
	Mode                  string         `json:"mode"`
	MaxActiveProfiles     int            `json:"max_active_profiles"`
	MaxConcurrentLaunches int            `json:"max_concurrent_launches"`
	MinFreeDiskMiB        int            `json:"min_free_disk_mib"`
	MemoryPerProfileMiB   int            `json:"memory_per_profile_mib,omitempty"`
	MemoryReserveMiB      int            `json:"memory_reserve_mib,omitempty"`
	Resources             *HostResources `json:"resources,omitempty"`
}

func (l Limits) Validate() error {
	if l.MaxActiveProfiles < 0 || l.MaxConcurrentLaunch < 0 || l.MinFreeDiskMiB < 0 || l.MemoryPerProfileMiB < 0 || l.MemoryReserveMiB < 0 {
		return errors.New("limits must not be negative")
	}
	if (l.Auto || l.MinFreeDiskMiB > 0) && l.StoragePath == "" {
		return errors.New("limits.auto or limits.min_free_disk_mib requires limits.storage_path")
	}
	if !l.Auto && (l.MemoryPerProfileMiB != 0 || l.MemoryReserveMiB != 0) {
		return errors.New("limits memory budgets require limits.auto")
	}
	return nil
}

// InspectCapacity does no writes or controller calls. Auto is resolved afresh
// for each admission; zero in auto mode means no slots, not unlimited.
func (l Limits) InspectCapacity() (CapacityReport, error) {
	if err := l.Validate(); err != nil {
		return CapacityReport{}, err
	}
	r := CapacityReport{Mode: "manual", MaxActiveProfiles: l.MaxActiveProfiles,
		MaxConcurrentLaunches: l.MaxConcurrentLaunch, MinFreeDiskMiB: l.MinFreeDiskMiB}
	if !l.Auto {
		return r, nil
	}
	probe := l.resources
	if probe == nil {
		probe = readHostResources
	}
	h, err := probe(l.StoragePath)
	if err != nil {
		return CapacityReport{}, err
	}
	if h.CPUs <= 0 || h.TotalMemoryMiB <= 0 || h.AvailableMemoryMiB < 0 || h.AvailableMemoryMiB > h.TotalMemoryMiB || h.TotalDiskMiB <= 0 || h.FreeDiskMiB < 0 || h.FreeDiskMiB > h.TotalDiskMiB {
		return CapacityReport{}, errors.New("invalid host resource measurement")
	}
	r.Mode, r.Resources = "auto", &h
	r.MemoryPerProfileMiB = l.MemoryPerProfileMiB
	if r.MemoryPerProfileMiB == 0 {
		r.MemoryPerProfileMiB = 1152 // 1 GiB Worker + 128 MiB supporting processes.
	}
	r.MemoryReserveMiB = l.MemoryReserveMiB
	if r.MemoryReserveMiB == 0 {
		r.MemoryReserveMiB = int(max(int64(1024), h.TotalMemoryMiB/5))
	}
	if r.MaxActiveProfiles == 0 {
		slots := max(int64(0), (h.TotalMemoryMiB-int64(r.MemoryReserveMiB))/int64(r.MemoryPerProfileMiB))
		r.MaxActiveProfiles = int(min(int64(h.CPUs), slots))
	}
	if r.MaxConcurrentLaunches == 0 {
		r.MaxConcurrentLaunches = max(1, min(h.CPUs/4, r.MaxActiveProfiles/4))
	}
	if r.MinFreeDiskMiB == 0 {
		r.MinFreeDiskMiB = int(max(int64(4096), min(int64(16384), h.TotalDiskMiB/50)))
	}
	return r, nil
}

func readHostResources(path string) (HostResources, error) {
	data, err := os.ReadFile("/proc/meminfo")
	if err != nil {
		return HostResources{}, err
	}
	total, available, err := parseMemoryInfo(string(data))
	if err != nil {
		return HostResources{}, err
	}
	var disk syscall.Statfs_t
	if err := syscall.Statfs(path, &disk); err != nil {
		return HostResources{}, err
	}
	return HostResources{CPUs: runtime.NumCPU(), TotalMemoryMiB: total, AvailableMemoryMiB: available,
		TotalDiskMiB: int64(disk.Blocks) * int64(disk.Bsize) / (1 << 20),
		FreeDiskMiB:  int64(disk.Bavail) * int64(disk.Bsize) / (1 << 20)}, nil
}

func parseMemoryInfo(data string) (int64, int64, error) {
	values := map[string]int64{}
	for _, line := range strings.Split(data, "\n") {
		fields := strings.Fields(line)
		if len(fields) == 0 || (fields[0] != "MemTotal:" && fields[0] != "MemAvailable:") {
			continue
		}
		if len(fields) != 3 || fields[2] != "kB" {
			return 0, 0, errors.New("invalid memory measurement")
		}
		v, err := strconv.ParseInt(fields[1], 10, 64)
		if err != nil || v < 0 {
			return 0, 0, errors.New("invalid memory measurement")
		}
		values[fields[0]] = v / 1024
	}
	total, okTotal := values["MemTotal:"]
	available, okAvailable := values["MemAvailable:"]
	if !okTotal || !okAvailable || total <= 0 || available > total {
		return 0, 0, errors.New("missing or invalid MemTotal/MemAvailable")
	}
	return total, available, nil
}
