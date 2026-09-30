"""財報與股價爬蟲：依股票池逐檔抓取，支援快取有效期與增量更新。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from .fmp import FMPClient, FMPError
from .storage import Store

log = logging.getLogger(__name__)

DATASETS = ("profile", "statements", "prices", "marketcap")
ProgressFn = Callable[[int, int, str], None]


@dataclass
class CrawlReport:
    symbols: int = 0
    fetched: dict[str, int] = field(default_factory=dict)
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    api_calls: int = 0


def resolve_universe(client: FMPClient | None, crawl_cfg: dict) -> list[str]:
    universe = crawl_cfg.get("universe", "list")
    if universe == "list":
        syms = crawl_cfg.get("symbols") or []
    else:
        if client is None:
            raise FMPError("需要 API 金鑰才能取得成分股清單")
        syms = [r["symbol"] for r in client.constituents(universe) if r.get("symbol")]
    # FMP 以 '-' 表示股票類別（BRK-B），統一大寫並去重、保序
    seen, out = set(), []
    for s in syms:
        s = str(s).strip().upper().replace(".", "-")
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


class Crawler:
    def __init__(self, client: FMPClient, store: Store, crawl_cfg: dict):
        self.client = client
        self.store = store
        self.cfg = crawl_cfg
        self.ttl = crawl_cfg.get("ttl_hours", {})

    def run(
        self,
        symbols: list[str],
        datasets: tuple[str, ...] = DATASETS,
        force: bool = False,
        progress: ProgressFn | None = None,
    ) -> CrawlReport:
        rep = CrawlReport(symbols=len(symbols))
        calls_before = self.client.calls
        bench = self.cfg.get("benchmark")
        todo = list(symbols)
        if bench and "prices" in datasets and bench not in todo:
            todo.append(bench)

        for i, sym in enumerate(todo, 1):
            if progress:
                progress(i, len(todo), sym)
            is_bench_only = sym == bench and sym not in symbols
            for ds in datasets:
                if is_bench_only and ds != "prices":
                    continue
                # 每個資料集獨立 try/except：單一失敗不影響其他
                try:
                    n = self._fetch(sym, ds, force)
                except FMPError as e:
                    msg = f"{sym}/{ds}: {e}"
                    log.warning(msg)
                    rep.errors.append(msg)
                    self.store.log_fetch(sym, ds, "error", str(e))
                    if e.status == 401:
                        # 金鑰無效：後續請求必然全部失敗，直接中止
                        rep.api_calls = self.client.calls - calls_before
                        return rep
                    continue
                if n is None:
                    rep.skipped += 1
                else:
                    rep.fetched[ds] = rep.fetched.get(ds, 0) + n
                    self.store.log_fetch(sym, ds, "ok", f"{n} rows")
        rep.api_calls = self.client.calls - calls_before
        return rep

    def _fetch(self, sym: str, ds: str, force: bool) -> int | None:
        ttl_key = "prices" if ds == "marketcap" else ds
        if not force and self.store.is_fresh(sym, ds, self.ttl.get(ttl_key, 24)):
            return None
        if ds == "profile":
            p = self.client.profile(sym)
            if p:
                self.store.save_profile(sym, p)
            return 1 if p else 0
        if ds == "statements":
            period = self.cfg.get("period", "quarter")
            limit = int(self.cfg.get("statement_limit", 40))
            n = 0
            n += self.store.save_statements(sym, "income", self.client.income_statement(sym, period, limit))
            n += self.store.save_statements(sym, "balance", self.client.balance_sheet(sym, period, limit))
            n += self.store.save_statements(sym, "cashflow", self.client.cash_flow(sym, period, limit))
            return n
        if ds == "prices":
            # 每次抓完整區間而非增量：還原股價在每次配息後整段歷史都會被修正，
            # 增量接上會在接縫處產生假報酬。反正一檔一次請求，額度相同。
            start = self.cfg.get("price_start", "2014-01-01")
            return self.store.save_prices(sym, self.client.historical_prices(sym, start=start))
        if ds == "marketcap":
            start = self.cfg.get("price_start", "2014-01-01")
            return self.store.save_market_caps(sym, self.client.historical_market_cap(sym, start=start))
        raise ValueError(f"未知資料集：{ds}")
