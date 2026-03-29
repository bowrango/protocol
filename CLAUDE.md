# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A simulation framework for implementing and comparing reliable data transfer protocols (Stop-and-Go vs. Sliding Window) over an emulated unreliable network. The project is educational — the `src/custom/` protocol is the main thing to implement/improve.

## Running the System

All three components must run simultaneously using the same config file. Start them in order across separate terminals:

```bash
# Terminal 1 — start emulator first
cd Emulator && python3 emulator.py ../TestConfig/config1.ini

# Terminal 2 — start receiver (~1 sec after emulator)
cd src/baseline && make run-receiver config=../../TestConfig/config1.ini

# Terminal 3 — start sender (~1 sec after receiver)
cd src/baseline && make run-sender config=../../TestConfig/config1.ini
```

The Makefile kills any process holding the port before starting, so stale processes aren't a problem. Substitute `src/custom` or `src/example` for a different implementation.

Check results in `sender_monitor.log` (goodput/overhead) and `receiver_monitor.log` (file correctness).

## Test Configs

| Config | Drop % | Reorder % | Use |
|--------|--------|-----------|-----|
| `config1.ini` | 0% | 0% | Baseline correctness |
| `config2.ini` | 2% | 0% | Loss handling |
| `config3.ini` | 2% | 2% | Loss + reorder |

## Architecture

Packets flow: `Sender → Emulator (LatencyQueue → SendingQueue) → Receiver`

### Monitor (`Monitor/monitor.py`)
The interface every sender/receiver uses. Wraps UDP sockets, formats packets as `{source_id} {dest_id}\n{data}`, and tracks metrics.

- `send(dest_id, data)` / `recv(size)` — I/O
- `send_end(dest_id)` — called by sender after final ACK; shuts down emulator
- `recv_end(recv_file, sender_id)` — called by receiver after file is written; checks correctness

**Shutdown order matters**: receiver calls `recv_end()` first and keeps ACKing, then sender calls `send_end()`. If sender exits first, the receiver loops forever retransmitting.

### Emulator (`Emulator/emulator.py`)
Simulates an unreliable link:
- `LatencyQueue`: introduces `PROP_DELAY` propagation delay
- `SendingQueue`: enforces `LINK_BANDWIDTH`, applies drops and reordering
- Drop model 1 = fixed probability; model 2 = dynamic (congestion-based)
- Shuts down when it receives the sentinel packet `0 0\n` (sent by `send_end()`)

### Protocol Implementations (`src/`)
- `example/` — minimal reference (echo-style)
- `baseline/` — Stop-and-Go: one packet in flight, alternating sequence numbers, timeout = `4 × PROP_DELAY + 0.5s`
- `custom/` — Sliding Window with cumulative ACKs (implement here); window size set via `window_size` in config

## Key Config Parameters

```ini
PROP_DELAY = 0.1           # seconds; drives timeout calculation
MAX_PACKET_SIZE = 1024     # bytes; usable payload = MAX_PACKET_SIZE - 10
LINK_BANDWIDTH = 200000    # bytes/sec
RANDOM_DROP_PROBABILITY = 0.02
REORDER_PROBABILITY = 0.02
window_size = 10           # sliding window size (custom protocol)
```

## Implementing the Custom Protocol

The `src/custom/` sender and receiver stubs are empty. The expected design:

**Sender**: maintain a window of `W` unacked packets; advance on ACK; retransmit all unacked on timeout.

**Receiver**: accept out-of-order packets into a buffer; send cumulative ACKs (`ACK(n)` acknowledges all packets ≤ n); write to file in order.

After completing the file, the receiver must call `Monitor.recv_end()` and continue ACKing retransmits. The sender calls `Monitor.send_end()` only after receiving the ACK for the final data packet.
