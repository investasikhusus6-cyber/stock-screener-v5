# Stock Screener Web V5

V5 mempertahankan mesin scoring V3 dan menambahkan:
- Analisis laporan fundamental hingga 5 periode yang tersedia.
- Tahun berjalan memakai TTM/data terbaru bila Yahoo Finance menyediakannya, dan diberi label `TTM`.
- Tabel per tahun: Revenue, Net Income, ROE, ROA, NPM, growth, Debt/Equity, dan harga akhir tahun bila tersedia.
- Grafik tren Revenue dan Net Income.
- Kesimpulan screening di bagian paling bawah.
- Tetap mendukung saham Indonesia seperti BBCA -> BBCA.JK.

## Jalankan Windows
1. Install Python 3.11+.
2. Jalankan `run_local.bat`, atau:
   `python -m pip install -r requirements.txt`
   `python app.py`
3. Buka `http://127.0.0.1:5000`.

## Hosting
Project sudah disiapkan untuk Render melalui `render.yaml` dan `Procfile`.

## Catatan periode
FY = fiscal year/laporan tahunan yang tersedia.
TTM = trailing twelve months/data terbaru yang tersedia; bukan otomatis FY penuh.
Yahoo Finance/yfinance tidak selalu menyediakan 5 periode lengkap untuk setiap emiten. UI menampilkan periode yang benar-benar tersedia, bukan mengarang data.

Hasil screening bukan nasihat investasi. Verifikasi angka penting dengan laporan resmi emiten/BEI.
