"""Compare downloaded workflow artifacts with both public registries and smoke-test clean installs."""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
REPO = "https://github.com/xvierd/a2a-lite"
NPM = "https://registry.npmjs.org"
SLSA = "https://slsa.dev/provenance/v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "a2a-lite-release-verifier"}), timeout=45) as response:
        return response.read()


def check_pypi(version, directory):
    release = json.loads(fetch(f"https://pypi.org/pypi/a2a-lite/{version}/json"))
    require(release["info"]["name"] == "a2a-lite" and release["info"]["version"] == version, "Wrong PyPI release")
    wheel = f"a2a_lite-{version}-py3-none-any.whl"
    files = {f["filename"]: f for f in release["urls"]}
    expected = {wheel, f"a2a_lite-{version}.tar.gz"}
    require(set(files) == expected, "Unexpected PyPI distribution set")
    local_names = {f.name for f in directory.iterdir() if not f.name.startswith(".")}
    require(local_names == expected, "Unexpected python-dist contents")
    digests = {}
    for name, file in files.items():
        require(not file["yanked"], f"{name} was yanked")
        digest = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        remote = hashlib.sha256(fetch(file["url"])).hexdigest()
        require(digest == remote == file["digests"]["sha256"], f"{name} SHA-256 mismatch")
        digests[name] = digest
    return digests, files[wheel]


def check_npm(version, sha, directory):
    release = json.loads(fetch(f"{NPM}/a2a-lite/{version}"))
    require(release["name"] == "a2a-lite" and release["version"] == version, "Wrong npm release")
    require(not release.get("gitHead") or release["gitHead"] == sha, "npm gitHead disagrees with the expected commit")
    tar_name = f"a2a-lite-{version}.tgz"
    files = {f.name for f in directory.iterdir() if not f.name.startswith(".")}
    require(files == {tar_name}, "Unexpected npm-dist contents")
    dist = release["dist"]
    digest = hashlib.sha512((directory / tar_name).read_bytes()).digest()
    integrity = "sha512-" + base64.b64encode(digest).decode()
    require(integrity == dist["integrity"], "npm artifact does not match registry integrity")
    require(hashlib.sha512(fetch(dist["tarball"])).digest() == digest, "Published npm tarball differs from workflow")
    attestations = json.loads(fetch(dist["attestations"]["url"]))["attestations"]
    proofs = [a for a in attestations if a["predicateType"] == SLSA]
    require(len(proofs) == 1, "Expected one SLSA v1 provenance statement")
    envelope = proofs[0]["bundle"]["dsseEnvelope"]
    statement = json.loads(base64.b64decode(envelope["payload"], validate=True))
    require(statement["predicateType"] == SLSA, "Wrong signed predicate")
    expected_subject = f"pkg:npm/a2a-lite@{version}"
    require(
        any(s["name"] == expected_subject and s["digest"].get("sha512") == digest.hex() for s in statement["subject"]),
        "Provenance subject differs from released tarball",
    )
    definition = statement["predicate"]["buildDefinition"]
    workflow = definition["externalParameters"]["workflow"]
    require(
        workflow["repository"] == REPO and workflow["path"] == ".github/workflows/publish-npm.yml",
        "Unexpected npm publishing workflow",
    )
    source = "git+" + REPO + "@" + workflow["ref"]
    require(
        any(d["uri"] == source and d["digest"].get("gitCommit") == sha for d in definition["resolvedDependencies"]),
        "Provenance source does not match the expected commit",
    )
    invocation = statement["predicate"]["runDetails"]["metadata"]["invocationId"]
    require(
        re.fullmatch(re.escape(REPO) + r"/actions/runs/[0-9]+/attempts/[0-9]+", invocation),
        "Unexpected npm workflow run URL",
    )
    return dist, invocation


