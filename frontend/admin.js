const apiBase = window.APP_CONFIG.BACKEND_URL.replace(/\/$/, "");

const adminStatus = document.getElementById("adminStatus");
const passwordInput = document.getElementById("passwordInput");
const loginBtn = document.getElementById("loginBtn");
const createEventBtn = document.getElementById("createEventBtn");
const importBtn = document.getElementById("importBtn");
const importSummary = document.getElementById("importSummary");
const membersTable = document.getElementById("membersTable");
const attendanceTable = document.getElementById("attendanceTable");
const attendanceBadge = document.getElementById("attendanceBadge");
const saveGeoBtn = document.getElementById("saveGeoBtn");
const exportBtn = document.getElementById("exportBtn");
const resetBtn = document.getElementById("resetBtn");
const manualMarkBtn = document.getElementById("manualMarkBtn");
const faceVideo = document.getElementById("faceVideo");
const faceCanvas = document.getElementById("faceCanvas");
const faceEnrollment = document.getElementById("faceEnrollment");
const startFaceCameraBtn = document.getElementById("startFaceCameraBtn");
const registerFaceBtn = document.getElementById("registerFaceBtn");

let faceStream = null;

function setStatus(message, tone = "") {
  adminStatus.textContent = message;
  adminStatus.className = `status${tone ? ` ${tone}` : ""}`;
}

async function api(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    credentials: "include",
    ...options
  });
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : null;
  if (!response.ok) {
    throw new Error(payload?.error || "Request failed");
  }
  return payload;
}

const map = L.map("map").setView([22.3072, 73.1812], 16);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

let marker = null;
let circle = null;

function drawGeo(lat, lng, radius) {
  if (marker) {
    map.removeLayer(marker);
  }
  if (circle) {
    map.removeLayer(circle);
  }
  marker = L.marker([lat, lng]).addTo(map);
  circle = L.circle([lat, lng], { radius }).addTo(map);
  map.setView([lat, lng], 17);
}

map.on("click", (event) => {
  const { lat, lng } = event.latlng;
  document.getElementById("centerLat").value = lat.toFixed(6);
  document.getElementById("centerLng").value = lng.toFixed(6);
  drawGeo(lat, lng, Number(document.getElementById("radiusMetres").value || 100));
});

document.getElementById("radiusMetres").addEventListener("input", () => {
  const lat = Number(document.getElementById("centerLat").value);
  const lng = Number(document.getElementById("centerLng").value);
  const radius = Number(document.getElementById("radiusMetres").value || 100);
  if (Number.isFinite(lat) && Number.isFinite(lng)) {
    drawGeo(lat, lng, radius);
  }
});

async function login() {
  await api("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: passwordInput.value })
  });
  setStatus("Admin logged in.", "success");
  await Promise.all([loadMembers(), loadAttendance(), loadGeo()]);
}

async function createEvent() {
  await api("/api/create-event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: document.getElementById("eventName").value,
      date: document.getElementById("eventDate").value,
      club_name: document.getElementById("clubName").value
    })
  });
  setStatus("Active event created.", "success");
  await loadGeo();
}

