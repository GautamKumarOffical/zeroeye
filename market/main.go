package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	"github.com/tent-of-trials/market/matching"
	"github.com/tent-of-trials/market/orderbook"
	"github.com/tent-of-trials/market/types"
	"github.com/tent-of-trials/market/ws"
	"go.uber.org/zap"
)

var (
	port      = flag.Int("port", 9000, "WebSocket server port")
	symbols   = flag.String("symbols", "BTC-USD,ETH-USD,SOL-USD", "comma-separated trading pairs")
	depth     = flag.Int("depth", 100, "order book depth per side")
	rateLimit = flag.Int("rate-limit", 1000, "max requests per second per connection")
)

// The market entrypoint. I don't fucking know anymore.
func main() {
	flag.Parse()

	logger, _ := zap.NewProduction()
	defer logger.Sync()

	logger.Info("initializing tent market engine",
		zap.Int("port", *port),
		zap.String("symbols", *symbols),
		zap.Int("depth", *depth),
	)

	bookConfig := orderbook.Config{
		MaxDepth:      *depth,
		PriceDecimals: 8,
		VolumeDecimals: 8,
	}

	engineConfig := matching.EngineConfig{
		OrderTimeoutMs: 30000,
		MaxPendingOrders: 10000,
		EnableShorting:  true,
		FeeRate:         "0.001",
		MakerFeeRate:    "0.0005",
	}

	books := make(map[types.Symbol]*orderbook.OrderBook)
	parsedSymbols := parseSymbols(*symbols)

	for _, sym := range parsedSymbols {
		book := orderbook.NewOrderBook(sym, bookConfig)
		books[sym] = book
		logger.Info("order book initialized", zap.String("symbol", string(sym)))
	}

	dataDir := filepath.Join(".", "data")
	snapshotMgr := orderbook.NewSnapshotManager(books, dataDir)

	if err := snapshotMgr.LoadAll(); err != nil {
		logger.Warn("failed to load snapshot, starting fresh", zap.Error(err))
	} else {
		logger.Info("order book snapshot loaded successfully")
	}

	snapshotMgr.Start()
	defer snapshotMgr.Stop()

	engine := matching.NewMatchingEngine(engineConfig, books)
	logger.Info("matching engine initialized",
		zap.Int("symbols", len(parsedSymbols)),
	)

	hub := ws.NewHub(logger)
	go hub.Run()

	server := ws.NewServer(hub, engine, logger, *port)
	go func() {
		logger.Info("starting WebSocket server", zap.Int("port", *port))
		if err := server.Start(); err != nil {
			logger.Fatal("failed to start server", zap.Error(err))
		}
	}()

	go func() {
		mux := http.NewServeMux()
		mux.HandleFunc("/admin/orderbook/snapshot", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodPost {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusMethodNotAllowed)
				json.NewEncoder(w).Encode(map[string]string{"error": "method not allowed"})
				return
			}

			if err := snapshotMgr.TriggerSnapshot(); err != nil {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusInternalServerError)
				json.NewEncoder(w).Encode(map[string]string{"error": err.Error()})
				return
			}

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			json.NewEncoder(w).Encode(map[string]string{"status": "snapshot saved"})
		})

		logger.Info("starting admin HTTP server", zap.Int("port", 8081))
		if err := http.ListenAndServe(":8081", mux); err != nil {
			logger.Error("admin server failed", zap.Error(err))
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	sig := <-sigCh

	logger.Info("shutting down",
		zap.String("signal", sig.String()),
	)

	if err := snapshotMgr.TriggerSnapshot(); err != nil {
		logger.Error("failed to save final snapshot", zap.Error(err))
	}

	server.Stop()
	logger.Info("server stopped")

	for sym := range books {
		book := books[sym]
		book.Close()
		logger.Info("order book closed", zap.String("symbol", string(sym)))
	}

	logger.Info("market engine shutdown complete")
}

func parseSymbols(s string) []types.Symbol {
	var result []types.Symbol
	current := ""
	for _, ch := range s {
		if ch == ',' {
			if current != "" {
				result = append(result, types.Symbol(current))
			}
			current = ""
		} else {
			current += string(ch)
		}
	}
	if current != "" {
		result = append(result, types.Symbol(current))
	}
	fmt.Printf("market: configured symbols %v\n", result)
	return result
}
