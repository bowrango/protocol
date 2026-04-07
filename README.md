# Reliable Data Transmission Protocol

A project implementing and optimising reliable data transfer protocols over an emulated unreliable network.

## Overview

The system consists of three components:

- **Network Emulator** (`Emulator/emulator.py`) — simulates an unreliable network link, introducing configurable packet loss, reordering, propagation delay, and bandwidth limits.
- **Network Monitor** (`Monitor/monitor.py`) — an interface layer that each sender/receiver instantiates to communicate through the emulator.
- **Protocol Implementations** (`src/`) — sender and receiver implementations using different protocol strategies.

## Project Structure

```
.
├── Emulator/                   # Network emulator
├── Monitor/                    # Network monitor
├── TestConfig/                 # Sample configuration files
├── data/                       # Files used for transmission tests
├── src/
│   ├── baseline/               # Stop-and-Go protocol implementation
│   ├── custom/                 # Sliding window protocol (implemented)
│   └── example/                # Reference example
├── base_config.ini             # Base configuration template
├── run_experiments.py          # Automated experiment runner
├── generate_latex_results.py   # Converts results JSON → LaTeX macros
├── generate_plots.py           # Generates variance bar-chart figures
├── report/                     # Lab report directory
│   ├── experiment scripts      # Run in background process
│   ├── results.tex             # Auto-generated LaTeX macros
│   └── figures/                # Generated variance plots
```

## Quick Start

Run all three components in order, using the same config file.

**1. Start the emulator:**
```bash
cd Emulator
python3 emulator.py ../TestConfig/config1.ini
```

**2. Start the receiver** (in its implementation directory):
```bash
make run-receiver config=../../TestConfig/config1.ini
# or
python3 receiver.py ../../TestConfig/config1.ini
```

**3. Start the sender** (after ~1 second delay):
```bash
make run-sender config=../../TestConfig/config1.ini
# or
python3 sender.py ../../TestConfig/config1.ini
```

Logs are written to `sender_monitor.log` (goodput/overhead metrics) and `receiver_monitor.log` (correctness check).

## Monitor API

Each sender and receiver instantiates a `Monitor` object, passing the config file path and the appropriate header (`sender` or `receiver`).

| Method | Description |
|---|---|
| `Monitor.send(dest, data)` | Send a packet to `dest` via the emulator (calls `socket.sendto()`) |
| `Monitor.recv(bytes)` | Receive an incoming packet (calls `socket.recvfrom()`) |
| `Monitor.send_end(dest_id)` | Called by sender after the final ACK is received — shuts down the emulator |
| `Monitor.recv_end(recv_file, sender_id)` | Called by receiver after the full file is written — checks correctness |

### Shutdown Order

The shutdown sequence matters:

1. Receiver receives the final packet and calls `Monitor.recv_end()`, then keeps running and continues ACKing any retransmitted packets.
2. Sender receives the ACK for the final packet and calls `Monitor.send_end()`.

This ordering handles the case where the receiver's ACK is dropped since if the receiver quit immediately, the sender would retransmit forever with no response.

## Configuration

Configuration files control both the emulator and the endpoints. See `base_config.ini` for a documented template.

Key parameters:

| Parameter | Description |
|---|---|
| `PROP_DELAY` | Propagation delay (seconds) |
| `MAX_PACKET_SIZE` | Maximum packet size (bytes) |
| `LINK_BANDWIDTH` | Link bandwidth (bytes/sec) |
| `RANDOM_DROP_PROBABILITY` | Probability of dropping a packet |
| `REORDER_PROBABILITY` | Probability of reordering a packet |
| `window_size` | Sender sliding window size (packets) |

## Protocols

### Baseline (`src/baseline/`)

The sender transmits one packet and waits for its ACK before sending the next. On timeout, the packet is retransmitted. Simple and low-overhead, but goodput is limited by the round-trip time.

### Custom (`src/custom/`)

The sender maintains a window of `W` unacknowledged packets in flight. The receiver uses cumulative ACKs with selective ACK (SACK) piggyback. Features include dynamic EWMA timeout estimation (Karn's algorithm), fast retransmit on 3 duplicate ACKs, and SACK-guided selective retransmission.

## Report

### `run_experiments.py`

Runs the stop-and-go baseline across three bandwidth settings (200,000 / 20,000 / 2,000 bytes/s), each with 2% packet loss and 2% reordering, using `data/to_send_large.txt` as the payload. Results are saved to `experiment_results.json` after each bandwidth group, so the script can be safely interrupted and resumed.

```bash
python3 run_experiments.py
```

### `generate_latex_results.py`

Reads `experiment_results.json` and writes `report/results.tex`, which defines `\renewcommand` macros for every mean[std] value in the report. The report automatically `\input`s this file on compilation, so re-running this script and recompiling the PDF is all that is needed to update the numbers.

```bash
python3 generate_latex_results.py
cd report && pdflatex matt.bowring.Project3.final.tex
```

### `generate_plots.py`

Reads `experiment_results.json` and writes `figures/goodput_variance.pdf` and `figures/overhead_variance.pdf` — grouped bar charts showing per-run goodput and overhead for the custom protocol vs. stop-and-go.

```bash
python3 generate_plots.py
```

Requires both `sng_200k` and `custom_200k` entries to be present in `experiment_results.json`.
