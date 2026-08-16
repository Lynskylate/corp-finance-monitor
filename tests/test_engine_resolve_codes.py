"""Tests for Engine.resolve_stock_codes — BSE dual-code alias resolution across sources."""

import unittest

from corp_finance_monitor.core.engine import Engine


class _StubRegistry:
    def __init__(self, groups: dict[str, list[str]] | None = None):
        self._groups = groups or {}

    def get_code_aliases(self, stock_code: str) -> list[str]:
        return self._groups.get(stock_code, [stock_code])


class _RegistryWithoutAliases:
    """Registry exposing no get_code_aliases (older registry interface)."""


class _StubSource:
    def __init__(self, registry=None, broken=False):
        self._registry = registry
        self._broken = broken

    def _get_registry(self):
        if self._broken:
            raise RuntimeError("registry unavailable")
        return self._registry


class _PlainSource:
    """Source without _get_registry at all."""


def _engine_with(sources: dict) -> Engine:
    # resolve_stock_codes 只读 engine.sources；跳过完整 __init__ 避免存储/配置依赖
    engine = Engine.__new__(Engine)
    engine.sources = sources
    return engine


class TestResolveStockCodes(unittest.TestCase):
    def test_resolves_bse_alias_group(self):
        registry = _StubRegistry({"920454": ["833454", "920454"], "833454": ["833454", "920454"]})
        engine = _engine_with({"cninfo": _StubSource(registry)})
        self.assertEqual(engine.resolve_stock_codes("920454"), ["833454", "920454"])

    def test_unions_and_sorts_across_sources(self):
        r1 = _StubRegistry({"920454": ["833454", "920454"]})
        r2 = _StubRegistry({"920454": ["920454", "430454"]})
        engine = _engine_with({"a": _StubSource(r1), "b": _StubSource(r2)})
        self.assertEqual(engine.resolve_stock_codes("920454"), ["430454", "833454", "920454"])

    def test_unknown_code_returns_self_with_registry(self):
        engine = _engine_with({"cninfo": _StubSource(_StubRegistry())})
        self.assertEqual(engine.resolve_stock_codes("000001"), ["000001"])

    def test_skips_sources_without_usable_registry(self):
        # 无 _get_registry / registry 为 None / 无 get_code_aliases / 抛异常 → 全部跳过
        engine = _engine_with(
            {
                "plain": _PlainSource(),
                "none": _StubSource(registry=None),
                "no-aliases": _StubSource(_RegistryWithoutAliases()),
                "broken": _StubSource(broken=True),
            }
        )
        self.assertEqual(engine.resolve_stock_codes("000001"), ["000001"])

    def test_no_sources_returns_self(self):
        engine = _engine_with({})
        self.assertEqual(engine.resolve_stock_codes("920454"), ["920454"])


if __name__ == "__main__":
    unittest.main()
