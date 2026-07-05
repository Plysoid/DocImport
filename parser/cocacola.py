import re
from models.entities import Invoice, InvoiceItem
from utils.text import to_float


class CocaColaParser:
    PRODUCT_RE = re.compile(
        r"(?i)(?:"
        r"\d+[\.,]?\d*\s*(?:PET|РЕТ|ПЕТ|CAN|САМ)\s*[XХ]\s*\d+|"
        r"\d+[\.,]?\d*(?:PET|РЕТ|ПЕТ|CAN|САМ)[XХ]\d+|"
        r"(?:PET|РЕТ|ПЕТ|CAN|САМ)\s*[XХ]\s*\d+"
        r")"
    )


    def parse(self, source_file: str, page: int, text: str) -> Invoice:
        inv = Invoice(source_file=source_file, page=page, raw_text=text)
        inv.doc = self._doc(text)
        inv.date = self._date(text)
        inv.address = self._address_text(text)
        inv.doc_qty, inv.doc_sum, inv.doc_sum_source = self._doc_totals(text)
        inv.items = self._items(text)
        if not inv.doc and not inv.items:
            inv.status = "порожня/не розпізнана сторінка"
        else:
            inv.status = f"{len(inv.items)} рядків"
        return inv

    def _doc(self, text):
        m = re.search(r"Накладна\s*(?:№|Мо|Ме|No|Ne|Nº)?\s*([0-9]{6,15})", text, re.I)
        return m.group(1) if m else ""

    def _date(self, text):
        m = re.search(r"Дата\s*відвантаження\s*[: ]+\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})", text, re.I)
        if m:
            return m.group(1)
        m = re.search(r"([0-9]{2}\.[0-9]{2}\.[0-9]{4})", text)
        return m.group(1) if m else ""


    def _doc_totals(self, text):
        """Повертає контрольні підсумки товарного розділу: Σ(QTY), Σ(SUMBPDV).

        Пріоритет для суми: `Загальна сума без ПДВ`, потім рядок `Всього:`.
        Для кількості використовується перше число в рядку `Всього:`.
        Підтримує OCR-випадки без коми: 407650 -> 4076.50.
        """
        lines = [str(x or "").strip() for x in str(text or "").splitlines()]
        qty_total = 0.0
        amount_total = 0.0
        source = ""

        def number_tokens(line):
            out = []
            for raw in re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2}|\d+,\d{2}|\b\d{4,7}\b|\b\d{1,3}\b", line or ""):
                val = self._num(raw)
                out.append((raw, val))
            return out

        # 1) Всього: | 9 | 2.207,09 | |
        for i, line in enumerate(lines):
            u = line.upper()
            if not re.match(r"^\s*ВСЬОГО\s*[:|]", u):
                continue
            if "ДО ОПЛАТИ" in u or "З ПДВ" in u:
                continue

            vals = number_tokens(line)
            if not vals and i + 1 < len(lines):
                vals = number_tokens(lines[i + 1])

            numeric = [v for _, v in vals if v > 0]

            # Перше невелике ціле число у рядку `Всього:` — це сумарна кількість.
            for raw, val in vals:
                if re.fullmatch(r"\d{1,3}", raw) and 0 < val <= 999:
                    qty_total = float(val)
                    break

            # Останнє число, схоже на суму, — сума без ПДВ.
            amount_candidates = [v for _, v in vals if 10 <= v <= 999999]
            if amount_candidates:
                amount_total = round(amount_candidates[-1], 2)
                source = "Всього"
            break

        # 2) Суму уточнюємо по рядку `Загальна сума без ПДВ`, якщо він є.
        for line in lines:
            u = line.upper()
            if "ЗАГАЛЬНА" in u and "СУМА" in u and "ПДВ" in u:
                vals = number_tokens(line)
                amount_candidates = [v for _, v in vals if 10 <= v <= 999999]
                if amount_candidates:
                    amount_total = round(amount_candidates[-1], 2)
                    source = "Загальна сума без ПДВ"
                    break

        return qty_total, amount_total, source

    def _doc_sum(self, text):
        qty, amount, source = self._doc_totals(text)
        return amount, source

    def _address_text(self, text):
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        candidates = []

        # Адреса покупця у Coca-Cola йде у правому блоці шапки:
        # ... 79040, ЛЬВІВ
        # Тел.: 0322421292 КОПЕРНИКА 21
        # або просто наступним рядком: ШИРОКА 86-А
        service_markers = (
            "ЄДРПОУ", "IBAN", "ІВАМ", "ЇВАМ", "БАНКІВСЬКІ РЕКВІЗИТИ", "СІТІБАНК",
            "ЦЕНТР", "ВОДІЙ", "УВАГА", "ТОВАРНИЙ", "ПОСТАВКА", "НАКЛАДНА",
            "ЗАВАНТАЖЕН", "КОКА-КОЛА", "БЕВЕРІДЖИЗ"
        )

        for i, line in enumerate(lines):
            u = line.upper()
            matches = list(re.finditer(r"\b[0-9]{5}\s*,\s*[А-ЯІЇЄҐA-Z'’\- ]+", u))
            if not matches:
                continue

            m = matches[-1]
            city = line[m.start():].strip()
            city = re.sub(r"\s+", " ", city)
            if "ГОРОДНИЦ" in city.upper():
                continue

            street = ""
            for j in range(i + 1, min(i + 7, len(lines))):
                s = lines[j].strip()
                # рядок може бути: Тел.: 0322421292 БАНКІВСЬКА 3
                s = re.sub(r"^.*?(?:ТЕЛ\.?|TEN)\s*[: ]*\d{6,}\s*", "", s, flags=re.I).strip()
                s = s.strip(" |;:,.\t")
                if not s:
                    continue
                su = s.upper()
                if any(x in su for x in service_markers):
                    continue
                if len(s) <= 80:
                    street = s
                    break

            if street:
                candidates.append(f"{city} {street}")
                candidates.append(street)
            else:
                candidates.append(city)

        # повертаємо короткий адресний блок, а не весь OCR-текст
        return " | ".join(candidates) if candidates else ""

    def _items(self, text):
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        records = []
        current = []
        in_table = False
        for line in lines:
            u = line.upper()
            if "ТОВАРНИЙ" in u or "ШТРИХ" in u:
                in_table = True
                continue
            if not in_table:
                continue
            if u.startswith("ВСЬОГО") or "ЗАГАЛЬНА СУМА" in u or "ТАРА" in u:
                break
            # новий товарний рядок: починається з коду постачальника
            if re.match(r"^\d{4,8}\b", line):
                if current:
                    records.append(" ".join(current))
                current = [line]
            else:
                if current:
                    current.append(line)
        if current:
            records.append(" ".join(current))

        items = []
        for rec in records:
            item = self._parse_record(rec)
            if item:
                items.append(item)
        return items

    def _parse_record(self, rec):
        clean = re.sub(r"\s+", " ", rec.replace("|", " ")).strip()
        # OCR часто дає кириличну Х у X6 / X12. Для пошуку шаблону це не проблема,
        # але далі корисно мати однаковий текст.
        clean = clean.replace("Х", "X")
        clean = clean.replace("'", " ").replace("`", " ").replace("’", " ")
        m_code = re.match(r"^(\d{4,8})\b(.*)$", clean)
        if not m_code:
            return None
        rest = m_code.group(2).strip()
        m_prod = self.PRODUCT_RE.search(rest)
        if not m_prod:
            return None
        before = rest[:m_prod.start()]
        after = rest[m_prod.start():]

        digits = re.findall(r"\d+", before)
        barcode = "".join(digits)
        # залишаємо реалістичну довжину штрих-коду; OCR може додати сміття
        if len(barcode) > 13:
            barcode = barcode[:13]

        # назва до одиниці виміру, числа упаковки всередині назви не мають потрапити в ціну/кількість
        unit_match = re.search(r"\b(ЯЩ|AL|ALL|AU|AW|ШТ|ящ)\b", after, re.I)
        if unit_match:
            name = self._clean_item_name(after[:unit_match.start()].strip(" -;:,.|"))
            tail_text = after[unit_match.end():]
            unit = unit_match.group(1).upper()
        else:
            price_match = re.search(r"\d{2,4}[,.]\d{2}|\b\d{5}\b", after)
            if not price_match:
                return None
            name = self._clean_item_name(after[:price_match.start()].strip(" -;:,.|"))
            tail_text = after[price_match.start():]
            unit = "ЯЩ"
        if unit in ("AU", "AW", "AL", "ALL"):
            unit = "ЯЩ"

        parsed = self._price_qty_amount(tail_text)
        # Фолбек на весь хвіст after використовуємо тільки якщо після одиниці виміру
        # взагалі немає чисел. Інакше числа з назви (500 PET X12) зсувають колонки.
        if not parsed and not self._numbers(tail_text):
            parsed = self._price_qty_amount(after)
        if not parsed:
            return None
        price, qty, amount = parsed

        warnings = []

        # Якщо OCR зіпсував ціну, але кількість і сума виглядають коректно,
        # відновлюємо ціну як сума / кількість.
        # Приклад: 985,32 | 1 | 385,32 -> ціна має бути 385,32.
        if qty and amount and not self._amount_ok(price, qty, amount):
            price, qty, amount, fix_flag = self._reconcile_price_qty_amount(price, qty, amount)
            if fix_flag:
                warnings.append(fix_flag)

        qty, amount, fix_flag = self._fix_qty_amount(price, qty, amount)
        if fix_flag:
            warnings.append(fix_flag)

        # Якщо OCR втратив кому у ціні/сумі: 25764 -> 257.64, 128820 -> 1288.20.
        if re.search(r"\b\d{5,6}\b", tail_text or ""):
            warnings.append("numfix")

        warning = "+".join(dict.fromkeys(warnings))

        return InvoiceItem(raw_name=name, barcode=barcode, qty=qty, unit=unit, price=price, amount=amount, parse_warning=warning)

    def _clean_item_name(self, name):
        name = str(name or "")
        name = name.replace("'", " ").replace("`", " ").replace("’", " ")
        name = re.sub(r"\b0?7442\b.*$", "", name).strip(" -;:,.|")
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def _price_qty_amount(self, s):
        """
        Надійно дістає price / qty / amount з хвоста товарного рядка.

        Типові OCR-випадки:
        - 385,32 1 385.32 5     де 5 — перенесена 13-та цифра штрихкоду;
        - 23883 3 71649         де коми втрачені;
        - 238,83 З 716,49       де кількість 3 прочиталась як кирилична З.
        """
        vals = self._number_tokens(s)

        # 1) Шукаємо трійку, яка математично сходиться: price * qty ~= amount.
        # Це захищає від хвостового checksum-рядка штрихкоду.
        best = None
        for i in range(len(vals) - 2):
            price = vals[i]
            qty = vals[i + 1]
            amount = vals[i + 2]
            if not self._looks_price(price):
                continue
            if not self._looks_qty(qty):
                continue
            if not self._looks_amount(amount):
                continue
            if self._amount_ok(price, qty, amount):
                return price, qty, amount
            # запасний кандидат: ціна/кількість/сума у нормальних діапазонах
            if best is None:
                best = (price, qty, amount)

        if best:
            # Важливо: тут не змінюємо суму на основі ціни.
            # OCR може помилитися саме в ціні: 985,32 | 1 | 385,32.
            # Узгодження робимо пізніше в _reconcile_price_qty_amount().
            return best

        # 2) OCR може прочитати кількість 3 як З/Z, і тоді з чисел лишаються ціна та сума.
        decimals = re.findall(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2}|\d+,\d{2}|\b\d{4,5}\b", s or "")
        nums = [self._num(x) for x in decimals]
        nums = [x for x in nums if x > 0]
        if len(nums) >= 2:
            price = nums[0]
            amount = nums[-1]
            if self._looks_price(price) and self._looks_amount(amount):
                qty = round(amount / price)
                if self._looks_qty(qty) and self._amount_ok(price, qty, amount):
                    return price, float(qty), amount
        return None

    def _number_tokens(self, s):
        tokens = re.findall(
            r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2}|\d+,\d{2}|\b\d+\b",
            s or ""
        )
        vals = []
        for t in tokens:
            v = self._num(t)
            if 0 < v < 100000:
                vals.append(v)
        return vals

    def _numbers(self, s):
        return self._number_tokens(s)

    def _num(self, t):
        s = str(t).strip().replace(" ", "")
        if not s:
            return 0.0

        # Український формат із комою: 1.158,24 -> 1158.24, 385,32 -> 385.32
        if "," in s:
            return to_float(s)

        # Крапка як десятковий розділювач: 385.32 -> 385.32.
        # Важливо: старий to_float видаляв крапку і робив 38532.
        if re.fullmatch(r"\d+\.\d{2}", s):
            try:
                return float(s)
            except Exception:
                return 0.0

        # Втрачені коми: 36252 -> 362.52, 23883 -> 238.83.
        if s.isdigit() and len(s) >= 4:
            return float(s[:-2] + "." + s[-2:])

        try:
            return float(s)
        except Exception:
            return 0.0

    def _looks_price(self, v):
        return 10 <= float(v) <= 5000

    def _looks_qty(self, v):
        # кількість у накладних — практично завжди ціле число ящиків
        return float(v).is_integer() and 0 < float(v) <= 999

    def _looks_amount(self, v):
        return 10 <= float(v) <= 999999

    def _amount_ok(self, price, qty, amount):
        return abs(float(price) * float(qty) - float(amount)) <= max(0.10, float(price) * 0.02)

    def _reconcile_price_qty_amount(self, price, qty, amount):
        """Виправляє OCR-помилки, не знищуючи коректну суму.

        Головне правило: якщо кількість і сума виглядають правдоподібно,
        а ціна не сходиться, спочатку довіряємо сумі з накладної.
        """
        price = float(price or 0)
        qty = float(qty or 0)
        amount = float(amount or 0)

        if not price or not qty or not amount:
            return price, qty, amount, ""

        # Типовий випадок: ціна OCR помилкова, а сума і кількість правильні.
        # 985,32 | 1 | 385,32 -> price = 385,32, amount = 385,32.
        if qty == 1 and self._looks_price(amount):
            return round(amount, 2), qty, round(amount, 2), "pricefix"

        # Якщо кількість склеїлась з першою цифрою суми: 14 257,64,
        # а price * 1 = amount, не перетворюємо це на ціну 18,40.
        if qty >= 10 and self._amount_ok(price, 1, amount):
            return price, 1.0, amount, "qtyfix"

        # Якщо з суми та кількості виходить нормальна ціна — відновлюємо її.
        derived_price = round(amount / qty, 2) if qty else 0
        if self._looks_price(derived_price) and self._amount_ok(derived_price, qty, amount):
            return derived_price, qty, amount, "pricefix"

        # Якщо ціна і сума дають цілу кількість — виправляємо кількість.
        computed_qty = round(amount / price) if price else 0
        if self._looks_qty(computed_qty) and self._amount_ok(price, computed_qty, amount):
            return price, float(computed_qty), amount, "qtyfix"

        return price, qty, amount, "warn"

    def _fix_qty_amount(self, price, qty, amount):
        """Обережні виправлення після основного узгодження.

        Не можна робити amount = price тільки тому, що qty == 1:
        саме так псувалась правильна сума 385,32 у рядку з помилковою ціною 985,32.
        """
        price = float(price or 0)
        qty = float(qty or 0)
        amount = float(amount or 0)

        if not price or not amount:
            return qty, amount, ""

        if self._amount_ok(price, qty, amount):
            return qty, amount, ""

        # типова OCR-помилка: кількість склеїлась з сусідньою цифрою (11 замість 1)
        if qty >= 10 and abs(amount - price) <= max(0.10, price * 0.01):
            return 1.0, amount, "qtyfix"

        # якщо сума менша за ціну при великій кількості — найчастіше кількість зайва
        if qty >= 10 and amount < price:
            return 1.0, amount, "qtywarn"

        return qty, amount, "warn"
