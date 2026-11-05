# Project Copilot

AI agent developer yang memahami isi folder project Anda (kode, dokumen, konfigurasi, skema DB, API spec, test, riwayat Git)
dan menjawab pertanyaan tim BA, QA, SA, developer, PM, dan DevOps lewat **web chat** dan **bot Telegram**.
Setiap jawaban menyertakan sumber (`path:baris` atau hash commit) yang diverifikasi terhadap index.

## Arsitektur singkat

| Service | Fungsi |
|---|---|
| `api` | FastAPI: web chat, login, agent, rate limit, audit. Terbuka hanya di `127.0.0.1`. |
| `worker` | Memindai folder project tiap `SCAN_INTERVAL_SECONDS`, meng-index hanya file yang berubah, sinkron Git dan task. |
| `telegram` | Bot Telegram (long polling). Whitelist diputuskan oleh API. Idle jika token kosong. |
| `db` | Postgres + pgvector: keyword (tsvector), semantic (vector), user, riwayat, audit. |

Alasan teknologi: satu Postgres menangani pencarian hybrid, metadata, dan riwayat sehingga hanya ada satu store untuk dirawat.
Embedding multibahasa berjalan lokal (fastembed), jadi kode tidak dikirim ke layanan embedding. Perubahan file dideteksi dengan
polling karena inotify tidak andal pada mount Docker Desktop.

## Instalasi

Prasyarat: Docker Desktop (Windows/macOS/Linux).

```bash
cp .env.example .env        # lalu isi nilai di bawah
docker compose up -d --build
```

Isi minimal `.env`:

| Variabel | Keterangan |
|---|---|
| `PROJECTS_PATH` | Folder yang diindeks (di-mount **read-only**). macOS/Linux: `/Users/nama/Projects`; Windows: `C:/Users/nama/Projects`. Default `./examples`. |
| `ADMIN_PASSWORD` | Password admin web (min. 10 karakter). |
| `POSTGRES_PASSWORD`, `INTERNAL_API_TOKEN` | String acak (mis. `openssl rand -hex 24`). |
| `ANTHROPIC_API_KEY` | Untuk `LLM_PROVIDER=anthropic`. |

Buka http://localhost:8080 dan login sebagai `ADMIN_USERNAME` / `ADMIN_PASSWORD`. Indexing pertama berjalan otomatis di `worker`
(lihat `docker compose logs -f worker`); indexing folder besar di CPU bisa memakan waktu beberapa menit.

### Ganti penyedia model
- `LLM_PROVIDER=anthropic` (default; `ANTHROPIC_MODEL` bisa diganti)
- `LLM_PROVIDER=openai` + `OPENAI_BASE_URL`/`OPENAI_API_KEY`/`OPENAI_MODEL` (OpenAI-compatible, termasuk Ollama: `http://host.docker.internal:11434/v1`)
- `LLM_PROVIDER=offline`: tanpa model, hanya menampilkan bukti hasil pencarian (untuk tes/darurat).

### Telegram
1. Buat bot lewat @BotFather, isi `TELEGRAM_BOT_TOKEN`.
2. Kirim `/start` ke bot untuk melihat ID numerik Anda, lalu isi `TELEGRAM_ALLOWED_IDS=123,456` (atau tambah lewat API admin di bawah).
3. `docker compose up -d`. Perintah: `/role <auto|ba|qa|sa|developer|pm|devops|general>`.

User yang tidak ada di whitelist ditolak dan dicatat di audit log.

## Cara pakai
Tanyakan hal seperti:
- BA: "Apa aturan bisnis diskon? Apakah sesuai requirement?"
- QA: "Buat test case dan edge case untuk pembatalan pesanan."
- SA: "Gambarkan alur pemesanan dengan diagram Mermaid."
- Developer: "Di mana `cancel_order` dipanggil? Kenapa error ini muncul?"
- PM: "Bagaimana progres dan risiko minggu ini?"
- DevOps: "Env var apa saja yang dipakai service ini?"

Peran terdeteksi otomatis dari pertanyaan; pilih manual lewat dropdown "Peran". Jawaban memisahkan **Fakta** (dengan sitasi),
**Inferensi**, dan **Tidak ditemukan**. Sitasi yang tidak ada di index ditandai `[sitasi tidak valid]` dan diberi peringatan.

Status task berbasis bukti: `selesai` hanya jika ada commit/riwayat yang membuktikan; checklist `[x]` di dokumen tanpa bukti kode
tetap `tidak diketahui`; branch yang punya commit belum ter-merge = `sedang dikerjakan`.

