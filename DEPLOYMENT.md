# 🚀 Deployment Guide - GitHub + Cloudflare + Cloud Run

## What You Have Now

✅ Complete voice-enabled web application  
✅ Mobile-responsive interface with beautiful UI  
✅ Full backend API with Whisper + TTS  
✅ Dockerized Python service ready for Cloud Run or Render  
✅ PWA support (installable on phone)  
✅ `.env` ignored by git so secrets stay out of the repository  

---

## 🎯 Recommended Deployment Path

This repository is a **Python containerized web app**, not a Cloudflare Worker.
The lowest-risk path is:

1. Push the repository to GitHub  
2. Deploy the app to **Google Cloud Run**  
3. Put **Cloudflare** in front of it for DNS, SSL, and your custom domain  

Use Render only if you prefer it over Cloud Run.

---

## Step 1: Create or Use a GitHub Repository

1. Go to [github.com](https://github.com) and sign in  
2. Create a new repository or choose an existing private repository  
3. Do **not** commit API keys or a filled-in `.env` file  
4. Keep `.env.example` committed as the template  

## Step 2: Push This Code to GitHub

From `/home/runner/work/Super-Claude/Super-Claude`:

```bash
cd /home/runner/work/Super-Claude/Super-Claude

# If needed, initialize git
# git init

git add .
git commit -m "Initial commit"

# Connect to GitHub (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git branch -M main
git push -u origin main
```

## Step 3: Deploy to Google Cloud Run

1. Install and sign in to the [Google Cloud SDK](https://cloud.google.com/sdk)  
2. Pick a Google Cloud project  
3. Enable:
   - Cloud Run
   - Artifact Registry
   - Secret Manager
4. Store your API key in Secret Manager  
5. Deploy from the repository root:

```bash
gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com

echo -n "sk-your-openai-key" | \
  gcloud secrets create openai-api-key --data-file=-

PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding openai-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud run deploy conductor-agent \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets OPENAI_API_KEY=openai-api-key:latest
```

6. Open the deploy URL and check `/health`  
7. Confirm `api_keys_configured` is `true`

## Step 4: Add Cloudflare in Front of the App

1. Add your domain to [Cloudflare](https://www.cloudflare.com/)  
2. In Cloud Run, add a custom domain for your service, such as `app.example.com`  
3. Copy the DNS record values Google provides  
4. In Cloudflare DNS, create the required record  
5. Leave the record proxied if you want Cloudflare SSL/CDN in front  
6. Wait for certificate and DNS propagation  
7. Test:
   - `https://your-domain/`
   - `https://your-domain/health`

## Step 5: Optional Render Path

If you do not want Cloud Run, the repo also includes `render.yaml`:

1. Go to [render.com](https://render.com)  
2. Sign in with GitHub  
3. Create a new Web Service from this repository  
4. Let Render detect `render.yaml`  
5. Set `OPENAI_API_KEY` in the Render dashboard  
6. Deploy and test `/health`  
7. Then connect Cloudflare to the Render hostname or custom domain

---

## 📱 Using Your Voice App

### On Your Phone:

1. Open the Render URL in your phone's browser  
2. Grant microphone permission when prompted  
3. Tap the big **🎤 button**  
4. Start talking!  
5. Get voice responses back  

### Install as App (PWA):

#### iPhone (Safari):
1. Open the URL in Safari  
2. Tap the **Share** button  
3. Tap **"Add to Home Screen"**  
4. Tap **"Add"**  

#### Android (Chrome):
1. Open the URL in Chrome  
2. Tap the **⋮ menu**  
3. Tap **"Add to Home screen"**  
4. Tap **"Add"**  

Now you have an app icon on your home screen! 🎉

---

## ⚙️ Settings

### Change Voice:

1. Open settings in the web app (⚙️ icon)  
2. Select voice:
   - **Nova**: Clear female (default, recommended)
   - **Alloy**: Neutral  
   - **Echo**: Male  
   - **Onyx**: Deep male  
   - **Shimmer**: Soft female  

---

## 🔧 Troubleshooting

### "Can I deploy this directly with workers-sdk?"
- Not as-is. This repo is a Python server app, not a Cloudflare Worker.
- A Workers deploy would require a separate entrypoint and architectural changes.

### "Cloudflare is up but the app fails"
- Confirm the Cloud Run or Render origin works before testing through Cloudflare
- Check that your DNS record matches the target provided by your host
- Verify SSL mode and wait for DNS propagation

### "Microphone access denied"
- Go to browser settings → Permissions → Allow microphone for this site

### "API error"
- Check that `OPENAI_API_KEY` is set correctly in Cloud Run Secret Manager or Render dashboard
- Make sure you have OpenAI API credits

### "No response"
- Check Cloud Run logs or Render logs  
- Make sure the ingestion completed (vector database has data)

### App won't install
- Use Safari on iPhone or Chrome on Android  
- Some browsers don't support PWA installation

---

## 💰 Costs

### Cloud Run Hosting:
- Usage-based pricing  
- Usually the best fit for this repo because the container is already ready

### Render Hosting:
- **Free tier**: Free! (sleeps after 15min inactivity)  
- **Paid tier**: $7/month (always on, faster)  

### OpenAI API:
- **Whisper**: ~$0.01 per conversation  
- **TTS**: ~$0.02 per response  
- **GPT-4o-mini**: ~$0.001 per query  

**Total**: ~$15-30/month for moderate use

---

## 🎊 You're Done!

You now have:
- ✅ Voice AI accessible from your phone  
- ✅ Remembers all your conversations  
- ✅ Works anywhere with internet  
- ✅ Can sit behind your Cloudflare domain  
- ✅ Professional UI  
- ✅ Installable as an app  

**Your conductor agent is live behind GitHub + Cloud Run + Cloudflare! 🚀**

Need help? Check your Cloud Run or Render logs and confirm the API key is being injected securely.
