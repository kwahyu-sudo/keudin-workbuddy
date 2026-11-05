# KeUdin Wrapper — Cara Pakai

CLI satu file (`keudin.py`) pemanggil API KeUdin untuk WorkBuddy.
Satu perintah = satu langkah skill `SKILL.md`. Baca skill itu dulu
sebelum menjalankan alur — wrapper ini hanya memanggil API, keputusan
(termasuk approval) tetap di tangan manusia lewat WorkBuddy.

## Prasyarat

- Python 3.8+ (cek: `python --version` atau `py --version` di Windows).
- **Tanpa dependency** — hanya standard library (`urllib`, `argparse`,
  `json`). Tidak perlu `pip install` apa pun, di Windows/macOS/Linux.
- File: `keudin.py` di folder ini. Jalankan dari folder ini, misal:
  `python keudin.py trips` (Windows bisa pakai `py keudin.py trips`).

## 1. Set API key SEKALI

Key **hanya** dibaca dari environment variable `KEUDIN_API_KEY`, dikirim
sebagai header `X-API-Key` pada setiap request `/api/*`. Wrapper tidak
pernah mencetak nilai key, tidak menuliskannya ke file, dan tidak
memiliki key bawaan. Bila env kosong, wrapper menolak sebelum request
apa pun dibuat (exit 2).

Ganti `<KEUDIN_API_KEY>` dengan key asli dari operator — jangan pernah
menempelkan nilai asli ke chat, dokumen, atau laporan.

### Windows — permanen (berlaku untuk terminal BARU)

```cmd
setx KEUDIN_API_KEY "<KEUDIN_API_KEY>"
```

Tutup terminal, buka terminal baru, lalu cek (cek ini hanya membuktikan
variabel ada — jangan tampilkan nilainya ke orang lain):

```cmd
echo %KEUDIN_API_KEY:~0,3%
```

### Windows — sesi berjalan saja (PowerShell, langsung aktif)

```powershell
$env:KEUDIN_API_KEY="<KEUDIN_API_KEY>"
```

Berlaku hanya di jendela PowerShell itu; tutup jendela = hilang.
Untuk sesi permanen, pakai `setx` di atas.

### macOS / Linux — sesi berjalan saja

```bash
export KEUDIN_API_KEY="<KEUDIN_API_KEY>"
```

Agar permanen, tambahkan baris yang sama ke `~/.bashrc` atau `~/.zshrc`,
lalu buka terminal baru.

### Base URL

Default: `https://hackeu.akalimitasi.my.id` (demo live).
Override bila perlu — urutan menang: flag `--base-url` > env
`KEUDIN_BASE_URL` > default. Untuk uji lokal saja:
`python keudin.py --base-url http://127.0.0.1:8090 trips`.

### User-Agent

Wrapper mengirim `User-Agent: keudin-cli/1.0 (+workbuddy)` di semua
request — Cloudflare di depan demo memblokir UA default Python-urllib
(HTTP 403 Error 1010, terbukti dari Windows 26 Okt 2026). Override
bila perlu lewat env `KEUDIN_USER_AGENT`.

## 2. Tabel perintah per langkah skill

| Langkah skill | Perintah wrapper |
|---|---|
| 1/2 — Upload ST/SPD baru | `python keudin.py upload surat_tugas.pdf [--bukti kuitansi1.png --bukti kuitansi2.jpg]` |
| 1 — Daftar trip | `python keudin.py trips` |
| 3/4/5 — Detail trip | `python keudin.py trip <id>` |
| 4 — Koreksi trip | `python keudin.py update <id> --json '{...}'` atau `--set ...` (lihat §3) |
| 4 — Pengeluaran manual | `python keudin.py add-expense <id> [--json '{...}']` (lihat catatan §3) |
| 2 — Kuitansi susulan | `python keudin.py upload-bukti <id> kuitansi.png` (satu file per panggilan) |
| 5/6 — Approval | `python keudin.py approve <id>` lalu, setelah user setuju, `python keudin.py approve <id> --confirm` |
| 6 — Daftar arsip | `python keudin.py archives` |
| 6 — Unduh arsip | `python keudin.py download <archive_id> [--out hasil.zip]` |
| Pembuka sesi — Statistik | `python keudin.py stats` |

