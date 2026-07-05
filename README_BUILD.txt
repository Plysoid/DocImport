DocImport v3.3.1

Запуск з Python:
1. py -3.12 -m venv venv
2. venv\Scripts\activate
3. pip install -r requirements.txt
4. python main.py

Збірка EXE на Windows 10/11:
1. Встановити Python 3.12 x64.
2. Запустити build_exe.bat.
3. Готова програма буде в dist\DocImport\DocImport.exe.

Для чистого Windows 10:
- Python не потрібен, якщо запускаєте з dist\DocImport.
- Потрібен Tesseract OCR. Рекомендований portable-варіант:

DocImport\
  DocImport.exe
  data\
  input\
  output\
  logs\
  tesseract\
    tesseract.exe
    tessdata\
      ukr.traineddata
      eng.traineddata

Якщо Tesseract встановлено системно, portable-папка tesseract не обов'язкова.

Зміни v3.2.0:
- очищення папки logs при запуску;
- версія у заголовку програми: DocImport v3.3.1;
- додано build_exe.bat і DocImport.spec;
- додано підтримку portable tesseract\tesseract.exe.
