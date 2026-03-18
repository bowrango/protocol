Custom protocol implementation

Starting Point:
The sender maintains a sliding
window of packets to be transmitted to the receiver, moving the window forward as it receives ACKs.
The sender transmits W packets to the receiver, where W is the window size. The receiver uses acumulative ACK scheme, and retransmits on a timeout. For example, consider that when transmit-
ting a window of 5 packets, packet 3 is dropped but packets 1, 2, 4, 5 are successfully delivered. The
receiver sends an ACK for packet 2 multiple times (when each of packets 2, 4, and 5 are received).
Under this strategy, the sender will eventually timeout on packet 3, and retransmit packets 

More Points:
Does a sender need to wait until a timeout to detect packet loss, or are there cases it can
retransmit earlier?
Are there disadvantages of a cumulative ACK scheme, and how could one do better? (hint:
selective ACKs).
What is a good window size to use and how would this depend on network settings such as
bandwidth and delay?
What is a good choice of timeout? (hint: ideally, the timeout should match the round-trip time
of the network, but it is desirable to leave some slack for delay variability. The amount of slack
may need to be experimentally tuned and repo