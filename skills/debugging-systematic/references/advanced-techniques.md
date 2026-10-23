# Advanced Debugging Techniques

## Core Dump Analysis
```bash
# When process crashes
gdb program core
(gdb) bt          # backtrace
(gdb) info locals # local variables
(gdb) frame 3     # inspect frame
```

## Network Debugging
```bash
# Capture traffic
tcpdump -i any -w capture.pcap

# Analyze with Wireshark
wireshark capture.pcap

# Or use Charles Proxy, mitmproxy
```

## Performance Profiling
```typescript
// Node.js
node --prof app.js
node --prof-process isolate-*.log

// Chrome DevTools
// Performance tab -> Record -> Analyze flame graph
```

## Time Travel Debugging

Modern debuggers (rr, WinDbg, Chrome DevTools) can:
- Record execution
- Replay backwards
- Find exact moment state became invalid

## Resources

- [Debugging Guide by Julia Evans](https://jvns.ca/debugging-attitude/)
- [The Art of Debugging by Norman Matloff](https://www.amazon.com/Art-Debugging-GDB-DDD-Eclipse/dp/1593271743)
- [Effective Debugging by Diomidis Spinellis](https://www.spinellis.gr/debugging/)
