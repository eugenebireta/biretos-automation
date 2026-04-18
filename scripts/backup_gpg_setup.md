# GPG setup for backup encryption

Per critique 1+3: cloud-bound backups (B2) must be encrypted so even the storage provider cannot read them. For offsite-to-own-VPS, encryption adds ransomware defense.

## Threat model

- B2 Object Lock protects against DELETE. It does NOT protect against READ.
- Offsite to RU VPS: if RU VPS is compromised, attacker reads all backups.
- Encryption key MUST live outside both VPSes (owner's machine + paper copy).

## Setup (one-time, on owner's Windows machine)

```powershell
# 1. Generate keypair — 4096-bit RSA (compatible with all gpg versions)
gpg --batch --passphrase "REPLACE_WITH_STRONG_PASSPHRASE" --quick-generate-key "biretos-backup@local" rsa4096 default 5y

# 2. Export PUBLIC key (safe to place on VPSes for encryption)
gpg --armor --export biretos-backup@local > d:\BIRETOS\backups\pre_critique_2026_04_17\biretos_backup_pub.asc

# 3. Export PRIVATE key (KEEP OFFLINE, print on paper, store in password manager)
gpg --armor --export-secret-keys biretos-backup@local > d:\BIRETOS\biretos_backup_PRIVATE.asc
# Move d:\BIRETOS\biretos_backup_PRIVATE.asc to:
#   - Bitwarden or 1Password as secure note
#   - USB stick in desk drawer
#   - Printed QR code on paper in safe
# Then delete from disk after confirmed backups exist
```

## Installation on biretos.ae + dev.bireta.ru (public key only)

```bash
# Copy public key to VPS
scp biretos_backup_pub.asc root@216.9.227.124:/root/.gnupg/biretos_backup_pub.asc
scp biretos_backup_pub.asc root@77.233.222.214:/root/.gnupg/biretos_backup_pub.asc

# Import on each VPS
ssh root@216.9.227.124 "gpg --import /root/.gnupg/biretos_backup_pub.asc && gpg --list-keys biretos-backup@local"
ssh root@77.233.222.214 "gpg --import /root/.gnupg/biretos_backup_pub.asc && gpg --list-keys biretos-backup@local"

# Mark as trusted
ssh root@216.9.227.124 "echo '5' | gpg --command-fd 0 --edit-key biretos-backup@local trust save"
ssh root@77.233.222.214 "echo '5' | gpg --command-fd 0 --edit-key biretos-backup@local trust save"
```

## How to encrypt in backup.sh (patch, to be applied after keypair exists)

```bash
# After each gzip file is created, pipe through gpg:
gpg --batch --yes --recipient biretos-backup@local --trust-model always \
    --output "${FILE}.gpg" --encrypt "${FILE}"
rm "${FILE}"  # only encrypted version stays
```

## How to decrypt (on owner's machine, using PRIVATE key)

```powershell
gpg --decrypt backup_file.sql.gz.gpg > backup_file.sql.gz
```

## Status 2026-04-17

- **NOT YET INSTALLED** — owner has not generated keypair yet
- This is blocking 2E (encryption) and 2B (Backblaze — we should only upload encrypted)
- Approach: owner runs Step 1-3 above locally, gives me public key, I install on VPSes and patch backup.sh

## Why this order (pubkey first, encryption after)

Encryption without tested key = irrecoverable data loss. Must:
1. Generate keypair
2. **Test decrypt** a dummy file end-to-end
3. Store private key in 3 places (Bitwarden + USB + paper)
4. Only THEN enable encryption in backup.sh

Rushing step 1-2 = worse than no encryption (unreadable backups).
