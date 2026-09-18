"""
scheduler.py
============

Background auto-refresh scheduler for HoshiyarLahore.

Runs INSIDE the FastAPI process (no external cron needed) so live weather and
historical baselines stay current automatically while the API is running -
whether that's on a laptop during development or once deployed.

WHAT IT DOES
------------
- Refreshes current + 72h forecast weather every REFRESH_MINUTES (default 60).
  Open-Meteo itself updates its forecast roughly hourly, so refreshing more
  often than that gains nothing and just wastes requests.
- Refreshes the 10-year historical baseline once every HISTORICAL_REFRESH_HOURS
  (default 24). Climatological "normals" don't meaningfully change hour to
  hour, so this is intentionally infrequent.
- Runs an immediate refresh once at startup, so the app has current data right
  away instead of waiting a full interval.
- Failures (no internet, Open-Meteo down, etc.) are caught and logged. They
  NEVER crash the server - the API just keeps serving the last good data, and
  the failure is recorded so /api/status can report it honestly.

CONFIGURATION (environment variables, all optional)
----------------------------------------------------
HOSHIYAR_AUTO_REFRESH        "1" (default) or "0" to disable entirely
HOSHIYAR_REFRESH_MINUTES     weather refresh interval in minutes (default 60)
HOSHIYAR_HISTORICAL_HOURS    historical refresh interval in hours (default 24)

IMPORTANT - DEPLOYMENT REQUIREMENT
-----------------------------------
This scheduler only works if the backend runs as a PERSISTENT, always-on
process - e.g. a Render/Railway "Web Service". It will NOT work on serverless
platforms (e.g. Vercel serverless functions, AWS Lambda) because those spin
processes up per-request and don't keep a background thread alive between
requests. This is one reason the plan puts the backend on Render/Railway
(persistent) and only the frontend on Vercel.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import threading

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger("hoshiyar.scheduler")

# In-memory bookkeeping (reset on process restart; /api/status also reads the
# database directly for ground-truth freshness, so a restart doesn't lie).
_last_weather_refresh: dt.datetime | None = None
_last_weather_error: str | None = None
_last_historical_refresh: dt.datetime | None = None
_last_historical_error: str | None = None

_scheduler: BackgroundScheduler | None = None


def _refresh_weather_job() -> None:
    global _last_weather_refresh, _last_weather_error, _weather_cooldown_until
    try:
        from backend.scripts.refresh_weather import refresh_all_towns
        ok, failed, last_fetch_error = refresh_all_towns()
        if ok == 0:
            # Every town failed - this is NOT a successful refresh, even though
            # refresh_all_towns() itself didn't raise. Record the REAL reason
            # (e.g. a 429 rate limit) rather than guessing "offline" - a wrong
            # guess here is actively misleading when debugging.
            reason = last_fetch_error or "unknown error"
            _last_weather_error = f"all {failed} tehsils failed to fetch: {reason}"
            logger.warning("Auto-refresh: weather refresh failed - %s",
                           _last_weather_error)
            # A persistent 429 (e.g. Open-Meteo rate-limiting a shared/NAT'd
            # host IP - common on free hosting tiers) will not clear up in the
            # handful of seconds our per-request retries wait. Without a
            # cooldown, every subsequent visitor's request would immediately
            # retrigger another full multi-town retry cycle against an
            # endpoint that's still blocked - slow for that visitor and
            # needlessly hammers Open-Meteo harder. Back off for a while
            # instead, and just serve current data until the cooldown expires.
            if "429" in reason:
                _weather_cooldown_until = dt.datetime.now() + dt.timedelta(
                    minutes=WEATHER_FAILURE_COOLDOWN_MINUTES
                )
                logger.warning(
                    "Auto-refresh: backing off further attempts until %s "
                    "(%d minute cooldown after a 429).",
                    _weather_cooldown_until, WEATHER_FAILURE_COOLDOWN_MINUTES,
                )
        else:
            _last_weather_refresh = dt.datetime.now()
            _last_weather_error = (
                f"{failed} of {ok + failed} tehsils failed: {last_fetch_error}"
                if failed else None
            )
            _weather_cooldown_until = None  # a real success clears any cooldown
            logger.info("Auto-refresh: weather updated at %s (%d/%d ok)",
                       _last_weather_refresh, ok, ok + failed)
    except Exception as exc:  # noqa: BLE001 - never let the scheduler die
        _last_weather_error = str(exc)
        logger.warning("Auto-refresh: weather refresh failed: %s", exc)


# ---------------------------------------------------------------------------
# Request-triggered "refresh if stale" - see ensure_fresh_weather() below.
# ---------------------------------------------------------------------------

_refresh_lock = threading.Lock()
STALE_THRESHOLD_MINUTES = int(os.environ.get("HOSHIYAR_STALE_THRESHOLD_MINUTES", "10"))

# Cooldown after a total (all-tehsil) 429 failure - see _refresh_weather_job().
WEATHER_FAILURE_COOLDOWN_MINUTES = int(
    os.environ.get("HOSHIYAR_FAILURE_COOLDOWN_MINUTES", "5")
)
_weather_cooldown_until: dt.datetime | None = None


def _weather_age_minutes() -> float | None:
    """Age of the current weather data in minutes, or None if there's none yet."""
    try:
        from backend.app.db.database import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT fetched_at FROM weather_current ORDER BY fetched_at DESC LIMIT 1"
            ).fetchone()
            if row is None or not row["fetched_at"]:
                return None
            fetched = dt.datetime.fromisoformat(row["fetched_at"])
            return (dt.datetime.now() - fetched).total_seconds() / 60.0
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return None


