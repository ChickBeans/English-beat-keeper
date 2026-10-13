"""Sync voice/ with the Cloudflare R2 bucket (S3 API, standard library only).

  python tools/r2_sync.py push [--dry-run]   # upload new / changed files from voice/
  python tools/r2_sync.py pull               # download files missing locally (fresh checkout)
  python tools/r2_sync.py ls                 # list what is in the bucket

Reads R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT (https://<account>.r2.cloudflarestorage.com)
and optionally R2_BUCKET (default beatkeep-voice). Objects keep their path, e.g. voice/bf_emma/<set id>.mp3.
MP3s are immutable (a changed take gets a new name or is overwritten together with the manifest),
so they are cached for a year; the manifest for a minute.
"""
import datetime, hashlib, hmac, os, sys, urllib.parse, urllib.request, xml.etree.ElementTree as ET

KEY, SECRET = os.environ.get("R2_ACCESS_KEY_ID"), os.environ.get("R2_SECRET_ACCESS_KEY")
ENDPOINT, BUCKET = (os.environ.get("R2_ENDPOINT") or "").rstrip("/"), os.environ.get("R2_BUCKET", "beatkeep-voice")
ROOT = "voice"

def sign(method, path, query="", body=b"", headers=None):
    headers = dict(headers or {})
    host = urllib.parse.urlparse(ENDPOINT).netloc
    now = datetime.datetime.now(datetime.timezone.utc)
    amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload = hashlib.sha256(body).hexdigest()
    headers.update({"host": host, "x-amz-date": amz, "x-amz-content-sha256": payload})
    names = sorted(k.lower() for k in headers)
    canon_h = "".join("%s:%s\n" % (k, str(headers[next(h for h in headers if h.lower() == k)]).strip()) for k in names)
    signed = ";".join(names)
    req = "\n".join([method, urllib.parse.quote(path), query, canon_h, signed, payload])
    scope = "%s/auto/s3/aws4_request" % day
    sts = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(req.encode()).hexdigest()])
    k = ("AWS4" + SECRET).encode()
    for part in (day, "auto", "s3", "aws4_request"): k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    headers["Authorization"] = "AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s" % (KEY, scope, signed, sig)
    return headers

def call(method, key="", query="", body=b"", headers=None):
    path = "/%s/%s" % (BUCKET, key) if key else "/%s" % BUCKET
    h = sign(method, path, query, body, headers)
    url = ENDPOINT + urllib.parse.quote(path) + ("?" + query if query else "")
    return urllib.request.urlopen(urllib.request.Request(url, data=body if method == "PUT" else None, method=method, headers=h))

def remote():
    out, token = {}, None
    while True:
        q = {"list-type": "2", "prefix": ROOT + "/"}
        if token: q["continuation-token"] = token
        query = "&".join("%s=%s" % (urllib.parse.quote(k, safe=""), urllib.parse.quote(v, safe="")) for k, v in sorted(q.items()))
        root = ET.fromstring(call("GET", query=query).read())
        ns = {"s": root.tag.split("}")[0].strip("{")}
        for c in root.findall("s:Contents", ns):
            out[c.find("s:Key", ns).text] = c.find("s:ETag", ns).text.strip('"')
        if root.findtext("s:IsTruncated", namespaces=ns) != "true": return out
        token = root.findtext("s:NextContinuationToken", namespaces=ns)

def local():
    out = {}
    for d, _, fs in os.walk(ROOT):
        for f in fs:
            if f.endswith((".mp3", ".json")) and not f.endswith(".tmp"): out[os.path.join(d, f).replace(os.sep, "/")] = None
    return out

def main():
    if not (KEY and SECRET and ENDPOINT): sys.exit("R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_ENDPOINT are not set")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ls"
    rem = remote()
    if cmd == "ls":
        for k in sorted(rem): print(k)
        print(len(rem), "objects"); return
    if cmd == "push":
        n = 0
        for path in sorted(local()):
            body = open(path, "rb").read()
            if rem.get(path) == hashlib.md5(body).hexdigest(): continue
            typ = "application/json" if path.endswith(".json") else "audio/mpeg"
            cache = "public, max-age=60" if path.endswith(".json") else "public, max-age=31536000, immutable"
            print("put", path, len(body))
            if "--dry-run" not in sys.argv: call("PUT", path, body=body, headers={"content-type": typ, "cache-control": cache})
            n += 1
        print(n, "uploaded"); return
    if cmd == "pull":
        n = 0
        for key in sorted(rem):
            if os.path.exists(key): continue
            os.makedirs(os.path.dirname(key), exist_ok=True)
            open(key, "wb").write(call("GET", key).read()); n += 1
        print(n, "downloaded"); return
    sys.exit("usage: r2_sync.py push|pull|ls")

if __name__ == "__main__":
    main()
