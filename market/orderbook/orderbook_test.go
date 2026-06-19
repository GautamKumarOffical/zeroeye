package orderbook

import (
	"testing"

	"github.com/shopspring/decimal"
	"github.com/tent-of-trials/market/types"
)

// newTestOrder creates a test order with the given side and price for use in orderbook tests.
func newTestOrder(side types.OrderSide, price float64) *types.Order {
	p := decimal.NewFromFloat(price)
	qty := decimal.NewFromFloat(1.0)
	return &types.Order{
		Side:         side,
		Type:         types.Limit,
		Price:        p,
		Quantity:     qty,
		RemainingQty: qty,
	}
}

// TestCancelBidRemovesLevelAndDeletesOrder verifies that cancelling a bid removes the level and order ID from the book.
func TestCancelBidRemovesLevelAndDeletesOrder(t *testing.T) {
	ob := NewOrderBook("BTC/USD", Config{MaxDepth: 10, PriceDecimals: 2, VolumeDecimals: 8})

	order := newTestOrder(types.Buy, 100.0)
	if _, err := ob.AddOrder(order); err != nil {
		t.Fatalf("AddOrder failed: %v", err)
	}
	orderID := order.ID

	bids := ob.GetBids()
	if len(bids) != 1 {
		t.Fatalf("expected 1 bid level, got %d", len(bids))
	}

	if err := ob.CancelOrder(orderID); err != nil {
		t.Fatalf("CancelOrder failed: %v", err)
	}

	bids = ob.GetBids()
	if len(bids) != 0 {
		t.Fatalf("expected 0 bid levels after cancel, got %d", len(bids))
	}

	// cancelling again should return ErrOrderNotFound
	if err := ob.CancelOrder(orderID); err != ErrOrderNotFound {
		t.Fatalf("expected ErrOrderNotFound on re-cancel, got %v", err)
	}
}

// TestCancelAskRemovesLevel verifies that cancelling an ask removes the matching ask level from the book.
func TestCancelAskRemovesLevel(t *testing.T) {
	ob := NewOrderBook("ETH/USD", Config{MaxDepth: 10, PriceDecimals: 2, VolumeDecimals: 8})

	order := newTestOrder(types.Sell, 200.0)
	if _, err := ob.AddOrder(order); err != nil {
		t.Fatalf("AddOrder failed: %v", err)
	}

	asks := ob.GetAsks()
	if len(asks) != 1 {
		t.Fatalf("expected 1 ask level, got %d", len(asks))
	}

	if err := ob.CancelOrder(order.ID); err != nil {
		t.Fatalf("CancelOrder failed: %v", err)
	}

	asks = ob.GetAsks()
	if len(asks) != 0 {
		t.Fatalf("expected 0 ask levels after cancel, got %d", len(asks))
	}
}

// TestCancelUnknownOrderReturnsErrOrderNotFound verifies that cancelling a non-existent order returns the appropriate error.
func TestCancelUnknownOrderReturnsErrOrderNotFound(t *testing.T) {
	ob := NewOrderBook("BTC/USD", Config{MaxDepth: 10, PriceDecimals: 2, VolumeDecimals: 8})

	err := ob.CancelOrder("nonexistent-id-12345")
	if err != ErrOrderNotFound {
		t.Fatalf("expected ErrOrderNotFound, got %v", err)
	}
}

// TestClosedBookRejectsAddAndCancel verifies that a closed order book rejects both add and cancel operations.
func TestClosedBookRejectsAddAndCancel(t *testing.T) {
	ob := NewOrderBook("BTC/USD", Config{MaxDepth: 10, PriceDecimals: 2, VolumeDecimals: 8})

	order := newTestOrder(types.Buy, 100.0)
	if _, err := ob.AddOrder(order); err != nil {
		t.Fatalf("AddOrder failed: %v", err)
	}

	ob.Close()

	// adding to closed book should fail
	newOrder := newTestOrder(types.Sell, 200.0)
	if _, err := ob.AddOrder(newOrder); err != ErrBookClosed {
		t.Fatalf("expected ErrBookClosed on AddOrder to closed book, got %v", err)
	}

	// cancelling from closed book should fail
	if err := ob.CancelOrder(order.ID); err != ErrBookClosed {
		t.Fatalf("expected ErrBookClosed on CancelOrder to closed book, got %v", err)
	}
}

