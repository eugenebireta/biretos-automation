# Backblaze B2 with Object Lock — setup guide for owner

Per critique 1: without an immutable (WORM) cloud copy, backups can be destroyed by:
- Ransomware that encrypts all connected storage
- Compromised root on any VPS → `rm -rf` on rsync destination
- Runaway AI (me) with root access doing something stupid

B2 Object Lock is the ONLY layer that physically cannot be bypassed — even with full root + stolen API keys, backups from the last N days cannot be deleted.

## Cost estimate for your data

Your real backup volume:
- biretos.ae hourly: ~30 MB/hour × 24 × 7 day retention = ~5 GB sliding
- dev.bireta.ru hourly: ~300 MB/hour × 24 × 7 day = ~50 GB sliding
- Daily×7 + Weekly×4 + Monthly forever = ~1-2 GB after ~1 year

**Total at steady state: ~10-15 GB**

B2 pricing (2026): **$6/TB/month storage + $10/TB egress**
- 15 GB × $6/1024 = **$0.09/month storage**
- Egress only on restore (rare): if restore full 15 GB = $0.15 one-time
- **Effective cost: ~$0.10/month**

Alternatives considered:
- **Cloudflare R2:** zero egress, same $/TB. But Bucket Lock is new (March 2025), less battle-tested
- **AWS S3 Glacier:** cheaper storage, but expensive retrieval + complex
- **Hetzner Storage Box:** cheapest (€3.10/mo for 1 TB) but no true immutability

**Recommendation: Backblaze B2 + Object Lock 30-day Compliance mode.**

## Setup steps (owner does this, 15-20 minutes)

### Step 1. Create B2 account
- Go to https://www.backblaze.com/cloud-storage
- Sign up (free account, first 10 GB free tier)
- Verify email

### Step 2. Enable B2 + create bucket
- Navigate to: My Account → B2 Cloud Storage
- Create Application Key (master key) first — needed to create buckets
- Create bucket:
  - Name: `biretos-backup-2026` (or similar unique)
  - Type: **Private**
  - Object Lock: **ENABLED** (⚠ cannot be changed after creation!)
  - Default retention: **Compliance mode, 30 days**

### Step 3. Create restricted application key for upload
- In Application Keys section → Add a New Application Key
- Settings:
  - Name: `biretos-upload-usa` (one key per VPS for rotation)
  - Bucket: `biretos-backup-2026` (restricted to this bucket only)
  - Type of Access: **Read and Write**
  - Allow List All Bucket Names: No (principle of least privilege)
  - File name prefix: leave empty (allow all)
  - Duration: leave empty (never expires)

- Copy: `keyID`, `applicationKey`, `endpoint` (e.g. `s3.us-west-004.backblazeb2.com`)
- Create another key for RU VPS: `biretos-upload-ru`

### Step 4. Give me the credentials

Either add to `config/.secrets.env`:
```
B2_KEY_ID_USA=...
B2_APP_KEY_USA=...
B2_KEY_ID_RU=...
B2_APP_KEY_RU=...
B2_BUCKET=biretos-backup-2026
B2_ENDPOINT=s3.us-west-004.backblazeb2.com
```

Or paste to me in chat — I'll install them on VPSes.

### Step 5. I install rclone + integrate into backup.sh

After I have keys, I will:
1. Install `rclone` on both VPSes
2. Configure `rclone` with B2 endpoint (uses S3-compatible API)
3. Add to `backup.sh` daily (at 23:00 promotion):
   ```bash
   rclone copy /root/backups/daily/db_$(date +%Y%m%d).sql.gz \
       biretos_b2:biretos-backup-2026/biretos.ae/daily/ \
       --b2-versions --retention-mode compliance --retention-period 30d
   ```
4. First weekly upload: all current daily files + current media → B2
5. Telegram alert on upload failure

## Verification that Object Lock works

After first upload, I'll run this from VPS:
```bash
# Try to delete a file — should fail if Object Lock enforced
rclone delete biretos_b2:biretos-backup-2026/biretos.ae/daily/test_file.gz
# Expected: "Failed to delete file: 403 Forbidden (object is under legal hold or compliance retention)"
```

If this fails to delete = immutability confirmed.

## What's NOT in scope for Phase 2B

- Two-factor auth for Backblaze account (owner should enable separately)
- Automatic retention extension beyond 30 days (we can add to Phase 3)
- Multi-region replication (B2 already has 99.999999999% durability)
- Restore automation (manual on demand — not part of hourly flow)

---

**Status 2026-04-17: BLOCKED — waiting for owner to complete Step 1-4.**

When ready, say: "B2 keys ready" and paste credentials (or put in `.secrets.env`).
