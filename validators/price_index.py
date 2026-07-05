from collections import defaultdict


class PriceIndex:
    """Заморожений індекс цін поточного пакета.

    Нічого не виправляє. Тільки збирає підтверджені ціни:
    - package price: однакова ціна товару у >=2 різних накладних;
    - history price: LASTPRICE з data/price_history.xlsx.

    Пріоритет під час читання: package price > history price.
    """

    def __init__(self, invoices=None, price_history=None):
        self.invoices = list(invoices or [])
        self.price_history = price_history
        self.package_prices = {}
        self._package_price_docs = defaultdict(set)
        self._build()

    def _round2(self, value):
        try:
            return round(float(value or 0), 2)
        except Exception:
            return 0.0

    def _amount_ok(self, price, qty, amount, tolerance=0.10):
        try:
            expected = round(float(price) * float(qty), 2)
            return abs(expected - float(amount)) <= max(tolerance, abs(expected) * 0.002)
        except Exception:
            return False

    def _key(self, item):
        product = getattr(item, "product", None)
        if not product:
            return None
        code = str(getattr(product, "code", "") or "").strip()
        unit = str(getattr(item, "unit", "") or "ЯЩ").strip() or "ЯЩ"
        if not code:
            return None
        return code, unit

    def _item_code(self, item):
        product = getattr(item, "product", None)
        if not product:
            return ""
        return str(getattr(product, "code", "") or "").strip()

    def _doc_id(self, inv):
        doc = str(getattr(inv, "doc", "") or "").strip()
        if doc:
            return doc
        src = str(getattr(inv, "source_file", "") or "").strip()
        page = str(getattr(inv, "page", "") or "").strip()
        return f"{src}#{page}" if src or page else str(id(inv))

    def _build(self):
        groups = defaultdict(set)

        for inv in self.invoices:
            doc = self._doc_id(inv)
            for it in getattr(inv, "items", []):
                key = self._key(it)
                if not key:
                    continue

                price = self._round2(getattr(it, "price", 0))
                qty = float(getattr(it, "qty", 0) or 0)
                amount = self._round2(getattr(it, "amount", 0))

                if price > 0 and qty > 0 and amount > 0 and qty < 100 and self._amount_ok(price, qty, amount):
                    groups[(key, price)].add(doc)

        best_by_key = {}
        for (key, price), docs in groups.items():
            if len(docs) < 2:
                continue
            self._package_price_docs[(key, price)] = set(docs)
            old = best_by_key.get(key)
            if old is None or len(docs) > len(old[1]):
                best_by_key[key] = (price, docs)

        self.package_prices = {key: price for key, (price, docs) in best_by_key.items()}

    def package_price(self, item):
        key = self._key(item)
        if not key:
            return None
        return self.package_prices.get(key)

    def history_price(self, item):
        if not self.price_history or not getattr(self.price_history, "prices", None):
            return None
        code = self._item_code(item)
        if not code:
            return None
        return self.price_history.get(code)

    def get(self, item):
        price = self.package_price(item)
        if price:
            return price
        return self.history_price(item)

    def source(self, item):
        if self.package_price(item):
            return "package"
        if self.history_price(item):
            return "history"
        return ""

    def confirmed_prices(self):
        """ITEM -> LASTPRICE для оновлення price_history.xlsx.

        Повертає тільки ціни, підтверджені у поточному пакеті >=2 різними накладними.
        Якщо один ITEM має кілька одиниць/цін, бере найсильніше підтвердження.
        """
        best = {}
        for (key, price), docs in self._package_price_docs.items():
            code, _unit = key
            old = best.get(code)
            if old is None or len(docs) > len(old[1]):
                best[code] = (price, docs)
        return {code: price for code, (price, docs) in best.items()}
