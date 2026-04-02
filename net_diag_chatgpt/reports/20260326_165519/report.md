# ChatGPT USA Route Diagnostic Report

**Generated:** 2026-03-26T13:56:29.624061

## Comparison: Direct vs Proxy

| Test | Direct Status | Proxy Status | Improvement |
|------|---------------|--------------|-------------|
| dns_leak | ERROR | FAIL | N/A |
| http_timing | ERROR | ERROR | N/A |
| idle_tcp | ERROR | ERROR | N/A |
| playwright_har | SUCCESS | SUCCESS | N/A |
| tcp_rtt | ERROR | ERROR | -294.6% |
| tls_handshake | ERROR | ERROR | N/A |
| ws_echo | SUCCESS | SUCCESS | N/A |

## Detailed Results

### tcp_rtt (direct)

**Status:** ERROR

**Details:** No HTTP response received

**Metrics:**

```json
{
  "dns_ms": 5.333333333333333,
  "connect_ms": 0.0,
  "appconnect_ms": 0.0,
  "ttfb_ms": 0.0,
  "total_ms": 5.664666666666666,
  "http_code": 0
}
```

### tls_handshake (direct)

**Status:** ERROR

**Details:** openssl not found or not accessible. Install OpenSSL to enable TLS handshake testing.

### dns_leak (direct)

**Status:** ERROR

**Details:** nslookup timeout

### http_timing (direct)

**Status:** ERROR

**Details:** Unexpected error: Expecting ',' delimiter: line 1 column 97 (char 96)

### ws_echo (direct)

**Status:** SUCCESS

**Details:** WebSocket echo test skipped (WS_ECHO_URL not configured)

**Metrics:**

```json
{
  "skipped": true
}
```

### playwright_har (direct)

**Status:** SUCCESS

**Details:** Playwright HAR test skipped (PLAYWRIGHT_ENABLED not set to 'true')

**Metrics:**

```json
{
  "skipped": true
}
```

### idle_tcp (direct)

**Status:** ERROR

**Details:** Failed to measure connect times

**Metrics:**

```json
{
  "first_connect_ms": 0.0,
  "second_connect_ms": 0.0,
  "idle_seconds": 30,
  "connect_diff_ms": 0.0
}
```

### tcp_rtt (proxy)

**Status:** ERROR

**Details:** No HTTP response received

**Metrics:**

```json
{
  "dns_ms": 0.01933333333333333,
  "connect_ms": 8.255666666666666,
  "appconnect_ms": 0.0,
  "ttfb_ms": 0.0,
  "total_ms": 22.35366666666667,
  "http_code": 0
}
```

### tls_handshake (proxy)

**Status:** ERROR

**Details:** openssl s_client does not support SOCKS5 proxy. Use proxy-aware tool or test direct connection.

### dns_leak (proxy)

**Status:** FAIL

**Details:** Cannot verify DNS leak through proxy: nslookup does not support SOCKS5 proxy. Cannot verify DNS leak through proxy.. DNS should be resolved through X-Ray (1.1.1.1) when proxy is active.

**Metrics:**

```json
{
  "resolver": null,
  "ips": []
}
```

### http_timing (proxy)

**Status:** ERROR

**Details:** Unexpected error: Expecting ',' delimiter: line 1 column 97 (char 96)

### ws_echo (proxy)

**Status:** SUCCESS

**Details:** WebSocket echo test skipped (WS_ECHO_URL not configured)

**Metrics:**

```json
{
  "skipped": true
}
```

### playwright_har (proxy)

**Status:** SUCCESS

**Details:** Playwright HAR test skipped (PLAYWRIGHT_ENABLED not set to 'true')

**Metrics:**

```json
{
  "skipped": true
}
```

### idle_tcp (proxy)

**Status:** ERROR

**Details:** Failed to measure connect times

**Metrics:**

```json
{
  "first_connect_ms": 0.0,
  "second_connect_ms": 0.0,
  "idle_seconds": 30,
  "connect_diff_ms": 0.0
}
```

