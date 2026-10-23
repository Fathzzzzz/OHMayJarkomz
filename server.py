"""Server chat TCP untuk beberapa client."""
import json
import socket
import sys
import threading
import time
import errno

# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------
HOST = "0.0.0.0"
PORT = 6767
ENCODING = "utf-8"
MAX_NAME_LEN = 20
MAX_TEXT_LEN = 4096

# ---------------------------------------------------------------------------
# State bersama
# ---------------------------------------------------------------------------
clients = {}                 # name -> ClientConnection
clients_lock = threading.Lock()
log_lock = threading.Lock()


def now():
    return time.strftime("%H:%M:%S")


def log(text, address=None):
    line = f"[{now()}] {text}" if address is None else f"[{now()}] [{address[0]}:{address[1]}] {text}"
    with log_lock:
        print(line, flush=True)


def is_valid_name(name):
    """1-20 karakter, tanpa spasi, tidak diawali '/'."""
    if not name or len(name) > MAX_NAME_LEN:
        return False
    if name.startswith("/") or any(c.isspace() for c in name):
        return False
    return True


# ---------------------------------------------------------------------------
# Pembungkus koneksi
# ---------------------------------------------------------------------------
class ClientConnection:
    def __init__(self, sock, address):
        self.sock = sock
        self.address = address
        self.name = None
        self.reader = sock.makefile("r", encoding=ENCODING, newline="\n")
        self.send_lock = threading.Lock()

    def send(self, payload):
        raw = json.dumps(payload, ensure_ascii=False) + "\n"
        with self.send_lock:
            self.sock.sendall(raw.encode(ENCODING))

    def close(self):
        for closer in (self.reader.close, self.sock.close):
            try:
                closer()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Helper pengiriman
# ---------------------------------------------------------------------------
def send_safe(conn, payload):
    try:
        conn.send(payload)
        return True
    except OSError:
        return False


def send_info(conn, text):
    send_safe(conn, {"type": "info", "text": text, "time": now()})


def send_error(conn, text):
    send_safe(conn, {"type": "error", "text": text, "time": now()})


def broadcast(payload, exclude=None):
    with clients_lock:
        targets = [c for n, c in clients.items() if n != exclude]
    for conn in targets:
        if not send_safe(conn, payload):
            log(f"Gagal mengirim ke '{conn.name}'", conn.address)


def online_names():
    with clients_lock:
        return sorted(clients.keys())


def register(name, conn):
    with clients_lock:
        if name in clients:
            return False
        conn.name = name
        clients[name] = conn
    return True


def unregister(name):
    with clients_lock:
        clients.pop(name, None)


# ---------------------------------------------------------------------------
# Handler pesan
# ---------------------------------------------------------------------------
def handle_message(conn, msg):
    """Return True untuk lanjut, False untuk hentikan koneksi."""
    tipe = msg.get("type")

    # --- Chat ke semua -----------------------------------------------------
    if tipe == "all":
        text = str(msg.get("text", "")).strip()
        if not text:
            send_error(conn, "Pesan kosong tidak dikirim.")
            return True
        if len(text) > MAX_TEXT_LEN:
            send_error(conn, f"Pesan terlalu panjang (maks {MAX_TEXT_LEN}).")
            return True

        log(f"{conn.name}: {text}", conn.address)
        broadcast({
            "type": "chat",
            "from": conn.name,       # diisi server, bukan dari client
            "text": text,
            "time": now(),
        })
        return True

    # --- Private message ---------------------------------------------------
    if tipe == "pm":
        target = str(msg.get("to", "")).strip()
        text = str(msg.get("text", "")).strip()

        if not target or not text:
            send_error(conn, "Format salah. Gunakan: /pm <nama> <pesan>")
            return True
        if len(text) > MAX_TEXT_LEN:
            send_error(conn, f"Pesan terlalu panjang (maks {MAX_TEXT_LEN}).")
            return True

        with clients_lock:
            recipient = clients.get(target)

        if recipient is None:
            send_error(conn, f"User '{target}' tidak ditemukan atau sedang offline.")
            log(f"PM gagal ke '{target}' (offline)", conn.address)
            return True

        waktu = now()
        payload = {
            "type": "pm",
            "from": conn.name,
            "to": target,
            "text": text,
            "time": waktu,
        }
        delivered = send_safe(recipient, payload)

        if not delivered:
            send_error(conn, f"Gagal mengirim PM ke '{target}'.")
            return True

        # Konfirmasi ke pengirim (kecuali PM ke diri sendiri)
        if recipient is not conn:
            send_safe(conn, {
                "type": "pm_sent",
                "to": target,
                "text": text,
                "time": waktu,
            })

        log(f"PM {conn.name} -> {target}: {text}", conn.address)
        return True

    # --- Daftar user -------------------------------------------------------
    if tipe == "users":
        daftar = online_names()
        send_info(conn, f"User online ({len(daftar)}): {', '.join(daftar)}")
        return True

    # --- Quit --------------------------------------------------------------
    if tipe == "quit":
        log(f"{conn.name} meminta keluar (/quit)", conn.address)
        return False

    # --- Tipe tidak dikenal ------------------------------------------------
    send_error(conn, f"Tipe pesan tidak dikenal: {tipe!r}")
    return True


