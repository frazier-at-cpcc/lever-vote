#!/bin/sh
# Test, copy app.py, polls.json and static/ into a Proxmox container, and restart. Votes in state.json are kept.
# usage: DEPLOY_HOST=root@pve DEPLOY_CT=112 DEPLOY_URL=https://vote.example.com ./deploy.sh
set -e
: "${DEPLOY_HOST:?set DEPLOY_HOST (ssh target of the Proxmox host)}" "${DEPLOY_CT:?set DEPLOY_CT (container id)}"
cd "$(dirname "$0")"
python3 test_app.py
tar czf - app.py polls.json static | ssh "$DEPLOY_HOST" \
  "cat > /tmp/lv.tgz && pct push $DEPLOY_CT /tmp/lv.tgz /tmp/lv.tgz && rm /tmp/lv.tgz && pct exec $DEPLOY_CT -- sh -c 'tar xzf /tmp/lv.tgz -C /opt/lever-vote 2>/dev/null; rm /tmp/lv.tgz; systemctl restart lever-vote'"
if [ -n "$DEPLOY_URL" ]; then curl -sf -A Mozilla/5.0 "$DEPLOY_URL/healthz" && echo " deployed"; fi
