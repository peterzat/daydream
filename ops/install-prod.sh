#!/usr/bin/env bash
# One-time (idempotent) prod install for daydream on this box. Run it YOURSELF:
#
#     sudo ops/install-prod.sh
#
# It creates the sandboxed service user and the /srv/daydream layout, installs
# cloudflared from Cloudflare's apt repo, the systemd units, and a narrow
# sudoers entry. It asks for the tunnel token (typed, never echoed, never
# passing through a Claude session). Re-running changes nothing that is
# already right. Design and reasons: docs/GOING-LIVE.md section 7; the
# Cloudflare side: docs/CLOUDFLARE-SETUP.md.
#
# What it does NOT do: open any port (UFW is untouched), enable anything at
# boot except the nightly backup timer, or start the village (that is
# `bin/game prod wake`).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "run with sudo: sudo $0" >&2
    exit 2
fi
OPERATOR="${SUDO_USER:-peter}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPS="$REPO/ops"
SRV=/srv/daydream

say() { printf '\n==> %s\n' "$*"; }

# ---- the service user -------------------------------------------------------
say "service user 'daydream' (no shell, no home outside /srv/daydream/data)"
if ! id daydream >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$SRV/data" --no-create-home \
        --shell /usr/sbin/nologin daydream
    echo "created user daydream"
else
    echo "user daydream exists"
fi
if id -nG daydream | tr ' ' '\n' | grep -qx docker; then
    echo "error: daydream is in the docker group (root-equivalent); remove it first" >&2
    exit 1
fi
for g in daydream systemd-journal; do
    if ! id -nG "$OPERATOR" | tr ' ' '\n' | grep -qx "$g"; then
        usermod -aG "$g" "$OPERATOR"
        echo "added $OPERATOR to $g (log out and back in for it to apply)"
    fi
done

# ---- layout -----------------------------------------------------------------
say "layout under $SRV"
command -v setfacl >/dev/null || apt-get install -y acl
install -d -o "$OPERATOR" -g daydream -m 2750 "$SRV" "$SRV/releases" "$SRV/venvs"
install -d -o daydream -g daydream -m 2770 "$SRV/data"
install -d -o root -g daydream -m 0750 "$SRV/etc"
# The operator's CLI and the service both write the data dir: group rw on
# every new file and dir, whoever creates it.
setfacl -m "u:$OPERATOR:rwx,g:daydream:rwx" "$SRV/data"
setfacl -d -m "u::rwx,u:$OPERATOR:rwx,g::rwx,g:daydream:rwx,o::---" "$SRV/data"
# The GPU lock every daydream process on the box shares (the arbiter's
# cross-process layer): dev, prod and a tier_long run take turns on the card.
if [[ ! -e "$SRV/data/gpu.lock" ]]; then
    install -o daydream -g daydream -m 0660 /dev/null "$SRV/data/gpu.lock"
fi
if [[ ! -f "$SRV/etc/prod.env" ]]; then
    install -o root -g daydream -m 0640 "$OPS/prod.env.example" "$SRV/etc/prod.env"
    echo "installed $SRV/etc/prod.env from ops/prod.env.example (review it)"
else
    echo "$SRV/etc/prod.env exists (left as is)"
fi

# ---- cloudflared ------------------------------------------------------------
say "age (encrypts the offsite backups to your SSH keys)"
command -v age >/dev/null || apt-get install -y age

say "cloudflared from Cloudflare's apt repo"
if ! command -v cloudflared >/dev/null; then
    install -d -m 0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
        -o /usr/share/keyrings/cloudflare-main.gpg
    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' \
        > /etc/apt/sources.list.d/cloudflared.list
    apt-get update -qq
    apt-get install -y cloudflared
fi
cloudflared --version
install -d -o root -g root -m 0700 /etc/cloudflared
if [[ ! -s /etc/cloudflared/daydream.env ]]; then
    echo
    echo "Paste the tunnel token for 'daydream' (Zero Trust > Networks > Tunnels >"
    echo "daydream > the 'cloudflared service install <TOKEN>' command's last word)."
    read -rsp "tunnel token: " token
    echo
    if [[ -z "$token" ]]; then
        echo "no token given; re-run once the tunnel exists" >&2
    else
        umask 077
        printf 'TUNNEL_TOKEN=%s\n' "$token" > /etc/cloudflared/daydream.env
        chmod 0600 /etc/cloudflared/daydream.env
        echo "saved /etc/cloudflared/daydream.env (root-only)"
    fi
    unset token
else
    echo "/etc/cloudflared/daydream.env exists (left as is)"
fi

# ---- units + sudoers ----------------------------------------------------------
say "systemd units"
for u in daydream-prod.service cloudflared-daydream.service daydream-backup.service \
         daydream-backup.timer daydream-keepsakes.timer; do
    install -o root -g root -m 0644 "$OPS/systemd/$u" "/etc/systemd/system/$u"
done
install -o root -g root -m 0644 "$OPS/systemd/daydream-offsite.timer" /etc/systemd/system/
for u in daydream-keepsakes.service daydream-offsite.service; do
    sed -e "s|@OPERATOR@|$OPERATOR|g" -e "s|@REPO@|$REPO|g" "$OPS/systemd/$u" \
        > "/etc/systemd/system/$u"
    chmod 0644 "/etc/systemd/system/$u"
done
systemctl daemon-reload
systemctl enable --now daydream-backup.timer daydream-keepsakes.timer daydream-offsite.timer >/dev/null
echo "installed; only the backup, keepsakes and offsite timers are enabled at boot"

say "sudoers: start/stop/restart of the daydream units only"
tmp="$(mktemp)"
cp "$OPS/sudoers.d/daydream" "$tmp"
sed -i "s/^peter /$OPERATOR /" "$tmp"
visudo -cf "$tmp" >/dev/null
install -o root -g root -m 0440 "$tmp" /etc/sudoers.d/daydream
rm -f "$tmp"
echo "installed /etc/sudoers.d/daydream"

say "sandbox score"
systemd-analyze security daydream-prod.service --no-pager | tail -1 || true

cat <<EOF

Done. Next (as $OPERATOR, after logging out and back in):
  bin/game prod deploy          # first release into $SRV/releases
  bin/game prod world reset     # a fresh village for prod
  bin/game prod wake            # engines, tunnel, service; the edge says awake
EOF
