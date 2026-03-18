Baseline implementation of Stop and Go protocol.

The sender sends a packet and waits for an ACK before sending the next packet. If the corresponding ACK is not received within a predefined timeout period, the packet is retransmitted. This protocol results in a low overhead but significantly lower goodput.