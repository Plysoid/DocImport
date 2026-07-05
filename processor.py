from pathlib import Path
from catalogs.products import ProductCatalog
from catalogs.shops import ShopCatalog
from ocr.reader import OCRReader
from parser.cocacola import CocaColaParser
from exporters.excel_exporter import ExcelExporter
from exporters.dbf_exporter import DBFExporter
from exporters.correction_exporter import CorrectionExporter
from validators.invoice_validator import InvoiceValidator


class Processor:
    def __init__(self, settings, log=lambda s: None):
        self.settings = settings
        self.log = log
        self.products = ProductCatalog()
        self.shops = ShopCatalog()
        self.ocr = OCRReader(settings)
        self.parser = CocaColaParser()

    def files(self):
        folder = Path(self.settings.input_dir)
        seen = set()
        out = []
        for ext in ("*.pdf", "*.jpg", "*.jpeg", "*.png", "*.tif", "*.tiff"):
            for f in folder.glob(ext):
                key = str(f.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    out.append(f)
        return sorted(out)

    def run(self):
        CorrectionExporter().ensure_templates(Path(self.settings.products_file).parent)
        self.products.load(self.settings.products_file)
        self.shops.load(self.settings.shops_file)
        self.log(f"Товарів у довіднику: {len(self.products.items)}")
        self.log(f"Магазинів у довіднику: {len(self.shops.items)}")
        invoices = []
        for f in self.files():
            self.log(f"Обробка: {f.name}")
            pages = self.ocr.read_file(f)
            for pg in pages:
                text_upper = str(pg["text"] or "").upper()
                if "ОВАЦІЯ" not in text_upper:
                    self.log(f"  стор. {pg['page']}: чужий документ або не наша фірма, пропущено")
                    continue

                inv = self.parser.parse(f.name, pg["page"], pg["text"])
                shop, shop_method = self.shops.find(inv.address or pg["text"])
                inv.shop = shop
                if not inv.doc and not inv.items:
                    self.log(f"  стор. {pg['page']}: порожня/не розпізнана, пропущено")
                    continue
                for it in inv.items:
                    pr, method = self.products.find(it.barcode, it.raw_name)
                    it.product = pr
                    if getattr(it, "parse_warning", ""):
                        method = self._add_match_flags(method, it.parse_warning)
                    it.match_method = method
                invoices.append(inv)
                self.log(f"  стор. {pg['page']}: DOC={inv.doc}; SHOP={(shop.code if shop else '')}; рядків={len(inv.items)}")
        InvoiceValidator().validate(invoices, self._add_match_flags)
        out = Path(self.settings.output_dir)
        ExcelExporter().export(invoices, out / "result.xlsx")
        DBFExporter().export(invoices, out / "result.dbf")
        CorrectionExporter().export_unknowns(invoices, out)
        self.log("Готово: output/result.xlsx, output/result.dbf")
        self.log("Діагностика: output/unknown_products.xlsx, output/unknown_addresses.xlsx, output/warnings.xlsx, output/fixes.xlsx")
        return invoices

    def _add_match_flags(self, base, *flags):
        parts = []
        for chunk in (base, *flags):
            for part in str(chunk or "").split("+"):
                part = part.strip()
                if part and part not in parts:
                    parts.append(part)
        return "+".join(parts)