async function importExcel() {
  const file = document.getElementById("excelInput").files[0];
  if (!file) {
    throw new Error("Select an .xlsx file first");
  }
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${apiBase}/api/import`, {
    method: "POST",
    credentials: "include",
    body: formData
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Import failed");
  }
  importSummary.textContent = `Imported ${payload.imported} members. ${payload.warnings.length ? payload.warnings.join(" | ") : "No warnings."}`;
  await loadMembers();
}

async function loadMembers() {
  const payload = await api("/api/members");
  faceEnrollment.setAttribute("list", "adminEnrollmentList");
  let datalist = document.getElementById("adminEnrollmentList");
  if (!datalist) {
    datalist = document.createElement("datalist");
    datalist.id = "adminEnrollmentList";
    document.body.appendChild(datalist);
  }
  datalist.innerHTML = payload.members.map((member) => `<option value="${member.enrollment}">${member.name}</option>`).join("");
  membersTable.innerHTML = payload.members.map((member) => `
    <tr>
      <td>${member.enrollment}</td>
      <td>${member.name}</td>
      <td>${member.face_registered ? "Registered" : "Pending"}</td>
    </tr>
  `).join("");
}

async function loadAttendance() {
  const payload = await api("/api/attendance");
  attendanceBadge.textContent = `Present: ${payload.attendance.length} / ${payload.total_members}`;
  attendanceTable.innerHTML = payload.attendance.map((row) => `
    <tr>
      <td>${row.name}</td>
      <td>${row.enrollment}</td>
      <td>${row.timestamp_ist}</td>
      <td>${row.method}</td>
    </tr>
  `).join("");
}

async function loadGeo() {
  const payload = await api("/api/geo/get");
  if (!payload.settings) {
    return;
  }
  document.getElementById("centerLat").value = payload.settings.center_lat ?? "";
  document.getElementById("centerLng").value = payload.settings.center_lng ?? "";
  document.getElementById("radiusMetres").value = payload.settings.radius_metres ?? 100;
  document.getElementById("geoEnabled").value = payload.settings.enabled ? "1" : "0";
  if (payload.settings.center_lat != null && payload.settings.center_lng != null) {
    drawGeo(payload.settings.center_lat, payload.settings.center_lng, payload.settings.radius_metres);
  }
}

async function saveGeo() {
  const lat = document.getElementById("centerLat").value;
  const lng = document.getElementById("centerLng").value;
  const radius = document.getElementById("radiusMetres").value;
  const enabled = document.getElementById("geoEnabled").value === "1";
  await api("/api/geo/set", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      center_lat: lat ? Number(lat) : null,
      center_lng: lng ? Number(lng) : null,
      radius_metres: Number(radius),
      enabled
    })
  });
  setStatus("Geo boundary saved.", "success");
  if (lat && lng) {
    drawGeo(Number(lat), Number(lng), Number(radius));
  }
}

async function exportAttendance() {
  window.location.href = `${apiBase}/api/export`;
}

async function resetSession() {
  await api("/api/reset-session", { method: "POST" });
  setStatus("Verification session reset.", "success");
}

async function manualMark() {
  await api("/api/mark", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      enrollment: document.getElementById("manualEnrollment").value,
      method: "manual",
      admin_note: document.getElementById("manualNote").value
    })
  });
  setStatus("Manual attendance recorded.", "success");
  await loadAttendance();
}

async function startFaceCamera() {
  faceStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
  faceVideo.srcObject = faceStream;
  setStatus("Face registration camera is live.", "success");
}

function captureFaceImage() {
  faceCanvas.width = faceVideo.videoWidth || 640;
  faceCanvas.height = faceVideo.videoHeight || 480;
  const context = faceCanvas.getContext("2d");
  context.drawImage(faceVideo, 0, 0, faceCanvas.width, faceCanvas.height);
  return faceCanvas.toDataURL("image/jpeg", 0.8);
}

async function registerFace() {
  await api("/api/register-face", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      enrollment: faceEnrollment.value,
      image_data: captureFaceImage()
    })
  });
  setStatus("Face registered successfully.", "success");
  await loadMembers();
}

loginBtn.addEventListener("click", () => login().catch((error) => setStatus(error.message, "error")));
createEventBtn.addEventListener("click", () => createEvent().catch((error) => setStatus(error.message, "error")));
importBtn.addEventListener("click", () => importExcel().catch((error) => setStatus(error.message, "error")));
saveGeoBtn.addEventListener("click", () => saveGeo().catch((error) => setStatus(error.message, "error")));
exportBtn.addEventListener("click", () => exportAttendance());
resetBtn.addEventListener("click", () => resetSession().catch((error) => setStatus(error.message, "error")));
manualMarkBtn.addEventListener("click", () => manualMark().catch((error) => setStatus(error.message, "error")));
startFaceCameraBtn.addEventListener("click", () => startFaceCamera().catch((error) => setStatus(error.message, "error")));
registerFaceBtn.addEventListener("click", () => registerFace().catch((error) => setStatus(error.message, "error")));
