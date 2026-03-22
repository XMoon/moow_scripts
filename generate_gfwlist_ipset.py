#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen


GOOGLE_IP_RANGES_URL = "https://www.gstatic.com/ipranges/goog.json"
RIPESTAT_ANNOUNCED_PREFIXES_URL = (
    "https://stat.ripe.net/data/announced-prefixes/data.json?resource={asn}"
)


def log(message: str) -> None:
    print(f"[gfwlist] {message}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default="/etc/ipset",
        help="directory used to write gfwlist4.txt and gfwlist6.txt",
    )
    return parser.parse_args()


def fetch_json(url: str) -> dict:
    log(f"GET {url}")
    request = Request(url, headers={"User-Agent": "curl/8.5.0"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def collect_google() -> tuple[set[str], set[str]]:
    log("google: collecting prefixes via custom handler")
    data = fetch_json(GOOGLE_IP_RANGES_URL)
    ipv4 = set()
    ipv6 = set()
    for prefix in data["prefixes"]:
        if "ipv4Prefix" in prefix:
            ipv4.add(prefix["ipv4Prefix"])
        if "ipv6Prefix" in prefix:
            ipv6.add(prefix["ipv6Prefix"])
    return ipv4, ipv6


def collect_from_asns(name: str, asns: list[str]) -> tuple[set[str], set[str]]:
    ipv4 = set()
    ipv6 = set()
    for asn in asns:
        log(f"{name}: collecting prefixes via ASN {asn} with RIPEstat announced-prefixes")
        data = fetch_json(RIPESTAT_ANNOUNCED_PREFIXES_URL.format(asn=asn))
        for item in data["data"]["prefixes"]:
            prefix = item["prefix"]
            if ":" in prefix:
                ipv6.add(prefix)
            else:
                ipv4.add(prefix)
    return ipv4, ipv6


def collect_manual(name: str, source: dict) -> tuple[set[str], set[str]]:
    log(f"{name}: collecting prefixes via manual config")
    return set(source.get("ipv4", [])), set(source.get("ipv6", []))


CUSTOM_HANDLERS: dict[str, Callable[[], tuple[set[str], set[str]]]] = {
    "google": collect_google,
}


# Add new services here with type=custom/asn/manual.
SOURCES = {
    "google": {
        "type": "custom",
        "handler": "google",
    },
    "telegram": {
        "type": "asn",
        "asns": ["AS44907", "AS59930", "AS62041", "AS62014"],
    },
}


def collect_source(name: str, source: dict) -> tuple[set[str], set[str]]:
    source_type = source["type"]
    if source_type == "custom":
        log(f"{name}: source type=custom")
        return CUSTOM_HANDLERS[source["handler"]]()
    if source_type == "asn":
        log(f"{name}: source type=asn")
        return collect_from_asns(name, source["asns"])
    if source_type == "manual":
        log(f"{name}: source type=manual")
        return collect_manual(name, source)
    raise ValueError(f"unsupported source type: {source_type}")


def write_prefixes(path: Path, prefixes: set[str]) -> None:
    log(f"writing {len(prefixes)} prefixes to {path}")
    content = "\n".join(sorted(prefixes))
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    log(f"using output directory {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    ipv4 = set()
    ipv6 = set()
    for name, source in SOURCES.items():
        log(f"processing source {name}")
        source_ipv4, source_ipv6 = collect_source(name, source)
        ipv4.update(source_ipv4)
        ipv6.update(source_ipv6)
        log(
            f"{name}: collected {len(source_ipv4)} IPv4 prefixes and {len(source_ipv6)} IPv6 prefixes"
        )

    gfwlist4 = output_dir / "gfwlist4.txt"
    gfwlist6 = output_dir / "gfwlist6.txt"
    write_prefixes(gfwlist4, ipv4)
    write_prefixes(gfwlist6, ipv6)

    log(f"wrote {len(ipv4)} IPv4 prefixes to {gfwlist4}")
    log(f"wrote {len(ipv6)} IPv6 prefixes to {gfwlist6}")


if __name__ == "__main__":
    main()
