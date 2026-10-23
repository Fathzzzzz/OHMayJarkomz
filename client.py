"""Client terminal untuk server chat."""
import json
import socket
import sys
import threading
import time

# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------
DEFAULT_HOST = "127.0.0.1"   # ganti jika server berjalan di komputer lain
DEFAULT_PORT = 6767
ENCODING = "utf-8"
MAX_NAME_LEN = 20
MAX_TEXT_LEN = 4096
PROMPT = "> "

# stop_event dipakai bersama oleh kedua thread sebagai sinyal "berhenti".
# Begitu di-set, loop input maupun loop penerima akan berhenti.
stop_event = threading.Event()


# ---------------------------------------------------------------------------
# Utilitas tampilan
# ---------------------------------------------------------------------------
def local_time():
    """Timestamp lokal HH:MM:SS."""
    return time.strftime("%H:%M:%S")


def print_line(text):
    """
    Cetak satu baris pesan tanpa merusak baris input yang sedang diketik.

    '\r' mengembalikan kursor ke awal baris, lalu baris pesan dicetak dan
    prompt '> ' ditulis ulang.
    """
    sys.stdout.write("\r" + text + "\n")
    sys.stdout.write(PROMPT)
    sys.stdout.flush()



def print_help():
    print_line("[i] Perintah tersedia:")
    print_line("    /users              - lihat daftar pengguna online")
    print_line("    /pm <username> <pesan> - kirim pesan pribadi")
    print_line("    /help               - tampilkan bantuan ini")
    print_line("    /quit               - keluar dari chat")


# ---------------------------------------------------------------------------
# Pengiriman pesan
# ---------------------------------------------------------------------------
def send_message(sock, payload):
    """Kirim satu objek Python sebagai JSON + newline ke server."""
    raw = json.dumps(payload, ensure_ascii=False) + "\n"
    try:
        sock.sendall(raw.encode(ENCODING))
        return True
    except OSError as error:
        print_line(f"[!] Gagal mengirim data ke server: {error}")
        stop_event.set()
        return False


# ---------------------------------------------------------------------------
# Thread penerima
# ---------------------------------------------------------------------------
def display(data, username):
    """Tampilkan satu balasan server tanpa mengubah bentuk pesannya."""
    msg_type = data.get("type")
    stamp = data.get("time") or local_time()
    text = data.get("text", "")

    if msg_type == "chat":
        print_line(f"[{stamp}] {data.get('from')}: {text}")
    elif msg_type == "pm":
        print_line(f"[{stamp}] [PM dari {data.get('from')}] {text}")
    elif msg_type == "pm_sent":
        print_line(f"[{stamp}] [PM -> {data.get('to')}] {text}")
    elif msg_type in ("info", "error", "join_ok"):
        prefix = "[SERVER]" if msg_type != "error" else "ERROR"
        print_line(f"[{stamp}] {prefix} {text}")
    else:
        print_line(f"[{stamp}] [SERVER] (pesan tak dikenal) {data}")


def receive_messages(sock, username):
    """Thread kedua: baca terus pesan dari server sampai koneksi berakhir."""
    reader = sock.makefile("r", encoding=ENCODING, newline="\n")

    try:
        while not stop_event.is_set():
            line = reader.readline()
            if not line:
                # Server menutup koneksi.
                break
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                print_line("[!] Menerima data tidak valid dari server.")
                continue
            if isinstance(data, dict):
                display(data, username)
    except (ConnectionError, OSError) as error:
        if not stop_event.is_set():
            print_line(f"[!] Koneksi error: {error}")
    finally:
        if not stop_event.is_set():
            print_line("[!] Koneksi ke server terputus.")
            print_line("[i] Tekan Enter untuk menutup aplikasi.")
        stop_event.set()


