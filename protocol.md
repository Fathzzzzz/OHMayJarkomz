# Protokol chat


## Gambaran umum

- Transport: TCP (`SOCK_STREAM`)
- Encoding: UTF-8
- Framing: satu objek JSON per baris
- Delimiter: newline (`\n`)
- Port default: `6767`

TCP tidak menyimpan batas pesan aplikasi. Satu `sendall()` dapat terbagi menjadi beberapa penerimaan, dan beberapa pesan dapat tiba sekaligus. Karena itu penerima membaca stream dengan `readline()` lalu memproses setiap baris JSON secara terpisah.

Contoh pengiriman:

```python
raw = json.dumps(payload, ensure_ascii=False) + "\n"
sock.sendall(raw.encode("utf-8"))
```

Newline di dalam teks pesan akan di-escape oleh `json.dumps`, sehingga tetap berbeda dari newline delimiter.

## Jenis pesan client ke server

| `type` | Field utama | Fungsi |
|---|---|---|
| `join` | `name` | Pesan pertama untuk mendaftarkan nama |
| `all` | `text` | Pesan publik ke semua client |
| `pm` | `to`, `text` | Pesan pribadi |
| `users` | tidak ada | Meminta daftar user online |
| `quit` | tidak ada | Keluar dari chat |

### Join

```json
{"type": "join", "name": "Budi"}
```

Server menolak nama kosong, nama lebih dari 20 karakter, nama yang mengandung whitespace, nama yang diawali `/`, dan nama yang sedang dipakai.

`join` harus menjadi pesan pertama. Setelah itu server menyimpan koneksi pada dictionary `clients`.

### Pesan publik

```json
{"type": "all", "text": "Halo semuanya"}
```

Server mengambil nama pengirim dari koneksi yang sudah terdaftar. Client tidak dapat mengubah nama pengirim dengan menambahkan field lain.

Server mengirim hasilnya kepada semua client:

```json
{
  "type": "chat",
  "from": "Budi",
  "text": "Halo semuanya",
  "time": "14:05:12"
}
```

### Pesan pribadi

```json
{"type": "pm", "to": "Ani", "text": "Hai Ani"}
```

Server mengirim pesan kepada Ani:

```json
{
  "type": "pm",
  "from": "Budi",
  "to": "Ani",
  "text": "Hai Ani",
  "time": "14:05:20"
}
```

Pengirim menerima konfirmasi terpisah:

```json
{
  "type": "pm_sent",
  "to": "Ani",
  "text": "Hai Ani",
  "time": "14:05:20"
}
```

Jika tujuan tidak online, server mengirim `error` kepada pengirim dan tidak meneruskan pesan.

### Daftar user

Request:

```json
{"type": "users"}
```

Response:

```json
{
  "type": "info",
  "text": "User online (2): Ani, Budi",
  "time": "14:06:00"
}
```

### Keluar

```json
{"type": "quit"}
```

Server menghapus koneksi dari daftar, mengumumkan user yang keluar, lalu menutup socket. Jika koneksi putus tanpa `quit`, blok pembersihan server melakukan hal yang sama.

## Jenis pesan server ke client

| `type` | Field | Keterangan |
|---|---|---|
| `join_ok` | `text`, `time` | Join diterima dan berisi sambutan |
| `chat` | `from`, `text`, `time` | Pesan publik |
| `pm` | `from`, `to`, `text`, `time` | Pesan pribadi untuk penerima |
| `pm_sent` | `to`, `text`, `time` | Konfirmasi kepada pengirim PM |
| `info` | `text`, `time` | Informasi server, join, leave, atau daftar user |
| `error` | `text`, `time` | Kesalahan request atau jaringan |

Contoh `info`:

```json
{"type": "info", "text": "Ani bergabung ke chat", "time": "14:07:01"}
{"type": "info", "text": "Ani keluar dari chat", "time": "14:08:10"}
```

Contoh `error`:

```json
{"type": "error", "text": "User 'Citra' tidak ditemukan atau sedang offline.", "time": "14:08:30"}
```

Jika server dihentikan dengan `Ctrl+C`, client yang masih terhubung menerima:

```json
{"type": "info", "text": "Server dimatikan.", "time": "14:09:00"}
```

## Urutan join

```text
Client                         Server
  |                              |
  | --- koneksi TCP ----------> |
  | --- join {name} ----------> |
  |                              | validasi nama
  | <--- join_ok -------------- |
  | <--- info daftar user ----- |
  |                              | client lain menerima info join
```

Server mendaftarkan client sebelum mengirim daftar user. Akses dictionary dilakukan di dalam `clients_lock`.

## Urutan pesan publik

```text
Budi                         Server                         Ani
  | --- all {text} ----------> |
  |                            | validasi dan catat log
  | <--- chat ---------------- |
  |                            | --- chat ----------------> |
```

Server mengambil snapshot target di dalam lock, lalu melakukan pengiriman di luar lock. Satu client yang lambat tidak menahan akses client lain. Setiap koneksi memiliki `send_lock`, sehingga dua thread tidak menyisipkan JSON pada stream yang sama.

## Urutan PM

```text
Budi                         Server                         Ani
  | --- pm {to, text} -------> |
  |                            | cari Ani
  | <--- pm_sent ------------- |
  |                            | --- pm -----------------> |
```

Field `from` dibuat server berdasarkan nama koneksi Budi. Nilai `from` dari request client tidak digunakan.

## Penanganan error

1. Baris yang bukan JSON valid dibalas dengan `error`; koneksi tetap dipertahankan.
2. JSON yang valid tetapi bukan object dibalas dengan `error`.
3. Pesan publik atau PM yang kosong ditolak.
4. Pesan lebih dari 4096 karakter ditolak.
5. Koneksi putus memicu pembersihan pada `finally` agar server tetap hidup.
6. Socket ditutup setelah reader dan koneksi tidak lagi digunakan.
