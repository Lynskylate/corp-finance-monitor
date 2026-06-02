#!/usr/bin/env python3
"""
corp-finance-monitor CLI — 企业财报发现、同步、查询与订阅服务
"""
import argparse
import json
import logging
import os
import sys
from typing import Dict, Type

from corp_finance_monitor.api import serve
from corp_finance_monitor.core import Config, Engine, AbstractSource, FilingKind
from corp_finance_monitor.core.model import Subscription

SOURCE_REGISTRY: Dict[str, Type[AbstractSource]] = {}


def _register_builtin_sources():
    try:
        from corp_finance_monitor.sources.cninfo import CninfoSource
        SOURCE_REGISTRY["cninfo"] = CninfoSource
    except ImportError:
        pass
    try:
        from corp_finance_monitor.sources.sse import SSESource
        SOURCE_REGISTRY["sse"] = SSESource
    except ImportError:
        pass
    try:
        from corp_finance_monitor.sources.hkex import HKEXSource
        SOURCE_REGISTRY["hkex"] = HKEXSource
    except ImportError:
        pass


KIND_LABELS = {
    FilingKind.ANNUAL: "年报",
    FilingKind.SEMI: "中报",
    FilingKind.Q1: "一季报",
    FilingKind.Q3: "三季报",
    FilingKind.PROSPECTUS: "招股书",
    FilingKind.INTERIM: "中期报告",
    FilingKind.QUARTERLY: "季度报告",
    FilingKind.ESG: "ESG报告",
    FilingKind.OTHER: "其他",
}


def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def _new_engine(config_path: str) -> tuple[Config, Engine]:
    cfg = Config.from_file(config_path)
    engine = Engine(cfg, SOURCE_REGISTRY)
    engine.initialize()
    return cfg, engine


def cmd_run(args):
    _setup_logging(args.verbose)
    cfg, engine = _new_engine(args.config)
    try:
        if cfg.engine.run_once:
            stats = engine.run_once()
            print(f"\n{'='*50}")
            print(f"  Complete: {stats}")
            print(f"{'='*50}")
        else:
            engine.run_loop()
    finally:
        engine.close()


def cmd_sync(args):
    _setup_logging(args.verbose)
    _, engine = _new_engine(args.config)
    try:
        # --since modes:
        #   not provided → None (auto-incremental from last successful run)
        #   YYYY-MM-DD → explicit date window
        since = args.since
        stats = engine.run_once(
            selected_sources=args.source or None,
            since=since,
        )
        print(json.dumps({"stats": stats}, ensure_ascii=False, indent=2))
    finally:
        engine.close()


def cmd_list(args):
    _setup_logging(args.verbose)
    _, engine = _new_engine(args.config)
    try:
        refs = engine.storage.list_refs(
            source=args.source,
            stock_code=args.stock,
            kind=FilingKind(args.kind) if args.kind else None,
            since=args.since,
        )

        print(f"\nStored filings ({len(refs)}):")
        print(f"  {'Source':<8s} {'Stock':<10s} {'Kind':<10s} {'Date':<12s} {'Title'}")
        print(f"  {'-'*88}")
        for ref in refs:
            label = KIND_LABELS.get(ref.kind, ref.kind.value)
            print(
                f"  {ref.source:<8s} {ref.stock_code:<10s} {label:<10s} "
                f"{ref.published_at:<12s} {ref.title[:60]}"
            )
        print()
    finally:
        engine.close()


def cmd_runs(args):
    _setup_logging(args.verbose)
    _, engine = _new_engine(args.config)
    try:
        runs = engine.state_store.list_runs(limit=args.limit)
        print(f"\nRun history ({len(runs)}):")
        print("  ID   Started At                  Finished At                 Disc  Fetch  Fail")
        print("  " + "-" * 84)
        for run in runs:
            print(
                f"  {run.id:<4d} {run.started_at[:19]:<26s} {run.finished_at[:19]:<26s} "
                f"{run.discovered:<5d} {run.fetched:<6d} {run.failed}"
            )
        print()
    finally:
        engine.close()


def cmd_subscribe(args):
    _setup_logging(args.verbose)
    _, engine = _new_engine(args.config)
    try:
        if args.action == "list":
            subs = engine.state_store.list_subscriptions(
                source=args.source,
                stock_code=args.stock,
                active_only=args.active_only,
            )
            print(f"\nSubscriptions ({len(subs)}):")
            print("  ID   Name                 Source   Stock      Kind         Target")
            print("  " + "-" * 88)
            for sub in subs:
                print(
                    f"  {sub.id or 0:<4d} {sub.name[:20]:<20s} {sub.source[:8]:<8s} "
                    f"{sub.stock_code[:10]:<10s} {sub.kind[:12]:<12s} {sub.target[:28]}"
                )
            print()
            return

        sub = Subscription(
            id=None,
            name=args.name,
            source=args.source or "",
            stock_code=args.stock or "",
            kind=args.kind or "",
            target=args.target or "",
            active=True,
        )
        created = engine.state_store.create_subscription(sub)
        print(json.dumps({"subscription": created.__dict__}, ensure_ascii=False, indent=2))
    finally:
        engine.close()


