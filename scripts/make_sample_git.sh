#!/bin/sh
# Membuat riwayat Git deterministik untuk examples/sample-shop (dipakai tes end-to-end).
# Pemakaian: make_sample_git.sh <folder-project>
set -e
cd "$1"
rm -rf .git CHANGELOG.md src/payment.py
# Fixture palsu untuk menguji penyamaran secret dan filter (sengaja tidak disimpan di repo).
printf 'DB_PASSWORD=SuperSecretEnvValue123\nAPI_TOKEN=abcd1234efgh5678ijkl\n' > .env
printf -- '-----BEGIN RSA PRIVATE KEY-----\nMIIFAKEFAKEFAKE\n-----END RSA PRIVATE KEY-----\n' > deploy.pem
head -c 2000 /dev/urandom > logo.bin
mkdir -p node_modules/x dist && echo "module.exports=1" > node_modules/x/i.js && echo built > dist/out.js
git init -q -b main
git config user.email dev@example.com && git config user.name "Dev Contoh"
git add -A
GIT_AUTHOR_DATE="2025-01-10T10:00:00" GIT_COMMITTER_DATE="2025-01-10T10:00:00" git commit -q -m "feat: struktur awal toko dan modul diskon"
echo "# catatan rilis" > CHANGELOG.md && git add CHANGELOG.md
GIT_AUTHOR_DATE="2025-01-12T10:00:00" GIT_COMMITTER_DATE="2025-01-12T10:00:00" git commit -q -m "docs: tambah changelog"
git checkout -q -b feature/payment
echo "# TODO placeholder payment" > src/payment.py && git add src/payment.py
GIT_AUTHOR_DATE="2025-01-15T10:00:00" GIT_COMMITTER_DATE="2025-01-15T10:00:00" git commit -q -m "feat: kerangka integrasi pembayaran (WIP)"
git checkout -q main
