"""The IB Gateway manifest is a registry image, and the build records a digest."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_deployment_pulls_from_the_registry_and_not_a_local_tag() -> None:
    text = (ROOT / "k8s/ib-gateway/base/deployment.yaml").read_text()
    assert "192.168.10.73:30500/bifrost-platform-plugin-ib-gateway:" in text
    assert "imagePullPolicy: Always" in text
    assert "imagePullPolicy: IfNotPresent" not in text
    image_line = next(line.strip() for line in text.splitlines() if line.strip().startswith("image:"))
    assert image_line.startswith("image: 192.168.10.73:30500/")


def test_build_pipeline_pushes_a_digest_and_bakes_the_git_sha() -> None:
    text = (ROOT / "k8s/cicd/pipeline-build.yaml").read_text()
    assert "bifrost-build-ib-gateway" in text
    assert "--digest-file=$(results.digest.path)" in text
    assert "--build-arg=GIT_SHA=$(params.revision)" in text
    assert "registry.cicd.svc.cluster.local:5000/bifrost-platform-plugin-ib-gateway" in text
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "IB_GATEWAY_GIT_SHA" in dockerfile


def test_install_script_does_not_import_with_ctr() -> None:
    text = (ROOT / "scripts/install-ib-gateway.sh").read_text()
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))
    assert "ctr" not in code
    assert "docker build" not in code
    assert "REFUSED" in text
