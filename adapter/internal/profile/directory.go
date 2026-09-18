package profile

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"
)

const directoryVersion = 1

const (
	RecordCreating = "creating"
	RecordReady    = "ready"
	RecordDeleting = "deleting"
	RecordDeleted  = "deleted"
)

var (
	ErrProfileDisabled   = errors.New("profile is disabled; no new session may be started or reused")
	ErrRevisionMismatch  = errors.New("profile revision changed; reload and retry")
	ErrDirectoryReadOnly = errors.New("profile directory is not persisted; changes require profile_directory")
)

// Record is one browser definition together with its directory metadata.
type Record struct {
	Definition
	Revision  int       `json:"revision"`
	UpdatedAt time.Time `json:"updated_at"`
	UpdatedBy string    `json:"updated_by,omitempty"`
	Status    string    `json:"status,omitempty"`
}

type directoryFile struct {
	Version  int      `json:"version"`
	Revision int      `json:"revision"`
	Browsers []Record `json:"browsers"`
}

// BrowserPatch is the set of fields an administrator may change while a
// browser keeps its Home, application, network policy and identity. Nil means
// "leave unchanged".
type BrowserPatch struct {
	Label    *string
	StartURL *string
	Disabled *bool
}

// directory is the Adapter-owned, revisioned set of browser definitions. When
// a path is configured every change is persisted with the same protections as
// the journal (0600, fsync, atomic replace); without a path it is the static
// configuration and cannot be modified.
type directory struct {
	mu       sync.RWMutex
	path     string
	revision int
	records  map[string]Record
	now      func() time.Time
}

func newDirectory(definitions []Definition, now func() time.Time) (*directory, error) {
	d := &directory{records: make(map[string]Record, len(definitions)), now: now}
	homes := make(map[string]string, len(definitions))
	for _, definition := range definitions {
		if err := validateDefinition(definition); err != nil {
			return nil, fmt.Errorf("profile %q: %w", definition.ID, err)
		}
		if _, exists := d.records[definition.ID]; exists {
			return nil, fmt.Errorf("duplicate profile ID %q", definition.ID)
		}
		if previous, exists := homes[definition.HomeName]; exists {
			return nil, fmt.Errorf("profiles %q and %q share one Home", previous, definition.ID)
		}
		homes[definition.HomeName] = definition.ID
		d.records[definition.ID] = Record{Definition: definition, Revision: 1, UpdatedAt: now().UTC(), Status: RecordReady}
	}
	return d, nil
}

func (d *directory) get(id string) (Definition, bool) {
	d.mu.RLock()
	defer d.mu.RUnlock()
	record, ok := d.records[id]
	if ok && record.Status == RecordDeleted {
		ok = false
	}
	return record.Definition, ok
}

func (d *directory) record(id string) (Record, bool) {
	d.mu.RLock()
	defer d.mu.RUnlock()
	record, ok := d.records[id]
	if ok && record.Status == RecordDeleted {
		ok = false
	}
	return record, ok
}

func (s *Service) record(id string) (Record, bool) { return s.directory.record(id) }