def _is_weather_stale() -> bool:
    age = _weather_age_minutes()
    return age is None or age > STALE_THRESHOLD_MINUTES


def _in_failure_cooldown() -> bool:
    return _weather_cooldown_until is not None and dt.datetime.now() < _weather_cooldown_until


def ensure_fresh_weather() -> None:
    """
    FastAPI dependency: if the current weather is older than
    HOSHIYAR_STALE_THRESHOLD_MINUTES (default 10), triggers a SYNCHRONOUS
    refresh before the request proceeds - so a visitor arriving after a
    period of inactivity (e.g. a judge opening the site after it's been idle,
    or waking a sleeping free-tier backend) sees genuinely current data
    rather than stale cached numbers, without you having to run anything by
    hand or wait for the next hourly cycle.

    WHY THIS IS SAFE (and doesn't repeat the earlier 429 rate-limit issue):
    -------------------------------------------------------------------------
    The frontend fires several API calls in parallel on every page load
    (towns, overview, alerts, ranking, predictive-alerts). Without locking,
    each of those concurrent requests would independently decide "data is
    stale" and each try to refresh - multiplying request volume to
    Open-Meteo exactly like the burst that caused the original 429 problem.

    A single process-wide lock fixes this: the FIRST request to notice stale
    data acquires the lock and performs the real refresh; every other
    concurrent request either finds data already fresh (if it arrives after
    the refresh completes) or waits briefly for the in-progress refresh
    rather than starting a duplicate one. If a refresh is already underway
    and taking unusually long, later requests give up waiting after a bounded
    timeout and simply proceed with whatever is currently in the database,
    rather than making the visitor's page hang indefinitely.

    WHY THERE'S ALSO A FAILURE COOLDOWN
    -------------------------------------
    A 429 from Open-Meteo can be a brief burst-related hiccup (recovers in
    seconds - our per-request retry/backoff handles that fine) OR a longer,
    IP-level rate limit (e.g. Open-Meteo's free tier is limited per IP, and
    a shared/NAT'd IP on a hosting platform's free tier can already be
    exhausted by OTHER tenants' unrelated traffic - not fixable by this app
    being more conservative on its own). Without a cooldown, EVERY visitor's
    request during a longer block would independently retrigger a full
    multi-town retry cycle against an endpoint that's still rate-limited -
    slow for that visitor (multiple seconds of retries, doomed to fail) and
    it hammers Open-Meteo harder rather than giving the block a chance to
    clear. After a total (all-tehsil) 429 failure, further attempts back off
    for HOSHIYAR_FAILURE_COOLDOWN_MINUTES (default 5) - visitors during that
    window get an instant response with whatever data is currently cached,
    and the very next attempt after the cooldown expires tries again for real.

    WHY 10 MINUTES BY DEFAULT
    --------------------------
    Render's free tier sleeps after 15 minutes idle, so if the backend was
    asleep, by definition more than 15 minutes have passed since the last
    request - a 10-minute threshold guarantees that wake-up visit always
    triggers a genuine refresh. During active use, most page loads/reloads
    within a 10-minute window are instant (no refetch), so this does not
    turn every click into a live API call.

    THE TRADEOFF, STATED HONESTLY
    -------------------------------
    The one visitor whose request actually triggers the refresh will see a
    slightly slower page load (typically a few seconds; longer if Open-Meteo
    is transiently rate-limited and the retry/backoff logic kicks in) while
    the fetch completes, since this blocks that request. Every other request
    - including reloads by the same visitor - is effectively instant. This is
    a deliberate tradeoff in favour of demo-visible freshness; if page-load
    latency ever matters more than that, lower STALE_THRESHOLD_MINUTES's
    importance by raising the threshold, or ask for the fully non-blocking
    ("serve now, refresh in the background") variant instead.
    """
    if not _is_weather_stale():
        return  # fast path: a single indexed DB read, no lock needed

    if _in_failure_cooldown():
        # We already know (from a very recent attempt) that Open-Meteo is
        # rate-limiting us. Don't retry on every request during the cooldown -
        # just serve current data instantly instead of making this visitor
        # wait through a retry cycle that's very likely to fail again.
        return

    acquired = _refresh_lock.acquire(timeout=25)
    if not acquired:
        logger.warning("ensure_fresh_weather: timed out waiting for an "
                       "in-progress refresh; serving current data.")
        return
    try:
        if not _is_weather_stale():
            # Someone else refreshed while we were waiting for the lock.
            return
        if _in_failure_cooldown():
            # Someone else's attempt (while we waited for the lock) just
            # failed with a 429 and started a fresh cooldown - don't pile on.
            return
        logger.info(
            "ensure_fresh_weather: weather data is stale (>%sm old) - "
            "refreshing now, triggered by an incoming request.",
            STALE_THRESHOLD_MINUTES,
        )
        _refresh_weather_job()
    finally:
        _refresh_lock.release()


