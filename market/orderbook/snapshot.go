package orderbook

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"github.com/shopspring/decimal"
	"github.com/tent-of-trials/market/types"
)

type persistedOrder struct {
	ID        string `json:"id"`
	Side      string `json:"side"`
	Price     string `json:"price"`
	Quantity  string `json:"quantity"`
	Status    string `json:"status"`
	CreatedAt int64  `json:"created_at"`
	UpdatedAt int64  `json:"updated_at"`
}

type snapshotState struct {
	Symbol    string           `json:"symbol"`
	Sequence  uint64           `json:"sequence"`
	UpdatedAt int64            `json:"updated_at"`
	Bids      []persistedLevel `json:"bids"`
	Asks      []persistedLevel `json:"asks"`
	Orders    []persistedOrder `json:"orders"`
}

type persistedLevel struct {
	Price    string `json:"price"`
	Quantity string `json:"quantity"`
	Count    int    `json:"count"`
}

// Snapshot serializes the full order book state to deterministic JSON.
func (ob *OrderBook) Snapshot() ([]byte, error) {
	ob.mu.RLock()
	defer ob.mu.RUnlock()

	state := snapshotState{
		Symbol:    string(ob.symbol),
		Sequence:  ob.sequence,
		UpdatedAt: ob.updatedAt.UnixMilli(),
		Bids:      levelsToPersisted(ob.bids),
		Asks:      levelsToPersisted(ob.asks),
		Orders:    ordersToPersisted(ob.orders),
	}
	sort.Slice(state.Orders, func(i, j int) bool {
		return state.Orders[i].ID < state.Orders[j].ID
	})
	return json.Marshal(state)
}

// Recover restores order book state from a snapshot payload.
func (ob *OrderBook) Recover(data []byte) error {
	var state snapshotState
	if err := json.Unmarshal(data, &state); err != nil {
		return fmt.Errorf("decode snapshot: %w", err)
	}

	ob.mu.Lock()
	defer ob.mu.Unlock()

	if ob.closed {
		return ErrBookClosed
	}

	ob.symbol = typesSymbol(state.Symbol)
	ob.sequence = state.Sequence
	ob.bids = persistedToLevels(state.Bids)
	ob.asks = persistedToLevels(state.Asks)
	ob.orders = make(map[string]*types.Order, len(state.Orders))
	for _, item := range state.Orders {
		order, err := persistedToOrder(item)
		if err != nil {
			return err
		}
		ob.orders[order.ID] = order
	}
	return nil
}

// WriteSnapshotFile writes snapshot JSON and a SHA-256 checksum sidecar.
func WriteSnapshotFile(path string, payload []byte) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(path, payload, 0o644); err != nil {
		return err
	}
	sum := sha256.Sum256(payload)
	checksumPath := path + ".sha256"
	return os.WriteFile(checksumPath, []byte(hex.EncodeToString(sum[:])+"\n"), 0o644)
}

// ReadSnapshotFile loads snapshot JSON after validating checksum.
func ReadSnapshotFile(path string) ([]byte, error) {
	payload, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	checksumPath := path + ".sha256"
	expected, err := os.ReadFile(checksumPath)
	if err != nil {
		return nil, fmt.Errorf("missing checksum: %w", err)
	}
	sum := sha256.Sum256(payload)
	if hex.EncodeToString(sum[:]) != string(bytesTrimSpace(expected)) {
		return nil, fmt.Errorf("snapshot checksum mismatch")
	}
	return payload, nil
}

func levelsToPersisted(levels []*types.Level) []persistedLevel {
	out := make([]persistedLevel, 0, len(levels))
	for _, level := range levels {
		if level == nil {
			continue
		}
		out = append(out, persistedLevel{
			Price:    level.Price.String(),
			Quantity: level.Quantity.String(),
			Count:    level.Count,
		})
	}
	return out
}

func persistedToLevels(levels []persistedLevel) []*types.Level {
	out := make([]*types.Level, 0, len(levels))
	for _, level := range levels {
		price, err := decimalParse(level.Price)
		if err != nil {
			continue
		}
		qty, err := decimalParse(level.Quantity)
		if err != nil {
			continue
		}
		out = append(out, &types.Level{Price: price, Quantity: qty, Count: level.Count})
	}
	return out
}

func ordersToPersisted(orders map[string]*types.Order) []persistedOrder {
	out := make([]persistedOrder, 0, len(orders))
	for _, order := range orders {
		if order == nil {
			continue
		}
		out = append(out, persistedOrder{
			ID:        order.ID,
			Side:      order.Side.String(),
			Price:     order.Price.String(),
			Quantity:  order.RemainingQty.String(),
			Status:    fmt.Sprintf("%d", int(order.Status)),
			CreatedAt: order.CreatedAt.UnixMilli(),
			UpdatedAt: order.UpdatedAt.UnixMilli(),
		})
	}
	return out
}

func persistedToOrder(item persistedOrder) (*types.Order, error) {
	price, err := decimalParse(item.Price)
	if err != nil {
		return nil, err
	}
	qty, err := decimalParse(item.Quantity)
	if err != nil {
		return nil, err
	}
	side := types.Buy
	if item.Side == "sell" {
		side = types.Sell
	}
	return &types.Order{
		ID:           item.ID,
		Side:         side,
		Price:        price,
		RemainingQty: qty,
	}, nil
}

func typesSymbol(symbol string) types.Symbol {
	return types.Symbol(symbol)
}

func decimalParse(value string) (decimal.Decimal, error) {
	return decimal.NewFromString(value)
}

func bytesTrimSpace(value []byte) string {
	return string(bytesTrim(value))
}

func bytesTrim(value []byte) []byte {
	for len(value) > 0 && (value[0] == ' ' || value[0] == '\n' || value[0] == '\r' || value[0] == '\t') {
		value = value[1:]
	}
	for len(value) > 0 {
		last := value[len(value)-1]
		if last != ' ' && last != '\n' && last != '\r' && last != '\t' {
			break
		}
		value = value[:len(value)-1]
	}
	return value
}
