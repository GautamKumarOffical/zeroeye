package orderbook

import (
	"encoding/json"
	"fmt"
	"sort"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/shopspring/decimal"
	"github.com/tent-of-trials/market/types"
)

const (
	DefaultSnapshotIntervalSecs = 60
	SnapshotFileName            = "orderbook_snapshot.json"
	SnapshotChecksumFileName    = "orderbook_snapshot.sha256"
)

type SnapshotData struct {
	Symbol    types.Symbol    `json:"symbol"`
	Bids      []types.Level   `json:"bids"`
	Asks      []types.Level   `json:"asks"`
	Orders    []*types.Order  `json:"orders"`
	Sequence  uint64          `json:"sequence"`
	UpdatedAt time.Time       `json:"updated_at"`
}

type Config struct {
	MaxDepth       int
	PriceDecimals  int32
	VolumeDecimals int32
}

type OrderBook struct {
	mu        sync.RWMutex
	symbol    types.Symbol
	config    Config
	bids      []*types.Level
	asks      []*types.Level
	orders    map[string]*types.Order
	sequence  uint64
	updatedAt time.Time
	closed    bool
}

func NewOrderBook(symbol types.Symbol, config Config) *OrderBook {
	return &OrderBook{
		symbol:   symbol,
		config:   config,
		bids:     make([]*types.Level, 0, config.MaxDepth),
		asks:     make([]*types.Level, 0, config.MaxDepth),
		orders:   make(map[string]*types.Order),
		sequence: 0,
	}
}

func (ob *OrderBook) AddOrder(order *types.Order) ([]*types.Trade, error) {
	ob.mu.Lock()
	defer ob.mu.Unlock()

	if ob.closed {
		return nil, ErrBookClosed
	}

	if order.ID == "" {
		order.ID = uuid.New().String()
	}

	order.CreatedAt = time.Now()
	order.UpdatedAt = time.Now()
	order.Status = types.New

	ob.orders[order.ID] = order
	ob.sequence++

	level := &types.Level{
		Price:    order.Price,
		Quantity: order.RemainingQty,
		Count:    1,
	}

	if order.Side == types.Buy {
		ob.bids = insertLevel(ob.bids, level, true)
	} else {
		ob.asks = insertLevel(ob.asks, level, false)
	}

	ob.updatedAt = time.Now()
	return nil, nil
}

func (ob *OrderBook) CancelOrder(orderID string) error {
	ob.mu.Lock()
	defer ob.mu.Unlock()

	if ob.closed {
		return ErrBookClosed
	}

	order, exists := ob.orders[orderID]
	if !exists {
		return ErrOrderNotFound
	}

	order.Status = types.Cancelled
	order.UpdatedAt = time.Now()
	delete(ob.orders, orderID)

	if order.Side == types.Buy {
		ob.bids = removeLevel(ob.bids, order.Price)
	} else {
		ob.asks = removeLevel(ob.asks, order.Price)
	}

	ob.updatedAt = time.Now()
	return nil
}

func (ob *OrderBook) GetBids() []*types.Level {
	ob.mu.RLock()
	defer ob.mu.RUnlock()

	result := make([]*types.Level, len(ob.bids))
	copy(result, ob.bids)
	return result
}

func (ob *OrderBook) GetAsks() []*types.Level {
	ob.mu.RLock()
	defer ob.mu.RUnlock()

	result := make([]*types.Level, len(ob.asks))
	copy(result, ob.asks)
	return result
}

func (ob *OrderBook) GetSnapshot() *types.DepthUpdate {
	ob.mu.RLock()
	defer ob.mu.RUnlock()

	bids := make([]types.Level, len(ob.bids))
	for i, l := range ob.bids {
		if l != nil {
			bids[i] = *l
		}
	}

	asks := make([]types.Level, len(ob.asks))
	for i, l := range ob.asks {
		if l != nil {
			asks[i] = *l
		}
	}

	return &types.DepthUpdate{
		Symbol:    ob.symbol,
		Bids:      bids,
		Asks:      asks,
		Timestamp: time.Now().UnixMilli(),
	}
}

func (ob *OrderBook) Close() {
	ob.mu.Lock()
	defer ob.mu.Unlock()
	ob.closed = true
	ob.bids = nil
	ob.asks = nil
	ob.orders = nil
}

func (ob *OrderBook) Snapshot() ([]byte, error) {
	ob.mu.RLock()
	defer ob.mu.RUnlock()

	snapshot := SnapshotData{
		Symbol:    ob.symbol,
		Bids:      make([]types.Level, len(ob.bids)),
		Asks:      make([]types.Level, len(ob.asks)),
		Orders:    make([]*types.Order, 0, len(ob.orders)),
		Sequence:  ob.sequence,
		UpdatedAt: ob.updatedAt,
	}

	for i, l := range ob.bids {
		if l != nil {
			snapshot.Bids[i] = *l
		}
	}

	for i, l := range ob.asks {
		if l != nil {
			snapshot.Asks[i] = *l
		}
	}

	for _, o := range ob.orders {
		if o != nil {
			snapshot.Orders = append(snapshot.Orders, o)
		}
	}

	data, err := json.MarshalIndent(snapshot, "", "  ")
	if err != nil {
		return nil, fmt.Errorf("failed to marshal snapshot: %w", err)
	}

	return data, nil
}

func (ob *OrderBook) Recover(data []byte) error {
	ob.mu.Lock()
	defer ob.mu.Unlock()

	var snapshot SnapshotData
	if err := json.Unmarshal(data, &snapshot); err != nil {
		return fmt.Errorf("failed to unmarshal snapshot: %w", err)
	}

	ob.symbol = snapshot.Symbol
	ob.sequence = snapshot.Sequence
	ob.updatedAt = snapshot.UpdatedAt

	ob.bids = make([]*types.Level, 0, len(snapshot.Bids))
	for _, l := range snapshot.Bids {
		level := l
		ob.bids = append(ob.bids, &level)
	}

	ob.asks = make([]*types.Level, 0, len(snapshot.Asks))
	for _, l := range snapshot.Asks {
		level := l
		ob.asks = append(ob.asks, &level)
	}

	ob.orders = make(map[string]*types.Order, len(snapshot.Orders))
	for _, o := range snapshot.Orders {
		if o != nil {
			ob.orders[o.ID] = o
		}
	}

	return nil
}

var (
	ErrBookClosed    = &BookError{"order book is closed"}
	ErrOrderNotFound = &BookError{"order not found"}
)

type BookError struct {
	message string
}

func (e *BookError) Error() string {
	return e.message
}

func insertLevel(levels []*types.Level, level *types.Level, desc bool) []*types.Level {
	levels = append(levels, level)
	sort.Slice(levels, func(i, j int) bool {
		if desc {
			return levels[i].Price.GreaterThan(levels[j].Price)
		}
		return levels[i].Price.LessThan(levels[j].Price)
	})
	return levels
}

func removeLevel(levels []*types.Level, price decimal.Decimal) []*types.Level {
	for i, l := range levels {
		if l.Price.Equal(price) {
			return append(levels[:i], levels[i+1:]...)
		}
	}
	return levels
}