# ---------------------------------------------------------------------------
# Thread per client
# ---------------------------------------------------------------------------
def handle_client(sock, address):
    conn = ClientConnection(sock, address)
    log("Koneksi baru diterima", address)

    try:
        # === Handshake join ===============================================
        first = conn.reader.readline()
        if not first:
            log("Client menutup koneksi sebelum join", address)
            return

        try:
            data = json.loads(first)
        except json.JSONDecodeError:
            send_error(conn, "Format pesan tidak valid (bukan JSON).")
            log("Join ditolak: JSON tidak valid", address)
            return

        if not isinstance(data, dict) or data.get("type") != "join":
            send_error(conn, "Pesan pertama harus bertipe 'join'.")
            log("Join ditolak: bukan 'join'", address)
            return

        name = str(data.get("name", "")).strip()
        if not is_valid_name(name):
            send_error(conn, "Nama tidak valid (1-20 karakter, tanpa spasi, tidak diawali '/').")
            log(f"Join ditolak: nama tidak valid {name!r}", address)
            return

        if not register(name, conn):
            send_error(conn, f"Nama '{name}' sudah dipakai, coba nama lain.")
            log(f"Join ditolak: '{name}' sudah dipakai", address)
            return

        # Sukses → kirim join_ok (ini yang ditunggu client)
        send_safe(conn, {
            "type": "join_ok",
            "text": f"Selamat datang, {name}! Ketik /help untuk melihat perintah.",
            "time": now(),
        })
        log(f"'{name}' bergabung", address)

        # Umumkan ke yang lain + info daftar user baru ke semua
        broadcast({
            "type": "info",
            "text": f"{name} bergabung ke chat",
            "time": now(),
        }, exclude=name)

        daftar = online_names()
        broadcast({
            "type": "info",
            "text": f"User online ({len(daftar)}): {', '.join(daftar)}",
            "time": now(),
        })

        # === Loop pesan ===================================================
        while True:
            line = conn.reader.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                send_error(conn, "Pesan diabaikan: bukan JSON yang valid.")
                continue

            if not isinstance(msg, dict):
                send_error(conn, "Pesan diabaikan: JSON harus berupa objek.")
                continue

            if not handle_message(conn, msg):
                break

    except (ConnectionError, OSError) as e:
        log(f"Koneksi terputus tidak normal: {e}", address)
    except Exception as e:
        log(f"Error tak terduga: {e!r}", address)
    finally:
        if conn.name:
            unregister(conn.name)
            log(f"'{conn.name}' keluar", address)
            broadcast({
                "type": "info",
                "text": f"{conn.name} keluar dari chat",
                "time": now(),
            })
            daftar = online_names()
            broadcast({
                "type": "info",
                "text": f"User online ({len(daftar)}): {', '.join(daftar) or '-'}",
                "time": now(),
            })
        conn.close()
        log("Koneksi ditutup", address)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(50)
    except OSError as e:
        print(f"[FATAL] Gagal membuka {HOST}:{PORT} -> {e}", flush=True)
        if e.errno == errno.EADDRINUSE:
            print(f"[HINT] Port {PORT} sedang dipakai. Pilih port lain yang belum digunakan.",
                  flush=True)
        server_socket.close()
        sys.exit(1)

    log(f"Server chat berjalan di {HOST}:{PORT}")
    log("Menunggu client... (Ctrl+C untuk menghentikan)")

    try:
        while True:
            try:
                client_sock, address = server_socket.accept()
            except OSError as e:
                log(f"accept() gagal: {e}")
                break

            t = threading.Thread(
                target=handle_client,
                args=(client_sock, address),
                daemon=True,
                name=f"client-{address[0]}:{address[1]}",
            )
            t.start()
            log(f"Thread '{t.name}' dijalankan "
                f"(total aktif: {threading.active_count()})", address)

    except KeyboardInterrupt:
        log("Server dihentikan oleh admin (Ctrl+C).")
    finally:
        with clients_lock:
            remaining = list(clients.values())
        for conn in remaining:
            send_safe(conn, {"type": "info", "text": "Server dimatikan.", "time": now()})
            try:
                conn.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
        server_socket.close()
        log("Socket server ditutup. Sampai jumpa.")


if __name__ == "__main__":
    main()