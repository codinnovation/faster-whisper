# 🚀 Quick Coolify Deployment Guide

## What Happened?
Your first deployment failed because Docker tried to install **277 packages** (including unnecessary GUI tools) when installing ffmpeg. This has been fixed!

## ✅ What I Fixed
1. **Optimized Dockerfile** - Now uses `--no-install-recommends` to install only essential packages
2. **Added minimal Dockerfile** - Ultra-lightweight backup option
3. **Better health checks** - Uses built-in Python libraries instead of external dependencies

## 📋 Deploy to Coolify Now

### Step 1: Push Your Code to Git
```bash
cd d:\CODE - REPO\faster-whisper
git add .
git commit -m "Optimized Dockerfile for Coolify deployment"
git push
```

### Step 2: In Coolify Dashboard

1. **Create New Resource** → **Public Repository** or **Private Git**
2. **Paste your repository URL**

### Step 3: Configure Build Settings

| Setting | Value |
|---------|-------|
| **Build Pack** | `Dockerfile` |
| **Dockerfile Location** | `./Dockerfile` |
| **Port** | `8000` |

### Step 4: Environment Variables

Add these in the **Environment** tab:

```bash
WHISPER_MODEL_SIZE=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

### Step 5: Resource Allocation

- **Memory**: `2GB` minimum (4GB recommended)
- **CPU**: `1-2 cores`

### Step 6: Optional - Persistent Storage

To avoid re-downloading the model on every deployment:

- **Add Volume**
- **Mount Path**: `/root/.cache/huggingface`
- **Size**: `5GB`

### Step 7: Deploy!

Click **Deploy** and wait 5-10 minutes for first build.

---

## 🆘 If Build Still Fails

### Option A: Use Minimal Dockerfile
In Coolify, change **Dockerfile Location** to:
```
./Dockerfile.minimal
```

### Option B: Check Build Logs
1. Go to Coolify deployment logs
2. Look for the specific error
3. Common issues:
   - **Timeout**: Increase build timeout in Coolify settings
   - **Out of memory**: Increase build memory limit
   - **Network issues**: Retry the build

---

## ✅ After Successful Deployment

Your API will be available at: `https://your-app.coolify.io`

### Test It:
```bash
# Health check
curl https://your-app.coolify.io/health

# API documentation
# Visit: https://your-app.coolify.io/docs
```

### Upload an audio file:
```bash
curl -X POST "https://your-app.coolify.io/transcribe" \
  -F "file=@your-audio.mp3" \
  -F "language=en"
```

---

## 🎯 Model Size Guide

| Model | Accuracy | Speed | Memory | Best For |
|-------|----------|-------|--------|----------|
| `tiny` | ⭐⭐ | ⚡⚡⚡⚡ | 1GB | Testing, demos |
| `base` | ⭐⭐⭐ | ⚡⚡⚡ | 2GB | **Recommended start** |
| `small` | ⭐⭐⭐⭐ | ⚡⚡ | 3GB | Production quality |
| `medium` | ⭐⭐⭐⭐⭐ | ⚡ | 5GB | High accuracy needed |

Start with `base` and upgrade if you need better accuracy!

---

## 📞 Need Help?

1. Check Coolify deployment logs
2. Verify environment variables are set
3. Ensure port 8000 is configured
4. Test health endpoint: `/health`

**You're all set!** 🎉
