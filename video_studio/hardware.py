"""OMNIA Video Studio — Hardware & Platform Environment Detection (Module 1).

Discovers host CPU, RAM, disk, OS platform, architecture, and potential acceleration APIs
safely without heavy dependencies or unhandled errors.
"""

import sys
import platform
import os
import shutil
import logging
from typing import Dict, Any, List
from video_studio.registry_models import AccelerationAPI

logger = logging.getLogger("Omnia.VideoStudio.Hardware")

class VideoStudioHardwareDetector:
    """Safe, non-intrusive probe of host compute, platform, and acceleration capabilities."""

    @classmethod
    def detect_platform(cls) -> Dict[str, str]:
        system_os = platform.system().lower()
        if "win" in system_os:
            os_name = "windows"
        elif "darwin" in system_os:
            os_name = "macos"
        else:
            os_name = "linux"

        arch = platform.machine()
        return {
            "os": os_name,
            "architecture": arch,
            "python_version": sys.version.split()[0],
            "release": platform.release(),
        }

    @classmethod
    def detect_system_resources(cls) -> Dict[str, Any]:
        ram_total_mb = 4096
        ram_free_mb = 2048
        try:
            import psutil
            mem = psutil.virtual_memory()
            ram_total_mb = int(mem.total / (1024 * 1024))
            ram_free_mb = int(mem.available / (1024 * 1024))
        except ImportError:
            pass

        # Disk space in current working directory
        disk_free_mb = 10240
        try:
            stat = shutil.disk_usage(".")
            disk_free_mb = int(stat.free / (1024 * 1024))
        except Exception:
            pass

        return {
            "ram_total_mb": ram_total_mb,
            "ram_free_mb": ram_free_mb,
            "disk_free_mb": disk_free_mb,
            "cpu_count": os.cpu_count() or 4,
        }

    @classmethod
    def detect_acceleration_apis(cls) -> List[AccelerationAPI]:
        """Probes available acceleration platforms without hard dependencies."""
        available: List[AccelerationAPI] = []
        plat = cls.detect_platform()["os"]

        if plat == "windows":
            available.append(AccelerationAPI.DIRECTML)
        elif plat == "macos":
            available.append(AccelerationAPI.METAL)
            available.append(AccelerationAPI.VIDEOTOOLBOX)
        elif plat == "linux":
            available.append(AccelerationAPI.VULKAN)

        # Check for CUDA via PyTorch or environment if present
        try:
            import torch
            if torch.cuda.is_available():
                available.append(AccelerationAPI.CUDA)
                available.append(AccelerationAPI.NVENC)
                available.append(AccelerationAPI.NVDEC)
        except Exception:
            # Check NVIDIA CLI or driver path presence
            if shutil.which("nvidia-smi") is not None:
                available.append(AccelerationAPI.CUDA)
                available.append(AccelerationAPI.NVENC)
                available.append(AccelerationAPI.NVDEC)

        return available

    @classmethod
    def get_complete_hardware_profile(cls) -> Dict[str, Any]:
        plat = cls.detect_platform()
        res = cls.detect_system_resources()
        acc = cls.detect_acceleration_apis()
        return {
            "platform": plat,
            "resources": res,
            "acceleration": [a.value for a in acc],
            "has_gpu_acceleration": len(acc) > 0,
        }