def _refresh_historical_job() -> None:
    global _last_historical_refresh, _last_historical_error
    try:
        from backend.scripts.refresh_historical import refresh_historical
        ok, failed, last_fetch_error = refresh_historical(years=10, start_month=4, end_month=9)
        if ok == 0:
            reason = last_fetch_error or "unknown error"
            _last_historical_error = f"all {failed} tehsils failed to fetch: {reason}"
            logger.warning("Auto-refresh: historical refresh failed - %s",
                           _last_historical_error)
        else:
            _last_historical_refresh = dt.datetime.now()
            _last_historical_error = (
                f"{failed} of {ok + failed} tehsils failed: {last_fetch_error}"
                if failed else None
            )
            logger.info("Auto-refresh: historical baselines updated at %s (%d/%d ok)",
                       _last_historical_refresh, ok, ok + failed)
    except Exception as exc:  # noqa: BLE001
        _last_historical_error = str(exc)
        logger.warning("Auto-refresh: historical refresh failed: %s", exc)


def _historical_table_empty() -> bool:
    """
    Check whether weather_historical currently has any rows. Used to decide
    whether to rebuild historical baselines IMMEDIATELY at startup rather than
    waiting for the daily schedule.

    Why this matters: on hosts with an ephemeral filesystem (e.g. Render/
    Railway free tiers, which wipe local files on every spin-down/restart),
    the SQLite database can come back empty after any restart. Without this
    check, an empty historical table could sit empty for up to
    HOSHIYAR_HISTORICAL_HOURS (default 24h) before the next scheduled rebuild -
    long enough to break the "compared to normal" feature after an idle period.
    If we can't even check (DB not yet initialised), we treat it as empty so
    we attempt to build it rather than silently waiting.
    """
    try:
        from backend.app.db.database import get_connection
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM weather_historical"
            ).fetchone()
            return (row["c"] if row else 0) == 0
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - table/DB may not exist yet
        return True


