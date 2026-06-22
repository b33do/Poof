#!/bin/bash
set -x

# Unload VFIO
modprobe -r vfio_pci vfio_iommu_type1 vfio 2>/dev/null || true
