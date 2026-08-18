def check_rate_limit(cur, identifier: str, endpoint: str, max_requests=10, window_seconds=60) -> bool:
    cur.execute(
        """SELECT COUNT(*) as cnt FROM rate_limit_log
           WHERE identifier=%s AND endpoint=%s
           AND requested_at > NOW() - INTERVAL %s SECOND""",
        (identifier, endpoint, window_seconds),
    )
    res = cur.fetchone()
    cnt = res["cnt"] if isinstance(res, dict) else res[0]
    if cnt >= max_requests:
        return False
    cur.execute("INSERT INTO rate_limit_log (identifier, endpoint) VALUES (%s, %s)",
                (identifier, endpoint))
    return True
