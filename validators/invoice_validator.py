from collections import Counter, defaultdict


class InvoiceValidator:
    def __init__(self, price_history=None, max_history_deviation=0.20):
        self.price_history = price_history
        self.max_history_deviation = max_history_deviation

    """Двопрохідна перевірка після OCR.

    Принципи:
    - спочатку збираємо типові ціни тільки з математично коректних рядків;
    - не довіряємо сумі рядка, якщо ціна+кількість виглядають узгоджено з пакетом;
    - не виводимо ціну з помилкової суми, якщо підсумок документа не підтверджує суму;
    - усі автоматичні виправлення записуємо в inv.fixes.
    """

    def validate(self, invoices, add_flags):
        self.add_flags = add_flags
        for inv in invoices:
            if not hasattr(inv, "fixes"):
                inv.fixes = []

        typical = self._typical_prices_from_good_rows(invoices)

        # 1. Локальні безпечні виправлення з типовими цінами пакета.
        self._apply_package_price_control(invoices, typical)

        # 2. Контроль відхилення від останньої підтвердженої ціни.
        self._apply_history_price_control(invoices, typical)

        # 3. Контроль підсумків документа: Σ(QTY), Σ(SUM).
        self._apply_document_totals_control(invoices, typical)

        # 4. Повторний контроль після виправлень.
        typical = self._typical_prices_from_good_rows(invoices)
        self._apply_package_price_control(invoices, typical)
        self._apply_history_price_control(invoices, typical)
        self._apply_document_totals_control(invoices, typical)

        # 5. Фінальне маркування попереджень.
        self._final_warnings(invoices)
        return invoices

    # ------------------------------------------------------------

    def _record(self, inv, item, field, old, new, reason):
        inv.fixes.append({
            "doc": getattr(inv, "doc", "") or "",
            "file": getattr(inv, "source_file", "") or "",
            "page": getattr(inv, "page", "") or "",
            "item": getattr(getattr(item, "product", None), "code", "") or "",
            "item_name": getattr(getattr(item, "product", None), "name", "") or "",
            "item_nakl": getattr(item, "raw_name", "") or "",
            "field": field,
            "old": old,
            "new": new,
            "reason": reason,
        })

    def _flag(self, item, flag):
        item.match_method = self.add_flags(item.match_method, flag)

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
        if not item.product:
            return None
        code = str(getattr(item.product, "code", "") or "")
        unit = str(item.unit or "ЯЩ")
        if not code:
            return None
        return code, unit

    def _candidate_qtys(self, qty):
        try:
            q = int(float(qty))
        except Exception:
            return []

        candidates = []
        if q >= 10:
            s = str(q)
            candidates.append(int(s[0]))      # 14 -> 1, 21 -> 2
            if int(s[-1]) > 0:
                candidates.append(int(s[-1])) # 11 -> 1, 12 -> 2
        candidates.extend([1, 2, 3, 4, 5, 6, 7, 8, 9])

        out = []
        for c in candidates:
            c = float(c)
            if c not in out and 0 < c <= 999:
                out.append(c)
        return out

    # ------------------------------------------------------------

    def _typical_prices_from_good_rows(self, invoices):
        groups = defaultdict(list)
        for inv in invoices:
            for it in inv.items:
                key = self._key(it)
                if not key:
                    continue
                price = self._round2(it.price)
                qty = float(it.qty or 0)
                amount = self._round2(it.amount)
                # Типову ціну будуємо тільки з рядків, де price*qty=sum.
                # Це не дає помилковій сумі 988,76 породити хибну ціну 494,38.
                if price > 0 and qty > 0 and amount > 0 and qty < 100 and self._amount_ok(price, qty, amount):
                    groups[key].append(price)

        typical = {}
        for key, prices in groups.items():
            if not prices:
                continue
            c = Counter(prices)
            price, freq = c.most_common(1)[0]
            if freq >= 2 or len(c) == 1:
                typical[key] = price
        return typical

    # ------------------------------------------------------------

    def _apply_package_price_control(self, invoices, typical):
        if not typical:
            return

        for inv in invoices:
            for it in inv.items:
                key = self._key(it)
                if key not in typical:
                    continue

                ref = typical[key]
                price = self._round2(it.price)
                qty = float(it.qty or 0)
                amount = self._round2(it.amount)
                if not ref or not price or not qty or not amount:
                    continue

                expected_ref = round(ref * qty, 2)

                # A. Ціна вже типова, кількість є, а сума зіпсована OCR.
                # Приклад: 194,38 | 2 | 988,76 -> 388,76.
                if abs(price - ref) <= 0.01 and not self._amount_ok(price, qty, amount):
                    old = amount
                    it.amount = expected_ref
                    self._flag(it, "amountfix-pack")
                    self._record(inv, it, "SUMBPDV", old, it.amount, "price*qty with package price")
                    continue

                # B. Сума відповідає типовій ціні, але сама ціна зіпсована.
                # Приклад: 985,32 | 1 | 385,32 -> price 385,32.
                if abs(price - ref) > 0.01 and self._amount_ok(ref, qty, amount):
                    old = price
                    it.price = ref
                    self._flag(it, "pricefix-pack")
                    self._record(inv, it, "CINABPDV", old, it.price, "package price")
                    continue

                # C. Кількість склеїлась: 14 257,64 -> qty 1.
                if qty >= 10:
                    for q in self._candidate_qtys(qty):
                        if self._amount_ok(ref, q, amount):
                            old_qty = qty
                            old_price = price
                            it.qty = q
                            it.price = ref
                            self._flag(it, "qtyfix-pack")
                            self._record(inv, it, "QTY", old_qty, it.qty, "package price and amount")
                            if abs(old_price - ref) > 0.01:
                                self._record(inv, it, "CINABPDV", old_price, it.price, "package price after qty fix")
                            break

    # ------------------------------------------------------------


    def _history_ref(self, item, typical):
        # Історію НЕ вимикаємо лише через наявність типової ціни пакета.
        # OCR-рядок 985,32 | 1 | 985,32 математично коректний і може сам
        # створити фальшиву "типову" ціну. Тому історія використовується
        # як контроль відхилення > max_history_deviation.
        if not self.price_history or not getattr(self.price_history, "prices", None):
            return None
        if not item.product:
            return None
        code = str(getattr(item.product, "code", "") or "").strip()
        return self.price_history.get(code)

    def _price_deviation(self, price, ref):
        try:
            price = float(price or 0)
            ref = float(ref or 0)
            if price <= 0 or ref <= 0:
                return 0.0
            return abs(price - ref) / ref
        except Exception:
            return 0.0

    def _apply_history_price_control(self, invoices, typical):
        if not self.price_history or not getattr(self.price_history, "prices", None):
            return

        for inv in invoices:
            for it in inv.items:
                ref = self._history_ref(it, typical)
                if not ref:
                    continue

                price = self._round2(it.price)
                qty = float(it.qty or 0)
                amount = self._round2(it.amount)
                if not price or not qty or not amount:
                    continue

                deviation = self._price_deviation(price, ref)
                if deviation <= self.max_history_deviation:
                    continue

                expected = round(ref * qty, 2)

                # Найбезпечніший OCR-випадок: qty=1, price==amount, але обидва
                # далеко відлетіли від останньої підтвердженої ціни.
                # Приклад: 985,32 | 1 | 985,32, історична 385,32.
                if qty == 1 and abs(price - amount) <= 0.01:
                    old_price = price
                    old_amount = amount
                    it.price = ref
                    it.amount = expected
                    self._flag(it, "pricefix-history")
                    self._flag(it, "amountfix-history")
                    self._record(inv, it, "CINABPDV", old_price, it.price, "last confirmed price")
                    self._record(inv, it, "SUMBPDV", old_amount, it.amount, "last confirmed price")
                    continue

                # Якщо сума вже відповідає історичній ціні — виправляємо тільки ціну.
                if self._amount_ok(ref, qty, amount):
                    old = price
                    it.price = ref
                    self._flag(it, "pricefix-history")
                    self._record(inv, it, "CINABPDV", old, it.price, "last confirmed price")
                    continue

                # Якщо поточна ціна дає рядкову суму, але відхилення від історії надто велике,
                # не чіпаємо автоматично, а маркуємо для перевірки.
                self._flag(it, "pricewarn-history")

    def _apply_document_totals_control(self, invoices, typical):
        for inv in invoices:
            if not inv.items:
                continue

            doc_sum = self._round2(getattr(inv, "doc_sum", 0))
            doc_qty = self._round2(getattr(inv, "doc_qty", 0))

            for _ in range(4):
                changed = False
                qty_total = self._round2(sum(float(it.qty or 0) for it in inv.items))
                sum_total = self._round2(sum(float(it.amount or 0) for it in inv.items))

                # 1. Якщо рядок не сходиться, спочатку пробуємо виправити суму,
                # а не ціну. Ціна в OCR зазвичай надійніша, особливо якщо вона типова.
                for it in inv.items:
                    price = self._round2(it.price)
                    qty = float(it.qty or 0)
                    amount = self._round2(it.amount)
                    if not price or not qty or not amount:
                        continue
                    if self._amount_ok(price, qty, amount):
                        continue

                    expected = round(price * qty, 2)
                    key = self._key(it)
                    ref = typical.get(key) if key else None

                    # 1A. Якщо ціна збігається з типовою — сума точно підозріла.
                    if ref and abs(price - ref) <= 0.01:
                        old = amount
                        it.amount = expected
                        self._flag(it, "amountfix-pack")
                        self._record(inv, it, "SUMBPDV", old, it.amount, "price is package price")
                        changed = True
                        break

                    # 1C. Якщо кількість склеїлась і це підтверджується рядком/документом.
                    for q in self._candidate_qtys(qty):
                        if not self._amount_ok(price, q, amount):
                            continue
                        new_qty_total = qty_total - qty + q
                        if (not doc_qty) or abs(new_qty_total - doc_qty) <= 0.001:
                            old = qty
                            it.qty = q
                            self._flag(it, "qtyfix-docqty")
                            self._record(inv, it, "QTY", old, it.qty, "document quantity")
                            changed = True
                            break
                    if changed:
                        break

                if changed:
                    continue

                # 2. Рядки сходяться, але Σ(QTY) не сходиться з Всього.
                if doc_qty and abs(qty_total - doc_qty) > 0.001:
                    for it in inv.items:
                        price = self._round2(it.price)
                        qty = float(it.qty or 0)
                        amount = self._round2(it.amount)
                        if not price or not qty or not amount:
                            continue
                        for q in self._candidate_qtys(qty):
                            if not self._amount_ok(price, q, amount):
                                continue
                            new_qty_total = qty_total - qty + q
                            if abs(new_qty_total - doc_qty) <= 0.001:
                                old = qty
                                it.qty = q
                                self._flag(it, "qtyfix-docqty")
                                self._record(inv, it, "QTY", old, it.qty, "document quantity total")
                                changed = True
                                break
                        if changed:
                            break

                if changed:
                    continue

                # 3. Σ(SUM) не сходиться — пробуємо виправити одну суму.
                if doc_sum and abs(sum_total - doc_sum) > 0.10:
                    for it in inv.items:
                        price = self._round2(it.price)
                        qty = float(it.qty or 0)
                        amount = self._round2(it.amount)
                        if not price or not qty or not amount:
                            continue
                        expected = round(price * qty, 2)
                        if abs(expected - amount) <= 0.10:
                            continue
                        if abs((sum_total - amount + expected) - doc_sum) <= 0.10:
                            old = amount
                            it.amount = expected
                            self._flag(it, "amountfix-docsum")
                            self._record(inv, it, "SUMBPDV", old, it.amount, "document sum total")
                            changed = True
                            break

                if not changed:
                    break

    # ------------------------------------------------------------

    @staticmethod
    def confirmed_prices_for_history(invoices):
        """Повертає ITEM -> LASTPRICE, якщо ціна підтвердилась у >=2 різних накладних.

        Беремо тільки математично коректні рядки після всіх виправлень.
        """
        groups = defaultdict(set)
        helper = InvoiceValidator()
        for inv in invoices:
            doc = str(getattr(inv, "doc", "") or getattr(inv, "source_file", "") or "")
            for it in getattr(inv, "items", []):
                product = getattr(it, "product", None)
                code = str(getattr(product, "code", "") or "").strip()
                if not code:
                    continue
                price = helper._round2(getattr(it, "price", 0))
                qty = float(getattr(it, "qty", 0) or 0)
                amount = helper._round2(getattr(it, "amount", 0))
                if price > 0 and qty > 0 and amount > 0 and helper._amount_ok(price, qty, amount):
                    groups[(code, price)].add(doc)

        confirmed = {}
        for (code, price), docs in groups.items():
            if len(docs) >= 2:
                confirmed[code] = price
        return confirmed

    def _final_warnings(self, invoices):
        for inv in invoices:
            doc_sum = self._round2(getattr(inv, "doc_sum", 0))
            doc_qty = self._round2(getattr(inv, "doc_qty", 0))
            qty_total = self._round2(sum(float(it.qty or 0) for it in inv.items))
            sum_total = self._round2(sum(float(it.amount or 0) for it in inv.items))

            if doc_sum and abs(sum_total - doc_sum) > 0.10:
                for it in inv.items:
                    self._flag(it, "docsumwarn")
            if doc_qty and abs(qty_total - doc_qty) > 0.001:
                for it in inv.items:
                    self._flag(it, "docqtywarn")

            for it in inv.items:
                price = self._round2(it.price)
                qty = float(it.qty or 0)
                amount = self._round2(it.amount)
                if price and qty and amount and not self._amount_ok(price, qty, amount):
                    self._flag(it, "linewarn")