def start_scheduler() -> BackgroundScheduler | None:
    """Start the background scheduler. Call once, at FastAPI startup."""
    global _scheduler

    if os.environ.get("HOSHIYAR_AUTO_REFRESH", "1") == "0":
        logger.info("Auto-refresh disabled (HOSHIYAR_AUTO_REFRESH=0)")
        return None

    weather_minutes = int(os.environ.get("HOSHIYAR_REFRESH_MINUTES", "60"))
    historical_hours = int(os.environ.get("HOSHIYAR_HISTORICAL_HOURS", "24"))

    sched = BackgroundScheduler(daemon=True)
    sched.add_job(
        _refresh_weather_job, "interval", minutes=weather_minutes,
        next_run_time=dt.datetime.now(),  # run once immediately, then on interval
        id="weather_refresh", replace_existing=True,
    )

    # Historical baselines normally only rebuild on the slow daily schedule
    # (fetching 10 years of archive data is not cheap). BUT if the table is
    # empty right now - e.g. an ephemeral filesystem wiped it on a cold start -
    # rebuild immediately instead of leaving "compared to normal" broken for
    # up to a day. This runs in the background thread; it does not block the
    # API from serving requests in the meantime.
    #
    # Staggered by 45s after the weather job's immediate run, rather than
    # firing at the exact same instant: two concurrent bursts of requests
    # (5 towns each) hitting Open-Meteo in the same second is an easy way to
    # trip a transient rate limit, especially from a shared/NAT'd IP on a
    # hosting platform's free tier. Letting the weather burst finish first
    # keeps each burst small and separated.
    historical_kwargs = {}
    if _historical_table_empty():
        historical_kwargs["next_run_time"] = dt.datetime.now() + dt.timedelta(seconds=45)
        logger.info("Historical baselines table is empty - scheduling a "
                   "rebuild in 45s instead of waiting for the daily cycle.")

    sched.add_job(
        _refresh_historical_job, "interval", hours=historical_hours,
        id="historical_refresh", replace_existing=True, **historical_kwargs,
    )
    sched.start()
    _scheduler = sched
    logger.info(
        "Auto-refresh started: weather every %sm, historical every %sh",
        weather_minutes, historical_hours,
    )
    return sched


def stop_scheduler() -> None:
    """Stop the scheduler cleanly. Call at FastAPI shutdown."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def trigger_refresh_now() -> dict:
    """Force an immediate weather refresh (used by the manual /api/refresh
    endpoint, e.g. for a demo 'watch it update live' moment)."""
    _refresh_weather_job()
    return refresh_status()


def refresh_status() -> dict:
    """In-memory scheduler bookkeeping: last run times/errors and config."""
    now = dt.datetime.now()

    def age_minutes(t):
        return None if t is None else round((now - t).total_seconds() / 60, 1)

    return {
        "auto_refresh_enabled": os.environ.get("HOSHIYAR_AUTO_REFRESH", "1") != "0",
        "refresh_interval_minutes": int(os.environ.get("HOSHIYAR_REFRESH_MINUTES", "60")),
        "historical_interval_hours": int(os.environ.get("HOSHIYAR_HISTORICAL_HOURS", "24")),
        "request_triggered_refresh_threshold_minutes": STALE_THRESHOLD_MINUTES,
        "weather_failure_cooldown_active": _in_failure_cooldown(),
        "weather_failure_cooldown_until": (
            _weather_cooldown_until.isoformat() if _weather_cooldown_until else None
        ),
        "weather_last_refreshed": (
            _last_weather_refresh.isoformat() if _last_weather_refresh else None
        ),
        "weather_since_refresh_minutes": age_minutes(_last_weather_refresh),
        "weather_last_error": _last_weather_error,
        "historical_last_refreshed": (
            _last_historical_refresh.isoformat() if _last_historical_refresh else None
        ),
        "historical_since_refresh_minutes": age_minutes(_last_historical_refresh),
        "historical_last_error": _last_historical_error,
    }