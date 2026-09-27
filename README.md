# Stock Screener V5.1 — Vercel Ready

Versi web Flask dari Stock Screener V5.1, siap di-upload ke GitHub lalu di-import ke Vercel.

## Isi
- Analisis saham `.JK` otomatis
- Snapshot fundamental terbaru
- Rata-rata fundamental dari periode tahunan yang tersedia
- TTM jika Yahoo Finance menyediakannya
- PER/PBV historis jika tersedia
- Grafik Revenue & Net Income
- Multi-ticker sampai 10 kode
- API `/api/analyze?ticker=BBCA`
- Health check `/health`

## Deploy ke Vercel
1. Extract ZIP ini.
2. Upload seluruh isi folder ke repository GitHub baru, misalnya `stock-screener-v5-1`.
3. Di Vercel pilih **Add New → Project**.
4. Pilih repository tersebut.
5. Biarkan Root Directory di root repository.
6. Tidak perlu memasukkan Build Command khusus.
7. Klik Deploy.

Vercel saat ini mendukung Flask secara langsung melalui Python runtime, jadi proyek ini sengaja memakai `app.py` di root dan tidak membutuhkan `vercel.json` atau `Procfile`.

## Local Windows

```bat
python -m pip install -r requirements.txt
python app.py
```

Buka `http://127.0.0.1:5000`.

## Catatan
Data berasal dari Yahoo Finance melalui `yfinance`. Data pasar dapat terlambat/berubah dan beberapa field bisa kosong. Hasil screening bukan instruksi beli/jual; verifikasi laporan resmi emiten/BEI.
