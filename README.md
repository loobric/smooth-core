# Smooth Core

> Application-agnostic REST API and database for tool data synchronization across CAM systems, CNC machines, and tool rooms.

[![License](https://img.shields.io/badge/License-Elastic%202.0-blue.svg)](LICENSE)


## Overview

Smooth Core is the central REST API and database system that provides a unified interface for managing tool data across manufacturing systems. It's designed to bridge the gap between CAM software, CNC machines, and tool rooms with a focus on real-time synchronization and data integrity.

### Key Features

- **RESTful API** with bulk operations for efficient data handling
- **Multi-tenant Architecture** with automatic data isolation
- **Standards-Aligned** with ISO 13399, STEP-NC, and MTConnect
- **Comprehensive Security** with role-based access control and audit logging
- **Developer-Friendly** with OpenAPI documentation and client libraries

## Quick Start Documentation

- [For Users](docs/QUICK_START.md)
- [For Developers](docs/DEVELOPMENT.md)

## Getting Help

- **Issues**: If you encounter any problems, please [open an issue](https://github.com/loobric/smooth-core/issues).
- **Discussion**: For questions and discussions, use [GitHub Discussions](https://github.com/loobric/smooth-core/discussions).

## Clients

This project was started out of a personal need to synchronize linuxcnc machine control with FreeCAD CAM workbenches. As such, these are the reference implementations of clients.  Additional clients are welcome and encouraged.

### **smooth-freecad** - FreeCAD CAM workbench integration

[smooth-freecad](https://github.com/loobric/smooth-freecad)

### **smooth-linuxcnc** - LinuxCNC controller integration

[smooth-linuxcnc](https://github.com/loobric/smooth-linuxcnc)

### **Smooth-CLI** - Command Line Interface

[smooth-cli](https://github.com/loobric/smooth-cli)

## Contributing

We welcome contributions! Please see our [Contributing Guide](docs/CONTRIBUTING.md) for details on how to get started.