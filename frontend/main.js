const apiBase = window.APP_CONFIG.BACKEND_URL.replace(/\/$/, "");

const geoStatus = document.getElementById("geoStatus");
const requestLocationBtn = document.getElementById("requestLocationBtn");
const checkinPanel = document.getElementById("checkinPanel");
const enrollmentInput = document.getElementById("enrollmentInput");
const enrollmentList = document.getElementById("enrollmentList");
const lookupBtn = document.getElementById("lookupBtn");
const memberStatus = document.getElementById("memberStatus");
const memberCard = document.getElementById("memberCard");
const startCameraBtn = document.getElementById("startCameraBtn");
const verifyBtn = document.getElementById("verifyBtn");
const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const successOverlay = document.getElementById("successOverlay");
const successName = document.getElementById("successName");

let geoAllowed = false;
let currentMember = null;
let mediaStream = null;

function setStatus(element, message, tone = "") {
  element.textContent = message;
  element.className = `status${tone ? ` ${tone}` : ""}`;
  element.classList.remove("hidden");
}

async function api(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });
  if (response.headers.get("content-type")?.includes("application/json")) {
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || data.message || "Request failed");
    }
    return data;
  }
  if (!response.ok) {
    throw new Error("Request failed");
  }
  return response;
}

async function loadMembers() {
  try {
    const data = await api("/api/geo/get");
    if (!data.event) {
      setStatus(geoStatus, "No active event is configured yet.", "error");
      requestLocationBtn.disabled = true;
      return;
    }
    const membersData = await fetch(`${apiBase}/api/public-members`, { credentials: "include" });
    if (membersData.ok) {
      const payload = await membersData.json();
      enrollmentList.innerHTML = payload.members.map((member) => `<option value="${member.enrollment}"></option>`).join("");
    }
  } catch (error) {
    setStatus(geoStatus, error.message, "error");
  }
}

async function requestLocation() {
  if (!navigator.geolocation) {
    setStatus(geoStatus, "This browser does not support geolocation.", "error");
    return;
  }

  setStatus(geoStatus, "Checking whether you are inside the venue boundary.");
  navigator.geolocation.getCurrentPosition(async (position) => {
    try {
      const data = await api("/api/check-location", {
        method: "POST",
        body: JSON.stringify({
          lat: position.coords.latitude,
          lng: position.coords.longitude
        })
      });
      geoAllowed = data.allowed;
      if (!data.allowed) {
        checkinPanel.classList.add("hidden");
        setStatus(geoStatus, `${data.message}. Distance: ${data.distance_metres} m`, "error");
        return;
      }
      setStatus(geoStatus, data.message || "You are inside the venue boundary.", "success");
      checkinPanel.classList.remove("hidden");
    } catch (error) {
      setStatus(geoStatus, error.message, "error");
    }
  }, (error) => {
    setStatus(geoStatus, `Location error: ${error.message}`, "error");
  }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
}

async function lookupMember() {
  if (!geoAllowed) {
    setStatus(memberStatus, "Location must pass before member lookup.", "error");
    return;
  }
  try {
    const data = await api(`/api/member/${encodeURIComponent(enrollmentInput.value.trim())}`);
    currentMember = data.member;
    const alreadyMarked = Boolean(currentMember.already_marked);
    memberCard.innerHTML = `
      <div class="badge">${alreadyMarked ? "Already marked" : "Ready for verification"}</div>
      <h3 style="margin-top:14px;">${currentMember.name}</h3>
      <p class="muted">${currentMember.enrollment}</p>
      <p>${currentMember.department} · ${currentMember.course}</p>
      <p>${currentMember.institute}</p>
    `;
    if (alreadyMarked) {
      setStatus(memberStatus, "Attendance is already marked for this enrollment.", "error");
      startCameraBtn.disabled = true;
      verifyBtn.disabled = true;
      return;
    }
    setStatus(memberStatus, "Member loaded. Start the camera to continue.", "success");
    startCameraBtn.disabled = false;
    verifyBtn.disabled = true;
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus(memberStatus, "Camera access is not supported in this browser.", "error");
      startCameraBtn.disabled = true;
    }
  } catch (error) {
    currentMember = null;
    startCameraBtn.disabled = true;
    verifyBtn.disabled = true;
    memberCard.textContent = "Member details appear here after enrollment lookup.";
    setStatus(memberStatus, error.message, "error");
  }
}

async function startCamera() {
  mediaStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
  video.srcObject = mediaStream;
  verifyBtn.disabled = false;
  setStatus(memberStatus, "Camera is live. Look at the camera and verify.", "success");
}

function captureFrame() {
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const context = canvas.getContext("2d");
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.72);
}

async function verifyAndMark() {
  if (!currentMember) {
    return;
  }
  verifyBtn.disabled = true;
  setStatus(memberStatus, "Verifying your face. Please hold still.");
  try {
    const imageData = captureFrame();
    const verifyResult = await api("/api/verify", {
      method: "POST",
      body: JSON.stringify({
        enrollment: currentMember.enrollment,
        image_data: imageData
      })
    });
    if (!verifyResult.matched) {
      setStatus(memberStatus, `Face not recognized yet. Confidence ${verifyResult.confidence}%.`, "error");
      verifyBtn.disabled = false;
      return;
    }
    await api("/api/mark", {
      method: "POST",
      body: JSON.stringify({
        enrollment: currentMember.enrollment,
        method: "biometric"
      })
    });
    successName.textContent = `${currentMember.name}, attendance marked`;
    successOverlay.classList.add("visible");
    window.setTimeout(resetKiosk, 3000);
  } catch (error) {
    setStatus(memberStatus, error.message, "error");
    verifyBtn.disabled = false;
  }
}

function resetKiosk() {
  successOverlay.classList.remove("visible");
  enrollmentInput.value = "";
  currentMember = null;
  memberCard.textContent = "Member details appear here after enrollment lookup.";
  setStatus(memberStatus, "Ready for the next student.", "success");
  startCameraBtn.disabled = true;
  verifyBtn.disabled = true;
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    video.srcObject = null;
    mediaStream = null;
  }
}

requestLocationBtn.addEventListener("click", requestLocation);
lookupBtn.addEventListener("click", lookupMember);
startCameraBtn.addEventListener("click", startCamera);
verifyBtn.addEventListener("click", verifyAndMark);

loadMembers();
