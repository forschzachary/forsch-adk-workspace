#!/usr/bin/env bash
# disable-stray-gateway.sh — make the adk-bridge container run ONLY the
# ADK Discord bridge, with NO stray Hermes "gateway-default" service.
#
# WHY: adk-bridge is built FROM the hermes-agent image. That image ships
# /etc/cont-init.d/02-reconcile-profiles, which runs hermes_cli.container_boot
# on every boot. container_boot ALWAYS registers a `gateway-default` s6 slot
# and AUTO-STARTS it (hermes gateway run) whenever
# $HERMES_HOME/gateway_state.json reads "running". adk-bridge bind-mounts the
# SAME ~/.hermes as the real `hermes` container, so it reads that shared
# "running" state and starts a SECOND gateway. That stray gateway:
#   - double-connects the SAME Discord bot token,
#   - floods logs with: s6-log: fatal: unable to lock
#     /opt/data/logs/gateways/default/lock: Resource busy
#     (the two containers fight over the shared log lock), and
#   - emits: WARNING gateway.run: Unauthorized user ... on discord.
# Evidence: /opt/data/logs/container-boot.log shows
#   "profile=default prior_state=running action=started".
# There is no env var that disables the reconciler (HERMES_GATEWAY_NO_SUPERVISE
# only gates the LEGACY-migration path, not the prior-state auto-start), so we
# neuter the cont-init script instead.
#
# DURABILITY: this edits the container's writable layer, which survives
# `docker restart adk-bridge` (the UI "Deploy" button). It does NOT survive
# `docker rm` + recreate from the image — so re-run THIS script after any
# reimage/recreate of adk-bridge. The script is idempotent.
set -euo pipefail
C="${1:-adk-bridge}"

docker exec -i "$C" sh -s <<'INNER'
set -e
# Move any stray backup OUT of cont-init.d — s6 runs EVERY file there,
# so a *.bak in that dir would re-run the stock reconciler.
mkdir -p /opt/hermes/hubert-overrides
for f in /etc/cont-init.d/02-reconcile-profiles.*; do
  [ -e "$f" ] && mv "$f" /opt/hermes/hubert-overrides/ || true
done
# Preserve the stock reconciler once, for reference.
if [ ! -e /opt/hermes/hubert-overrides/02-reconcile-profiles.stock-bak ] \
   && grep -q container_boot /etc/cont-init.d/02-reconcile-profiles 2>/dev/null; then
  cp /etc/cont-init.d/02-reconcile-profiles \
     /opt/hermes/hubert-overrides/02-reconcile-profiles.stock-bak
fi
cat > /etc/cont-init.d/02-reconcile-profiles <<'EOF'
#!/command/with-contenv sh
# HUBERT ADK-BRIDGE OVERRIDE: do NOT run the Hermes gateway reconciler.
# See workspace/adk/scripts/disable-stray-gateway.sh for the full rationale.
set -e
chown hermes:hermes /run/service 2>/dev/null || true
if [ -d /run/service/.s6-svscan ]; then
  for entry in control lock; do
    [ -e "/run/service/.s6-svscan/$entry" ] && \
      chown hermes:hermes "/run/service/.s6-svscan/$entry" 2>/dev/null || true
  done
fi
echo "[adk-bridge] cont-init: gateway reconciler DISABLED (ADK-only container)"
exit 0
EOF
chmod 0755 /etc/cont-init.d/02-reconcile-profiles
sh -n /etc/cont-init.d/02-reconcile-profiles
echo "[disable-stray-gateway] override installed"
INNER

echo "[disable-stray-gateway] done. Restart to apply: docker restart $C"