# ---------------------------------------------------------------------------
# Argumen CLI dan username
# ---------------------------------------------------------------------------
def parse_args(argv):
    """Ambil host dan port dari argumen CLI (opsional)."""
    host, port = DEFAULT_HOST, DEFAULT_PORT
    args = argv[1:]
    if args and args[0] in ("-h", "--help"):
        print("Penggunaan: python3 client.py [host] [port]")
        sys.exit(0)
    if len(args) >= 1:
        host = args[0]
    if len(args) >= 2:
        try:
            port = int(args[1])
        except ValueError:
            print(f"[!] Port '{args[1]}' bukan angka. Memakai port default {DEFAULT_PORT}.")
            port = DEFAULT_PORT
    return host, port


def ask_username():
    """Minta username sampai mendapat input yang tidak kosong."""
    while True:
        try:
            username = input("Masukkan username: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[i] Dibatalkan.")
            sys.exit(0)
        if (username and len(username) <= MAX_NAME_LEN
                and not username.startswith("/")
                and not any(char.isspace() for char in username)):
            return username
        print("[!] Username harus 1-20 karakter, tanpa spasi, dan tidak diawali '/'.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    host, port = parse_args(sys.argv)
    username = ask_username()

    # 1. Buat socket TCP dan hubungkan ke server.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
    except OSError as error:
        print(f"[!] Tidak dapat terhubung ke {host}:{port} -> {error}")
        print("[i] Pastikan server.py sudah dijalankan dan host/port benar.")
        sock.close()
        sys.exit(1)

    print(f"[i] Terhubung ke server {host}:{port} sebagai '{username}'.")
    print("[i] Ketik /help untuk daftar perintah, /quit untuk keluar.")

    # 2. Kirim join dengan nama sebagai pesan pertama.
    if not send_message(sock, {"type": "join", "name": username}):
        sock.close()
        sys.exit(1)

    # 3. Jalankan thread penerima pesan.
    receiver = threading.Thread(
        target=receive_messages,
        args=(sock, username),
        daemon=True,
        name="receiver",
    )
    receiver.start()

    # 4. Loop utama: baca input user dan kirim ke server.
    try:
        while not stop_event.is_set():
            try:
                line = input(PROMPT).strip()
            except EOFError:
                # stdin habis (mis. input di-pipe) -> anggap keluar.
                send_message(sock, {"type": "quit"})
                break
            except KeyboardInterrupt:
                print()
                send_message(sock, {"type": "quit"})
                break

            if not line:
                continue

            # --- Perintah lokal -------------------------------------------
            if line in ("/quit", "/exit"):
                send_message(sock, {"type": "quit"})
                print("[i] Keluar dari chat.")
                break

            if line == "/help":
                print_help()
                continue

            if line == "/users":
                send_message(sock, {"type": "users"})
                continue

            if line.startswith("/pm"):
                # /pm <username> <pesan>  -> pecah maksimal 3 bagian
                parts = line.split(" ", 2)
                if len(parts) < 3 or not parts[1].strip() or not parts[2].strip():
                    print_line("[!] Format: /pm <nama> <pesan>")
                    continue
                if len(parts[2].strip()) > MAX_TEXT_LEN:
                    print_line(f"[!] Pesan terlalu panjang (maks {MAX_TEXT_LEN} karakter).")
                    continue
                send_message(sock, {
                    "type": "pm",
                    "to": parts[1].strip(),
                    "text": parts[2].strip(),
                })
                continue

            if line.startswith("/"):
                print_line("[!] Perintah tidak dikenal. Ketik /help.")
                continue

            # Batasi panjang sebelum mengirim ke server.
            if len(line) > MAX_TEXT_LEN:
                print_line(f"[!] Pesan terlalu panjang (maks {MAX_TEXT_LEN} karakter).")
                continue

            send_message(sock, {
                "type": "all",
                "text": line,
            })

    finally:
        # 5. Bersihkan: hentikan thread penerima dan tutup socket.
        stop_event.set()
        try:
            sock.shutdown(socket.SHUT_RDWR)   # bangunkan readline() yang blocking
        except OSError:
            pass
        sock.close()
        print("[i] Koneksi ditutup. Sampai jumpa.")


if __name__ == "__main__":
    main()
