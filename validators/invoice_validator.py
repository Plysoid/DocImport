from collections import Counter, defaultdict


class InvoiceValidator:
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

        # 2. Контроль підсумків документа: Σ(QTY), Σ(SUM).
        self._apply_document_totals_control(invoices, typical)

        # 3. Повторний контроль після виправлень.
        typical = self._typical_prices_from_good_rows(invoices)
        self._apply_package_price_control(invoices, typical)
        self._apply_document_totals_control(invoices, typical)

        # 4. Фінальне маркування попереджень.
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

                    # 1B. Якщо заміна суми закриває суму документа.
                    if doc_sum and abs((sum_total - amount + expected) - doc_sum) <= 0.10:
                        old = amount
                        it.amount = expected
                        self._flag(it, "amountfix-docsum")
                        self._record(inv, it, "SUMBPDV", old, it.amount, "document sum")
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

                    # 1D. Виводити ціну із amount/qty можна тільки якщо підсумок
                    # документа вже підтверджує суму. Інакше це породжує 494,38 з 988,76/2.
                    if doc_sum and abs(sum_total - doc_sum) <= 0.10 and qty:
                        derived = round(amount / qty, 2)
                        if 10 <= derived <= 5000 and abs(derived - price) > 0.01:
                            old = price
                            it.price = derived
                            self._flag(it, "pricefix-docsum")
                            self._record(inv, it, "CINABPDV", old, it.price, "document sum confirms amount")
                            changed = True
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
