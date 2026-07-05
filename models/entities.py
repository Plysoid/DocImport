from dataclasses import dataclass, field


@dataclass
class Product:
    code: str = ""
    name: str = ""
    barcode: str = ""


@dataclass
class Shop:
    code: str = ""
    address: str = ""


@dataclass
class InvoiceItem:
    raw_name: str = ""
    barcode: str = ""
    qty: float = 0.0
    unit: str = "ЯЩ"
    price: float = 0.0
    amount: float = 0.0
    product: Product | None = None
    match_method: str = ""
    parse_warning: str = ""


@dataclass
class Invoice:
    source_file: str = ""
    page: int = 1
    doc: str = ""
    date: str = ""
    address: str = ""
    shop: Shop | None = None
    items: list[InvoiceItem] = field(default_factory=list)
    status: str = ""
    raw_text: str = ""
    doc_sum: float = 0.0
    doc_qty: float = 0.0
    doc_sum_source: str = ""