func (d *directory) ids() []string {
	d.mu.RLock()
	defer d.mu.RUnlock()
	ids := make([]string, 0, len(d.records))
	for id := range d.records {
		if d.records[id].Status == RecordDeleted {
			continue
		}
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

func (d *directory) all() []Record {
	d.mu.RLock()
	defer d.mu.RUnlock()
	records := make([]Record, 0, len(d.records))
	for _, record := range d.records {
		if record.Status == RecordDeleted {
			continue
		}
		copy := record
		copy.RequiredRuntimeCapabilities = cloneCapabilities(record.RequiredRuntimeCapabilities)
		records = append(records, copy)
	}
	sort.Slice(records, func(i, j int) bool { return records[i].ID < records[j].ID })
	return records
}

func (d *directory) definitions() []Definition {
	records := d.all()
	result := make([]Definition, 0, len(records))
	for _, record := range records {
		result = append(result, record.Definition)
	}
	return result
}

func cloneCapabilities(values map[string]int) map[string]int {
	if values == nil {
		return nil
	}
	copy := make(map[string]int, len(values))
	for key, value := range values {
		copy[key] = value
	}
	return copy
}

// DirectoryProfileIDs reads only the Profile IDs from a persisted directory
// so tools that run without the service (the account CLI) can validate
// grants against the same set the running Adapter uses.
func DirectoryProfileIDs(path string) ([]string, error) {
	d := &directory{records: make(map[string]Record), now: time.Now}
	if err := d.open(path); err != nil {
		return nil, err
	}
	return d.ids(), nil
}

// open binds the directory to its file. An existing file replaces the static
// definitions (the configuration then only seeds a first import); a missing
// file is created from them so the next start reads the same set.
func (d *directory) open(path string) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	d.path = path
	file, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		if len(d.records) == 0 {
			return errors.New("profile directory does not exist and no profiles are configured for import")
		}
		d.revision = 1
		return d.writeLocked()
	}
	if err != nil {
		return fmt.Errorf("open profile directory: %w", err)
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
		return errors.New("profile directory must be a private regular file")
	}
	var data directoryFile
	decoder := json.NewDecoder(io.LimitReader(file, 4<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&data); err != nil {
		return fmt.Errorf("decode profile directory: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return errors.New("profile directory contains trailing data")
	}
	if data.Version != directoryVersion || data.Revision < 1 || len(data.Browsers) == 0 {
		return errors.New("unsupported or empty profile directory")
	}
	records := make(map[string]Record, len(data.Browsers))
	homes := make(map[string]string, len(data.Browsers))
	for _, record := range data.Browsers {
		if err := validateDefinition(record.Definition); err != nil {
			return fmt.Errorf("profile directory entry %q: %w", record.ID, err)
		}
		if record.Revision < 1 {
			return fmt.Errorf("profile directory entry %q has no revision", record.ID)
		}
		if record.Status == "" {
			record.Status = RecordReady
		}
		switch record.Status {
		case RecordCreating, RecordReady, RecordDeleting, RecordDeleted:
		default:
			return fmt.Errorf("profile directory entry %q has unsupported status %q", record.ID, record.Status)
		}
		if _, exists := records[record.ID]; exists {
			return fmt.Errorf("profile directory has duplicate ID %q", record.ID)
		}
		if previous, exists := homes[record.HomeName]; exists {
			return fmt.Errorf("profile directory entries %q and %q share one Home", previous, record.ID)
		}
		homes[record.HomeName] = record.ID
		records[record.ID] = record
	}
	d.records, d.revision = records, data.Revision
	return nil
}

func (d *directory) writeLocked() error {
	if d.path == "" {
		return ErrDirectoryReadOnly
	}
	browsers := make([]Record, 0, len(d.records))
	for _, record := range d.records {
		browsers = append(browsers, record)
	}
	sort.Slice(browsers, func(i, j int) bool { return browsers[i].ID < browsers[j].ID })
	encoded, err := json.MarshalIndent(directoryFile{Version: directoryVersion, Revision: d.revision, Browsers: browsers}, "", "  ")
	if err != nil {
		return fmt.Errorf("encode profile directory: %w", err)
	}
	encoded = append(encoded, '\n')
	temp, err := os.CreateTemp(filepath.Dir(d.path), ".profile-directory-*")
	if err != nil {
		return fmt.Errorf("create temporary profile directory: %w", err)
	}
	name := temp.Name()
	keep := false
	defer func() {
		temp.Close()
		if !keep {
			os.Remove(name)
		}
	}()
	if err := temp.Chmod(0o600); err != nil {
		return fmt.Errorf("protect profile directory: %w", err)
	}
	if _, err := temp.Write(encoded); err != nil {
		return fmt.Errorf("write profile directory: %w", err)
	}
	if err := temp.Sync(); err != nil {
		return fmt.Errorf("sync profile directory: %w", err)
	}
	if err := temp.Close(); err != nil {
		return fmt.Errorf("close profile directory: %w", err)
	}
	if err := os.Rename(name, d.path); err != nil {
		return fmt.Errorf("replace profile directory: %w", err)
	}
	keep = true
	if dir, err := os.Open(filepath.Dir(d.path)); err == nil {
		_ = dir.Sync()
		dir.Close()
	}
	return nil
}

// update applies a patch under optimistic locking. Only display fields and
// the enabled flag may change here; identity, Home, application, network and
// capability fields are immutable through this path.
func (d *directory) update(id string, expectedRevision int, actor string, patch BrowserPatch) (Record, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.path == "" {
		return Record{}, ErrDirectoryReadOnly
	}
	current, ok := d.records[id]
	if !ok {
		return Record{}, ErrProfileNotFound
	}
	if current.Status != RecordReady {
		return Record{}, fmt.Errorf("profile record is %s", current.Status)
	}
	if current.Revision != expectedRevision {
		return Record{}, ErrRevisionMismatch
	}
	next := current
	next.RequiredRuntimeCapabilities = cloneCapabilities(current.RequiredRuntimeCapabilities)
	if patch.Label != nil {
		next.Label = *patch.Label
	}
	if patch.StartURL != nil {
		next.StartURL = *patch.StartURL
	}
	if patch.Disabled != nil {
		next.Disabled = *patch.Disabled
	}
	if err := validateDefinition(next.Definition); err != nil {
		return Record{}, err
	}
	if next.Label == current.Label && next.StartURL == current.StartURL && next.Disabled == current.Disabled {
		return current, nil
	}
	next.Revision = current.Revision + 1
	next.UpdatedAt, next.UpdatedBy = d.now().UTC(), actor
	previousRecords, previousRevision := d.records[id], d.revision
	d.records[id], d.revision = next, d.revision+1
	if err := d.writeLocked(); err != nil {
		d.records[id], d.revision = previousRecords, previousRevision
		return Record{}, err
	}
	return next, nil
}

func (d *directory) add(record Record) error {
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.path == "" {
		return ErrDirectoryReadOnly
	}
	if record.Status == "" {
		record.Status = RecordCreating
	}
	if err := validateDefinition(record.Definition); err != nil {
		return err
	}
	if _, exists := d.records[record.ID]; exists {
		return fmt.Errorf("profile ID %q already exists", record.ID)
	}
	for _, current := range d.records {
		if current.Status != RecordDeleted && current.HomeName == record.HomeName {
			return fmt.Errorf("Home %q is already assigned", record.HomeName)
		}
	}
	if record.Revision == 0 {
		record.Revision = 1
	}
	if record.UpdatedAt.IsZero() {
		record.UpdatedAt = d.now().UTC()
	}
	previous := d.revision
	d.records[record.ID], d.revision = record, d.revision+1
	if err := d.writeLocked(); err != nil {
		delete(d.records, record.ID)
		d.revision = previous
		return err
	}
	return nil
}

func (d *directory) status(id, status, actor string) (Record, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if d.path == "" {
		return Record{}, ErrDirectoryReadOnly
	}
	record, ok := d.records[id]
	if !ok {
		return Record{}, ErrProfileNotFound
	}
	if status != RecordDeleting && status != RecordDeleted && status != RecordReady {
		return Record{}, errors.New("invalid profile record status")
	}
	if record.Status == RecordDeleted && status != RecordDeleted {
		return Record{}, ErrBrowserDeleted
	}
	previous := record
	previousRevision := d.revision
	record.Status = status
	record.Revision++
	record.UpdatedAt, record.UpdatedBy = d.now().UTC(), actor
	d.records[id], d.revision = record, d.revision+1
	if err := d.writeLocked(); err != nil {
		d.records[id], d.revision = previous, previousRevision
		return Record{}, err
	}
	return record, nil
}
