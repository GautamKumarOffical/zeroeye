package orderbook

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"time"

	"github.com/tent-of-trials/market/types"
)

type SnapshotManager struct {
	books     map[types.Symbol]*OrderBook
	dataDir   string
	interval  time.Duration
	mu        sync.Mutex
	stopCh    chan struct{}
	stopped   bool
}

func NewSnapshotManager(books map[types.Symbol]*OrderBook, dataDir string) *SnapshotManager {
	intervalSecs := DefaultSnapshotIntervalSecs
	if envVal := os.Getenv("OB_SNAPSHOT_INTERVAL_SECS"); envVal != "" {
		if parsed, err := strconv.Atoi(envVal); err == nil && parsed > 0 {
			intervalSecs = parsed
		}
	}

	return &SnapshotManager{
		books:    books,
		dataDir:  dataDir,
		interval: time.Duration(intervalSecs) * time.Second,
		stopCh:   make(chan struct{}),
	}
}

func (sm *SnapshotManager) Start() {
	go sm.snapshotLoop()
}

func (sm *SnapshotManager) Stop() {
	sm.mu.Lock()
	defer sm.mu.Unlock()
	if !sm.stopped {
		close(sm.stopCh)
		sm.stopped = true
	}
}

func (sm *SnapshotManager) snapshotLoop() {
	ticker := time.NewTicker(sm.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			sm.SaveAll()
		case <-sm.stopCh:
			return
		}
	}
}

func (sm *SnapshotManager) SaveAll() error {
	sm.mu.Lock()
	defer sm.mu.Unlock()

	if err := os.MkdirAll(sm.dataDir, 0755); err != nil {
		return fmt.Errorf("failed to create data directory: %w", err)
	}

	for symbol, book := range sm.books {
		if err := sm.saveBook(symbol, book); err != nil {
			return fmt.Errorf("failed to save snapshot for %s: %w", symbol, err)
		}
	}

	return nil
}

func (sm *SnapshotManager) saveBook(symbol types.Symbol, book *OrderBook) error {
	data, err := book.Snapshot()
	if err != nil {
		return err
	}

	snapshotPath := filepath.Join(sm.dataDir, SnapshotFileName)
	checksumPath := filepath.Join(sm.dataDir, SnapshotChecksumFileName)

	if err := os.WriteFile(snapshotPath, data, 0644); err != nil {
		return fmt.Errorf("failed to write snapshot: %w", err)
	}

	checksum := sha256.Sum256(data)
	checksumHex := fmt.Sprintf("%x", checksum)

	if err := os.WriteFile(checksumPath, []byte(checksumHex), 0644); err != nil {
		return fmt.Errorf("failed to write checksum: %w", err)
	}

	return nil
}

func (sm *SnapshotManager) LoadAll() error {
	sm.mu.Lock()
	defer sm.mu.Unlock()

	snapshotPath := filepath.Join(sm.dataDir, SnapshotFileName)
	checksumPath := filepath.Join(sm.dataDir, SnapshotChecksumFileName)

	if _, err := os.Stat(snapshotPath); os.IsNotExist(err) {
		return nil
	}

	data, err := os.ReadFile(snapshotPath)
	if err != nil {
		return fmt.Errorf("failed to read snapshot: %w", err)
	}

	expectedChecksum, err := os.ReadFile(checksumPath)
	if err != nil {
		return fmt.Errorf("failed to read checksum file: %w", err)
	}

	actualChecksum := sha256.Sum256(data)
	actualChecksumHex := fmt.Sprintf("%x", actualChecksum)

	if string(expectedChecksum) != actualChecksumHex {
		return fmt.Errorf("snapshot checksum mismatch: expected %s, got %s", string(expectedChecksum), actualChecksumHex)
	}

	for symbol, book := range sm.books {
		if err := book.Recover(data); err != nil {
			return fmt.Errorf("failed to recover order book %s: %w", symbol, err)
		}
	}

	return nil
}

func (sm *SnapshotManager) TriggerSnapshot() error {
	return sm.SaveAll()
}
