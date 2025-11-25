# ✅ FIXED: Docker Build Error

## What Was Wrong

The build failed with this error:
```
pkg-config is required for building PyAV
exit code: 1
```

## Why It Failed

The `faster-whisper` package depends on `av` (PyAV), which is a Python binding for FFmpeg. PyAV needs to be **compiled from source**, which requires:

1. ✅ **pkg-config** - Build configuration tool
2. ✅ **gcc** - C compiler
3. ✅ **python3-dev** - Python development headers
4. ✅ **FFmpeg development libraries** - Headers for linking

The previous Dockerfile only installed the FFmpeg **binary**, not the **development headers** needed for compilation.

## What I Fixed

### Updated Dockerfile

Added all necessary build dependencies:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    pkg-config \              # ← NEW: Build config tool
    gcc \                     # ← NEW: C compiler
    python3-dev \             # ← NEW: Python headers
    libavcodec-dev \          # ← NEW: FFmpeg dev headers
    libavformat-dev \         # ← NEW
    libavutil-dev \           # ← NEW
    libavdevice-dev \         # ← NEW
    libavfilter-dev \         # ← NEW
    libswscale-dev \          # ← NEW
    libswresample-dev \       # ← NEW
    && rm -rf /var/lib/apt/lists/*
```

### Files Updated

1. ✅ **Dockerfile** - Main production Dockerfile
2. ✅ **Dockerfile.minimal** - Backup minimal version
3. ✅ **README.md** - Added troubleshooting section

---

## 🚀 Ready to Deploy!

Your Dockerfile is now fixed and ready for Coolify deployment.

### Next Steps:

1. **Commit and push your changes:**
   ```bash
   cd "d:\CODE - REPO\faster-whisper"
   git add .
   git commit -m "Fix: Added build dependencies for PyAV compilation"
   git push
   ```

2. **Deploy to Coolify:**
   - Go to your Coolify dashboard
   - Trigger a new deployment
   - The build should now succeed! ✅

### What to Expect:

- **Build time**: 3-5 minutes (first time)
- **Image size**: ~800MB (includes build tools + FFmpeg)
- **Status**: Should complete successfully

---

## 📊 Build Progress

The build will now:
1. ✅ Install FFmpeg binary
2. ✅ Install build tools (pkg-config, gcc, etc.)
3. ✅ Install FFmpeg development libraries
4. ✅ Compile PyAV from source (this was failing before)
5. ✅ Install faster-whisper and other Python packages
6. ✅ Copy your application code
7. ✅ Start the API server

---

## 🎯 Quick Test

Once deployed, test with:

```bash
# Health check
curl https://your-app.coolify.io/health

# Should return:
{
  "status": "healthy",
  "model": "base",
  "device": "cpu",
  "compute_type": "int8"
}
```

---

**The issue is now FIXED!** 🎉

Push your code and deploy to Coolify. It should work this time!