Semua perintah JSON mencetak JSON ringkas ke stdout (bisa dibaca
WorkBuddy). Error dicetak singkat Bahasa Indonesia ke stderr dengan
exit code non-nol. Flag global `--base-url` dan `--timeout` (detik,
default 180; upload memakai minimal 300) bisa diletakkan sebelum
maupun sesudah nama perintah.

Contoh output (id dan angka hanya contoh):

```bash
python keudin.py upload surat_tugas.pdf --bukti hotel.png
# {"kegiatan_id": 12, "message": "Upload & ekstraksi berhasil."}

python keudin.py trip 12
# {"kegiatan": {"id": 12, "nomor_surat_tugas": "ST/001/2026",
#   "kota_tujuan": "Bandung", "tanggal_berangkat": "2026-11-03",
#   "tanggal_kembali": "2026-11-05"},
#  "pelaksana": [{"nama": "Budi", "nip": "19880101",
#   "pangkat": "Penata", "golongan": "III/c"}],
#  "pengeluaran": [{"jenis": "kuitansi_hotel", "nominal": 1500000}],
#  "status": "..."}

python keudin.py stats
# {"perlu_review": 2, "selesai_bulan_ini": 5}
```

## 3. Bentuk body yang BENAR — baca ini sebelum `update`

Server **tidak** menerima field datar di `PUT /api/trips/{id}`.
Body wajib bersarang:

```json
{
  "kegiatan": {"kota_tujuan": "Bandung", "tanggal_kembali": "2026-11-05"},
  "pelaksana": [{"id": 1, "nama": "Budi", "nip": "19880101"}],
  "pengeluaran": [{"id": 7, "jenis": "kuitansi_hotel", "nominal": 1500000}]
}
```

Field `kegiatan` yang bisa diubah: `nomor_surat_tugas`,
`tanggal_surat_tugas`, `dasar_hukum`, `maksud_perjalanan`, `kota_tujuan`,
`tanggal_berangkat`, `tanggal_kembali`, `pejabat_penandatangan`.
Field `pelaksana`: `nama`, `nip`, `pangkat`, `golongan`, `ruang`,
`jabatan`, `unit_kerja` (wajib sertakan `id`). Field `pengeluaran`:
`jenis`, `nominal`, `tanggal`, `vendor`, `no_bukti`, `pelaksana_id`
(wajib sertakan `id`). Field di luar daftar ini diabaikan server. PUT bersifat merge:
hanya field yang dikirim yang diubah; field yang tidak dikirim tetap
(tidak ter-null) — jadi update nama saja aman, tidak wajib kirim
objek penuh.

Alternatif `--set` (lebih mudah diketik WorkBuddy, tanpa JSON):

```bash
python keudin.py update 12 --set kegiatan.kota_tujuan=Bandung
python keudin.py update 12 --set pelaksana.0.nama=Budi --set pelaksana.0.nip=19880101
```

Catatan: `--set` memakai indeks list (`pelaksana.0...`), bukan `id`.
Untuk `pelaksana`/`pengeluaran`, cara paling aman adalah `--json`
dengan `id` eksplisit dari `trip <id>`. `--set` dan `--json` boleh
digabung (`--set` menimpa `--json`).

**Catatan `add-expense`:** server saat ini **mengabaikan body** dan
selalu membuat baris kosong (`jenis: bukti_lain`, nominal 0, pelaksana
pertama bila ada). Jadi alurnya dua langkah: (1) `add-expense <id>`
→ catat `id` pengeluaran dari respons; (2) `update <id> --json
'{"pengeluaran": [{"id": <id_baru>, "jenis": "...", "nominal": ...}]}'`
untuk mengisi nilainya. Jangan mengira `--json` di `add-expense`
langsung mengisi data.

