"""Polite HTTP: honest UA, robots.txt, 1 req/s/host, backoff on 429/5xx, JSONL request log."""
import json, time, datetime as dt, urllib.robotparser as rp
from urllib.parse import urlsplit
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from . import config


class Retryable(Exception):
    def __init__(self, resp):
        self.resp = resp


class RobotsBlocked(Exception):
    pass


class HostFailing(Exception):
    pass


class Client:
    def __init__(self, agency: str):
        self.agency = agency
        self.cfg = config.AGENCIES[agency]
        self.s = requests.Session()
        self.s.headers["User-Agent"] = config.USER_AGENT
        self._last: dict[str, float] = {}
        self._robots: dict[str, rp.RobotFileParser] = {}
        self.consecutive_errors: dict[str, int] = {}
        config.LOGS.mkdir(parents=True, exist_ok=True)
        self.logf = config.LOGS / f"requests-{agency}.jsonl"

    def _log(self, **kw):
        kw["ts"] = dt.datetime.now(dt.timezone.utc).isoformat()
        with open(self.logf, "a", encoding="utf8") as f:
            f.write(json.dumps(kw) + "\n")

    def _allowed(self, url: str) -> bool:
        u = urlsplit(url)
        if any(u.path.startswith(p) for p in self.cfg["robots_override_prefixes"]):
            return True  # authorized override, see config.py
        if u.netloc not in self._robots:
            r = rp.RobotFileParser()
            try:
                resp = self.s.get(f"{u.scheme}://{u.netloc}/robots.txt", timeout=config.TIMEOUT)
                r.parse(resp.text.splitlines() if resp.ok else [])
            except requests.RequestException:
                r.parse([])
            self._robots[u.netloc] = r
        return self._robots[u.netloc].can_fetch(config.USER_AGENT, url)

    def _throttle(self, host):
        wait = config.MIN_INTERVAL - (time.monotonic() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def request(self, method, url, stream=False, headers=None):
        if not self._allowed(url):
            raise RobotsBlocked(url)
        host = urlsplit(url).netloc

        @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, max=60),
               retry=retry_if_exception_type((Retryable, requests.ConnectionError, requests.Timeout)),
               reraise=True)
        def go():
            self._throttle(host)
            t0 = time.monotonic()
            r = self.s.request(method, url, stream=stream, headers=headers, timeout=config.TIMEOUT)
            self._log(method=method, url=url, status=r.status_code, ms=int((time.monotonic() - t0) * 1000))
            if r.status_code in (429,) or r.status_code >= 500:
                ra = r.headers.get("Retry-After")
                if ra and ra.isdigit():
                    time.sleep(min(int(ra), 120))
                raise Retryable(r)
            return r
        try:
            r = go()
            self.consecutive_errors[host] = 0
            return r
        except Retryable as e:
            self._fail(host)
            return e.resp
        except (requests.ConnectionError, requests.Timeout):
            self._fail(host)
            raise

    def _fail(self, host):
        n = self.consecutive_errors[host] = self.consecutive_errors.get(host, 0) + 1
        if n > config.MAX_CONSECUTIVE_ERRORS:
            raise HostFailing(f"{host}: {n} consecutive errors")

    def get(self, url, **kw): return self.request("GET", url, **kw)
    def head(self, url, **kw): return self.request("HEAD", url, **kw)
