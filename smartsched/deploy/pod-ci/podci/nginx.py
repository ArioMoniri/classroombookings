"""Insert the /ci/ location into the app's nginx config on the pod (smartsched/deploy/nginx/default.conf).

The repo file stays untouched in git; pod CI owns the deploy checkout, re-renders after every checkout and
restarts the proxy (a bind-mounted file keeps its old inode otherwise). The pod CI web server listens on
the docker0 address (172.17.0.1, pinned in /etc/docker/daemon.json), reachable from the proxy container
but not from the internet (the security group only opens 80/443).
"""

from __future__ import annotations

import re
from pathlib import Path

BEGIN = "    # >>> smartsched pod-ci (inserted on the pod by smartsched/deploy/pod-ci/podci/nginx.py) >>>"
END = "    # <<< smartsched pod-ci <<<"


def block(upstream: str) -> str:
    return "\n".join([
        BEGIN,
        "    location = /ci { return 301 /ci/; }",
        "    location /ci/ {",
        f"        proxy_pass http://{upstream};",
        "        proxy_read_timeout 60s;",
        "        proxy_buffering off;",
        "    }",
        END,
    ])


def render(conf: str, upstream: str = "172.17.0.1:8095") -> str:
    conf = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n\n?", "", conf, flags=re.S)
    if "location /ci/" in conf:
        return conf  # the repo config already routes /ci/ itself
    # Before the catch-all `location / {` (the last one), so /ci/ wins by prefix length anyway and the
    # block sits inside the same server {} as the app.
    matches = list(re.finditer(r"^[ \t]*location / \{", conf, flags=re.M))
    if not matches:
        raise ValueError("nginx config has no `location / {` catch-all to insert /ci/ before")
    at = matches[-1].start()
    return conf[:at] + block(upstream) + "\n\n" + conf[at:]


def apply(path: Path, upstream: str = "172.17.0.1:8095") -> bool:
    old = path.read_text(encoding="utf-8")
    new = render(old, upstream)
    if new != old:
        path.write_text(new, encoding="utf-8")
        return True
    return False