**Catatan ID:** respons upload memakai field `kegiatan_id`
(bukan `trip_id`); id arsip di `archives`/`download` sama dengan
id trip/kegiatan. `download` tanpa `--out` memakai nama file dari
server, atau `arsip-<id>.zip` bila server tidak memberi nama.

## 4. Gerbang approval (wajib dibaca WorkBuddy)

```bash
python keudin.py approve 12
```

Perintah ini **hanya** mengambil detail trip, mencetak RINGKASAN FINAL
format skill (pelaksana, NIP, pangkat/golongan, tujuan, tanggal +
jumlah hari, nomor ST, total + jumlah item, daftar 5 dokumen), lalu
**BERHENTI** dengan pesan `belum ada approval` dan exit code 3 —
endpoint approve **tidak** dipanggil. Ini gerbang mekanis yang
mencerminkan gerbang manusia di skill Langkah 5.

Hanya setelah user menjawab setuju secara jelas atas ringkasan itu,
jalankan:

```bash
python keudin.py approve 12 --confirm
```

Approve bersifat final: 5 dokumen langsung di-generate (SPD lembar 1,
rincian biaya, rincian transportasi, daftar nominatif, RPAK).
Trip yang sudah pernah di-approve ditolak server bila di-approve lagi
(HTTP 400).

## 5. Error & exit code

| Kondisi | Pesan (stderr) | Exit |
|---|---|---|
| `KEUDIN_API_KEY` kosong di env lokal | `KEUDIN_API_KEY belum diset di environment...` (tanpa request) | 2 |
| HTTP 401 | Server menolak akses (API key tidak cocok) | 1 |
| HTTP 503 | Server KeUdin belum dikonfigurasi API key-nya | 1 |
| HTTP 422 | File tidak bisa dibaca sebagai dokumen valid | 1 |
| HTTP 404 | Data dengan ID itu tidak ditemukan di server | 1 |
| HTTP 400 (mis. sudah di-approve / blocking) | Permintaan ditolak server + alasan server | 1 |
| HTTP 413 / 429 | File melebihi 20 MB / terlalu banyak request | 1 |
| Koneksi gagal / timeout | Server KeUdin tidak bisa dihubungi saat ini | 1 |
| `approve` tanpa `--confirm` | Belum ada approval (gerbang, bukan error) | 3 |
| Argumen / file lokal / JSON tidak valid | Pesan pemakaian | 2 |

Catatan: HTTP 401 bisa berarti key lokal salah ATAU key server berbeda
— periksa keduanya, jangan pernah menampilkan nilai key saat memeriksa.

## 6. Langkah berikutnya (untuk Iwan — BUKAN dijalankan di sini)

1. Set `KEUDIN_API_KEY` di mesin WorkBuddy (§1 di atas).
2. Berikan file skill ke WorkBuddy:
   SKILL.md (di folder ini)
   beserta wrapper ini (`keudin.py` di folder ini).
3. Perintah pertama ke WorkBuddy (SPD ke Bandung 3 hari), contoh:

> Pakai skill KeUdin di SKILL.md dan wrapper `keudin.py` di folder
> ini. Buatkan dokumen perjalanan dinas: SPD ke Bandung selama 3 hari.
> Ikuti alur 6 langkah skill: upload Surat Tugas yang saya lampirkan,
> tampilkan ringkasan ekstraksi, lengkapi yang kosong lewat dialog
> dengan saya, tampilkan RINGKASAN FINAL dan MINTA approval saya dulu
> — jangan panggil approve sebelum saya bilang setuju. API key sudah
> ada di environment (`KEUDIN_API_KEY`); jangan pernah tampilkan
> nilainya.

Uji live terhadap demo (upload ST asli, approve, unduh arsip) adalah
tugas pekerja berikutnya, bukan bagian dari wrapper ini. Uji wrapper
ini sejauh ini hanya offline (mock) — lihat `test_keudin.py`.
