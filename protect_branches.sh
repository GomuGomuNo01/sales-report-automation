#!/usr/bin/env bash
# =============================================================
# protect_branches.sh
# Protège les branches main et dev contre les modifications
# non autorisées sur le dépôt GitHub.
#
# Prérequis : être connecté avec  gh auth login
# Usage     : bash protect_branches.sh
# =============================================================

REPO="GomuGomuNo01/sales-report-automation"

protect() {
  local BRANCH=$1
  echo "→ Protection de la branche : $BRANCH"

  gh api \
    --method PUT \
    -H "Accept: application/vnd.github+json" \
    "/repos/$REPO/branches/$BRANCH/protection" \
    --input - <<EOF
{
  "required_status_checks": null,
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0,
    "bypass_pull_request_allowances": {
      "users": ["GomuGomuNo01"],
      "teams": [],
      "apps": []
    }
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": false
}
EOF

  if [ $? -eq 0 ]; then
    echo "  ✓ $BRANCH protégée"
  else
    echo "  ✗ Échec pour $BRANCH — vérifiez que gh auth login est fait"
  fi
}

protect "main"
protect "dev"

echo ""
echo "Règles appliquées :"
echo "  • Force-push interdit"
echo "  • Suppression de branche interdite"
echo "  • Toute modification passe par une Pull Request"
echo "  • Seul GomuGomuNo01 peut bypasser la règle PR"
