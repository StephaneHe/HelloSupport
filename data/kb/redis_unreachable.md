# Redis: cache unreachable

## Symptoms

The application logs "Connection refused" or "Could not connect to Redis at host:6379",
"NOAUTH Authentication required", or timeouts. Pages become slow because every request
falls back to the database instead of the cache.

## Checks

1. Check that the Redis service is running (see "Service status").
2. Run `redis-cli -h <host> -p 6379 ping`; the expected answer is `PONG`.
3. Check the `bind` and `protected-mode` settings in `redis.conf`: by default Redis only
   accepts local connections.
4. "NOAUTH" means a password is required: check `requirepass` and the client configuration.
5. Check memory: when `maxmemory` is reached with the `noeviction` policy, writes fail
   with "OOM command not allowed".

## Service status

If Redis is stopped, every connection is refused. Look at the Redis log for the reason
(out of memory, failed persistence to disk, killed by the system) before restarting it.
If Redis is running, look at network settings, authentication and memory limits.

## Limits

This sheet does not cover Redis Cluster or Sentinel failover, nor data loss recovery.
