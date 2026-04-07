#!/usr/bin/env python3
"""
Custom sliding-window receiver with:
  1. Out-of-order packet buffering
  2. Cumulative ACKs with SACK information
  3. In-order file writes
"""
import sys, os, socket, configparser
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../Monitor'))
from monitor import Monitor

# Packet markers
FIN    = b'FIN\n'
FINACK = b'FINACK\n'


def make_ack(cum_seq: int, rwnd: int, sack_set=None) -> bytes:
    """Build ACK with advertised window and optional SACK block.
    cum_seq: highest in-order sequence number received (-1 if none yet).
    rwnd: receiver's available buffer space (packets).
    sack_set: set of out-of-order sequence numbers buffered.
    Format: 'ACK <cum_seq>\nRWND <rwnd>\nSACK <s1>,<s2>,...\n'
    """
    msg = f'ACK {cum_seq}\nRWND {rwnd}\n'.encode()
    if sack_set:
        sack_str = ','.join(str(s) for s in sorted(sack_set))
        msg += f'SACK {sack_str}\n'.encode()
    return msg


if __name__ == '__main__':
    config_path = sys.argv[1]

    recv_monitor = Monitor(config_path, 'receiver')

    cfg = configparser.RawConfigParser(allow_no_value=True)
    cfg.read(config_path)
    sender_id      = int(cfg.get('sender', 'id'))
    max_pkt_size   = int(cfg.get('network', 'MAX_PACKET_SIZE'))
    write_location = cfg.get('receiver', 'write_location')
    window_size    = int(cfg.get('sender', 'window_size'))

    # Clamp buffer to max allowed
    max_buffer = max(window_size, 50)

    # --- Receiver state ---
    expected_seq = 0          # next in-order sequence number
    buffer = {}               # out-of-order: seq -> chunk
    file_done = False

    with open(write_location, 'wb') as f:
        while True:
            addr, data = recv_monitor.recv(max_pkt_size)
            if data is None:
                continue

            # Check for FIN
            if data.strip() == FIN.strip():
                recv_monitor.send(sender_id, FINACK)
                break

            # Parse: '{seq}\n{chunk}'
            try:
                newline = data.index(b'\n')
                seq = int(data[:newline])
                chunk = data[newline + 1:]
            except (ValueError, IndexError):
                continue

            if seq == expected_seq:
                # In-order: write immediately, then flush any buffered
                f.write(chunk)
                expected_seq += 1
                # Flush contiguous buffered packets
                while expected_seq in buffer:
                    f.write(buffer.pop(expected_seq))
                    expected_seq += 1
            elif seq > expected_seq:
                # Out-of-order: buffer it (if not already and within limit)
                if seq not in buffer and len(buffer) < max_buffer:
                    buffer[seq] = chunk

            # Send cumulative ACK (expected_seq - 1 = last in-order received)
            # Include advertised window and SACK info
            cum_ack = expected_seq - 1
            rwnd = max_buffer - len(buffer)
            sack_info = set(buffer.keys()) if buffer else None
            recv_monitor.send(addr, make_ack(cum_ack, rwnd, sack_info))

    # Verify received file
    recv_monitor.recv_end(write_location, sender_id)

    # Keep ACKing retransmitted FINs until emulator shuts down
    recv_monitor.socketfd.settimeout(2.0)
    while True:
        try:
            addr, data = recv_monitor.recv(max_pkt_size)
            if data and data.strip() == FIN.strip():
                recv_monitor.send(sender_id, FINACK)
        except socket.timeout:
            break
        except Exception:
            break
