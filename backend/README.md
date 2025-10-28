# 🩸 BloodBridge Backend API

Backend API for BloodBridge - Emergency Blood Donor Platform

## 🚀 Deploy on Render

### Quick Deploy Steps:

1. **Push to GitHub:**
   ```bash
   cd backend
   git init
   git add .
   git commit -m "Backend ready for deployment"
   git remote add origin YOUR_GITHUB_REPO
   git push -u origin main
   ```

2. **Deploy on Render:**
    - Go to [render.com](https://render.com)
    - Click "New +" → "Web Service"
    - Connect your GitHub repository
    - Select `backend` directory
    - Settings:
        - **Name:** bloodbridge-api
        - **Environment:** Python 3
        - **Build Command:** `pip install -r requirements.txt`
        - **Start Command:** `gunicorn app:app`
        - **Plan:** Free

3. **Environment Variables (Important!):**

   Add these in Render Dashboard → Environment:

   ```
   SECRET_KEY=your-secret-key-change-this
   GMAIL_ADDRESS=bloodbridge2025@gmail.com
   GMAIL_APP_PASSWORD=gxzmrlbmhkvpmykl
   ADMIN_PASSWORD=admin123
   TWILIO_ACCOUNT_SID=ACbb0963a2a72de9651d993910293cdfeb
   TWILIO_AUTH_TOKEN=a266914995fe5a8b4b7d4a397da86b65
   TWILIO_PHONE_NUMBER=+16816412288
   GOOGLE_APPLICATION_CREDENTIALS=firebase_config.json
   ```

4. **Firebase Credentials:**
    - Upload `firebase_config.json` via Render dashboard
    - Or set as environment variable (Base64 encoded)

5. **Get Backend URL:**
   ```
   Your API will be live at:
   https://bloodbridge-api.onrender.com
   ```

6. **Use in Frontend:**
    - Copy the backend URL
    - Update frontend `config.js` with this URL
    - Deploy frontend separately

---

## 🔌 API Endpoints:

### Health Check

```
GET /api/health
```

### Register Donor

```
POST /api/register
Body: {name, email, password, blood_group, address, city, state, phone}
```

### Search Donors

```
POST /api/search
Body: {blood_group, city}
```

### Emergency Alert

```
POST /api/emergency
Body: {requester_name, hospital_name, blood_group, city, state, address, notes, g-recaptcha-response}
```

### Admin Login

```
POST /api/admin/login
Body: {password}
```

### Get All Donors (Admin)

```
POST /api/admin/donors
Body: {password}
```

### Verify Donor

```
POST /api/admin/verify/<donor_id>
```

### Delete Donor

```
DELETE /api/admin/delete/<donor_id>
```

### Send OTP

```
POST /api/send-otp
Body: {phone}
```

### Verify OTP

```
POST /api/verify-otp
Body: {phone, code}
```

---

## ✅ Features:

- ✅ CORS enabled for frontend
- ✅ Firebase Firestore database
- ✅ Gmail SMTP for emergency alerts
- ✅ Twilio SMS for OTP
- ✅ Spam protection (IP-based rate limiting)
- ✅ CAPTCHA verification
- ✅ Parallel email sending
- ✅ Admin authentication
- ✅ Complete REST API

---

## 🧪 Test Locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python app.py

# Test endpoints
curl http://localhost:5000/api/health
```

---

## 📊 Free Tier Limits (Render):

- ✅ 750 hours/month free
- ✅ Auto-deploy from GitHub
- ✅ HTTPS included
- ⚠️ Sleeps after 15 min inactivity
- ⚠️ Cold start ~30 seconds

---

## 🔒 Security:

- ✅ Environment variables for secrets
- ✅ CORS configured
- ✅ Rate limiting active
- ✅ CAPTCHA verification
- ✅ IP tracking
- ✅ Admin password protection

---

## 📚 Documentation:

- Main README: See root directory
- API Docs: This file
- Frontend Setup: See `../frontend/README.md`

---

**Backend is production-ready! Deploy on Render and get your API URL! 🚀**
