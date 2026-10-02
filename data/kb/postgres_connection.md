# PostgreSQL: application cannot connect

## Symptoms

The application logs errors such as "connection refused", "could not connect to server",
"timeout expired" or "password authentication failed for user". Pages that need the
database fail while static pages still load.

## Checks

1. Check that the PostgreSQL service is running (see "Service status").
2. Check the host and port the application uses (default port 5432) and that
   `listen_addresses` in `postgresql.conf` includes the interface the client connects to.
3. Check `pg_hba.conf`: a missing rule for the client address or user produces
   "no pg_hba.conf entry for host".
4. Check the credentials: "password authentication failed" means the server is reachable
   but the user or password is wrong.
5. Check `max_connections`: "too many clients already" means the pool is exhausted.

## Service status

If the service is stopped, connections are refused immediately. Find out why it stopped
(disk full, crash, maintenance, failed upgrade) by reading the PostgreSQL log before
restarting it. If the service is running, the problem is usually network, configuration
or credentials: a running service does not prove that this client can connect.

## Limits

This sheet covers connection problems only. Slow queries, replication lag and data
corruption are out of scope.