def run(args, cwd, env):
    result = subprocess.run(
        args, cwd=cwd, env=env, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300
    )
    if result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed ({result.returncode})\n{result.stdout}")
    return result.stdout.strip()


def smoke_python(version, work, env, wheel):
    venv = work / "venv"
    run([sys.executable, "-I", "-m", "venv", str(venv)], work, env)
    python = str(venv / "bin/python")
    report = work / "pip-report.json"
    run(
        [
            python,
            "-I",
            "-m",
            "pip",
            "--isolated",
            "install",
            "--no-cache-dir",
            "--index-url",
            "https://pypi.org/simple",
            "--report",
            str(report),
            f"a2a-lite=={version}",
        ],
        work,
        env,
    )
    installed = next(i for i in json.loads(report.read_text())["install"] if i["metadata"]["name"] == "a2a-lite")
    download = installed["download_info"]
    require(
        download["url"] == wheel["url"] and download["archive_info"]["hashes"]["sha256"] == wheel["digests"]["sha256"],
        "Clean Python install did not use the verified registry wheel",
    )
    cli = str(venv / "bin/a2a-lite")
    require(run([cli, "version"], work, env) == f"A2A Lite v{version}", "Wrong Python CLI version")
    require("Usage" in run([cli, "--help"], work, env), "Missing Python CLI help")
    run([python, "-I", str(HERE / "python_smoke.py"), version], work, env)


def smoke_npm(version, work, env, dist):
    install = work / "npm-install"
    install.mkdir()
    (install / "package.json").write_text(json.dumps({"name": "release-check", "private": True, "version": "0.0.0"}))
    options = ["--registry", NPM, "--cache", str(work / "npm-cache"), "--userconfig", os.devnull]
    run(["npm", "install", *options, "--no-audit", "--no-fund", "--save-exact", f"a2a-lite@{version}"], install, env)
    installed = json.loads((install / "package-lock.json").read_text())["packages"]["node_modules/a2a-lite"]
    require(
        installed["version"] == version
        and installed["resolved"] == dist["tarball"]
        and installed["integrity"] == dist["integrity"],
        "Clean npm install did not use the verified tarball",
    )
    # npm CLI validates registry signatures and signed Sigstore attestations on installed packages.
    run(["npm", "audit", "signatures", *options], install, env)
    cli = str(install / "node_modules/.bin/a2a-lite")
    require(run([cli, "--version"], install, env) == version, "Wrong npm CLI version")
    require("doctor" in run([cli, "--help"], install, env), "Missing npm CLI help")
    shutil.copy(HERE / "npm_smoke.mjs", install)
    run(["node", "npm_smoke.mjs"], install, env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True, help="Full Git commit SHA from the successful release workflows")
    parser.add_argument("--python-dist", required=True, type=Path, help="Extracted python-dist workflow artifact")
    parser.add_argument("--npm-dist", required=True, type=Path, help="Extracted npm-dist workflow artifact")
    args = parser.parse_args()
    require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", args.version), "Expected a stable release version")
    require(re.fullmatch(r"[0-9a-f]{40}", args.commit), "Expected a full lowercase Git commit SHA")
    digests, wheel = check_pypi(args.version, args.python_dist)
    dist, invocation = check_npm(args.version, args.commit, args.npm_dist)
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "NODE_PATH", "VIRTUAL_ENV", "NODE_OPTIONS", "PYTHONOPTIMIZE"):
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="a2a-lite-release-") as tmp:
        work = Path(tmp)
        smoke_python(args.version, work, env, wheel)
        smoke_npm(args.version, work, env, dist)
    print(
        json.dumps(
            {
                "version": args.version,
                "commit": args.commit,
                "pypiSha256": digests,
                "npmIntegrity": dist["integrity"],
                "npmProvenanceRun": invocation,
                "registryInstalls": "passed",
                "npmSignatures": "verified",
                "cli": "passed",
                "esmAndCjs": "passed",
                "messageTaskStream": "passed",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
