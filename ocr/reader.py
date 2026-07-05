from pathlib import Path
from PIL import Image
import fitz
import pytesseract
import cv2
import numpy as np


class OCRReader:
    def __init__(self, settings):
        self.settings = settings

    def _prep(self, image: Image.Image) -> Image.Image:
        img = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        return Image.fromarray(gray)

    def _ocr(self, image: Image.Image, psm=None) -> str:
        img = self._prep(image)
        cfg = f"--oem {self.settings.oem} --psm {psm or self.settings.psm}"
        return pytesseract.image_to_string(img, lang=self.settings.ocr_language, config=cfg)

    def read_file(self, filename):
        p = Path(filename)
        if p.suffix.lower() == ".pdf":
            return self.read_pdf(p)
        return [self.read_image(p, 1)]

    def read_pdf(self, filename):
        out = []
        with fitz.open(filename) as doc:
            for i in range(len(doc)):
                page = doc.load_page(i)
                pix = page.get_pixmap(dpi=self.settings.dpi, alpha=False)
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text = self._ocr(img, psm=6)
                out.append({"page": i + 1, "text": text, "image": img})
                if self.settings.save_debug:
                    Path("logs").mkdir(exist_ok=True)
                    img.save(Path("logs") / f"{filename.stem}_p{i+1}.png")
                    (Path("logs") / f"{filename.stem}_p{i+1}.txt").write_text(text, encoding="utf-8")
        return out

    def read_image(self, filename, page=1):
        img = Image.open(filename).convert("RGB")
        # фото частіше краще читається як блоки, не як одна колонка
        text = self._ocr(img, psm=4)
        if self.settings.save_debug:
            Path("logs").mkdir(exist_ok=True)
            (Path("logs") / f"{Path(filename).stem}.txt").write_text(text, encoding="utf-8")
        return {"page": page, "text": text, "image": img}
