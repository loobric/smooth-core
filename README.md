# Smooth Core

> Application-agnostic REST API and database for tool data synchronization across CAM systems, CNC machines, and tool rooms.

[![License](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)


## Overview

Smooth Core is the central REST API and database system that provides a unified interface for managing tool data across manufacturing systems. It's designed to bridge the gap between CAM software, CNC machines, and tool rooms with a focus on real-time synchronization and data integrity.

### Key Features

- **RESTful API** with bulk operations for efficient data handling
- **Multi-tenant Architecture** with automatic data isolation
- **Security built in**: role-based access control, tag-scoped API keys, immutable audit log
- **Change detection** by version or timestamp for efficient client sync
- **Backup and restore** with versioned tool set history and rollback
- **Developer-Friendly** with OpenAPI documentation and a CLI

Planned work (standards import, more clients, hosted offering) lives in [ROADMAP.md](ROADMAP.md) — this README only claims what runs today.

## Quick Start Documentation

- [For Users and the curious](docs/QUICK_START.md)
- [For Developers](docs/DEVELOPMENT.md)

## How-to guides

Task-oriented walkthroughs for linking a CNC control and a CAM library:

- [Mirror your machine's tools into CAM](docs/HOWTO_MIRROR_MACHINE_TOOLS_TO_CAM.md)
  — the machine has the tools; get them into your CAM library (control → CAM).
- [Reconcile a machine and a CAM library you built separately](docs/HOWTO_RECONCILE_MACHINE_AND_CAM_LIBRARY.md)
  — both sides exist; link them by identity, then reconcile numbering.
- Coming soon: the reverse direction (CAM → control), once the coverage view
  ships ([issue #18](https://github.com/loobric/smooth-core/issues/18)).

## Getting Help

- **Issues**: If you encounter any problems, please [open an issue](https://github.com/loobric/smooth-core/issues).
- **Discussion**: For questions and discussions, use [GitHub Discussions](https://github.com/loobric/smooth-core/discussions).

## Clients

This project was started out of a personal need to synchronize linuxcnc machine control with FreeCAD CAM workbenches. As such, these are the reference implementations of clients.  Additional clients are welcome and encouraged.

### **smooth-freecad** - FreeCAD CAM workbench integration

[smooth-freecad](https://github.com/loobric/smooth-freecad)

### **smooth-linuxcnc** - LinuxCNC controller integration

[smooth-linuxcnc](https://github.com/loobric/smooth-linuxcnc)

### **loobric** - Command Line Interface

Installed with smooth-core (the `loobric` command). Use it to manage API keys
and to review and bind reported tools. See the
[CLI reference and walkthrough](docs/CLI.md).

## Contributing

We welcome contributions! Please see our [Contributing Guide](docs/CONTRIBUTING.md) for details on how to get started.