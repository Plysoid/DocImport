from pathlib import Path
from openpyxl import Workbook


class ExcelExporter:
    def export(self, invoices, filename):
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        wb = Workbook()
        ws = wb.active
        ws.title = "result"
        headers = [
            "DOC", "DATE", "SHOP", "ADDRESS", "ADDRNAKL",
            "ITEM", "ITEMNAME", "ITEMNAKL", "ITEMSHK",
            "QTY", "ODVYM", "CINABPDV", "SUMBPDV",
            "FILE", "PAGE", "DOCQTY", "DOCSUM", "MATCH"
        ]
        ws.append(headers)
        for inv in invoices:
            for it in inv.items:
                pr = it.product
                sh = inv.shop
                ws.append([
                    inv.doc,
                    inv.date,
                    sh.code if sh else "",
                    sh.address if sh else "",
                    inv.address,
                    pr.code if pr else "",
                    pr.name if pr else "",
                    it.raw_name,
                    pr.barcode if pr else it.barcode,
                    it.qty,
                    it.unit,
                    it.price,
                    it.amount,
                    inv.source_file,
                    inv.page,
                    getattr(inv, "doc_qty", 0),
                    inv.doc_sum,
                    it.match_method,
                ])
        wb.save(filename)
