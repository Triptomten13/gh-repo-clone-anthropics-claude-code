"""Headers for every live stream (text/event-stream).

no-transform: proxies — including the web server's gzip — must pass a live stream through untouched; compressing it
buffers the whole reply (measured: a 44 s G-sus answer arrived in one piece). X-Accel-Buffering: nginx-style proxies.
"""
STREAM_HEADERS = {"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"}
