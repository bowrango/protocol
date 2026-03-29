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

def make_data(seq: int, chunk: bytes) -> bytes:
	return f'{seq}\n'.encode() + chunk

def make_ack(seq: int) -> bytes:
	return f'ACK {seq}\n'.encode()

if __name__ == '__main__':
	print("Sender starting up!")
	config_path = sys.argv[1]

	send_monitor = Monitor(config_path, 'sender')

	cfg = configparser.RawConfigParser(allow_no_value=True)
	cfg.read(config_path)
	receiver_id   = int(cfg.get('receiver', 'id'))
	file_to_send  = cfg.get('nodes', 'file_to_send')
	max_pkt_size  = int(cfg.get('network', 'MAX_PACKET_SIZE'))
	prop_delay    = float(cfg.get('network', 'PROP_DELAY'))

	# Timeout = 2 RTTs + margin
	timeout = 4 * prop_delay + 0.5
	send_monitor.socketfd.settimeout(timeout)

	# Chunk the file; leave room for the seq-number header line
	chunk_size = max_pkt_size - 10

	with open(file_to_send, 'rb') as f:
		chunks = []
		while True:
			chunk = f.read(chunk_size)
			if not chunk:
				break
			chunks.append(chunk)

	print(f'Sender: {len(chunks)} packets to send.')

	seq = 0
	for i, chunk in enumerate(chunks):
		packet = make_data(seq, chunk)
		while True:
			send_monitor.send(receiver_id, packet)
			try:
				_, ack = send_monitor.recv(max_pkt_size)
				if ack == make_ack(seq):
					break
			except socket.timeout:
				print(f'Sender: timeout on seq={seq}, retransmitting.')

		seq ^= 1  # alternate 0/1

	# Signal end of file
	while True:
		send_monitor.send(receiver_id, FIN)
		try:
			_, ack = send_monitor.recv(max_pkt_size)
			if ack == FINACK:
				break
		except socket.timeout:
			print('Sender: timeout waiting for FINACK, retransmitting FIN.')

	send_monitor.send_end(receiver_id)
	print('Sender: done.')
