# Worker Metrics Private Network Contract

Status: implementation pending CI verification
Date: 2026-09-29
Issue: #21

## Authorization

The user explicitly approved the bounded worker-metrics network gate on
2026-09-29.

That approval covers an opt-in Prometheus listener owned by the worker process.
It does not authorize public exposure, security-group/IAM/VPN changes, GPU
provisioning, cloud resource creation, or recurring spend.

## Process-level exposure

Configuration:

    WORKER_METRICS_ENABLED=false
    WORKER_METRICS_HOST=127.0.0.1
    WORKER_METRICS_PORT=9101

Secure defaults:

- disabled unless explicitly enabled;
- loopback bind by default;
- wildcard binds such as 0.0.0.0 and :: are rejected;
- public IP literals are rejected;
- allowed non-loopback binds are RFC1918 IPv4 or ULA IPv6 private addresses;
- hostnames are rejected to avoid DNS-dependent trust ambiguity;
- only GET /metrics is served;
- unrelated paths return 404;
- no control or mutation endpoint exists.

## Deployment model

For the first single-node measurement environment, Prometheus can scrape the
worker on 127.0.0.1:9101 without changing the host's external network surface.

If Prometheus later runs on another instance/container/host, enabling a private
worker IP bind is not sufficient by itself. The deployment must separately
approve and document the exact private route and security-group/firewall rule
that permits only the intended Prometheus source to reach the worker metrics
port.

No public ingress rule should be created for port 9101.

## Authentication and encryption

This increment does not add HTTP authentication or TLS to the worker metrics
listener. The security boundary is the private bind plus infrastructure
reachability policy.

If the metrics path must cross an untrusted network boundary in the future,
terminate authenticated/encrypted transport in an approved sidecar, proxy, or
service-mesh layer rather than weakening the private-bind rule.

## Rollback

Immediate runtime rollback:

    WORKER_METRICS_ENABLED=false

Code rollback:

- revert the focused issue #21 change;
- remove the worker scrape job from the Prometheus baseline;
- no cloud resource rollback is required because this issue does not create or
  modify cloud infrastructure.

## Evidence required before hardware benchmarking

Before accepting full distributed Production Evidence v1 telemetry:

- worker listener is enabled only on the intended node;
- bind address is loopback or the approved private IP;
- Prometheus can scrape /metrics;
- an unintended/public address cannot reach the listener;
- the worker metric families appear separately from gateway metrics;
- the exact network path is recorded if scraping is remote.
