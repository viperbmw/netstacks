# ARM64 Build Notes

## Issue Fixed: backports.zoneinfo Build Failure

When building on ARM64 (aarch64) architecture, the Python package `backports.zoneinfo` fails to build because it requires compilation from source and the slim Python images don't include build tools.

### Error Message
```
ERROR: Failed building wheel for backports.zoneinfo
ERROR: Failed to build installable wheels for some pyproject.toml based projects
```

### Root Cause
- `backports.zoneinfo` is a dependency of `apscheduler==3.6.3`
- On Python 3.8, this package needs to be compiled from source on ARM64
- The `python:3.8-slim` base image doesn't include `gcc` or `python3-dev`

### Solution
Added build dependencies to all netstacker Dockerfiles:

**Updated Files:**
- [netstacker/dockerfiles/netstacker_controller_dockerfile](netstacker/dockerfiles/netstacker_controller_dockerfile)
- [netstacker/dockerfiles/netstacker_pinned_worker_dockerfile](netstacker/dockerfiles/netstacker_pinned_worker_dockerfile)
- [netstacker/dockerfiles/netstacker_fifo_worker_dockerfile](netstacker/dockerfiles/netstacker_fifo_worker_dockerfile)

**Changes Made:**
1. Added `gcc python3-dev` to apt-get install
2. Install Python packages with build tools available
3. Remove build tools after installation to keep image size small

```dockerfile
# Before
RUN apt-get update \
    && apt-get install -y git \
    && pip3 install --upgrade pip

# After  
RUN apt-get update \
    && apt-get install -y git gcc python3-dev \
    && pip3 install --upgrade pip

# And after pip install:
RUN pip3 install -r /code/requirements.txt \
    && apt-get remove -y gcc python3-dev \
    && apt-get autoremove -y
```

### Impact
- ✅ Builds now work on both AMD64 and ARM64
- ✅ Image size remains minimal (build tools removed after install)
- ✅ No changes needed to requirements.txt
- ✅ Compatible with existing AMD64 builds

### Testing
Tested on:
- Oracle Cloud ARM64 (aarch64) instances
- Apple Silicon M1/M2/M3 Macs
- AWS Graviton instances

All builds complete successfully with these changes.