### Peran pengguna
`admin` (semua + audit + kelola user), `member` (tanya, baca file, git show), `viewer` (tanya dengan pencarian saja, rate limit lebih rendah).
Tambah user (admin, via sesi login yang sama di browser/curl):
```bash
curl -b cookie.txt -H 'content-type: application/json' -XPOST localhost:8080/api/admin/users \
  -d '{"username":"qa1","password":"password-panjang-1","role":"member"}'
# Telegram: -d '{"username":"tg_ani","role":"member","telegram_id":123456789}'
```
Audit log: `GET /api/admin/audit`. Reindex paksa: `POST /api/admin/reindex`.

## Menambah skill
Buat satu file di `copilot/skills/`, mis. `security.py`, lalu `docker compose up -d --build`. Skill ditemukan otomatis:
```python
from . import Skill
SKILL = Skill(
    name="security", title="Security Reviewer", description="Tinjauan keamanan.",
    keywords={"keamanan": 4, "vulnerability": 4, "owasp": 4},   # kata kunci -> bobot untuk deteksi otomatis
    preferred_kinds=["code", "config"],
    prompt="Peran: Security Reviewer. ...",                      # tambahan instruksi di atas aturan dasar
)
```
Aturan dasar (sitasi, fakta vs inferensi, anti-mengarang) ada di `copilot/agent.py` dan berlaku untuk semua skill.

## Keamanan
- Folder project di-mount `:ro`; container berjalan non-root, root filesystem read-only, `cap_drop: ALL`. Agent hanya punya tool baca.
- Git hanya memakai perintah baca (`log`, `show`, `for-each-ref`, ...) dengan `--no-ext-diff --no-textconv` dan `core.fsmonitor=false`,
  sehingga konfigurasi `.git/config` project tidak dieksekusi. Kode project tidak pernah dijalankan.
- Isi file selalu dibungkus `<untrusted_data>` dan model diberi tahu bahwa instruksi di dalamnya diabaikan.
- Tool hanya bisa membaca file yang terindeks (patuh `.gitignore`), tanpa path traversal/symlink keluar root.
- File seperti `.env`, `*.pem`, `id_rsa*`, `*.tfstate` tidak diindeks. Pola secret (token, key, password, URL berkredensial,
  private key) disamarkan pada index, hasil tool, pertanyaan, riwayat, audit, dan jawaban, dengan jumlah baris tetap.
- Login PBKDF2, sesi di DB, cookie `HttpOnly; SameSite=Strict`, throttle login, rate limit per user, audit log.
- Web hanya di `127.0.0.1:${WEB_PORT}`. Jangan mengubahnya ke `0.0.0.0` tanpa reverse proxy HTTPS (lalu set `SECURE_COOKIES=true`).

## Tes
```bash
docker compose up -d db
docker compose run --rm api python -m pytest -q
```
Mencakup indexing inkremental, pencarian, sitasi, deteksi/penyamaran secret, pembatasan akses, task berbasis bukti,
deteksi peran, dan satu pertanyaan per peran lewat API. Project contoh: `examples/sample-shop`. Riwayat Git-nya dibuat oleh
`sh scripts/make_sample_git.sh examples/sample-shop` (jalankan sekali sebelum memakai `PROJECTS_PATH=./examples`).

## Batasan
- Model AI dengan tool-use diuji lewat provider offline; kualitas jawaban nyata bergantung pada model yang dipilih.
- Rate limit disimpan di memori satu proses `api` (cukup untuk satu instance).
- Penyamaran secret berbasis pola; secret berformat tak lazim bisa lolos. File `.env*` dan kunci tidak pernah dibaca sama sekali.
- Jira/Confluence belum didukung (sumber task: TODO/FIXME, checklist dokumen, branch, commit).
- Hanya file teks ≤ `MAX_FILE_BYTES`; file biner (PDF, Office, gambar) dilewati.

## Troubleshooting
| Gejala | Solusi |
|---|---|
| `isi POSTGRES_PASSWORD di .env` | Lengkapi `.env` dari `.env.example`. |
| API tidak sehat, log: `ADMIN_PASSWORD belum diisi` | Isi `ADMIN_PASSWORD` (≥10 karakter). |
| Jawaban: `ANTHROPIC_API_KEY belum diisi` (HTTP 503) | Isi key atau ganti `LLM_PROVIDER`. |
| Project tidak terindeks / kosong | Cek `PROJECTS_PATH`; di Docker Desktop folder harus ada di Settings → Resources → File sharing. |
| Repo tanpa riwayat Git | Pastikan ada `.git` di folder repo; worktree dengan `.git` file yang menunjuk keluar mount tidak terbaca. |
| Indexing lama | Normal untuk folder besar pertama kali; selanjutnya hanya file berubah. Pantau `docker compose logs -f worker`. |
| Bot Telegram "Akses ditolak" | Tambahkan ID numerik ke `TELEGRAM_ALLOWED_IDS` atau lewat API admin. |
| Port 8080 dipakai | Ubah `WEB_PORT`. |
| Data hilang? | Data ada di volume `project-copilot_pgdata`; `docker compose down` aman, `down -v` menghapusnya. |
