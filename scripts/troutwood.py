#!/usr/bin/env python3
"""
Troutwood's "map of the markets": its data files refuse plain requests, because
the site hands every visitor temporary guest credentials (an Amazon Cognito
guest identity) and signs its requests with them. This does the same thing its
page does for any visitor: takes a guest identity from the pool named in the
site's own code, and reads its two data files with it, into
  troutwood/core.json, troutwood/bubble-metric-config.json
and prints what the data holds, so the map layer can be built from it.
"""
import gzip, json, pathlib, re, subprocess, sys, urllib.request

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "boto3"], check=True)
import boto3  # noqa: E402
from botocore import UNSIGNED  # noqa: E402
from botocore.config import Config  # noqa: E402

SITE = "https://map.troutwood.com/"
BUCKET, REGION = "datacache862b3-main", "us-east-2"
OUT = pathlib.Path("troutwood")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy)"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")


def pool_id():
    html = get(SITE)
    code = html
    for src in re.findall(r'src="(/[^"]+\.js)"', html):
        try:
            code += get(SITE.rstrip("/") + src)
        except Exception:  # noqa: BLE001
            pass
    m = re.search(r"us-east-2:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", code)
    return m.group(0) if m else None


def describe(obj, depth=0, key="data"):
    pad = "  " * depth
    if isinstance(obj, dict):
        print(f"{pad}{key}: object with {len(obj)} keys: {', '.join(list(obj)[:25])}")
        for k in list(obj)[:6]:
            if depth < 3:
                describe(obj[k], depth + 1, k)
    elif isinstance(obj, list):
        print(f"{pad}{key}: list of {len(obj)}")
        if obj and depth < 3:
            describe(obj[0], depth + 1, f"{key}[0]")
    else:
        print(f"{pad}{key}: {str(obj)[:120]}")


def main():
    pid = pool_id()
    if not pid:
        sys.exit("troutwood: no guest identity pool found in the site's code")
    ci = boto3.client("cognito-identity", region_name=REGION, config=Config(signature_version=UNSIGNED))
    ident = ci.get_id(IdentityPoolId=pid)["IdentityId"]
    cr = ci.get_credentials_for_identity(IdentityId=ident)["Credentials"]
    s3 = boto3.client("s3", region_name=REGION, aws_access_key_id=cr["AccessKeyId"],
                      aws_secret_access_key=cr["SecretKey"], aws_session_token=cr["SessionToken"])
    OUT.mkdir(exist_ok=True)
    for key, name in (("public/core.json.gz", "core.json"), ("public/bubble-metric-config.json", "bubble-metric-config.json")):
        body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        if body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        (OUT / name).write_bytes(body)
        print(f"troutwood {name}: {len(body):,} bytes")
        describe(json.loads(body), key=name)


if __name__ == "__main__":
    main()
