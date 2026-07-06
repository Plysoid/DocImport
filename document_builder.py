import re
from dataclasses import dataclass, field


@dataclass
class DocumentPage:
    page: int
    text: str = ""


@dataclass
class DocumentText:
    source_file: str
    page: int
    pages: list[int] = field(default_factory=list)
    text: str = ""
    doc: str = ""

    @property
    def page_label(self):
        if not self.pages:
            return str(self.page)
        if len(self.pages) == 1:
            return str(self.pages[0])
        return f"{self.pages[0]}-{self.pages[-1]}"


class DocumentBuilder:
    """Збирає OCR-сторінки в логічні документи перед парсингом.

    Мета: якщо товарний розділ закінчується на наступній сторінці або
    підсумки документа винесені на наступну сторінку, parser має отримати
    один об'єднаний текст документа.
    """

    def build(self, source_file, pages):
        documents = []
        current = None

        for pg in sorted(pages, key=lambda x: int(x.get("page", 0) or 0)):
            page_no = int(pg.get("page", 0) or 0)
            text = str(pg.get("text") or "")
            doc = self.doc_number(text)

            if current is None:
                current = self._new_doc(source_file, page_no, text, doc)
                continue

            if self._should_append(current, page_no, text, doc):
                self._append_page(current, page_no, text, doc)
                continue

            documents.append(current)
            current = self._new_doc(source_file, page_no, text, doc)

        if current is not None:
            documents.append(current)

        return documents

    def _new_doc(self, source_file, page_no, text, doc):
        return DocumentText(
            source_file=source_file,
            page=page_no,
            pages=[page_no],
            text=str(text or ""),
            doc=doc or "",
        )

    def _append_page(self, current, page_no, text, doc):
        current.pages.append(page_no)
        # Розділювач потрібний, щоб випадково не склеїти кінець одного рядка
        # з початком наступної OCR-сторінки.
        current.text = current.text.rstrip() + "\n\n--- PAGE BREAK ---\n\n" + str(text or "").lstrip()
        if not current.doc and doc:
            current.doc = doc

    def _should_append(self, current, page_no, text, doc):
        # Не склеюємо не сусідні сторінки.
        if current.pages and page_no != current.pages[-1] + 1:
            return False

        current_doc = current.doc or ""
        next_doc = doc or ""

        # Найнадійніший випадок: той самий номер накладної на наступній сторінці.
        if current_doc and next_doc and current_doc == next_doc:
            return self._needs_continuation(current.text) or self._looks_like_continuation(text)

        # Якщо номер на наступній сторінці OCR не прочитав, але попередня сторінка
        # не завершена, а наступна виглядає як продовження/підсумки.
        if current_doc and not next_doc:
            return self._needs_continuation(current.text) and self._looks_like_continuation(text)

        return False

    def _needs_continuation(self, text):
        """Сторінка виглядає як незавершений товарний розділ."""
        u = str(text or "").upper()
        if "ТОВАРНИЙ" not in u and "ШТРИХ" not in u:
            return False
        return not self._has_document_totals(u)

    def _looks_like_continuation(self, text):
        u = str(text or "").upper()
        if self._has_document_totals(u):
            return True
        if "ТАРА" in u:
            return True
        if "ТОВАРНИЙ" in u or "ШТРИХ" in u:
            return True
        # продовження товарного блоку без шапки таблиці: рядок починається з коду товару
        return bool(re.search(r"(?m)^\s*\d{4,8}\b", str(text or "")))

    def _has_document_totals(self, upper_text):
        return (
            re.search(r"(?m)^\s*ВСЬОГО\s*[:|]", upper_text or "") is not None
            or "ЗАГАЛЬНА СУМА" in (upper_text or "")
            or "ВСЬОГО ДО ОПЛАТИ" in (upper_text or "")
        )

    def doc_number(self, text):
        m = re.search(r"Накладна\s*(?:№|Мо|Ме|No|Ne|Nº)?\s*([0-9]{6,15})", str(text or ""), re.I)
        return m.group(1) if m else ""
