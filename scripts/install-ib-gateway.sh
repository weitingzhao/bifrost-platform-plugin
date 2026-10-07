#!/usr/bin/env bash
# IB Gateway images are built by Tekton into the cluster registry.
#
# Importing a laptop build onto the nodes is refused. That path has no
# registry digest and no git SHA in the health hash (TD-122).
#
#   1. release.sh hold --what bifrost-platform-plugin
#   2. Pipeline bifrost-build-ib-gateway at k8s/cicd/pipeline-build.yaml
#      (revision = the 40-char SHA). The kaniko result `digest` is the pin.
#   3. Put that digest on k8s/ib-gateway/base/deployment.yaml, then apply.
set -euo pipefail

echo "REFUSED: ib-gateway images are not built on a laptop and copied onto nodes." >&2
echo "Build bifrost-build-ib-gateway (k8s/cicd/pipeline-build.yaml) and pin the digest." >&2
exit 1
