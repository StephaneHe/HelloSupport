# Nginx: web server unavailable

## Symptoms

The browser shows "This site can't be reached", "connection refused", or an HTTP 502 Bad
Gateway / 504 Gateway Timeout page. Monitoring reports the HTTP health check as failing.

## Checks

1. Check that the nginx service is running (see "Service status").
2. Run `nginx -t` to validate the configuration; a syntax error prevents a reload or start.
3. Check that ports 80/443 are not already used by another process.
4. For 502/504 errors, nginx is up but the upstream application behind it is down or too
   slow: check the upstream service and the `proxy_pass` target.
5. Check the TLS certificate expiry date if only HTTPS fails.

## Service status

If nginx is stopped, nothing answers on ports 80/443 and clients get "connection refused".
Check the error log (`/var/log/nginx/error.log`) for the reason before starting it again.
If nginx is running but users still see errors, the cause is usually the upstream
application, the configuration, or the network in front of the server.

## Limits

This sheet does not cover application bugs behind the proxy, DNS problems or CDN issues.
