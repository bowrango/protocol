#!/usr/bin/env python3
"""
Custom sliding-window sender with:
  1. Cumulative ACKs
  2. Selective ACK (SACK) — retransmit only missing packets
  3. Fast retransmit — 3 duplicate ACKs triggers immediate retransmit
  4. Dynamic timeout — EWMA RTT estimation (TCP-style)
"""
import sys, os, time, socket, configparser
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../Monitor'))
from monitor import Monitor

# Packet markers
FIN    = b'FIN\n'
FINACK = b'FINACK\n'


def make_data(seq: int, chunk: bytes) -> bytes:
    return f'{seq}\n'.encode() + chunk


def parse_ack(data: bytes):
    """Parse ACK packet. Returns (ack_seq, rwnd, sack_set).
    Format: 'ACK <seq>\nRWND <n>\n' optionally followed by 'SACK <s1>,<s2>,...\n'
    """
    lines = data.split(b'\n')
    ack_seq = None
    rwnd = None
    sack_set = set()
    for line in lines:
        line = line.strip()
        if line.startswith(b'ACK '):
            ack_seq = int(line[4:])
        elif line.startswith(b'RWND '):
            rwnd = int(line[5:])
        elif line.startswith(b'SACK '):
            for s in line[5:].split(b','):
                s = s.strip()
                if s:
                    sack_set.add(int(s))
    return ack_seq, rwnd, sack_set


if __name__ == '__main__':
    config_path = sys.argv[1]

    send_monitor = Monitor(config_path, 'sender')

    cfg = configparser.RawConfigParser(allow_no_value=True)
    cfg.read(config_path)
    receiver_id  = int(cfg.get('receiver', 'id'))
    file_to_send = cfg.get('nodes', 'file_to_send')
    max_pkt_size = int(cfg.get('network', 'MAX_PACKET_SIZE'))
    prop_delay   = float(cfg.get('network', 'PROP_DELAY'))
    window_size  = int(cfg.get('sender', 'window_size'))

    # Clamp window to allowed range
    max_window = max(1, min(window_size, 50))

    # Chunk the file
    chunk_size = max_pkt_size - 10
    with open(file_to_send, 'rb') as f:
        chunks = []
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            chunks.append(chunk)
    total_packets = len(chunks)

    # --- Dynamic timeout (TCP-style EWMA) ---
    ALPHA = 0.125
    BETA  = 0.25
    MIN_TIMEOUT = 0.05
    MAX_TIMEOUT = 4.0
    # Mutable container so nested functions can update: [estimated_rtt, rtt_dev, timeout]
    rtt = [2 * prop_delay, prop_delay, 0.0]
    rtt[2] = rtt[0] + 4 * rtt[1] + 0.05

    send_monitor.socketfd.settimeout(rtt[2])

    # --- Sliding window state ---
    base        = 0      # oldest unACKed sequence number
    next_seq    = 0      # next sequence number to send
    dup_ack_cnt = 0      # duplicate ACK counter
    last_ack    = -1     # last cumulative ACK received
    sacked      = set()  # selectively acknowledged packets (above base)

    # Track send times for RTT measurement (only for first transmission)
    send_times  = {}

    FAST_RETRANSMIT_THRESH = 3

    def update_timeout(sample_rtt):
        rtt[0] = (1 - ALPHA) * rtt[0] + ALPHA * sample_rtt
        rtt[1] = (1 - BETA) * rtt[1] + BETA * abs(sample_rtt - rtt[0])
        rtt[2] = max(MIN_TIMEOUT, min(MAX_TIMEOUT, rtt[0] + 4 * rtt[1] + 0.02))
        send_monitor.socketfd.settimeout(rtt[2])

    def send_packet(seq):
        pkt = make_data(seq, chunks[seq])
        send_monitor.send(receiver_id, pkt)
        if seq not in send_times:
            send_times[seq] = time.time()

    def retransmit_missing():
        for seq in range(base, next_seq):
            if seq not in sacked:
                send_times.pop(seq, None)
                send_packet(seq)

    # Advertised window from receiver (starts at configured max)
    rwnd = max_window

    # --- Main send loop ---
    while base < total_packets:
        # Fill the window, capped by receiver's advertised window
        effective_window = min(max_window, rwnd) if rwnd is not None else max_window
        while next_seq < total_packets and next_seq < base + effective_window:
            send_packet(next_seq)
            next_seq += 1

        # Wait for ACK
        try:
            _, ack_data = send_monitor.recv(max_pkt_size)
            if ack_data is None:
                continue

            ack_seq, ack_rwnd, sack_info = parse_ack(ack_data)
            if ack_seq is None:
                continue

            # Update advertised window from receiver
            if ack_rwnd is not None:
                rwnd = ack_rwnd

            # Update SACK set (only keep entries above current base)
            sacked.update(sack_info)

            if ack_seq >= base:
                # RTT sample from the ACKed packet (only if not retransmitted)
                if ack_seq in send_times:
                    sample = time.time() - send_times[ack_seq]
                    update_timeout(sample)

                if ack_seq > last_ack:
                    # New cumulative ACK — advance window
                    old_base = base
                    base = ack_seq + 1
                    last_ack = ack_seq
                    dup_ack_cnt = 0
                    # Clean up send_times and sacked for acknowledged packets
                    for s in range(old_base, base):
                        send_times.pop(s, None)
                        sacked.discard(s)

                elif ack_seq == last_ack:
                    # Duplicate ACK
                    dup_ack_cnt += 1
                    if dup_ack_cnt >= FAST_RETRANSMIT_THRESH:
                        # Fast retransmit: send only the missing packet
                        missing = []
                        for seq in range(base, next_seq):
                            if seq not in sacked:
                                missing.append(seq)
                        if missing:
                            send_times.pop(missing[0], None)
                            send_packet(missing[0])
                        dup_ack_cnt = 0

        except socket.timeout:
            # Retransmit all unACKed, non-SACKed packets
            retransmit_missing()

    # --- FIN handshake ---
    send_monitor.socketfd.settimeout(rtt[2])
    for _ in range(50):
        send_monitor.send(receiver_id, FIN)
        try:
            _, ack_data = send_monitor.recv(max_pkt_size)
            if ack_data and ack_data.strip() == FINACK.strip():
                break
        except socket.timeout:
            pass

    send_monitor.send_end(receiver_id)
