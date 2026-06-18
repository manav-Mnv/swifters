# Club Attendance System

Attendance system scaffold for Swift Coding Club with:

- `frontend/`: static kiosk and admin pages for Vercel hosting
- `backend/`: Flask API, SQLite storage, Excel import, geo boundary checks, and attendance export

## What is included

- Admin login with in-memory lockout
- Active event creation
- Excel `.xlsx` import with required-column validation
- Geo boundary settings per event using Haversine distance
- Student location gate before enrollment and face verification
- Face registration endpoint and a DeepFace-ready verifier with a development fallback
- Biometric attendance marking and manual override support
- Attendance export to `.xlsx`

## Local setup

1. Copy `backend/.env.example` to `backend/.env` and fill in real values.
2. Install backend dependencies:
   `py -m pip install -r backend/requirements.txt`
3. Start the backend:
   `py backend/run.py`
4. Serve `frontend/` with any static server or deploy it to Vercel.
5. Update `frontend/config.js` with your backend URL or Cloudflare Tunnel URL.

## Cloudflare Tunnel

1. Install `cloudflared` on the Mac host.
2. Run your Flask app on `localhost:5000`.
3. Start the tunnel:
   `cloudflared tunnel --url http://localhost:5000`
4. Put the generated HTTPS URL into `frontend/config.js` and `backend/.env`.

## Notes

- Real DeepFace verification activates only when `deepface` and its native dependencies are installed on the Mac.
- Without DeepFace, the backend falls back to a development-only placeholder verifier so the rest of the system remains testable.