// TestSnapshotReturnsCopies verifies that snapshots return copies so callers cannot mutate internal bid/ask slices.
func TestSnapshotReturnsCopies(t *testing.T) {
	ob := NewOrderBook("BTC/USD", Config{MaxDepth: 10, PriceDecimals: 2, VolumeDecimals: 8})

	bid := newTestOrder(types.Buy, 100.0)
	ask := newTestOrder(types.Sell, 200.0)
	if _, err := ob.AddOrder(bid); err != nil {
		t.Fatalf("AddOrder bid failed: %v", err)
	}
	if _, err := ob.AddOrder(ask); err != nil {
		t.Fatalf("AddOrder ask failed: %v", err)
	}

	snap := ob.GetSnapshot()
	if len(snap.Bids) != 1 || len(snap.Asks) != 1 {
		t.Fatalf("expected 1 bid and 1 ask in snapshot, got %d bids and %d asks", len(snap.Bids), len(snap.Asks))
	}

	// mutate the snapshot
	origBidPrice := snap.Bids[0].Price
	snap.Bids[0].Price = decimal.NewFromFloat(9999.0)

	// internal bids should be unaffected
	bids := ob.GetBids()
	if !bids[0].Price.Equal(origBidPrice) {
		t.Fatalf("snapshot mutation leaked into internal bids: expected %v, got %v", origBidPrice, bids[0].Price)
	}
}

// TestCancelBidPreservesOtherLevels verifies that cancelling one bid preserves other bid levels.
func TestCancelBidPreservesOtherLevels(t *testing.T) {
	ob := NewOrderBook("BTC/USD", Config{MaxDepth: 10, PriceDecimals: 2, VolumeDecimals: 8})

	o1 := newTestOrder(types.Buy, 100.0)
	o2 := newTestOrder(types.Buy, 99.0)
	o3 := newTestOrder(types.Buy, 98.0)

	for _, o := range []*types.Order{o1, o2, o3} {
		if _, err := ob.AddOrder(o); err != nil {
			t.Fatalf("AddOrder failed: %v", err)
		}
	}

	if err := ob.CancelOrder(o2.ID); err != nil {
		t.Fatalf("CancelOrder failed: %v", err)
	}

	bids := ob.GetBids()
	if len(bids) != 2 {
		t.Fatalf("expected 2 bid levels after cancel, got %d", len(bids))
	}
	// Verify the correct price levels remain (100.0 and 98.0, not 99.0)
	if bids[0].Price.Equal(decimal.NewFromFloat(99.0)) {
		t.Fatalf("wrong level preserved: price 99.0 should have been cancelled")
	}
	if !bids[0].Price.Equal(decimal.NewFromFloat(100.0)) {
		t.Fatalf("expected top bid at 100.0, got %v", bids[0].Price)
	}
	if !bids[1].Price.Equal(decimal.NewFromFloat(98.0)) {
		t.Fatalf("expected second bid at 98.0, got %v", bids[1].Price)
	}
}

// TestAddMultipleOrdersAndCancelOne verifies that adding multiple orders then cancelling one behaves correctly.
func TestAddMultipleOrdersAndCancelOne(t *testing.T) {
	ob := NewOrderBook("BTC/USD", Config{MaxDepth: 10, PriceDecimals: 2, VolumeDecimals: 8})

	bid1 := newTestOrder(types.Buy, 100.0)
	bid2 := newTestOrder(types.Buy, 100.0)
	ask1 := newTestOrder(types.Sell, 200.0)

	for _, o := range []*types.Order{bid1, bid2, ask1} {
		if _, err := ob.AddOrder(o); err != nil {
			t.Fatalf("AddOrder failed: %v", err)
		}
	}

	if err := ob.CancelOrder(bid1.ID); err != nil {
		t.Fatalf("CancelOrder failed: %v", err)
	}

	bids := ob.GetBids()
	asks := ob.GetAsks()
	if len(bids) != 1 {
		t.Fatalf("expected 1 bid level after cancel, got %d", len(bids))
	}
	if len(asks) != 1 {
		t.Fatalf("expected 1 ask level, got %d", len(asks))
	}
	// Verify remaining bid has correct price and count
	if !bids[0].Price.Equal(decimal.NewFromFloat(100.0)) {
		t.Fatalf("expected remaining bid at 100.0, got %v", bids[0].Price)
	}
	if bids[0].Count != 1 {
		t.Fatalf("expected 1 order at 100.0 after cancel, got %d", bids[0].Count)
	}
}
