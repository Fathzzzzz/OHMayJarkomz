# Chat TCP di terminal

Proyek ini berisi chat sederhana dengan model client-server. Server menerima beberapa client sekaligus. Setiap client dilayani oleh thread sendiri, jadi percakapan tetap berjalan ketika client lain bergabung atau terputus.

## Berkas

- `server.py`: socket TCP dan pengelola semua koneksi.
- `client.py`: program terminal untuk pengguna.
- `protocol.md`: format JSON yang dipakai kedua program.

## Yang dipakai

- Python 3
- TCP melalui `socket.SOCK_STREAM`
- Thread bawaan Python
- Modul bawaan: `socket`, `threading`, `json`, `sys`, `time`, dan `errno`

Tidak ada Flask, FastAPI, WebSocket, atau package tambahan.

## Menjalankan server

Dari folder yang berisi `server.py`:

```bash
python3 server.py
```

Konfigurasi default di bagian atas file:

```python
PORT = 6767
```

`0.0.0.0` membuat server menerima koneksi pada semua interface jaringan. Port `6767` harus sama dengan port yang dipakai client.

## Menjalankan client

Client boleh dijalankan dari folder lain. Yang penting alamat server dan portnya benar.

Jika server dan client berjalan pada komputer yang sama:

```bash
python3 /path/ke/client.py
```

Jika server berada di komputer lain:

```bash
python3 /path/ke/client.py 192.168.1.10 6767
```

Format argumen:

```text
python3 client.py [host] [port]
```

Nilai default pada `client.py` adalah:

```python
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6767
```

Saat client mulai, masukkan nama 1 sampai 20 karakter. Nama tidak boleh mengandung spasi dan tidak boleh diawali `/`.

## Perintah

| Perintah | Fungsi |
|---|---|
| Teks biasa | Mengirim pesan ke semua pengguna yang sedang online |
| `/users` | Menampilkan daftar pengguna online |
| `/pm <nama> <pesan>` | Mengirim pesan pribadi |
| `/help` | Menampilkan bantuan |
| `/quit` atau `/exit` | Keluar dengan rapi |

Contoh:

```text
> Halo, apakah laporan sudah selesai?
> /users
> /pm Ani Tolong cek bagian kesimpulan.
> /quit
```

## Menjalankan dari folder berbeda

Lokasi file tidak menentukan koneksi socket. Server dan client berkomunikasi melalui alamat IP dan port.

Misalnya:

```text
Folder A: /Users/mymac/Projects/chat-server/server.py
Folder B: /Users/mymac/Downloads/chat-client/client.py
```

Jalankan server dari Folder A. Jalankan client dari Folder B dengan host dan port yang sama. Jika server ada di komputer yang sama, gunakan `127.0.0.1`. Jika server ada di komputer lain, gunakan IP komputer server, bukan `127.0.0.1`.

## Pengujian yang disarankan

1. Jalankan server.
2. Buka dua terminal client.
3. Masuk sebagai `Budi` dan `Ani`.
4. Pastikan Budi melihat Ani bergabung.
5. Kirim teks biasa dari Budi dan pastikan Ani menerimanya.
6. Jalankan `/users`.
7. Jalankan `/pm Ani pesan percobaan` dari Budi.
8. Jalankan `/quit` pada salah satu client dan pastikan client lain tetap hidup.
9. Tutup paksa satu client, lalu kirim pesan dari client yang tersisa. Server seharusnya tetap berjalan.

## Jika koneksi gagal

- Pastikan server sudah dijalankan lebih dulu.
- Pastikan port client sama dengan `PORT` pada server.
- Untuk komputer berbeda, pastikan memakai IP komputer server dan firewall mengizinkan TCP pada port `6767`.
- `127.0.0.1` hanya menunjuk ke komputer tempat perintah itu dijalankan.
- Cek port di macOS/Linux:

```bash
lsof -nP -iTCP:6767 -sTCP:LISTEN
```

Jika port sedang dipakai, ubah `PORT` dan `DEFAULT_PORT` ke angka yang sama, misalnya `6789`.

## Catatan implementasi

Server menyimpan koneksi aktif dalam dictionary yang dilindungi `threading.Lock`. Pesan dikirim sebagai JSON yang diakhiri newline. Karena TCP adalah stream, program membaca pesan per baris, bukan menganggap satu `recv()` sebagai satu pesan.

Identitas pengirim ditentukan server dari sesi join. Field nama dari client tidak dipakai saat server meneruskan pesan. Ini mencegah client mengaku sebagai pengguna lain.
