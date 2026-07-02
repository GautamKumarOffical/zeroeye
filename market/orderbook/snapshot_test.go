package orderbook

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/tent-of-trials/market/types"
)

func TestSnapshotRecoverRoundTrip(t *testing.T) {
	book := NewOrderBook("BTC-USD", Config{MaxDepth: 10, PriceDecimals: 8, VolumeDecimals: 8})
	order := &types.Order{
		ID:           "ord-1",
		Side:         types.Buy,
		Price:        decimal.RequireFromString("100"),
		RemainingQty: decimal.RequireFromString("1.5"),
	}
	if _, err := book.AddOrder(order); err != nil {
		t.Fatalf("add order: %v", err)
	}

	payload, err := book.Snapshot()
	if err != nil {
		t.Fatalf("snapshot: %v", err)
	}

	restored := NewOrderBook("BTC-USD", Config{MaxDepth: 10, PriceDecimals: 8, VolumeDecimals: 8})
	if err := restored.Recover(payload); err != nil {
		t.Fatalf("recover: %v", err)
	}

	if len(restored.orders) != 1 {
		t.Fatalf("expected 1 order, got %d", len(restored.orders))
	}
}

func TestWriteAndReadSnapshotFileChecksum(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "orderbook_snapshot.json")
	payload := []byte(`{"symbol":"BTC-USD","sequence":1}`)
	if err := WriteSnapshotFile(path, payload); err != nil {
		t.Fatalf("write snapshot: %v", err)
	}
	read, err := ReadSnapshotFile(path)
	if err != nil {
		t.Fatalf("read snapshot: %v", err)
	}
	if string(read) != string(payload) {
		t.Fatalf("payload mismatch")
	}
	if _, err := os.Stat(path + ".sha256"); err != nil {
		t.Fatalf("checksum sidecar missing: %v", err)
	}
}