def cmd_serve(args):
    _setup_logging(args.verbose)
    cfg = Config.from_file(args.config)
    if args.host:
        cfg.api.host = args.host
    if args.port:
        cfg.api.port = args.port
    serve(cfg, SOURCE_REGISTRY)


def cmd_init(args):
    path = args.path
    if os.path.exists(path):
        print(f"Error: {path} already exists.")
        sys.exit(1)

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write("""# corp-finance-monitor 配置
# 数据源配置: 每个source定义watchlist（监控的股票和报告类型）
# 存储配置: 目前支持disk

engine:
  run_once: true
  interval_minutes: 360
  concurrency: 1
  fetch_delay_seconds: 0.5

storage:
  backend: disk
  base_dir: ./data

state_store:
  backend: sqlite
  path: ./data/.cfm_state/state.db

api:
  enabled: true
  host: 127.0.0.1
  port: 8190

sources:
  cninfo:
    options:
      full_market: false
      full_market_batch_size: 50
    watchlist:
      - stock: "000725"
        org_id: "gssz0000725"
        kinds: [annual, semi, q1, q3]

  sse:
    watchlist: []

  hkex:
    watchlist:
      - stock: "00700"
        kinds: [annual, interim]
""")
    print(f"Config created: {path}")
    print("Edit it to add your watchlist, then run:")
    print(f"  python3 main.py sync -c {path} --source cninfo")
    print(f"  python3 main.py serve -c {path}")


def main():
    _register_builtin_sources()

    parser = argparse.ArgumentParser(
        description="corp-finance-monitor — 企业财报发现与更新系统"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="执行一轮发现-下载或持续轮询")
    p_run.add_argument("-c", "--config", default="config.yaml", help="Config path")
    p_run.add_argument("-v", "--verbose", action="store_true")

    p_sync = sub.add_parser("sync", help="执行一轮同步，可选指定source和日期窗口")
    p_sync.add_argument("-c", "--config", default="config.yaml", help="Config path")
    p_sync.add_argument("--source", action="append", help="Only sync selected source(s)")
    p_sync.add_argument(
        "--since",
        help=(
            "Incremental sync: only discover filings published after this date. "
            "Format: YYYY-MM-DD. If omitted, auto-detects from last successful run. "
            "Use 'full' for a full sync ignoring date filters."
        ),
    )
    p_sync.add_argument("-v", "--verbose", action="store_true")

    p_list = sub.add_parser("list", help="列出已存储的财报")
    p_list.add_argument("-c", "--config", default="config.yaml")
    p_list.add_argument("--source", help="Filter by source")
    p_list.add_argument("--stock", help="Filter by stock code")
    p_list.add_argument("--kind", choices=[k.value for k in FilingKind], help="Filter by kind")
    p_list.add_argument("--since", help="Filter by published date >= YYYY-MM-DD")
    p_list.add_argument("-v", "--verbose", action="store_true")

    p_runs = sub.add_parser("runs", help="查看同步运行历史")
    p_runs.add_argument("-c", "--config", default="config.yaml")
    p_runs.add_argument("--limit", type=int, default=20)
    p_runs.add_argument("-v", "--verbose", action="store_true")

    p_subscribe = sub.add_parser("subscribe", help="管理订阅")
    subscribe_sub = p_subscribe.add_subparsers(dest="action", required=True)
    p_sub_list = subscribe_sub.add_parser("list", help="列出订阅")
    p_sub_list.add_argument("-c", "--config", default="config.yaml")
    p_sub_list.add_argument("--source")
    p_sub_list.add_argument("--stock")
    p_sub_list.add_argument("--active-only", action="store_true")
    p_sub_list.add_argument("-v", "--verbose", action="store_true")

    p_sub_add = subscribe_sub.add_parser("add", help="新增订阅")
    p_sub_add.add_argument("-c", "--config", default="config.yaml")
    p_sub_add.add_argument("--name", required=True)
    p_sub_add.add_argument("--source")
    p_sub_add.add_argument("--stock")
    p_sub_add.add_argument("--kind")
    p_sub_add.add_argument("--target")
    p_sub_add.add_argument("-v", "--verbose", action="store_true")

    p_serve = sub.add_parser("serve", help="启动HTTP查询/订阅API")
    p_serve.add_argument("-c", "--config", default="config.yaml")
    p_serve.add_argument("--host")
    p_serve.add_argument("--port", type=int)
    p_serve.add_argument("-v", "--verbose", action="store_true")

    p_init = sub.add_parser("init", help="初始化配置文件")
    p_init.add_argument("path", nargs="?", default="config.yaml", help="Output path")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "sync":
        cmd_sync(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "runs":
        cmd_runs(args)
    elif args.command == "subscribe":
        cmd_subscribe(args)
    elif args.command == "serve":
        cmd_serve(args)
    elif args.command == "init":
        cmd_init(args)


if __name__ == "__main__":
    main()
