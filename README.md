# Reliable Data Transmission Protocol

A project implementing and optimising reliable data transfer protocols over an emulated unreliable network.

## Overview

The system consists of three components:

- **Network Emulator** (`Emulator/emulator.py`) — simulates an unreliable network link, introducing configurable packet loss, reordering, propagation delay, and bandwidth limits.
- **Network Monitor** (`monitor.py`) — an interface layer that each sender/receiver instantiates to communicate through the emulator.
- **Protocol Implementations** (`src/`) — sender and receiver implementations using different protocol strategies.

## Project Structure

```
.
├── Emulator/           # Network emulator
├── TestConfig/         # Sample configuration files
├── files/              # Files used for transmission tests
├── src/
│   ├── baseline/       # Stop-and-Go protocol implementation
│   ├── custom/         # Sliding window protocol implementation
│   └── example/        # Reference example
└── base_config.ini     # Base configuration template
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

The sender maintains a window of `W` unacknowledged packets in flight. The receiver uses cumulative ACKs. On timeout (or detected loss), unacknowledged packets are retransmitted.
