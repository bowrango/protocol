#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../Monitor'))
from monitor import Monitor

import configparser
import socket

# Packet markers
FIN    = b'FIN\n'
FINACK = b'FINACK\n'

def make_ack(seq: int) -> bytes:
	return f'ACK {seq}\n'.encode()

if __name__ == '__main__':
	print("Receiver starting up!")
	config_path = sys.argv[1]

	recv_monitor = Monitor(config_path, 'receiver')

	cfg = configparser.RawConfigParser(allow_no_value=True)
	cfg.read(config_path)
	sender_id      = int(cfg.get('sender', 'id'))
	max_pkt_size   = int(cfg.get('network', 'MAX_PACKET_SIZE'))
	write_location = cfg.get('receiver', 'write_location')

	expected_seq = 0

	with open(write_location, 'wb') as f:
		while True:
			addr, data = recv_monitor.recv(max_pkt_size)

			if data == FIN:
				recv_monitor.send(sender_id, FINACK)
				break

			# Parse: '{seq}\n{chunk}'
			newline = data.index(b'\n')
			seq     = int(data[:newline])
			chunk   = data[newline + 1:]
			if seq == expected_seq:
				f.write(chunk)
				expected_seq ^= 1

			recv_monitor.send(addr, make_ack(seq))

	# Verify received file and log stats
	recv_monitor.recv_end(write_location, sender_id)

	# Keep ACKing retransmitted FINs until the emulator shuts down
	recv_monitor.socketfd.settimeout(2.0)
	while True:
		try:
			addr, data = recv_monitor.recv(max_pkt_size)
			if data == FIN:
				recv_monitor.send(sender_id, FINACK)
		except socket.timeout:
			break
		except Exception:
			break

	print('Receiver: done.')
