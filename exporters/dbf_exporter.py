from pathlib import Path
import dbf
from utils.text import to_date


class DBFExporter:
    SPEC = (
        "DOC C(20); DATE D; SHOP C(3); ADDRESS C(50); ADDRNAKL C(100); "
        "ITEM C(8); ITEMNAME C(50); ITEMNAKL C(50); ITEMSHK C(13); "
        "QTY N(10,3); ODVYM C(10); CINABPDV N(18,3); SUMBPDV N(18,3); MATCH C(50)"
    )

    def export(self, invoices, filename):
        p = Path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            p.unlink()
        table = dbf.Table(str(p), self.SPEC, codepage="cp1251")
        table.open(mode=dbf.READ_WRITE)
        try:
            for inv in invoices:
                sh = inv.shop
                for it in inv.items:
                    pr = it.product
                    table.append((
                        (inv.doc or "")[:20],
                        to_date(inv.date),
                        (sh.code if sh else "")[:3],
                        ((sh.address if sh else "") or "")[:50],
                        (inv.address or "")[:100],
                        (pr.code if pr else "")[:8],
                        (pr.name if pr else "")[:50],
                        (it.raw_name or "")[:50],
                        ((pr.barcode if pr else it.barcode) or "")[:13],
                        float(it.qty or 0),
                        (it.unit or "ЯЩ")[:10],
                        float(it.price or 0),
                        float(it.amount or 0),
                        (it.match_method or "")[:50],
                    ))
        finally:
            table.close()
