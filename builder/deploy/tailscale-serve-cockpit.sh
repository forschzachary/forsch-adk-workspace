#!/usr/bin/env bash
# Expose the read-only Builder Cockpit over HTTPS on the tailnet (iframe-able).
# Additive to the existing :443 -> litellm mapping. Persists in tailscaled state;
# re-run after a reimage. Cockpit must be listening on 127.0.0.1:8780 (systemd).
set -euo pipefail
/usr/bin/tailscale serve --bg --https=8443 http://127.0.0.1:8780
/usr/bin/tailscale serve status
