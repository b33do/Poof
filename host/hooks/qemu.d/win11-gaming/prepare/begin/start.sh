#!/bin/bash
set -x

# Load VFIO
modprobe vfio_pci
modprobe vfio
modprobe vfio_iommu_type1

