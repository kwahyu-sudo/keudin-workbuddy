#!/usr/bin/env python3
"""Wrapper CLI pemanggil API KeUdin untuk WorkBuddy.

Satu file, HANYA standard library Python (urllib, argparse, json),
kompatibel Python 3.8+, portabel Windows/macOS/Linux. Tanpa pip install.

Satu perintah per langkah skill KeUdin (SKILL.md). Lihat CARA-PAKAI.md.

KEAMANAN (keras):
- API key HANYA dibaca dari environment variable KEUDIN_API_KEY.
- Key dikirim sebagai header X-API-Key pada SETIAP request /api/*.
- Key TIDAK PERNAH dicetak ke stdout/stderr/log, tidak di-hardcode,
  dan tidak ditulis ke file. Bila env kosong, tidak ada request yang dibuat.
- Base URL default https://hackeu.akalimitasi.my.id, bisa di-override
  lewat flag --base-url atau env KEUDIN_BASE_URL (flag menang atas env).

Exit code:
- 0 = sukses
- 1 = error API / koneksi / gerbang approval belum dilewati
- 2 = pemakaian salah (argumen, file lokal tidak ada, JSON tidak valid)
- 3 = gerbang approval: `approve` tanpa --confirm (sengaja berhenti)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime

DEFAULT_BASE_URL = "https://hackeu.akalimitasi.my.id"

# Cloudflare di depan server demo memblokir User-Agent default Python
# (urllib mengirim "Python-urllib/3.x" -> HTTP 403 Error 1010 "Access denied").
# Setiap request WAJIB mengirim UA yang tidak diblokir. Bisa di-override
# lewat env KEUDIN_USER_AGENT bila operator mengganti proteksi di depannya.
DEFAULT_USER_AGENT = "keudin-cli/1.0 (+workbuddy)"

# Field kegiatan yang dikenal server (PUT /api/trips/{id}, lihat app.py).
# Dipakai agar `--set kota_tujuan=Bandung` otomatis menjadi
# {"kegiatan": {"kota_tujuan": "Bandung"}} -- bentuk yang diterima server.
KEGIATAN_FIELDS = {
    "nomor_surat_tugas", "tanggal_surat_tugas", "dasar_hukum",
    "maksud_perjalanan", "kota_tujuan", "tanggal_berangkat",
    "tanggal_kembali", "pejabat_penandatangan",
}


def die(message, code=1):
    """Cetak pesan error singkat Bahasa Indonesia ke stderr, keluar."""
    print("Error: " + message, file=sys.stderr)
    return code


def get_api_key():
    """Ambil key dari env saja. Kembalikan None bila kosong/tidak ada."""
    key = os.environ.get("KEUDIN_API_KEY", "")
    if key is None:
        return None
    key = key.strip()
    return key or None


def get_base_url(cli_value):
    if cli_value:
        return cli_value.rstrip("/")
    env_value = os.environ.get("KEUDIN_BASE_URL", "").strip()
    if env_value:
        return env_value.rstrip("/")
    return DEFAULT_BASE_URL


def get_user_agent():
    """UA yang dikirim di setiap request (lihat DEFAULT_USER_AGENT)."""
    value = os.environ.get("KEUDIN_USER_AGENT", "").strip()
    return value or DEFAULT_USER_AGENT


def format_rupiah(total):
    """Format angka menjadi gaya Indonesia: 1500000 -> 1.500.000."""
    try:
        number = float(total)
    except (TypeError, ValueError):
        return "-"
    if number == int(number):
        text = str(int(number))
    else:
        text = "{:.2f}".format(number)
    if "." in text:
        whole, frac = text.split(".", 1)
    else:
        whole, frac = text, ""
    grouped = ""
    while len(whole) > 3:
        grouped = "." + whole[-3:] + grouped
        whole = whole[:-3]
    grouped = whole + grouped
    return grouped + ("," + frac if frac else "")


def parse_date(text):
    try:
        return datetime.strptime(str(text), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def count_days(berangkat, kembali):
    """Jumlah hari inklusif (berangkat s.d. kembali). None bila tak bisa."""
    start = parse_date(berangkat)
    end = parse_date(kembali)
    if start is None or end is None or end < start:
        return None
    return (end - start).days + 1


# ---------------------------------------------------------------- HTTP ----

class ApiError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def map_http_error(status, detail):
    """Petakan status HTTP ke pesan singkat gaya skill SKILL.md §5."""
    if status == 401:
        return ("Server menolak akses (API key tidak cocok). "
                "Proses dihentikan dulu. Periksa KEUDIN_API_KEY, lalu ulangi.")
    if status == 503:
        return ("Server KeUdin belum dikonfigurasi API key-nya, "
                "jadi belum bisa dipakai. Minta operator menyetel env "
                "di server, lalu mulai ulang alur.")
    if status == 422:
        return "File-nya tidak bisa dibaca sebagai dokumen yang valid."
    if status == 404:
        return ("Data dengan ID itu tidak ditemukan di server. "
                "Segarkan daftar (trips/archives), lalu pilih ulang.")
    if status == 413:
        return "File melebihi batas ukuran server (20 MB)."
    if status == 429:
        return "Terlalu banyak request. Tunggu sebentar, lalu ulangi."
    if status == 400:
        if isinstance(detail, dict) and detail.get("message"):
            extra = detail["message"]
            issues = detail.get("blocking_issues") or detail.get("skipped_pelaksana")
            if issues:
                extra += " | " + "; ".join(str(x) for x in issues)
            return "Permintaan ditolak server: " + extra
        if isinstance(detail, str) and detail:
            return "Permintaan ditolak server: " + detail
        return "Permintaan ditolak server."
    if isinstance(detail, str) and detail:
        return "Server mengembalikan HTTP {}: {}".format(status, detail[:200])
    return "Server mengembalikan HTTP {}.".format(status)


def request_json(base_url, api_key, method, path, body=None, timeout=180):
    """Request JSON. Kembalikan dict/list hasil parse. Raise ApiError."""
    url = base_url + path
    data = None
    headers = {"X-API-Key": api_key, "Accept": "application/json",
               "User-Agent": get_user_agent()}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif method in ("POST", "PUT"):
        data = b""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = None
        try:
            parsed = json.loads(exc.read().decode("utf-8", "replace"))
            detail = parsed.get("detail", parsed) if isinstance(parsed, dict) else parsed
        except Exception:
            detail = None
        raise ApiError(map_http_error(exc.code, detail))
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ApiError("Server KeUdin tidak bisa dihubungi saat ini. "
                       "Periksa base_url dan apakah server berjalan, "
                       "lalu coba sekali lagi.")
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise ApiError("Respons server bukan JSON yang valid.")


def build_multipart(fields):
    """Bangun body multipart/form-data manual (stdlib saja).

    fields: list of (field_name, filename_or_None, bytes_or_None).
    Untuk field file, filename wajib; untuk field teks, filename None.
    Kembalikan (body_bytes, content_type).
    """
    boundary = uuid.uuid4().hex
    parts = []
    for name, filename, content in fields:
        header = ['--' + boundary,
                  'Content-Disposition: form-data; name="{}"'.format(name)]
        if filename is not None:
            header[0] = header[0]
            header[1] += '; filename="{}"'.format(os.path.basename(filename))
            header.append("Content-Type: " + guess_content_type(filename))
        header.append("")
        parts.append("\r\n".join(header).encode("utf-8"))
        parts.append(content if content is not None else b"")
    parts.append(("--" + boundary + "--").encode("utf-8"))
    body = b"\r\n".join(parts) + b"\r\n"
    return body, "multipart/form-data; boundary=" + boundary


def guess_content_type(filename):
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".zip"):
        return "application/zip"
    return "application/octet-stream"


def request_multipart(base_url, api_key, path, fields, timeout=300):
    """Request multipart. Kembalikan dict/list hasil parse. Raise ApiError."""
    body, content_type = build_multipart(fields)
    req = urllib.request.Request(
        base_url + path, data=body, method="POST",
        headers={"X-API-Key": api_key, "Content-Type": content_type,
                 "Accept": "application/json",
                 "User-Agent": get_user_agent()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = None
        try:
            parsed = json.loads(exc.read().decode("utf-8", "replace"))
            detail = parsed.get("detail", parsed) if isinstance(parsed, dict) else parsed
        except Exception:
            detail = None
        raise ApiError(map_http_error(exc.code, detail))
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ApiError("Server KeUdin tidak bisa dihubungi saat ini. "
                       "Periksa base_url dan apakah server berjalan, "
                       "lalu coba sekali lagi.")
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise ApiError("Respons server bukan JSON yang valid.")


def read_file_bytes(path):
    if not os.path.isfile(path):
        raise ApiError("File tidak ditemukan: {}".format(path))
    with open(path, "rb") as handle:
        return handle.read()


def print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


# ------------------------------------------------------------- --set ------

def set_path(obj, dotted, value):
    """Set nilai pada dict/list mengikuti path bertitik.

    Contoh: kegiatan.kota_tujuan=Bandung,
    pelaksana.0.nama=Budi (angka = indeks list).
    """
    parts = dotted.split(".")
    current = obj
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if part.isdigit():
            index = int(part)
            if not isinstance(current, list):
                raise ApiError("--set '{}': indeks list di posisi bukan list.".format(dotted))
            while len(current) <= index:
                current.append({})
            if last:
                current[index] = value
            else:
                if not isinstance(current[index], (dict, list)):
                    current[index] = {}
                current = current[index]
        else:
            if not isinstance(current, dict):
                raise ApiError("--set '{}': path tidak cocok dengan struktur.".format(dotted))
            if last:
                current[part] = value
            else:
                nxt = parts[i + 1]
                if part not in current or not isinstance(current[part], (dict, list)):
                    current[part] = [] if nxt.isdigit() else {}
                current = current[part]


def parse_set_value(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def apply_set_args(payload, set_args):
    for item in set_args or []:
        if "=" not in item:
            raise ApiError("--set harus berbentuk kunci=nilai, didapat: '{}'.".format(item))
        key, _, raw = item.partition("=")
        key = key.strip()
        if not key:
            raise ApiError("--set kosong tidak valid.")
        if "." not in key:
            if key in KEGIATAN_FIELDS:
                key = "kegiatan." + key
            else:
                raise ApiError(
                    "--set '{}': pakai bentuk bertitik, mis. "
                    "kegiatan.kota_tujuan=..., pelaksana.0.nama=..., "
                    "atau pengeluaran.0.nominal=...".format(key))
        set_path(payload, key, parse_set_value(raw))
    return payload


def deep_merge(base, override):
    for key, value in override.items():
        if (key in base and isinstance(base[key], dict)
                and isinstance(value, dict)):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


# ------------------------------------------------------------ approve -----

def print_final_summary(trip):
    """Cetak ringkasan final format skill Langkah 5 dari GET trip.

    Bentuk aktual server: {"kegiatan": {...}, "pelaksana": [...],
    "pengeluaran": [...]} -- bukan field datar. Fallback ke field datar
    bila server suatu saat mengembalikannya.
    """
    kegiatan = trip.get("kegiatan") or {}
    if not isinstance(kegiatan, dict):
        kegiatan = {}
    pelaksana = trip.get("pelaksana") or []
    if not isinstance(pelaksana, list):
        pelaksana = []
    pengeluaran = trip.get("pengeluaran") or []
    if not isinstance(pengeluaran, list):
        pengeluaran = []

    def pick(container, *names):
        for name in names:
            if container.get(name) not in (None, ""):
                return container[name]
        return None

    def show(value):
        return str(value) if value not in (None, "") else "(kosong)"

    first = pelaksana[0] if pelaksana else {}
    total = 0
    for item in pengeluaran:
        try:
            total += float(item.get("nominal") or 0)
        except (TypeError, ValueError):
            pass
    berangkat = pick(kegiatan, "tanggal_berangkat")
    kembali = pick(kegiatan, "tanggal_kembali")
    days = count_days(berangkat, kembali)
    days_text = "{} hari".format(days) if days is not None else "? hari"

    lines = ["RINGKASAN FINAL \u2014 mohon periksa sebelum dokumen dibuat"]
    if pelaksana:
        for person in pelaksana:
            # Server memecah golongan dan ruang ("III" + "a"); dokumen resmi
            # menulisnya menyatu ("III/a"). Jangan kehilangan ruang di gerbang
            # approval -- approver harus melihat bentuk yang akan tercetak.
            golongan = pick(person, "golongan")
            ruang = pick(person, "ruang")
            gol_text = show(golongan)
            if golongan and ruang:
                gol_text = "{}/{}".format(golongan, ruang)
            lines.append("Pelaksana   : {} ({})".format(
                show(pick(person, "nama")), show(pick(person, "nip"))))
            lines.append("Pangkat/Gol : {} / {}".format(
                show(pick(person, "pangkat")), gol_text))
    else:
        lines.append("Pelaksana   : (kosong)")
        lines.append("Pangkat/Gol : (kosong) / (kosong)")
    lines.append("Tujuan      : {}".format(show(pick(kegiatan, "kota_tujuan"))))
    lines.append("Tanggal     : {} s.d. {} ({})".format(
        show(berangkat), show(kembali), days_text))
    lines.append("Surat Tugas : {}".format(show(pick(kegiatan, "nomor_surat_tugas"))))
    lines.append("Total biaya : Rp{} ({} item pengeluaran)".format(
        format_rupiah(total), len(pengeluaran)))
    lines.append("Dokumen yang akan dibuat: SPD lembar 1, rincian biaya, "
                 "rincian transportasi, daftar nominatif, RPAK")
    print("\n".join(lines))


def sanitize_download_filename(header_value, archive_id):
    """Ambil nama file dari Content-Disposition, atau default dari id."""
    if header_value:
        for part in header_value.split(";"):
            part = part.strip()
            if part.lower().startswith("filename="):
                name = part.split("=", 1)[1].strip().strip('"').strip("'")
                name = os.path.basename(name)
                if name and name not in (".", ".."):
                    return name
    return "arsip-{}.zip".format(archive_id)


# -------------------------------------------------------------- parser ----

def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    # default=SUPPRESS penting: subparser menyalin default-nya sendiri ke
    # namespace, sehingga tanpa SUPPRESS flag global yang ditulis SEBELUM
    # nama perintah akan ditimpa balik jadi None. Dengan SUPPRESS, nilai
    # hanya ditulis bila flag benar-benar diberikan -> --base-url/--timeout
    # berlaku di posisi mana pun.
    common.add_argument("--base-url", default=argparse.SUPPRESS,
                        help="Override base URL (atau env KEUDIN_BASE_URL). "
                        "Default: " + DEFAULT_BASE_URL)
    common.add_argument("--timeout", type=float, default=argparse.SUPPRESS,
                        help="Timeout request dalam detik (default: 180).")

    parser = argparse.ArgumentParser(
        prog="keudin.py",
        description="Wrapper CLI API KeUdin (satu perintah per langkah skill). "
        "API key hanya dari env KEUDIN_API_KEY, tidak pernah dicetak.",
        parents=[common])
    sub = parser.add_subparsers(dest="command", metavar="perintah")

    p = sub.add_parser("upload", parents=[common],
                       help="Upload Surat Tugas (+ bukti opsional) -> trip draft.")
    p.add_argument("surat_tugas", help="File PDF Surat Tugas/SPD.")
    p.add_argument("--bukti", action="append", default=[],
                   help="File kuitansi (boleh diulang untuk banyak file).")

    sub.add_parser("trips", parents=[common], help="Daftar semua trip.")

    p = sub.add_parser("trip", parents=[common], help="Detail satu trip.")
    p.add_argument("id", help="ID trip (kegiatan_id).")

    p = sub.add_parser("update", parents=[common],
                       help="Koreksi data trip (PUT). Body WAJIB bentuk "
                       "bersarang server: {kegiatan: {...}, pelaksana: "
                       "[{id, ...}], pengeluaran: [{id, ...}]}.")
    p.add_argument("id", help="ID trip.")
    p.add_argument("--json", default=None,
                   help="Body JSON bersarang, mis. "
                   "'{\"kegiatan\": {\"kota_tujuan\": \"Bandung\"}}'.")
    p.add_argument("--set", dest="set_args", action="append", default=[],
                   help="Kunci=nilai bertitik, mis. "
                   "kegiatan.kota_tujuan=Bandung atau "
                   "pelaksana.0.nama=Budi. Bisa diulang.")

    p = sub.add_parser("add-expense", parents=[common],
                       help="Tambah pengeluaran (POST). CATATAN: server saat "
                       "ini mengabaikan body dan membuat baris kosong "
                       "(jenis bukti_lain, nominal 0) -- lengkapi lewat "
                       "'update' dengan id pengeluaran yang dikembalikan.")
    p.add_argument("id", help="ID trip.")
    p.add_argument("--json", default=None,
                   help="Body JSON (diteruskan apa adanya; server saat ini "
                   "mengabaikannya -- lihat catatan di atas).")

    p = sub.add_parser("upload-bukti", parents=[common],
                       help="Upload satu kuitansi ke trip (ekstraksi otomatis).")
    p.add_argument("id", help="ID trip.")
    p.add_argument("file", help="File kuitansi (satu file per panggilan).")

    p = sub.add_parser("approve", parents=[common],
                       help="Gerbang approval. Tanpa --confirm: hanya tampilkan "
                       "ringkasan final lalu BERHENTI (exit 3). Dengan "
                       "--confirm: panggil POST approve.")
    p.add_argument("id", help="ID trip.")
    p.add_argument("--confirm", action="store_true",
                   help="Konfirmasi eksplisit: benar-benar panggil approve.")

    p = sub.add_parser("archives", parents=[common],
                       help="Daftar arsip dokumen hasil generate.")
    p.add_argument("--search", default=None, help="Cari nomor surat/nama.")
    p.add_argument("--month", default=None,
                   help="Filter bulan format MM-YYYY, atau 'all'.")
    p.add_argument("--page", type=int, default=None)
    p.add_argument("--per-page", type=int, default=None)

    p = sub.add_parser("download", parents=[common],
                       help="Unduh paket ZIP arsip (tulis biner apa adanya).")
    p.add_argument("archive_id", help="ID arsip (= ID trip/kegiatan).")
    p.add_argument("--out", default=None,
                   help="File tujuan. Default: nama dari server, atau "
                   "arsip-<id>.zip bila server tidak memberi nama.")

    sub.add_parser("stats", parents=[common],
                   help="Statistik agregat (perlu_review, selesai_bulan_ini).")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.command:
        print("Pakai: keudin.py <perintah> --help  "
              "(upload, trips, trip, update, add-expense, upload-bukti, "
              "approve, archives, download, stats)", file=sys.stderr)
        return 2

    api_key = get_api_key()
    if api_key is None:
        return die("KEUDIN_API_KEY belum diset di environment. "
                   "Set dulu variabel KEUDIN_API_KEY (lihat CARA-PAKAI.md), "
                   "lalu ulangi perintah.", code=2)

    base_url = get_base_url(getattr(args, "base_url", None))
    timeout = getattr(args, "timeout", None)
    if timeout is None:
        timeout = 180
    cmd = args.command

    try:
        if cmd == "upload":
            fields = [("surat_tugas", args.surat_tugas,
                       read_file_bytes(args.surat_tugas))]
            for bukti_path in args.bukti:
                fields.append(("bukti", bukti_path, read_file_bytes(bukti_path)))
            result = request_multipart(base_url, api_key, "/api/upload",
                                       fields, timeout=max(timeout, 300))
            print_json(result)

        elif cmd == "trips":
            print_json(request_json(base_url, api_key, "GET", "/api/trips",
                                    timeout=timeout))

        elif cmd == "trip":
            print_json(request_json(base_url, api_key, "GET",
                                    "/api/trips/{}".format(args.id),
                                    timeout=timeout))

        elif cmd == "update":
            payload = {}
            if args.json:
                try:
                    parsed = json.loads(args.json)
                except ValueError:
                    return die("--json bukan JSON yang valid.", code=2)
                if not isinstance(parsed, dict):
                    return die("--json harus berupa object JSON.", code=2)
                payload = parsed
            payload = apply_set_args(payload, args.set_args)
            result = request_json(base_url, api_key, "PUT",
                                  "/api/trips/{}".format(args.id),
                                  body=payload, timeout=timeout)
            print_json(result)

        elif cmd == "add-expense":
            body = None
            if args.json:
                try:
                    body = json.loads(args.json)
                except ValueError:
                    return die("--json bukan JSON yang valid.", code=2)
            result = request_json(base_url, api_key, "POST",
                                  "/api/trips/{}/expenses".format(args.id),
                                  body=body, timeout=timeout)
            print_json(result)

        elif cmd == "upload-bukti":
            fields = [("file", args.file, read_file_bytes(args.file))]
            result = request_multipart(
                base_url, api_key,
                "/api/trips/{}/upload-bukti".format(args.id),
                fields, timeout=max(timeout, 300))
            print_json(result)

        elif cmd == "approve":
            if not args.confirm:
                trip = request_json(base_url, api_key, "GET",
                                    "/api/trips/{}".format(args.id),
                                    timeout=timeout)
                print_final_summary(trip)
                print("Belum ada approval: endpoint approve TIDAK dipanggil. "
                      "Jalankan lagi dengan --confirm hanya setelah user "
                      "menyetujui ringkasan final di atas.",
                      file=sys.stderr)
                return 3
            result = request_json(base_url, api_key, "POST",
                                  "/api/trips/{}/approve".format(args.id),
                                  timeout=timeout)
            print_json(result)

        elif cmd == "archives":
            query = []
            if args.search:
                query.append("search=" + urllib.request.quote(args.search))
            if args.month:
                query.append("month=" + urllib.request.quote(args.month))
            if args.page is not None:
                query.append("page={}".format(args.page))
            if args.per_page is not None:
                query.append("per_page={}".format(args.per_page))
            path = "/api/archives" + ("?" + "&".join(query) if query else "")
            print_json(request_json(base_url, api_key, "GET", path,
                                    timeout=timeout))

        elif cmd == "download":
            url = base_url + "/api/archives/{}/download".format(args.archive_id)
            req = urllib.request.Request(
                url, method="GET", headers={"X-API-Key": api_key,
                                            "User-Agent": get_user_agent()})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read()
                    header = ""
                    try:
                        header = resp.headers.get("Content-Disposition", "")
                    except Exception:
                        header = ""
            except urllib.error.HTTPError as exc:
                detail = None
                try:
                    parsed = json.loads(exc.read().decode("utf-8", "replace"))
                    detail = parsed.get("detail", parsed) if isinstance(parsed, dict) else parsed
                except Exception:
                    detail = None
                raise ApiError(map_http_error(exc.code, detail))
            except (urllib.error.URLError, TimeoutError, OSError):
                raise ApiError("Server KeUdin tidak bisa dihubungi saat ini. "
                               "Periksa base_url dan apakah server berjalan, "
                               "lalu coba sekali lagi.")
            out_path = args.out or sanitize_download_filename(header, args.archive_id)
            with open(out_path, "wb") as handle:
                handle.write(raw)
            print_json({"archive_id": args.archive_id, "file": out_path,
                        "filename": os.path.basename(out_path),
                        "bytes": len(raw)})

        elif cmd == "stats":
            print_json(request_json(base_url, api_key, "GET", "/api/stats",
                                    timeout=timeout))

    except ApiError as exc:
        return die(exc.message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
